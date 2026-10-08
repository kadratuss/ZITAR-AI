#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Research Memory V1
Append-only, hash-chained, versioned memory for MTF Research V2.

INPUT : zitar_mtf_research_v2.json
OUTPUT:
  zitar_research_memory_v1.jsonl
  zitar_research_memory_index_v1.json
  zitar_research_changes_v1.json

NO orders. NO V3 writes. NO trading authority.
Existing observations are never overwritten.
"""

import argparse, hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path

BASE=Path(__file__).resolve().parent
DEFAULT_INPUT=BASE/"zitar_mtf_research_v2.json"
JOURNAL=BASE/"zitar_research_memory_v1.jsonl"
INDEX=BASE/"zitar_research_memory_index_v1.json"
CHANGES=BASE/"zitar_research_changes_v1.json"

def canon(x):
    return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"))

def sha(x):
    if isinstance(x,str): x=x.encode("utf-8")
    return hashlib.sha256(x).hexdigest()

def atomic_json(path,obj):
    tmp=path.with_suffix(path.suffix+".tmp")
    with tmp.open("w",encoding="utf-8",newline="\n") as h:
        json.dump(obj,h,ensure_ascii=False,indent=2);h.flush()
        try: os.fsync(h.fileno())
        except OSError: pass
    tmp.replace(path)

def read_journal():
    if not JOURNAL.exists(): return []
    out=[]
    with JOURNAL.open("r",encoding="utf-8") as h:
        for n,line in enumerate(h,1):
            if not line.strip(): continue
            try: out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Journal JSON error line {n}: {e}")
    return out

def validate_chain(records):
    prev="GENESIS"
    for i,r in enumerate(records,1):
        if r.get("prev_hash")!=prev:
            return False,f"prev_hash mismatch at record {i}"
        body={k:v for k,v in r.items() if k!="record_hash"}
        expected=sha(canon(body))
        if r.get("record_hash")!=expected:
            return False,f"record_hash mismatch at record {i}"
        prev=r["record_hash"]
    return True,"OK"

def append_record(record):
    line=canon(record)+"\n"
    with JOURNAL.open("a",encoding="utf-8",newline="\n") as h:
        h.write(line);h.flush()
        try: os.fsync(h.fileno())
        except OSError: pass

def compact_observation(z):
    c=z["contexts"]
    return {
        "overall":z["overall_structure_observation"],
        "short":c["SHORT"]["observation"],
        "medium":c["MEDIUM"]["observation"],
        "long":c["LONG"]["observation"],
        "monthly":c["MONTHLY_CONTEXT"]["observation"],
        "agreement":z["cross_timeframe_agreement"]["level"],
        "confidence":z["data_confidence"]["level"],
        "conflicts":z["explicit_conflicts"],
        "positive_momentum":z["momentum_context"]["positive_timeframes"],
        "negative_momentum":z["momentum_context"]["negative_timeframes"],
        "high_volume":z["activity_context"]["volume_ratio_ge_1_5_timeframes"],
        "high_volatility":z["activity_context"]["atr14_pct_ge_5_timeframes"],
    }

def evidence_hash(z):
    return sha(canon(z.get("evidence",[])))

def meaningful_hash(z):
    # Used for idempotency: same research state is not appended twice.
    return sha(canon({
        "symbol":z["symbol"],
        "observation":compact_observation(z),
        "evidence_hash":evidence_hash(z)
    }))

def diff(old,new):
    if not old:
        return {"change_type":"INITIAL_OBSERVATION","changed_fields":[]}
    fields=["overall","short","medium","long","monthly","agreement","confidence",
            "positive_momentum","negative_momentum","high_volume","high_volatility"]
    changed=[]
    for k in fields:
        if old["observation"].get(k)!=new.get(k):
            changed.append({
                "field":k,
                "before":old["observation"].get(k),
                "after":new.get(k)
            })
    if old["observation"].get("conflicts")!=new.get("conflicts"):
        changed.append({"field":"conflicts",
                        "before":old["observation"].get("conflicts"),
                        "after":new.get("conflicts")})
    return {"change_type":"CHANGED" if changed else "EVIDENCE_REFRESH",
            "changed_fields":changed}

def latest_by_symbol(records):
    d={}
    for r in records: d[r["symbol"]]=r
    return d

def build_index(records):
    latest=latest_by_symbol(records)
    versions={}
    for r in records: versions[r["symbol"]]=versions.get(r["symbol"],0)+1
    return {
        "engine":"ZITAR_RESEARCH_MEMORY_V1",
        "updated_utc":datetime.now(timezone.utc).isoformat(),
        "record_count":len(records),
        "chain_head":records[-1]["record_hash"] if records else "GENESIS",
        "symbols":{s:{
            "versions":versions[s],
            "latest_record_id":r["record_id"],
            "latest_record_hash":r["record_hash"],
            "latest_observed_utc":r["observed_utc"],
            "latest_observation":r["observation"]
        } for s,r in sorted(latest.items())}
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",default=str(DEFAULT_INPUT))
    a=ap.parse_args()
    inp=Path(a.input)
    if not inp.exists(): raise SystemExit(f"INPUT NOT FOUND: {inp}")

    source_bytes=inp.read_bytes()
    payload=json.loads(source_bytes.decode("utf-8"))
    if payload.get("engine")!="ZITAR_CROSS_TIMEFRAME_RESEARCH_V2":
        raise SystemExit("Unexpected input engine; expected ZITAR_CROSS_TIMEFRAME_RESEARCH_V2")
    if payload.get("execution_authority") is not False or payload.get("real_orders") is not False:
        raise SystemExit("Safety refusal: research input authority flags are not false")

    records=read_journal()
    ok,msg=validate_chain(records)
    if not ok: raise SystemExit("MEMORY CHAIN INVALID: "+msg)

    latest=latest_by_symbol(records)
    prev_hash=records[-1]["record_hash"] if records else "GENESIS"
    now=datetime.now(timezone.utc).isoformat()
    added=0; skipped=0; changes=[]

    for z in payload["results"]:
        symbol=z["symbol"]
        obs=compact_observation(z)
        mh=meaningful_hash(z)
        old=latest.get(symbol)

        if old and old.get("meaningful_hash")==mh:
            skipped+=1
            continue

        version=(old.get("symbol_version",0)+1) if old else 1
        change=diff(old,obs)
        record={
            "record_id":f"{symbol}:v{version}:{now}",
            "symbol":symbol,
            "symbol_version":version,
            "observed_utc":now,
            "source_engine":payload["engine"],
            "source_generated_utc":payload.get("generated_utc"),
            "source_file_sha256":sha(source_bytes),
            "meaningful_hash":mh,
            "evidence_hash":evidence_hash(z),
            "observation":obs,
            "change_from_previous":change,
            "research_integrity":{
                "execution_authority":False,
                "is_buy_sell_signal":False,
                "old_observation_overwritten":False,
                "uncertainty_preserved":True
            },
            "prev_hash":prev_hash
        }
        record["record_hash"]=sha(canon(record))
        append_record(record)
        records.append(record); latest[symbol]=record
        prev_hash=record["record_hash"]; added+=1
        changes.append({
            "symbol":symbol,"version":version,
            "change_type":change["change_type"],
            "changed_fields":change["changed_fields"],
            "record_hash":record["record_hash"]
        })

    ok,msg=validate_chain(records)
    if not ok: raise SystemExit("POST-WRITE MEMORY CHAIN INVALID: "+msg)

    atomic_json(INDEX,build_index(records))
    atomic_json(CHANGES,{
        "engine":"ZITAR_RESEARCH_CHANGESET_V1",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "source":str(inp),
        "added_records":added,
        "idempotent_skips":skipped,
        "changes":changes
    })

    print("="*86)
    print("ZITAR RESEARCH MEMORY V1")
    print("="*86)
    print("MODE             : APPEND-ONLY RESEARCH MEMORY")
    print("EXEC AUTHORITY   : NO")
    print("V3 STATE WRITE   : NO")
    print("CHAIN VALID      : YES")
    print("PREVIOUS RECORDS :",len(records)-added)
    print("ADDED RECORDS    :",added)
    print("IDEMPOTENT SKIPS :",skipped)
    print("TOTAL RECORDS    :",len(records))
    print("CHAIN HEAD       :",records[-1]["record_hash"] if records else "GENESIS")
    print("-"*86)
    for c in changes:
        names=",".join(x["field"] for x in c["changed_fields"]) or "-"
        print(f"{c['symbol']:12} v{c['version']:<3} {c['change_type']:20} changed={names}")
    print("-"*86)
    print("JOURNAL :",JOURNAL)
    print("INDEX   :",INDEX)
    print("CHANGES :",CHANGES)
    print("OLD OBSERVATIONS ARE NEVER OVERWRITTEN")
    print("="*86)

if __name__=="__main__":
    main()
