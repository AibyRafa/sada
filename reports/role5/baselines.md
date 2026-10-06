# Sada — AI vs simpler alternatives (2026-10-06 00:23)

Why each AI part is used, measured on the same held-out clips as the other reports.

## 1. Voice identity: deep speaker embedding vs classic MFCC

Enrollment = ref + enroll clips (155), as role 4. Test = held-out test split (47 mufti clips). Metric: the closest voiceprint is the right mufti.

| method | clean | phone | noisy |
|---|---|---|---|
| classic MFCC averages (no deep model) | 96% | 23% | 32% |
| **Sada: Resemblyzer voiceprints (role 4)** | 96% | 91% | 100% |

## 2. Generated speech: 14-feature model vs the best single feature

The single-feature baseline picks its feature on the training data only, like the model.

| test | single best feature | **Sada: logistic regression** |
|---|---|---|
| test split, clean | 0.95 (f0_jitter) | **1.00** |
| test split, phone | 0.88 (f0_jitter) | **1.00** |
| test split, noisy | 0.97 (f0_jitter) | **1.00** |
| voice never seen: tts1 (AUC; flagged at p>=0.5) | 0.94 (f0_jitter) | **1.00**; 100% flagged |
| voice never seen: tts2 (AUC; flagged at p>=0.5) | 0.95 (f0_jitter) | **0.95**; 33% flagged |
| voice never seen: tts3 (AUC; flagged at p>=0.5) | 0.80 (mod_4hz) | **1.00**; 100% flagged |

## 3. Finding the original: why NOT a learned model
Locating a clip inside a lecture is an exact-match problem, so Sada uses signal processing
(band-limited spectral fingerprints), not AI: results are explainable down to the second and
need no training data. See compare.md (found 100% in the library, 0% false finds).

## Limits
- Small data: few recordings per mufti, 3 generic TTS voices. A higher number here is evidence of
  added value on THIS data, not a general accuracy claim.
