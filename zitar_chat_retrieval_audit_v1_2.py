#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZİTAR Chat Retrieval Audit V1.2 - validates Context V1.2 before Ollama/Qwen."""
import json
from pathlib import Path

B=Path(__file__).resolve().parent
CTX=B/"zitar_chat_context_v1_2.json"
S="BTCTRY"

def main():
    if not CTX.exists():raise SystemExit("Missing zitar_chat_context_v1_2.json")
    x=json.loads(CTX.read_text(encoding="utf-8"))
    sc=x.get("symbol_context",{}).get(S,{})
    checks=[]
    def ck(n,o,d):checks.append((n,bool(o),d))
    ck("ENGINE_V1_2",x.get("engine")=="ZITAR_CHAT_CONTEXT_V1_2",x.get("engine"))
    ck("SYMBOL_EXISTS",S in x.get("symbols",[]),S)
    for key in ("ZITAR_RESEARCH","MEMORY","AI_OPINION_HISTORY","EVENT_NEWS_EVIDENCE","NEWS_MARKET_JOIN"):
        v=sc.get(key,[])
        ck(key+"_PRESENT",isinstance(v,list) and len(v)>0,f"records={len(v) if isinstance(v,list) else 'invalid'}")
    rm=x.get("resolved_memory",{})
    ck("MEMORY_JSONL_21",rm.get("records_file")=="zitar_research_memory_v1.jsonl" and rm.get("records")==21,
       f"file={rm.get('records_file')} records={rm.get('records')}")
    a=x.get("authority",{})
    ck("NO_EXECUTION_AUTHORITY",a.get("execution_authority") is False,str(a.get("execution_authority")))
    ck("NO_REAL_ORDERS",a.get("real_orders") is False,str(a.get("real_orders")))
    ck("NO_V3_WRITE",a.get("v3_write") is False,str(a.get("v3_write")))
    ck("NO_SCHEDULER_MUTATION",a.get("scheduler_mutation") is False,str(a.get("scheduler_mutation")))
    ck("LLM_NOT_CALLED",a.get("llm_called") is False,str(a.get("llm_called")))

    print("="*116)
    print("ZITAR CHAT RETRIEVAL AUDIT V1.2 - BTCTRY PRE-QWEN GATE")
    print("="*116)
    for n,o,d in checks:print(f"{'PASS' if o else 'FAIL':<5} {n:<38} {d}")
    print("-"*116)
    print(f"RESULT: {sum(o for _,o,_ in checks)}/{len(checks)} PASS")
    print("NEXT: only after full PASS, connect local Ollama/Qwen as a non-authoritative narrator.")
    print("RULE: GROUNDED RETRIEVAL != TRADING AUTHORITY.")
    print("="*116)
    if not all(o for _,o,_ in checks):raise SystemExit(1)

if __name__=="__main__":main()
