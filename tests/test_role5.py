"""Role 5 tests (fast, no real data needed). Run: .venv-role4\\Scripts\\python tests\\test_role5.py"""

from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

SR = 16000


def fake_speech(seconds: float, seed: int) -> np.ndarray:
    """Speech-like test signal: 60 ms blocks of noise with random spectral shape and loudness, with pauses."""
    rng = np.random.default_rng(seed)
    out = []
    n = int(0.06 * SR)
    for _ in range(int(seconds / 0.06)):
        if rng.random() < 0.12:
            out.append(rng.standard_normal(n) * 1e-4)
            continue
        spec = np.fft.rfft(rng.standard_normal(n))
        f = np.linspace(0, 1, spec.size)
        shape = np.exp(-((f - rng.uniform(0.02, 0.5)) ** 2) / rng.uniform(0.002, 0.05))
        out.append(np.fft.irfft(spec * shape, n) * rng.uniform(0.05, 0.5))
    x = np.concatenate(out).astype(np.float32)
    return x / (np.abs(x).max() + 1e-9) * 0.8


def make_library(originals: dict[str, np.ndarray]):
    from forensics.fingerprint import fingerprint
    from forensics.library import Library, Original

    origs, feats, dbs = [], [], []
    for name, x in originals.items():
        F, db = fingerprint(x)
        o = Original(name, Path(name), name.split("_")[0], "ibn_baz" if name.startswith("speakerA") else "other",
                     x.size / SR)
        origs.append(o)
        feats.append(F)
        dbs.append(db)
    return Library(origs, feats, dbs)


A = fake_speech(60, 1)
B = fake_speech(40, 2)
LIB = None


def lib():
    global LIB
    if LIB is None:
        LIB = make_library({"speakerA_video1": A, "speakerB_video1": B})
    return LIB


def test_fingerprint_survives_phone():
    from forensics.fingerprint import FP_BANDS, fingerprint
    from voiceid.audio import degrade

    F, db = fingerprint(A[: 5 * SR])
    G, _ = fingerprint(degrade(A[: 5 * SR], "phone"))
    assert F.shape[1] == FP_BANDS and len(F) == len(db)
    c = float((F * G).sum() / (np.linalg.norm(F) * np.linalg.norm(G)))
    assert c > 0.8, c


def test_excerpt_found_at_right_place():
    from forensics.compare import compare_with_original

    r = compare_with_original(A[12 * SR: 20 * SR], lib())
    assert r.status == "excerpt", r
    assert r.source == "speakerA_video1"
    assert abs(r.pieces[0].orig_start - 12.0) < 0.1
    assert not r.edits


def test_internal_cut_found():
    from forensics.compare import compare_with_original

    x = np.concatenate([A[5 * SR: 9 * SR], A[15 * SR: 19 * SR]])
    r = compare_with_original(x, lib())
    assert r.status == "edited", r
    cuts = [e for e in r.edits if e.kind == "cut"]
    assert cuts and abs(cuts[0].time - 4.0) < 0.25 and abs(cuts[0].removed_sec - 6.0) < 0.25, r.edits


def test_join_of_two_recordings_found():
    from forensics.compare import compare_with_original

    x = np.concatenate([A[30 * SR: 33 * SR], B[10 * SR: 14 * SR]])
    r = compare_with_original(x, lib())
    joins = [e for e in r.edits if e.kind == "joined"]
    assert joins and abs(joins[0].time - 3.0) < 0.25, r.edits


def test_unknown_audio_not_found():
    from forensics.compare import compare_with_original

    r = compare_with_original(fake_speech(6, 99), lib(), {"match": 0.72, "strong": 0.8})
    assert r.status == "not_found", r
    assert "not mean" in (r.note or "")


def test_no_library():
    from forensics.compare import compare_with_original

    assert compare_with_original(A[:SR * 3], None).status == "no_library"


def test_logreg_roundtrip():
    from forensics.lr import LogReg

    rng = np.random.default_rng(0)
    X = np.vstack([rng.normal(0, 1, (50, 3)), rng.normal(2, 1, (50, 3))])
    y = np.r_[np.zeros(50), np.ones(50)]
    m = LogReg().fit(X, y, ["a", "b", "c"])
    assert ((m.proba(X) >= 0.5) == y).mean() > 0.85
    with tempfile.TemporaryDirectory() as d:
        m.save(Path(d) / "m.json", {"x": 1})
        m2, extra = LogReg.load(Path(d) / "m.json")
        assert np.allclose(m.proba(X), m2.proba(X)) and extra["x"] == 1


def test_artifact_features_finite():
    from forensics.artifact import FEATURE_NAMES, artifact_score, clip_features

    v = clip_features(A[: 4 * SR])
    assert v.shape == (len(FEATURE_NAMES),) and np.isfinite(v).all()
    assert artifact_score(A[: SR], None) is None


def test_splice_candidates_run():
    from forensics.splice import FEATURE_NAMES, candidates, detect_splice_points

    idx, X = candidates(A[: 6 * SR])
    assert X.shape == (len(idx), len(FEATURE_NAMES)) and np.isfinite(X).all()
    assert detect_splice_points(A[: 6 * SR], None) == []


def test_verdict_rules():
    from forensics.verdict import Answer, _overall

    ok = Answer("match", "")
    assert _overall(Answer("mismatch", ""), ok, Answer("edited", ""), ok)[0] == "misattributed"
    assert _overall(ok, Answer("no_signs", ""), Answer("edited", ""), ok)[0] == "edited"
    assert _overall(ok, Answer("no_signs", ""), Answer("unknown", ""), Answer("unknown", ""))[0] == "unverified"
    assert _overall(ok, Answer("original_recording", ""), Answer("not_edited", ""), Answer("excerpt", ""))[0] \
        == "verified_excerpt"


def test_voice_answer_uses_original_owner():
    from forensics.compare import compare_with_original
    from forensics.verdict import _voice_answer

    r = compare_with_original(B[5 * SR: 12 * SR], lib())          # B belongs to "other"
    a = _voice_answer(None, "ibn_baz", r)
    assert a.status == "mismatch", a


def test_no_religious_ruling_words():
    import forensics.verdict as v

    text = Path(v.__file__).read_text(encoding="utf-8")
    for w in ("حلال", "حرام", "يجوز", "لا يجوز", "فتوى صحيحة"):
        assert w not in text, w


def test_content_levels_and_referral():
    """Scientific package p.2: Sada answers level A about the audio only; level D (fatwa / personal case) is referred;
    p.5 transparency: Sada says it is an AI tool."""
    from api.contract import build_result
    from forensics.verdict import Answer, Verdict

    v = Verdict("c.wav", "ibn_baz", "verified_excerpt", "", Answer("match", "", {"score": 0.5}),
                Answer("original_recording", "", {"artifact_score": 0.1}), Answer("not_edited", "", {"edits": [], "pieces": []}),
                Answer("excerpt", "", {"source": None}))
    d = v.to_dict()
    assert d["content_policy"]["clip_content"] == "not_evaluated"
    assert set(d["content_policy"]["levels_ar"]) == {"A", "B", "C", "D"}
    assert "الذكاء الاصطناعي" in d["disclaimer_ar"] and "فتوى" in d["disclaimer_ar"]
    r = build_result(v, speaker_id="ibn_baz", duration=8.0, identity_thresholds=None,
                     artifact_settings={"high": 0.5}, library_info="", processing_ms=1)
    assert r["content_policy"]["sada_output_level"] == "A"
    assert any("جهة مؤهلة" in x for x in r["limitations"])
    assert any("الذكاء الاصطناعي" in x for x in r["limitations"])
    assert any(s["type"] == "official_source" and s.get("url", "").startswith("https://") for s in r["sources"])


def test_sources_table_shows_the_original_page():
    """Mentor's note: every original recording has a documented source; the result links to it."""
    import tempfile

    import forensics.sources as S
    from api.contract import build_result
    from forensics.verdict import Answer, Verdict

    d = Path(tempfile.mkdtemp())
    f = d / "sources.csv"
    f.write_text("file,sheikh_id,entity,url,title,obtained,permission,notes\n"
                 "raw/ibn_baz.wav,ibn_baz,الموقع الرسمي,https://binbaz.org.sa/audios/1,درس,2026-10-05,,\n",
                 encoding="utf-8")
    t = S.load_sources(f)
    assert S.source_of("raw/ibn_baz.mp3", t)["url"].startswith("https://")      # other format, same recording
    old = S.SOURCES
    S.SOURCES = f
    try:
        pieces = [{"source": "raw/ibn_baz.mp3", "orig_start": 60.0, "orig_end": 68.0}]
        v = Verdict("c.wav", "ibn_baz", "verified_excerpt", "", Answer("match", "", {"score": 0.5}),
                    Answer("original_recording", "", {"artifact_score": 0.1}),
                    Answer("not_edited", "", {"edits": [], "pieces": pieces}),
                    Answer("excerpt", "", {"source": "raw/ibn_baz.mp3"}))
        r = build_result(v, speaker_id="ibn_baz", duration=8.0, identity_thresholds=None,
                         artifact_settings={"high": 0.5}, library_info="", processing_ms=1)
    finally:
        S.SOURCES = old
    src = [x for x in r["sources"] if x["title"].startswith("مصدر التسجيل الأصلي")]
    assert src and src[0]["url"] == "https://binbaz.org.sa/audios/1" and "2026-10-05" in src[0]["description"]


def test_api_contract_mapping():
    from api.contract import build_result
    from forensics.verdict import Answer, Verdict

    def V(voice, gen, edit, comp, overall="x", art=0.1):
        return Verdict("c.wav", "ibn_baz", overall, "", Answer(voice, "", {"score": 0.4}),
                       Answer(gen, "", {"artifact_score": art}), Answer(edit, "", {"edits": [], "pieces": []}),
                       Answer(comp, "", {"source": None}))
    kw = dict(speaker_id="ibn_baz", duration=8.0, identity_thresholds={"low": 0.28, "high": 0.37},
              artifact_settings={"high": 0.5}, library_info="", processing_ms=1)
    r = build_result(V("match", "original_recording", "not_edited", "excerpt"), **kw)
    assert r["status"] == "likely_authentic" and r["confidence"] == 0.9 and r["decision_threshold"] == 0.5
    assert r["splice_analysis"]["findings"] == []
    r = build_result(V("match", "original_recording", "not_edited", "excerpt", art=0.7), **kw)   # model unsure:
    assert r["status"] == "likely_authentic" and r["confidence"] is None                          # no number shown
    r = build_result(V("match", "unclear", "unknown", "unknown"), **kw)        # voice match alone is not enough
    assert r["status"] == "inconclusive" and "splice_analysis" not in r
    r = build_result(V("unclear", "suspicious", "unknown", "unknown", art=0.9), **kw)
    assert r["status"] == "likely_synthetic" and r["confidence"] == 0.9 and r["decision_threshold"] == 0.5
    assert "لا تنشر المقطع" in r["recommendation"]
    assert build_result(V("mismatch", "suspicious", "unknown", "unknown", "misattributed", art=0.999), **kw)["confidence"] == 0.99
    r = build_result(V("mismatch", "original_recording", "edited", "assembled"), **kw)
    assert r["status"] == "inconclusive" and r["voiceprint"]["flag"] == "unexpected_mismatch"
    for x in (r["voiceprint"].get("match"), r["acoustic_analysis"].get("score")):
        assert x is None or 0 <= x <= 1


def _cmp(status, sheikh, coverage=1.0):
    from forensics.compare import CompareResult, Piece

    pieces = [] if status in ("not_found", "no_library") else [Piece(0, 8, f"raw/{sheikh}.mp3", sheikh, 60, 68, 0.97)]
    return CompareResult(status, pieces[0].source if pieces else None, sheikh if pieces else None, pieces,
                         coverage=coverage if pieces else 0.0)


def test_conflict_original_beats_voiceprint():          # C1
    from forensics.verdict import Answer, resolve_conflicts

    v, c = resolve_conflicts(Answer("mismatch", "x", {"score": 0.2, "best_match": "al_fawzan"}),
                             Answer("original_recording", "", {"artifact_score": 0.1}), _cmp("excerpt", "ibn_baz"),
                             "ibn_baz")
    assert v.status == "match" and c and c[0]["code"] == "voice_vs_original"


def test_conflict_voice_clone_pattern():                # C4
    from forensics.verdict import Answer, resolve_conflicts, review_reason

    g = Answer("suspicious", "g", {"artifact_score": 0.9})
    v, c = resolve_conflicts(Answer("match", "v", {"score": 0.5, "best_match": "ibn_baz"}), g, _cmp("not_found", None),
                             "ibn_baz")
    assert [x["code"] for x in c] == ["voice_match_and_generated"] and "مستنسخة" in g.text_ar
    assert review_reason("likely_generated", v, c)


def test_no_conflict_no_review_when_verified():
    from forensics.verdict import Answer, resolve_conflicts, review_reason

    v, c = resolve_conflicts(Answer("match", "v", {"score": 0.5, "best_match": "ibn_baz"}),
                             Answer("original_recording", "", {"artifact_score": 0.02}), _cmp("excerpt", "ibn_baz"),
                             "ibn_baz")
    assert c == [] and review_reason("verified_excerpt", v, c) is None
    assert review_reason("unverified", v, []) is not None          # missing reference -> a person looks


def test_silence_is_reported_not_crashing():
    from forensics.compare import compare_with_original
    from forensics.verdict import _complete_answer

    r = compare_with_original(np.zeros(SR * 4, dtype=np.float32), lib())
    assert r.status == "no_speech" and "لا يوجد كلام" in _complete_answer(r).text_ar


def main() -> int:
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} role-5 tests passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
