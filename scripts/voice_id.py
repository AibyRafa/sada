r"""Sada — Role 4 (voice identity), built on role 1's data. Run from the project folder:

  .venv-role4\Scripts\python scripts\voice_id.py check       does Resemblyzer work here?
  .venv-role4\Scripts\python scripts\voice_id.py data        role 1's clips as role 4 uses them
  .venv-role4\Scripts\python scripts\voice_id.py compare     try 4 methods, pick the best on the cal split
  .venv-role4\Scripts\python scripts\voice_id.py build       voiceprints (chosen method) -> data/voiceprints/
  .venv-role4\Scripts\python scripts\voice_id.py calibrate   thresholds from the cal split (+ other voices)
  .venv-role4\Scripts\python scripts\voice_id.py evaluate    held-out test split: clean, phone, noisy
  .venv-role4\Scripts\python scripts\voice_id.py test FILE --sheikh ibn_baz     one clip
  .venv-role4\Scripts\python scripts\voice_id.py all         check, data, compare, build, calibrate, evaluate

Splits (role 1's data/manifest.csv): ref = data/ref; real clips of each mufti in thirds:
enroll (may join the voiceprint), cal (tunes thresholds), test (held out). Other voices: cal / test.
Reports: reports/role4/. Settings: voiceid/thresholds.yaml. Cache: cache/role4/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:  # never crash on a console that cannot print a character
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

import numpy as np  # noqa: E402

from voiceid import SHEIKHS  # noqa: E402
from voiceid import thresholds as th_mod  # noqa: E402

REPORTS = ROOT / "reports" / "role4"
MIN_TRIALS = 20
FIX = {
    "numpy": "pip install numpy", "scipy": "pip install \"scipy<2.0\"", "librosa": "pip install librosa",
    "soundfile": "pip install soundfile", "yaml": "pip install pyyaml",
    "torch": "pip install torch --index-url https://download.pytorch.org/whl/cpu",
    "webrtcvad": "pip install webrtcvad-wheels", "resemblyzer": "pip install --no-deps resemblyzer",
}


def get_encoder():
    from voiceid.encoder import ResemblyzerEncoder

    return ResemblyzerEncoder()


def stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def write_report(name: str, lines: list[str], append: bool = False) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / name
    with path.open("a" if append else "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


# ================================================================== shared machinery
class Data:
    """Role 1's clips + cached window embeddings, loaded lazily per (split, condition)."""

    def __init__(self, enc, args):
        from voiceid.dataset import load_clips

        self.enc, self.no_cache = enc, getattr(args, "no_cache", False)
        t = th_mod.load()["identity"]
        self.win, self.hop = float(t["window_sec"]), float(t["hop_sec"])
        self.clips, self.problems = load_clips()
        self._emb: dict[tuple[str, str], np.ndarray] = {}

    def split(self, *names, mufti: bool | None = None):
        return [c for c in self.clips if c.split in names and (mufti is None or c.is_mufti == mufti)]

    def emb(self, clips, condition="clean", label=""):
        from voiceid.dataset import clip_embeddings

        todo = [c for c in clips if (c.file, condition) not in self._emb]
        t0 = time.perf_counter()
        for i, c in enumerate(todo, 1):
            self._emb[(c.file, condition)] = clip_embeddings(self.enc, c, self.win, self.hop, condition,
                                                             use_cache=not self.no_cache)
            if i % 50 == 0:
                print(f"    {label} {condition}: {i}/{len(todo)} clips ({time.perf_counter() - t0:.0f} s)", flush=True)
        if todo:
            print(f"  embedded {len(todo)} {label} clips ({condition}) in {time.perf_counter() - t0:.0f} s", flush=True)
        return {c.file: self._emb[(c.file, condition)] for c in clips}


def make_model(data: Data, method, keep: float = 0.7):
    """(voiceprints, background, reports per sheikh) for a method.

    Sources: role 1's ref clips; with enroll=ref+real also the "enroll" third of the
    real clips; with +phone also phone-quality copies of both. Each source gets its own
    robust centroid and a voiceprint is their average (no source dominates).
    """
    from voiceid.scoring import background_mean, transform
    from voiceid.voiceprints import build_voiceprint

    sources = [("ref", "clean")]
    if method.enroll in ("ref+real", "ref+real+phone"):
        sources.append(("enroll", "clean"))
    if method.enroll == "ref+real+phone":
        sources += [("ref", "phone"), ("enroll", "phone")]
    embs = {}  # (split, condition) -> {file: E}
    for split, cond in sources:
        embs[(split, cond)] = data.emb(data.split(split, mufti=True), cond, label=f"enrol-{split}")
    mu = None
    if method.scoring == "centered":
        arrays, names = [], []
        for (split, cond), d in embs.items():
            for c in data.split(split, mufti=True):
                arrays.append(d[c.file])
                names.append(c.sheikh_id)
        others = data.split("cal", mufti=False)
        for c, E in zip(others, data.emb(others, label="cal-other").values()):
            arrays.append(E)
            names.append(c.speaker)
        mu = background_mean(arrays, names)
    per_sheikh, groups = defaultdict(dict), {}
    for (split, cond), d in embs.items():
        for c in data.split(split, mufti=True):
            if len(d[c.file]):
                key = c.file if cond == "clean" else f"{c.file} [{cond}]"
                per_sheikh[c.sheikh_id][key] = transform(d[c.file], mu)
                groups[key] = f"{split}/{cond}"
    vps, reports = {}, {}
    for sid, d in sorted(per_sheikh.items()):
        vps[sid], reports[sid] = build_voiceprint(d, keep=keep, groups=groups)
    return vps, mu, reports


def items(data: Data, clips, mu, condition="clean", label=""):
    from voiceid.calibration import Item
    from voiceid.scoring import transform

    e = data.emb(clips, condition, label)
    return [Item(c.file, c.sheikh_id, c.speaker, transform(e[c.file], mu)) for c in clips]


def calibrate_method(data: Data, method, conditions=("clean", "phone", "noisy"), max_false=0.05, keep=0.7):
    from voiceid.calibration import trials, two_thresholds, eer

    vps, mu, reports = make_model(data, method, keep)
    pct = float(th_mod.load()["identity"]["percentile"])
    cal = data.split("cal")
    tr = None
    for cond in conditions:
        part = trials(items(data, cal, mu, cond, "cal"), vps, pct)
        if tr is None:
            tr = part
        else:
            tr.genuine += part.genuine
            tr.impostor_mufti += part.impostor_mufti
            tr.impostor_other += part.impostor_other
    rate, t_eer = eer(tr.genuine, tr.impostor)
    low, high = two_thresholds(tr.genuine, tr.impostor, max_false) if tr.genuine and tr.impostor else (0.0, 1.0)
    return {"vps": vps, "mu": mu, "reports": reports, "trials": tr, "eer": rate, "t_eer": t_eer,
            "low": low, "high": high}


def evaluate_method(data: Data, vps, mu, low, high, conditions=("clean", "phone", "noisy")):
    from voiceid.calibration import evaluate

    pct = float(th_mod.load()["identity"]["percentile"])
    test = data.split("test")
    return {cond: evaluate(items(data, test, mu, cond, "test"), vps, pct, low, high) for cond in conditions}


# ================================================================== commands
def cmd_check(_args) -> int:
    print(f"Python {sys.version.split()[0]} ({sys.executable})")
    for mod in ("numpy", "scipy", "yaml", "soundfile", "librosa", "torch", "webrtcvad", "resemblyzer"):
        try:
            m = importlib.import_module(mod)
            print(f"  {mod:<12} {getattr(m, '__version__', 'ok')}")
        except Exception as exc:
            print(f"  {mod:<12} MISSING ({type(exc).__name__}: {exc})   fix: {FIX[mod]}")
    try:
        from voiceid.audio import _loader

        print(f"  role 1 loader: {'src.audio_utils.load_audio' if _loader() else 'not importable here, using librosa directly'}")
        t0 = time.perf_counter()
        enc = get_encoder()
        t1 = time.perf_counter()
        v = enc.embed((0.1 * np.random.default_rng(0).standard_normal(16000 * 3)).astype(np.float32), trim_silence=False)
        assert v is not None and v.shape == (256,), "unexpected embedding"
        print(f"OK: Resemblyzer loaded in {t1 - t0:.1f} s; one 3 s window in {(time.perf_counter() - t1) * 1000:.0f} ms.")
        return 0
    except Exception:
        traceback.print_exc()
        print("FAILED: install the MISSING packages above (run_role4.bat does it), then run again.")
        return 1


def cmd_data(_args) -> int:
    from voiceid.dataset import load_clips, summary

    clips, problems = load_clips()
    print("\n".join(summary(clips)))
    for p in problems[:30]:
        print(f"  problem: {p}")
    if len(problems) > 30:
        print(f"  ... {len(problems) - 30} more problems")
    return 0 if clips else 1


def cmd_compare(args) -> int:
    """Try every method; choose by the cal-split EER (the test split is only reported, never used to choose)."""
    from voiceid.calibration import EvalResult
    from voiceid.scoring import ALL_METHODS

    data = Data(get_encoder(), args)
    rows, results = [], []
    for m in ALL_METHODS:
        print(f"\n--- method: {m.name}")
        cal = calibrate_method(data, m, max_false=args.max_false, keep=args.keep)
        ev = evaluate_method(data, cal["vps"], cal["mu"], cal["low"], cal["high"])
        results.append((m, cal, ev))
        c = ev["clean"]
        rows.append(
            f"| {m.name} | {cal['eer']:.1%} | {c.identified}/{c.clips} | {EvalResult.rate(c.right, 'match'):.0%} | "
            f"{EvalResult.rate(c.wrong, 'mismatch'):.0%} | {EvalResult.rate(c.wrong, 'match'):.0%} | "
            f"{ev['phone'].identified}/{ev['phone'].clips} | {ev['noisy'].identified}/{ev['noisy'].clips} |")
        print(rows[-1])
    best = min(results, key=lambda r: (round(r[1]["eer"], 3), ALL_METHODS.index(r[0])))[0]
    lines = [f"# Method comparison — {stamp()}", "",
             "Chosen by the EER on the **cal** split (clean + phone + noisy clips). The test columns are shown for "
             "information only; they never decide.", "",
             "| method | cal EER | test clean: closest right | right mufti -> match | wrong mufti -> mismatch | "
             "wrong mufti -> match | test phone: closest right | test noisy: closest right |",
             "|---|---|---|---|---|---|---|---|", *rows, "", f"**Chosen: {best.name}**", ""]
    path = write_report("compare.md", lines)
    th = th_mod.load()
    th["identity"].update(scoring=best.scoring, enroll=best.enroll)
    th_mod.save(th)
    print(f"\nChosen: {best.name} (saved in voiceid/thresholds.yaml). Report: {rel(path)}")
    return 0


def cmd_build(args) -> int:
    from voiceid.scoring import Method, save_background
    from voiceid.voiceprints import VOICEPRINT_DIR, report_rows, save_voiceprint

    method = Method.from_thresholds(th_mod.load())
    data = Data(get_encoder(), args)
    vps, mu, reports = make_model(data, method, args.keep)
    if not vps:
        print("No enrolment clips with speech (data/ref).")
        return 1
    for old in VOICEPRINT_DIR.glob("*.npy"):
        if old.stem not in vps and not old.stem.startswith("_"):
            old.unlink()
    save_background(VOICEPRINT_DIR, mu)
    md = [f"# Voiceprints — {stamp()}", "", f"Method: {method.name}. Encoder: {data.enc.name}.", ""]
    for sid, vp in vps.items():
        reps = reports[sid]
        save_voiceprint(VOICEPRINT_DIR, sid, vp, {
            "sheikh_id": sid, "name": SHEIKHS[sid], "encoder": data.enc.name, "built": stamp(),
            "scoring": method.scoring, "enroll": method.enroll, "keep": args.keep, "clips": len(reps),
            "recordings": report_rows(reps)})
        sims = np.array([r.mean_similarity for r in reps])
        line = (f"{sid}: {len(reps)} clips, {sum(r.windows for r in reps)} windows; clip similarity to the "
                f"voiceprint median {np.median(sims):.3f}, lowest {sims.min():.3f}")
        print(line)
        md += [f"## {sid}", f"- {line}"]
        for r in reps:
            if r.flag and "[" not in r.recording_id:
                print(f"  FLAG {r.recording_id}: {r.flag} (similarity {r.mean_similarity:.3f})")
                md.append(f"- FLAG `{r.recording_id}` (similarity {r.mean_similarity:.3f}): {r.flag}")
        if len(reps) < 10:
            md.append(f"- NOTE: only {len(reps)} enrolment clips; more audio from other recordings would help.")
        md.append("")
    print(f"Saved to {rel(VOICEPRINT_DIR)}. Report: {rel(write_report('voiceprints.md', md))}")
    return 0


def cmd_calibrate(args) -> int:
    from voiceid.calibration import change_pairs, eer
    from voiceid.scoring import Method, transform

    th = th_mod.load()
    t = th["identity"]
    method = Method.from_thresholds(th)
    conds = tuple(c.strip() for c in args.conditions.split(",") if c.strip())
    data = Data(get_encoder(), args)
    cal = calibrate_method(data, method, conds, args.max_false, args.keep)
    tr, mu = cal["trials"], cal["mu"]
    g, imp = np.array(tr.genuine), np.array(tr.impostor)
    if len(g) == 0 or len(imp) == 0:
        print(f"Not enough trials (genuine {len(g)}, impostor {len(imp)}).")
        return 1

    # speaker-change threshold, in the same (transformed) space as identity_score
    enroll = data.split("ref", "enroll" if method.enroll != "ref" else "ref", mufti=True)
    e = data.emb(enroll, label="enrol")
    others = data.split("cal", mufti=False)
    eo = data.emb(others, label="cal-other")
    by_voice = defaultdict(list)
    for c in enroll:
        if len(e[c.file]):
            by_voice[c.sheikh_id].append(transform(e[c.file], mu))
    for c in others:
        if len(eo[c.file]):
            by_voice[c.speaker].append(transform(eo[c.file], mu))
    same, diff = change_pairs([transform(e[c.file], mu) for c in enroll if len(e[c.file]) > 1],
                              {k: np.concatenate(v) for k, v in by_voice.items()})
    change_t, change_line = None, "- Speaker change: not enough window pairs"
    if len(same) >= 10 and len(diff) >= 10:
        c_rate, change_t = eer(same, diff)
        change_line = (f"- Speaker change: {len(same)} same-voice / {len(diff)} different-voice window pairs, "
                       f"EER {c_rate:.1%} at similarity {change_t:.3f}")

    def q(a):
        a = np.asarray(a)
        return f"median {np.median(a):.3f}, 5-95% {np.quantile(a, .05):.3f} to {np.quantile(a, .95):.3f}" if len(a) else "none"

    n_cal = defaultdict(int)
    for c in data.split("cal"):
        n_cal[c.sheikh_id if c.is_mufti else c.speaker] += 1
    lines = [
        f"## Identity calibration — {stamp()}", "",
        f"- Method: {method.name}. Encoder {data.enc.name}; windows {data.win:g} s, hop {data.hop:g} s; "
        f"clip score = {float(t['percentile']):g}th percentile; clip conditions: {', '.join(conds)}",
        f"- Cal split ({', '.join(f'{k}: {v}' for k, v in sorted(n_cal.items()))}); the test split is kept for evaluate.",
        f"- Trials: {len(g)} genuine, {len(tr.impostor_mufti)} other-mufti, {len(tr.impostor_other)} other-voice",
        f"- Genuine: {q(g)}",
        f"- Other mufti: {q(tr.impostor_mufti)}",
        f"- Other voice: {q(tr.impostor_other)}",
        f"- Clip-level EER: {cal['eer']:.1%} at {cal['t_eer']:.3f}",
        f"- Thresholds (max {args.max_false:.0%} wrong per side): low {cal['low']:.3f}, high {cal['high']:.3f}",
        change_line,
        "- Caveat: clips of one mufti may come from the same few source videos; clips found online are harder.", "",
    ]
    print("\n" + "\n".join(lines))
    if cal["eer"] > 0.2:
        print("WARNING: EER above 20%: identity is weak on this data.")
    few = len(g) < MIN_TRIALS or len(imp) < MIN_TRIALS
    if few:
        print(f"Only {len(g)} genuine / {len(imp)} impostor trials (< {MIN_TRIALS}). Use --force to save anyway.")
    if args.dry_run or (few and not args.force):
        print("(dry run: thresholds not changed)")
        return 0
    t.update(low=round(cal["low"], 4), high=round(cal["high"], 4), calibrated=True)
    if change_t is not None:
        t["change_similarity"] = round(float(change_t), 4)
    th_mod.save(th)
    print(f"Saved voiceid/thresholds.yaml and {rel(write_report('calibration.md', lines, append=True))}")
    return 0


def cmd_evaluate(args) -> int:
    from voiceid.calibration import confusion_lines, report_lines
    from voiceid.scoring import Method, load_background
    from voiceid.voiceprints import VOICEPRINT_DIR, load_voiceprints

    conds = tuple(c.strip() for c in args.conditions.split(",") if c.strip())
    th = th_mod.load()
    t = th["identity"]
    method = Method.from_thresholds(th)
    if not t.get("calibrated"):
        print("NOTE: thresholds are placeholders (not calibrated). Run calibrate first for real numbers.")
    vps = load_voiceprints(VOICEPRINT_DIR)
    if not vps:
        print("No voiceprints yet. Run: build")
        return 1
    mu = load_background(VOICEPRINT_DIR) if method.scoring == "centered" else None
    data = Data(get_encoder(), args)
    low, high = float(t["low"]), float(t["high"])
    res = evaluate_method(data, vps, mu, low, high, conds)
    test = data.split("test")
    md = [f"# Role 4 evaluation — {stamp()}", "",
          f"Held-out test split of role 1's real clips ({sum(c.is_mufti for c in test)} mufti clips, "
          f"{sum(not c.is_mufti for c in test)} other/generated). Method: {method.name}. "
          f"Thresholds: low {low}, high {high} (calibrated: {t.get('calibrated', False)}). "
          "Each clip is scored like identity_score.", ""]
    for cond in conds:
        lines = report_lines(cond, res[cond])
        print("\n" + "\n".join(lines))
        md += lines + [""]
        if cond == "clean":
            conf = confusion_lines(res[cond])
            if conf:
                md += ["Confusion (clean): rows = true mufti, columns = closest voiceprint", ""] + conf + [""]
    md += ["- phone = 8 kHz telephone band (like re-recorded / WhatsApp clips); noisy = noise at 15 dB SNR.",
           "- Generated speech here is generic TTS, not a clone of a mufti: identity is not a deepfake detector "
           "(that is role 5).",
           "- Caveat: clips of one mufti may come from the same few source videos; clips found online are harder.", ""]
    print(f"\nReport: {rel(write_report('evaluation.md', md))}")
    return 0


def cmd_test(args) -> int:
    from voiceid.audio import load_audio
    from voiceid.identity import UNKNOWN, identity_score
    from voiceid.scoring import Method, load_background
    from voiceid.voiceprints import VOICEPRINT_DIR, load_voiceprints

    vps = load_voiceprints(VOICEPRINT_DIR)
    if not vps:
        print("No voiceprints yet. Run: build")
        return 1
    th = th_mod.load()
    t = th["identity"]
    mu = load_background(VOICEPRINT_DIR) if Method.from_thresholds(th).scoring == "centered" else None
    enc = get_encoder()
    audio = load_audio(args.file)
    t0 = time.perf_counter()
    r = identity_score(audio, args.sheikh if args.sheikh in SHEIKHS else UNKNOWN, enc, vps, th, mu)
    print(f"{Path(args.file).name}: {audio.size / 16000:.1f} s in {time.perf_counter() - t0:.1f} s")
    print(f"STATUS {r.status.upper()} | score {r.score} | compared with {r.target_id} | closest {r.best_match}")
    print("per mufti: " + ", ".join(f"{k} {v:.3f}" for k, v in sorted(r.per_sheikh.items(), key=lambda kv: -kv[1])))
    print(f"thresholds: low {t['low']} | high {t['high']} | calibrated: {t.get('calibrated', False)}")
    if r.note:
        print(f"note: {r.note}")
    for w in r.windows:
        print(f"  {w.start:6.1f}-{w.end:6.1f}  {w.score:6.3f}  {'#' * int(max(0.0, w.score) * 40)}")
    print(f"speaker changes at: {', '.join(f'{c:.1f}s' for c in r.speaker_changes) or 'none'}")
    return 0


def run_all(args) -> int:
    steps = [("check", cmd_check, None), ("data", cmd_data, None), ("compare", cmd_compare, None),
             ("build", cmd_build, None), ("calibrate", cmd_calibrate, "clean,phone,noisy"),
             ("evaluate", cmd_evaluate, "clean,phone,noisy")]
    for name, fn, cond in steps:
        print(f"\n==================== {name} ====================", flush=True)
        args.conditions = cond
        if fn(args) != 0:
            print(f"Stopped at '{name}'.")
            return 1
    print("\nALL DONE. Reports in reports/role4/")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--no-cache", action="store_true")
    common.add_argument("--keep", type=float, default=0.7, help="share of windows kept for the robust voiceprint")
    common.add_argument("--dry-run", action="store_true", help="calibrate: do not save thresholds")
    common.add_argument("--force", action="store_true", help="calibrate: save even with few trials")
    common.add_argument("--max-false", type=float, default=0.05)
    for name, fn in (("check", cmd_check), ("data", cmd_data), ("compare", cmd_compare), ("build", cmd_build)):
        sub.add_parser(name, parents=[common]).set_defaults(fn=fn)
    p = sub.add_parser("calibrate", parents=[common])
    p.add_argument("--conditions", default="clean,phone,noisy")
    p.set_defaults(fn=cmd_calibrate)
    p = sub.add_parser("evaluate", parents=[common])
    p.add_argument("--conditions", default="clean,phone,noisy")
    p.set_defaults(fn=cmd_evaluate)
    sub.add_parser("all", parents=[common]).set_defaults(fn=None)
    p = sub.add_parser("test", parents=[common])
    p.add_argument("file")
    p.add_argument("--sheikh", default="unknown", help="ibn_baz | al_fawzan | al_alsheikh | unknown")
    p.set_defaults(fn=cmd_test)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "all":
            return run_all(args)
        return int(args.fn(args) or 0)
    except ImportError as exc:
        print(f"ERROR: {exc}. Run run_role4.bat (installs what is missing), then try again.")
        return 1
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
