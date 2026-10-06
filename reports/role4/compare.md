# Method comparison — 2026-10-04 17:58

Chosen by the EER on the **cal** split (clean + phone + noisy clips). The test columns are shown for information only; they never decide.

| method | cal EER | test clean: closest right | right mufti -> match | wrong mufti -> mismatch | wrong mufti -> match | test phone: closest right | test noisy: closest right |
|---|---|---|---|---|---|---|---|
| raw / enroll ref | 27.0% | 21/47 | 40% | 64% | 20% | 25/47 | 23/47 |
| centered / enroll ref | 28.4% | 21/47 | 38% | 57% | 19% | 17/47 | 21/47 |
| raw / enroll ref+real | 16.5% | 46/47 | 91% | 91% | 0% | 38/47 | 47/47 |
| centered / enroll ref+real | 9.4% | 45/47 | 94% | 96% | 2% | 43/47 | 47/47 |
| raw / enroll ref+real+phone | 12.0% | 45/47 | 91% | 95% | 1% | 46/47 | 47/47 |
| centered / enroll ref+real+phone | 11.3% | 43/47 | 89% | 95% | 4% | 46/47 | 46/47 |

**Chosen: centered / enroll ref+real**

