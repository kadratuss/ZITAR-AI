from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

DEVICE = 1
SAMPLE_RATE = 16000
CHANNELS = 1
RECORD_SECONDS = 6
MODEL_SIZE = "small"
LANGUAGE = "tr"
CHAT_URL = "http://127.0.0.1:5016/api/chat"

BASE_DIR = Path(__file__).resolve().parent
WAV_PATH = BASE_DIR / "zitar_voice_chat_test.wav"

# V1: deliberately conservative aliases observed/expected for Turkish speech.
# We do NOT run a general spelling corrector over the user's sentence.
VOICE_ALIASES = {
    "bteci": "BTC",
    "bitici": "BTC",
    "b t c": "BTC",
    "btc": "BTC",
}


def normalize_voice_text(text: str) -> tuple[str, list[str]]:
    out = text
    changes = []
    for spoken, canonical in VOICE_ALIASES.items():
        pattern = re.compile(rf"(?<!\w){re.escape(spoken)}(?!\w)", re.IGNORECASE)
        new = pattern.sub(canonical, out)
        if new != out:
            changes.append(f"{spoken} -> {canonical}")
            out = new
    return out, changes


def record_wav() -> tuple[int, float]:
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

    samples = audio.astype(np.float32).reshape(-1)
    peak = int(np.max(np.abs(samples))) if samples.size else 0
    rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0

    with wave.open(str(WAV_PATH), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())

    return peak, rms


def transcribe() -> tuple[str, str, float]:
    print(f"\nWhisper modeli: {MODEL_SIZE} / CPU int8")
    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")

    segments, info = model.transcribe(
        str(WAV_PATH),
        language=LANGUAGE,
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    text = " ".join(s.text.strip() for s in segments if s.text.strip()).strip()
    return text, info.language, float(info.language_probability)


def call_zitar(question: str) -> dict:
    body = json.dumps(
        {"question": question, "use_qwen": True},
        ensure_ascii=False,
    ).encode("utf-8")

    req = urllib.request.Request(
        CHAT_URL,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    print("ZİTAR VOICE CHAT LAB V1")
    print("STT -> SYMBOL NORMALIZER -> CHAT API 5016")
    print("READ ONLY • EXECUTION AUTHORITY YOK • V3 WRITE YOK")

    peak, rms = record_wav()
    print(f"\nSes peak: {peak} / 32767")
    print(f"Ses RMS : {rms:.1f}")
    if peak >= 32760:
        print("UYARI   : Kayıtta clipping/tavana vurma görüldü.")

    raw, lang, prob = transcribe()
    print("\n=== RAW STT ===")
    print(raw or "[METİN ALGILANMADI]")
    print(f"Dil={lang} | olasılık={prob:.4f}")

    if not raw:
        return

    normalized, changes = normalize_voice_text(raw)
    print("\n=== NORMALIZED ===")
    print(normalized)
    print("Düzeltmeler:", ", ".join(changes) if changes else "yok")

    print("\n=== 5016'YA GÖNDERİLİYOR ===")
    try:
        result = call_zitar(normalized)
    except urllib.error.HTTPError as e:
        print(f"HTTP ERROR: {e.code} {e.reason}")
        print(e.read().decode("utf-8", errors="replace"))
        return
    except Exception as e:
        print(f"CHAT ERROR: {type(e).__name__}: {e}")
        return

    print("\n=== ROUTING ===")
    print("symbol :", result.get("symbol"))
    print("intent :", result.get("intent"))
    print("mode   :", result.get("mode"))

    guard = result.get("guard")
    if guard is not None:
        print("guard  :", json.dumps(guard, ensure_ascii=False))

    print("\n=== ZİTAR ANSWER ===")
    print(result.get("answer", "[CEVAP YOK]"))


if __name__ == "__main__":
    main()
