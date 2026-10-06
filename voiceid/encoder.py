"""Speaker embeddings with Resemblyzer.

Resemblyzer API (checked against its source, resemble-ai/Resemblyzer v0.1.4):
- `VoiceEncoder(device, verbose)`; `embed_utterance(wav)` -> L2-normalized float32 (256,)
- The model was trained on audio passed through `preprocess_wav`:
  `normalize_volume(wav, -30 dBFS, increase_only=True)` then `trim_long_silences(wav)`.
  Its mel spectrogram is not log-scaled, so the input level matters: every window
  goes through exactly these two steps.
- Weights (`pretrained.pt`) ship inside the package; no download.

`SpeakerEncoder` is the interface: an ECAPA encoder can replace this one later.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from voiceid import SR

MIN_SPEECH_SEC = 1.0  # less speech than this in a window (after trimming silences) -> skipped


class SpeakerEncoder(Protocol):
    name: str

    def embed(self, audio: np.ndarray) -> np.ndarray | None:
        """L2-normalized embedding of a 16 kHz mono window, or None if it has too little speech."""
        ...


def l2norm(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def unit_rows(E: np.ndarray) -> np.ndarray:
    E = np.asarray(E, dtype=np.float32)
    return E / np.maximum(np.linalg.norm(E, axis=1, keepdims=True), 1e-9)


class ResemblyzerEncoder:
    name = "resemblyzer"

    def __init__(self, device: str = "cpu") -> None:
        from resemblyzer import VoiceEncoder
        from resemblyzer.audio import normalize_volume, trim_long_silences
        from resemblyzer.hparams import audio_norm_target_dBFS, sampling_rate

        if sampling_rate != SR:
            raise RuntimeError(f"Resemblyzer expects {sampling_rate} Hz")
        self.encoder = VoiceEncoder(device, verbose=False)
        self._normalize_volume = normalize_volume
        self._trim_long_silences = trim_long_silences
        self._target_dbfs = audio_norm_target_dBFS

    def preprocess(self, audio: np.ndarray, trim_silence: bool = True) -> np.ndarray | None:
        wav = np.asarray(audio, dtype=np.float32)
        if wav.size == 0 or float(np.sqrt(np.mean(wav.astype(np.float64) ** 2))) < 1e-5:
            return None  # digital silence: normalize_volume would divide by zero
        wav = self._normalize_volume(wav, self._target_dbfs, increase_only=True)
        wav = np.clip(wav, -1.0, 1.0).astype(np.float32)  # trim_long_silences converts to int16
        if trim_silence:
            wav = self._trim_long_silences(wav)
        return np.asarray(wav, dtype=np.float32)

    def embed(self, audio: np.ndarray, trim_silence: bool = True) -> np.ndarray | None:
        wav = self.preprocess(audio, trim_silence=trim_silence)
        if wav is None or wav.size < MIN_SPEECH_SEC * SR:
            return None
        return l2norm(np.asarray(self.encoder.embed_utterance(wav), dtype=np.float32))
