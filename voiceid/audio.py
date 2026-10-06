"""Audio for role 4: role 1's loader, windows, and degradations for testing.

Audio is loaded with role 1's `src.audio_utils.load_audio` (librosa, 16 kHz mono,
peak-normalized), so both roles read files the same way. If that module cannot be
imported (e.g. whisper is missing), the same librosa call is used directly.
The voice encoder re-normalizes the level itself (Resemblyzer's -30 dBFS), so
role 1's peak normalization does not change the result.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from voiceid import SR

_role1_loader = None


def _loader():
    global _role1_loader
    if _role1_loader is None:
        try:
            from src.audio_utils import load_audio as role1_load_audio  # role 1

            _role1_loader = role1_load_audio
        except Exception:
            _role1_loader = False
    return _role1_loader or None


def load_audio(path: str | Path) -> np.ndarray:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    fn = _loader()
    if fn is not None:
        return np.asarray(fn(str(path)), dtype=np.float32)
    try:
        import librosa

        y, _ = librosa.load(str(path), sr=SR, mono=True)
    except ImportError:  # minimal fallback for 16 kHz PCM wav (tests)
        import wave

        with wave.open(str(path), "rb") as w:
            if w.getframerate() != SR or w.getsampwidth() != 2:
                raise RuntimeError(f"{path.name}: need librosa to read this file")
            y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
            if w.getnchannels() > 1:
                y = y.reshape(-1, w.getnchannels()).mean(axis=1)
    return np.asarray(y, dtype=np.float32)


def rms_db(x: np.ndarray) -> float:
    if x.size == 0:
        return -120.0
    return float(20 * np.log10(np.sqrt(np.mean(x.astype(np.float64) ** 2)) + 1e-9))


def iter_windows(n_samples: int, win_sec: float, hop_sec: float, sr: int = SR):
    """(start, end) sample indices of sliding windows; the tail gets its own window if long enough."""
    win, hop = int(win_sec * sr), int(hop_sec * sr)
    if n_samples <= win:
        yield 0, n_samples
        return
    start = 0
    while start + win <= n_samples:
        yield start, start + win
        start += hop
    if start < n_samples and n_samples - start > win // 2:
        yield n_samples - win, n_samples


CONDITIONS = ("clean", "phone", "noisy")


def degrade(audio: np.ndarray, kind: str, seed: int = 0, sr: int = SR, snr_db: float = 15.0) -> np.ndarray:
    """Simulate a shared clip: 'phone' = 8 kHz telephone band; 'noisy' = noise at 15 dB SNR."""
    x = np.asarray(audio, dtype=np.float32)
    if kind == "clean":
        return x
    if kind == "phone":
        from scipy.signal import butter, resample_poly, sosfiltfilt

        y = resample_poly(x, 1, 2)
        sos = butter(4, [300, 3400], btype="bandpass", fs=sr // 2, output="sos")
        y = resample_poly(sosfiltfilt(sos, y), 2, 1)[: x.size]
        return np.pad(y, (0, x.size - y.size)).astype(np.float32)
    if kind == "noisy":
        rng = np.random.default_rng(seed)
        rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) or 1e-4
        return (x + rng.standard_normal(x.size) * rms / 10 ** (snr_db / 20)).astype(np.float32)
    raise ValueError(f"unknown condition '{kind}' (use one of {CONDITIONS})")
