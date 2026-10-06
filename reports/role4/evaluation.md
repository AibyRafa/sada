# Role 4 evaluation — 2026-10-04 17:58

Held-out test split of role 1's real clips (47 mufti clips, 20 other/generated). Method: centered / enroll ref+real. Thresholds: low 0.2801, high 0.3675 (calibrated: True). Each clip is scored like identity_score.

### clean: 47 mufti clips
- Closest voiceprint is the right mufti: 45/47 (96%)
- Attributed to the RIGHT mufti: match 94%, unclear 4%, mismatch 2%   (want: mostly match, mismatch ~0)
- Attributed to the WRONG mufti: mismatch 96%, unclear 2%, match 2%   (want: mostly mismatch, match ~0)
- Other real voice vs any mufti: match 0% (want ~0), unclear 0%, mismatch 100%
- Generated speech (TTS, not a cloned mufti) vs any mufti: match 0% (want ~0), unclear 0%, mismatch 100%
- Right-mufti clip scores: median 0.664, lowest 5% below 0.443
- al_alsheikh: 9 clips | closest = right 9/9 | match 9/9
- al_fawzan: 11 clips | closest = right 9/11 | match 9/11
- ibn_baz: 27 clips | closest = right 27/27 | match 26/27

Confusion (clean): rows = true mufti, columns = closest voiceprint

| true \ closest | al_alsheikh | al_fawzan | ibn_baz |
|---|---|---|---|
| al_alsheikh | 9 | 0 | 0 |
| al_fawzan | 2 | 9 | 0 |
| ibn_baz | 0 | 0 | 27 |

### phone: 47 mufti clips
- Closest voiceprint is the right mufti: 43/47 (91%)
- Attributed to the RIGHT mufti: match 74%, unclear 17%, mismatch 9%   (want: mostly match, mismatch ~0)
- Attributed to the WRONG mufti: mismatch 93%, unclear 5%, match 2%   (want: mostly mismatch, match ~0)
- Other real voice vs any mufti: match 0% (want ~0), unclear 0%, mismatch 100%
- Generated speech (TTS, not a cloned mufti) vs any mufti: match 0% (want ~0), unclear 0%, mismatch 100%
- Right-mufti clip scores: median 0.420, lowest 5% below 0.259
- al_alsheikh: 9 clips | closest = right 6/9 | match 1/9
- al_fawzan: 11 clips | closest = right 11/11 | match 11/11
- ibn_baz: 27 clips | closest = right 26/27 | match 23/27

### noisy: 47 mufti clips
- Closest voiceprint is the right mufti: 47/47 (100%)
- Attributed to the RIGHT mufti: match 83%, unclear 13%, mismatch 4%   (want: mostly match, mismatch ~0)
- Attributed to the WRONG mufti: mismatch 99%, unclear 1%, match 0%   (want: mostly mismatch, match ~0)
- Other real voice vs any mufti: match 0% (want ~0), unclear 0%, mismatch 100%
- Generated speech (TTS, not a cloned mufti) vs any mufti: match 0% (want ~0), unclear 0%, mismatch 100%
- Right-mufti clip scores: median 0.475, lowest 5% below 0.317
- al_alsheikh: 9 clips | closest = right 9/9 | match 9/9
- al_fawzan: 11 clips | closest = right 11/11 | match 6/11
- ibn_baz: 27 clips | closest = right 27/27 | match 24/27

- phone = 8 kHz telephone band (like re-recorded / WhatsApp clips); noisy = noise at 15 dB SNR.
- Generated speech here is generic TTS, not a clone of a mufti: identity is not a deepfake detector (that is role 5).
- Caveat: clips of one mufti may come from the same few source videos; clips found online are harder.

