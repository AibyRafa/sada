r"""Sada — Role 5 (forgery and manipulation), built on role 1's data and role 4. Run from the project folder:

  .venv-role4\Scripts\python scripts\forensics.py library        originals found in raw/ and data/originals/
  .venv-role4\Scripts\python scripts\forensics.py calibrate      thresholds of the original search (cal split)
  .venv-role4\Scripts\python scripts\forensics.py evaluate       original search on held-out clips, joins, cuts, crops
  .venv-role4\Scripts\python scripts\forensics.py artifact       train + test the generated-speech score
  .venv-role4\Scripts\python scripts\forensics.py splice         train + test the blind join detector
  .venv-role4\Scripts\python scripts\forensics.py check FILE --sheikh ibn_baz    one clip, all 4 questions
  .venv-role4\Scripts\python scripts\forensics.py all            library, calibrate, evaluate, artifact, splice

Reports: reports/role5/. Settings: forensics/settings.yaml. Models: forensics/models/. Cache: cache/role5/.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

import numpy as np  # noqa: E402

REPORTS = ROOT / "reports" / "role5"
CACHE = ROOT / "cache" / "role5"
CONDITIONS = ("clean", "phone", "noisy")
TOL = 0.25   # seconds


# ================================================================== helpers
def stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def write_report(name: str, lines: list[str]) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    p = REPORTS / name
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  report: {p.relative_to(ROOT)}")
    return p


def pct(x) -> str:
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{100 * x:.0f}%"


def rate(flags) -> float | None:
    flags = list(flags)
    return float(np.mean(flags)) if flags else None


def seed_of(name: str) -> int:
    return int(hashlib.md5(name.encode("utf-8")).hexdigest()[:6], 16)


_AUDIO: dict[str, np.ndarray] = {}


def audio_of(path: Path, condition: str = "clean") -> np.ndarray:
    from voiceid.audio import degrade, load_audio

    key = str(path)
    if key not in _AUDIO:
        _AUDIO[key] = load_audio(path)
    x = _AUDIO[key]
    return x if condition == "clean" else degrade(x, condition, seed=seed_of(path.name))


def clips():
    from voiceid.dataset import load_clips

    cl, problems = load_clips()
    return cl, problems


def manip_log() -> list[dict]:
    p = ROOT / "data" / "manipulation_log.csv"
    if not p.is_file():
        return []
    with open(p, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if (ROOT / "data" / r["file"]).is_file()]


def library(log=print):
    from forensics.library import Library

    lib = Library.build(log=log)
    if len(lib) == 0:
        raise RuntimeError("no original recordings found in raw/ or data/originals/")
    return lib


def own_original(lib, clip_path: Path) -> set[str]:
    """For role 1's own recordings (data/real/speakerX_real_03.wav <- raw/mine/speakerX_real_03.m4a)."""
    stem = clip_path.stem
    return {o.id for o in lib.originals if Path(o.id).stem == stem}


def window_scores(audio, lib) -> list[float]:
    from forensics.compare import _windows, speech_mask
    from forensics.fingerprint import fingerprint

    Q, db = fingerprint(audio)
    starts, X, _ = _windows(Q, speech_mask(db))
    if not starts:
        return []
    return [m[0][2] if m else 0.0 for m in lib.search(X)]


# ================================================================== library
def cmd_library(_args) -> int:
    lib = library()
    lines = [f"# Role 5 — library of original recordings ({stamp()})", "",
             f"{len(lib)} originals, {lib.hours * 60:.1f} minutes in total.", "",
             "| original | speaker | mufti | minutes |", "|---|---|---|---|"]
    for m in lib.manifest():
        lines.append(f"| {m['id']} | {m['speaker']} | {m['sheikh_id']} | {m['minutes']} |")
    lines += ["", "Add full lectures from the official sources to `data/originals/` (file name starting with the",
              "role-1 speaker name, e.g. `speakerA_lecture3.mp3`) and run this again."]
    write_report("library.md", lines)
    print(f"{len(lib)} originals, {lib.hours * 60:.1f} min")
    return 0


# ================================================================== calibrate (original search)
def cmd_calibrate(args) -> int:
    from forensics.compare import compare_with_original
    from forensics.verdict import load_settings, save_settings

    lib = library()
    cl, _ = clips()
    conds = args.conditions.split(",")
    neg: list[float] = []
    pos: list[float] = []
    neg_src = Counter()
    t0 = time.perf_counter()
    cal = [c for c in cl if c.split == "cal"]
    for i, c in enumerate(cal, 1):
        for cond in conds:
            x = audio_of(c.path, cond)
            if c.label == "fake":                       # generated speech: never in the library
                neg += window_scores(x, lib)
                neg_src["generated"] += 1
                continue
            own = own_original(lib, c.path)
            if not own and cond == "clean":
                r = compare_with_original(x, lib)
                own = {r.source} if r.source else set()
                c._own = own
            own = own or getattr(c, "_own", set())
            if not own:
                continue
            pos += window_scores(x, lib)
            neg += window_scores(x, lib.without(own))   # same voice, its own recording removed
            neg_src[f"{c.sheikh_id} (own recording removed)"] += 1
        if i % 20 == 0:
            print(f"  {i}/{len(cal)} cal clips ({time.perf_counter() - t0:.0f} s)", flush=True)
    neg_a, pos_a = np.array(neg), np.array(pos)
    if neg_a.size < 50:
        print("ERROR: too few negative windows to calibrate")
        return 1
    q999 = float(np.quantile(neg_a, 0.999))
    match = float(np.clip(np.ceil((q999 + 0.02) * 100) / 100, 0.5, 0.8))
    strong = float(np.clip(np.ceil((neg_a.max() + 0.03) * 100) / 100, match + 0.08, 0.92))
    s = load_settings()
    match, strong = round(match, 2), round(strong, 2)
    s["compare"] = {"match": match, "strong": strong, "calibrated": True,
                    "negative_windows": int(neg_a.size), "positive_windows": int(pos_a.size)}
    save_settings(s)
    lines = [f"# Role 5 — calibration of the original search ({stamp()})", "",
             "Window = 1 s of the clip searched in every original. Score = normalized correlation of fingerprints.",
             "Negatives = windows whose true original is NOT in the library: generated speech, and real clips",
             "searched with their own recording removed (same voice, other recordings still there).",
             "Positives = windows of real clips with their original in the library.", "",
             f"Conditions: {', '.join(conds)}. Clips used: {dict(neg_src)}", "",
             "| | windows | median | 99.9% | max |", "|---|---|---|---|---|",
             f"| negatives | {neg_a.size} | {np.median(neg_a):.3f} | {q999:.3f} | {neg_a.max():.3f} |",
             f"| positives | {pos_a.size} | {np.median(pos_a) if pos_a.size else float('nan'):.3f} | "
             f"{np.quantile(pos_a, 0.001) if pos_a.size else float('nan'):.3f} (0.1%) | |", "",
             f"**match = {match}** (a window counts as found; a clip needs 2 agreeing windows)  ",
             f"**strong = {strong}** (one window alone is enough)  ",
             f"Positive windows at or above match: {pct(rate(pos_a >= match))}"]
    write_report("calibration.md", lines)
    print(f"match={match} strong={strong} (negatives max {neg_a.max():.3f}, 99.9% {q999:.3f})")
    return 0


# ================================================================== evaluate (original search)
def _cut_clip(lib, src_id: str, start: float, gap: float, fade: bool, part: float = 3.5):
    from forensics.library import decode

    o = next(o for o in lib.originals if o.id == src_id)
    if start + 2 * part + gap > o.duration - 0.2:
        return None
    a = decode(o.path, start, part)
    b = decode(o.path, start + part + gap, part)
    if a.size < part * 15000 or b.size < part * 15000:
        return None
    if fade:
        n = int(0.03 * 16000)
        w = np.linspace(0, 1, n, dtype=np.float32)
        return np.concatenate([a[:-n], a[-n:] * (1 - w) + b[:n] * w, b[n:]]), a.size / 16000 - n / 32000
    return np.concatenate([a, b]), a.size / 16000


def cmd_evaluate(args) -> int:
    from forensics.compare import compare_with_original
    from forensics.verdict import load_settings

    s = load_settings()["compare"]
    if not s.get("calibrated"):
        print("  (compare thresholds not calibrated yet: using defaults)")
    lib = library()
    cl, _ = clips()
    conds = args.conditions.split(",")
    test_real = [c for c in cl if c.split == "test" and c.label == "real"]
    test_fake = [c for c in cl if c.split == "test" and c.label == "fake"]
    log = manip_log()
    R = defaultdict(lambda: defaultdict(list))   # R[metric][cond] -> flags
    t0 = time.perf_counter()
    found_at: dict[str, tuple[str, float]] = {}
    rnd = random.Random(7)

    def tick(i, n, what):
        if i % 20 == 0:
            print(f"  {what}: {i}/{n} ({time.perf_counter() - t0:.0f} s)", flush=True)

    # A. held-out real clips whose original is in the library
    for i, c in enumerate(test_real, 1):
        own = own_original(lib, c.path)
        for cond in conds:
            r = compare_with_original(audio_of(c.path, cond), lib, s)
            found = bool(r.pieces)
            if c.is_mufti:
                R["A_found_mufti"][cond].append(found)
                if found:
                    R["A_right_mufti"][cond].append(r.sheikh_id == c.sheikh_id)
                    R["A_false_edit"][cond].append(r.status == "edited")
                    if cond == "clean":
                        found_at[c.file] = (r.source, r.pieces[0].orig_start - r.pieces[0].clip_start)
            else:
                R["A_found_other"][cond].append(found)
                if found:
                    R["A_right_file"][cond].append(bool(own) and r.source in own)
                    R["A_false_edit"][cond].append(r.status == "edited")
            if found and cond != "clean" and c.file in found_at:
                src, off = found_at[c.file]
                R["A_same_place"][cond].append(r.source == src and abs((r.pieces[0].orig_start - r.pieces[0].clip_start)
                                                                     - off) <= TOL)
        tick(i, len(test_real), "held-out clips")

    # B. role 1's spliced clips (two recordings joined) and C. cropped clips
    for i, row in enumerate(log, 1):
        path = ROOT / "data" / row["file"]
        t = float(row["time_sec"])
        kind = row["type"]
        for cond in conds:
            r = compare_with_original(audio_of(path, cond), lib, s)
            if row["file"].startswith("spliced/"):
                ok = any(e.kind in ("joined", "cut") and abs(e.time - t) <= TOL for e in r.edits)
                R[f"B_join_{kind}"][cond].append(ok)
                R["B_join_all"][cond].append(ok)
                if ok:
                    R["B_err"][cond].append(min(abs(e.time - t) for e in r.edits if e.kind in ("joined", "cut")))
                srcs = {Path(p.source).stem for p in r.pieces}
                R["B_sources"][cond].append({Path(row["source_a"]).stem, Path(row["source_b"]).stem} <= srcs)
            else:
                found = bool(r.pieces)
                R["C_found"][cond].append(found)
                if found:
                    last = r.pieces[-1]
                    R["C_end"][cond].append(abs(last.orig_end - t) <= TOL and r.status == "excerpt")
                    R["C_mid"][cond].append(bool(r.cut_mid_speech_end))
                    R["C_false_edit"][cond].append(r.status == "edited")
        tick(i, len(log), "spliced/cropped")

    # D. internal cuts inside the muftis' own recordings (made here in memory, never saved)
    made = 0
    for c in [c for c in test_real if c.is_mufti and c.file in found_at][: args.max_cuts]:
        src, off = found_at[c.file]
        gap = round(rnd.uniform(1.0, 4.0), 2)
        fade = made % 2 == 1
        res = _cut_clip(lib, src, max(0.0, off), gap, fade)
        if res is None:
            continue
        x0, t = res
        made += 1
        for cond in conds:
            x = x0 if cond == "clean" else __import__("voiceid.audio", fromlist=["degrade"]).degrade(x0, cond, seed=made)
            r = compare_with_original(x, lib, s)
            cuts = [e for e in r.edits if e.kind == "cut" and abs(e.time - t) <= TOL]
            R["D_cut"][cond].append(bool(cuts))
            if cuts:
                R["D_gap"][cond].append(abs(cuts[0].removed_sec - gap) <= TOL)
    # E. originals NOT in the library
    loo = [c for c in test_real if (own_original(lib, c.path) or (c.file in found_at))]
    for i, c in enumerate(loo, 1):
        own = own_original(lib, c.path) or {found_at[c.file][0]}
        sub = lib.without(own)
        for cond in conds:
            r = compare_with_original(audio_of(c.path, cond), sub, s)
            R["E_loo_found"][cond].append(bool(r.pieces))
        tick(i, len(loo), "own recording removed")
    for c in test_fake:
        for cond in conds:
            r = compare_with_original(audio_of(c.path, cond), lib, s)
            R["E_tts_found"][cond].append(bool(r.pieces))

    def row(label, key, n_key=None):
        cells = [pct(rate(R[key][c])) + f" ({len(R[key][c])})" for c in conds]
        return f"| {label} | " + " | ".join(cells) + " |"

    def sec(title):
        return title + " |" * len(conds)

    err = {c: (f"{np.mean(R['B_err'][c]) * 1000:.0f} ms" if R["B_err"][c] else "n/a") for c in conds}
    lines = [f"# Role 5 — compare_with_original: evaluation ({stamp()})", "",
             f"Library: {len(lib)} originals, {lib.hours * 60:.1f} min. Thresholds: match {s['match']}, "
             f"strong {s['strong']} (calibrated: {s.get('calibrated', False)}).",
             f"Clips: role 4's **test** split only (never used for calibration). Tolerance for times: ±{TOL} s.",
             "Cells: rate (number of clips).", "",
             "| | " + " | ".join(conds) + " |", "|---|" + "---|" * len(conds),
             sec("| **A. Clip from an original in the library** |"),
             row("mufti clip found", "A_found_mufti"),
             row("... found in a recording of the right mufti", "A_right_mufti"),
             row("team-member clip found", "A_found_other"),
             row("... found in its own recording", "A_right_file"),
             row("same place as the clean copy (phone / noisy)", "A_same_place"),
             row("wrongly reported as edited", "A_false_edit"),
             sec("| **B. Two recordings joined (role 1's spliced clips)** |"),
             row("join found at the right time - hard cut", "B_join_hard"),
             row("join found at the right time - 30 ms fade", "B_join_fade"),
             row("join found at the right time - fade + noise", "B_join_noisy"),
             row("join found at the right time - all", "B_join_all"),
             row("both source recordings named", "B_sources"),
             f"| mean time error of found joins | " + " | ".join(err[c] for c in conds) + " |",
             sec("| **C. Cut before the end (role 1's cropped clips)** |"),
             row("found", "C_found"),
             row("reported as excerpt ending at the right place", "C_end"),
             row("reported 'speaker was still talking'", "C_mid"),
             row("wrongly reported as edited", "C_false_edit"),
             sec(f"| **D. Words removed inside a mufti recording ({made} clips made in memory)** |"),
             row("cut found at the right time", "D_cut"),
             row("... removed length right (±0.25 s)", "D_gap"),
             sec("| **E. Original NOT in the library** (should NOT be found) |"),
             row("real clip, its own recording removed -> wrongly found", "E_loo_found"),
             row("generated speech -> wrongly found", "E_tts_found"), "",
             "## Limits",
             "- The spliced / cropped clips are role 1's own recordings (team member's voice), joined from her own",
             "  recordings. The muftis' cuts (D) are made in memory from role 1's downloaded lectures and never saved.",
             "- Phone = 8 kHz band-limited copy; noisy = white noise at 15 dB SNR. Real re-shared clips (WhatsApp",
             "  re-encoding, music, speed change) can be harder.",
             "- 'Not found' only means the original is not in the library; it never means the clip is fake.",
             "  The library only covers what role 1 downloaded."]
    write_report("compare.md", lines)
    print("\n".join(lines[6:]))
    return 0


# ================================================================== artifact (generated speech)
def _art_feats(c, cond):
    from forensics.artifact import clip_features

    CACHE.mkdir(parents=True, exist_ok=True)
    st = c.path.stat()
    key = hashlib.sha1(f"{c.file}|{st.st_size}|{int(st.st_mtime)}|{cond}|art1".encode()).hexdigest()[:20]
    f = CACHE / f"art_{key}.npy"
    if f.is_file():
        return np.load(f)
    v = clip_features(audio_of(c.path, cond))
    np.save(f, v)
    return v


def cmd_artifact(args) -> int:
    from forensics.artifact import FEATURE_NAMES
    from forensics.lr import LogReg
    from forensics.verdict import MODELS, load_settings, save_settings

    cl, _ = clips()
    conds = args.conditions.split(",")
    use = [c for c in cl if c.label in ("real", "fake", "ref")]
    t0 = time.perf_counter()
    F = {}
    for i, c in enumerate(use, 1):
        for cond in conds:
            F[(c.file, cond)] = _art_feats(c, cond)
        if i % 50 == 0:
            print(f"  features {i}/{len(use)} ({time.perf_counter() - t0:.0f} s)", flush=True)
    fake = [c for c in use if c.label == "fake"]
    real = [c for c in use if c.label != "fake"]
    train_real = [c for c in real if c.split != "test"]
    test_real = [c for c in real if c.split == "test"]
    voices = sorted({c.speaker for c in fake})
    if len(fake) < 6 or not test_real:
        print("ERROR: not enough generated / real clips")
        return 1

    def XY(rs, fs, cs=conds):
        X = [F[(c.file, cd)] for c in rs for cd in cs] + [F[(c.file, cd)] for c in fs for cd in cs]
        return np.array(X), np.r_[np.zeros(len(rs) * len(cs)), np.ones(len(fs) * len(cs))]

    def auc(p, y):
        pos, neg = p[y == 1], p[y == 0]
        return float((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean())

    lines = [f"# Role 5 — artifact_score (generated speech): evaluation ({stamp()})", "",
             f"Real speech: {len(real)} clips (muftis + team member). Generated: {len(fake)} clips, "
             f"{len(voices)} edge-tts voices ({', '.join(voices)}).",
             f"Each clip in {len(conds)} conditions ({', '.join(conds)}); features on speech frames only.", "",
             "## 1. Leave one generated voice out (the voice is never seen in training)", "",
             "| held-out voice | condition | AUC | generated flagged (p>=0.5) | real flagged (p>=0.5) |",
             "|---|---|---|---|---|"]
    for v in voices:
        Xtr, ytr = XY(train_real, [c for c in fake if c.speaker != v])
        m = LogReg(l2=3.0).fit(Xtr, ytr, FEATURE_NAMES)
        for cd in conds:
            Xte, yte = XY(test_real, [c for c in fake if c.speaker == v], [cd])
            p = m.proba(Xte)
            lines.append(f"| {v} | {cd} | {auc(p, yte):.2f} | {pct(rate(p[yte == 1] >= 0.5))} | "
                         f"{pct(rate(p[yte == 0] >= 0.5))} |")
    # final model: train split (all voices), test on test split
    ftr = [c for c in fake if c.split != "test"]
    fte = [c for c in fake if c.split == "test"]
    Xtr, ytr = XY(train_real, ftr)
    m = LogReg(l2=3.0).fit(Xtr, ytr, FEATURE_NAMES)
    Xc, yc = XY([c for c in train_real if c.split == "cal"] or train_real, ftr)
    pc = m.proba(Xc)
    high = float(np.clip(np.quantile(pc[yc == 0], 0.95) if (yc == 0).any() else 0.7, 0.5, 0.9))
    low = float(min(0.3, high - 0.1))
    lines += ["", "## 2. Final model: trained on the cal/enroll/ref clips, tested on the test split", "",
              f"Thresholds (from training data: 95% of real clips below `high`): low {low:.2f}, high {high:.2f}", "",
              "| condition | AUC | generated -> suspicious (>= high) | real -> suspicious (>= high) | real -> no signs (<= low) |",
              "|---|---|---|---|---|"]
    for cd in conds:
        Xte, yte = XY(test_real, fte, [cd])
        p = m.proba(Xte)
        lines.append(f"| {cd} | {auc(p, yte):.2f} | {pct(rate(p[yte == 1] >= high))} | {pct(rate(p[yte == 0] >= high))} | "
                     f"{pct(rate(p[yte == 0] <= low))} |")
    top = sorted(zip(m.w, FEATURE_NAMES), key=lambda t: -abs(t[0]))[:6]
    lines += ["", "Strongest features: " + ", ".join(f"{n} ({w:+.2f})" for w, n in top), "",
              "## Limits (say these with any number)",
              "- Only 3 generic edge-tts voices. This is NOT a test against voice clones of the muftis, and a good",
              "  voice clone may pass. Real speech here comes from a few recordings only.",
              "- The score is one signal among four; Sada never calls a clip fake from this score alone."]
    m.save(MODELS / "artifact.json", {"low": low, "high": high, "trained": stamp(), "conditions": conds})
    s = load_settings()
    s["artifact"] = {"low": round(low, 3), "high": round(high, 3), "calibrated": True}
    save_settings(s)
    write_report("artifact.md", lines)
    print("\n".join(lines[6:]))
    return 0


# ================================================================== splice (blind joins)
def cmd_splice(args) -> int:
    from forensics.lr import LogReg
    from forensics.splice import FEATURE_NAMES, TOLERANCE, candidates, label_candidates
    from forensics.verdict import MODELS, load_settings, save_settings

    cl, _ = clips()
    conds = args.conditions.split(",")
    spl = [r for r in manip_log() if r["file"].startswith("spliced/")]
    if len(spl) < 10:
        print("ERROR: role 1's spliced clips are missing")
        return 1
    items = [(ROOT / "data" / r["file"], float(r["time_sec"]), r["type"]) for r in spl]
    cal_s, test_s = items[0::2], items[1::2]
    real = [c for c in cl if c.label in ("real", "ref") and c.speaker != "test"]
    cal_r = [(c.path, None, "real") for c in real if c.split in ("cal", "ref", "enroll")][:150]
    test_r = [(c.path, None, "real") for c in real if c.split == "test"]

    def build(its, cd):
        X, y, g = [], [], []
        for gi, (p, t, _k) in enumerate(its):
            idx, Fm = candidates(audio_of(p, cd))
            X.append(Fm)
            y.append(label_candidates(idx, [t] if t is not None else []))
            g += [gi] * len(idx)
        return np.vstack(X), np.concatenate(y), np.array(g)

    Xs, ys = [], []
    for cd in conds:
        X, y, _ = build(cal_s + cal_r, cd)
        Xs.append(X)
        ys.append(y)
    m = LogReg(l2=2.0).fit(np.vstack(Xs), np.concatenate(ys), FEATURE_NAMES)

    def clip_max(its, cd):
        X, y, g = build(its, cd)
        p = m.proba(X)
        return [(float(p[g == i].max()) if (g == i).any() else 0.0,
                 float(p[g == i][y[g == i] == 1].max()) if (y[g == i] == 1).any() else 0.0) for i in range(len(its))]

    neg = np.concatenate([[a for a, _ in clip_max(cal_r, cd)] for cd in conds])
    thr = float(np.quantile(neg, 0.95))
    lines = [f"# Role 5 — detect_splice_points (blind, no original): evaluation ({stamp()})", "",
             f"Trained on half of role 1's spliced clips ({len(cal_s)}) + real clips; tested on the other half "
             f"({len(test_s)}) + held-out real clips ({len(test_r)}).",
             f"Threshold = 95% of real training clips below it: {thr:.3f}. A join counts if found within ±{TOLERANCE} s.", "",
             "| condition | hard cut | 30 ms fade | fade + noise | real clips wrongly flagged |", "|---|---|---|---|---|"]
    worst_det, worst_fa = 1.0, 0.0
    for cd in conds:
        res = clip_max(test_s, cd)
        rr = clip_max(test_r, cd)
        det = defaultdict(list)
        for (a, b), (_p, _t, k) in zip(res, test_s):
            det[k].append(b >= thr)
        fa = rate([a >= thr for a, _ in rr]) or 0.0
        d = {k: rate(v) for k, v in det.items()}
        lines.append(f"| {cd} | {pct(d.get('hard'))} | {pct(d.get('fade'))} | {pct(d.get('noisy'))} | {pct(fa)} |")
        if cd == "clean":
            worst_det = min(v for v in d.values() if v is not None)
        worst_fa = max(worst_fa, fa)
    usable = worst_det >= 0.6 and worst_fa <= 0.1
    lines += ["", f"**Used in the verdict: {'yes' if usable else 'NO'}** (needs >= 60% of joins found on clean clips with",
              "<= 10% of real clips flagged). When it is not used, Sada says it cannot judge edits without the original.",
              "", "## Why this is hard",
              "Role 1's joins are made inside the same speaker's recordings (same room, same phone, cut in mid-speech).",
              "Without the original there is often nothing left to hear. With the original in the library,",
              "compare_with_original finds these joins (see compare.md)."]
    m.save(MODELS / "splice.json", {"threshold": thr, "usable": usable, "trained": stamp()})
    s = load_settings()
    s["splice"] = {"threshold": round(thr, 4), "usable": bool(usable)}
    save_settings(s)
    write_report("splice.md", lines)
    print("\n".join(lines[4:]))
    return 0


# ================================================================== check one clip
def cmd_check(args) -> int:
    from forensics.verdict import Analyzer

    path = Path(args.file)
    if not path.is_file():
        print(f"ERROR: file not found: {path}")
        return 1
    a = Analyzer()
    v = a.analyze_file(path, args.sheikh)
    print(f"\n=== {v.file}  (attributed to: {v.claimed_sheikh}) ===")
    print(f"OVERALL: {v.overall}  |  {v.overall_ar}")
    for q, ans in (("1 voice", v.voice), ("2 generated", v.generated), ("3 edited", v.edited), ("4 complete", v.complete)):
        print(f"[{q}] {ans.status}: {ans.text_ar}")
    print(v.disclaimer_ar)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / "last_check.json"
    out.write_text(v.to_json(), encoding="utf-8")
    print(f"full result: {out.relative_to(ROOT)}")
    return 0


def run_all(args) -> int:
    steps = [("library", cmd_library), ("calibrate", cmd_calibrate), ("evaluate", cmd_evaluate),
             ("artifact", cmd_artifact), ("splice", cmd_splice)]
    failed = []
    for name, fn in steps:
        print(f"\n==================== {name} ====================", flush=True)
        try:
            if fn(args) != 0:
                failed.append(name)
        except Exception as exc:  # noqa: BLE001  keep going: one step must not hide the others
            import traceback

            traceback.print_exc()
            print(f"step '{name}' failed: {exc}")
            failed.append(name)
    print("\nALL DONE." if not failed else f"\nDONE WITH PROBLEMS in: {', '.join(failed)}", "Reports in reports/role5/")
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--conditions", default=",".join(CONDITIONS))
    common.add_argument("--max-cuts", type=int, default=40, help="evaluate: mufti clips used for internal cuts")
    for name, fn in (("library", cmd_library), ("calibrate", cmd_calibrate), ("evaluate", cmd_evaluate),
                     ("artifact", cmd_artifact), ("splice", cmd_splice)):
        sub.add_parser(name, parents=[common]).set_defaults(fn=fn)
    sub.add_parser("all", parents=[common]).set_defaults(fn=run_all)
    p = sub.add_parser("check", parents=[common])
    p.add_argument("file")
    p.add_argument("--sheikh", default="unknown", help="ibn_baz | al_fawzan | al_alsheikh | unknown")
    p.set_defaults(fn=cmd_check)
    args = ap.parse_args(argv)
    try:
        return int(args.fn(args) or 0)
    except ImportError as exc:
        print(f"ERROR: {exc}. Run run_role5.bat (installs what is missing), then try again.")
        return 1
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
