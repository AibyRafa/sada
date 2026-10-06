r"""Sada — measured cost of one check (criterion: operational realism, "supported by measurements").

  .venv-role4\Scripts\python scripts\timing.py            -> reports/role5/timing.md

Times the whole pipeline (voice + generated + original search + verdict) on real project clips of every kind,
on THIS machine. Nothing is estimated: every number below is measured when the script runs.
"""

from __future__ import annotations

import datetime as dt
import os
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

KINDS = ("real", "fake", "spliced", "cropped")


def peak_memory_mb() -> float | None:
    """Peak memory of this process (Windows: peak working set; Linux/macOS: max RSS). None if unknown."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

            c = PMC()
            c.cb = ctypes.sizeof(PMC)
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.GetCurrentProcess.restype = wintypes.HANDLE      # 64-bit handle: the default int would truncate it
            try:
                get = k32.K32GetProcessMemoryInfo                 # Windows 7+: in kernel32
            except AttributeError:
                get = ctypes.WinDLL("psapi").GetProcessMemoryInfo
            get.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
            get.restype = wintypes.BOOL
            if get(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
                return c.PeakWorkingSetSize / 2**20
            return None
        import resource

        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return r / 2**20 if sys.platform == "darwin" else r / 1024
    except Exception:  # noqa: BLE001
        return None
PER_KIND = 5


def pick() -> list[Path]:
    out = []
    for k in KINDS:
        d = ROOT / "data" / k
        if d.is_dir():
            out += sorted(p for p in d.iterdir() if p.suffix.lower() in (".wav", ".mp3", ".m4a"))[:PER_KIND]
    return out


def main() -> int:
    clips = pick()
    if not clips:
        print("no clips in data/ (real, fake, spliced, cropped)")
        return 1
    t0 = time.perf_counter()
    from forensics.verdict import Analyzer
    from voiceid.audio import load_audio

    a = Analyzer(log=lambda *x: None)
    load_s = time.perf_counter() - t0
    rows = []
    for p in clips:
        audio = load_audio(p)
        dur = len(audio) / 16000.0
        t = time.perf_counter()
        v = a.analyze(audio, "ibn_baz", p.name)
        rows.append((p.parent.name, p.name, dur, time.perf_counter() - t, v.overall))
        print(f"{p.parent.name}/{p.name}: {dur:.1f} s clip -> {rows[-1][3]:.2f} s")
    secs = [r[3] for r in rows]
    per_min = [r[3] / (r[2] / 60.0) for r in rows if r[2] > 0]
    secs_sorted = sorted(secs)
    p90 = secs_sorted[min(len(secs_sorted) - 1, int(round(0.9 * (len(secs_sorted) - 1))))]
    mem = peak_memory_mb()
    lib_min = sum(o.duration for o in a.library.originals) / 60.0 if a.library.originals else 0.0
    lines = [
        f"# Sada — measured time per check ({dt.datetime.now():%Y-%m-%d %H:%M})",
        "",
        f"- Machine: {platform.system()} {platform.release()}, {platform.processor() or platform.machine()}, "
        f"{os.cpu_count()} logical CPUs, no GPU used",
        f"- Voice model available: {'yes' if a.identity is not None else 'no'}; original library: "
        f"{len(a.library.originals)} recordings, {lib_min:.1f} min",
        f"- One-time start (load models + index the library): **{load_s:.1f} s**",
        f"- Peak memory of the whole check process: **{mem:.0f} MB**" if mem else "- Peak memory: not measurable here",
        f"- Clips timed: {len(rows)} ({', '.join(f'{k}: {sum(r[0] == k for r in rows)}' for k in KINDS)})",
        "",
        "| | value |",
        "|---|---|",
        f"| median time per clip | **{statistics.median(secs):.2f} s** |",
        f"| 90th percentile | {p90:.2f} s |",
        f"| slowest clip | {max(secs):.2f} s |",
        f"| median seconds of work per minute of audio | {statistics.median(per_min):.1f} s |",
        "",
        "| clip | length (s) | time (s) | result |",
        "|---|---|---|---|",
    ]
    lines += [f"| {k}/{n} | {d:.1f} | {s:.2f} | {o} |" for k, n, d, s, o in rows]
    lines += ["", "Limits: measured on this one laptop, with the current library size. The original search grows "
              "with the library; a larger library needs re-measuring."]
    out = ROOT / "reports" / "role5" / "timing.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:15]))
    print(f"\nreport: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
