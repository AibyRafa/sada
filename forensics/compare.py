"""compare_with_original: find a shared clip inside the original recordings and say what changed.

1. The clip is cut into 1 s windows (every 0.25 s). Each window is searched in every original
   (fingerprints, forensics/fingerprint.py) and the best positions are kept.
2. Windows that agree on the same original AND the same offset (original time - clip time)
   form one "piece". A clip copied straight from a lecture is one piece. A clip with a hidden
   cut is two pieces of the same original with a jump in offset; a clip joined from two
   recordings is two pieces of different originals.
3. A frame-by-frame pass (Viterbi) finds where exactly one piece ends and the next begins.
4. Result: where the clip sits in the original, how much of the original is missing before and
   after it, whether the speaker was still talking when the clip was cut, and every internal edit.

"Not found" only means the original is not in our library. It never means the clip is fake.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from forensics.fingerprint import FP_FPS, fingerprint
from forensics.library import Library

WIN_SEC = 1.0
HOP_SEC = 0.25
MAX_WINDOWS = 240        # clips longer than 1 minute: spread the windows wider so the search stays fast
OFFSET_TOL = 0.06        # s: windows of the same piece agree on the offset within this
SMOOTH_SEC = 0.3
SWITCH_PENALTY = 2.0     # Viterbi cost of changing piece (in similarity x frames)
NONE_LEVEL = 0.3         # per-frame similarity below which a frame is "not from any original"
MIN_PIECE_SEC = 0.3
PIECE_MIN_SIM = 0.6      # a piece whose frames resemble the original less than this is not a match
EDIT_MIN_JUMP = 0.3      # s: smaller offset changes are the same piece
MIN_COVERAGE = 0.25     # less of the clip's speech than this found = chance resemblance -> not found
MISSING_TOL = 1.0        # s of original before/after the clip that still counts as "complete"
DEFAULTS = {"match": 0.55, "strong": 0.7}   # replaced by forensics/settings.yaml after calibration


@dataclass
class Piece:
    clip_start: float
    clip_end: float
    source: str
    sheikh_id: str
    orig_start: float
    orig_end: float
    similarity: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Edit:
    time: float          # seconds in the clip
    kind: str            # cut | joined | reordered | unmatched
    detail: str
    removed_sec: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CompareResult:
    status: str                      # complete | excerpt | edited | not_found | no_library | no_speech
    source: str | None = None        # main original (id)
    sheikh_id: str | None = None     # mufti of that original (from its file name), if known
    pieces: list[Piece] = field(default_factory=list)
    edits: list[Edit] = field(default_factory=list)
    coverage: float = 0.0            # share of the clip's speech found in originals
    original_duration: float | None = None
    missing_before: float | None = None   # seconds of the original before the clip
    missing_after: float | None = None    # seconds of the original after the clip
    cut_mid_speech_start: bool | None = None
    cut_mid_speech_end: bool | None = None
    best_score: float = 0.0
    note: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def speech_mask(db: np.ndarray) -> np.ndarray:
    if db.size == 0:
        return np.zeros(0, bool)
    top = float(np.percentile(db, 95))
    floor = float(np.percentile(db, 5))          # background / noise level
    thr = max(top - 35.0, -65.0, min(floor + 5.0, top - 10.0))
    return db > thr


def _windows(Q: np.ndarray, sp: np.ndarray) -> tuple[list[int], np.ndarray, int]:
    T = len(Q)
    W = min(int(WIN_SEC * FP_FPS), T)
    hop = max(1, int(HOP_SEC * FP_FPS), (T - W) // MAX_WINDOWS)   # same 0.25 s hop for clips up to 1 minute
    starts = list(range(0, max(1, T - W + 1), hop))
    if T - W > 0 and starts[-1] != T - W:
        starts.append(T - W)
    keep = [s for s in starts if sp[s:s + W].mean() >= 0.5]
    if not keep:
        return [], np.zeros((0, W, Q.shape[1]), np.float32), W
    return keep, np.stack([Q[s:s + W] for s in keep]), W


def _cluster(starts, matches, thr):
    """[(orig index, offset d (s), {window: score})] sorted by support."""
    cl: list[dict] = []
    flat = []
    for wi, (s, ms) in enumerate(zip(starts, matches)):
        for oi, t, sc in ms:
            if sc >= thr:
                flat.append((sc, wi, oi, t - s / FP_FPS))
    for sc, wi, oi, d in sorted(flat, reverse=True):
        for c in cl:
            if c["oi"] == oi and abs(c["d"] - d) <= OFFSET_TOL:
                if wi not in c["w"]:
                    c["w"][wi] = sc
                break
        else:
            cl.append({"oi": oi, "d": d, "w": {wi: sc}})
    for c in cl:
        c["support"] = sum(c["w"].values())
    return sorted(cl, key=lambda c: -c["support"])


def _frame_sim(Q: np.ndarray, F: np.ndarray, shift: int) -> np.ndarray:
    T = len(Q)
    out = np.zeros(T, np.float32)
    a, b = max(0, -shift), min(T, len(F) - shift)
    if b <= a:
        return out
    q, o = Q[a:b], F[a + shift:b + shift]
    q = q - q.mean(axis=1, keepdims=True)
    o = o - o.mean(axis=1, keepdims=True)
    out[a:b] = (q * o).sum(axis=1) / (np.linalg.norm(q, axis=1) * np.linalg.norm(o, axis=1) + 1e-6)
    k = max(1, int(SMOOTH_SEC * FP_FPS))
    return np.convolve(out, np.ones(k) / k, mode="same").astype(np.float32)


def _viterbi(E: np.ndarray, penalty: float) -> np.ndarray:
    """E: (K, T) per-frame gains. Path maximizing total gain minus penalty per switch."""
    K, T = E.shape
    score = E[:, 0].copy()
    back = np.zeros((K, T), np.int32)
    for t in range(1, T):
        best = int(np.argmax(score))
        stay = score
        jump = score[best] - penalty
        choose_jump = jump > stay
        back[:, t] = np.where(choose_jump, best, np.arange(K))
        score = np.where(choose_jump, jump, stay) + E[:, t]
    path = np.zeros(T, np.int32)
    path[-1] = int(np.argmax(score))
    for t in range(T - 1, 0, -1):
        path[t - 1] = back[path[t], t]
    return path


def _speech_near(lib: Library, oi: int, t0: float, t1: float) -> bool | None:
    db = lib.dbs[oi]
    a, b = int(max(0.0, t0) * FP_FPS), int(max(0.0, t1) * FP_FPS)
    if b <= a or a >= len(db):
        return None
    sp = speech_mask(db)
    return bool(sp[a:min(b, len(db))].mean() >= 0.5)


def compare_with_original(audio: np.ndarray, library: Library | None, settings: dict | None = None) -> CompareResult:
    """Contract function. `library` = forensics.library.Library.build() (cached fingerprints of the originals)."""
    if library is None or len(library) == 0:
        return CompareResult("no_library", note="no original recordings in raw/ or data/originals/")
    s = {**DEFAULTS, **(settings or {})}
    Q, db = fingerprint(audio)
    sp = speech_mask(db)
    starts, X, W = _windows(Q, sp)
    if not starts:
        return CompareResult("no_speech", note="no speech found in the clip")
    matches = library.search(X)
    best_score = max((m[0][2] for m in matches if m), default=0.0)
    clusters = _cluster(starts, matches, s["match"])
    chosen = []
    covered: set[int] = set()
    for c in clusters:
        new = [w for w in c["w"] if w not in covered]
        if not new:
            continue
        if len(c["w"]) >= 2 or max(c["w"].values()) >= s["strong"]:
            chosen.append(c)
            covered.update(c["w"])
        if len(chosen) >= 6:
            break
    if not chosen:
        return CompareResult("not_found", best_score=round(best_score, 3),
                             note="original not in the library (this alone does not mean the clip is fake)")

    T = len(Q)
    sims = np.stack([_frame_sim(Q, library.feats[c["oi"]], int(round(c["d"] * FP_FPS))) for c in chosen])
    E = np.vstack([sims - NONE_LEVEL, np.zeros((1, T), np.float32)])
    E[:, ~sp] = 0.0                    # silence carries no evidence: keep the neighbours' choice
    E[-1, ~sp] = 0.0
    path = _viterbi(E, SWITCH_PENALTY)
    none = len(chosen)

    # runs -> pieces (drop runs that are too short, they join the neighbour)
    runs = []
    t = 0
    while t < T:
        u = t
        while u < T and path[u] == path[t]:
            u += 1
        runs.append([int(path[t]), t, u])
        t = u
    min_len = int(MIN_PIECE_SEC * FP_FPS)
    changed = True
    while changed and len(runs) > 1:
        changed = False
        for i, (k, a, b) in enumerate(runs):
            if b - a < min_len and sp[a:b].any():
                j = i - 1 if i > 0 else i + 1
                runs[j][1], runs[j][2] = min(runs[j][1], a), max(runs[j][2], b)
                runs.pop(i)
                changed = True
                break
        merged = [runs[0]]
        for r in runs[1:]:
            if r[0] == merged[-1][0]:
                merged[-1][2] = r[2]
            else:
                merged.append(r)
        runs = merged

    pieces: list[Piece] = []
    unmatched: list[tuple[float, float]] = []
    for r in runs:                       # weak pieces = chance resemblance, not the original
        k, a, b = r
        if k != none:
            m = sp[a:b] if sp[a:b].any() else np.ones(b - a, bool)
            if float(sims[k, a:b][m].mean()) < PIECE_MIN_SIM:
                r[0] = none
    for k, a, b in runs:
        if k == none:
            if sp[a:b].sum() >= 0.5 * FP_FPS:
                unmatched.append((a / FP_FPS, b / FP_FPS))
            continue
        c = chosen[k]
        o = library.originals[c["oi"]]
        sim = float(sims[k, a:b][sp[a:b]].mean()) if sp[a:b].any() else float(sims[k, a:b].mean())
        pieces.append(Piece(round(a / FP_FPS, 2), round(b / FP_FPS, 2), o.id, o.sheikh_id,
                            round(a / FP_FPS + c["d"], 2), round(b / FP_FPS + c["d"], 2), round(sim, 3)))

    matched_sp = sum(int(sp[int(p.clip_start * FP_FPS):int(p.clip_end * FP_FPS)].sum()) for p in pieces)
    if not pieces or matched_sp < MIN_COVERAGE * max(1, int(sp.sum())):
        return CompareResult("not_found", best_score=round(best_score, 3),
                             note="original not in the library (this alone does not mean the clip is fake)")

    # edits between consecutive pieces
    edits: list[Edit] = []
    for p, q in zip(pieces, pieces[1:]):
        jump = (q.orig_start - q.clip_start) - (p.orig_start - p.clip_start)
        if p.source != q.source:
            edits.append(Edit(q.clip_start, "joined", f"{p.source} -> {q.source}"))
        elif jump > EDIT_MIN_JUMP:
            edits.append(Edit(q.clip_start, "cut", f"{jump:.1f} s of the original removed here "
                                                   f"({p.orig_end:.1f}s -> {q.orig_start:.1f}s)", round(jump, 2)))
        elif jump < -EDIT_MIN_JUMP:
            edits.append(Edit(q.clip_start, "reordered", f"jumps back {-jump:.1f} s in the original"))
    for a, b in unmatched:
        edits.append(Edit(round(a, 2), "unmatched", f"{b - a:.1f} s of speech not found in the original"))
    edits.sort(key=lambda e: e.time)

    # main source and context
    dur_by_src: dict[str, float] = {}
    for p in pieces:
        dur_by_src[p.source] = dur_by_src.get(p.source, 0.0) + p.clip_end - p.clip_start
    main = max(dur_by_src, key=dur_by_src.get)
    oi = next(i for i, o in enumerate(library.originals) if o.id == main)
    mp = [p for p in pieces if p.source == main]
    first, last = mp[0], mp[-1]
    odur = library.originals[oi].duration
    before = max(0.0, first.orig_start)
    after = max(0.0, odur - last.orig_end)
    cont_before = _speech_near(library, oi, first.orig_start - 0.4, first.orig_start) if before > 0.2 else False
    cont_after = _speech_near(library, oi, last.orig_end, last.orig_end + 0.4) if after > 0.2 else False

    matched = np.zeros(T, bool)
    for p in pieces:
        matched[int(p.clip_start * FP_FPS):int(p.clip_end * FP_FPS)] = True
    coverage = float(matched[sp].mean()) if sp.any() else 0.0

    if edits:
        status = "edited"
    elif before > MISSING_TOL or after > MISSING_TOL:
        status = "excerpt"
    else:
        status = "complete"
    return CompareResult(status, main, library.originals[oi].sheikh_id, pieces, edits, round(coverage, 3),
                         round(odur, 2), round(before, 2), round(after, 2), cont_before, cont_after,
                         round(best_score, 3))
