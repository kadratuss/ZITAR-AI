from pathlib import Path
import wave
import numpy as np
import sounddevice as sd
from piper import PiperVoice

BASE = Path(__file__).resolve().parent
MODEL = BASE / "zitar_voice_models" / "tr_TR-dfki-medium.onnx"
CONFIG = BASE / "zitar_voice_models" / "tr_TR-dfki-medium.onnx.json"
OUT = BASE / "zitar_tts_test.wav"

TEXT = "Merhaba. Ben ZİTAR. Ses sistemi çalışıyor."

print("ZİTAR TTS LAB V1")
print("Metin:", TEXT)

voice = PiperVoice.load(str(MODEL), config_path=str(CONFIG))

with wave.open(str(OUT), "wb") as wav_file:
    voice.synthesize_wav(TEXT, wav_file)

with wave.open(str(OUT), "rb") as wf:
    rate = wf.getframerate()
    channels = wf.getnchannels()
    width = wf.getsampwidth()
    frames = wf.readframes(wf.getnframes())

if width != 2:
    raise RuntimeError(f"Beklenmeyen sample width: {width}")

audio = np.frombuffer(frames, dtype=np.int16)
if channels > 1:
    audio = audio.reshape(-1, channels)

print(f"WAV: {OUT}")
print(f"Sample rate: {rate} Hz")
print("Hoparlörden oynatılıyor...")
sd.play(audio, rate, device=3)
sd.wait()
print("TTS TEST TAMAMLANDI.")
