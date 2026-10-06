"""identity_score: is the voice in a clip the voice of the mufti it is attributed to?

1. Slide 3 s windows (hop 1.5 s) over the clip; skip quiet windows.
2. Embed each window (Resemblyzer); cosine with the mufti's voiceprint.
3. Clip score = 75th percentile of window scores (a questioner in part of the
   clip does not drag it down).
4. Two thresholds -> match / unclear / mismatch.
5. Speaker changes = consecutive windows that do not sound alike (role 5 uses
   them so a questioner -> sheikh hand-over is not reported as a cut).

A voice match never proves authenticity: voice cloning is designed to match
voiceprints. The final verdict also needs the synthetic-speech check (role 5).

The result has the same fields as IdentityResult in the main Sada app.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from voiceid import SHEIKHS, SR
from voiceid.audio import iter_windows, rms_db
from voiceid.thresholds import classify

UNKNOWN = "unknown"


@dataclass
class WindowScore:
    start: float
    end: float
    score: float


@dataclass
class IdentityResult:
    sheikh_id: str
    status: str                     # match | unclear | mismatch | unavailable
    target_id: str | None = None    # voiceprint actually compared with
    best_match: str | None = None   # closest voiceprint overall
    score: float | None = None
    windows: list[WindowScore] = field(default_factory=list)
    speaker_changes: list[float] = field(default_factory=list)
    per_sheikh: dict[str, float] = field(default_factory=dict)
    note: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def embed_windows(audio: np.ndarray, encoder, win: float = 3.0, hop: float = 1.5) -> tuple[list, np.ndarray]:
    """([(start_s, end_s)], embeddings (n, dim)) of the speech windows of a clip."""
    floor = rms_db(audio) - 20.0
    spans, embs = [], []
    for a, b in iter_windows(audio.size, win, hop):
        piece = audio[a:b]
        if piece.size < SR or rms_db(piece) < floor:
            continue
        e = encoder.embed(piece)
        if e is None:
            continue
        spans.append((a / SR, b / SR))
        embs.append(np.asarray(e, dtype=np.float32))
    return spans, (np.stack(embs) if embs else np.zeros((0, 256), dtype=np.float32))


def clip_score(E: np.ndarray, voiceprint: np.ndarray, pct: float = 75) -> float:
    return float(np.percentile(E @ voiceprint, pct))


MISATTRIBUTION_MARGIN = 0.05  # another mufti must beat the attributed one by this much to call "mismatch"


def decide(per_sheikh: dict[str, float], target: str, low: float, high: float,
           margin: float = MISATTRIBUTION_MARGIN) -> str:
    """match / unclear / mismatch for the clip attributed to `target`.

    Two thresholds on the target's score, plus identification among the muftis:
    - never "match" if another mufti's voiceprint fits the clip better;
    - "mismatch" if another mufti fits clearly better (by `margin`) and passes `high`
      (the voice is most likely that other mufti's: a misattributed clip).
    """
    score = per_sheikh[target]
    status = classify(score, low, high)
    best = max(per_sheikh, key=per_sheikh.get)
    if best != target:
        if status == "match":
            status = "unclear"
        if per_sheikh[best] >= high and per_sheikh[best] - score >= margin:
            status = "mismatch"
    return status


def score_embeddings(spans: list, E: np.ndarray, sheikh_id: str, voiceprints: dict[str, np.ndarray],
                     thresholds: dict) -> IdentityResult:
    t = thresholds["identity"]
    if len(E) == 0:
        return IdentityResult(sheikh_id, "unclear", note="not enough speech")
    low, high, pct = float(t["low"]), float(t["high"]), float(t.get("percentile", 75))
    per = {s: clip_score(E, vp, pct) for s, vp in voiceprints.items()}
    best = max(per, key=per.get)
    target = sheikh_id if sheikh_id in voiceprints else best
    sims = E @ voiceprints[target]
    score = float(np.percentile(sims, pct))
    status = decide(per, target, low, high)
    note = None
    if status != "match" and best != target and target == sheikh_id:
        note = f"the voice is closer to another mufti's voiceprint ({best})"
    if sheikh_id not in voiceprints:
        note = "no attributed mufti given: compared with the closest voiceprint"
        if status == "mismatch":
            status, note = "unclear", "the voice matches none of the muftis in the library"
    change_sim = float(t.get("change_similarity", 0.6))
    changes = [round((spans[i - 1][1] + spans[i][0]) / 2, 2)
               for i in range(1, len(E)) if float(E[i - 1] @ E[i]) < change_sim]
    return IdentityResult(
        sheikh_id=sheikh_id, status=status, target_id=target, best_match=best, score=round(score, 4),
        windows=[WindowScore(round(a, 2), round(b, 2), round(float(s), 4)) for (a, b), s in zip(spans, sims)],
        speaker_changes=changes, per_sheikh={k: round(v, 4) for k, v in per.items()}, note=note,
    )


def identity_score(audio: np.ndarray, sheikh_id: str, encoder, voiceprints: dict[str, np.ndarray],
                   thresholds: dict, background: np.ndarray | None = None) -> IdentityResult:
    """Contract function (same name and fields as in the main Sada app).

    background: the mean vector saved next to the voiceprints when scoring = centered
    (data/voiceprints/_background.npy); None for raw scoring.
    """
    from voiceid.scoring import transform

    if encoder is None or not voiceprints:
        return IdentityResult(sheikh_id, "unavailable", note="encoder or voiceprints missing")
    t = thresholds["identity"]
    spans, E = embed_windows(audio, encoder, float(t["window_sec"]), float(t["hop_sec"]))
    return score_embeddings(spans, transform(E, background), sheikh_id, voiceprints, thresholds)


def check_file(path: str, sheikh_id: str = UNKNOWN) -> IdentityResult:
    """One call for other roles (e.g. the API): load the clip, the encoder, the voiceprints and the thresholds."""
    from voiceid import thresholds as th
    from voiceid.audio import load_audio
    from voiceid.encoder import ResemblyzerEncoder
    from voiceid.scoring import load_background
    from voiceid.voiceprints import VOICEPRINT_DIR, load_voiceprints

    global _ENCODER
    if _ENCODER is None:
        _ENCODER = ResemblyzerEncoder()
    thresholds = th.load()
    background = load_background(VOICEPRINT_DIR) if thresholds["identity"].get("scoring") == "centered" else None
    return identity_score(load_audio(path), sheikh_id if sheikh_id in SHEIKHS else UNKNOWN, _ENCODER,
                          load_voiceprints(VOICEPRINT_DIR), thresholds, background)


_ENCODER = None
