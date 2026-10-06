"""How window embeddings are compared.

scoring:
  raw       cosine of Resemblyzer embeddings as they are.
  centered  subtract a background mean (the "average voice" of all enrolment
            audio) before the cosine. Resemblyzer embeddings are all positive,
            so raw cosines of different speakers are already high (~0.5);
            centering removes that shared part and widens the gap.
enroll:
  ref       voiceprints from role 1's data/ref clips only.
  ref+real  also from one third of data/real (the "enroll" split), so a
            voiceprint covers more than one recording/session.
  ref+real+phone  the same, plus phone-quality copies of that audio, so clips
            re-recorded or shared over phones/WhatsApp still fit the voiceprint.
Each source (ref, enroll, and their phone copies) gets its own centroid; the
voiceprint is their average, so no source dominates.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from voiceid.encoder import l2norm, unit_rows

BACKGROUND_FILE = "_background.npy"
SCORINGS = ("raw", "centered")
ENROLLS = ("ref", "ref+real", "ref+real+phone")


@dataclass(frozen=True)
class Method:
    scoring: str = "centered"
    enroll: str = "ref+real"

    @property
    def name(self) -> str:
        return f"{self.scoring} / enroll {self.enroll}"

    @staticmethod
    def from_thresholds(th: dict) -> "Method":
        t = th.get("identity", {})
        return Method(t.get("scoring", "raw"), t.get("enroll", "ref"))


ALL_METHODS = [Method(s, e) for e in ENROLLS for s in SCORINGS]


def transform(E: np.ndarray, background: np.ndarray | None) -> np.ndarray:
    """Unit-length rows, centered on the background mean when one is given."""
    E = unit_rows(np.asarray(E, dtype=np.float32))
    if background is None or len(E) == 0:
        return E
    return unit_rows(E - background[None, :])


def background_mean(embeddings: list[np.ndarray], speakers: list[str] | None = None) -> np.ndarray:
    """Mean embedding; with `speakers` (one name per array) every speaker weighs the same,
    so a mufti with many clips does not become "the average voice"."""
    pairs = [(unit_rows(E), (speakers[i] if speakers else "")) for i, E in enumerate(embeddings) if len(E)]
    if not pairs:
        raise ValueError("no embeddings for the background mean")
    by: dict[str, list[np.ndarray]] = {}
    for E, s in pairs:
        by.setdefault(s, []).append(E)
    means = [np.concatenate(v).mean(axis=0) for v in by.values()]
    return np.mean(np.stack(means), axis=0).astype(np.float32)


def save_background(directory: str | Path, mu: np.ndarray | None) -> None:
    path = Path(directory) / BACKGROUND_FILE
    if mu is None:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, mu.astype(np.float32))


def load_background(directory: str | Path) -> np.ndarray | None:
    path = Path(directory) / BACKGROUND_FILE
    return np.load(path).astype(np.float32) if path.is_file() else None


__all__ = ["Method", "ALL_METHODS", "transform", "background_mean", "save_background", "load_background", "l2norm"]
