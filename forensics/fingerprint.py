"""Audio fingerprint features used to find a clip inside the original recordings.

24 log-mel bands between 250 and 3800 Hz at 50 frames per second. That band survives a phone /
WhatsApp channel (300-3400 Hz), so a re-shared copy still lines up with its original.
Each band has its running 1.5 s mean removed (channel / volume changes cancel out), and each frame
its mean over the bands (only the spectral SHAPE is compared, so loudness patterns alone do not match).
"""

from __future__ import annotations

import numpy as np

from forensics.features import SR, mel_filterbank

FP_WIN = 512           # 32 ms
FP_HOP = 320           # 20 ms -> 50 frames per second
FP_FPS = SR // FP_HOP
FP_BANDS = 24
FP_FMIN, FP_FMAX = 250.0, 3800.0
CMN_SEC = 1.5

_FB: np.ndarray | None = None


def _filterbank() -> np.ndarray:
    global _FB
    if _FB is None:
        def hz2mel(h): return 2595 * np.log10(1 + h / 700)
        def mel2hz(m): return 700 * (10 ** (m / 2595) - 1)
        n_fft = FP_WIN
        pts = mel2hz(np.linspace(hz2mel(FP_FMIN), hz2mel(FP_FMAX), FP_BANDS + 2))
        freqs = np.fft.rfftfreq(n_fft, 1 / SR)
        fb = np.zeros((FP_BANDS, freqs.size), dtype=np.float32)
        for m in range(FP_BANDS):
            a, c, b = pts[m], pts[m + 1], pts[m + 2]
            up = (freqs - a) / (c - a)
            down = (b - freqs) / (b - c)
            fb[m] = np.clip(np.minimum(up, down), 0, None)
        _FB = fb
    return _FB


def _frames(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    if x.size < FP_WIN:
        x = np.pad(x, (0, FP_WIN - x.size))
    n = 1 + (x.size - FP_WIN) // FP_HOP
    idx = np.arange(FP_WIN)[None, :] + FP_HOP * np.arange(n)[:, None]
    return x[idx]


def raw_bands(x: np.ndarray, block: int = 20000) -> tuple[np.ndarray, np.ndarray]:
    """(log band energies (T, 16), frame level in dB (T,)). Works in blocks so hours of audio fit in memory."""
    x = np.asarray(x, dtype=np.float32)
    n = max(1, 1 + (max(x.size, FP_WIN) - FP_WIN) // FP_HOP)
    fb = _filterbank()
    win = np.hanning(FP_WIN).astype(np.float32)
    L = np.empty((n, FP_BANDS), dtype=np.float32)
    db = np.empty(n, dtype=np.float32)
    for s in range(0, n, block):
        e = min(n, s + block)
        seg = x[s * FP_HOP: (e - 1) * FP_HOP + FP_WIN]
        f = _frames(seg)[: e - s]
        db[s:e] = 10 * np.log10(np.mean(f.astype(np.float64) ** 2, axis=1) + 1e-10)
        P = np.abs(np.fft.rfft(f * win, axis=1)) ** 2
        L[s:e] = np.log(P @ fb.T + 1e-7)
    return L, db


def normalize(L: np.ndarray) -> np.ndarray:
    """Remove the running mean of each band (CMN over 1.5 s)."""
    k = int(CMN_SEC * FP_FPS)
    if len(L) <= 1:
        return np.zeros_like(L)
    cs = np.vstack([np.zeros((1, L.shape[1]), np.float64), np.cumsum(L, axis=0, dtype=np.float64)])
    t = np.arange(len(L))
    a = np.clip(t - k // 2, 0, len(L))
    b = np.clip(t + k // 2 + 1, 0, len(L))
    mean = (cs[b] - cs[a]) / (b - a)[:, None]
    return (L - mean).astype(np.float32)


def fingerprint(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(normalized features (T, 24), frame dB (T,))."""
    L, db = raw_bands(x)
    F = normalize(L)
    return F - F.mean(axis=1, keepdims=True), db
