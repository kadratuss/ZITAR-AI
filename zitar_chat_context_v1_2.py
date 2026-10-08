#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZİTAR Chat Context Builder V1.2 - full memory JSONL + pair-aware news join retrieval."""
import json, os, hashlib
from datetime import datetime, timezone
from pathlib import Path

B=Path(__file__).resolve().parent
OUT=B/"zitar_chat_context_v1_2.json"

FILES={
 "mtf":B/"zitar_mtf_research_v2.json",
 "opinion":B/"zitar_research_opinion_v1.json",
 "event_radar":B/"zitar_event_news_radar_v2_4.json",
 "news":B/"zitar_news_intelligence_v1_1.json",
 "news_market_join":B/"zitar_news_market_join_v1_1.json",
}
MEMJSONL=B/"zitar_research_memory_v1.jsonl"
MEMINDEX=B/"zitar_research_memory_index_v1.json"

ASSET_PAIR={"BTC":"BTCTRY","ETH":"ETHTRY","SOL":"SOLTRY","XRP":"XRPTRY","DOGE":"DOGETRY",
"AVAX":"AVAXTRY","NEAR":"NEARTRY","PEPE":"PEPETRY","TRUMP":"TRUMPTRY","PENGU":"PENGUTRY",
"SAGA":"SAGATRY","COTI":"COTITRY","MINA":"MINATRY","MUBARAK":"MUBARAKTRY","PHA":"PHATRY",
"ENA":"ENATRY","FORM":"FORMTRY","G":"GTRY","TST":"TSTTRY","USDT":"USDTTRY"}

def loadj(p):
    try:
        x=json.loads(p.read_text(encoding="utf-8"))
        return x if isinstance(x,(dict,list)) else None
    except:return None
def load_jsonl(p):
    out=[]
    if not p.exists():return out
    for ln in p.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            try:out.append(json.loads(ln))
            except:pass
    return out
def find(obj,s):
    out=[]
    def w(x,path="root"):
        if isinstance(x,dict):
            z=x.get("symbol") or x.get("pair")
            if str(z).upper()==s:out.append({"path":path,"data":x})
            for k,v in x.items():
                if isinstance(v,(dict,list)):w(v,f"{path}.{k}")
        elif isinstance(x,list):
            for i,v in enumerate(x):
                if isinstance(v,(dict,list)):w(v,f"{path}[{i}]")
    w(obj);return out
def join_for_symbol(join,symbol):
    out=[]
    for i,u in enumerate(join.get("units",[]) if isinstance(join,dict) else []):
        pair=u.get("pair") or u.get("symbol")
        if pair and str(pair).upper()==symbol:out.append({"path":f"root.units[{i}]","data":u});continue
        asset=str(u.get("asset","")).upper()
        if ASSET_PAIR.get(asset)==symbol:out.append({"path":f"root.units[{i}]","data":u})
    return out
def atomic(p,o):
    q=p.with_suffix(p.suffix+".tmp")
    with q.open("w",encoding="utf-8") as h:
        json.dump(o,h,ensure_ascii=False,indent=2);h.flush()
        try:os.fsync(h.fileno())
        except OSError:pass
    q.replace(p)

def main():
    d={k:loadj(p) for k,p in FILES.items()}
    memory=load_jsonl(MEMJSONL)
    index=loadj(MEMINDEX)
    syms=set()
    for obj in (d["mtf"],d["opinion"],memory):
        def c(x):
            if isinstance(x,dict):
                s=x.get("symbol") or x.get("pair")
                if isinstance(s,str) and s.upper().endswith("TRY"):syms.add(s.upper())
                for v in x.values():
                    if isinstance(v,(dict,list)):c(v)
            elif isinstance(x,list):
                for v in x:c(v)
        c(obj)
    ctx={}
    for s in sorted(syms):
        ctx[s]={
          "ZITAR_RESEARCH":find(d["mtf"],s),
          "MEMORY":find(memory,s),
          "AI_OPINION_HISTORY":find(d["opinion"],s),
          "EVENT_NEWS_EVIDENCE":find(d["event_radar"],s),
          "NEWS_MARKET_JOIN":join_for_symbol(d["news_market_join"],s),
        }
    packet={"engine":"ZITAR_CHAT_CONTEXT_V1_2","generated_utc":datetime.now(timezone.utc).isoformat(),
      "mode":"READ_ONLY_GROUNDING",
      "authority":{"execution_authority":False,"real_orders":False,"v3_write":False,
                   "scheduler_mutation":False,"source_db_write":False,"llm_called":False},
      "resolved_memory":{"records_file":MEMJSONL.name if MEMJSONL.exists() else None,
                         "records":len(memory),"index_file":MEMINDEX.name if MEMINDEX.exists() else None},
      "source_availability":{**{k:(v is not None) for k,v in d.items()},
                             "research_memory_records":bool(memory),"research_memory_index":index is not None},
      "symbols":sorted(syms),"symbol_context":ctx,
      "rules":["Full JSONL is retrieval content; index is metadata only.",
               "Asset-only news join units are mapped to explicit TRY pairs deterministically.",
               "No BUY/SELL conversion.","No causal inference from news timing.",
               "Expose uncertainty.","Chat has no execution authority."]}
    atomic(OUT,packet)
    btc=ctx.get("BTCTRY",{})
    print("="*118)
    print("ZITAR CHAT CONTEXT BUILDER V1.2 - MEMORY RECORD + NEWS JOIN FIX")
    print("="*118)
    print("READ ONLY | LLM: NO | V3 WRITE: NO | REAL ORDERS: NO")
    print("MEMORY RECORD FILE :",MEMJSONL.name if MEMJSONL.exists() else "MISSING")
    print("MEMORY RECORDS     :",len(memory))
    print("MEMORY INDEX FILE  :",MEMINDEX.name if MEMINDEX.exists() else "MISSING")
    print("SYMBOLS            :",len(syms))
    print("-"*118)
    print("BTCTRY RETRIEVAL PREVIEW")
    for k,v in btc.items():print(f"  {k:<26}: {len(v)}")
    print("CONTEXT JSON       :",OUT)
    print("="*118)
    if not memory:raise SystemExit(1)

if __name__=="__main__":main()
