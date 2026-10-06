"""detect_splice_points: blind search for joins inside a clip (no original needed).

Used when the original is NOT in the library (compare.py finds joins far more reliably
when it is). How it works:
1. Candidate points = the strongest "clicks" (a jump in the waveform's second difference far
   above the local signal, which a hard cut leaves) and the strongest spectral changes
   (average spectrum of the 0.3 s before vs after).
2. Each candidate gets a few numbers; a small logistic regression trained on role 1's spliced
   clips (true join times in data/manipulation_log.csv) gives a probability.
3. Candidates near a speaker change found by role 4 are dropped (a questioner handing over to
   the sheikh is a natural change, not a cut).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from forensics.features import FPS, HOP, frame_db, logmel

CONTEXT = 30          # frames (0.3 s) each side for spectral change
MIN_GAP = 40          # frames between candidates
EDGE = 0.4            # s ignored at the start / end
TOP_K = 8
SPEAKER_CHANGE_MARGIN = 0.75
TOLERANCE = 0.25      # s: a found point this close to the true join counts as correct
FEATURE_NAMES = ["click_z", "click_log", "click_rank", "novelty_z", "novelty", "level_jump_db",
                 "level_db", "flux_z", "click_novelty"]


@dataclass
class SplicePoint:
    time: float
    probability: float
    kind: str = "join"

    def to_dict(self) -> dict:
        return asdict(self)


def _rz(v: np.ndarray) -> np.ndarray:
    m = np.median(v)
    return (v - m) / (np.median(np.abs(v - m)) * 1.4826 + 1e-9)


def curves(audio: np.ndarray) -> dict[str, np.ndarray]:
    x = np.asarray(audio, dtype=np.float32)
    M = logmel(x)
    T = len(M)
    M = (M - M.mean(axis=0)) / (M.std(axis=0) + 1e-6)
    cs = np.vstack([np.zeros((1, M.shape[1])), np.cumsum(M, axis=0)])
    nov = np.zeros(T, np.float32)
    if T > 2 * CONTEXT:
        t = np.arange(CONTEXT, T - CONTEXT)
        left = (cs[t] - cs[t - CONTEXT]) / CONTEXT
        right = (cs[t + CONTEXT] - cs[t]) / CONTEXT
        nov[CONTEXT:T - CONTEXT] = np.linalg.norm(left - right, axis=1) / np.sqrt(M.shape[1])
    flux = np.r_[0, np.linalg.norm(np.diff(M, axis=0), axis=1) / np.sqrt(M.shape[1])].astype(np.float32)
    # click: |second difference| peak vs the local RMS of the second difference (per 10 ms frame)
    d2 = np.abs(np.diff(x, 2, prepend=x[:2]))
    n = T * HOP
    d2 = np.pad(d2, (0, max(0, n - d2.size)))[:n].reshape(T, HOP)
    loc = np.convolve(np.sqrt((d2.astype(np.float64) ** 2).mean(axis=1)) + 1e-7, np.ones(5) / 5, "same")
    click = np.log(d2.max(axis=1) / loc + 1e-6).astype(np.float32)
    db = frame_db(x)[:T]
    lv = np.convolve(db, np.ones(CONTEXT) / CONTEXT, mode="same")
    return {"novelty": nov, "flux": flux, "click": click, "db": db, "level": lv}


def candidates(audio: np.ndarray) -> tuple[list[int], np.ndarray]:
    c = curves(audio)
    T = len(c["click"])
    lo, hi = int(EDGE * FPS), T - int(EDGE * FPS)
    if hi - lo < 5:
        return [], np.zeros((0, len(FEATURE_NAMES)))
    cz, nz, fz = _rz(c["click"][lo:hi]), _rz(c["novelty"][lo:hi]), _rz(c["flux"][lo:hi])
    score = np.maximum(cz, 0) + 0.7 * np.maximum(nz, 0)
    chosen: list[int] = []
    for t in np.argsort(-score):
        if all(abs(t - u) >= MIN_GAP for u in chosen):
            chosen.append(int(t))
        if len(chosen) >= TOP_K:
            break
    order = np.argsort(-cz)
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    feats = []
    for t in chosen:
        a, b = max(0, t - 3), min(len(cz), t + 4)
        g = t + lo
        jump = abs(float(c["level"][max(0, g - CONTEXT // 2)] - c["level"][min(T - 1, g + CONTEXT // 2)]))
        k = int(a + np.argmax(cz[a:b]))
        feats.append([float(cz[k]), float(c["click"][lo + k]), float(np.log1p(rank[k])),
                      float(nz[a:b].max()), float(c["novelty"][g]), jump,
                      float(c["db"][g] - np.percentile(c["db"], 95)), float(fz[a:b].max()),
                      float(max(cz[k], 0) * max(nz[a:b].max(), 0))])
    return [t + lo for t in chosen], np.array(feats, dtype=np.float64).reshape(-1, len(FEATURE_NAMES))


def detect_splice_points(audio: np.ndarray, model=None, threshold: float = 0.5,
                         speaker_changes: list[float] | None = None) -> list[SplicePoint]:
    """Contract function. `model` = forensics.lr.LogReg from forensics/models/splice.json."""
    if model is None:
        return []
    idx, X = candidates(audio)
    if not idx:
        return []
    out = []
    for t, p in zip(idx, model.proba(X)):
        sec = t / FPS
        if speaker_changes and any(abs(sec - s) <= SPEAKER_CHANGE_MARGIN for s in speaker_changes):
            continue
        if p >= threshold:
            out.append(SplicePoint(round(sec, 2), round(float(p), 3)))
    return sorted(out, key=lambda s: s.time)


def label_candidates(idx: list[int], true_times: list[float], tol: float = TOLERANCE) -> np.ndarray:
    return np.array([1.0 if any(abs(t / FPS - s) <= tol for s in true_times) else 0.0 for t in idx])
