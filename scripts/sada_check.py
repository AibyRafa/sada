r"""Sada — one clip, the four questions, as JSON (for role 3's API).

  .venv-role4\Scripts\python scripts\sada_check.py FILE --sheikh ibn_baz

In Python (load once, then call per request):
  from forensics.verdict import Analyzer
  analyzer = Analyzer()                      # voiceprints + library + models
  result = analyzer.analyze_file("clip.mp3", "ibn_baz").to_dict()
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--sheikh", default="unknown", help="ibn_baz | al_fawzan | al_alsheikh | unknown")
    a = ap.parse_args()
    from forensics.verdict import Analyzer

    v = Analyzer(log=lambda *_: None).analyze_file(a.file, a.sheikh)
    print(v.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
