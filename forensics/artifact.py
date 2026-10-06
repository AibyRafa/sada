"""artifact_score: does the speech sound machine-generated (TTS / voice conversion)?

Per clip, a few numbers measured on the SPEECH frames only (so silence / noise floor,
which differs between our sources, does not decide):
  - pitch: how steady it is (frame-to-frame jitter, spread, share of voiced frames)
  - spectrum: flatness, spectral flux, how sharp the harmonics are (cepstral peak),
    energy above 4 kHz vs 1-4 kHz (computed after a phone-band copy too, see below)
  - rhythm: how regular the loudness envelope is (modulation spectrum around 4 Hz)
A small logistic regression (forensics/lr.py) turns them into a probability.

Training data = role 1's clips: data/fake (edge-tts, 3 voices) vs real speech (muftis + team member).
It is trained on clean, phone and noisy copies so the channel alone cannot give the answer.
LIMIT (written in every report): these are 3 generic TTS voices. A score here says
"sounds like THIS kind of generated speech"; it is not a detector of voice clones of the muftis.
"""

from __future__ import annotations

import numpy as np

from forensics.features import FPS, HOP, SR, frame_db, frames, logmel, power_spectrum

FEATURE_NAMES = [
    "voiced_ratio", "f0_jitter", "f0_spread", "f0_slope_std",
    "flatness_mean", "flatness_std", "flux_mean", "flux_std",
    "cep_peak_mean", "cep_peak_std", "hf_ratio_db",
    "mod_4hz", "mod_peakiness", "db_std",
]


def pitch_track(x: np.ndarray, fmin: float = 70.0, fmax: float = 350.0) -> tuple[np.ndarray, np.ndarray]:
    """(f0 Hz per 10 ms frame (0 = unvoiced), voicing strength 0..1). Normalized autocorrelation."""
    f = frames(x, win=640, hop=HOP).astype(np.float64)     # 40 ms frames
    f = f - f.mean(axis=1, keepdims=True)
    n = f.shape[1]
    F = np.fft.rfft(f, n=2 * n, axis=1)
    ac = np.fft.irfft(np.abs(F) ** 2, axis=1)[:, :n]
    ac = ac / (ac[:, :1] + 1e-12)
    lo, hi = int(SR / fmax), int(SR / fmin)
    seg = ac[:, lo:hi]
    k = np.argmax(seg, axis=1)
    strength = seg[np.arange(len(seg)), k]
    f0 = SR / (k + lo)
    f0[strength < 0.45] = 0.0
    return f0.astype(np.float32), strength.astype(np.float32)


def clip_features(audio: np.ndarray) -> np.ndarray:
    x = np.asarray(audio, dtype=np.float32)
    if x.size < SR // 2:
        x = np.pad(x, (0, SR // 2 - x.size))
    db = frame_db(x)
    speech = db > max(np.percentile(db, 95) - 30.0, -60.0)
    if speech.sum() < 20:
        speech = np.ones_like(speech)
    P = power_spectrum(x)
    T = min(len(P), len(speech))
    P, speech, db = P[:T], speech[:T], db[:T]
    Ps = P[speech] + 1e-10
    flat = np.exp(np.mean(np.log(Ps), axis=1)) / np.mean(Ps, axis=1)
    M = logmel(x)[:T]
    flux = np.r_[0, np.linalg.norm(np.diff(M, axis=0), axis=1)][speech]
    cep = np.fft.irfft(np.log(Ps), axis=1)[:, int(SR / 350):int(SR / 70)]   # quefrency of 70-350 Hz pitch
    cep_peak = cep.max(axis=1) - np.median(cep, axis=1)
    freqs = np.fft.rfftfreq(512, 1 / SR)
    hf = Ps[:, freqs >= 4000].sum(axis=1).mean()
    mf = Ps[:, (freqs >= 1000) & (freqs < 4000)].sum(axis=1).mean()

    f0, _ = pitch_track(x)
    f0 = f0[:T]
    v = (f0 > 0) & speech[: len(f0)]
    voiced_ratio = float(v.sum() / max(1, speech.sum()))
    if v.sum() >= 10:
        lf = np.log(f0[v])
        cont = v[1:] & v[:-1]
        d = np.diff(np.log(np.maximum(f0, 1)))[cont]
        jitter = float(np.median(np.abs(d))) if d.size else 0.0
        spread = float(np.std(lf))
        slope_std = float(np.std(d)) if d.size else 0.0
    else:
        jitter = spread = slope_std = 0.0

    env = db - db.mean()
    spec = np.abs(np.fft.rfft(env * np.hanning(len(env)))) ** 2
    mf_ = np.fft.rfftfreq(len(env), 1 / FPS)
    band = (mf_ >= 2) & (mf_ <= 8)
    mod4 = float(np.log(spec[band].sum() / (spec[(mf_ > 0.5) & (mf_ <= 20)].sum() + 1e-9) + 1e-9))
    peaky = float(np.log(spec[band].max() / (spec[band].mean() + 1e-9) + 1e-9)) if band.any() else 0.0

    return np.array([
        voiced_ratio, jitter, spread, slope_std,
        float(np.mean(flat)), float(np.std(flat)), float(np.mean(flux)), float(np.std(flux)),
        float(np.mean(cep_peak)), float(np.std(cep_peak)), float(10 * np.log10(hf / (mf + 1e-12) + 1e-12)),
        mod4, peaky, float(np.std(db[speech])),
    ], dtype=np.float64)


def artifact_score(audio: np.ndarray, model=None) -> float | None:
    """Contract function: probability (0..1) that the speech is generated, or None without a trained model."""
    if model is None:
        return None
    return float(model.proba(clip_features(audio)[None, :])[0])
