"""Calibration and evaluation on role 1's clips (pure functions; unit-tested with a fake encoder).

Inputs are window embeddings per clip. Voiceprints come from the "ref" clips.
- calibrate (on the "cal" half of the real clips): genuine = a mufti's clip vs
  his voiceprint; impostor = a mufti's clip vs another mufti's voiceprint, and
  "other" voices (team member, generated speech) vs every voiceprint.
- evaluate (on the held-out "test" half): identification, right attribution
  -> match?, wrong attribution -> mismatch?, other voices -> never match?
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from voiceid.encoder import unit_rows
from voiceid.identity import clip_score, decide


@dataclass
class Item:
    """One clip ready for scoring."""
    file: str
    sheikh_id: str   # true id: a mufti id or "other"
    speaker: str     # role 1's name (to tell generated speech apart in reports)
    E: np.ndarray


# ------------------------------------------------------------------ thresholds
@dataclass
class Trials:
    genuine: list[float] = field(default_factory=list)
    impostor_mufti: list[float] = field(default_factory=list)
    impostor_other: list[float] = field(default_factory=list)

    @property
    def impostor(self) -> list[float]:
        return self.impostor_mufti + self.impostor_other


def trials(items: list[Item], voiceprints: dict[str, np.ndarray], pct: float) -> Trials:
    t = Trials()
    for it in items:
        if len(it.E) == 0:
            continue
        for s, vp in voiceprints.items():
            sc = clip_score(unit_rows(it.E), vp, pct)
            if it.sheikh_id == s:
                t.genuine.append(sc)
            elif it.sheikh_id in voiceprints:
                t.impostor_mufti.append(sc)
            else:
                t.impostor_other.append(sc)
    return t


def eer(genuine, impostor) -> tuple[float, float]:
    """Equal error rate and its threshold (higher score = more genuine)."""
    genuine, impostor = np.asarray(genuine, float), np.asarray(impostor, float)
    if genuine.size == 0 or impostor.size == 0:
        return 1.0, 0.0
    best = (np.inf, 1.0, 0.0)
    for th in np.unique(np.concatenate([genuine, impostor])):
        frr, far = float(np.mean(genuine < th)), float(np.mean(impostor >= th))
        if abs(frr - far) < best[0]:
            best = (abs(frr - far), (frr + far) / 2, float(th))
    return best[1], best[2]


def two_thresholds(genuine, impostor, max_false: float = 0.05, min_gap: float = 0.02) -> tuple[float, float]:
    """low: <= max_false of genuine fall below it; high: <= max_false of impostors reach it.
    No overlap -> the empty gap is the gray zone. Never narrower than min_gap."""
    low = float(np.quantile(genuine, max_false))
    high = float(np.quantile(impostor, 1 - max_false))
    if low > high:
        low, high = high, low
    if high - low < min_gap:
        mid = (low + high) / 2
        low, high = mid - min_gap / 2, mid + min_gap / 2
    return low, high


def change_pairs(same_voice: list[np.ndarray], by_voice: dict[str, np.ndarray], max_pairs: int = 3000,
                 seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """(same-voice, different-voice) window similarities for the speaker-change threshold.

    same_voice: per-clip window embeddings of ONE speaker each (consecutive windows compared).
    by_voice: {voice id: all its windows} to draw different-voice pairs from.
    """
    rng = np.random.default_rng(seed)
    same = [float(a @ b) for E in same_voice for a, b in zip(unit_rows(E)[:-1], unit_rows(E)[1:])] \
        if same_voice else []
    keys = sorted(k for k, v in by_voice.items() if len(v))
    pairs = [(a, b) for i, a in enumerate(keys) for b in keys[i + 1:]]
    diff: list[float] = []
    if pairs:
        n = max(1, max_pairs // len(pairs))
        for a, b in pairs:
            A, B = unit_rows(by_voice[a]), unit_rows(by_voice[b])
            diff += np.sum(A[rng.integers(0, len(A), n)] * B[rng.integers(0, len(B), n)], axis=1).tolist()
    if len(same) > max_pairs:
        same = rng.choice(np.array(same), max_pairs, replace=False).tolist()
    return np.array(same, dtype=float), np.array(diff, dtype=float)


# ------------------------------------------------------------------ evaluation
@dataclass
class EvalResult:
    clips: int = 0
    identified: int = 0
    right: Counter = field(default_factory=Counter)      # status when attributed to the true mufti
    wrong: Counter = field(default_factory=Counter)      # status when attributed to another mufti
    other: Counter = field(default_factory=Counter)      # "other" voices vs every mufti
    generated: Counter = field(default_factory=Counter)  # generated speech (tts*) vs every mufti
    confusion: Counter = field(default_factory=Counter)  # (true, closest)
    per_sheikh: dict = field(default_factory=dict)
    genuine_scores: list[float] = field(default_factory=list)

    @staticmethod
    def rate(c: Counter, key: str) -> float:
        n = sum(c.values())
        return c[key] / n if n else float("nan")


def evaluate(items: list[Item], voiceprints: dict[str, np.ndarray], pct: float, low: float, high: float) -> EvalResult:
    r = EvalResult()
    for it in items:
        if len(it.E) == 0:
            continue
        E = unit_rows(it.E)
        scores = {s: clip_score(E, vp, pct) for s, vp in voiceprints.items()}
        if it.sheikh_id in voiceprints:
            closest = max(scores, key=scores.get)
            r.clips += 1
            r.confusion[(it.sheikh_id, closest)] += 1
            ps = r.per_sheikh.setdefault(it.sheikh_id, {"clips": 0, "identified": 0, "match": 0})
            ps["clips"] += 1
            if closest == it.sheikh_id:
                r.identified += 1
                ps["identified"] += 1
            st = decide(scores, it.sheikh_id, low, high)
            r.right[st] += 1
            ps["match"] += st == "match"
            r.genuine_scores.append(scores[it.sheikh_id])
            for s in scores:
                if s != it.sheikh_id:
                    r.wrong[decide(scores, s, low, high)] += 1
        else:
            bucket = r.generated if it.speaker.lower().startswith("tts") else r.other
            for s in scores:
                bucket[decide(scores, s, low, high)] += 1
    return r


def report_lines(cond: str, r: EvalResult) -> list[str]:
    def p(x):
        return "-" if x != x else f"{x:.0%}"

    lines = [f"### {cond}: {r.clips} mufti clips"]
    if r.clips:
        lines.append(f"- Closest voiceprint is the right mufti: {r.identified}/{r.clips} ({r.identified / r.clips:.0%})")
    lines += [
        f"- Attributed to the RIGHT mufti: match {p(r.rate(r.right, 'match'))}, unclear {p(r.rate(r.right, 'unclear'))}, "
        f"mismatch {p(r.rate(r.right, 'mismatch'))}   (want: mostly match, mismatch ~0)",
        f"- Attributed to the WRONG mufti: mismatch {p(r.rate(r.wrong, 'mismatch'))}, unclear {p(r.rate(r.wrong, 'unclear'))}, "
        f"match {p(r.rate(r.wrong, 'match'))}   (want: mostly mismatch, match ~0)",
        f"- Other real voice vs any mufti: match {p(r.rate(r.other, 'match'))} (want ~0), "
        f"unclear {p(r.rate(r.other, 'unclear'))}, mismatch {p(r.rate(r.other, 'mismatch'))}",
        f"- Generated speech (TTS, not a cloned mufti) vs any mufti: match {p(r.rate(r.generated, 'match'))} (want ~0), "
        f"unclear {p(r.rate(r.generated, 'unclear'))}, mismatch {p(r.rate(r.generated, 'mismatch'))}",
    ]
    if r.genuine_scores:
        g = np.array(r.genuine_scores)
        lines.append(f"- Right-mufti clip scores: median {np.median(g):.3f}, lowest 5% below {np.quantile(g, .05):.3f}")
    for s, d in sorted(r.per_sheikh.items()):
        lines.append(f"- {s}: {d['clips']} clips | closest = right {d['identified']}/{d['clips']} | "
                     f"match {d['match']}/{d['clips']}")
    return lines


def confusion_lines(r: EvalResult) -> list[str]:
    names = sorted({t for t, _ in r.confusion} | {c for _, c in r.confusion})
    if len(names) < 2:
        return []
    out = ["| true \\ closest | " + " | ".join(names) + " |", "|---" * (len(names) + 1) + "|"]
    for t in names:
        out.append(f"| {t} | " + " | ".join(str(r.confusion[(t, c)]) for c in names) + " |")
    return out
