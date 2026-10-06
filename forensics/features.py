"""Frame features in plain numpy (no librosa needed): STFT, log-mel, energy."""

from __future__ import annotations

import numpy as np

SR = 16000
WIN = 400      # 25 ms
HOP = 160      # 10 ms -> 100 frames per second
N_FFT = 512
FPS = SR // HOP


def frames(x: np.ndarray, win: int = WIN, hop: int = HOP) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    if x.size < win:
        x = np.pad(x, (0, win - x.size))
    n = 1 + (x.size - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    return x[idx]


def power_spectrum(x: np.ndarray) -> np.ndarray:
    f = frames(x) * np.hanning(WIN).astype(np.float32)
    return (np.abs(np.fft.rfft(f, n=N_FFT, axis=1)) ** 2).astype(np.float32)   # (T, 257)


_MEL_CACHE: dict[int, np.ndarray] = {}


def mel_filterbank(n_mels: int = 40, sr: int = SR, n_fft: int = N_FFT) -> np.ndarray:
    if n_mels in _MEL_CACHE:
        return _MEL_CACHE[n_mels]
    def hz2mel(h): return 2595 * np.log10(1 + h / 700)
    def mel2hz(m): return 700 * (10 ** (m / 2595) - 1)
    pts = mel2hz(np.linspace(hz2mel(50), hz2mel(sr / 2), n_mels + 2))
    bins = np.floor((n_fft + 1) * pts / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for m in range(1, n_mels + 1):
        a, c, b = bins[m - 1], bins[m], bins[m + 1]
        if c > a:
            fb[m - 1, a:c] = (np.arange(a, c) - a) / (c - a)
        if b > c:
            fb[m - 1, c:b] = (b - np.arange(c, b)) / (b - c)
    _MEL_CACHE[n_mels] = fb
    return fb


def logmel(x: np.ndarray, n_mels: int = 40) -> np.ndarray:
    return np.log(power_spectrum(x) @ mel_filterbank(n_mels).T + 1e-8).astype(np.float32)   # (T, n_mels)


def frame_db(x: np.ndarray) -> np.ndarray:
    f = frames(x)
    return (10 * np.log10(np.mean(f.astype(np.float64) ** 2, axis=1) + 1e-10)).astype(np.float32)
