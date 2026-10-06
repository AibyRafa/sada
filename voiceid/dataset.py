"""Role 1's data as role 4 sees it.

Reads data/manifest.csv (columns: file, label, speaker, source, consent, notes)
and maps role 1's speaker names to mufti ids with voiceid/speakers.yaml.

Use of each clip:
  label ref,  mufti speaker  -> "ref"   (builds the voiceprint)
  label real, mufti speaker  -> "enroll", "cal" or "test" in turn (thirds per speaker):
                                 enroll = may join the voiceprint (method enroll=ref+real),
                                 cal = tunes the thresholds, test = held out for evaluate
  label real/fake, other     -> "cal" or "test" in turn, as "other voice" clips
  spliced / cropped          -> not used here (role 5 tests them)
"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from voiceid import OTHER, ROOT, SHEIKHS

SPEAKERS_YAML = Path(__file__).resolve().parent / "speakers.yaml"
USED_LABELS = {"ref", "real", "fake"}


@dataclass
class Clip:
    file: str            # path relative to data/, as in the manifest
    path: Path
    label: str           # ref | real | fake
    speaker: str         # role 1's name (speakerA, tts1, ...)
    sheikh_id: str       # ibn_baz | al_fawzan | al_alsheikh | other
    split: str           # ref | enroll | cal | test
    source: str = ""

    @property
    def is_mufti(self) -> bool:
        return self.sheikh_id in SHEIKHS


def speaker_map(path: str | Path | None = None) -> dict[str, str]:
    return {str(k): str(v) for k, v in (yaml.safe_load(Path(path or SPEAKERS_YAML).read_text(encoding="utf-8")) or {}).items()}


def load_clips(root: str | Path | None = None, mapping: dict[str, str] | None = None) -> tuple[list[Clip], list[str]]:
    """(clips, problems). Problems = unmapped speakers or missing files."""
    root = Path(root or ROOT)
    manifest = root / "data" / "manifest.csv"
    if not manifest.is_file():
        raise FileNotFoundError(f"Role 1's manifest not found: {manifest}")
    mapping = mapping if mapping is not None else speaker_map()
    with open(manifest, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    problems: list[str] = []
    unmapped = Counter()
    pending: dict[tuple[str, str], list[dict]] = defaultdict(list)
    out: list[Clip] = []
    for r in rows:
        label, speaker = (r.get("label") or "").strip(), (r.get("speaker") or "").strip()
        if label not in USED_LABELS:
            continue
        sid = mapping.get(speaker)
        if sid is None:
            unmapped[speaker] += 1
            continue
        if sid == "skip":
            continue
        if sid not in SHEIKHS and sid != OTHER:
            problems.append(f"speakers.yaml: '{speaker}: {sid}' is not a mufti id or 'other'")
            continue
        path = root / "data" / r["file"]
        if not path.is_file():
            problems.append(f"missing file: data/{r['file']}")
            continue
        if label == "ref" and sid in SHEIKHS:
            out.append(Clip(r["file"], path, label, speaker, sid, "ref", r.get("source", "")))
        elif label == "ref":
            problems.append(f"ref clip of a non-mufti voice ignored: data/{r['file']}")
        else:
            pending[(sid, speaker)].append(r)
    for (sid, speaker), group in pending.items():
        order = ("enroll", "cal", "test") if sid in SHEIKHS else ("cal", "test")
        for i, r in enumerate(sorted(group, key=lambda r: r["file"])):
            out.append(Clip(r["file"], root / "data" / r["file"], r["label"], speaker, sid,
                            order[i % len(order)], r.get("source", "")))
    for speaker, n in unmapped.items():
        problems.append(f"speaker '{speaker}' ({n} clips) is not in voiceid/speakers.yaml")
    return out, problems


def summary(clips: list[Clip]) -> list[str]:
    c = Counter((x.sheikh_id, x.speaker, x.split) for x in clips)
    keys = sorted({(s, sp) for s, sp, _ in c})
    lines = [f"{'role-4 id':<12} {'role-1 name':<12} {'ref':>5} {'enroll':>7} {'cal':>5} {'test':>5}"]
    for s, sp in keys:
        lines.append(f"{s:<12} {sp:<12} {c[(s, sp, 'ref')]:>5} {c[(s, sp, 'enroll')]:>7} {c[(s, sp, 'cal')]:>5} "
                     f"{c[(s, sp, 'test')]:>5}")
    return lines


# ------------------------------------------------------------------ embeddings (cached)
CACHE_DIR = ROOT / "cache" / "role4"


def _key(clip: Clip, encoder_name: str, win: float, hop: float, condition: str) -> str:
    st = clip.path.stat()
    raw = f"{clip.file}|{st.st_size}|{int(st.st_mtime)}|{encoder_name}|{win}|{hop}|{condition}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def clip_embeddings(encoder, clip: Clip, win: float, hop: float, condition: str = "clean",
                    use_cache: bool = True) -> np.ndarray:
    """Window embeddings (n, dim) of one clip, the same windows identity_score uses. Cached on disk."""
    from voiceid.audio import degrade, load_audio
    from voiceid.identity import embed_windows

    cache = CACHE_DIR / f"{_key(clip, encoder.name, win, hop, condition)}.npy"
    if use_cache and cache.is_file():
        return np.load(cache)
    audio = load_audio(clip.path)
    if condition != "clean":
        audio = degrade(audio, condition, seed=int(hashlib.md5(clip.file.encode()).hexdigest()[:6], 16))
    _, E = embed_windows(audio, encoder, win, hop)
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        np.save(cache, E)
    return E
