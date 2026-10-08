from __future__ import annotations

import sys
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

DEVICE = 1
SAMPLE_RATE = 16000
CHANNELS = 1
RECORD_SECONDS = 5
MODEL_SIZE = "small"
LANGUAGE = "tr"

BASE_DIR = Path(__file__).resolve().parent
WAV_PATH = BASE_DIR / "zitar_voice_stt_test.wav"


def record_wav() -> None:
    print(f"\nMikrofon: device {DEVICE}")
    print(f"Kayıt: {RECORD_SECONDS} saniye / {SAMPLE_RATE} Hz / mono")
    input("\nHazır olduğunda ENTER'a bas ve konuş... ")

    print("\nKAYIT BAŞLADI 🎤")
    audio = sd.rec(
        int(RECORD_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        device=DEVICE,
    )

    for remaining in range(RECORD_SECONDS, 0, -1):
        print(f"  {remaining}...", flush=True)
        time.sleep(1)

    sd.wait()
    print("KAYIT BİTTİ.")

    peak = int(np.max(np.abs(audio))) if audio.size else 0
    print(f"Ses peak seviyesi: {peak} / 32767")

    with wave.open(str(WAV_PATH), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())

    print(f"WAV: {WAV_PATH}")


def transcribe() -> None:
    print(f"\nWhisper modeli yükleniyor: {MODEL_SIZE}")
    print("İlk çalıştırmada model indirileceği için biraz sürebilir.")

    # İlk laboratuvar bilinçli olarak CPU:
    # Ollama'nın kullandığı GPU/VRAM'e dokunmuyoruz.
    model = WhisperModel(
        MODEL_SIZE,
        device="cpu",
        compute_type="int8",
    )

    print("Türkçe transkripsiyon yapılıyor...\n")
    segments, info = model.transcribe(
        str(WAV_PATH),
        language=LANGUAGE,
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=False,
    )

    text = " ".join(seg.text.strip() for seg in segments if seg.text.strip()).strip()

    print("=" * 60)
    print("ZİTAR STT SONUCU")
    print("=" * 60)
    print(text if text else "[METİN ALGILANMADI]")
    print("=" * 60)
    print(f"Dil: {info.language} | Dil olasılığı: {info.language_probability:.4f}")

    if not text:
        sys.exit(2)


if __name__ == "__main__":
    print("ZİTAR VOICE — STT LAB V1")
    print("READ ONLY • CHAT/EXECUTION BAĞLANTISI YOK")
    record_wav()
    transcribe()
