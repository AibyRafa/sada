"""Voiceprints: one robust centroid of 3 s window embeddings per mufti.

Lectures and fatwa programmes contain other voices (a student reading the text,
a presenter, a caller). The centroid is recomputed from the windows closest to
it, so the mufti's dominant voice wins and the others are dropped. The report
per recording shows how much of it matched; a FLAG means it is mostly another
voice or was given the wrong sheikh_id.

Files: data/voiceprints/<sheikh_id>.npy (same format as the main Sada app) + .json report.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from voiceid import ROOT
from voiceid.encoder import l2norm, unit_rows

VOICEPRINT_DIR = ROOT / "data" / "voiceprints"

LOW_MAIN_VOICE = 0.3  # recordings with less than this share of windows in the main voice are flagged


def robust_centroid(E: np.ndarray, keep: float = 0.7, iters: int = 10) -> tuple[np.ndarray, np.ndarray]:
    """(centroid, kept_mask) of the dominant voice in E (n, dim)."""
    if E.ndim != 2 or len(E) == 0:
        raise ValueError("no embeddings")
    E = unit_rows(E)
    mask = np.ones(len(E), dtype=bool)
    c = l2norm(E.mean(axis=0))
    if len(E) < 4:
        return c, mask
    for _ in range(iters):
        sims = E @ c
        new_mask = sims >= np.quantile(sims, 1.0 - keep)
        c = l2norm(E[new_mask].mean(axis=0))
        if np.array_equal(new_mask, mask):
            break
        mask = new_mask
    return c, mask


@dataclass
class RecordingReport:
    recording_id: str
    windows: int
    main_voice: float       # share of its windows used for the voiceprint
    mean_similarity: float  # mean cosine of all its windows to the voiceprint
    flag: str = ""


def build_voiceprint(per_recording: dict[str, np.ndarray], keep: float = 0.7,
                     groups: dict[str, str] | None = None) -> tuple[np.ndarray, list[RecordingReport]]:
    """Robust voiceprint from {recording/clip id: window embeddings} + a report per recording.

    groups ({id: group name}, optional): recordings from different sources/sessions
    (e.g. role 1's ref clips vs real clips, clean vs phone copies). Each group gets
    its own robust centroid and the voiceprint is their average, so a small session
    is not swallowed by a big one.

    FLAG = far from the voiceprint on both counts: few windows in the main voice AND
    an outlier mean similarity. Another speaker, a wrong label, or a very different
    recording session.
    """
    items = [(rid, unit_rows(E)) for rid, E in per_recording.items() if len(E)]
    if not items:
        raise ValueError("no recordings with speech")
    groups = groups or {}
    by_group: dict[str, list[np.ndarray]] = {}
    for rid, E in items:
        by_group.setdefault(groups.get(rid, ""), []).append(E)
    cents = [robust_centroid(np.concatenate(Es), keep=keep)[0] for Es in by_group.values()]
    centroid = l2norm(np.mean(np.stack(cents), axis=0))
    reports = []
    for rid, E in items:
        sims = E @ centroid
        main = sims >= np.quantile(np.concatenate([e @ centroid for _, e in items]), 1.0 - keep)
        reports.append(RecordingReport(rid, len(E), round(float(main.mean()), 3), round(float(sims.mean()), 4)))
    sims = np.array([r.mean_similarity for r in reports])
    med = float(np.median(sims))
    mad = float(np.median(np.abs(sims - med))) * 1.4826
    cut = med - max(3 * mad, 0.05)
    for r in reports:
        if r.main_voice < LOW_MAIN_VOICE and r.mean_similarity < cut:
            r.flag = "far from this voiceprint: another speaker, a wrong label, or a very different recording? listen to it"
    return centroid, reports


def save_voiceprint(directory: str | Path, sheikh_id: str, centroid: np.ndarray, meta: dict) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{sheikh_id}.npy"
    np.save(path, l2norm(centroid.astype(np.float32)))
    (directory / f"{sheikh_id}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_voiceprints(directory: str | Path) -> dict[str, np.ndarray]:
    directory = Path(directory)
    if not directory.exists():
        return {}
    return {f.stem: l2norm(np.load(f).astype(np.float32)) for f in sorted(directory.glob("*.npy"))
            if not f.stem.startswith("_")}


def report_rows(reports: list[RecordingReport]) -> list[dict]:
    return [asdict(r) for r in reports]
