import sys
from pathlib import Path

import librosa
import soundfile as sf

SR = 16000
CLIP_SEC = 8
MIN_SEC = 3

if len(sys.argv) != 6:
    print("Usage: python scripts/split_audio.py <file> <speaker> <ref|real> <start_sec> <end_sec>")
    sys.exit(1)

path, speaker, label = sys.argv[1], sys.argv[2], sys.argv[3]
start, end = float(sys.argv[4]), float(sys.argv[5])

wav, _ = librosa.load(path, sr=SR, mono=True, offset=start, duration=end - start)

if label == "ref":
    out_dir = Path("data/ref") / speaker
else:
    out_dir = Path("data") / label
out_dir.mkdir(parents=True, exist_ok=True)

n_existing = len(list(out_dir.glob(f"{speaker}_{label}_*.wav")))
size = CLIP_SEC * SR
count = 0

for i in range(0, len(wav), size):
    clip = wav[i:i + size]
    if len(clip) < MIN_SEC * SR:
        continue
    count += 1
    name = f"{speaker}_{label}_{n_existing + count:02d}.wav"
    sf.write(out_dir / name, clip, SR)

print(f"Saved {count} clips to {out_dir}")