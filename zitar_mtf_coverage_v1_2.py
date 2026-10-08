#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Multi-Timeframe Coverage Audit V1.2
READ-ONLY research audit. NO orders. NO V3 writes.

Uses zitar_mtf_research_v1_1.py as the analysis/resolver engine.
Default universe = frozen 21-symbol V3 prospective universe.
Outputs:
  zitar_mtf_coverage_v1_2.json
  zitar_mtf_coverage_v1_2.csv
"""

import argparse, csv, json, os
from datetime import datetime, timezone
from pathlib import Path

import zitar_mtf_research_v1_1 as mtf

BASE = Path(__file__).resolve().parent
OUT_JSON = BASE / "zitar_mtf_coverage_v1_2.json"
OUT_CSV = BASE / "zitar_mtf_coverage_v1_2.csv"

FROZEN_21 = [
    "AVAXTRY","BTCTRY","COTITRY","DOGETRY","ENATRY","ETHTRY","FORMTRY",
    "GTRY","MINATRY","MUBARAKTRY","NEARTRY","ONETRY","PENGUTRY","PEPETRY",
    "PHATRY","SAGATRY","SOLTRY","TRUMPTRY","TSTTRY","USDTTRY","XRPTRY"
]

def atomic_json(path, payload):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as h:
        json.dump(payload, h, ensure_ascii=False, indent=2)
        h.flush()
        try: os.fsync(h.fileno())
        except OSError: pass
    tmp.replace(path)

def atomic_csv(path, rows):
    tmp = path.with_suffix(path.suffix + ".tmp")
    fields = [
        "symbol","timeframe","status","candle_count","gap_count",
        "trend_observation","momentum_observation","rsi14_simple","source"
    ]
    with tmp.open("w", encoding="utf-8-sig", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
        h.flush()
        try: os.fsync(h.fileno())
        except OSError: pass
    tmp.replace(path)

def classify(x):
    q = x.get("data_quality", "MISSING")
    cont = x.get("continuity", {})
    gaps = cont.get("gap_count", 0) if cont.get("checked") else 0
    if q == "MISSING":
        return "MISSING"
    if gaps:
        return "GAP"
    if q == "OK":
        return "HEALTHY"
    if q == "LIMITED":
        return "LIMITED"
    return "INSUFFICIENT"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", help="Optional custom symbols; default frozen 21")
    ap.add_argument("--json", default=str(OUT_JSON))
    ap.add_argument("--csv", default=str(OUT_CSV))
    a = ap.parse_args()

    symbols = [s.upper() for s in (a.symbols or FROZEN_21)]
    all_symbols = []
    flat = []
    counts = {"HEALTHY":0,"LIMITED":0,"INSUFFICIENT":0,"MISSING":0,"GAP":0}
    tf_counts = {tf:{"HEALTHY":0,"LIMITED":0,"INSUFFICIENT":0,"MISSING":0,"GAP":0}
                 for tf in mtf.TFS}

    for i, symbol in enumerate(symbols, 1):
        print(f"[{i:02}/{len(symbols)}] {symbol} ...", flush=True)
        result = mtf.one(symbol)
        symbol_counts = {"HEALTHY":0,"LIMITED":0,"INSUFFICIENT":0,"MISSING":0,"GAP":0}

        for x in result["timeframes"]:
            status = classify(x)
            counts[status] += 1
            symbol_counts[status] += 1
            tf_counts[x["timeframe"]][status] += 1
            cont = x.get("continuity", {})
            flat.append({
                "symbol":symbol,
                "timeframe":x["timeframe"],
                "status":status,
                "candle_count":x.get("candle_count",0),
                "gap_count":cont.get("gap_count","") if cont.get("checked") else "",
                "trend_observation":x.get("trend_observation",""),
                "momentum_observation":x.get("momentum_observation",""),
                "rsi14_simple":x.get("rsi14_simple",""),
                "source":x.get("source") or "",
            })

        all_symbols.append({
            "symbol":symbol,
            "coverage":symbol_counts,
            "research_summary":result["summary"],
            "timeframes":result["timeframes"],
        })

    total = len(symbols) * len(mtf.TFS)
    healthy = counts["HEALTHY"]
    usable = counts["HEALTHY"] + counts["LIMITED"]

    payload = {
        "engine":"ZITAR_MTF_COVERAGE_V1_2",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "mode":"READ_ONLY_RESEARCH_AUDIT",
        "real_orders":False,
        "execution_authority":False,
        "v3_state_writes":False,
        "universe_name":"FROZEN_V3_21" if symbols == FROZEN_21 else "CUSTOM",
        "symbol_count":len(symbols),
        "timeframe_count":len(mtf.TFS),
        "total_cells":total,
        "coverage":counts,
        "healthy_pct":round(healthy/total*100,2) if total else 0,
        "usable_pct":round(usable/total*100,2) if total else 0,
        "timeframe_coverage":tf_counts,
        "symbols":all_symbols,
        "research_integrity_note":
            "Coverage quality is not evidence of strategy edge. "
            "LIMITED/INSUFFICIENT/MISSING/GAP cells must not be silently treated as healthy."
    }

    atomic_json(Path(a.json), payload)
    atomic_csv(Path(a.csv), flat)

    print("\n" + "="*78)
    print("ZITAR MTF COVERAGE AUDIT V1.2")
    print("="*78)
    print("MODE            : READ-ONLY RESEARCH AUDIT")
    print("REAL ORDERS     : NO")
    print("V3 STATE WRITE  : NO")
    print(f"SYMBOLS         : {len(symbols)}")
    print(f"TIMEFRAMES      : {len(mtf.TFS)}")
    print(f"TOTAL CELLS     : {total}")
    print(f"HEALTHY         : {counts['HEALTHY']} ({payload['healthy_pct']}%)")
    print(f"LIMITED         : {counts['LIMITED']}")
    print(f"INSUFFICIENT    : {counts['INSUFFICIENT']}")
    print(f"MISSING         : {counts['MISSING']}")
    print(f"GAP             : {counts['GAP']}")
    print(f"USABLE H+L      : {usable} ({payload['usable_pct']}%)")
    print("-"*78)
    for tf in mtf.TFS:
        c=tf_counts[tf]
        print(f"{tf:>3} | healthy={c['HEALTHY']:>2} limited={c['LIMITED']:>2} "
              f"insuff={c['INSUFFICIENT']:>2} missing={c['MISSING']:>2} gap={c['GAP']:>2}")
    print("-"*78)
    print("PER SYMBOL")
    for z in all_symbols:
        c=z["coverage"]
        print(f"{z['symbol']:12} H={c['HEALTHY']} L={c['LIMITED']} "
              f"I={c['INSUFFICIENT']} M={c['MISSING']} G={c['GAP']} | "
              f"{z['research_summary']['research_structure_observation']}")
    print("-"*78)
    print("JSON:", Path(a.json))
    print("CSV :", Path(a.csv))
    print("RESEARCH INTEGRITY: DATA COVERAGE != STRATEGY EDGE")
    print("="*78)

if __name__ == "__main__":
    main()
