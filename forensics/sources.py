"""Where each original recording comes from: data/sources.csv (one row per original).

Columns: file, sheikh_id, entity, url, title, obtained, permission, notes
  file       path as the library lists it (raw/speakerA_video1.mp3, data/originals/speakerB_fatwa18501.mp3)
  entity     the publishing body (official website / official channel)
  url        the exact page of THIS recording
  obtained   date the team downloaded it (YYYY-MM-DD)
  permission what the source allows / the permission status

Rows are matched to originals by file path, then by file name without extension (raw/x.wav == raw/x.mp3),
so converting a recording to another format keeps its source. Nothing here is guessed: an empty cell stays empty.
"""

from __future__ import annotations

import csv
from pathlib import Path

from forensics.library import project_root

SOURCES = project_root() / "data" / "sources.csv"
FIELDS = ("file", "sheikh_id", "entity", "url", "title", "obtained", "permission", "notes")


def _key(path: str) -> str:
    p = Path(str(path).replace("\\", "/"))
    return (p.parent / p.stem).as_posix().lower()


def load_sources(path: Path | None = None) -> dict[str, dict]:
    path = Path(path or SOURCES)
    if not path.is_file():
        return {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        r = {k: (r.get(k) or "").strip() for k in FIELDS}
        if r["file"]:
            out[_key(r["file"])] = r
    return out


def source_of(file: str, sources: dict[str, dict] | None = None) -> dict | None:
    """The row for an original (by its library id or any path that ends the same way)."""
    sources = load_sources() if sources is None else sources
    k = _key(file)
    if k in sources:
        return sources[k]
    for key, row in sources.items():          # absolute path given: match on the tail
        if k.endswith("/" + key):
            return row
    return None


def missing_links(originals, sources: dict[str, dict] | None = None) -> list[str]:
    """Originals of the muftis with no documented page (url). Own test recordings do not need one."""
    sources = load_sources() if sources is None else sources
    out = []
    for o in originals:
        if o.sheikh_id in ("other", "unknown"):
            continue
        row = source_of(o.id, sources)
        if not row or not row["url"]:
            out.append(o.id)
    return out
