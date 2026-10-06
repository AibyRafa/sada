# Role 5 — compare_with_original: evaluation (2026-10-06 00:06)

Library: 33 originals, 135.9 min. Thresholds: match 0.71, strong 0.79 (calibrated: True).
Clips: role 4's **test** split only (never used for calibration). Tolerance for times: ±0.25 s.
Cells: rate (number of clips).

| | clean | phone | noisy |
|---|---|---|---|
| **A. Clip from an original in the library** | | | |
| mufti clip found | 100% (47) | 100% (47) | 100% (47) |
| ... found in a recording of the right mufti | 100% (47) | 100% (47) | 100% (47) |
| team-member clip found | 100% (5) | 100% (5) | 100% (5) |
| ... found in its own recording | 100% (5) | 100% (5) | 100% (5) |
| same place as the clean copy (phone / noisy) | n/a (0) | 100% (47) | 100% (47) |
| wrongly reported as edited | 0% (52) | 0% (52) | 0% (52) |
| **B. Two recordings joined (role 1's spliced clips)** | | | |
| join found at the right time - hard cut | 100% (10) | 100% (10) | 70% (10) |
| join found at the right time - 30 ms fade | 100% (10) | 100% (10) | 100% (10) |
| join found at the right time - fade + noise | 100% (10) | 100% (10) | 100% (10) |
| join found at the right time - all | 100% (30) | 100% (30) | 90% (30) |
| both source recordings named | 100% (30) | 100% (30) | 90% (30) |
| mean time error of found joins | 21 ms | 24 ms | 40 ms |
| **C. Cut before the end (role 1's cropped clips)** | | | |
| found | 100% (15) | 100% (15) | 100% (15) |
| reported as excerpt ending at the right place | 100% (15) | 100% (15) | 100% (15) |
| reported 'speaker was still talking' | 100% (15) | 100% (15) | 100% (15) |
| wrongly reported as edited | 0% (15) | 0% (15) | 0% (15) |
| **D. Words removed inside a mufti recording (40 clips made in memory)** | | | |
| cut found at the right time | 95% (40) | 90% (40) | 68% (40) |
| ... removed length right (±0.25 s) | 100% (38) | 100% (36) | 100% (27) |
| **E. Original NOT in the library** (should NOT be found) | | | |
| real clip, its own recording removed -> wrongly found | 0% (52) | 0% (52) | 0% (52) |
| generated speech -> wrongly found | 0% (15) | 0% (15) | 0% (15) |

## Limits
- The spliced / cropped clips are role 1's own recordings (team member's voice), joined from her own
  recordings. The muftis' cuts (D) are made in memory from role 1's downloaded lectures and never saved.
- Phone = 8 kHz band-limited copy; noisy = white noise at 15 dB SNR. Real re-shared clips (WhatsApp
  re-encoding, music, speed change) can be harder.
- 'Not found' only means the original is not in the library; it never means the clip is fake.
  The library only covers what role 1 downloaded.
