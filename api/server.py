r"""Sada API (role 3): serves the frontend (web/) and the endpoints of its contract.

  GET  /api/v1/speakers       the three muftis (voiceprints of role 4)
  POST /api/v1/verify         multipart: audio, speaker_id  ->  result JSON (api/contract.py)
  POST /api/v1/fetch-audio    {"url": ...}  ->  the audio bytes behind a link (api/fetch.py)
  GET  /api/v1/health         is everything loaded?

Run (from the project folder):  .venv-role4\Scripts\python -m api.server     then open http://127.0.0.1:8000
Uploaded audio is decoded from a temporary file that is deleted right away; nothing is kept.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import JSONResponse, RedirectResponse, Response  # noqa: E402
from starlette.routing import Mount, Route  # noqa: E402
from starlette.staticfiles import StaticFiles  # noqa: E402

from api.contract import SHEIKHS_AR, build_result, speakers_payload  # noqa: E402

WEB = ROOT / "web"
MAX_BYTES = 50 * 1024 * 1024          # = CONFIG.limits in web/js/config.js (50MB so short videos fit)
MIN_SEC, MAX_SEC = 3.0, 600.0
FORMATS = {"mp3", "wav", "m4a", "aac", "ogg", "opus", "flac",
           "mp4", "mov", "webm"}   # video: ffmpeg keeps the sound only, the picture is never analysed
TMP = ROOT / "cache" / "role3" / "tmp"

STATE: dict = {"analyzer": None, "error": None, "loading": True}
LOCK = threading.Lock()


def err(status: int, code: str) -> JSONResponse:
    return JSONResponse({"detail": {"code": code}}, status_code=status)


def load_analyzer() -> None:
    try:
        from forensics.verdict import Analyzer

        STATE["analyzer"] = Analyzer(log=lambda *a: print(*a, flush=True))
    except Exception as e:  # noqa: BLE001
        STATE["error"] = f"{type(e).__name__}: {e}"
        print("!! could not load the analyzer:", STATE["error"], flush=True)
    finally:
        STATE["loading"] = False


def decode_upload(data: bytes, ext: str) -> np.ndarray:
    from forensics.library import decode

    TMP.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(suffix=f".{ext}", dir=TMP)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        x = decode(name)
    finally:
        try:
            os.remove(name)
        except OSError:
            pass
    peak = float(np.abs(x).max()) if x.size else 0.0
    return x / peak if peak > 0 else x       # same peak normalization as role 1's loader


def run_verify(data: bytes, ext: str, speaker_id: str, filename: str) -> tuple[int, dict]:
    t0 = time.perf_counter()
    try:
        audio = decode_upload(data, ext)
    except Exception:  # noqa: BLE001
        return 422, {"detail": {"code": "invalid_file"}}
    dur = audio.size / 16000
    if dur < MIN_SEC:
        return 422, {"detail": {"code": "file_too_short"}}
    if dur > MAX_SEC:
        return 422, {"detail": {"code": "file_too_long"}}
    a = STATE["analyzer"]
    try:
        with LOCK:
            v = a.analyze(audio, speaker_id, filename)
        ident = a.identity["thresholds"]["identity"] if a.identity else None
        lib = a.library
        info = f"{len(lib)} تسجيلًا أصليًا ({lib.hours * 60:.0f} دقيقة)"
        body = build_result(v, speaker_id=speaker_id, duration=dur, identity_thresholds=ident,
                            artifact_settings=a.settings["artifact"], library_info=info,
                            processing_ms=int((time.perf_counter() - t0) * 1000))
        return 200, body
    except Exception as e:  # noqa: BLE001
        print("!! processing failure:", type(e).__name__, e, flush=True)
        return 500, {"detail": {"code": "processing_failure"}}


# ---------------------------------------------------------------- endpoints
async def speakers(_req: Request):
    from voiceid.voiceprints import VOICEPRINT_DIR

    return JSONResponse(speakers_payload(VOICEPRINT_DIR))


async def health(_req: Request):
    a = STATE["analyzer"]
    return JSONResponse({
        "loading": STATE["loading"], "ready": a is not None, "error": STATE["error"],
        "identity": bool(a and a.identity), "originals": len(a.library) if a else 0,
        "artifact_model": bool(a and a.artifact_model)})


async def verify(req: Request):
    if STATE["loading"]:
        return err(503, "backend_unavailable")
    if STATE["analyzer"] is None:
        return err(500, "processing_failure")
    try:
        form = await req.form(max_files=1, max_fields=5, max_part_size=MAX_BYTES + 1024)
    except Exception:  # noqa: BLE001
        return err(413, "file_too_large")
    up = form.get("audio")
    speaker_id = str(form.get("speaker_id") or "")
    if speaker_id not in SHEIKHS_AR:
        return err(422, "unsupported_speaker")
    if up is None or not hasattr(up, "read"):
        return err(422, "invalid_file")
    filename = (up.filename or "clip").replace("\\", "/").rsplit("/", 1)[-1]
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in FORMATS:
        return err(415, "unsupported_format")
    data = await up.read(MAX_BYTES + 1)
    await form.close()
    if len(data) > MAX_BYTES:
        return err(413, "file_too_large")
    if not data:
        return err(422, "invalid_file")
    status, body = await asyncio.to_thread(run_verify, data, ext, speaker_id, filename)
    return JSONResponse(body, status_code=status)


async def fetch_audio_ep(req: Request):
    from api.fetch import FetchError, fetch_audio, rate_ok

    client = req.client.host if req.client else "?"
    if not rate_ok(client):
        return JSONResponse({"error": {"code": "link_unreachable"}}, status_code=429)
    try:
        body = await req.json()
        url = str(body.get("url", ""))[:2048]
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": {"code": "invalid_link"}}, status_code=400)
    try:
        data, ctype, name = await asyncio.to_thread(fetch_audio, url)
    except FetchError as e:
        return JSONResponse({"error": {"code": e.code}}, status_code=e.status)
    return Response(data, media_type=ctype,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


async def home(_req: Request):
    return RedirectResponse("/index.html")


routes = [
    Route("/api/v1/speakers", speakers, methods=["GET"]),
    Route("/api/v1/health", health, methods=["GET"]),
    Route("/api/v1/verify", verify, methods=["POST"]),
    Route("/api/v1/fetch-audio", fetch_audio_ep, methods=["POST"]),
    Route("/", home),
]
if WEB.is_dir():
    routes.append(Mount("/", app=StaticFiles(directory=str(WEB), html=True), name="web"))

@contextlib.asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=load_analyzer, daemon=True).start()
    yield


app = Starlette(routes=routes, lifespan=lifespan)


def main() -> None:
    import uvicorn

    # local: 127.0.0.1:8000. Hosting (Hugging Face Spaces / Render / Docker) sets PORT -> listen on all interfaces.
    port = int(os.environ.get("PORT") or os.environ.get("SADA_PORT") or 8000)
    host = os.environ.get("SADA_HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    print(f"Sada is starting on http://{host}:{port}  (the models load in the background, ~30 s)", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)   # privacy: no IP or request log


if __name__ == "__main__":
    main()
