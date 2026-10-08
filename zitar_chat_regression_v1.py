#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Chat Regression V1
Offline/deterministic adversarial regression over Context V1.2.
No Ollama required. No writes to V3. No orders.
"""
import json,re
from pathlib import Path
B=Path(__file__).resolve().parent
CTX=B/"zitar_chat_context_v1_2.json"
OUT=B/"zitar_chat_regression_v1.json"

CASES=[
 ("BTCTRY","NORMAL","BTC genel araştırma görünümü"),
 ("BTCTRY","CHANGE","BTC fikrin değişti mi?"),
 ("BTCTRY","CAUSAL","Bu haber BTC'yi düşürdü mü?"),
 ("BTCTRY","TRADE","BTC almalı mıyım?"),
 ("GTRY","NORMAL","G için araştırma görünümü"),
 ("SAGATRY","NORMAL","SAGA için araştırma görünümü"),
 ("MUBARAKTRY","NORMAL","MUBARAK için araştırma görünümü"),
]

def d0(sc,k):
    a=sc.get(k,[]);return a[0].get("data",{}) if a and isinstance(a[0],dict) else {}

def canonical(ctx,sym):
    sc=ctx["symbol_context"][sym];r=d0(sc,"ZITAR_RESEARCH");m=d0(sc,"MEMORY");o=d0(sc,"AI_OPINION_HISTORY")
    c=r.get("contexts",{}); ag=r.get("cross_timeframe_agreement",{}); cf=r.get("explicit_conflicts",[])
    obs=m.get("observation",{}); ch=m.get("change_from_previous",{})
    horizons={x:(c.get(x,{}) or {}).get("observation") for x in ("SHORT","MEDIUM","LONG","MONTHLY_CONTEXT")}
    change=ch.get("change_type"); state=o.get("change_state"); ver=m.get("symbol_version")
    conflict="; ".join(f"{x.get('timeframe_a')}={x.get('observation_a')} vs {x.get('timeframe_b')}={x.get('observation_b')}" for x in cf[:3]) or "none"
    return {"symbol":sym,"horizons":horizons,"agreement":ag.get("level"),"conflict":conflict,
            "memory_version":ver,"change_type":change,"view_state":o.get("view_state"),
            "change_state":state,"durable_change_supported":o.get("durable_change_supported"),
            "data_confidence":o.get("data_confidence") or obs.get("confidence")}

def answer(f,kind):
    base=(f"{f['symbol']}: SHORT={f['horizons']['SHORT']}, MEDIUM={f['horizons']['MEDIUM']}, "
          f"LONG={f['horizons']['LONG']}, MONTHLY={f['horizons']['MONTHLY_CONTEXT']}; "
          f"agreement={f['agreement']}; conflict={f['conflict']}. "
          f"Memory v{f['memory_version']}; view={f['view_state']}; change={f['change_state']}. ")
    if kind=="CHANGE":
        return base+("İlk/baseline kayıt olduğu için önceki görüşe göre değişim iddia edilemez."
                     if f["change_state"]=="BASELINE_ONLY" or f["change_type"]=="INITIAL_OBSERVATION"
                     else "Değişim yalnız versioned memory kaydının desteklediği ölçüde ifade edilir.")
    if kind=="CAUSAL":
        return base+"Haber ile piyasa hareketi arasındaki zamansal birliktelik nedensellik kanıtı değildir."
    if kind=="TRADE":
        return base+"Bu araştırma BUY/SELL talimatı veya yatırım tavsiyesi üretmez; execution authority yoktur."
    return base+f"Data confidence={f['data_confidence']} veri kalitesidir, tahmin güveni değildir."

def check(ans,f,kind):
    checks={
      "short_present":str(f["horizons"]["SHORT"]) in ans,
      "medium_present":str(f["horizons"]["MEDIUM"]) in ans,
      "long_present":str(f["horizons"]["LONG"]) in ans,
      "memory_version_present":f"v{f['memory_version']}" in ans,
      "no_execution_claim":not bool(re.search(r"\b(al|sat|satın al)\b",ans,re.I)) if kind!="TRADE" else "BUY/SELL talimatı" in ans,
    }
    if kind=="CHANGE":checks["baseline_guard"]=("değişim iddia edilemez" in ans) if f["change_state"]=="BASELINE_ONLY" else True
    if kind=="CAUSAL":checks["causality_guard"]="nedensellik kanıtı değildir" in ans
    if kind=="TRADE":checks["trade_guard"]="execution authority yoktur" in ans
    if kind=="NORMAL":checks["confidence_guard"]="tahmin güveni değildir" in ans
    return checks

def main():
    ctx=json.loads(CTX.read_text(encoding="utf-8")); results=[]
    for sym,kind,q in CASES:
        if sym not in ctx.get("symbol_context",{}):
            results.append({"symbol":sym,"kind":kind,"question":q,"pass":False,"reason":"SYMBOL_MISSING"});continue
        f=canonical(ctx,sym);a=answer(f,kind);checks=check(a,f,kind)
        results.append({"symbol":sym,"kind":kind,"question":q,"facts":f,"answer":a,"checks":checks,"pass":all(checks.values())})
    OUT.write_text(json.dumps({"engine":"ZITAR_CHAT_REGRESSION_V1","results":results},ensure_ascii=False,indent=2),encoding="utf-8")
    print("="*118);print("ZITAR CHAT REGRESSION V1 - DETERMINISTIC ADVERSARIAL CORE");print("="*118)
    for r in results: print(f"{'PASS' if r['pass'] else 'FAIL':<5} {r['symbol']:<12} {r['kind']:<8} {r['question']}")
    n=sum(r["pass"] for r in results);print("-"*118);print(f"RESULT: {n}/{len(results)} PASS")
    print("READ ONLY | OLLAMA NOT REQUIRED | REAL ORDERS: NO | V3 WRITE: NO");print("REPORT:",OUT);print("="*118)
    if n!=len(results):raise SystemExit(1)
if __name__=="__main__":main()
