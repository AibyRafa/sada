# Sada — measured time per check (2026-10-06 00:24)

- Machine: Windows 11, AMD64 Family 25 Model 68 Stepping 1, AuthenticAMD, 16 logical CPUs, no GPU used
- Voice model available: yes; original library: 33 recordings, 135.9 min
- One-time start (load models + index the library): **2.6 s**
- Peak memory of the whole check process: **1213 MB**
- Clips timed: 20 (real: 5, fake: 5, spliced: 5, cropped: 5)

| | value |
|---|---|
| median time per clip | **1.00 s** |
| 90th percentile | 1.92 s |
| slowest clip | 2.87 s |
| median seconds of work per minute of audio | 12.1 s |

| clip | length (s) | time (s) | result |
|---|---|---|---|
| real/speakerA_real_01.wav | 8.0 | 2.87 | verified_excerpt |
| real/speakerA_real_02.wav | 8.0 | 1.89 | verified_excerpt |
| real/speakerA_real_03.wav | 8.0 | 1.81 | verified_excerpt |
| real/speakerA_real_04.wav | 8.0 | 1.92 | verified_excerpt |
| real/speakerA_real_05.wav | 8.0 | 1.92 | verified_excerpt |
| fake/tts1_fake_01.wav | 4.7 | 0.89 | misattributed |
| fake/tts1_fake_02.wav | 3.9 | 0.71 | misattributed |
| fake/tts1_fake_03.wav | 5.7 | 1.08 | misattributed |
| fake/tts1_fake_04.wav | 5.7 | 1.12 | misattributed |
| fake/tts1_fake_05.wav | 6.0 | 1.21 | misattributed |
| spliced/speakerX_spliced_01.wav | 5.9 | 1.32 | misattributed |
| spliced/speakerX_spliced_02.wav | 3.9 | 0.78 | misattributed |
| spliced/speakerX_spliced_03.wav | 4.3 | 0.92 | misattributed |
| spliced/speakerX_spliced_04.wav | 4.2 | 0.90 | misattributed |
| spliced/speakerX_spliced_05.wav | 5.1 | 1.11 | misattributed |
| cropped/speakerX_cropped_01.wav | 2.7 | 0.53 | misattributed |
| cropped/speakerX_cropped_02.wav | 2.3 | 0.42 | misattributed |
| cropped/speakerX_cropped_03.wav | 2.1 | 0.38 | misattributed |
| cropped/speakerX_cropped_04.wav | 2.9 | 0.54 | misattributed |
| cropped/speakerX_cropped_05.wav | 3.6 | 0.72 | misattributed |

Limits: measured on this one laptop, with the current library size. The original search grows with the library; a larger library needs re-measuring.
