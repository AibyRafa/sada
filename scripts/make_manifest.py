import csv
from pathlib import Path

DATA = Path("data")
MANIFEST = DATA / "manifest.csv"
FIELDS = ["file", "label", "speaker", "source", "consent", "notes"]
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".flac"}
FOLDER_LABELS = {"ref": "ref", "real": "real", "fake": "fake", "spliced": "spliced", "cropped": "cropped"}


def load_existing():
    if not MANIFEST.exists():
        return {}
    with open(MANIFEST, newline="", encoding="utf-8-sig") as f:
        return {row["file"]: row for row in csv.DictReader(f)}


rows = load_existing()
added = 0

for path in sorted(DATA.rglob("*")):
    if path.suffix.lower() not in AUDIO_EXT:
        continue
    rel = path.relative_to(DATA).as_posix()
    if rel in rows:  # keep rows you've already filled in
        continue

    parts = rel.split("/")
    label = FOLDER_LABELS.get(parts[0], "unknown")
    if label == "ref" and len(parts) > 2:  # ref/speakerA/clip.wav
        speaker = parts[1]
    else:
        speaker = path.stem.split("_")[0]

    rows[rel] = {
        "file": rel,
        "label": label,
        "speaker": speaker,
        "source": "",
        "consent": "pending",
        "notes": "",
    }
    added += 1

with open(MANIFEST, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows.values())

print(f"Done. {added} new files added, {len(rows)} total.")