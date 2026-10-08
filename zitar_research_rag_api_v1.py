#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Research Retrieval / RAG API V1
Read-only retrieval over:
- zitar_research_memory_v1.jsonl
- zitar_research_memory_index_v1.json
- zitar_mtf_research_v2.json

NO orders. NO execution authority. NO V3 writes.

HTTP:
  GET /api/research/health
  GET /api/research/symbols
  GET /api/research/latest?symbol=BTCTRY
  GET /api/research/history?symbol=BTCTRY
  GET /api/research/changes?symbol=BTCTRY
  GET /api/research/context?symbol=BTCTRY

Default port: 5012
"""

import argparse, json, hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

BASE=Path(__file__).resolve().parent
JOURNAL=BASE/"zitar_research_memory_v1.jsonl"
INDEX=BASE/"zitar_research_memory_index_v1.json"
MTF=BASE/"zitar_mtf_research_v2.json"

def canon(x):
    return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def sha(s):
    if isinstance(s,str): s=s.encode("utf-8")
    return hashlib.sha256(s).hexdigest()

def load_json(path,default=None):
    if not path.exists(): return default
    return json.loads(path.read_text(encoding="utf-8"))

def load_records():
    if not JOURNAL.exists(): return []
    out=[]
    for n,line in enumerate(JOURNAL.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip(): continue
        try: out.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Journal JSON error line {n}: {e}")
    return out

def validate_chain(records):
    prev="GENESIS"
    for i,r in enumerate(records,1):
        if r.get("prev_hash")!=prev: return False,f"prev_hash mismatch record {i}"
        body={k:v for k,v in r.items() if k!="record_hash"}
        if r.get("record_hash")!=sha(canon(body)): return False,f"record_hash mismatch record {i}"
        prev=r["record_hash"]
    return True,"OK"

def sym(s):
    return (s or "").strip().upper()

def history(symbol):
    return [r for r in load_records() if r.get("symbol")==symbol]

def latest(symbol):
    h=history(symbol)
    return h[-1] if h else None

def changes(symbol):
    h=history(symbol)
    out=[]
    for r in h:
        out.append({
            "symbol":symbol,
            "version":r.get("symbol_version"),
            "observed_utc":r.get("observed_utc"),
            "change_from_previous":r.get("change_from_previous"),
            "record_hash":r.get("record_hash")
        })
    return out

def current_mtf(symbol):
    p=load_json(MTF,{}) or {}
    for z in p.get("results",[]):
        if z.get("symbol")==symbol: return z
    return None

def rag_context(symbol):
    h=history(symbol)
    cur=current_mtf(symbol)
    return {
        "engine":"ZITAR_RESEARCH_RETRIEVAL_V1",
        "symbol":symbol,
        "memory_versions":len(h),
        "latest_memory":h[-1] if h else None,
        "previous_memory":h[-2] if len(h)>=2 else None,
        "version_history":[{
            "version":r.get("symbol_version"),
            "observed_utc":r.get("observed_utc"),
            "observation":r.get("observation"),
            "change":r.get("change_from_previous"),
            "evidence_hash":r.get("evidence_hash")
        } for r in h],
        "current_mtf_research":cur,
        "provenance":{
            "memory_journal":JOURNAL.name,
            "current_research":MTF.name,
            "authority":"RESEARCH_ONLY",
            "execution_authority":False
        },
        "answering_rules":[
            "Distinguish stored observation from current market research.",
            "Do not convert descriptive observations into BUY/SELL instructions.",
            "State when history is too short to establish a durable view change.",
            "Preserve conflicts and uncertainty.",
            "Cite evidence/source categories in future AI responses."
        ]
    }

class Handler(BaseHTTPRequestHandler):
    def sendj(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False,indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(b)))
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers(); self.wfile.write(b)

    def log_message(self,fmt,*args):
        print(f"[research-api] {self.address_string()} - {fmt%args}")

    def do_GET(self):
        u=urlparse(self.path); q=parse_qs(u.query); path=u.path
        try:
            if path=="/api/research/health":
                rec=load_records(); ok,msg=validate_chain(rec)
                idx=load_json(INDEX,{}) or {}
                self.sendj({
                    "service":"ZITAR Research Retrieval/RAG API V1",
                    "status":"ONLINE" if ok else "DEGRADED",
                    "chain_valid":ok,"chain_detail":msg,
                    "record_count":len(rec),
                    "symbol_count":len({r.get("symbol") for r in rec}),
                    "index_record_count":idx.get("record_count"),
                    "execution_authority":False,
                    "real_orders":False
                }); return

            if path=="/api/research/symbols":
                rec=load_records()
                ss=sorted({r.get("symbol") for r in rec if r.get("symbol")})
                self.sendj({"symbols":ss,"count":len(ss)}); return

            if path in ("/api/research/latest","/api/research/history",
                        "/api/research/changes","/api/research/context"):
                s=sym((q.get("symbol") or [""])[0])
                if not s:
                    self.sendj({"error":"symbol query parameter required"},400); return
                if path=="/api/research/latest":
                    x=latest(s)
                    self.sendj(x if x else {"error":"symbol not found","symbol":s},200 if x else 404); return
                if path=="/api/research/history":
                    h=history(s)
                    self.sendj({"symbol":s,"versions":len(h),"history":h}); return
                if path=="/api/research/changes":
                    c=changes(s)
                    self.sendj({"symbol":s,"versions":len(c),"changes":c}); return
                self.sendj(rag_context(s)); return

            self.sendj({
                "service":"ZITAR Research Retrieval/RAG API V1",
                "endpoints":[
                    "/api/research/health",
                    "/api/research/symbols",
                    "/api/research/latest?symbol=BTCTRY",
                    "/api/research/history?symbol=BTCTRY",
                    "/api/research/changes?symbol=BTCTRY",
                    "/api/research/context?symbol=BTCTRY"
                ]
            })
        except Exception as e:
            self.sendj({"error":type(e).__name__,"detail":str(e)},500)

def selftest():
    rec=load_records(); ok,msg=validate_chain(rec)
    assert ok,msg
    ss=sorted({r["symbol"] for r in rec})
    assert len(ss)==21,f"expected 21 symbols, got {len(ss)}"
    for s in ss:
        c=rag_context(s)
        assert c["memory_versions"]>=1
        assert c["latest_memory"] is not None
        assert c["provenance"]["execution_authority"] is False
    print("SELFTEST PASS")
    print("CHAIN VALID :",ok)
    print("RECORDS     :",len(rec))
    print("SYMBOLS     :",len(ss))
    print("BTCTRY VERS :",len(history("BTCTRY")))
    print("EXEC AUTH   : NO")
    print("REAL ORDERS : NO")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--host",default="127.0.0.1")
    ap.add_argument("--port",type=int,default=5012)
    ap.add_argument("--selftest",action="store_true")
    a=ap.parse_args()
    if a.selftest:
        selftest(); return
    print("="*72)
    print("ZITAR RESEARCH RETRIEVAL / RAG API V1")
    print(f"http://{a.host}:{a.port}")
    print("READ-ONLY | EXEC AUTHORITY: NO | REAL ORDERS: NO")
    print("="*72)
    ThreadingHTTPServer((a.host,a.port),Handler).serve_forever()

if __name__=="__main__":
    main()
