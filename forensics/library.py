"""Library of ORIGINAL recordings (full lectures / fatwas) that a shared clip is compared with.

Where originals are looked for (all sub-folders, audio or video files):
  raw/              role 1's downloaded recordings (speakerA_video1.mp3, ...)
  data/originals/   any extra original you add later (full lectures from the official sites)
A file named "<speaker>_..." gets the mufti of that speaker in voiceid/speakers.yaml (speakerA -> ibn_baz).
When the same recording exists twice with different extensions (video1.mp4 + video1.wav) only one is used.

Decoding: .wav is read directly; anything else (mp3, m4a, mp4, ...) through ffmpeg
(the copy bundled with the `imageio-ffmpeg` package, or ffmpeg on PATH).
Fingerprints are cached in cache/role5/originals/ so each original is decoded only once.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import maximum_filter1d

from forensics.features import SR
from forensics.fingerprint import FP_FPS, fingerprint

AUDIO_EXT = {".wav", ".mp3", ".m4a", ".mp4", ".aac", ".ogg", ".opus", ".flac", ".webm", ".mkv", ".mov", ".wma"}
PREFER = [".wav", ".flac", ".m4a", ".mp3", ".mp4"]   # which copy to keep when a recording exists twice
SKIP_NAMES = {"test", "test.wav"}


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def ffmpeg_exe() -> str | None:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def _read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if sw == 2:
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    elif sw == 4:
        x = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2 ** 31
    elif sw == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128
    else:
        raise RuntimeError(f"{path.name}: unsupported wav sample width {sw}")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if sr != SR:
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(sr, SR)
        x = resample_poly(x, SR // g, sr // g).astype(np.float32)
    return x


def decode(path: str | Path, start: float | None = None, duration: float | None = None) -> np.ndarray:
    """16 kHz mono float32 of any audio/video file (optionally only [start, start+duration])."""
    path = Path(path)
    exe = ffmpeg_exe()
    if exe is None:
        if path.suffix.lower() != ".wav":
            raise RuntimeError("ffmpeg not found: run  pip install imageio-ffmpeg  (run_role5.bat does it)")
        try:
            x = _read_wav(path)
        except wave.Error:  # float wav etc.
            import soundfile as sf

            x, sr = sf.read(str(path), dtype="float32", always_2d=True)
            x = x.mean(axis=1)
            if sr != SR:
                from scipy.signal import resample_poly
                from math import gcd

                g = gcd(sr, SR)
                x = resample_poly(x, SR // g, sr // g).astype(np.float32)
        if start is not None:
            a = int(max(0.0, start) * SR)
            b = None if duration is None else a + int(duration * SR)
            x = x[a:b]
        return x
    cmd = [exe, "-v", "error", "-nostdin"]
    if start is not None:
        cmd += ["-ss", f"{max(0.0, start):.3f}"]
    cmd += ["-i", str(path)]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    r = subprocess.run(cmd, capture_output=True, check=False)
    if r.returncode != 0 and not r.stdout:
        raise RuntimeError(f"ffmpeg could not read {path.name}: {r.stderr.decode('utf-8', 'replace')[-300:]}")
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768


@dataclass
class Original:
    id: str               # path relative to the project, with / separators
    path: Path
    speaker: str          # role 1's name from the file name prefix (speakerA) or ""
    sheikh_id: str        # ibn_baz | al_fawzan | al_alsheikh | other | unknown
    duration: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["path"] = str(self.path)
        return d


def _speaker_of(name: str, mapping: dict[str, str]) -> tuple[str, str]:
    stem = name.split("_")[0]
    sid = mapping.get(stem)
    if sid is None or sid == "skip":
        return "", "unknown"
    return stem, sid


def discover(root: Path | None = None, folders: list[str] | None = None) -> list[Original]:
    root = Path(root or project_root())
    try:
        from voiceid.dataset import speaker_map

        mapping = speaker_map()
    except Exception:
        mapping = {}
    found: dict[tuple[str, str], Path] = {}
    for folder in folders or ["raw", "data/originals"]:
        base = root / folder
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in AUDIO_EXT:
                continue
            stem = p.name[: -len(p.suffix)]
            if stem.lower() in SKIP_NAMES or stem.lower().startswith(("test", "tts")):
                continue
            if any(part.lower().startswith(("tts", "_")) for part in p.relative_to(base).parts[:-1]):
                continue   # generated speech (raw/tts_tmp) is never an original
            key = (str(p.parent), stem)
            old = found.get(key)
            rank = PREFER.index(p.suffix.lower()) if p.suffix.lower() in PREFER else len(PREFER)
            if old is None or rank < (PREFER.index(old.suffix.lower()) if old.suffix.lower() in PREFER else len(PREFER)):
                found[key] = p
    out = []
    for p in sorted(found.values()):
        rid = p.relative_to(root).as_posix()
        spk, sid = _speaker_of(p.name, mapping)
        out.append(Original(rid, p, spk, sid))
    return out


class Library:
    """Fingerprints of all originals + the FFTs used to search them quickly."""

    CHUNK = 1 << 16       # FFT length in frames (about 22 minutes per chunk)
    BATCH = 32            # query windows per search pass (bounds memory for long clips)

    def __init__(self, originals: list[Original], feats: list[np.ndarray], dbs: list[np.ndarray]):
        self.originals = originals
        self.feats = feats
        self.dbs = dbs
        self._chunks = None
        self._den: dict[int, list[np.ndarray]] = {}

    def __len__(self) -> int:
        return len(self.originals)

    @property
    def hours(self) -> float:
        return sum(o.duration for o in self.originals) / 3600

    # ------------------------------------------------------------------ build / load
    @staticmethod
    def build(root: Path | None = None, cache_dir: Path | None = None, folders: list[str] | None = None,
              log=print, exclude: set[str] | None = None) -> "Library":
        root = Path(root or project_root())
        cache_dir = Path(cache_dir or root / "cache" / "role5" / "originals")
        cache_dir.mkdir(parents=True, exist_ok=True)
        originals, feats, dbs = [], [], []
        for o in discover(root, folders):
            if exclude and o.id in exclude:
                continue
            st = o.path.stat()
            key = hashlib.sha1(f"{o.id}|{st.st_size}|{int(st.st_mtime)}|fp2".encode("utf-8")).hexdigest()[:20]
            f = cache_dir / f"{key}.npz"
            if f.is_file():
                z = np.load(f)
                F, db, dur = z["F"].astype(np.float32), z["db"].astype(np.float32), float(z["dur"])
            else:
                log(f"  decoding original {o.id} ...")
                try:
                    x = decode(o.path)
                except Exception as e:  # noqa: BLE001
                    log(f"  !! skipped {o.id}: {e}")
                    continue
                if x.size < SR:
                    log(f"  !! skipped {o.id}: shorter than 1 s")
                    continue
                F, db = fingerprint(x)
                dur = x.size / SR
                np.savez_compressed(f, F=F.astype(np.float16), db=db.astype(np.float16), dur=dur)
            o.duration = dur
            originals.append(o)
            feats.append(F)
            dbs.append(db)
        return Library(originals, feats, dbs)

    def without(self, ids: set[str]) -> "Library":
        keep = [i for i, o in enumerate(self.originals) if o.id not in ids]
        return Library([self.originals[i] for i in keep], [self.feats[i] for i in keep], [self.dbs[i] for i in keep])

    def manifest(self) -> list[dict]:
        return [{"id": o.id, "speaker": o.speaker, "sheikh_id": o.sheikh_id, "minutes": round(o.duration / 60, 1)}
                for o in self.originals]

    # ------------------------------------------------------------------ search
    def _prepare(self, W: int):
        if self._chunks is None:
            self._chunks = []
            step = self.CHUNK // 2                       # chunks overlap so every window position is covered
            for oi, F in enumerate(self.feats):
                for s in range(0, max(1, len(F)), step):
                    seg = F[s: s + self.CHUNK]
                    if len(seg) < 2:
                        break
                    n = min(self.CHUNK, 1 << int(np.ceil(np.log2(len(seg) + 64))))
                    OF = np.fft.rfft(seg.T, n=n, axis=1).astype(np.complex64)
                    cs1 = np.vstack([np.zeros((1, seg.shape[1])), np.cumsum(seg, axis=0, dtype=np.float64)])
                    cs2 = np.concatenate([[0.0], np.cumsum((seg.astype(np.float64) ** 2).sum(axis=1))])
                    self._chunks.append((oi, s, len(seg), n, OF, cs1, cs2))
                    if s + self.CHUNK >= len(F):
                        break
        if W not in self._den:
            dens = []
            for (_oi, _s, ln, _n, _OF, cs1, cs2) in self._chunks:
                m = ln - W + 1
                if m <= 0:
                    dens.append(np.zeros(0))
                    continue
                s1 = cs1[W:W + m] - cs1[:m]
                var = (cs2[W:W + m] - cs2[:m]) - (s1 ** 2).sum(axis=1) / W
                dens.append(np.sqrt(np.maximum(var, 1e-6)))
            self._den[W] = dens
        return self._chunks, self._den[W]

    def search(self, windows: np.ndarray, top: int = 4, min_sep: float = 0.5) -> list[list[tuple[int, float, float]]]:
        """windows: (n, W, B) query fingerprints. For each window, best matches
        [(original index, start time in the original (s), score)], score = normalized correlation (-1..1).
        Windows are searched in small batches: the spectra of all windows at once take about 6MB per window
        (a 5-minute clip has ~1,300 windows, ~8GB), a batch of 32 stays near 200MB. Results are identical."""
        out: list[list[tuple[int, float, float]]] = []
        for b in range(0, len(windows), self.BATCH):
            out.extend(self._search(windows[b:b + self.BATCH], top, min_sep))
        return out

    def _search(self, windows: np.ndarray, top: int, min_sep: float) -> list[list[tuple[int, float, float]]]:
        n, W, B = windows.shape
        chunks, dens = self._prepare(W)
        Q = windows - windows.mean(axis=1, keepdims=True)
        qn = np.sqrt((Q.astype(np.float64) ** 2).sum(axis=(1, 2))) + 1e-9
        Qt = np.transpose(Q, (0, 2, 1))
        qf: dict[int, np.ndarray] = {}
        sep = int(min_sep * FP_FPS)
        cands: list[list[tuple[int, float, float]]] = [[] for _ in range(n)]
        for (oi, s, ln, nf, OF, _c1, _c2), den in zip(chunks, dens):
            m = ln - W + 1
            if m <= 0:
                continue
            if nf not in qf:
                qf[nf] = np.conj(np.fft.rfft(Qt, n=nf, axis=2)).astype(np.complex64)     # (n, B, F)
            corr = np.fft.irfft(np.einsum("wbf,bf->wf", qf[nf], OF), n=nf, axis=1)[:, :m]   # (n, m)
            sc = corr / (qn[:, None] * den[None, :])
            for i in range(n):
                row = sc[i]
                peaks = np.flatnonzero(row >= maximum_filter1d(row, 2 * sep + 1, mode="nearest"))
                k = min(top, peaks.size)
                idx = peaks[np.argpartition(-row[peaks], k - 1)[:k]]
                for j in idx:
                    cands[i].append((oi, (s + int(j)) / FP_FPS, float(row[j])))
        out = []
        for i in range(n):
            best: list[tuple[int, float, float]] = []
            for c in sorted(cands[i], key=lambda c: -c[2]):
                if all(c[0] != b[0] or abs(c[1] - b[1]) * FP_FPS >= sep for b in best):
                    best.append(c)
                if len(best) >= top:
                    break
            out.append(best)
        return out


def meta_json(lib: Library) -> str:
    return json.dumps(lib.manifest(), ensure_ascii=False, indent=1)
