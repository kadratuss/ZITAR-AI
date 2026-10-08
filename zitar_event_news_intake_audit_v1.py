#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Event & News Radar - Intake Audit V1
READ ONLY. No DB writes. No orders. No V3 writes.
Audits portfolio_hub.db/news_intake before the radar engine is designed.
"""
import sqlite3, json
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
DB = BASE / "portfolio_hub.db"

def qident(name):
    return '"' + str(name).replace('"','""') + '"'

def main():
    if not DB.exists():
        raise SystemExit(f"DB NOT FOUND: {DB}")

    uri = f"file:{DB.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )]
        if "news_intake" not in tables:
            raise SystemExit("news_intake table not found")

        cols = [dict(r) for r in con.execute("PRAGMA table_info(news_intake)")]
        names = [c["name"] for c in cols]
        count = con.execute("SELECT COUNT(*) FROM news_intake").fetchone()[0]

        print("="*100)
        print("ZITAR EVENT & NEWS RADAR - INTAKE AUDIT V1")
        print("="*100)
        print("MODE        : READ ONLY")
        print("REAL ORDERS : NO")
        print("V3 WRITE    : NO")
        print("DATABASE    :", DB)
        print("NEWS ROWS   :", count)
        print("-"*100)
        print("COLUMNS")
        for c in cols:
            print(f"  {c['name']:<28} {c['type'] or '-'}")
        print("-"*100)

        # Null/blank coverage for every column.
        print("FIELD COVERAGE")
        for n in names:
            qi=qident(n)
            nonempty=con.execute(
                f"SELECT COUNT(*) FROM news_intake WHERE {qi} IS NOT NULL AND TRIM(CAST({qi} AS TEXT))<>''"
            ).fetchone()[0]
            print(f"  {n:<28} {nonempty:>6}/{count:<6} ({(100*nonempty/count if count else 0):6.2f}%)")

        # Safe sample: print compact values, truncating large text.
        print("-"*100)
        print("LATEST SAMPLE (up to 5 rows; values truncated)")
        order_col = next((x for x in [
            "published_at","published_utc","created_at","fetched_at","intake_utc","id"
        ] if x in names), None)
        sql="SELECT * FROM news_intake"
        if order_col:
            sql += f" ORDER BY {qident(order_col)} DESC"
        sql += " LIMIT 5"
        for i,row in enumerate(con.execute(sql),1):
            obj={}
            for k in names:
                v=row[k]
                if v is None: continue
                t=str(v).replace("\n"," ").replace("\r"," ")
                obj[k]=t[:180] + ("…" if len(t)>180 else "")
            print(f"[{i}] "+json.dumps(obj, ensure_ascii=False))

        print("-"*100)
        print("RADAR DESIGN GATE")
        semantic = {
            "time": [x for x in names if any(k in x.lower() for k in ("time","date","publish","created","fetched"))],
            "source": [x for x in names if any(k in x.lower() for k in ("source","publisher","domain","url","link"))],
            "title_text": [x for x in names if any(k in x.lower() for k in ("title","headline","summary","text","content","body"))],
            "symbol_asset": [x for x in names if any(k in x.lower() for k in ("symbol","asset","token","coin","pair"))],
        }
        for k,v in semantic.items():
            print(f"  {k:<14}: {', '.join(v) if v else 'NOT FOUND'}")
        print("="*100)
        print("NEXT: use this schema/coverage to build deterministic Event & News Radar V1.")
        print("RULE: event/pump detection is an observation, never an automatic BUY signal.")
        print("="*100)
    finally:
        con.close()

if __name__ == "__main__":
    main()
