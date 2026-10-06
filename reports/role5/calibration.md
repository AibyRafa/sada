# Role 5 — calibration of the original search (2026-10-05 23:51)

Window = 1 s of the clip searched in every original. Score = normalized correlation of fingerprints.
Negatives = windows whose true original is NOT in the library: generated speech, and real clips
searched with their own recording removed (same voice, other recordings still there).
Positives = windows of real clips with their original in the library.

Conditions: clean, phone, noisy. Clips used: {'ibn_baz (own recording removed)': 81, 'al_fawzan (own recording removed)': 33, 'al_alsheikh (own recording removed)': 27, 'generated': 45, 'other (own recording removed)': 15}

| | windows | median | 99.9% | max |
|---|---|---|---|---|
| negatives | 4297 | 0.451 | 0.690 | 0.698 |
| positives | 3608 | 0.991 | 0.550 (0.1%) | |

**match = 0.71** (a window counts as found; a clip needs 2 agreeing windows)  
**strong = 0.79** (one window alone is enough)  
Positive windows at or above match: 98%
