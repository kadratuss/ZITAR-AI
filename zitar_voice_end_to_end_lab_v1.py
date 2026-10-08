from __future__ import annotations

import json
import re
import time
import urllib.request
import urllib.error
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from piper import PiperVoice

BASE = Path(__file__).resolve().parent

MIC_DEVICE = 1
SPEAKER_DEVICE = 3
SAMPLE_RATE = 16000
CHANNELS = 1
RECORD_SECONDS = 6
WHISPER_MODEL = "small"
CHAT_URL = "http://127.0.0.1:5016/api/chat"

VOICE_MODEL = BASE / "zitar_voice_models" / "tr_TR-dfki-medium.onnx"
VOICE_CONFIG = BASE / "zitar_voice_models" / "tr_TR-dfki-medium.onnx.json"
INPUT_WAV = BASE / "zitar_voice_input.wav"
OUTPUT_WAV = BASE / "zitar_voice_answer.wav"

VOICE_ALIASES = {
    "bteci": "BTC",
    "bitici": "BTC",
    "b t c": "BTC",
    "btc": "BTC",
}

SECTION_RE = re.compile(r"^\[[A-ZİIĞÜŞÖÇ_]+\]\s*$", re.MULTILINE)


def normalize_question(text: str) -> tuple[str, list[str]]:
    out = text.strip()
    changes = []
    for spoken, canonical in VOICE_ALIASES.items():
        pat = re.compile(rf"(?<!\w){re.escape(spoken)}(?!\w)", re.IGNORECASE)
        new = pat.sub(canonical, out)
        if new != out:
            changes.append(f"{spoken} -> {canonical}")
            out = new
    return out, changes


def tts_safe_text(answer: str) -> str:
    # Presentation-only. We remove machine section labels, not research content.
    text = SECTION_RE.sub("", answer)
    text = text.replace("READ ONLY.", "")
    text = text.replace("V3 write yok.", "")
    text = text.replace("Execution authority yok;", "")
    text = text.replace("gerçek emir yok;", "")
    text = text.replace("durable_change_supported=False", "kalıcı görüş değişimi desteklenmiyor")
    text = text.replace("BASELINE_ONLY", "yalnız başlangıç kaydı")
    text = text.replace("MIXED_NO_DIRECTIONAL_VIEW", "belirgin yön görüşü yok")
    text = text.replace("Data confidence=HIGH", "Veri kalitesi yüksek")
    text = text.replace("overall=MIXED", "genel görünüm karışık")
    text = text.replace("view=", "görüş ")
    text = text.replace("change=", "değişim ")
    text = text.replace("BTCTRY", "Bitcoin Türk lirası")
    text = text.replace("BTC", "Bitcoin")
    text = text.replace("5m", "beş dakika")
    text = text.replace("15m", "on beş dakika")
    text = text.replace("1m", "bir dakika")
    text = text.replace("30m", "otuz dakika")
    text = text.replace("1h", "bir saat")
    text = text.replace("4h", "dört saat")
    text = text.replace("1d", "bir gün")
    text = text.replace("1w", "bir hafta")
    text = text.replace("MEDIUM", "orta")
    text = text.replace("MIXED", "karışık")
    text = text.replace("UP", "yukarı")
    text = text.replace("DOWN", "aşağı")
    text = re.sub(r"\$280M\b", "iki yüz seksen milyon dolar", text)
    text = re.sub(r"\$84K\b", "seksen dört bin dolar", text)
    text = re.sub(r"\$86,000\b", "seksen altı bin dolar", text)
    text = re.sub(r"\$16 billion\b", "on altı milyar dolar", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def record() -> tuple[int, float]:
    input("\nENTER'a bas ve ZİTAR'a sorunu söyle... ")
    print("Dinliyorum 🎤")
    audio = sd.rec(
        int(RECORD_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        device=MIC_DEVICE,
    )
    for n in range(RECORD_SECONDS, 0, -1):
        print(f"{n}...", flush=True)
        time.sleep(1)
    sd.wait()

    flat = audio.astype(np.float32).reshape(-1)
    peak = int(np.max(np.abs(flat))) if flat.size else 0
    rms = float(np.sqrt(np.mean(flat * flat))) if flat.size else 0.0

    with wave.open(str(INPUT_WAV), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    return peak, rms


def ask_chat(question: str) -> dict:
    data = json.dumps(
        {"question": question, "use_qwen": True},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        CHAT_URL,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def speak(voice: PiperVoice, text: str) -> None:
    with wave.open(str(OUTPUT_WAV), "wb") as wf:
        voice.synthesize_wav(text, wf)

    with wave.open(str(OUTPUT_WAV), "rb") as wf:
        rate = wf.getframerate()
        channels = wf.getnchannels()
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)

    if channels > 1:
        audio = audio.reshape(-1, channels)

    sd.play(audio, rate, device=SPEAKER_DEVICE)
    sd.wait()


def main() -> None:
    print("ZİTAR VOICE END-TO-END LAB V1")
    print("STT -> 5016 GROUNDED CHAT -> PRESENTATION FORMATTER -> TTS")
    print("READ ONLY • EXECUTION AUTHORITY YOK • V3 WRITE YOK")

    print("\nWhisper yükleniyor...")
    whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    print("Piper yükleniyor...")
    voice = PiperVoice.load(str(VOICE_MODEL), config_path=str(VOICE_CONFIG))

    peak, rms = record()
    print(f"\nSes peak={peak}/32767 | RMS={rms:.1f}")

    segments, info = whisper.transcribe(
        str(INPUT_WAV),
        language="tr",
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    raw = " ".join(s.text.strip() for s in segments if s.text.strip()).strip()
    print("\nRAW STT:", raw or "[METİN YOK]")

    if not raw:
        print("Konuşma algılanmadı.")
        return

    question, changes = normalize_question(raw)
    print("SORU   :", question)
    print("NORMAL :", ", ".join(changes) if changes else "değişiklik yok")

    try:
        result = ask_chat(question)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print("5016 CHAT ERROR:", e)
        return

    print("\nROUTING:")
    print("symbol =", result.get("symbol"))
    print("intent =", result.get("intent"))
    print("mode   =", result.get("mode"))
    print("guard  =", json.dumps(result.get("guard"), ensure_ascii=False))

    answer = str(result.get("answer") or "").strip()
    if not answer:
        print("ZİTAR cevabı boş.")
        return

    print("\n=== KANONİK ZİTAR CEVABI ===")
    print(answer)

    spoken = tts_safe_text(answer)
    print("\n=== TTS PRESENTATION ===")
    print(spoken)

    print("\nZİTAR konuşuyor 🔊")
    speak(voice, spoken)
    print("TAMAMLANDI.")


if __name__ == "__main__":
    main()
