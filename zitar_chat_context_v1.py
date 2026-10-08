#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Chat Context Builder V1
Master Plan 13/26 - Grounding foundation.

Builds a READ-ONLY context packet for ZİTAR Chat from existing artifacts.
NO LLM call yet. NO orders. NO V3 writes. NO state mutation.
"""
import json, os, hashlib
from datetime import datetime, timezone
from pathlib import Path

B=Path(__file__).resolve().parent
OUT=B/"zitar_chat_context_v1.json"

SOURCES={
 "mtf": B/"zitar_mtf_research_v2.json",
 "research_memory_index": B/"zitar_research_memory_v1_index.json",
 "opinion": B/"zitar_research_opinion_v1.json",
 "event_radar": B/"zitar_event_news_radar_v2_4.json",
 "news": B/"zitar_news_intelligence_v1_1.json",
 "news_market_join": B/"zitar_news_market_join_v1_1.json",
}

def load_optional(p):
    if not p.exists(): return None
    try:
        x=json.loads(p.read_text(encoding="utf-8"))
        return x if isinstance(x,(dict,list)) else None
    except Exception:
        return None

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None

def atomic(p,obj):
    q=p.with_suffix(p.suffix+".tmp")
    with q.open("w",encoding="utf-8") as h:
        json.dump(obj,h,ensure_ascii=False,indent=2); h.flush()
        try: os.fsync(h.fileno())
        except OSError: pass
    q.replace(p)

def find_symbol_records(obj,symbol):
    found=[]
    def walk(x,path="root"):
        if isinstance(x,dict):
            s=x.get("symbol") or x.get("pair")
            if str(s).upper()==symbol: found.append({"path":path,"data":x})
            for k,v in x.items():
                if isinstance(v,(dict,list)): walk(v,f"{path}.{k}")
        elif isinstance(x,list):
            for i,v in enumerate(x):
                if isinstance(v,(dict,list)): walk(v,f"{path}[{i}]")
    walk(obj)
    return found

def main():
    docs={k:load_optional(p) for k,p in SOURCES.items()}
    availability={k:(docs[k] is not None) for k in SOURCES}
    symbols=set()

    # Discover symbols from MTF and opinion artifacts.
    for key in ("mtf","opinion"):
        obj=docs.get(key)
        if obj is None: continue
        def collect(x):
            if isinstance(x,dict):
                s=x.get("symbol") or x.get("pair")
                if isinstance(s,str) and s.upper().endswith("TRY"): symbols.add(s.upper())
                for v in x.values():
                    if isinstance(v,(dict,list)): collect(v)
            elif isinstance(x,list):
                for v in x: collect(v)
        collect(obj)

    # Radar/news join can add pair symbols.
    join=docs.get("news_market_join")
    if join:
        for u in join.get("units",[]):
            a=u.get("asset")
            # Do not invent pair mapping here; only consume explicit pair/symbol if present.
            p=u.get("pair") or u.get("symbol")
            if isinstance(p,str) and p.upper().endswith("TRY"): symbols.add(p.upper())

    symbol_context={}
    for s in sorted(symbols):
        symbol_context[s]={
          "MTF_RESEARCH":find_symbol_records(docs["mtf"],s) if docs["mtf"] else [],
          "AI_OPINION_HISTORY":find_symbol_records(docs["opinion"],s) if docs["opinion"] else [],
          "EVENT_NEWS_EVIDENCE":find_symbol_records(docs["event_radar"],s) if docs["event_radar"] else [],
          "NEWS_MARKET_JOIN":find_symbol_records(docs["news_market_join"],s) if docs["news_market_join"] else [],
        }

    packet={
      "engine":"ZITAR_CHAT_CONTEXT_V1",
      "generated_utc":datetime.now(timezone.utc).isoformat(),
      "mode":"READ_ONLY_GROUNDING",
      "authority":{
        "execution_authority":False,
        "real_orders":False,
        "v3_write":False,
        "scheduler_mutation":False,
        "source_db_write":False,
        "llm_called":False,
      },
      "source_categories":{
        "LIVE_DATA":"Current/most recent local market observations contained in artifacts; freshness must be stated.",
        "ZITAR_RESEARCH":"Deterministic MTF/Event/News research outputs.",
        "MEMORY":"Versioned ZİTAR research-memory/history artifacts.",
        "INFERENCE":"Reasoning derived from grounded evidence; must be labeled as inference.",
        "UNCERTAINTY":"Missing, stale, conflicting, or insufficient evidence must be stated explicitly.",
        "GENERAL_KNOWLEDGE":"Model knowledge, if later used, must be distinguished from ZİTAR-local evidence."
      },
      "source_availability":availability,
      "source_hashes":{k:sha(p) for k,p in SOURCES.items()},
      "symbols":sorted(symbols),
      "symbol_context":symbol_context,
      "global_context":{
        "research_memory_index":docs["research_memory_index"],
        "news_summary":docs["news"].get("summary",{}) if isinstance(docs["news"],dict) else None,
        "radar_summary":docs["event_radar"].get("summary",{}) if isinstance(docs["event_radar"],dict) else None,
        "news_market_summary":docs["news_market_join"].get("summary",{}) if isinstance(docs["news_market_join"],dict) else None,
      },
      "chat_integrity_rules":[
        "Ground factual ZİTAR claims in supplied local artifacts.",
        "Do not convert research descriptions into BUY/SELL instructions.",
        "Do not claim causation from temporal news association.",
        "Do not treat data confidence as predictive confidence.",
        "Do not hide conflicting evidence.",
        "If evidence is missing or insufficient, say so.",
        "Historical success does not establish forward success.",
        "Chat has no execution authority."
      ]
    }
    atomic(OUT,packet)

    print("="*118)
    print("ZITAR CHAT CONTEXT BUILDER V1 - MASTER PLAN 13/26")
    print("="*118)
    print("MODE: READ ONLY GROUNDING | LLM CALLED: NO | V3 WRITE: NO | REAL ORDERS: NO")
    for k,v in availability.items():
        print(f"SOURCE {k:<24}: {'OK' if v else 'MISSING'}")
    print("-"*118)
    print("SYMBOLS DISCOVERED :",len(symbols))
    print("SYMBOL SAMPLE      :",", ".join(sorted(symbols)[:10]) if symbols else "NONE")
    print("CONTEXT JSON       :",OUT)
    print("-"*118)
    print("NEXT GATE: validate context coverage before connecting Qwen/Ollama.")
    print("RULE: GROUNDED CHAT != EXECUTION AUTHORITY.")
    print("="*118)

if __name__=="__main__": main()
