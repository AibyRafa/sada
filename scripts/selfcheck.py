r"""Sada — self check: is every part ready, and what happens if one is missing? (criterion: feasibility)

  .venv-role4\Scripts\python scripts\selfcheck.py

Each critical dependency is listed with its fallback, so a missing piece degrades Sada instead of breaking it.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OK, WARN, BAD = "OK  ", "WARN", "FAIL"


def has(mod: str) -> bool:
    try:
        importlib.import_module(mod)
        return True
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    rows = []

    def row(state, part, detail, fallback=""):
        rows.append((state, part, detail, fallback))

    row(OK if sys.version_info >= (3, 10) else BAD, "Python", sys.version.split()[0])
    for m in ("numpy", "scipy", "yaml"):
        row(OK if has(m) else BAD, m, "installed" if has(m) else "missing", "run_role5.bat installs it")
    row(OK if has("librosa") else WARN, "librosa (role 1 loader)", "installed" if has("librosa") else "missing",
        "16 kHz WAV still readable")
    from forensics.library import ffmpeg_exe

    row(OK if ffmpeg_exe() else WARN, "ffmpeg (mp3/m4a/mp4)", ffmpeg_exe() or "missing",
        "only WAV clips and WAV originals can be read")
    ident = has("torch") and has("resemblyzer") and has("webrtcvad")
    row(OK if ident else WARN, "Resemblyzer (voice identity, role 4)", "ready" if ident else "missing",
        "the voice question answers 'not checked'; the other 3 questions still work")
    from voiceid import thresholds as th
    from voiceid.voiceprints import VOICEPRINT_DIR, load_voiceprints

    vps = load_voiceprints(VOICEPRINT_DIR) if VOICEPRINT_DIR.is_dir() else {}
    row(OK if len(vps) == 3 else WARN, "voiceprints", f"{len(vps)} of 3", "run_role4.bat builds them")
    t = th.load()["identity"]
    row(OK if t.get("calibrated") else WARN, "identity thresholds", "calibrated" if t.get("calibrated") else
        "placeholders", "run_role4.bat calibrates them")
    from forensics.verdict import MODELS, load_settings

    s = load_settings()
    row(OK if s["compare"].get("calibrated") else WARN, "original-search thresholds",
        f"match {s['compare']['match']}, strong {s['compare']['strong']}", "defaults are used")
    art = (MODELS / "artifact.json").is_file()
    row(OK if art else WARN, "generated-speech model", "trained" if art else "missing",
        "the 'generated?' question answers 'not available'")
    row(OK, "blind splice detector", "used" if s["splice"].get("usable") else "not used (failed its test)",
        "edits are judged only against the original")
    from forensics.library import discover

    origs = discover()
    n = len(origs)
    row(OK if n else WARN, "original recordings", f"{n} files in raw/ + data/originals/",
        "without originals Sada cannot judge edits / completeness and says so")
    from forensics.sources import SOURCES, missing_links

    miss = missing_links(origs)
    row(OK if SOURCES.is_file() and not miss else WARN, "sources of the originals (data/sources.csv)",
        "every mufti recording has its page link" if SOURCES.is_file() and not miss else
        (f"{len(miss)} mufti recording(s) without a page link: " + ", ".join(miss[:4]) + (" ..." if len(miss) > 4 else "")
         if SOURCES.is_file() else "file missing"),
        "fill the url / obtained columns in data/sources.csv")
    web = has("starlette") and has("uvicorn") and has("multipart")
    row(OK if web else WARN, "web server (run_app.bat)", "ready" if web else "missing",
        "run_app.bat installs it; scripts/sada_check.py works without it")
    row(OK if (ROOT / "web" / "verify.html").is_file() else WARN, "frontend (web/)",
        "present" if (ROOT / "web" / "verify.html").is_file() else "missing")

    print("Sada self check\n")
    for st, part, detail, fb in rows:
        print(f"[{st}] {part:<38} {detail}" + (f"\n        if missing: {fb}" if fb and st != OK else ""))
    bad = sum(r[0] == BAD for r in rows)
    warn = sum(r[0] == WARN for r in rows)
    print(f"\n{len(rows) - bad - warn} ok, {warn} warnings, {bad} failures")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
