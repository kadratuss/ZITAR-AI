#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Event & News Radar V2.3
Schema-correct market-before/after evidence engine.

Fix confirmed by source audit:
OHLC columns are open_price/high_price/low_price/close_price.

READ ONLY source DBs. Writes only V2.3 JSON/CSV research artifacts.
NO source DB writes. NO V3 writes. NO LLM. NO orders.
"""
import csv, json, os, sqlite3
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE=Path(__file__).resolve().parent
RADAR1=BASE/"zitar_event_news_radar_v1.json"
DBS=[BASE/"learning_lab.db",BASE/"portfolio_hub.db",BASE/"long_history.db"]
OUTJ=BASE/"zitar_event_news_radar_v2_3.json"
OUTC=BASE/"zitar_event_news_radar_v2_3.csv"

PAIR={"BTC":"BTCTRY","ETH":"ETHTRY","SOL":"SOLTRY","XRP":"XRPTRY","DOGE":"DOGETRY",
      "AVAX":"AVAXTRY","NEAR":"NEARTRY","PEPE":"PEPETRY","TRUMP":"TRUMPTRY",
      "PENGU":"PENGUTRY","SAGA":"SAGATRY","COTI":"COTITRY","MINA":"MINATRY",
      "MUBARAK":"MUBARAKTRY","PHA":"PHATRY","ENA":"ENATRY","FORM":"FORMTRY"}

SCHEMAS=[
 ("learning_lab.db","candles","interval","1m",60000),
 ("portfolio_hub.db","timeframe_candles","timeframe","5m",300000),
]

def ro(p):
    c=sqlite3.connect(f"file:{p.as_posix()}?mode=ro",uri=True); c.row_factory=sqlite3.Row; return c

def pdt(v):
    if not v:return None
    try:return parsedate_to_datetime(v).astimezone(timezone.utc)
    except Exception:pass
    try:
        d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
        if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:return None

def discover(pair):
    for dbn,t,tfcol,tf,step in SCHEMAS:
        db=BASE/dbn
        if not db.exists():continue
        c=ro(db)
        try:
            tabs={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if t not in tabs:continue
            cols={r["name"] for r in c.execute(f'PRAGMA table_info("{t}")')}
            need={"symbol","open_time_ms","open_price","high_price","low_price","close_price","volume",tfcol}
            if not need.issubset(cols):continue
            n=c.execute(f'SELECT COUNT(*) FROM "{t}" WHERE symbol=? AND "{tfcol}"=?',(pair,tf)).fetchone()[0]
            if n>=30:return db,t,tfcol,tf,step,n
        finally:c.close()
    return None

def window(src,pair,center):
    db,t,tfcol,tf,step,n=src
    c=ro(db)
    try:
        rows=c.execute(
          f'SELECT CAST(open_time_ms AS INTEGER) open_time_ms, '
          f'open_price AS open, high_price AS high, low_price AS low, close_price AS close, volume '
          f'FROM "{t}" WHERE symbol=? AND "{tfcol}"=? '
          f'AND CAST(open_time_ms AS INTEGER) BETWEEN ? AND ? ORDER BY CAST(open_time_ms AS INTEGER)',
          (pair,tf,center-3*3600000,center+3*3600000)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:c.close()

def F(x):
    try:return float(x)
    except:return None
def med(xs):
    xs=sorted(x for x in xs if x is not None)
    if not xs:return None
    m=len(xs)//2
    return xs[m] if len(xs)%2 else (xs[m-1]+xs[m])/2
def pct(a,b):
    return ((b/a)-1)*100 if a not in (None,0) and b is not None else None

def analyze(rows,pub,step):
    before=[r for r in rows if int(r["open_time_ms"])+step<=pub]
    after=[r for r in rows if int(r["open_time_ms"])>=pub]
    if len(before)<12 or len(after)<6:
        return None,{"rows":len(rows),"before":len(before),"after":len(after)}
    pre=before[-12:]; post=after[:12]
    p0=F(pre[-1]["close"])
    a30=[r for r in post if int(r["open_time_ms"])<=pub+30*60000]
    a60=[r for r in post if int(r["open_time_ms"])<=pub+60*60000]
    r30=pct(p0,F(a30[-1]["close"])) if a30 else None
    r60=pct(p0,F(a60[-1]["close"])) if a60 else None
    prevol=med([F(r["volume"]) for r in pre])
    postvol=med([F(r["volume"]) for r in post[:6]])
    vr=postvol/prevol if prevol not in (None,0) and postvol is not None else None
    flags=[]
    if vr is not None and vr>=2:flags.append("VOLUME_EXPANSION_2X")
    if r30 is not None and abs(r30)>=2:flags.append("ABS_MOVE_30M_GE_2PCT")
    if r60 is not None and abs(r60)>=3:flags.append("ABS_MOVE_60M_GE_3PCT")
    direction="UP" if (r60 or 0)>0 else ("DOWN" if (r60 or 0)<0 else "FLAT")
    return {"return_30m_pct":r30,"return_60m_pct":r60,"volume_ratio":vr,
            "direction_60m":direction,"anomaly_flags":flags,
            "before_candles":len(pre),"after_candles":len(post)},None

def atomic_json(p,o):
    tmp=p.with_suffix(p.suffix+".tmp")
    with tmp.open("w",encoding="utf-8") as h:
        json.dump(o,h,ensure_ascii=False,indent=2);h.flush()
        try:os.fsync(h.fileno())
        except OSError:pass
    tmp.replace(p)

def main():
    if not RADAR1.exists():raise SystemExit("Run zitar_event_news_radar_v1.py first.")
    r1=json.loads(RADAR1.read_text(encoding="utf-8"))
    cache={}; links=[]; miss={"NO_SOURCE":0,"WINDOW":0}
    for o in r1.get("observations",[]):
        pub=pdt(o.get("published_utc"))
        if not pub:continue
        for asset in o.get("assets",[]):
            pair=PAIR.get(asset)
            if not pair:continue
            if pair not in cache:cache[pair]=discover(pair)
            src=cache[pair]
            x={"source_id":o.get("source_id"),"published_utc":pub.isoformat(),"title":o.get("title"),
               "asset":asset,"pair":pair,"event_types":[z.get("type") for z in o.get("event_matches",[])],
               "market_evidence_available":False,"pump_confirmed":False,"buy_signal":False}
            if not src:
                miss["NO_SOURCE"]+=1;x["missing_reason"]="NO_SOURCE"
            else:
                center=int(pub.timestamp()*1000)
                rows=window(src,pair,center)
                ev,why=analyze(rows,center,src[4])
                x["candle_source"]=src[0].name+"/"+src[1];x["timeframe"]=src[3]
                if ev:
                    x["market_evidence_available"]=True;x["evidence"]=ev
                else:
                    miss["WINDOW"]+=1;x["missing_reason"]="INSUFFICIENT_WINDOW";x["window_debug"]=why
            links.append(x)

    measured=sum(x["market_evidence_available"] for x in links)
    anomalous=sum(bool(x.get("evidence",{}).get("anomaly_flags")) for x in links)
    payload={"engine":"ZITAR_EVENT_NEWS_RADAR_V2_3","generated_utc":datetime.now(timezone.utc).isoformat(),
      "summary":{"asset_event_links":len(links),"market_evidence_measured":measured,
                 "descriptive_anomaly_links":anomalous,"miss_no_source":miss["NO_SOURCE"],
                 "miss_window":miss["WINDOW"],"pump_confirmed":0,"buy_signals":0},
      "methodology":{"preferred_source":"learning_lab.db/candles 1m",
                     "fallback_source":"portfolio_hub.db/timeframe_candles 5m",
                     "schema":"open_price/high_price/low_price/close_price",
                     "thresholds_descriptive_only":True},
      "limitations":["Timing association does not establish causation.",
                     "No historical spread/order-book/trade-count evidence is claimed.",
                     "Keyword/entity mapping may contain false positives.",
                     "Anomaly flags are descriptive thresholds, not a trading signal."],
      "authority":{"source_db_write":False,"v3_write":False,"llm_used":False,
                   "execution_authority":False,"real_orders":False},
      "links":links}
    atomic_json(OUTJ,payload)

    fields=["source_id","published_utc","asset","pair","candle_source","timeframe",
            "market_evidence_available","return_30m_pct","return_60m_pct","volume_ratio",
            "direction_60m","anomaly_flags","missing_reason","pump_confirmed","buy_signal","title"]
    tmp=OUTC.with_suffix(".csv.tmp")
    with tmp.open("w",encoding="utf-8-sig",newline="") as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader()
        for x in links:
            e=x.get("evidence",{})
            w.writerow({"source_id":x["source_id"],"published_utc":x["published_utc"],
              "asset":x["asset"],"pair":x["pair"],"candle_source":x.get("candle_source",""),
              "timeframe":x.get("timeframe",""),"market_evidence_available":x["market_evidence_available"],
              "return_30m_pct":e.get("return_30m_pct"),"return_60m_pct":e.get("return_60m_pct"),
              "volume_ratio":e.get("volume_ratio"),"direction_60m":e.get("direction_60m"),
              "anomaly_flags":"|".join(e.get("anomaly_flags",[])),
              "missing_reason":x.get("missing_reason",""),"pump_confirmed":"NO","buy_signal":"NO",
              "title":x["title"]})
        h.flush()
        try:os.fsync(h.fileno())
        except OSError:pass
    tmp.replace(OUTC)

    print("="*116)
    print("ZITAR EVENT & NEWS RADAR V2.3 - SCHEMA CORRECT MARKET EVIDENCE")
    print("="*116)
    print("SOURCE DB WRITE: NO | V3 WRITE: NO | LLM: NO | REAL ORDERS: NO")
    print("ASSET-EVENT LINKS :",len(links))
    print("MARKET MEASURED   :",measured)
    print("ANOMALY LINKS     :",anomalous)
    print("MISS NO_SOURCE    :",miss["NO_SOURCE"])
    print("MISS WINDOW       :",miss["WINDOW"])
    print("PUMP CONFIRMED    : 0")
    print("BUY SIGNALS       : 0")
    print("-"*116)
    for pair in sorted(cache):
        s=cache[pair]
        print(f"SOURCE {pair:<12}: {s[0].name+'/'+s[1]+' tf='+s[3] if s else 'NOT FOUND'}")
    print("-"*116)
    for x in [z for z in links if z["market_evidence_available"]][:20]:
        e=x["evidence"]
        print(f"{x['pair']:<12} {x['timeframe']:<3} 30m={e['return_30m_pct']!s:<12} "
              f"60m={e['return_60m_pct']!s:<12} volx={e['volume_ratio']!s:<12} "
              f"dir={e['direction_60m']:<4} flags={','.join(e['anomaly_flags']) or '-'}")
        print("  "+x["title"][:102])
    print("-"*116)
    print("JSON:",OUTJ)
    print("CSV :",OUTC)
    print("RULE: EVENT != CAUSATION; ANOMALY != PUMP; PUMP != BUY.")
    print("="*116)

if __name__=="__main__":main()
