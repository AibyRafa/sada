"""analyze(): Sada's four questions for one clip, from role 4 (identity) + role 5 (forensics).

  1. whose voice?     role 4 identity_score (voiceprints)            -> voice
  2. generated?       artifact_score  (+ "found in an original")     -> generated
  3. edited?          compare_with_original edits (+ blind splice)   -> edited
  4. complete?        compare_with_original: excerpt / missing parts -> complete

Rules that never change:
  - a voice match alone never makes a clip "authentic";
  - "original not found" never means "fake" (only that we cannot check it);
  - Sada never gives a religious ruling: it only describes the audio.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import yaml

FORENSICS_DIR = Path(__file__).resolve().parent
SETTINGS = FORENSICS_DIR / "settings.yaml"
MODELS = FORENSICS_DIR / "models"
DISCLAIMER_AR = ("صدى أداة آلية مدعومة بالذكاء الاصطناعي، وليست مختصًا بشريًا. تتحقق من الصوت فقط "
                 "(صاحبه، وسلامته من التوليد والتعديل، واكتماله)، ولا تقيّم مضمون الكلام، "
                 "ولا تصدر أي حكم شرعي أو فتوى، ولا تحكم على الأشخاص.")

# The four content levels of the challenge's scientific package (المرجعية والحزمة العلمية، ص 2) and where
# Sada stands. Sada only states level-A facts about the AUDIO, each traceable to its source (the position in
# an original recording, or the calibrated model that produced it). The clip's religious content is never
# evaluated; a clip that is a fatwa about a specific case (level D) is referred to a qualified body.
REFERRAL = {"label": "الرئاسة العامة للبحوث العلمية والإفتاء", "url": "https://alifta.gov.sa/ar/home"}
REFERRAL_AR = ("إذا كان المقطع فتوى أو جوابًا عن حالة شخص بعينه، فصدى لا يقيّم مضمونه ولا يطبّقه على حالتك: "
               f"ارجع إلى جهة مؤهلة مثل {REFERRAL['label']}.")
CONTENT_POLICY = {
    "sada_output_level": "A",
    "sada_output_ar": "معلومات تقنية عن الصوت فقط، كل معلومة موثقة بمصدرها (موضعها في التسجيل الأصلي أو النموذج المعاير).",
    "clip_content": "not_evaluated",
    "levels_ar": {
        "A": "معلومات أصلية مستقرة: صدى يجيب عن الصوت فقط إجابة موثقة بموضعها في التسجيل الأصلي.",
        "B": "شرح وتعريف واستدلال: إذا كان المقطع مقتطعًا يبيّن صدى موضعه في الأصل وما نقص منه، ويحيل للأصل "
             "لسماع الكلام في سياقه بدل الاعتماد على المقطع وحده.",
        "C": "مسائل خلافية أو عالية الحساسية: صدى لا يرجّح ولا يشرح المسألة؛ يبيّن فقط هل الكلام ثابت النسبة إلى قائله.",
        "D": "فتوى أو حالة شخصية: لا يقدّم صدى حكمًا ولا يطبّق الفتوى على حالة المستخدم، ويحيل إلى جهة مؤهلة.",
    },
    "referral_ar": REFERRAL_AR,
    "referral": REFERRAL,
}

SHEIKH_AR = {"ibn_baz": "الشيخ عبدالعزيز بن باز", "al_alsheikh": "الشيخ عبدالعزيز آل الشيخ",
             "al_fawzan": "الشيخ صالح الفوزان", "other": "متحدث آخر", "unknown": "غير محدد"}


def load_settings() -> dict:
    base = {"compare": {"match": 0.55, "strong": 0.7, "calibrated": False},
            "artifact": {"low": 0.3, "high": 0.7, "calibrated": False},
            "splice": {"threshold": 0.9, "usable": False}}
    if SETTINGS.is_file():
        data = yaml.safe_load(SETTINGS.read_text(encoding="utf-8")) or {}
        for k, v in data.items():
            base.setdefault(k, {}).update(v or {})
    return base


def save_settings(data: dict) -> None:
    head = "# Role 5 settings. Written by scripts/forensics.py (calibrate / train). Do not edit by hand.\n"
    SETTINGS.write_text(head + yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


@dataclass
class Answer:
    status: str          # short code (see each question)
    text_ar: str         # one Arabic sentence for the app
    details: dict = field(default_factory=dict)


@dataclass
class Verdict:
    file: str
    claimed_sheikh: str
    overall: str                  # verified_excerpt | verified_complete | edited | misattributed | likely_generated | unverified
    overall_ar: str
    voice: Answer
    generated: Answer
    edited: Answer
    complete: Answer
    conflicts: list = field(default_factory=list)      # [{"code", "text_ar", "resolution"}]
    needs_human_review: bool = False
    review_reason_ar: str | None = None
    disclaimer_ar: str = DISCLAIMER_AR
    content_policy: dict = field(default_factory=lambda: dict(CONTENT_POLICY))

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=1, default=float)


class Analyzer:
    """Loads everything once (voice encoder, voiceprints, library, models); analyze() per clip."""

    def __init__(self, with_identity: bool = True, log=print):
        from forensics.library import Library
        from forensics.lr import LogReg

        self.settings = load_settings()
        self.library = Library.build(log=log)
        self.artifact_model = LogReg.load(MODELS / "artifact.json")[0] if (MODELS / "artifact.json").is_file() else None
        sp = self.settings["splice"]
        self.splice_model = (LogReg.load(MODELS / "splice.json")[0]
                             if sp.get("usable") and (MODELS / "splice.json").is_file() else None)
        self.identity = None
        if with_identity:
            try:
                from voiceid import thresholds as th
                from voiceid.encoder import ResemblyzerEncoder
                from voiceid.scoring import load_background
                from voiceid.voiceprints import VOICEPRINT_DIR, load_voiceprints

                t = th.load()
                self.identity = {
                    "encoder": ResemblyzerEncoder(), "thresholds": t, "voiceprints": load_voiceprints(VOICEPRINT_DIR),
                    "background": load_background(VOICEPRINT_DIR) if t["identity"].get("scoring") == "centered" else None}
            except Exception as e:  # noqa: BLE001
                log(f"  (role 4 identity not available: {e})")

    # ------------------------------------------------------------------
    def analyze_file(self, path: str | Path, sheikh_id: str = "unknown") -> Verdict:
        from voiceid.audio import load_audio

        return self.analyze(load_audio(path), sheikh_id, Path(path).name)

    def analyze(self, audio: np.ndarray, sheikh_id: str = "unknown", name: str = "clip") -> Verdict:
        from forensics.artifact import artifact_score
        from forensics.compare import compare_with_original
        from forensics.splice import detect_splice_points

        s = self.settings
        # 1. identity (role 4)
        ident = None
        if self.identity is not None:
            from voiceid import SHEIKHS
            from voiceid.identity import UNKNOWN, identity_score

            i = self.identity
            ident = identity_score(audio, sheikh_id if sheikh_id in SHEIKHS else UNKNOWN, i["encoder"],
                                   i["voiceprints"], i["thresholds"], i["background"])
        # 4/3. original
        cmp = compare_with_original(audio, self.library, s["compare"])
        # 2. generated
        art = artifact_score(audio, self.artifact_model)
        # 3b. blind splice (only when no original was found and the model passed its test)
        blind = []
        if cmp.status in ("not_found", "no_library") and self.splice_model is not None:
            changes = ident.speaker_changes if ident is not None else None
            blind = detect_splice_points(audio, self.splice_model, s["splice"]["threshold"], changes)

        voice = _voice_answer(ident, sheikh_id, cmp)
        generated = _generated_answer(art, cmp, s["artifact"])
        edited = _edited_answer(cmp, blind, self.splice_model is not None)
        complete = _complete_answer(cmp)
        voice, conflicts = resolve_conflicts(voice, generated, cmp, sheikh_id)
        overall, overall_ar = _overall(voice, generated, edited, complete)
        review = review_reason(overall, voice, conflicts)
        if review:
            overall_ar += " يحتاج مراجعة بشرية قبل الاعتماد."
        return Verdict(name, sheikh_id, overall, overall_ar, voice, generated, edited, complete,
                       conflicts, bool(review), review)


# ---------------------------------------------------------------------- conflicts between the signals
def resolve_conflicts(voice: "Answer", gen: "Answer", cmp, claimed: str) -> tuple["Answer", list]:
    """When two signals disagree, say so, and resolve with the more DIRECT evidence:
    an exact match inside an original recording (whose owner is known) outranks a statistical model.

    C1 voice not confirmed, but the whole clip sits unedited in an original of the CLAIMED mufti
       -> the original wins (voice models weaken on poor audio); conflict reported, human review.
    C2 the voice resembles the claimed mufti, but the original belongs to SOMEONE ELSE
       -> misattributed stands (a look-alike or cloned voice); conflict reported, human review.
    C3 generated-speech signs, but the clip sits in an original recording -> the original wins.
    C4 voice matches AND generated-speech signs AND no original -> the pattern of a voice clone; flagged.
    The conflict sentence is added to the answer it concerns, so every client shows it.
    """
    from voiceid import SHEIKHS

    conflicts = []
    found = bool(cmp.pieces) and cmp.coverage >= 0.8
    srcs = {p.sheikh_id for p in cmp.pieces if p.sheikh_id not in ("unknown", "")}

    def add(code, resolution, text, answer):
        conflicts.append({"code": code, "resolution": resolution, "text_ar": text})
        answer.text_ar = f"{answer.text_ar} {text}".strip()

    if (claimed in SHEIKHS and found and srcs == {claimed} and cmp.status in ("complete", "excerpt")
            and voice.status in ("mismatch", "unclear")):                                   # C1
        old = voice.status
        voice = Answer("match", f"المقطع موجود حرفيًا في تسجيل أصلي {_li(SHEIKH_AR[claimed])}.",
                       {**voice.details, "voiceprint_status": old})
        add("voice_vs_original", "original",
            "تعارض: البصمة وحدها لم تؤكد الصوت، واعتمدنا الأصل لأنه دليل مباشر (تضعف البصمة مع رداءة التسجيل).",
            voice)
    elif (claimed in SHEIKHS and "original_speakers" in voice.details
          and voice.details.get("best_match") == claimed):                                  # C2
        add("voice_like_but_other_original", "original",
            "تعارض: الصوت يشبه بصمة الشيخ، لكن الأصل لمتحدث آخر؛ قد يكون صوتًا مشابهًا أو مستنسخًا، واعتمدنا الأصل.",
            voice)
    p = gen.details.get("artifact_score")
    if p is not None and gen.status == "original_recording" and p >= load_settings()["artifact"]["high"]:   # C3
        add("generated_vs_original", "original",
            "تعارض: فحص التوليد أعطى درجة مرتفعة، لكن المقطع موجود في تسجيل أصلي، فاعتمدنا الأصل.", gen)
    if gen.status == "suspicious" and not cmp.pieces and voice.status in ("match", "identified"):   # C4
        add("voice_match_and_generated", "flag",
            "تنبيه: الصوت يطابق البصمة وفيه علامات توليد معًا، وهذا نمط يظهر في الأصوات المستنسخة.", gen)
    return voice, conflicts


def review_reason(overall: str, voice: "Answer", conflicts: list) -> str | None:
    """When a person must look before the result is used."""
    if conflicts:
        return "تعارض بين المؤشرات: " + " ".join(c["text_ar"] for c in conflicts)
    if overall in ("unverified", "found_original"):
        return "لم تكتمل الأدلة (الأصل غير موجود أو الصوت لم يتأكد)."
    if voice.status == "unclear":
        return "التشابه الصوتي في المنطقة الرمادية."
    return None


# ---------------------------------------------------------------------- the four answers
def _voice_answer(ident, claimed: str, cmp) -> Answer:
    from voiceid import SHEIKHS

    d = {}
    if ident is not None:
        d = {"score": ident.score, "best_match": ident.best_match, "per_sheikh": ident.per_sheikh,
             "speaker_changes": ident.speaker_changes}
    # the original recording itself says whose words these are
    srcs = {p.sheikh_id for p in cmp.pieces if p.sheikh_id not in ("unknown", "")}
    if claimed in SHEIKHS and srcs and srcs != {claimed}:
        d["original_speakers"] = sorted(srcs)
        who = "، ".join(SHEIKH_AR.get(x, x) for x in sorted(srcs - {claimed}))
        return Answer("mismatch", f"المقطع موجود في تسجيل أصلي {_li(who)}، وليس كله {_li(SHEIKH_AR[claimed])}.", d)
    if ident is None:
        return Answer("unavailable", "لم يتم فحص الصوت (بصمات الدور 4 غير متوفرة).", d)

    if claimed not in SHEIKHS:      # nobody named: say whose voice it is closest to
        best = ident.best_match
        if ident.status == "match" and best:
            return Answer("identified", f"الصوت يطابق بصمة {SHEIKH_AR.get(best, best)}. "
                                        "(مطابقة الصوت وحدها لا تثبت أن المقطع سليم.)", d)
        return Answer("unidentified", "الصوت لا يطابق بوضوح أيًّا من المفتين في المكتبة.", d)
    name = SHEIKH_AR.get(claimed, claimed)
    if ident.status == "match":
        return Answer("match", f"الصوت يطابق بصمة {name}. (مطابقة الصوت وحدها لا تثبت أن المقطع سليم.)", d)
    if ident.status == "mismatch":
        best = ident.best_match
        extra = f"، وأقرب بصمة له: {SHEIKH_AR.get(best, best)}." if best and best != claimed else "."
        return Answer("mismatch", f"الصوت لا يطابق بصمة {name}{extra}", d)
    return Answer("unclear", f"لا يمكن الجزم: التشابه مع بصمة {name} في المنطقة الرمادية.", d)


def _generated_answer(p, cmp, st) -> Answer:
    d = {"artifact_score": None if p is None else round(p, 3)}
    if cmp.pieces and cmp.coverage >= 0.8:
        return Answer("original_recording", "المقطع مأخوذ من تسجيل أصلي موجود في المكتبة، فهو ليس صوتًا مولّدًا.", d)
    if p is None:
        return Answer("unavailable", "فحص التوليد غير متوفر (لم يُدرَّب النموذج بعد).", d)
    if p >= st["high"]:
        return Answer("suspicious", "في الصوت علامات تشبه الكلام المولَّد آليًا. يحتاج تحققًا إضافيًا.", d)
    if p <= st["low"]:
        return Answer("no_signs", "لم تظهر علامات واضحة لكلام مولَّد. (هذا لا يستبعد الاستنساخ المتقن.)", d)
    return Answer("unclear", "نتيجة فحص التوليد غير حاسمة.", d)


def _li(name: str) -> str:
    """Arabic preposition li- joined to a name: الشيخ -> للشيخ, متحدث -> لمتحدث."""
    return "ل" + name[1:] if name.startswith("ال") else "ل" + name


def _fmt(sec: float) -> str:
    sec = max(0.0, float(sec))
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def _edited_answer(cmp, blind, blind_on: bool) -> Answer:
    d = {"edits": [e.to_dict() for e in cmp.edits], "pieces": [p.to_dict() for p in cmp.pieces]}
    if cmp.status == "edited":
        parts = []
        for e in cmp.edits:
            if e.kind == "cut":
                parts.append(f"عند الثانية {e.time:.1f} حُذف {e.removed_sec:.1f} ثانية من الأصل")
            elif e.kind == "joined":
                parts.append(f"عند الثانية {e.time:.1f} وُصل بمقطع من تسجيل آخر")
            elif e.kind == "reordered":
                parts.append(f"عند الثانية {e.time:.1f} تغيّر ترتيب الكلام عن الأصل")
            elif e.kind == "unmatched":
                parts.append(f"عند الثانية {e.time:.1f} كلام غير موجود في الأصل")
        return Answer("edited", "المقطع معدَّل: " + "، و".join(parts) + ".", d)
    if cmp.pieces:
        return Answer("not_edited", "المقطع متصل كما في التسجيل الأصلي، دون قصّ أو وصل من الداخل.", d)
    if blind:
        d["blind_points"] = [b.to_dict() for b in blind]
        times = "، ".join(f"{b.time:.1f}" for b in blind)
        return Answer("suspicious", f"لم نجد الأصل، وفيه نقاط يُشتبه أنها وصل عند الثانية: {times}.", d)
    if blind_on:
        return Answer("unknown", "لم نجد الأصل، ولم تظهر علامات قصّ واضحة. لا يمكن الجزم دون الأصل.", d)
    return Answer("unknown", "لا يمكن التحقق من التعديل لأن التسجيل الأصلي غير موجود في المكتبة.", d)


def _complete_answer(cmp) -> Answer:
    d = {k: getattr(cmp, k) for k in ("status", "source", "sheikh_id", "coverage", "original_duration", "missing_before",
                                      "missing_after", "cut_mid_speech_start", "cut_mid_speech_end", "best_score")}
    if cmp.status == "no_speech":
        return Answer("unknown", "لا يوجد كلام واضح في المقطع يمكن مقارنته بالأصل.", d)
    if cmp.status == "no_library":
        return Answer("unknown", "مكتبة التسجيلات الأصلية فارغة، فلا يمكن معرفة إن كان المقطع كاملًا.", d)
    if not cmp.pieces:
        return Answer("unknown", "التسجيل الأصلي غير موجود في المكتبة، فلا يمكن معرفة إن كان المقطع كاملًا. "
                                 "(عدم وجود الأصل لا يعني أن المقطع مزيّف.)", d)
    first = cmp.pieces[0]
    src = Path(cmp.source or "").name
    if cmp.status == "edited":
        parts = "، ".join(f"{Path(p.source).name} ({_fmt(p.orig_start)}–{_fmt(p.orig_end)})" for p in cmp.pieces)
        return Answer("assembled", f"المقطع مركّب من {len(cmp.pieces)} أجزاء من الأصل: {parts}. "
                                   "ارجع للأصل لسماع الكلام في سياقه.", d)
    if cmp.status == "complete":
        return Answer("complete", f"المقطع يطابق التسجيل الأصلي كاملًا ({src}).", d)
    msg = f"المقطع جزء من تسجيل أصلي أطول ({src}، مدته {_fmt(cmp.original_duration or 0)}): يبدأ عند {_fmt(first.orig_start)}"
    if (cmp.missing_after or 0) > 0.5:
        msg += f"، وبعده {_fmt(cmp.missing_after)} من الأصل غير موجودة في المقطع"
    msg += "."
    if cmp.cut_mid_speech_end:
        msg += " قُطع المقطع والمتحدث ما زال يتكلم، فقد يكون الكلام ناقصًا: ارجع للأصل لسماع السياق كاملًا."
    elif cmp.cut_mid_speech_start:
        msg += " بدأ المقطع في وسط الكلام: ارجع للأصل لسماع ما قبله."
    return Answer("excerpt", msg, d)


def _overall(voice: Answer, gen: Answer, edit: Answer, comp: Answer) -> tuple[str, str]:
    if voice.status == "mismatch":
        return "misattributed", "منسوب لغير قائله: الصوت أو الأصل لا يعود للشيخ المذكور."
    if edit.status == "edited":
        return "edited", "مقطع معدَّل عن أصله."
    if gen.status == "suspicious":
        return "likely_generated", "يُشتبه أن الصوت مولَّد آليًا."
    if comp.status == "complete" and voice.status in ("match", "identified"):
        return "verified_complete", "مطابق للتسجيل الأصلي كاملًا."
    if comp.status == "excerpt" and voice.status in ("match", "identified"):
        return "verified_excerpt", "مقتطع من تسجيل أصلي دون تعديل داخلي. ارجع للأصل للسياق الكامل."
    if comp.status in ("complete", "excerpt"):
        return "found_original", "موجود في تسجيل أصلي، لكن فحص الصوت لم يؤكد صاحبه."
    return "unverified", "لا يمكن التحقق الكامل: الأصل غير موجود في المكتبة."
