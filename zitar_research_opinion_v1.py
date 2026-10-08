#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Versioned Research Opinion Engine V1

Deterministic research interpretation over:
  zitar_research_memory_v1.jsonl
  zitar_mtf_research_v2.json

Outputs:
  zitar_research_opinion_v1.json
  zitar_research_opinion_v1.csv

NO LLM. NO BUY/SELL. NO ranking. NO execution authority. NO V3 writes.
"Opinion" means a versioned research view, not investment advice.
"""

import csv, hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
JOURNAL = BASE / "zitar_research_memory_v1.jsonl"
MTF = BASE / "zitar_mtf_research_v2.json"
OUT_JSON = BASE / "zitar_research_opinion_v1.json"
OUT_CSV = BASE / "zitar_research_opinion_v1.csv"

def canon(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def sha(x):
    if isinstance(x, str):
        x = x.encode("utf-8")
    return hashlib.sha256(x).hexdigest()

def atomic_json(path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as h:
        json.dump(obj, h, ensure_ascii=False, indent=2)
        h.flush()
        try: os.fsync(h.fileno())
        except OSError: pass
    tmp.replace(path)

def atomic_csv(path, rows):
    fields = [
        "symbol","memory_version","view_state","change_state","evidence_state",
        "short","medium","long","monthly","agreement","data_confidence",
        "conflict_count","changed_fields","integrity_warning"
    ]
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
        h.flush()
        try: os.fsync(h.fileno())
        except OSError: pass
    tmp.replace(path)

def load_records():
    if not JOURNAL.exists():
        raise SystemExit(f"MEMORY JOURNAL NOT FOUND: {JOURNAL}")
    records=[]
    for n,line in enumerate(JOURNAL.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip(): continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise SystemExit(f"MEMORY JSON ERROR line {n}: {e}")
    return records

def validate_chain(records):
    prev="GENESIS"
    for i,r in enumerate(records,1):
        if r.get("prev_hash") != prev:
            return False, f"prev_hash mismatch record {i}"
        body={k:v for k,v in r.items() if k!="record_hash"}
        if r.get("record_hash") != sha(canon(body)):
            return False, f"record_hash mismatch record {i}"
        prev=r["record_hash"]
    return True,"OK"

def histories(records):
    out={}
    for r in records:
        out.setdefault(r["symbol"],[]).append(r)
    for s in out:
        out[s].sort(key=lambda r:int(r.get("symbol_version",0)))
    return out

def classify_view(obs):
    # Research description only; deliberately not BUY/SELL.
    core=[obs.get("short"),obs.get("medium"),obs.get("long")]
    ups=sum(x=="UP_DOMINANT" for x in core)
    dns=sum(x=="DOWN_DOMINANT" for x in core)
    mixed=sum(x=="MIXED" for x in core)

    if ups>=2 and dns==0:
        return "MULTI_HORIZON_UP_LEAN"
    if dns>=2 and ups==0:
        return "MULTI_HORIZON_DOWN_LEAN"
    if ups and dns:
        return "CROSS_HORIZON_CONFLICT"
    if ups==1 and dns==0:
        return "LOCALIZED_UP_LEAN"
    if dns==1 and ups==0:
        return "LOCALIZED_DOWN_LEAN"
    if mixed==3:
        return "MIXED_NO_DIRECTIONAL_VIEW"
    return "MIXED_OR_INSUFFICIENT"

def changed_fields(prev,cur):
    keys=["overall","short","medium","long","monthly","agreement","confidence",
          "conflicts","positive_momentum","negative_momentum",
          "high_volume","high_volatility"]
    return [k for k in keys if prev.get(k)!=cur.get(k)]

def make_opinion(symbol,hist):
    cur=hist[-1]
    prev=hist[-2] if len(hist)>=2 else None
    obs=cur["observation"]
    view=classify_view(obs)

    if prev is None:
        change_state="BASELINE_ONLY"
        changed=[]
        durable=False
        warning="Only one memory version exists; no view-change claim is supported yet."
    else:
        changed=changed_fields(prev["observation"],obs)
        old_view=classify_view(prev["observation"])
        if not changed:
            change_state="NO_MEANINGFUL_CHANGE"
        elif old_view != view:
            change_state="VIEW_CLASS_CHANGED"
        else:
            change_state="EVIDENCE_OR_COMPONENT_CHANGED"
        # V1 intentionally conservative: two snapshots can show change,
        # but cannot establish durability/persistence.
        durable=False
        warning="A change is observable, but durability requires additional prospective versions."

    evidence_state = (
        "HIGH_DATA_CONFIDENCE"
        if obs.get("confidence")=="HIGH"
        else "LIMITED_DATA_CONFIDENCE"
    )

    return {
        "symbol":symbol,
        "memory_version":cur.get("symbol_version"),
        "observed_utc":cur.get("observed_utc"),
        "view_state":view,
        "change_state":change_state,
        "changed_fields":changed,
        "previous_version":prev.get("symbol_version") if prev else None,
        "previous_view_state":classify_view(prev["observation"]) if prev else None,
        "evidence_state":evidence_state,
        "data_confidence":obs.get("confidence"),
        "agreement":obs.get("agreement"),
        "contexts":{
            "short":obs.get("short"),
            "medium":obs.get("medium"),
            "long":obs.get("long"),
            "monthly_aux":obs.get("monthly")
        },
        "conflicts":obs.get("conflicts",[]),
        "durable_change_supported":durable,
        "integrity_warning":warning,
        "provenance":{
            "memory_record_hash":cur.get("record_hash"),
            "evidence_hash":cur.get("evidence_hash"),
            "source_engine":cur.get("source_engine"),
            "source_generated_utc":cur.get("source_generated_utc")
        },
        "authority":{
            "research_only":True,
            "buy_sell_signal":False,
            "strategy_ranking":False,
            "execution_authority":False
        }
    }

def main():
    records=load_records()
    ok,msg=validate_chain(records)
    if not ok:
        raise SystemExit("MEMORY CHAIN INVALID: "+msg)

    hs=histories(records)
    opinions=[make_opinion(s,hs[s]) for s in sorted(hs)]

    payload={
        "engine":"ZITAR_VERSIONED_RESEARCH_OPINION_V1",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "memory_chain_valid":True,
        "symbol_count":len(opinions),
        "methodology":{
            "deterministic":True,
            "llm_used":False,
            "monthly_auxiliary":True,
            "durability_rule":"V1 never calls a view change durable from only one transition.",
            "interpretation":"Research view only; not a trading signal."
        },
        "opinions":opinions
    }
    atomic_json(OUT_JSON,payload)

    rows=[]
    for x in opinions:
        c=x["contexts"]
        rows.append({
            "symbol":x["symbol"],
            "memory_version":x["memory_version"],
            "view_state":x["view_state"],
            "change_state":x["change_state"],
            "evidence_state":x["evidence_state"],
            "short":c["short"],"medium":c["medium"],"long":c["long"],
            "monthly":c["monthly_aux"],
            "agreement":x["agreement"],
            "data_confidence":x["data_confidence"],
            "conflict_count":len(x["conflicts"]),
            "changed_fields":",".join(x["changed_fields"]),
            "integrity_warning":x["integrity_warning"]
        })
    atomic_csv(OUT_CSV,rows)

    print("="*112)
    print("ZITAR VERSIONED RESEARCH OPINION ENGINE V1")
    print("="*112)
    print("DETERMINISTIC: YES | LLM: NO | BUY/SELL: NO | EXEC AUTHORITY: NO | V3 WRITE: NO")
    print(f"MEMORY CHAIN : VALID | RECORDS={len(records)} | SYMBOLS={len(opinions)}")
    print("-"*112)
    print(f"{'SYMBOL':12} {'VER':4} {'VIEW STATE':30} {'CHANGE STATE':28} {'CONF':6} {'AGR':8}")
    print("-"*112)
    for x in opinions:
        print(f"{x['symbol']:12} v{x['memory_version']:<2}  {x['view_state']:30} "
              f"{x['change_state']:28} {str(x['data_confidence']):6} {str(x['agreement']):8}")
    print("-"*112)
    print("JSON:",OUT_JSON)
    print("CSV :",OUT_CSV)
    print("INTEGRITY: v1-only history cannot support a claim that ZITAR's view changed.")
    print("="*112)

if __name__=="__main__":
    main()
