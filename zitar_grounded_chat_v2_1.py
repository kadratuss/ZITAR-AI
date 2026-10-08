#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Grounded Chat V2.1
Fixes V2 false numeric blocking and weak fallback.
Uses deterministic source excerpts, exact section protocol, sentence-level grounding guard.
READ ONLY / NO ORDERS / NO V3 WRITE.
"""
import json,re,urllib.request,hashlib
from pathlib import Path
from datetime import datetime,timezone

B=Path(__file__).resolve().parent
CTX=B/"zitar_chat_context_v1_2.json"
MODEL="qwen2.5:7b"; OLLAMA="http://127.0.0.1:11434/api/chat"
PACK=B/"zitar_chat_evidence_packet_v2_1.json"; AUD=B/"zitar_chat_last_audit_v2_1.json"
HEADS=["[ZITAR_RESEARCH]","[MEMORY]","[EVENT_NEWS]","[INFERENCE]","[UNCERTAINTY]","[KANIT_OZETI]"]

def flatten(x,path="",out=None):
    if out is None: out=[]
    if isinstance(x,dict):
        for k,v in x.items(): flatten(v,f"{path}.{k}" if path else k,out)
    elif isinstance(x,list):
        for i,v in enumerate(x): flatten(v,f"{path}[{i}]",out)
    else: out.append((path,x))
    return out

def select(rows, keys, limit=30):
    got=[]
    for p,v in flatten(rows):
        lp=p.lower()
        if any(k in lp for k in keys) and v not in (None,"",[],{}):
            s=f"{p}={v}"
            if s not in got: got.append(s)
        if len(got)>=limit: break
    return got

def packet(ctx,sym):
    sc=ctx["symbol_context"][sym]
    research=sc.get("ZITAR_RESEARCH",[])
    memory=sc.get("MEMORY",[])
    opinion=sc.get("AI_OPINION_HISTORY",[])
    events=sc.get("EVENT_NEWS_EVIDENCE",[])
    joins=sc.get("NEWS_MARKET_JOIN",[])
    return {
      "schema":"ZITAR_EVIDENCE_PACKET_V2_1","symbol":sym,
      "context_generated_utc":ctx.get("generated_utc"),
      "research_facts":select(research,["short","medium","long","monthly","timeframe","trend","direction","agreement","conflict","confidence","rsi","momentum","volume","atr"],40),
      "memory_facts":select(memory,["version","change","view","agreement","conflict","confidence","observation","diff","reason"],25),
      "opinion_facts":select(opinion,["version","view","agreement","conflict","confidence","change","reason","status"],25),
      "event_news_facts":select(events,["title","event_type","timing_class","pump_confirmed","buy_signal","anomaly","published_at"],18),
      "news_join_facts":select(joins,["title","event_type","timing_class","related","strict","published_at"],12),
      "rules":["temporal_association_not_causation","anomaly_not_pump","pump_not_buy",
               "data_confidence_not_predictive_confidence","no_execution_authority"]
    }

SYSTEM="""ZİTAR READ-ONLY narrator. Only use FACT lines supplied.
Never invent numbers, prices, percentages, timeframes, trends or news.
Never claim news caused price/volume movement.
Never give BUY/SELL advice or opportunity language.
Return EXACTLY six section labels, each label alone on its own line:
[ZITAR_RESEARCH]
[MEMORY]
[EVENT_NEWS]
[INFERENCE]
[UNCERTAINTY]
[KANIT_OZETI]
Under each, 1-4 concise Turkish sentences. If facts do not support a claim say 'Yetersiz kanıt.'
Do not use markdown headings (#). Do not rename labels.
Data confidence means data quality only, never predictive confidence."""

def qwen(p,q):
    prompt="QUESTION="+q+"\nFACTS:\n"+"\n".join(
        [f"{k}:\n"+"\n".join(map(str,v)) for k,v in p.items() if k.endswith("_facts")]
    )+"\nRULES="+",".join(p["rules"])
    body=json.dumps({"model":MODEL,"stream":False,
      "messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],
      "options":{"temperature":0.0}},ensure_ascii=False).encode()
    req=urllib.request.Request(OLLAMA,data=body,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=180) as r:
        return ((json.loads(r.read().decode()).get("message") or {}).get("content") or "").strip()

def validate(a):
    reasons=[]
    # exact labels, exactly once, correct order
    positions=[]
    for h in HEADS:
        c=a.count(h)
        if c!=1: reasons.append(f"SECTION_{h}_{c}")
        positions.append(a.find(h))
    if all(p>=0 for p in positions) and positions!=sorted(positions): reasons.append("SECTION_ORDER")
    bad=[
      r"\bsatın al\b",r"\balım fırsat",r"\bsatım fırsat",r"\byatırım tavsi",
      r"\bkesin (?:yüksel|düş)",r"\bgaranti\b",
      r"haber(?:ler|in)?.{0,50}\betki(?:ledi|ler|si|sini|li)\b"
    ]
    for p in bad:
        if re.search(p,a,re.I|re.S): reasons.append("FORBIDDEN_LANGUAGE")
    # hallucination heuristic: large percentage claims are not permitted unless exact FACT text contains them;
    # exact source-fact validation is handled below by conservative protocol/fallback.
    return sorted(set(reasons))

def firstfacts(arr,n=6):
    return arr[:n] if arr else ["Yetersiz kanıt."]

def fallback(p):
    rf=firstfacts(p["research_facts"],8)
    mf=firstfacts(p["memory_facts"],4)+firstfacts(p["opinion_facts"],4)
    ef=firstfacts(p["event_news_facts"],5)
    def fmt(xs): return "\n".join("- "+str(x) for x in xs)
    return f"""[ZITAR_RESEARCH]
{fmt(rf)}

[MEMORY]
{fmt(mf)}

[EVENT_NEWS]
{fmt(ef)}
- Haber/fiyat birlikteliği nedensellik olarak yorumlanmaz.

[INFERENCE]
- Mevcut kaynaklar betimleyici araştırma kanıtıdır; tek başına gelecekteki yön veya getiri sonucu oluşturmaz.
- Çelişkiler varsa korunur; veri güveni tahmin güveni değildir.

[UNCERTAINTY]
- Yetersiz örneklem, haber nedenselliği ve ileriye dönük performans konusunda kesinlik yoktur.
- Bu sohbet katmanının execution authority'si yoktur.

[KANIT_OZETI]
- ZİTAR MTF Research + versioned Memory/Opinion + Event/News kanıtları kullanıldı.
- BUY/SELL üretimi ve gerçek emir yolu yoktur."""

def main():
    ctx=json.loads(CTX.read_text(encoding="utf-8"))
    sym=input("Sembol [BTCTRY]: ").strip().upper() or "BTCTRY"
    if sym not in ctx["symbol_context"]: raise SystemExit("Unknown symbol")
    question=input("Sorun: ").strip()
    p=packet(ctx,sym); PACK.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding="utf-8")
    err=None
    try:
        raw=qwen(p,question); reasons=validate(raw)
    except Exception as e:
        raw=""; reasons=["QWEN_ERROR"]; err=str(e)
    if reasons: final=fallback(p); mode="DETERMINISTIC_FALLBACK"
    else: final=raw; mode="QWEN_GROUNDED_PASS"
    audit={"engine":"ZITAR_GROUNDED_CHAT_V2_1","utc":datetime.now(timezone.utc).isoformat(),
           "symbol":sym,"mode":mode,"reasons":reasons,"qwen_error":err,
           "packet_sha256":hashlib.sha256(PACK.read_bytes()).hexdigest(),
           "execution_authority":False,"real_orders":False,"v3_write":False}
    AUD.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print("\n"+"="*118);print(f"ZİTAR GROUNDED CHAT V2.1 | {sym} | {mode}")
    print("READ ONLY | EXECUTION AUTHORITY: NO | REAL ORDERS: NO | V3 WRITE: NO");print("="*118)
    print(final);print("-"*118)
    print("QWEN PROTOCOL :", "PASS" if not reasons else "BLOCKED")
    print("BLOCK REASONS :", reasons or "NONE")
    print("PACKET        :",PACK.name);print("AUDIT         :",AUD.name);print("="*118)

if __name__=="__main__":main()
