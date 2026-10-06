## Identity calibration — 2026-10-04 17:38

- Data: role 1's clips. Voiceprints from data/ref; trials from the 'cal' half of data/real + data/fake (al_alsheikh: 14, al_fawzan: 17, ibn_baz: 41, speakerX: 5, tts1: 5, tts2: 5, tts3: 5); the 'test' half is kept for evaluate.
- Encoder resemblyzer; windows 3 s, hop 1.5 s; clip score = 75th percentile; clip conditions: clean, phone (voiceprints always clean)
- Trials: 144 genuine, 288 other-mufti, 120 other-voice
- Genuine: median 0.644, 5-95% 0.556 to 0.903
- Other mufti: median 0.548, 5-95% 0.447 to 0.757
- Other voice: median 0.538, 5-95% 0.379 to 0.635
- Clip-level EER: 29.9% at 0.606
- Thresholds (max 5% wrong per side): low 0.556, high 0.750
- Speaker change: 408 same-voice / 2982 different-voice window pairs, EER 4.6% at similarity 0.800
- Caveat: the real clips and the reference clips may come from the same source videos, which makes this easier than clips found online. Treat the numbers as an upper bound.

## Identity calibration — 2026-10-04 17:47

- Method: raw / enroll ref+real. Encoder resemblyzer; windows 3 s, hop 1.5 s; clip score = 75th percentile; clip conditions: clean, phone
- Cal split (al_alsheikh: 9, al_fawzan: 11, ibn_baz: 27, speakerX: 5, tts1: 5, tts2: 5, tts3: 5); the test split is kept for evaluate.
- Trials: 94 genuine, 188 other-mufti, 120 other-voice
- Genuine: median 0.696, 5-95% 0.584 to 0.922
- Other mufti: median 0.557, 5-95% 0.435 to 0.784
- Other voice: median 0.501, 5-95% 0.396 to 0.635
- Clip-level EER: 18.1% at 0.630
- Thresholds (max 5% wrong per side): low 0.584, high 0.721
- Speaker change: 593 same-voice / 2982 different-voice window pairs, EER 4.9% at similarity 0.794
- Caveat: clips of one mufti may come from the same few source videos; clips found online are harder.

## Identity calibration — 2026-10-04 17:51

- Method: centered / enroll ref+real+phone. Encoder resemblyzer; windows 3 s, hop 1.5 s; clip score = 75th percentile; clip conditions: clean, phone
- Cal split (al_alsheikh: 9, al_fawzan: 11, ibn_baz: 27, speakerX: 5, tts1: 5, tts2: 5, tts3: 5); the test split is kept for evaluate.
- Trials: 94 genuine, 188 other-mufti, 120 other-voice
- Genuine: median 0.646, 5-95% 0.423 to 0.735
- Other mufti: median 0.242, 5-95% -0.013 to 0.458
- Other voice: median -0.103, 5-95% -0.478 to 0.227
- Clip-level EER: 6.3% at 0.424
- Thresholds (max 5% wrong per side): low 0.417, high 0.437
- Speaker change: 593 same-voice / 2982 different-voice window pairs, EER 3.4% at similarity 0.561
- Caveat: clips of one mufti may come from the same few source videos; clips found online are harder.

## Identity calibration — 2026-10-04 17:55

- Method: centered / enroll ref+real+phone. Encoder resemblyzer; windows 3 s, hop 1.5 s; clip score = 75th percentile; clip conditions: clean, phone
- Cal split (al_alsheikh: 9, al_fawzan: 11, ibn_baz: 27, speakerX: 5, tts1: 5, tts2: 5, tts3: 5); the test split is kept for evaluate.
- Trials: 94 genuine, 188 other-mufti, 120 other-voice
- Genuine: median 0.646, 5-95% 0.423 to 0.735
- Other mufti: median 0.242, 5-95% -0.013 to 0.458
- Other voice: median -0.103, 5-95% -0.478 to 0.227
- Clip-level EER: 6.3% at 0.424
- Thresholds (max 5% wrong per side): low 0.417, high 0.437
- Speaker change: 593 same-voice / 2982 different-voice window pairs, EER 3.4% at similarity 0.561
- Caveat: clips of one mufti may come from the same few source videos; clips found online are harder.

## Identity calibration — 2026-10-04 17:58

- Method: centered / enroll ref+real. Encoder resemblyzer; windows 3 s, hop 1.5 s; clip score = 75th percentile; clip conditions: clean, phone, noisy
- Cal split (al_alsheikh: 9, al_fawzan: 11, ibn_baz: 27, speakerX: 5, tts1: 5, tts2: 5, tts3: 5); the test split is kept for evaluate.
- Trials: 141 genuine, 282 other-mufti, 180 other-voice
- Genuine: median 0.489, 5-95% 0.280 to 0.755
- Other mufti: median 0.157, 5-95% -0.015 to 0.388
- Other voice: median -0.132, 5-95% -0.435 to 0.071
- Clip-level EER: 9.4% at 0.321
- Thresholds (max 5% wrong per side): low 0.280, high 0.368
- Speaker change: 593 same-voice / 2982 different-voice window pairs, EER 3.5% at similarity 0.548
- Caveat: clips of one mufti may come from the same few source videos; clips found online are harder.

