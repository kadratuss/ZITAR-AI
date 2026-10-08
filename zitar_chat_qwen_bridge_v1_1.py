#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZİTAR Chat Qwen Bridge V1.1 - structured grounded answer + output guard."""
import json, urllib.request, urllib.error, re
from pathlib import Path

B=Path(__file__).resolve().parent
CTX=B/"zitar_chat_context_v1_2.json"
OLLAMA="http://127.0.0.1:11434/api/chat"
MODEL="qwen2.5:7b"

SYSTEM="""Sen ZİTAR'ın READ-ONLY araştırma anlatıcısısın. İşlem motoru değilsin.
Sadece verilen CONTEXT içindeki ZİTAR'a özgü olguları kullan.
Asla haberin fiyatı 'etkilediğini' veya hacim oranının 'etkiyi gösterdiğini' söyleme; yalnız zamansal birliktelik de.
Asla BUY/SELL fırsatı, tavsiye, sinyal veya işlem talimatı üretme.
pump_confirmed ve buy_signal alanları varsa bunları yalnız veri alanı olarak aktar; otorite verme.
data confidence = veri kalitesi; tahmin/kârlılık güveni değildir.
Çelişkileri ve eksik kanıtı açıkça söyle.
Yanıt Türkçe olmalı ve TAM OLARAK şu 6 başlığı kullanmalı:
[ZITAR_RESEARCH]
[MEMORY]
[EVENT_NEWS]
[INFERENCE]
[UNCERTAINTY]
[KANIT_OZETI]
Her başlık altında yalnız ilgili kanıtı anlat. Kaynakta yoksa 'Yetersiz kanıt' yaz.
GENERAL KNOWLEDGE kullanma."""

FORBIDDEN=[
 r"\bsatın al\b",r"\balım fırsat",r"\bsatım fırsat",r"\byatırım tavsi",
 r"\bhaber.*etki(?:ledi|sini|si)\b",r"\bhacim.*etki(?:li|yi|si)\b"
]

def compact(x,limit=50000):
    s=json.dumps(x,ensure_ascii=False,separators=(",",":"))
    return s if len(s)<=limit else s[:limit]+"\nCONTEXT_TRUNCATED"

def call(messages):
    data=json.dumps({"model":MODEL,"stream":False,"messages":messages,
                     "options":{"temperature":0.1}},ensure_ascii=False).encode()
    req=urllib.request.Request(OLLAMA,data=data,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=180) as r:
        return ((json.loads(r.read().decode()).get("message") or {}).get("content") or "").strip()

def validate(ans):
    heads=["[ZITAR_RESEARCH]","[MEMORY]","[EVENT_NEWS]","[INFERENCE]","[UNCERTAINTY]","[KANIT_OZETI]"]
    missing=[h for h in heads if h not in ans]
    bad=[p for p in FORBIDDEN if re.search(p,ans,re.I|re.S)]
    return missing,bad

def main():
    x=json.loads(CTX.read_text(encoding="utf-8"))
    symbol=input("Sembol [BTCTRY]: ").strip().upper() or "BTCTRY"
    if symbol not in x.get("symbol_context",{}):raise SystemExit("Unknown symbol")
    q=input("Sorun: ").strip()
    sc=x["symbol_context"][symbol]
    evidence={"symbol":symbol,"context_generated_utc":x.get("generated_utc"),
              "research":sc.get("ZITAR_RESEARCH",[]),"memory":sc.get("MEMORY",[]),
              "opinion_history":sc.get("AI_OPINION_HISTORY",[]),
              "event_news":sc.get("EVENT_NEWS_EVIDENCE",[]),
              "news_market_join":sc.get("NEWS_MARKET_JOIN",[])}
    prompt=f"""SORU: {q}
CONTEXT:
{compact(evidence)}
Önce MTF araştırmayı ve memory/opinion geçmişini cevapla; event/news yalnız destekleyici bağlamdır.
Haber ile fiyat arasında nedensellik kurma. Veride yoksa uydurma."""
    try: ans=call([{"role":"system","content":SYSTEM},{"role":"user","content":prompt}])
    except urllib.error.URLError as e:raise SystemExit(f"Ollama failed: {e}")
    missing,bad=validate(ans)
    status="PASS" if not missing and not bad else "FAIL"
    print("\n"+"="*112)
    print(f"ZİTAR CHAT QWEN BRIDGE V1.1 | {symbol} | OUTPUT GUARD: {status}")
    print("READ ONLY | EXECUTION AUTHORITY: NO | REAL ORDERS: NO")
    print("="*112)
    print(ans)
    print("-"*112)
    print("MISSING REQUIRED SECTIONS:",missing or "NONE")
    print("FORBIDDEN LANGUAGE HITS :",len(bad))
    print("QUALITY GATE            :",status)
    print("="*112)
    if status!="PASS":raise SystemExit(2)

if __name__=="__main__":main()
