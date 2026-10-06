"""Sada — Role 4: voice identity (whose voice is it?).

Built on role 1's data (data/manifest.csv):
  data/ref/<speaker>/*.wav   reference library  -> voiceprints
  data/real/*.wav            real clips          -> calibration / test
  data/fake/*.wav            generated speech    -> "other voice" tests
"""

from pathlib import Path

SR = 16000
ROOT = Path(__file__).resolve().parent.parent      # project root (the folder with data/, src/, scripts/)
SHEIKHS = {
    "ibn_baz": "Sheikh Abdulaziz bin Baz",
    "al_alsheikh": "Sheikh Abdulaziz Al ash-Sheikh",
    "al_fawzan": "Sheikh Saleh Al-Fawzan",
}
OTHER = "other"  # any voice that is NOT one of the muftis
