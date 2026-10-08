#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZİTAR Chat Retrieval Audit V1 - symbol-scoped grounding audit."""
import json
from pathlib import Path

B=Path(__file__).resolve().parent
CTX=B/"zitar_chat_context_v1_1.json"
SYMBOL="BTCTRY"

def main():
    if not CTX.exists(): raise SystemExit("Missing zitar_chat_context_v1_1.json")
    x=json.loads(CTX.read_text(encoding="utf-8"))
    sc=x.get("symbol_context",{}).get(SYMBOL)
    if not isinstance(sc,dict): raise SystemExit(f"{SYMBOL} context missing")

    checks=[]
    def ck(name,ok,detail):checks.append((name,bool(ok),detail))
    ck("SYMBOL_EXISTS",SYMBOL in x.get("symbols",[]),SYMBOL)
    ck("MTF_PRESENT",len(sc.get("ZITAR_RESEARCH",[]))>0,f"records={len(sc.get('ZITAR_RESEARCH',[]))}")
    ck("MEMORY_PRESENT",len(sc.get("MEMORY",[]))>0,f"records={len(sc.get('MEMORY',[]))}")
    ck("OPINION_PRESENT",len(sc.get("AI_OPINION_HISTORY",[]))>0,f"records={len(sc.get('AI_OPINION_HISTORY',[]))}")
    ck("EVENT_NEWS_PRESENT",len(sc.get("EVENT_NEWS_EVIDENCE",[]))>0,f"records={len(sc.get('EVENT_NEWS_EVIDENCE',[]))}")
    auth=x.get("authority",{})
    ck("NO_EXECUTION_AUTHORITY",auth.get("execution_authority") is False,str(auth.get("execution_authority")))
    ck("NO_REAL_ORDERS",auth.get("real_orders") is False,str(auth.get("real_orders")))
    ck("NO_V3_WRITE",auth.get("v3_write") is False,str(auth.get("v3_write")))
    ck("LLM_NOT_CALLED",auth.get("llm_called") is False,str(auth.get("llm_called")))

    print("="*112)
    print("ZITAR CHAT RETRIEVAL AUDIT V1 - BTCTRY")
    print("="*112)
    for n,ok,d in checks: print(f"{'PASS' if ok else 'FAIL':<5} {n:<32} {d}")
    print("-"*112)
    print("RETRIEVED SECTIONS:")
    for k,v in sc.items(): print(f"  {k:<26}: {len(v) if isinstance(v,list) else 'N/A'}")
    print("-"*112)
    print(f"RESULT: {sum(o for _,o,_ in checks)}/{len(checks)} PASS")
    print("RULE: RETRIEVAL != INFERENCE; CHAT STILL HAS NO EXECUTION AUTHORITY.")
    print("="*112)
    if not all(o for _,o,_ in checks): raise SystemExit(1)

if __name__=="__main__":main()
