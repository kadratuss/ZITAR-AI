#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZİTAR Chat Qwen Bridge V1 - grounded local narrator, NO execution authority."""
import json, urllib.request, urllib.error
from pathlib import Path

B=Path(__file__).resolve().parent
CTX=B/"zitar_chat_context_v1_2.json"
OLLAMA="http://127.0.0.1:11434/api/chat"
MODEL="qwen2.5:7b"

SYSTEM="""Sen ZİTAR'ın yerel araştırma anlatıcısısın.
Yalnız verilen ZİTAR CONTEXT içindeki sistem-özel olguları gerçek kabul et.
Genel bilgiyi kullanırsan [GENERAL_KNOWLEDGE] diye açıkça etiketle.
Çıkarımlarını [INFERENCE], belirsizlikleri [UNCERTAINTY] olarak etiketle.
Araştırma verilerini [ZITAR_RESEARCH], hafıza/geçmişi [MEMORY], güncel artifact verisini [LIVE_DATA] etiketiyle belirt.
BUY/SELL emri, portföy tahsisi veya işlem talimatı üretme.
Veri güvenini kârlılık/prediction güveni gibi sunma.
Haber-zaman birlikteliğini nedensellik diye sunma.
Çelişkileri gizleme. Kanıt yetersizse açıkça 'yetersiz kanıt' de.
Senin execution authority'n yok; gerçek emir veremezsin.
Türkçe, net ve gereksiz uzun olmayan cevap ver."""

def compact(x,limit=45000):
    s=json.dumps(x,ensure_ascii=False,separators=(",",":"))
    return s if len(s)<=limit else s[:limit]+"\n[UNCERTAINTY] CONTEXT_TRUNCATED"

def main():
    if not CTX.exists():raise SystemExit("Missing zitar_chat_context_v1_2.json")
    x=json.loads(CTX.read_text(encoding="utf-8"))
    symbol=(input("Sembol [BTCTRY]: ").strip().upper() or "BTCTRY")
    if symbol not in x.get("symbol_context",{}):raise SystemExit(f"Unknown symbol: {symbol}")
    q=input("Sorun: ").strip()
    if not q:raise SystemExit("Question required")

    evidence={
      "symbol":symbol,
      "generated_utc":x.get("generated_utc"),
      "authority":x.get("authority"),
      "context":x["symbol_context"][symbol],
      "integrity_rules":x.get("rules",[])
    }
    user=f"""SORU: {q}

ZİTAR CONTEXT:
{compact(evidence)}

Cevabın sonunda kısa bir 'Kanıt özeti' ver ve kullandığın kategorileri yaz.
Bu context dışında ZİTAR'a özgü veri uydurma."""

    payload=json.dumps({"model":MODEL,"stream":False,
                        "messages":[{"role":"system","content":SYSTEM},
                                    {"role":"user","content":user}],
                        "options":{"temperature":0.2}},ensure_ascii=False).encode("utf-8")
    req=urllib.request.Request(OLLAMA,data=payload,headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=180) as r:
            out=json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise SystemExit(f"Ollama connection failed: {e}")
    ans=((out.get("message") or {}).get("content") or "").strip()
    if not ans:raise SystemExit("Empty model response")

    print("\n"+"="*110)
    print(f"ZİTAR CHAT V1 | {symbol} | MODEL {MODEL}")
    print("READ-ONLY NARRATOR | EXECUTION AUTHORITY: NO | REAL ORDERS: NO")
    print("="*110)
    print(ans)
    print("="*110)

if __name__=="__main__":main()
