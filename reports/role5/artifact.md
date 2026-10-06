# Role 5 — artifact_score (generated speech): evaluation (2026-10-06 00:06)

Real speech: 259 clips (muftis + team member). Generated: 30 clips, 3 edge-tts voices (tts1, tts2, tts3).
Each clip in 3 conditions (clean, phone, noisy); features on speech frames only.

## 1. Leave one generated voice out (the voice is never seen in training)

| held-out voice | condition | AUC | generated flagged (p>=0.5) | real flagged (p>=0.5) |
|---|---|---|---|---|
| tts1 | clean | 1.00 | 100% | 0% |
| tts1 | phone | 1.00 | 100% | 2% |
| tts1 | noisy | 1.00 | 100% | 0% |
| tts2 | clean | 1.00 | 60% | 0% |
| tts2 | phone | 0.98 | 0% | 0% |
| tts2 | noisy | 1.00 | 40% | 0% |
| tts3 | clean | 1.00 | 100% | 2% |
| tts3 | phone | 1.00 | 100% | 2% |
| tts3 | noisy | 1.00 | 100% | 2% |

## 2. Final model: trained on the cal/enroll/ref clips, tested on the test split

Thresholds (from training data: 95% of real clips below `high`): low 0.30, high 0.50

| condition | AUC | generated -> suspicious (>= high) | real -> suspicious (>= high) | real -> no signs (<= low) |
|---|---|---|---|---|
| clean | 1.00 | 100% | 0% | 96% |
| phone | 1.00 | 100% | 2% | 98% |
| noisy | 1.00 | 100% | 0% | 98% |

Strongest features: mod_4hz (+1.63), flux_std (+1.45), flatness_std (+1.14), f0_jitter (+1.11), flux_mean (+0.89), mod_peakiness (-0.71)

## Limits (say these with any number)
- Only 3 generic edge-tts voices. This is NOT a test against voice clones of the muftis, and a good
  voice clone may pass. Real speech here comes from a few recordings only.
- The score is one signal among four; Sada never calls a clip fake from this score alone.
