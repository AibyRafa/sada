from src.audio_utils import load_audio, transcribe

wav = load_audio("data/real/test.wav")
print("Samples:", len(wav), "| Seconds:", len(wav) / 16000)

out = transcribe(wav)
print("Language:", out["language"])
print("Text:", out["text"])