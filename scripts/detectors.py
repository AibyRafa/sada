r"""Sada vs public deepfake-audio detectors, on the SAME held-out clips (criterion: innovation, "a test proves the
added value, with the limits of the comparison").

  run_detectors.bat                      (installs `transformers` once, downloads the detectors, writes the report)
  .venv-role4\Scripts\python scripts\detectors.py [--models a,b] [--max-cuts 40]

Report: reports/role5/detectors.md. Nothing is assumed: every number is measured when the script runs.

The detectors are open models published on Hugging Face (Apache-2.0). They answer ONE question: "is this voice
generated?". Sada answers four. The test groups:
  real      held-out real clips of the muftis           (correct answer: genuine, not flagged)
  tts       held-out generated clips (edge-tts)          (correct answer: flagged)
  spliced   role 1's clips joined from two recordings     (correct answer: the join is found at the right second)
  cropped   role 1's clips cut before the end             (correct answer: "excerpt", right end in the original)
  cuts      speech removed inside a mufti recording       (made here in memory, never saved)
For a detector, "caught" = it flags the clip as generated (probability >= 0.5, its own decision).
For Sada, "caught" = the specific answer for that group (see the table header). Clean audio only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np  # noqa: E402

MODELS = {
    "garystafford/wav2vec2-deepfake-voice-detector":
        "Hugging Face, Apache-2.0; XLS-R 300M; trained on ElevenLabs, Amazon Polly, Kokoro, Hume AI, Speechify, Luvvoice + YouTube speech",
    "mo-thecreator/Deepfake-audio-detection": "Hugging Face, Apache-2.0; wav2vec2-base; training data not stated on its model card",
}
CACHE = ROOT / "cache" / "role5" / "detectors"
SR = 16000
MAX_SEC = 30.0
FAKE_WORDS = ("fake", "spoof", "synthetic", "generated", "ai", "deepfake")
REAL_WORDS = ("real", "bonafide", "bona-fide", "bona_fide", "human", "genuine")


def _forensics_cli():
    """scripts/forensics.py (named like the forensics package, so it is loaded by path)."""
    spec = importlib.util.spec_from_file_location("sada_forensics_cli", ROOT / "scripts" / "forensics.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pct(x) -> str:
    return "—" if x is None else f"{100 * x:.0f}%"


def rate(flags) -> float | None:
    flags = list(flags)
    return float(np.mean(flags)) if flags else None


def auc(p, y) -> float | None:
    p, y = np.asarray(p, float), np.asarray(y)
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return None
    return float((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean())


# ---------------------------------------------------------------------- detectors
class HFDetector:
    """A Hugging Face audio-classification model -> probability that the clip is generated."""

    def __init__(self, name: str):
        import torch
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        self.name = name
        self.torch = torch
        self.fe = AutoFeatureExtractor.from_pretrained(name)
        self.model = AutoModelForAudioClassification.from_pretrained(name).eval()
        labels = {int(k): str(v).lower() for k, v in self.model.config.id2label.items()}
        self.labels = labels
        fake = [i for i, l in labels.items() if any(w in l for w in FAKE_WORDS) and not any(w in l for w in REAL_WORDS)]
        real = [i for i, l in labels.items() if any(w in l for w in REAL_WORDS)]
        if len(fake) == 1:
            self.fake_idx = fake[0]
        elif len(real) == 1 and len(labels) == 2:
            self.fake_idx = 1 - real[0]
        else:
            raise RuntimeError(f"cannot tell which label means 'generated': {labels}")
        self.sr = int(getattr(self.fe, "sampling_rate", SR) or SR)

    def __call__(self, audio: np.ndarray) -> float:
        x = np.asarray(audio, dtype=np.float32)[: int(MAX_SEC * SR)]
        if self.sr != SR:
            import librosa

            x = librosa.resample(x, orig_sr=SR, target_sr=self.sr)
        inp = self.fe(x, sampling_rate=self.sr, return_tensors="pt")
        with self.torch.no_grad():
            logits = self.model(**inp).logits[0]
        return float(self.torch.softmax(logits, -1)[self.fake_idx])


class DummyDetector:
    """--models dummy: random scores, only to test this script without downloading anything."""

    name, labels, fake_idx = "dummy", {0: "real", 1: "fake"}, 1

    def __call__(self, audio: np.ndarray) -> float:
        return float(np.random.default_rng(int(abs(float(np.sum(audio[:4000]))) * 1e4) % 2**32).random())


def cached(det, key: str, audio: np.ndarray) -> float:
    if det.name == "dummy":
        return det(audio)
    CACHE.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha1(f"{det.name}|{key}|{audio.size}|{float(np.sum(np.abs(audio))):.4f}".encode()).hexdigest()[:20]
    f = CACHE / f"{h}.txt"
    if f.is_file():
        return float(f.read_text())
    p = det(audio)
    f.write_text(f"{p:.6f}")
    return p


# ---------------------------------------------------------------------- the test groups (same as the other reports)
def build_groups(F, lib, max_cuts: int):
    from forensics.compare import compare_with_original
    from forensics.verdict import load_settings

    s = load_settings()["compare"]
    cl, _ = F.clips()
    G = {"real": [], "tts": [], "spliced": [], "cropped": [], "cuts": []}
    found_at = {}
    for c in cl:
        if c.split != "test":
            continue
        if c.label == "real" and c.is_mufti:
            a = F.audio_of(c.path)
            G["real"].append({"key": c.file, "audio": a, "sheikh": c.sheikh_id})
            r = compare_with_original(a, lib, s)
            if r.pieces:
                found_at[c.file] = (r.source, r.pieces[0].orig_start - r.pieces[0].clip_start)
        elif c.label == "fake":
            G["tts"].append({"key": c.file, "audio": F.audio_of(c.path), "voice": c.speaker})
    for row in F.manip_log():
        path = ROOT / "data" / row["file"]
        item = {"key": row["file"], "audio": F.audio_of(path), "t": float(row["time_sec"])}
        G["spliced" if row["file"].startswith("spliced/") else "cropped"].append(item)
    rnd = random.Random(7)
    for i, (file, (src, off)) in enumerate(list(found_at.items())[:max_cuts]):
        gap = round(rnd.uniform(1.0, 4.0), 2)
        res = F._cut_clip(lib, src, max(0.0, off), gap, i % 2 == 1)
        if res is not None:
            G["cuts"].append({"key": f"cut:{file}:{gap}", "audio": res[0], "t": res[1], "gap": gap})
    return G


def sada_caught(group: str, item: dict, analyzer, tol: float) -> bool:
    """Sada's specific answer for the group (whole pipeline: voice + generated + original + verdict)."""
    sheikhs = ["ibn_baz", "al_fawzan", "al_alsheikh"]
    if group == "real":
        v = analyzer.analyze(item["audio"], item["sheikh"], item["key"])
        return v.overall in ("edited", "misattributed", "likely_generated")          # = a false alarm
    if group == "tts":
        claim = sheikhs[int(hashlib.md5(item["key"].encode()).hexdigest(), 16) % 3]
        v = analyzer.analyze(item["audio"], claim, item["key"])
        return v.overall in ("likely_generated", "misattributed")
    v = analyzer.analyze(item["audio"], "unknown", item["key"])
    edits = v.edited.details.get("edits") or []
    if group == "spliced":
        return any(e["kind"] in ("joined", "cut") and abs(e["time"] - item["t"]) <= tol for e in edits)
    if group == "cuts":
        return any(e["kind"] == "cut" and abs(e["time"] - item["t"]) <= tol for e in edits)
    if group == "cropped":
        pieces = v.edited.details.get("pieces") or []
        return v.complete.status == "excerpt" and bool(pieces) and abs(pieces[-1]["orig_end"] - item["t"]) <= tol
    raise ValueError(group)


SADA_LABEL = {
    "real": "said «edited / misattributed / generated» (a false alarm)",
    "tts": "said «generated» or «not the sheikh's voice»",
    "spliced": "found the join at the right second (±0.25 s)",
    "cropped": "said «excerpt» with the right end in the original (±0.25 s)",
    "cuts": "found the removed speech at the right second (±0.25 s)",
}
GROUP_TITLE = {
    "real": "real mufti clips (should NOT be flagged)",
    "tts": "generated speech (edge-tts)",
    "spliced": "real speech joined from two recordings",
    "cropped": "real speech cut out of a longer recording",
    "cuts": "real mufti speech with words removed inside",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default=",".join(MODELS), help="comma-separated Hugging Face ids, or 'dummy'")
    ap.add_argument("--max-cuts", type=int, default=40)
    args = ap.parse_args(argv)

    F = _forensics_cli()
    from forensics.verdict import Analyzer

    t0 = time.perf_counter()
    analyzer = Analyzer(log=lambda *a: None)
    lib = analyzer.library
    G = build_groups(F, lib, args.max_cuts)
    print("clips: " + ", ".join(f"{k} {len(v)}" for k, v in G.items()), flush=True)

    # Sada
    sada = {}
    for g, items in G.items():
        sada[g] = rate(sada_caught(g, it, analyzer, F.TOL) for it in items)
    # the same task as the detectors: Sada's "generated?" answer alone (no voiceprint, no original search)
    from forensics.artifact import artifact_score

    hi = analyzer.settings["artifact"]["high"]
    gen_only = {g: rate((artifact_score(it["audio"], analyzer.artifact_model) or 0.0) >= hi for it in G[g])
                for g in ("real", "tts")} if analyzer.artifact_model is not None else {}
    print(f"Sada done ({time.perf_counter() - t0:.0f} s)", flush=True)

    # detectors
    dets, failed = [], []
    for name in [m for m in args.models.split(",") if m]:
        try:
            print(f"loading {name} (first time: download from Hugging Face)...", flush=True)
            dets.append(DummyDetector() if name == "dummy" else HFDetector(name))
        except Exception as e:  # noqa: BLE001
            failed.append((name, f"{type(e).__name__}: {e}"))
            print(f"  could not load {name}: {e}", flush=True)
    scores = {}
    for d in dets:
        for g, items in G.items():
            scores[(d.name, g)] = [cached(d, it["key"], it["audio"]) for it in items]
        print(f"{d.name} done ({time.perf_counter() - t0:.0f} s)", flush=True)

    # report
    names = [d.name for d in dets]
    L = [f"# Sada vs public deepfake detectors ({dt.datetime.now():%Y-%m-%d %H:%M})", "",
         "Same held-out clips as the other reports, clean audio. A detector \"catches\" a clip when it flags it as "
         "generated (its own decision, probability >= 0.5). Sada's answer for each group is written in the last column.", "",
         "## Detectors used", ""]
    for d in dets:
        L.append(f"- `{d.name}`: {MODELS.get(d.name, 'test only')}. "
                 f"Labels: {d.labels}; 'generated' = label {d.fake_idx}.")
    for n, e in failed:
        L.append(f"- `{n}`: **could not be run here** ({e}).")
    L += ["", "## Results", "",
          "| group | clips | " + " | ".join(f"`{n.split('/')[-1]}` flagged as generated" for n in names)
          + " | Sada | what Sada had to say |",
          "|---|---|" + "---|" * len(names) + "---|---|"]
    for g, items in G.items():
        cells = [pct(rate(np.array(scores[(n, g)]) >= 0.5)) for n in names]
        L.append(f"| {GROUP_TITLE[g]} | {len(items)} | " + " | ".join(cells) + f" | **{pct(sada[g])}** | {SADA_LABEL[g]} |")
    if gen_only:
        L += ["", f"Same task as the detectors, Sada's generated-speech check alone (score >= its calibrated "
              f"threshold {hi:.2f}): real mufti clips flagged {pct(gen_only['real'])}, generated clips flagged "
              f"{pct(gen_only['tts'])}. (Sada's model was trained on other edge-tts clips of the same 3 voices; "
              "the detectors never saw these voices.)"]
    L += ["", "## Generated vs real only (the detectors' own task)", "",
          "| detector | AUC real vs generated (1.00 = perfect ranking) |", "|---|---|"]
    for n in names:
        p = scores[(n, "real")] + scores[(n, "tts")]
        y = [0] * len(scores[(n, "real")]) + [1] * len(scores[(n, "tts")])
        a = auc(p, y)
        L.append(f"| `{n}` | {'—' if a is None else f'{a:.2f}'} |")
    L += ["", "## Limits of this comparison",
          "- Small data: the clip counts are in the table. Clean audio only.",
          "- The generated clips are 3 generic edge-tts voices, not voice clones of the muftis; a detector trained on",
          "  other generators may do better or worse on real clones.",
          "- The detectors are used as published, with their own 0.5 decision; they were not tuned on our data.",
          "- Sada's original search needs the original recording in its library; the detectors need nothing.",
          "- Sada's 'tts' answer includes «not the sheikh's voice»: the clip was attributed to a mufti, as in real use."]
    out = ROOT / "reports" / "role5" / "detectors.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nreport: {out.relative_to(ROOT)}  ({time.perf_counter() - t0:.0f} s)")
    return 0 if dets else 1


if __name__ == "__main__":
    raise SystemExit(main())
