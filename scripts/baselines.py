r"""Sada — does the AI add value over a simpler alternative? (judging criteria: AI fit + added value)

  .venv-role4\Scripts\python scripts\baselines.py         -> reports/role5/baselines.md

Same clips, same splits (role 4's test split, never used for tuning), same conditions:
  1. Voice identity: Resemblyzer deep speaker embedding (role 4)  vs  classic MFCC averages (no deep model).
     Metric: the closest mufti is the right one (identification), clean / phone / noisy.
  2. Generated speech: logistic regression on 14 speech features (role 5)  vs  the best SINGLE feature
     with a threshold. Metric: AUC on the test split, and leave-one-generated-voice-out.
Nothing here changes a model or a threshold; it only measures.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

import numpy as np  # noqa: E402

CONDITIONS = ("clean", "phone", "noisy")
REPORT = ROOT / "reports" / "role5" / "baselines.md"
_AUDIO: dict[str, np.ndarray] = {}


def pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def audio_of(path: Path, cond: str) -> np.ndarray:
    from voiceid.audio import degrade, load_audio

    k = str(path)
    if k not in _AUDIO:
        _AUDIO[k] = load_audio(path)
    x = _AUDIO[k]
    seed = int(hashlib.md5(path.name.encode("utf-8")).hexdigest()[:6], 16)
    return x if cond == "clean" else degrade(x, cond, seed=seed)


def auc(p: np.ndarray, y: np.ndarray) -> float:
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return float("nan")
    return float((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean())


# ------------------------------------------------------------------ 1. identity
def mfcc_vector(audio: np.ndarray) -> np.ndarray:
    """Classic baseline: mean and spread of 20 MFCCs over the speech frames."""
    from scipy.fft import dct

    from forensics.features import frame_db, logmel

    M = logmel(audio)
    C = dct(M, type=2, axis=1, norm="ortho")[:, 1:21]
    db = frame_db(audio)[: len(C)]
    sp = db > max(np.percentile(db, 95) - 30.0, -60.0)
    C = C[sp] if sp.sum() >= 20 else C
    return np.concatenate([C.mean(axis=0), C.std(axis=0)])


def identity_section(clips) -> list[str]:
    muf_enroll = [c for c in clips if c.is_mufti and c.split in ("ref", "enroll")]
    muf_test = [c for c in clips if c.is_mufti and c.split == "test"]
    sheikhs = sorted({c.sheikh_id for c in muf_enroll})
    lines = ["## 1. Voice identity: deep speaker embedding vs classic MFCC", "",
             f"Enrollment = ref + enroll clips ({len(muf_enroll)}), as role 4. Test = held-out test split "
             f"({len(muf_test)} mufti clips). Metric: the closest voiceprint is the right mufti.", "",
             "| method | clean | phone | noisy |", "|---|---|---|---|"]
    if not muf_test or len(sheikhs) < 2:
        return lines + ["| (not enough clips) | | | |"]
    # baseline: MFCC centroids (enrollment in clean audio, like role 4's voiceprints)
    E = np.array([mfcc_vector(audio_of(c.path, "clean")) for c in muf_enroll])
    mu, sd = E.mean(axis=0), E.std(axis=0) + 1e-6
    Z = (E - mu) / sd
    cents = {s: Z[[c.sheikh_id == s for c in muf_enroll]].mean(axis=0) for s in sheikhs}
    cents = {s: v / (np.linalg.norm(v) + 1e-9) for s, v in cents.items()}
    row = []
    for cond in CONDITIONS:
        ok = []
        for c in muf_test:
            z = (mfcc_vector(audio_of(c.path, cond)) - mu) / sd
            z = z / (np.linalg.norm(z) + 1e-9)
            ok.append(max(cents, key=lambda s: float(z @ cents[s])) == c.sheikh_id)
        row.append(pct(float(np.mean(ok))))
    lines.append("| classic MFCC averages (no deep model) | " + " | ".join(row) + " |")
    # Sada: Resemblyzer voiceprints of role 4 (same computation as identity_score)
    try:
        from voiceid import thresholds as th
        from voiceid.dataset import clip_embeddings
        from voiceid.encoder import ResemblyzerEncoder
        from voiceid.identity import clip_score
        from voiceid.scoring import load_background, transform
        from voiceid.voiceprints import VOICEPRINT_DIR, load_voiceprints

        t = th.load()["identity"]
        vps = load_voiceprints(VOICEPRINT_DIR)
        bg = load_background(VOICEPRINT_DIR) if t.get("scoring") == "centered" else None
        enc = ResemblyzerEncoder()
        row = []
        for cond in CONDITIONS:
            ok = []
            for c in muf_test:
                Em = transform(clip_embeddings(enc, c, float(t["window_sec"]), float(t["hop_sec"]), cond), bg)
                if not len(Em):
                    ok.append(False)
                    continue
                per = {s: clip_score(Em, v, float(t.get("percentile", 75))) for s, v in vps.items()}
                ok.append(max(per, key=per.get) == c.sheikh_id)
            row.append(pct(float(np.mean(ok))))
        lines.append("| **Sada: Resemblyzer voiceprints (role 4)** | " + " | ".join(row) + " |")
    except Exception as e:  # noqa: BLE001
        lines.append(f"| Sada: Resemblyzer voiceprints (role 4) | not available here ({type(e).__name__}) | | |")
    return lines


# ------------------------------------------------------------------ 2. generated speech
def artifact_section(clips) -> list[str]:
    from forensics.artifact import FEATURE_NAMES, clip_features
    from forensics.lr import LogReg

    use = [c for c in clips if c.label in ("real", "ref", "fake")]
    F = {(c.file, cd): clip_features(audio_of(c.path, cd)) for c in use for cd in CONDITIONS}
    fake = [c for c in use if c.label == "fake"]
    real = [c for c in use if c.label != "fake"]

    def XY(rs, fs, cs=CONDITIONS):
        X = [F[(c.file, cd)] for c in rs for cd in cs] + [F[(c.file, cd)] for c in fs for cd in cs]
        return np.array(X), np.r_[np.zeros(len(rs) * len(cs)), np.ones(len(fs) * len(cs))]

    def best_single(X, y):
        """Best one feature (and its sign) on the TRAINING data only."""
        best = (0.0, 0, 1.0)
        for j in range(X.shape[1]):
            for sign in (1.0, -1.0):
                a = auc(sign * X[:, j], y)
                if a > best[0]:
                    best = (a, j, sign)
        return best[1], best[2]

    lines = ["", "## 2. Generated speech: 14-feature model vs the best single feature", "",
             "The single-feature baseline picks its feature on the training data only, like the model.", "",
             "| test | single best feature | **Sada: logistic regression** |", "|---|---|---|"]
    r_tr = [c for c in real if c.split != "test"]
    r_te = [c for c in real if c.split == "test"]
    f_tr = [c for c in fake if c.split != "test"]
    f_te = [c for c in fake if c.split == "test"]
    if not (r_tr and r_te and f_tr and f_te):
        return lines + ["| (not enough clips) | | |"]
    Xtr, ytr = XY(r_tr, f_tr)
    m = LogReg(l2=3.0).fit(Xtr, ytr, FEATURE_NAMES)
    j, sg = best_single(Xtr, ytr)
    for cd in CONDITIONS:
        Xte, yte = XY(r_te, f_te, (cd,))
        lines.append(f"| test split, {cd} | {auc(sg * Xte[:, j], yte):.2f} ({FEATURE_NAMES[j]}) | "
                     f"**{auc(m.proba(Xte), yte):.2f}** |")
    for v in sorted({c.speaker for c in fake}):
        Xtr, ytr = XY(r_tr, [c for c in fake if c.speaker != v])
        m = LogReg(l2=3.0).fit(Xtr, ytr, FEATURE_NAMES)
        j, sg = best_single(Xtr, ytr)
        Xte, yte = XY(r_te, [c for c in fake if c.speaker == v])
        p = m.proba(Xte)
        lines.append(f"| voice never seen: {v} (AUC; flagged at p>=0.5) | {auc(sg * Xte[:, j], yte):.2f} "
                     f"({FEATURE_NAMES[j]}) | **{auc(p, yte):.2f}**; {pct(float((p[yte == 1] >= 0.5).mean()))} flagged |")
    return lines


def main() -> int:
    from voiceid.dataset import load_clips

    clips, _ = load_clips()
    lines = [f"# Sada — AI vs simpler alternatives ({dt.datetime.now():%Y-%m-%d %H:%M})", "",
             "Why each AI part is used, measured on the same held-out clips as the other reports.", ""]
    lines += identity_section(clips)
    lines += artifact_section(clips)
    lines += ["", "## 3. Finding the original: why NOT a learned model",
              "Locating a clip inside a lecture is an exact-match problem, so Sada uses signal processing",
              "(band-limited spectral fingerprints), not AI: results are explainable down to the second and",
              "need no training data. See compare.md (found 100% in the library, 0% false finds).", "",
              "## Limits",
              "- Small data: few recordings per mufti, 3 generic TTS voices. A higher number here is evidence of",
              "  added value on THIS data, not a general accuracy claim."]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nreport: {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
