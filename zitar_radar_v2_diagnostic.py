#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Radar V2 Diagnostics
Explains WHY Radar V2 market evidence measured 0.
READ ONLY: no DB writes, no V3 writes, no orders.
"""
import sqlite3, json
from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

BASE=Path(__file__).resolve().parent
R1=BASE/"zitar_event_news_radar_v1.json"
DBS=[BASE/"learning_lab.db",BASE/"long_history.db",BASE/"portfolio_hub.db"]
PAIR={"BTC":"BTCTRY","ETH":"ETHTRY","SOL":"SOLTRY","XRP":"XRPTRY","DOGE":"DOGETRY",
      "AVAX":"AVAXTRY","NEAR":"NEARTRY","PEPE":"PEPETRY","TRUMP":"TRUMPTRY",
      "PENGU":"PENGUTRY","SAGA":"SAGATRY","COTI":"COTITRY","MINA":"MINATRY",
      "MUBARAK":"MUBARAKTRY","PHA":"PHATRY","ENA":"ENATRY","FORM":"FORMTRY"}

def ro(p):
    c=sqlite3.connect(f"file:{p.as_posix()}?mode=ro",uri=True);c.row_factory=sqlite3.Row;return c
def iso_ms(v):
    if v is None:return "-"
    return datetime.fromtimestamp(int(v)/1000,tz=timezone.utc).isoformat()
def main():
    if not R1.exists():raise SystemExit("Run Radar V1 first")
    r=json.loads(R1.read_text(encoding="utf-8"))
    pairs=sorted({PAIR[a] for o in r.get("observations",[]) for a in o.get("assets",[]) if a in PAIR})
    print("="*118)
    print("ZITAR RADAR V2 ZERO-EVIDENCE DIAGNOSTIC")
    print("="*118)
    print("MODE: READ ONLY | DB WRITE: NO | V3 WRITE: NO | ORDERS: NO")
    print("RADAR MAPPED PAIRS:",", ".join(pairs) if pairs else "-")
    print("-"*118)
    found=[]
    for db in DBS:
        if not db.exists():continue
        c=ro(db)
        try:
            tabs=[x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for t in tabs:
                cols=[x["name"] for x in c.execute(f'PRAGMA table_info("{t}")')]
                if "symbol" not in cols or "open_time_ms" not in cols:continue
                tfcol="interval" if "interval" in cols else ("timeframe" if "timeframe" in cols else None)
                if not tfcol:continue
                for pair in pairs:
                    for tf in ("1m","5m"):
                        row=c.execute(
                          f'SELECT COUNT(*) n, MIN(open_time_ms) mn, MAX(open_time_ms) mx FROM "{t}" '
                          f'WHERE symbol=? AND "{tfcol}"=?',(pair,tf)).fetchone()
                        if row["n"]:
                            found.append((db.name,t,pair,tf,row["n"],row["mn"],row["mx"]))
                            print(f"{db.name:<22} {t:<24} {pair:<12} {tf:<3} n={row['n']:<8} "
                                  f"{iso_ms(row['mn'])} -> {iso_ms(row['mx'])}")
        finally:c.close()
    print("-"*118)
    # News time range for mapped observations
    pubs=[]
    for o in r.get("observations",[]):
        if not o.get("assets"):continue
        v=o.get("published_utc")
        try:
            d=datetime.fromisoformat(v.replace("Z","+00:00"))
            if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
            pubs.append(d.astimezone(timezone.utc))
        except Exception:pass
    if pubs:
        print("MAPPED NEWS RANGE :",min(pubs).isoformat(),"->",max(pubs).isoformat())
    if found:
        data_min=min(x[5] for x in found); data_max=max(x[6] for x in found)
        print("AVAILABLE DATA    :",iso_ms(data_min),"->",iso_ms(data_max))
        if pubs:
            news_min=int(min(pubs).timestamp()*1000);news_max=int(max(pubs).timestamp()*1000)
            overlap=not (news_max < data_min or news_min > data_max)
            print("GLOBAL TIME OVERLAP:", "YES" if overlap else "NO")
    else:
        print("NO 1m/5m mapped-pair candle sources found with the expected schema.")
    print("-"*118)
    print("INTERPRETATION:")
    print("  Radar V2 measured 0 because it could not obtain >=12 pre-event and >=6 post-event candles")
    print("  from an eligible local 1m/5m source. This diagnostic shows whether the cause is")
    print("  missing pair coverage, missing timeframe coverage, or non-overlapping timestamps.")
    print("="*118)
if __name__=="__main__":main()
