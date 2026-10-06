"""End-to-end test on role 1's REAL clips: the whole pipeline (roles 4 + 5) and the app's JSON (role 3 contract).

Run: .venv-role4\\Scripts\\python tests\\test_e2e.py
Needs the project data (data/, raw/) and, for the voice cases, Resemblyzer. Cases that cannot run are SKIPPED,
never counted as passed.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# (clip, attributed to, expected Sada overall, expected app status, needs the voice model)
CASES = [
    ("data/real/speakerA_real_70.wav", "ibn_baz", {"verified_excerpt", "verified_complete"}, "likely_authentic", True),
    ("data/spliced/speakerX_spliced_12.wav", "ibn_baz", {"misattributed"}, "inconclusive", False),
    ("data/fake/tts1_fake_01.wav", "al_alsheikh", {"likely_generated", "misattributed"}, "likely_synthetic", False),
    ("data/cropped/speakerX_cropped_04.wav", "al_fawzan", {"misattributed"}, "inconclusive", False),
]


def main() -> int:
    from forensics.verdict import Analyzer

    a = Analyzer(log=lambda *x: None)
    has_voice = a.identity is not None
    passed = failed = skipped = 0
    for rel, sid, overall_ok, app_status, needs_voice in CASES:
        path = ROOT / rel
        name = f"{rel} -> {sid}"
        if not path.is_file() or (needs_voice and not has_voice):
            print(f"SKIP {name} ({'file missing' if not path.is_file() else 'voice model not available'})")
            skipped += 1
            continue
        try:
            v = a.analyze_file(path, sid)
            assert v.overall in overall_ok, f"overall {v.overall}, expected {overall_ok}"
            try:
                from api.contract import build_result

                ident = a.identity["thresholds"]["identity"] if a.identity else None
                r = build_result(v, speaker_id=sid, duration=5.0, identity_thresholds=ident,
                                 artifact_settings=a.settings["artifact"], library_info="", processing_ms=1)
                assert r["status"] == app_status, f"app status {r['status']}, expected {app_status}"
            except ImportError:
                pass
            print(f"PASS {name}: {v.overall}")
            passed += 1
        except Exception:  # noqa: BLE001
            print(f"FAIL {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped (end-to-end on real clips)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
