"""thresholds.yaml: the `identity` section is identical to the main Sada app's."""

from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT = Path(__file__).resolve().parent / "thresholds.yaml"


def load(path: str | Path | None = None) -> dict:
    return yaml.safe_load(Path(path or DEFAULT).read_text(encoding="utf-8")) or {}


def save(data: dict, path: str | Path | None = None) -> Path:
    p = Path(path or DEFAULT)
    p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return p


def classify(score: float, low: float, high: float) -> str:
    """Two thresholds with a gray zone: mismatch < low <= unclear < high <= match."""
    if score < low:
        return "mismatch"
    if score >= high:
        return "match"
    return "unclear"
