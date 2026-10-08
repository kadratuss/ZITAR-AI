#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Radar Source Discovery Audit V3
Purpose: explain exactly why Radar source discovery sees no eligible candle table.
READ ONLY. No DB writes. No V3 writes. No orders.
"""
import sqlite3
from pathlib import Path

BASE=Path(__file__).resolve().parent
DBS=[BASE/"learning_lab.db",BASE/"long_history.db",BASE/"portfolio_hub.db"]
PAIRS=["BTCTRY","DOGETRY","ETHTRY","SOLTRY","XRPTRY"]
REQ={"symbol","open_time_ms","open","high","low","close","volume"}

def ro(p):
    c=sqlite3.connect(f"file:{p.as_posix()}?mode=ro",uri=True)
    c.row_factory=sqlite3.Row
    return c

def main():
    print("="*124)
    print("ZITAR RADAR SOURCE DISCOVERY AUDIT V3")
    print("="*124)
    print("READ ONLY | DB WRITE: NO | V3 WRITE: NO | ORDERS: NO")
    for db in DBS:
        print("\nDB:",db.name,"EXISTS:",db.exists())
        if not db.exists(): continue
        c=ro(db)
        try:
            tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            for t in tables:
                info=[dict(r) for r in c.execute(f'PRAGMA table_info("{t}")')]
                cols=[x["name"] for x in info]
                interesting=("symbol" in cols or "open_time_ms" in cols or t in ("candles","historical_candles","timeframe_candles"))
                if not interesting: continue
                missing=sorted(REQ-set(cols))
                print("-"*124)
                print("TABLE:",t)
                print("COLS :",", ".join(cols))
                print("MISSING FOR RADAR:",", ".join(missing) if missing else "NONE")
                tfcol="interval" if "interval" in cols else ("timeframe" if "timeframe" in cols else None)
                print("TF COLUMN:",tfcol or "NONE")
                if "symbol" in cols:
                    for p in PAIRS:
                        n=c.execute(f'SELECT COUNT(*) FROM "{t}" WHERE symbol=?',(p,)).fetchone()[0]
                        if n:
                            if tfcol:
                                vals=[r[0] for r in c.execute(
                                    f'SELECT DISTINCT "{tfcol}" FROM "{t}" WHERE symbol=? ORDER BY 1',(p,)
                                ).fetchall()]
                                print(f"  {p:<10} n={n:<8} tf_values={vals[:20]}")
                            else:
                                print(f"  {p:<10} n={n:<8}")
        finally:
            c.close()
    print("\n"+"="*124)
    print("INTERPRETATION: if MISSING FOR RADAR is not NONE, Radar V2.2 rejected that table before timeframe discovery.")
    print("This audit exposes the exact schema mismatch so the next fix can use the real stored fields.")
    print("="*124)

if __name__=="__main__":
    main()
