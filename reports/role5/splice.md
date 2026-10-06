# Role 5 — detect_splice_points (blind, no original): evaluation (2026-10-06 00:07)

Trained on half of role 1's spliced clips (15) + real clips; tested on the other half (15) + held-out real clips (52).
Threshold = 95% of real training clips below it: 0.800. A join counts if found within ±0.25 s.

| condition | hard cut | 30 ms fade | fade + noise | real clips wrongly flagged |
|---|---|---|---|---|
| clean | 0% | 20% | 0% | 4% |
| phone | 0% | 0% | 0% | 0% |
| noisy | 0% | 0% | 0% | 4% |

**Used in the verdict: NO** (needs >= 60% of joins found on clean clips with
<= 10% of real clips flagged). When it is not used, Sada says it cannot judge edits without the original.

## Why this is hard
Role 1's joins are made inside the same speaker's recordings (same room, same phone, cut in mid-speech).
Without the original there is often nothing left to hear. With the original in the library,
compare_with_original finds these joins (see compare.md).
