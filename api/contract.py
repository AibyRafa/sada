"""Maps Sada's verdict (roles 4 + 5) to the JSON contract of the frontend (sada-ui README, POST /api/v1/verify).

Mapping rules (honest by design):
  status
    likely_authentic  the voice matches the attributed mufti AND (the clip was found in an original recording
                      OR the generated-speech check shows no signs). A voice match alone is never enough.
    likely_synthetic  the generated-speech score reaches its calibrated threshold AND the clip was NOT found
                      in any original recording.
    inconclusive      everything else (voice not confirmed, voice of another mufti, nothing to compare with...).
  confidence / decision_threshold
    from the calibrated generated-speech model, the only calibrated probability Sada has:
      likely_synthetic  confidence = its score (probability of generated speech), threshold = its "high" setting.
      likely_authentic  confidence = 1 - its score (probability of natural speech), threshold = 1 - "high";
                        given only when it is on the authentic side of the threshold. The voice match and the
                        original recording are required conditions for this status and are shown as evidence.
    Shown at most 99%. Otherwise null (inconclusive, or no score): the UI says no numeric confidence was given.
  voiceprint.match
    the real similarity from role 4 (cosine after removing the average voice, clipped to 0..1). The calibrated
    thresholds are written in `observations`, because this similarity scale is not a percentage of certainty.
  acoustic_analysis.score   = 1 - generated-speech score  (higher = more natural, as the contract says)
  splice_analysis.findings  = edits found against the original recording; [] = original found and no edit;
                              absent = original not found (unknown, the UI then claims nothing).
"""

from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path

from forensics.verdict import CONTENT_POLICY, REFERRAL, REFERRAL_AR

SHEIKHS_AR = {
    "ibn_baz": "الشيخ عبدالعزيز بن باز",
    "al_alsheikh": "الشيخ عبدالعزيز آل الشيخ",
    "al_fawzan": "الشيخ صالح الفوزان",
}
# Only links that role 1's manifest gives as the official source are used (no invented links).
OFFICIAL = {"ibn_baz": {"label": "الموقع الرسمي لسماحة الشيخ ابن باز", "url": "https://binbaz.org.sa"}}

LIMITATIONS = [
    "مكتبة التسجيلات الأصلية صغيرة (ما نزّله الفريق)؛ إذا لم يوجد الأصل فيها فلا يمكن الحكم على القص والاكتمال، "
    "وعدم وجود الأصل لا يعني أن المقطع مزيّف.",
    "فحص التوليد دُرِّب على ثلاثة أصوات توليد عامة فقط، ولم يُختبر على استنساخ أصوات المشايخ.",
    "البصمة الصوتية مبنية من عدد محدود من التسجيلات لكل شيخ.",
    "صدى أداة آلية مدعومة بالذكاء الاصطناعي، وليست مختصًا بشريًا؛ نتيجتها تساعد على التحقق ولا تُغني عن الرجوع للأصل.",
    REFERRAL_AR,
]


def _clip01(x):
    if x is None:
        return None
    return float(min(1.0, max(0.0, x)))


def _fmt(sec: float) -> str:
    sec = max(0.0, float(sec))
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def speakers_payload(voiceprint_dir: Path) -> list[dict]:
    import json

    out = []
    for sid, name in SHEIKHS_AR.items():
        refs = None
        f = voiceprint_dir / f"{sid}.json"
        if f.is_file():
            try:
                refs = int(json.loads(f.read_text(encoding="utf-8")).get("clips"))
            except Exception:  # noqa: BLE001
                refs = None
        item = {"id": sid, "name": name}
        if refs is not None:
            item["reference_count"] = refs
        if sid in OFFICIAL:
            item["official_source"] = OFFICIAL[sid]
        out.append(item)
    return out


def build_result(v, *, speaker_id: str, duration: float, identity_thresholds: dict | None,
                 artifact_settings: dict, library_info: str, processing_ms: int) -> dict:
    """v = forensics.verdict.Verdict."""
    voice, gen, edit, comp = v.voice, v.generated, v.edited, v.complete
    art = gen.details.get("artifact_score")
    found = comp.status in ("complete", "excerpt", "assembled")
    voice_ok = voice.status in ("match", "identified")

    status, confidence, threshold = "inconclusive", None, None
    if voice_ok and (found or gen.status == "no_signs"):
        status = "likely_authentic"
        high = artifact_settings.get("high")
        if art is not None and high is not None and 1.0 - art >= 1.0 - high:
            confidence = min(_clip01(1.0 - art), 0.99)
            threshold = _clip01(1.0 - high)
    elif gen.status == "suspicious" and not found and art is not None:
        status = "likely_synthetic"
        confidence = min(_clip01(art), 0.99)   # a small model is never "100% sure"; shown at most 99%
        threshold = _clip01(artifact_settings.get("high"))

    # ---- path A: voiceprint
    vp = {}
    score = voice.details.get("score")
    if score is not None:
        vp["match"] = _clip01(score)
    if voice.status == "mismatch":
        vp["flag"] = "unexpected_mismatch"
    refs = None
    try:
        from voiceid.voiceprints import VOICEPRINT_DIR
        import json

        f = VOICEPRINT_DIR / f"{speaker_id}.json"
        if f.is_file():
            refs = int(json.loads(f.read_text(encoding="utf-8")).get("clips"))
    except Exception:  # noqa: BLE001
        refs = None
    if refs is not None:
        vp["references_compared"] = refs

    # ---- path B: generated speech
    acoustic = {}
    if art is not None:
        acoustic["score"] = _clip01(1.0 - art)
        if gen.status == "suspicious":
            acoustic["anomalies"] = ["خصائص الصوت أقرب إلى الكلام المولَّد آليًا في النموذج المدرَّب."]

    # ---- splice / edits (against the original)
    splice = None
    edits = edit.details.get("edits") or []
    if found:
        findings = []
        for e in edits:
            kind = e.get("kind")
            t = float(e.get("time", 0.0))
            if kind == "cut":
                findings.append({"type": "cut", "time": t,
                                 "reason": f"حُذف {e.get('removed_sec') or 0:.1f} ثانية من الأصل عند هذا الموضع"})
            elif kind == "joined":
                findings.append({"type": "cut", "time": t, "reason": "وُصل هنا بمقطع من تسجيل آخر"})
            elif kind == "reordered":
                findings.append({"type": "unnatural_sequence", "time": t, "reason": "تغيّر ترتيب الكلام عن الأصل"})
            elif kind == "unmatched":
                findings.append({"type": "unnatural_sequence", "time": t, "reason": "كلام غير موجود في التسجيل الأصلي"})
        splice = {"findings": findings}
        notes = []
        if comp.status == "excerpt":
            notes.append(comp.text_ar)
        if notes:
            splice["anomalies"] = notes

    # ---- texts
    observations = [v.overall_ar, voice.text_ar, gen.text_ar, edit.text_ar, comp.text_ar]
    if identity_thresholds and score is not None:
        observations.append(
            f"قيمة التشابه في البصمة {score:.2f} (بعد طرح متوسط الأصوات). الحدود المعايرة: "
            f"مطابق من {identity_thresholds['high']:.2f} فأعلى، وغير مطابق تحت {identity_thresholds['low']:.2f}.")
    rec = {
        "misattributed": "المقطع منسوب لغير قائله: لا تنشره منسوبًا إلى الشيخ، وارجع إلى المصدر الرسمي.",
        "edited": "المقطع معدَّل عن أصله: ارجع إلى التسجيل الأصلي لسماع الكلام كاملًا في سياقه قبل الاستشهاد به.",
        "likely_generated": "لا تنشر المقطع ولا تعتمد عليه، وتحقق من المصدر الرسمي للشيخ.",
        "verified_excerpt": "الصوت أصلي والمقطع مقتطع من تسجيل أطول: ارجع إلى الأصل لسماع السياق كاملًا.",
        "verified_complete": "المقطع يطابق تسجيلًا أصليًا كاملًا.",
    }.get("likely_generated" if status == "likely_synthetic" else v.overall,
          "ارجع إلى المصدر الرسمي قبل اعتماد المقطع أو مشاركته.")

    sources = [{"type": "methodology", "title": "منهجية صدى",
                "description": "بصمة صوتية (Resemblyzer) + مقارنة بالتسجيل الأصلي ببصمة طيفية + فحص خصائص الكلام المولَّد."}]
    src = comp.details.get("source")
    if found and src:
        pieces = edit.details.get("pieces") or []
        where = "، ".join(f"{Path(p['source']).name} ({_fmt(p['orig_start'])}–{_fmt(p['orig_end'])})" for p in pieces)
        sources.append({"type": "traceability", "title": "موضع المقطع في التسجيل الأصلي",
                        "description": where or Path(src).name})
        # where each original comes from (data/sources.csv): publishing body, exact page, date obtained
        try:
            from forensics.sources import load_sources, source_of

            table = load_sources()
        except Exception:  # noqa: BLE001
            table = {}
        seen = []
        for name in [p["source"] for p in pieces] or [src]:
            if name in seen:
                continue
            seen.append(name)
            row = source_of(name, table) if table else None
            if not row or not (row["entity"] or row["url"]):
                continue
            parts = [row["entity"]]
            if row["title"]:
                parts.append(f"«{row['title']}»")
            if row["obtained"]:
                parts.append(f"حُمّل بتاريخ {row['obtained']}")
            item = {"type": "traceability", "title": f"مصدر التسجيل الأصلي: {Path(name).name}",
                    "description": "، ".join(x for x in parts if x)}
            if row["url"].startswith("https://"):
                item["url"] = row["url"]
            sources.append(item)
    if speaker_id in OFFICIAL:
        sources.append({"type": "official_source", "title": OFFICIAL[speaker_id]["label"],
                        "description": "المصدر الرسمي للتسجيلات الأصلية: ارجع إليه لسماع الكلام كاملًا في سياقه.",
                        "url": OFFICIAL[speaker_id]["url"]})
    sources.append({"type": "official_source", "title": f"جهة الإحالة: {REFERRAL['label']}",
                    "description": "للفتوى والحالات الشخصية (المستوى د في الحزمة العلمية): صدى لا يقيّم مضمون المقطع.",
                    "url": REFERRAL["url"]})
    if refs is not None:
        sources.append({"type": "reference_recording", "title": f"بصمة {SHEIKHS_AR.get(speaker_id, speaker_id)}",
                        "description": "مبنية من مقاطع مرجعية من تسجيلات الشيخ."})

    out = {
        "status": status,
        "confidence": confidence,
        "decision_threshold": threshold,
        "speaker": {"id": speaker_id, "name": SHEIKHS_AR.get(speaker_id, speaker_id)},
        "voiceprint": vp,
        "acoustic_analysis": acoustic,
        "flagged_segments": [],
        "spectrogram": None,
        "recommendation": rec,
        "observations": [o for o in observations if o],
        "limitations": LIMITATIONS,
        "sources": sources,
        "duration": round(float(duration), 2),
        "verdict": v.to_dict(),      # full Sada answer (4 questions), for other clients
        "content_policy": CONTENT_POLICY,   # the four content levels: Sada answers level A about the audio only
        "meta": {
            "analysis_id": uuid.uuid4().hex[:12],
            "analyzed_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "models": {"speaker_encoder": "Resemblyzer (GE2E) — بصمات صدى المعايرة",
                       "artifact_classifier": "انحدار لوجستي على خصائص الكلام (مدرَّب على edge-tts)",
                       "splice_detector": "مقارنة بالتسجيل الأصلي (بصمة طيفية + Viterbi)"},
            "reference_set": library_info,
            "processing_ms": processing_ms,
        },
    }
    if splice is not None:
        out["splice_analysis"] = splice
    if speaker_id in OFFICIAL:
        out["official_source"] = OFFICIAL[speaker_id]
    return out
