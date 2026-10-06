import csv
import random
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 16000
random.seed(7)
np.random.seed(7)

SRC = sorted(Path("data/real").glob("speakerX_real_*.wav"))
SPL = Path("data/spliced")
CRP = Path("data/cropped")
SPL.mkdir(parents=True, exist_ok=True)
CRP.mkdir(parents=True, exist_ok=True)

if len(SRC) < 2:
    raise SystemExit("Need at least 2 files named speakerX_real_*.wav in data/real")


def read(path):
    wav, sr = sf.read(path, dtype="float32")
    assert sr == SR, f"{path} is not 16 kHz"
    return wav


def join(a, b, ms):
    n = int(SR * ms / 1000)
    if n == 0:
        return np.concatenate([a, b]), len(a) / SR
    fade = np.linspace(0, 1, n, dtype="float32")
    mix = a[-n:] * (1 - fade) + b[:n] * fade
    clip = np.concatenate([a[:-n], mix, b[n:]])
    return clip, (len(a) - n / 2) / SR


rows = []
count = 0

# Spliced clips: 10 per level
for level, ms, noisy in [("hard", 0, False), ("fade", 30, False), ("noisy", 30, True)]:
    for _ in range(10):
        pa, pb = random.sample(SRC, 2)
        a, b = read(pa), read(pb)
        a_part = a[: int(len(a) * random.uniform(0.35, 0.65))]
        b_part = b[int(len(b) * random.uniform(0.35, 0.65)):]
        clip, t = join(a_part, b_part, ms)
        if noisy:
            clip = np.clip(clip + np.random.randn(len(clip)).astype("float32") * 0.003, -1, 1)
        count += 1
        name = f"speakerX_spliced_{count:02d}.wav"
        sf.write(SPL / name, clip, SR)
        rows.append([f"spliced/{name}", level, pa.name, pb.name, round(t, 3)])

# Cropped clips: 15, cut off before the sentence ends
for i in range(1, 16):
    p = random.choice(SRC)
    w = read(p)
    cut = int(len(w) * random.uniform(0.4, 0.75))
    clip = w[:cut].copy()
    kind = "cut_end"
    if i % 2 == 0:
        n = int(SR * 0.05)
        clip[-n:] *= np.linspace(1, 0, n, dtype="float32")
        kind = "cut_end_fade"
    name = f"speakerX_cropped_{i:02d}.wav"
    sf.write(CRP / name, clip, SR)
    rows.append([f"cropped/{name}", kind, p.name, "", round(cut / SR, 3)])

with open("data/manipulation_log.csv", "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow(["file", "type", "source_a", "source_b", "time_sec"])
    writer.writerows(rows)

print(f"Done. {count} spliced and {len(rows) - count} cropped clips.")