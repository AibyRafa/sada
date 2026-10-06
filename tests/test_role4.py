"""Role 4 tests with synthetic voices and a fake encoder (no model needed).

  .venv-role4\\Scripts\\python -m pytest tests -q      or      .venv-role4\\Scripts\\python tests\\test_role4.py
"""

import csv
import sys
import tempfile
import types
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from voiceid import thresholds as th_mod  # noqa: E402
from voiceid.calibration import Item, evaluate, trials, two_thresholds  # noqa: E402
from voiceid.identity import embed_windows, identity_score  # noqa: E402
from voiceid.voiceprints import build_voiceprint, robust_centroid  # noqa: E402

SR = 16000
VOICES = {"speakerA": (500, 300), "speakerB": (2500, 500), "speakerC": (1000, 150),
          "speakerX": (1700, 200), "tts1": (3500, 300)}


def speech(seconds, seed=0, center_hz=800.0, bandwidth=600.0):
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    band = np.fft.irfft(spec * np.exp(-0.5 * ((f - center_hz) / bandwidth) ** 2), n)
    t = np.arange(n) / SR
    env = 0.55 + 0.45 * np.sin(2 * np.pi * 4 * t + rng.uniform(0, 6.28))
    gate = np.clip((np.sin(2 * np.pi * 0.35 * t + rng.uniform(0, 6.28)) + 0.85) / 0.15, 0, 1)
    x = band * env * gate
    return (x / (np.abs(x).max() + 1e-9) * 0.6).astype(np.float32)


class FakeEncoder:
    name = "fake"

    def embed(self, audio):
        spec = np.abs(np.fft.rfft(audio)) ** 2
        v = np.log(np.array([b.mean() for b in np.array_split(spec[: len(spec) // 2], 16)]) + 1e-9)
        v = v - v.mean()
        return (v / (np.linalg.norm(v) + 1e-9)).astype(np.float32)


ENC = FakeEncoder()
TH = {"identity": {"low": 0.5, "high": 0.8, "window_sec": 3.0, "hop_sec": 1.5, "percentile": 75,
                   "change_similarity": 0.6}}


def write_wav(path, x):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def make_project(root: Path, n_ref=6, n_real=6, mislabel=False):
    """A folder laid out like role 1's: data/ref/<speaker>/, data/real, data/fake, data/manifest.csv."""
    rows, seed = [], 0
    for sp, (c, bw) in VOICES.items():
        mufti = sp in ("speakerA", "speakerB", "speakerC")
        if mufti:
            for i in range(1, n_ref + 1):
                seed += 1
                rel = f"ref/{sp}/{sp}_ref_{i:02d}.wav"
                write_wav(root / "data" / rel, speech(8, seed, c, bw))
                rows.append([rel, "ref", sp, "src", "ok", ""])
        label = "fake" if sp.startswith("tts") else "real"
        for i in range(1, n_real + 1):
            seed += 1
            rel = f"{label}/{sp}_{label}_{i:02d}.wav"
            write_wav(root / "data" / rel, speech(8, seed, c, bw))
            rows.append([rel, label, sp, "src", "ok", ""])
    if mislabel:  # a speakerB clip filed under speakerA's reference library
        rel = "ref/speakerA/speakerA_ref_99.wav"
        write_wav(root / "data" / rel, speech(8, 999, *VOICES["speakerB"]))
        rows.append([rel, "ref", "speakerA", "src", "ok", ""])
    rows.append(["spliced/speakerX_spliced_01.wav", "spliced", "speakerX", "", "", ""])  # not used by role 4
    with open(root / "data" / "manifest.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["file", "label", "speaker", "source", "consent", "notes"])
        w.writerows(rows)


def emb(sec, seed, sp):
    return embed_windows(speech(sec, seed, *VOICES[sp]), ENC, 3.0, 1.5)[1]


# ------------------------------------------------------------------ unit tests
def test_dataset_maps_role1_names_and_splits():
    from voiceid.dataset import load_clips

    with tempfile.TemporaryDirectory() as d:
        make_project(Path(d))
        clips, problems = load_clips(d)
        by = {(c.sheikh_id, c.split) for c in clips}
        assert ("ibn_baz", "ref") in by and ("al_fawzan", "cal") in by and ("al_alsheikh", "test") in by
        assert ("ibn_baz", "enroll") in by and ("other", "enroll") not in by
        assert ("other", "cal") in by and ("other", "test") in by
        a_real = [c for c in clips if c.speaker == "speakerA" and c.split != "ref"]
        assert [sum(c.split == s for c in a_real) for s in ("enroll", "cal", "test")] == [2, 2, 2]
        x_real = [c for c in clips if c.speaker == "speakerX"]
        assert {c.split for c in x_real} == {"cal", "test"}
        assert not any("spliced" in c.file for c in clips)
        assert any("missing file" in p for p in problems) is False
        clips2, problems2 = load_clips(d, mapping={"speakerA": "ibn_baz"})
        assert any("not in voiceid/speakers.yaml" in p for p in problems2)


def test_speakers_yaml_matches_role1_manifest_names():
    from voiceid.dataset import speaker_map

    m = speaker_map()
    assert m["speakerA"] == "ibn_baz" and m["speakerB"] == "al_fawzan" and m["speakerC"] == "al_alsheikh"
    assert m["speakerX"] == "other" and m["tts1"] == "other"


def test_identity_score_and_speaker_change():
    vps = {"ibn_baz": robust_centroid(emb(30, 1, "speakerA"))[0], "al_fawzan": robust_centroid(emb(30, 2, "speakerB"))[0]}
    r = identity_score(speech(12, 3, *VOICES["speakerA"]), "ibn_baz", ENC, vps, TH)
    assert r.status == "match" and r.best_match == "ibn_baz"
    r = identity_score(speech(12, 4, *VOICES["speakerB"]), "ibn_baz", ENC, vps, TH)
    assert r.status == "mismatch"
    both = np.concatenate([speech(8, 5, *VOICES["speakerA"]), speech(8, 6, *VOICES["speakerB"])])
    assert any(6 <= c <= 10 for c in identity_score(both, "ibn_baz", ENC, vps, TH).speaker_changes)
    assert identity_score(speech(4), "ibn_baz", None, {}, TH).status == "unavailable"


def test_voiceprint_flags_mislabelled_reference_clip():
    clips = {f"a{i}": emb(8, 10 + i, "speakerA") for i in range(10)}
    clips["wrong"] = emb(8, 50, "speakerB")
    _, reps = build_voiceprint(clips)
    flags = {r.recording_id for r in reps if r.flag}
    assert flags == {"wrong"}


def test_trials_and_evaluation():
    vps = {s: robust_centroid(emb(40, i, sp))[0] for i, (s, sp) in
           enumerate([("ibn_baz", "speakerA"), ("al_fawzan", "speakerB"), ("al_alsheikh", "speakerC")])}
    items = [Item(f"{sp}{i}", s, sp, emb(8, 100 + i * 7 + k, sp)) for k, (s, sp) in
             enumerate([("ibn_baz", "speakerA"), ("al_fawzan", "speakerB"), ("al_alsheikh", "speakerC"),
                        ("other", "speakerX"), ("other", "tts1")]) for i in range(4)]
    tr = trials(items, vps, 75)
    assert len(tr.genuine) == 12 and len(tr.impostor_mufti) == 24 and len(tr.impostor_other) == 24
    assert min(tr.genuine) > max(tr.impostor)
    r = evaluate(items, vps, 75, 0.5, 0.8)
    assert r.clips == 12 and r.identified == 12
    assert r.rate(r.right, "match") == 1.0 and r.rate(r.wrong, "match") == 0.0
    assert sum(r.generated.values()) == 12 and r.rate(r.generated, "match") == 0.0
    low, high = two_thresholds([0.95, 0.96, 0.97], [0.4, 0.5, 0.6])
    assert 0.55 <= low < high <= 0.96


def test_centered_scoring_widens_the_gap():
    """Resemblyzer embeddings are all positive (ReLU), so different voices share a big common part."""
    from voiceid.scoring import background_mean, transform

    rng = np.random.default_rng(0)
    common = np.abs(rng.standard_normal(256)) * 2.0
    def voice(seed, n=40):
        own = np.abs(np.random.default_rng(seed).standard_normal(256))
        return np.maximum(common + own + 0.3 * rng.standard_normal((n, 256)), 0).astype(np.float32)
    A, B, C, X = voice(1), voice(2), voice(3), voice(4)
    mu = background_mean([A, B, C, X])
    raw_cross = float(np.mean(transform(A, None) @ transform(B, None).T))
    cen_cross = float(np.mean(transform(A, mu) @ transform(B, mu).T))
    raw_same = float(np.mean(transform(A[:20], None) @ transform(A[20:], None).T))
    cen_same = float(np.mean(transform(A[:20], mu) @ transform(A[20:], mu).T))
    assert raw_cross > 0.7                                  # raw: different voices look alike
    assert (cen_same - cen_cross) > 2 * (raw_same - raw_cross)   # centered: the gap is much wider
    assert np.allclose(np.linalg.norm(transform(A, mu), axis=1), 1.0, atol=1e-5)


def test_decide_never_matches_when_another_mufti_fits_better():
    from voiceid.identity import decide

    per = {"ibn_baz": 0.80, "al_fawzan": 0.90, "al_alsheikh": 0.50}
    assert decide(per, "al_fawzan", 0.6, 0.75) == "match"
    assert decide(per, "ibn_baz", 0.6, 0.75) == "mismatch"      # Al-Fawzan fits clearly better
    per2 = {"ibn_baz": 0.80, "al_fawzan": 0.82}
    assert decide(per2, "ibn_baz", 0.6, 0.75) == "unclear"      # close call: never "match"
    assert decide({"ibn_baz": 0.5, "al_fawzan": 0.55}, "ibn_baz", 0.6, 0.75) == "mismatch"


def test_voiceprint_groups_keep_a_small_session():
    big = {f"ref{i}": emb(8, 200 + i, "speakerA") for i in range(12)}
    small = {f"real{i}": emb(8, 300 + i, "speakerC") for i in range(3)}  # stands in for a 2nd session
    both = {**big, **small}
    plain, _ = build_voiceprint(both)
    grouped, _ = build_voiceprint(both, groups={**{k: "ref" for k in big}, **{k: "real" for k in small}})
    s_mean = robust_centroid(np.concatenate(list(small.values())))[0]
    assert float(grouped @ s_mean) > float(plain @ s_mean)


def test_degrade_phone_removes_high_frequencies():
    from voiceid.audio import degrade

    x = speech(4, 1, 5000, 800)
    spec = np.abs(np.fft.rfft(degrade(x, "phone")))
    f = np.fft.rfftfreq(x.size, 1 / SR)
    assert spec[f > 4500].sum() < 0.05 * spec.sum()
    assert degrade(x, "noisy").shape == x.shape


def test_resemblyzer_wrapper_uses_training_preprocessing():
    calls = []
    names = ("resemblyzer", "resemblyzer.audio", "resemblyzer.hparams")
    pkg, audio, hp = (types.ModuleType(n) for n in names)
    hp.audio_norm_target_dBFS, hp.sampling_rate = -30, 16000

    def normalize_volume(wav, target_dBFS, increase_only=False, decrease_only=False):
        calls.append(("normalize", target_dBFS, increase_only))
        return wav * 2.0

    def trim_long_silences(wav):
        calls.append(("trim",))
        return wav[np.abs(wav) > 0.05]

    class VoiceEncoder:
        def __init__(self, device=None, verbose=True, weights_fpath=None):
            calls.append(("init", device, verbose))

        def embed_utterance(self, wav, return_partials=False, rate=1.3, min_coverage=0.75):
            calls.append(("embed",))
            return np.ones(256, np.float32) / 16.0

    audio.normalize_volume, audio.trim_long_silences = normalize_volume, trim_long_silences
    pkg.VoiceEncoder, pkg.audio, pkg.hparams = VoiceEncoder, audio, hp
    saved = {k: sys.modules.get(k) for k in names}
    sys.modules.update(dict(zip(names, (pkg, audio, hp))))
    try:
        from voiceid.encoder import ResemblyzerEncoder

        enc = ResemblyzerEncoder()
        assert enc.embed(speech(3, 50)).shape == (256,)
        assert calls[:4] == [("init", "cpu", False), ("normalize", -30, True), ("trim",), ("embed",)]
        assert enc.embed(np.zeros(3 * SR, np.float32)) is None
    finally:
        for k, m in saved.items():
            sys.modules.pop(k, None) if m is None else sys.modules.__setitem__(k, m)


# ------------------------------------------------------------------ end to end on a role-1-shaped folder
def test_cli_all_on_role1_layout():
    import voice_id
    from voiceid import dataset, voiceprints

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        make_project(d, mislabel=True)
        (d / "th.yaml").write_text(th_mod.DEFAULT.read_text(encoding="utf-8"), encoding="utf-8")
        old = (dataset.ROOT, dataset.CACHE_DIR, voiceprints.VOICEPRINT_DIR, th_mod.DEFAULT, voice_id.REPORTS,
               voice_id.ROOT, voice_id.get_encoder)
        dataset.ROOT, dataset.CACHE_DIR, voiceprints.VOICEPRINT_DIR = d, d / "cache", d / "data" / "voiceprints"
        th_mod.DEFAULT, voice_id.REPORTS, voice_id.ROOT = d / "th.yaml", d / "reports" / "role4", d
        voice_id.get_encoder = lambda: FakeEncoder()
        try:
            for cmd in ("data", "compare", "build"):
                assert voice_id.main([cmd]) == 0
            assert "Chosen:" in (d / "reports/role4/compare.md").read_text(encoding="utf-8")
            assert (d / "data" / "voiceprints" / "ibn_baz.npy").is_file()
            if th_mod.load()["identity"]["scoring"] == "centered":
                assert (d / "data" / "voiceprints" / "_background.npy").is_file()
            from voiceid.voiceprints import load_voiceprints
            assert "_background" not in load_voiceprints(d / "data" / "voiceprints")
            assert "FLAG `ref/speakerA/speakerA_ref_99.wav`" in (d / "reports/role4/voiceprints.md").read_text(encoding="utf-8")
            assert voice_id.main(["calibrate", "--force"]) == 0
            t = th_mod.load()["identity"]
            assert t["calibrated"] is True and t["low"] < t["high"]
            assert voice_id.main(["evaluate"]) == 0
            rep = (d / "reports/role4/evaluation.md").read_text(encoding="utf-8")
            assert "### clean" in rep and "### phone" in rep and "### noisy" in rep
            assert voice_id.main(["test", str(d / "data/real/speakerA_real_01.wav"), "--sheikh", "ibn_baz"]) == 0
            assert list((d / "cache").glob("*.npy"))
        finally:
            (dataset.ROOT, dataset.CACHE_DIR, voiceprints.VOICEPRINT_DIR, th_mod.DEFAULT, voice_id.REPORTS,
             voice_id.ROOT, voice_id.get_encoder) = old


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception:
                import traceback

                fails += 1
                print("FAIL", name)
                traceback.print_exc()
    print("all passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
