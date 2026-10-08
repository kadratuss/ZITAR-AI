#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZİTAR Chat Context Builder V1.1 - memory filename discovery fix."""
import json, os, hashlib
from datetime import datetime, timezone
from pathlib import Path

B=Path(__file__).resolve().parent
OUT=B/"zitar_chat_context_v1_1.json"

FIXED={
 "mtf":B/"zitar_mtf_research_v2.json",
 "opinion":B/"zitar_research_opinion_v1.json",
 "event_radar":B/"zitar_event_news_radar_v2_4.json",
 "news":B/"zitar_news_intelligence_v1_1.json",
 "news_market_join":B/"zitar_news_market_join_v1_1.json",
}
MEMORY_CANDIDATES=[
 B/"zitar_research_memory_v1_index.json",
 B/"zitar_research_memory_index_v1.json",
 B/"zitar_research_memory_v1.jsonl",
]

def load_json(p):
    try:
        x=json.loads(p.read_text(encoding="utf-8"))
        return x if isinstance(x,(dict,list)) else None
    except:return None
def load_memory():
    for p in MEMORY_CANDIDATES:
        if not p.exists():continue
        if p.suffix==".jsonl":
            rows=[]
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    if line.strip():rows.append(json.loads(line))
                return rows,p
            except:continue
        x=load_json(p)
        if x is not None:return x,p
    return None,None
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest() if p and p.exists() else None
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
def atomic(p,o):
    q=p.with_suffix(p.suffix+".tmp")
    with q.open("w",encoding="utf-8") as h:
        json.dump(o,h,ensure_ascii=False,indent=2);h.flush()
        try:os.fsync(h.fileno())
        except OSError:pass
    q.replace(p)

def main():
    docs={k:(load_json(p) if p.exists() else None) for k,p in FIXED.items()}
    mem,mem_path=load_memory()
    docs["research_memory"]=mem
    paths={**FIXED,"research_memory":mem_path}
    avail={k:v is not None for k,v in docs.items()}

    syms=set()
    def collect(x):
        if isinstance(x,dict):
            s=x.get("symbol") or x.get("pair")
            if isinstance(s,str) and s.upper().endswith("TRY"):syms.add(s.upper())
            for v in x.values():
                if isinstance(v,(dict,list)):collect(v)
        elif isinstance(x,list):
            for v in x:collect(v)
    for k in ("mtf","opinion","research_memory"): 
        if docs[k] is not None:collect(docs[k])

    ctx={}
    for s in sorted(syms):
        ctx[s]={
          "ZITAR_RESEARCH":find(docs["mtf"],s) if docs["mtf"] else [],
          "MEMORY":find(docs["research_memory"],s) if docs["research_memory"] else [],
          "AI_OPINION_HISTORY":find(docs["opinion"],s) if docs["opinion"] else [],
          "EVENT_NEWS_EVIDENCE":find(docs["event_radar"],s) if docs["event_radar"] else [],
          "NEWS_MARKET_JOIN":find(docs["news_market_join"],s) if docs["news_market_join"] else [],
        }

    packet={"engine":"ZITAR_CHAT_CONTEXT_V1_1","generated_utc":datetime.now(timezone.utc).isoformat(),
      "mode":"READ_ONLY_GROUNDING",
      "authority":{"execution_authority":False,"real_orders":False,"v3_write":False,
                   "scheduler_mutation":False,"source_db_write":False,"llm_called":False},
      "source_availability":avail,
      "resolved_paths":{k:(p.name if p else None) for k,p in paths.items()},
      "source_hashes":{k:sha(p) for k,p in paths.items()},
      "symbols":sorted(syms),"symbol_context":ctx,
      "source_categories":["LIVE_DATA","ZITAR_RESEARCH","MEMORY","INFERENCE","UNCERTAINTY","GENERAL_KNOWLEDGE"],
      "rules":["Ground ZITAR factual claims in local evidence.","No BUY/SELL conversion.",
               "No causal claim from temporal association.","Expose conflicts and uncertainty.",
               "Chat has no execution authority."]}
    atomic(OUT,packet)

    print("="*118)
    print("ZITAR CHAT CONTEXT BUILDER V1.1 - MEMORY DISCOVERY FIX")
    print("="*118)
    print("READ ONLY | LLM: NO | V3 WRITE: NO | REAL ORDERS: NO")
    for k in ["mtf","research_memory","opinion","event_radar","news","news_market_join"]:
        print(f"SOURCE {k:<24}: {'OK' if avail[k] else 'MISSING'}")
    print("-"*118)
    print("MEMORY RESOLVED     :",mem_path.name if mem_path else "NONE")
    print("SYMBOLS DISCOVERED  :",len(syms))
    print("CONTEXT JSON        :",OUT)
    print("NEXT GATE: context retrieval audit, then Ollama/Qwen.")
    print("="*118)
    if not all(avail.values()):raise SystemExit(1)

if __name__=="__main__":main()
