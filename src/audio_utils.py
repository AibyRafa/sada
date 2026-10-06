import librosa
import numpy as np
import whisper

SR = 16000
_model = None

def load_audio(path: str, sr: int = SR) -> np.ndarray:
    wav, _ = librosa.load(path, sr=sr, mono=True)
    peak = np.max(np.abs(wav))
    if peak > 0:
        wav = wav / peak * 0.95
    return wav.astype(np.float32)

def transcribe(wav: np.ndarray, language=None) -> dict:
    global _model
    if _model is None:
        _model = whisper.load_model("base")  # use "small" later for better accuracy
    result = _model.transcribe(wav, language=language, fp16=False)
    return {
        "text": result["text"].strip(),
        "language": result["language"],
        "segments": [
            {"start": s["start"], "end": s["end"], "text": s["text"]}
            for s in result["segments"]
        ],
    }