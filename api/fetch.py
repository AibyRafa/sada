"""POST /api/v1/fetch-audio: download the audio behind a pasted link, safely.

Protections (sada-ui README):
  - only http / https, no credentials in the link;
  - the host is resolved and every address must be public (no loopback, private, link-local such as
    169.254.169.254, multicast or reserved); the connection goes to that checked address (no DNS rebinding);
  - redirects are followed by hand (max 3) and each hop is checked again;
  - hard size cap, total time limit, simple per-client rate limit;
  - the type is checked from the file's first bytes, not only from Content-Type;
  - no cookies are sent; full links are never logged.
Platform pages (YouTube, X, ...) are answered with link_not_audio.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import time
from collections import defaultdict, deque
from urllib.parse import unquote, urljoin, urlsplit

MAX_BYTES = 50 * 1024 * 1024
TOTAL_TIMEOUT = 25.0
MAX_REDIRECTS = 3
RATE = (10, 60.0)          # 10 links per minute per client
_hits: dict[str, deque] = defaultdict(deque)


class FetchError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status, self.code = status, code


def rate_ok(client: str) -> bool:
    q, now = _hits[client], time.monotonic()
    while q and now - q[0] > RATE[1]:
        q.popleft()
    if len(q) >= RATE[0]:
        return False
    q.append(now)
    return True


def _public_ip(host: str, port: int) -> str:
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise FetchError(502, "link_unreachable")
    addrs = []
    for *_x, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_link_local or ip.is_private:
            raise FetchError(400, "invalid_link")
        addrs.append(str(ip))
    if not addrs:
        raise FetchError(502, "link_unreachable")
    return addrs[0]


def sniff_audio(head: bytes) -> str | None:
    """Audio type from the first bytes, or None."""
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "audio/mpeg" if (len(head) < 2 or (head[1] & 0x06) != 0) else "audio/aac"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    if head[4:8] == b"ftyp":
        return "audio/mp4"
    if head[:4] == b"OggS":
        return "audio/ogg"
    if head[:4] == b"fLaC":
        return "audio/flac"
    return None


EXT = {"audio/mpeg": "mp3", "audio/aac": "aac", "audio/wav": "wav", "audio/mp4": "m4a", "audio/ogg": "ogg",
       "audio/flac": "flac"}
PLATFORMS = ("youtube.com", "youtu.be", "twitter.com", "x.com", "tiktok.com", "instagram.com", "facebook.com",
             "snapchat.com", "t.me", "telegram.me")


def fetch_audio(url: str) -> tuple[bytes, str, str]:
    """(audio bytes, content type, file name). Raises FetchError."""
    deadline = time.monotonic() + TOTAL_TIMEOUT
    for _hop in range(MAX_REDIRECTS + 1):
        u = urlsplit(url)
        if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
            raise FetchError(400, "invalid_link")
        host = u.hostname.lower()
        if any(host == p or host.endswith("." + p) for p in PLATFORMS):
            raise FetchError(422, "link_not_audio")
        port = u.port or (443 if u.scheme == "https" else 80)
        ip = _public_ip(host, port)
        left = max(1.0, deadline - time.monotonic())
        try:
            sock = socket.create_connection((ip, port), timeout=min(10.0, left))
            if u.scheme == "https":
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
                conn = http.client.HTTPSConnection(host, port, timeout=min(10.0, left))
            else:
                conn = http.client.HTTPConnection(host, port, timeout=min(10.0, left))
            conn.sock = sock                    # pinned to the checked address
            path = (u.path or "/") + (f"?{u.query}" if u.query else "")
            conn.request("GET", path, headers={"Host": host, "Accept": "audio/*", "User-Agent": "Sada/1.0"})
            r = conn.getresponse()
        except (OSError, http.client.HTTPException, ssl.SSLError):
            raise FetchError(502, "link_unreachable")
        if r.status in (301, 302, 303, 307, 308):
            loc = r.getheader("Location")
            conn.close()
            if not loc:
                raise FetchError(502, "link_unreachable")
            url = urljoin(url, loc)
            continue
        if r.status != 200:
            conn.close()
            raise FetchError(502, "link_unreachable")
        ctype = (r.getheader("Content-Type") or "").split(";")[0].strip().lower()
        if ctype.startswith(("text/", "application/json", "application/xml", "image/")):
            conn.close()
            raise FetchError(422, "link_not_audio")
        clen = r.getheader("Content-Length")
        if clen and clen.isdigit() and int(clen) > MAX_BYTES:
            conn.close()
            raise FetchError(413, "file_too_large")
        data = bytearray()
        try:
            while True:
                if time.monotonic() > deadline:
                    raise FetchError(502, "link_unreachable")
                chunk = r.read(65536)
                if not chunk:
                    break
                data += chunk
                if len(data) > MAX_BYTES:
                    raise FetchError(413, "file_too_large")
        except (OSError, http.client.HTTPException):
            raise FetchError(502, "link_unreachable")
        finally:
            conn.close()
        kind = sniff_audio(bytes(data[:16]))
        if kind is None:
            raise FetchError(422, "link_not_audio")
        name = unquote(u.path.rsplit("/", 1)[-1]) or "clip"
        if "." not in name:
            name = f"{name}.{EXT[kind]}"
        return bytes(data), kind, name
    raise FetchError(502, "link_unreachable")
