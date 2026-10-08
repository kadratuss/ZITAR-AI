from __future__ import annotations
import json,re,time,urllib.request,wave
from pathlib import Path
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from piper import PiperVoice

BASE=Path(__file__).resolve().parent
MIC_DEVICE=1; SPEAKER_DEVICE=3; SAMPLE_RATE=16000; RECORD_SECONDS=6
CHAT_URL="http://127.0.0.1:5016/api/chat"
MODEL=BASE/"zitar_voice_models"/"tr_TR-dfki-medium.onnx"
CONFIG=BASE/"zitar_voice_models"/"tr_TR-dfki-medium.onnx.json"
IN_WAV=BASE/"zitar_voice_input.wav"; OUT_WAV=BASE/"zitar_voice_answer.wav"
ALIASES={"bteci":"BTC","bitici":"BTC","b t c":"BTC","btc":"BTC"}

def normalize(q):
    changes=[]
    for a,b in ALIASES.items():
        n=re.sub(rf"(?<!\\w){re.escape(a)}(?!\\w)",b,q,flags=re.I)
        if n!=q: changes.append(f"{a} -> {b}"); q=n
    return q.strip(),changes

def parse_sections(a):
    d={}; key=None
    for line in a.splitlines():
        line=line.strip()
        m=re.fullmatch(r"\[([A-ZİIĞÜŞÖÇ_]+)\]",line)
        if m: key=m.group(1); d[key]=[]
        elif key and line: d[key].append(line)
    return {k:" ".join(v) for k,v in d.items()}

def natural(t):
    for a,b in [("BTCTRY","Bitcoin Türk lirası"),("BTC","Bitcoin"),
        ("MIXED_NO_DIRECTIONAL_VIEW","belirgin yön görüşü yok"),
        ("BASELINE_ONLY","yalnız başlangıç kaydı"),("DOWN_DOMINANT","aşağı yön baskın"),
        ("UP_DOMINANT","yukarı yön baskın"),("MEDIUM","orta"),("MIXED","karışık"),
        ("LOW","düşük"),("HIGH","yüksek"),("15m","on beş dakika"),("30m","otuz dakika"),
        ("5m","beş dakika"),("1m","bir dakika"),("1h","bir saat"),("4h","dört saat"),
        ("1d","bir gün"),("1w","bir hafta")]: t=t.replace(a,b)
    t=re.sub(r"\$280M\b","iki yüz seksen milyon dolar",t)
    t=re.sub(r"\$84K\b","seksen dört bin dolar",t)
    t=re.sub(r"\$86,000\b","seksen altı bin dolar",t)
    t=re.sub(r"\$16 billion\b","on altı milyar dolar",t,flags=re.I)
    return re.sub(r"\s+"," ",t).strip()

def spoken_summary(answer):
    s=parse_sections(answer)
    research=re.split(r"(?<=[.!?])\s+",s.get("ZITAR_RESEARCH",""))
    chosen=[x for x in research[:3] if x]
    news=re.split(r"(?<=[.!?])\s+",s.get("EVENT_NEWS",""))
    c=next((x for x in news if "nedensel" in x.lower()),"")
    if c: chosen.append(c)
    return natural(" ".join(chosen)) or "Sesli özet için uygun araştırma metni bulunamadı."

def record():
    input("\nENTER'a bas ve sorunu söyle... "); print("Dinliyorum 🎤")
    a=sd.rec(RECORD_SECONDS*SAMPLE_RATE,samplerate=SAMPLE_RATE,channels=1,dtype="int16",device=MIC_DEVICE)
    for n in range(RECORD_SECONDS,0,-1): print(f"{n}...",flush=True); time.sleep(1)
    sd.wait(); f=a.astype(np.float32).reshape(-1)
    peak=int(np.max(np.abs(f))) if f.size else 0; rms=float(np.sqrt(np.mean(f*f))) if f.size else 0
    with wave.open(str(IN_WAV),"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SAMPLE_RATE); w.writeframes(a.tobytes())
    return peak,rms

def chat(q):
    b=json.dumps({"question":q,"use_qwen":True},ensure_ascii=False).encode()
    r=urllib.request.Request(CHAT_URL,data=b,headers={"Content-Type":"application/json; charset=utf-8"},method="POST")
    with urllib.request.urlopen(r,timeout=120) as x: return json.loads(x.read().decode())

def speak(v,t):
    with wave.open(str(OUT_WAV),"wb") as w: v.synthesize_wav(t,w)
    with wave.open(str(OUT_WAV),"rb") as w:
        rate=w.getframerate(); ch=w.getnchannels(); a=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16)
    if ch>1:a=a.reshape(-1,ch)
    sd.play(a,rate,device=SPEAKER_DEVICE); sd.wait()

def main():
    print("ZİTAR VOICE END-TO-END LAB V2")
    print("FULL CANONICAL ON SCREEN • SHORT DETERMINISTIC VOICE")
    print("READ ONLY • EXECUTION AUTHORITY YOK • V3 WRITE YOK")
    wh=WhisperModel("small",device="cpu",compute_type="int8")
    voice=PiperVoice.load(str(MODEL),config_path=str(CONFIG))
    peak,rms=record(); print(f"\nSes peak={peak}/32767 | RMS={rms:.1f}")
    segs,info=wh.transcribe(str(IN_WAV),language="tr",beam_size=5,vad_filter=True,condition_on_previous_text=False)
    raw=" ".join(x.text.strip() for x in segs if x.text.strip()).strip(); print("RAW STT:",raw or "[METİN YOK]")
    if not raw:return
    q,changes=normalize(raw); print("SORU:",q); print("NORMAL:",", ".join(changes) if changes else "değişiklik yok")
    try:r=chat(q)
    except Exception as e: print("5016 CHAT ERROR:",type(e).__name__,e); return
    print("\nROUTING:"); print("symbol =",r.get("symbol")); print("intent =",r.get("intent")); print("mode   =",r.get("mode"))
    print("guard  =",json.dumps(r.get("guard"),ensure_ascii=False))
    ans=str(r.get("answer") or "").strip()
    print("\n=== TAM KANONİK CEVAP / AUDIT ===\n"+ans)
    short=spoken_summary(ans); print("\n=== KISA SESLİ SUNUM ===\n"+short)
    print("\nZİTAR konuşuyor 🔊"); speak(voice,short); print("TAMAMLANDI.")

if __name__=="__main__": main()
