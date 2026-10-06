import asyncio
import subprocess
from pathlib import Path

import edge_tts

VOICES = {
    "tts1": "ar-SA-HamedNeural",
    "tts2": "ar-SA-ZariyahNeural",
    "tts3": "ar-EG-ShakirNeural",
}

SENTENCES = [
    "اليوم الطقس جميل في مدينة ينبع والسماء صافية.",
    "بدأت الدراسة في الجامعة هذا الأسبوع.",
    "يعمل فريقنا على مشروع للكشف عن التلاعب في التسجيلات الصوتية.",
    "المكتبة تفتح أبوابها من الثامنة صباحاً حتى الرابعة عصراً.",
    "تعتمد تقنيات الذكاء الاصطناعي على كميات كبيرة من البيانات.",
    "سنلتقي غداً في قاعة المحاضرات لمناقشة خطة العمل.",
    "الرحلة من جدة إلى ينبع تستغرق حوالي ساعتين بالسيارة.",
    "من المفيد قراءة الكتب العلمية وتجربة البرامج الجديدة.",
    "يرجى تسليم التقرير قبل نهاية الأسبوع.",
    "تم تحديث الجدول الدراسي ويمكنكم الاطلاع عليه في الموقع.",
]

OUT = Path("data/fake")
TMP = Path("raw/tts_tmp")
OUT.mkdir(parents=True, exist_ok=True)
TMP.mkdir(parents=True, exist_ok=True)


async def main():
    for code, voice in VOICES.items():
        for i, text in enumerate(SENTENCES, 1):
            wav = OUT / f"{code}_fake_{i:02d}.wav"
            if wav.exists():
                continue
            mp3 = TMP / f"{code}_{i:02d}.mp3"
            await edge_tts.Communicate(text, voice).save(str(mp3))
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3),
                 "-ac", "1", "-ar", "16000", str(wav)],
                check=True,
            )
            print("saved", wav)


asyncio.run(main())