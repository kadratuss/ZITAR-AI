#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Grounded Chat V2
Deterministic evidence extraction -> compact evidence packet -> local Qwen narrator
-> strict validation -> deterministic fallback.

READ ONLY. NO execution authority. NO real orders. NO V3 writes.
"""
import json, re, urllib.request, urllib.error, hashlib
from pathlib import Path
from datetime import datetime, timezone

B = Path(__file__).resolve().parent
CTX = B / "zitar_chat_context_v1_2.json"
MODEL = "qwen2.5:7b"
OLLAMA = "http://127.0.0.1:11434/api/chat"
PACKET_OUT = B / "zitar_chat_evidence_packet_v2.json"
AUDIT_OUT = B / "zitar_chat_last_audit_v2.json"

SECTIONS = ["[ZITAR_RESEARCH]","[MEMORY]","[EVENT_NEWS]","[INFERENCE]","[UNCERTAINTY]","[KANIT_OZETI]"]
FORBIDDEN = [
    r"\bsatın al\b", r"\balım fırsat", r"\bsatım fırsat", r"\byatırım tavsi",
    r"\bkesin yüksel", r"\bkesin düş", r"\bgaranti\b",
    r"haber(?:ler|in)?.{0,45}\betki(?:ledi|ler|si|sini|li)\b",
    r"\bnedensellik\b.{0,40}\bvar\b"
]

def walk_scalars(x, path="root", out=None):
    if out is None: out=[]
    if isinstance(x, dict):
        for k,v in x.items(): walk_scalars(v, f"{path}.{k}", out)
    elif isinstance(x, list):
        for i,v in enumerate(x): walk_scalars(v, f"{path}[{i}]", out)
    elif isinstance(x, (str,int,float,bool)) or x is None:
        out.append((path,x))
    return out

def prune(obj, max_depth=5, max_list=8, depth=0):
    if depth >= max_depth:
        if isinstance(obj,(dict,list)): return "[TRUNCATED]"
        return obj
    if isinstance(obj, dict):
        keep={}
        preferred=("symbol","pair","timeframe","horizon","trend","direction","view","label","status",
                   "confidence","data_confidence","agreement","conflict","conflicts","rsi","momentum",
                   "volume","atr","version","change","reason","title","event_type","timing_class",
                   "pump_confirmed","buy_signal","anomaly","published_at","generated_utc","timestamp")
        for k in preferred:
            if k in obj: keep[k]=prune(obj[k],max_depth,max_list,depth+1)
        for k,v in obj.items():
            if k not in keep and len(keep)<18:
                keep[k]=prune(v,max_depth,max_list,depth+1)
        return keep
    if isinstance(obj,list):
        return [prune(v,max_depth,max_list,depth+1) for v in obj[:max_list]]
    return obj

def build_packet(ctx, symbol):
    sc=ctx["symbol_context"][symbol]
    packet={
      "schema":"ZITAR_EVIDENCE_PACKET_V2",
      "symbol":symbol,
      "built_utc":datetime.now(timezone.utc).isoformat(),
      "source_context_generated_utc":ctx.get("generated_utc"),
      "authority":{"execution":False,"real_orders":False,"v3_write":False},
      "research":prune(sc.get("ZITAR_RESEARCH",[]), max_list=4),
      "memory":prune(sc.get("MEMORY",[]), max_list=4),
      "opinion_history":prune(sc.get("AI_OPINION_HISTORY",[]), max_list=4),
      "event_news":prune(sc.get("EVENT_NEWS_EVIDENCE",[]), max_list=6),
      "news_market_join":prune(sc.get("NEWS_MARKET_JOIN",[]), max_list=6),
      "integrity":[
        "Temporal association is not causation.",
        "Anomaly is not pump.",
        "Pump is not BUY.",
        "Data confidence is not predictive confidence.",
        "Historical/observational evidence is not proof of future profitability."
      ]
    }
    return packet

def evidence_numbers(packet):
    nums=set()
    for _,v in walk_scalars(packet):
        if isinstance(v,(int,float)) and not isinstance(v,bool):
            nums.add(round(float(v),8))
        elif isinstance(v,str):
            for m in re.findall(r"(?<![\w])[-+]?\d+(?:[.,]\d+)?",v):
                try: nums.add(round(float(m.replace(",",".")),8))
                except: pass
    # harmless structural numbers / model name / labels
    nums.update({1.0,2.0,4.0,5.0,7.0,14.0,15.0,20.0,21.0,26.0,30.0,50.0,60.0})
    return nums

def response_numbers(ans):
    vals=[]
    for m in re.findall(r"(?<![\w])[-+]?\d+(?:[.,]\d+)?\s*%?",ans):
        raw=m.strip().replace("%","").replace(",",".")
        try: vals.append(round(float(raw),8))
        except: pass
    return vals

SYSTEM = """Sen ZİTAR'ın yerel READ-ONLY araştırma anlatıcısısın.
Sana verilen EVIDENCE_PACKET dışındaki ZİTAR verilerini ASLA üretme.
Genel piyasa rakamı, tipik yüzde, fiyat, RSI, tarih veya istatistik uydurma.
Haber ile fiyat arasında nedensellik kurma; yalnız packet'teki zamansal gözlemi aktar.
BUY/SELL tavsiyesi, fırsat, emir veya portföy tahsisi verme.
Data confidence'ı tahmin güveni gibi yorumlama.
Tam olarak şu başlıkları, bu sırayla kullan:
[ZITAR_RESEARCH]
[MEMORY]
[EVENT_NEWS]
[INFERENCE]
[UNCERTAINTY]
[KANIT_OZETI]
Bir bölüm için kanıt yoksa 'Yetersiz kanıt.' yaz.
INFERENCE bölümünde yalnız packet'ten mantıksal olarak çıkan, ihtiyatlı sentezi yaz.
UNCERTAINTY bölümünde çelişki, örneklem ve nedensellik sınırlamalarını belirt.
Kısa ve somut Türkçe kullan."""

def call_qwen(packet, question):
    prompt="SORU:\n"+question+"\n\nEVIDENCE_PACKET:\n"+json.dumps(packet,ensure_ascii=False,separators=(",",":"))
    body=json.dumps({"model":MODEL,"stream":False,
      "messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],
      "options":{"temperature":0.0}},ensure_ascii=False).encode("utf-8")
    req=urllib.request.Request(OLLAMA,data=body,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=180) as r:
        return ((json.loads(r.read().decode("utf-8")).get("message") or {}).get("content") or "").strip()

def validate(ans, packet):
    reasons=[]
    pos=[ans.find(h) for h in SECTIONS]
    if any(p<0 for p in pos): reasons.append("MISSING_REQUIRED_SECTION")
    elif pos != sorted(pos): reasons.append("SECTION_ORDER")
    for pat in FORBIDDEN:
        if re.search(pat,ans,re.I|re.S): reasons.append("FORBIDDEN_LANGUAGE:"+pat)
    allowed=evidence_numbers(packet)
    suspicious=[]
    for n in response_numbers(ans):
        if n not in allowed:
            # years can be narrator formatting if packet contains same year as timestamp; otherwise catch.
            suspicious.append(n)
    if suspicious: reasons.append("UNSUPPORTED_NUMBERS:"+",".join(map(str,sorted(set(suspicious))[:20])))
    return reasons

def summarize_items(items, fallback="Yetersiz kanıt."):
    if not items: return fallback
    # Deterministic, source-faithful compact scalar preview; no invented interpretation.
    bits=[]
    for rec in items[:2]:
        d=rec.get("data",rec) if isinstance(rec,dict) else rec
        if isinstance(d,dict):
            for k in ("view","label","direction","trend","agreement","confidence","data_confidence",
                      "version","change","reason","timing_class","event_type","title"):
                if k in d and d[k] not in (None,"",[],{}):
                    bits.append(f"{k}={d[k]}")
        if len(bits)>=8: break
    return "; ".join(bits[:8]) if bits else "Kayıt mevcut; güvenli özet için ham kanıta başvurulmalı."

def fallback(packet):
    return f"""[ZITAR_RESEARCH]
{summarize_items(packet.get("research",[]))}

[MEMORY]
{summarize_items(packet.get("memory",[]))} Opinion/history: {summarize_items(packet.get("opinion_history",[]))}

[EVENT_NEWS]
{summarize_items(packet.get("event_news",[]))} Haber-fiyat ilişkisi yalnız zamansal gözlem olarak ele alınır.

[INFERENCE]
Mevcut kanıtlar tek başına işlem yönü veya gelecekteki getiri sonucu üretmek için yeterli değildir.

[UNCERTAINTY]
Zamansal birliktelik nedensellik değildir. Veri güveni tahmin güveni değildir. Çelişkili veya sınırlı kanıt varsa korunmalıdır.

[KANIT_OZETI]
Kaynaklar: ZİTAR Research, versioned Memory/Opinion, Event/News evidence. Execution authority yok; gerçek emir yok."""

def main():
    if not CTX.exists(): raise SystemExit("Missing zitar_chat_context_v1_2.json")
    ctx=json.loads(CTX.read_text(encoding="utf-8"))
    symbol=input("Sembol [BTCTRY]: ").strip().upper() or "BTCTRY"
    if symbol not in ctx.get("symbol_context",{}): raise SystemExit(f"Unknown symbol: {symbol}")
    question=input("Sorun: ").strip()
    if not question: raise SystemExit("Question required")

    packet=build_packet(ctx,symbol)
    PACKET_OUT.write_text(json.dumps(packet,ensure_ascii=False,indent=2),encoding="utf-8")

    qwen_error=None
    try:
        raw=call_qwen(packet,question)
        reasons=validate(raw,packet)
    except Exception as e:
        raw=""
        reasons=["QWEN_ERROR"]
        qwen_error=str(e)

    if reasons:
        final=fallback(packet)
        mode="DETERMINISTIC_FALLBACK"
    else:
        final=raw
        mode="QWEN_GROUNDED_PASS"

    audit={
      "engine":"ZITAR_GROUNDED_CHAT_V2","utc":datetime.now(timezone.utc).isoformat(),
      "symbol":symbol,"model":MODEL,"mode":mode,"qwen_validation_reasons":reasons,
      "qwen_error":qwen_error,"execution_authority":False,"real_orders":False,"v3_write":False,
      "packet_sha256":hashlib.sha256(PACKET_OUT.read_bytes()).hexdigest()
    }
    AUDIT_OUT.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")

    print("\n"+"="*118)
    print(f"ZİTAR GROUNDED CHAT V2 | {symbol} | {mode}")
    print("EXECUTION AUTHORITY: NO | REAL ORDERS: NO | V3 WRITE: NO")
    print("="*118)
    print(final)
    print("-"*118)
    print("QWEN VALIDATION :", "PASS" if not reasons else "BLOCKED")
    print("BLOCK REASONS   :", reasons or "NONE")
    print("EVIDENCE PACKET :", PACKET_OUT.name)
    print("AUDIT FILE      :", AUDIT_OUT.name)
    print("="*118)

if __name__=="__main__":
    main()
