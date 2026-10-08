#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Cross-Timeframe Research Engine V2
READ-ONLY research synthesis. NO orders. NO V3 state writes.

Depends on:
  zitar_mtf_research_v1_1.py

Outputs:
  zitar_mtf_research_v2.json
  zitar_mtf_research_v2.csv

Important:
- Descriptive research only.
- No BUY/SELL signal.
- No strategy ranking.
- No allocation/execution authority.
"""

import csv, json, os
from datetime import datetime, timezone
from pathlib import Path
import zitar_mtf_research_v1_1 as mtf

BASE = Path(__file__).resolve().parent
OUT_JSON = BASE / "zitar_mtf_research_v2.json"
OUT_CSV = BASE / "zitar_mtf_research_v2.csv"

FROZEN_21 = [
    "AVAXTRY","BTCTRY","COTITRY","DOGETRY","ENATRY","ETHTRY","FORMTRY",
    "GTRY","MINATRY","MUBARAKTRY","NEARTRY","ONETRY","PENGUTRY","PEPETRY",
    "PHATRY","SAGATRY","SOLTRY","TRUMPTRY","TSTTRY","USDTTRY","XRPTRY"
]

GROUPS = {
    "SHORT": ["1m","5m","15m","30m"],
    "MEDIUM": ["1h","4h"],
    "LONG": ["1d","1w"],
    "MONTHLY_CONTEXT": ["1M"],
}

def atomic_json(path, payload):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as h:
        json.dump(payload, h, ensure_ascii=False, indent=2)
        h.flush()
        try: os.fsync(h.fileno())
        except OSError: pass
    tmp.replace(path)

def atomic_csv(path, rows):
    fields = [
        "symbol","overall_structure","agreement","confidence",
        "short_context","medium_context","long_context","monthly_context",
        "conflict_count","positive_momentum_tfs","negative_momentum_tfs",
        "high_volume_tfs","high_volatility_tfs"
    ]
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields)
        w.writeheader(); w.writerows(rows)
        h.flush()
        try: os.fsync(h.fileno())
        except OSError: pass
    tmp.replace(path)

def quality_weight(x):
    q=x.get("data_quality")
    if q=="OK": return 1.0
    if q=="LIMITED": return 0.5
    return 0.0

def group_context(items):
    usable=[x for x in items if quality_weight(x)>0]
    if not usable:
        return {"observation":"INSUFFICIENT","usable":0,"up":0,"down":0,"mixed":0}
    up=sum(x.get("trend_observation")=="UP" for x in usable)
    dn=sum(x.get("trend_observation")=="DOWN" for x in usable)
    mx=sum(x.get("trend_observation")=="MIXED" for x in usable)
    if up>dn and up>mx: obs="UP_DOMINANT"
    elif dn>up and dn>mx: obs="DOWN_DOMINANT"
    else: obs="MIXED"
    return {"observation":obs,"usable":len(usable),"up":up,"down":dn,"mixed":mx}

def agreement(items):
    directional=[x for x in items if quality_weight(x)>0 and x.get("trend_observation") in ("UP","DOWN")]
    if len(directional)<2:
        return {"level":"LOW_EVIDENCE","directional_timeframes":len(directional),"ratio":None}
    up=sum(x["trend_observation"]=="UP" for x in directional)
    dn=len(directional)-up
    ratio=max(up,dn)/len(directional)
    level="HIGH" if ratio>=0.80 else ("MEDIUM" if ratio>=0.60 else "LOW")
    return {"level":level,"directional_timeframes":len(directional),"ratio":round(ratio,3),
            "up":up,"down":dn}

def conflicts(items):
    usable={x["timeframe"]:x for x in items if quality_weight(x)>0}
    pairs=[
        ("5m","1h"),("15m","1h"),("30m","1h"),
        ("1h","4h"),("4h","1d"),("1d","1w")
    ]
    out=[]
    for a,b in pairs:
        if a in usable and b in usable:
            aa=usable[a].get("trend_observation")
            bb=usable[b].get("trend_observation")
            if {aa,bb}=={"UP","DOWN"}:
                out.append({"timeframe_a":a,"observation_a":aa,
                            "timeframe_b":b,"observation_b":bb})
    return out

def confidence(items):
    ok=sum(x.get("data_quality")=="OK" for x in items)
    limited=sum(x.get("data_quality")=="LIMITED" for x in items)
    bad=sum(x.get("data_quality") in ("MISSING","INSUFFICIENT") for x in items)
    gaps=sum((x.get("continuity") or {}).get("gap_count",0)>0 for x in items)
    # 1M is allowed to be limited without degrading otherwise clean 1m..1w research.
    core=[x for x in items if x.get("timeframe")!="1M"]
    core_ok=sum(x.get("data_quality")=="OK" for x in core)
    if core_ok==len(core) and gaps==0: level="HIGH"
    elif bad==0 and gaps==0: level="MEDIUM"
    else: level="LOW"
    return {"level":level,"ok":ok,"limited":limited,"insufficient_or_missing":bad,"gap_cells":gaps}

def synthesize(symbol):
    raw=mtf.one(symbol)
    items=raw["timeframes"]
    bytf={x["timeframe"]:x for x in items}

    contexts={}
    for name,tfs in GROUPS.items():
        contexts[name]=group_context([bytf[t] for t in tfs if t in bytf])

    agr=agreement([x for x in items if x["timeframe"]!="1M"])
    con=conflicts(items)
    conf=confidence(items)

    pos=[x["timeframe"] for x in items if x.get("momentum_observation")=="POSITIVE" and quality_weight(x)>0]
    neg=[x["timeframe"] for x in items if x.get("momentum_observation")=="NEGATIVE" and quality_weight(x)>0]
    highvol=[x["timeframe"] for x in items if quality_weight(x)>0 and
             x.get("volume_ratio_vs_20") is not None and x["volume_ratio_vs_20"]>=1.5]
    highatr=[x["timeframe"] for x in items if quality_weight(x)>0 and
             x.get("atr14_pct") is not None and x["atr14_pct"]>=5.0]

    return {
        "symbol":symbol,
        "overall_structure_observation":raw["summary"]["research_structure_observation"],
        "contexts":contexts,
        "cross_timeframe_agreement":agr,
        "explicit_conflicts":con,
        "momentum_context":{
            "positive_timeframes":pos,
            "negative_timeframes":neg,
            "note":"Descriptive only; RSI/momentum is not execution authority."
        },
        "activity_context":{
            "volume_ratio_ge_1_5_timeframes":highvol,
            "atr14_pct_ge_5_timeframes":highatr,
            "threshold_note":"Fixed descriptive thresholds for V2 research summaries; not optimized trading rules."
        },
        "data_confidence":conf,
        "evidence":[{
            "timeframe":x["timeframe"],
            "source":x.get("source"),
            "last_open_time_ms":x.get("last_open_time_ms"),
            "quality":x.get("data_quality"),
            "candle_count":x.get("candle_count"),
            "trend":x.get("trend_observation"),
            "momentum":x.get("momentum_observation"),
            "rsi14_simple":x.get("rsi14_simple"),
            "atr14_pct":x.get("atr14_pct"),
            "volume_ratio_vs_20":x.get("volume_ratio_vs_20"),
        } for x in items],
        "research_integrity":{
            "is_execution_signal":False,
            "is_strategy_ranking":False,
            "historical_success_claim":False,
            "interpretation":"Cross-timeframe descriptive observation only."
        }
    }

def main():
    results=[]
    rows=[]
    for i,s in enumerate(FROZEN_21,1):
        print(f"[{i:02}/21] {s} research synthesis ...", flush=True)
        z=synthesize(s);results.append(z)
        c=z["contexts"]
        rows.append({
            "symbol":s,
            "overall_structure":z["overall_structure_observation"],
            "agreement":z["cross_timeframe_agreement"]["level"],
            "confidence":z["data_confidence"]["level"],
            "short_context":c["SHORT"]["observation"],
            "medium_context":c["MEDIUM"]["observation"],
            "long_context":c["LONG"]["observation"],
            "monthly_context":c["MONTHLY_CONTEXT"]["observation"],
            "conflict_count":len(z["explicit_conflicts"]),
            "positive_momentum_tfs":",".join(z["momentum_context"]["positive_timeframes"]),
            "negative_momentum_tfs":",".join(z["momentum_context"]["negative_timeframes"]),
            "high_volume_tfs":",".join(z["activity_context"]["volume_ratio_ge_1_5_timeframes"]),
            "high_volatility_tfs":",".join(z["activity_context"]["atr14_pct_ge_5_timeframes"]),
        })

    payload={
        "engine":"ZITAR_CROSS_TIMEFRAME_RESEARCH_V2",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "mode":"READ_ONLY_RESEARCH",
        "real_orders":False,
        "execution_authority":False,
        "v3_state_writes":False,
        "universe":"FROZEN_V3_21",
        "symbol_count":len(results),
        "context_groups":GROUPS,
        "methodology":{
            "trend":"Uses V1.1 close/SMA20/SMA50 descriptive trend observations.",
            "agreement":"Agreement is calculated only among directional UP/DOWN core timeframes; MIXED is not forced into a direction.",
            "conflicts":"Explicit opposite UP/DOWN observations across predefined adjacent/cross-scale timeframe pairs.",
            "monthly":"1M is context only and may be LIMITED/INSUFFICIENT.",
            "authority":"Research synthesis only; cannot place or authorize orders."
        },
        "results":results
    }
    atomic_json(OUT_JSON,payload);atomic_csv(OUT_CSV,rows)

    print("\n"+"="*92)
    print("ZITAR CROSS-TIMEFRAME RESEARCH ENGINE V2")
    print("="*92)
    print("READ-ONLY | REAL ORDERS: NO | EXEC AUTHORITY: NO | V3 WRITE: NO")
    print("-"*92)
    print(f"{'SYMBOL':12} {'SHORT':14} {'MEDIUM':14} {'LONG':14} {'AGREE':12} {'CONF':8} CONFLICT")
    print("-"*92)
    for z in results:
        c=z["contexts"]
        print(f"{z['symbol']:12} {c['SHORT']['observation']:14} {c['MEDIUM']['observation']:14} "
              f"{c['LONG']['observation']:14} {z['cross_timeframe_agreement']['level']:12} "
              f"{z['data_confidence']['level']:8} {len(z['explicit_conflicts']):>3}")
    print("-"*92)
    print("JSON:",OUT_JSON)
    print("CSV :",OUT_CSV)
    print("RESEARCH ONLY - NO BUY/SELL SIGNAL - NO STRATEGY RANKING")
    print("="*92)

if __name__=="__main__":
    main()
