#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Event & News Radar V2.1 - Market Before/After Evidence
READ-ONLY source DB analysis. Writes only its own JSON/CSV research artifacts.

Joins asset-specific news observations to local historical candles.
Measures BEFORE vs AFTER price/volume around publication time.
NO LLM. NO source DB writes. NO V3 writes. NO orders.
IMPORTANT: anomaly/event evidence != pump confirmation != BUY.
"""
import csv, json, math, os, sqlite3
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE=Path(__file__).resolve().parent
RADAR1=BASE/"zitar_event_news_radar_v1.json"
DBS=[BASE/"learning_lab.db",BASE/"long_history.db",BASE/"portfolio_hub.db"]
OUTJ=BASE/"zitar_event_news_radar_v2.json"
OUTC=BASE/"zitar_event_news_radar_v2.csv"

# Binance TR pair aliases for mapped news assets.
PAIR={"BTC":"BTCTRY","ETH":"ETHTRY","SOL":"SOLTRY","XRP":"XRPTRY","DOGE":"DOGETRY",
      "AVAX":"AVAXTRY","NEAR":"NEARTRY","PEPE":"PEPETRY","TRUMP":"TRUMPTRY",
      "PENGU":"PENGUTRY","SAGA":"SAGATRY","COTI":"COTITRY","MINA":"MINATRY",
      "MUBARAK":"MUBARAKTRY","PHA":"PHATRY","ENA":"ENATRY","FORM":"FORMTRY"}

def dt(v):
    if not v:return None
    try:return parsedate_to_datetime(v).astimezone(timezone.utc)
    except Exception:pass
    try:
        x=datetime.fromisoformat(v.replace("Z","+00:00"))
        return (x if x.tzinfo else x.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except Exception:return None

def ro(db):
    c=sqlite3.connect(f"file:{db.as_posix()}?mode=ro",uri=True); c.row_factory=sqlite3.Row; return c

def table_cols(c,t):
    return [r["name"] for r in c.execute(f'PRAGMA table_info("{t}")')]

def choose_source(symbol):
    # Prefer 1m candles where available, then 5m. We inspect real schemas, never assume one DB.
    candidates=[]
    for db in DBS:
        if not db.exists():continue
        c=ro(db)
        try:
            tabs={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for t in tabs:
                cols=set(table_cols(c,t))
                if not {"symbol","open_time_ms","open","high","low","close","volume"}.issubset(cols):continue
                tfcol="interval" if "interval" in cols else ("timeframe" if "timeframe" in cols else None)
                if not tfcol:continue
                for tf,rank in [("1m",0),("5m",1)]:
                    n=c.execute(f'SELECT COUNT(*) FROM "{t}" WHERE symbol=? AND "{tfcol}"=?',(symbol,tf)).fetchone()[0]
                    if n>=30:candidates.append((rank,-n,db,t,tfcol,tf,n))
        finally:c.close()
    return sorted(candidates,key=lambda x:(x[0],x[1]))[0] if candidates else None

def candles(src,symbol,center_ms):
    _,_,db,t,tfcol,tf,n=src
    c=ro(db)
    try:
        # 3 hours either side gives enough baseline/follow-through at 1m/5m.
        rows=c.execute(
          f'SELECT CAST(open_time_ms AS INTEGER) AS open_time_ms,open,high,low,close,volume FROM "{t}" '
          f'WHERE symbol=? AND "{tfcol}"=? AND CAST(open_time_ms AS INTEGER) BETWEEN ? AND ? '
          f'ORDER BY CAST(open_time_ms AS INTEGER)',
          (symbol,tf,center_ms-3*3600_000,center_ms+3*3600_000)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:c.close()

def f(x):
    try:return float(x)
    except:return None

def median(xs):
    xs=sorted(x for x in xs if x is not None)
    if not xs:return None
    m=len(xs)//2
    return xs[m] if len(xs)%2 else (xs[m-1]+xs[m])/2

def pct(a,b):
    return ((b/a)-1)*100 if a not in (None,0) and b is not None else None

def analyze(rows,pub_ms,tf):
    step=60_000 if tf=="1m" else 300_000
    # publication belongs to the candle whose interval contains pub time.
    before=[r for r in rows if int(r["open_time_ms"])+step<=pub_ms]
    after=[r for r in rows if int(r["open_time_ms"])>=pub_ms]
    if len(before)<12 or len(after)<6:return None
    pre=before[-12:]
    post=after[:12]
    pre_close=f(pre[-1]["close"]); p30=None; p60=None
    target30=pub_ms+30*60_000; target60=pub_ms+60*60_000
    eligible30=[r for r in post if int(r["open_time_ms"])<=target30]
    eligible60=[r for r in post if int(r["open_time_ms"])<=target60]
    if eligible30:p30=f(eligible30[-1]["close"])
    if eligible60:p60=f(eligible60[-1]["close"])
    pre_vol=median([f(r["volume"]) for r in pre])
    post_vol=median([f(r["volume"]) for r in post[:6]])
    vr=(post_vol/pre_vol) if pre_vol not in (None,0) and post_vol is not None else None
    # Descriptive anomaly flags, not "pump".
    move30=pct(pre_close,p30); move60=pct(pre_close,p60)
    flags=[]
    if vr is not None and vr>=2:flags.append("VOLUME_EXPANSION_2X")
    if move30 is not None and abs(move30)>=2:flags.append("ABS_MOVE_30M_GE_2PCT")
    if move60 is not None and abs(move60)>=3:flags.append("ABS_MOVE_60M_GE_3PCT")
    return {"pre_close":pre_close,"return_30m_pct":move30,"return_60m_pct":move60,
            "pre_volume_median":pre_vol,"post_volume_median":post_vol,
            "volume_ratio":vr,"anomaly_flags":flags,
            "before_candles":len(pre),"after_candles":len(post)}

def atomic(path,text):
    tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(text,encoding="utf-8")
    with tmp.open("r+",encoding="utf-8") as h:
        h.flush()
        try:os.fsync(h.fileno())
        except OSError:pass
    tmp.replace(path)

def main():
    if not RADAR1.exists():raise SystemExit("Run zitar_event_news_radar_v1.py first")
    r1=json.loads(RADAR1.read_text(encoding="utf-8"))
    out=[]
    cache={}
    miss={"NO_SOURCE":0,"INSUFFICIENT_WINDOW":0}
    for o in r1.get("observations",[]):
        pub=dt(o.get("published_utc"))
        for asset in o.get("assets",[]):
            pair=PAIR.get(asset)
            if not pair or not pub:continue
            if pair not in cache:cache[pair]=choose_source(pair)
            src=cache[pair]
            rec={"source_id":o.get("source_id"),"published_utc":pub.isoformat(),"title":o.get("title"),
                 "asset":asset,"pair":pair,"event_types":[x.get("type") for x in o.get("event_matches",[])],
                 "market_evidence_available":False,"pump_confirmed":False,"buy_signal":False}
            if src:
                rows=candles(src,pair,int(pub.timestamp()*1000))
                ev=analyze(rows,int(pub.timestamp()*1000),src[5])
                if ev:
                    rec.update({"market_evidence_available":True,
                                "candle_source":src[2].name+"/"+src[3],"timeframe":src[5],
                                "evidence":ev})
                else:
                    miss["INSUFFICIENT_WINDOW"] += 1
                    rec["evidence_missing_reason"]="INSUFFICIENT_WINDOW"
                    rec["window_rows_found"]=len(rows)
            else:
                miss["NO_SOURCE"] += 1
                rec["evidence_missing_reason"]="NO_SOURCE"
            out.append(rec)

    measured=sum(x["market_evidence_available"] for x in out)
    anomalous=sum(bool(x.get("evidence",{}).get("anomaly_flags")) for x in out)
    payload={"engine":"ZITAR_EVENT_NEWS_RADAR_V2_1","generated_utc":datetime.now(timezone.utc).isoformat(),
             "mode":"READ_ONLY_MARKET_BEFORE_AFTER_RESEARCH",
             "summary":{"asset_event_links":len(out),"market_evidence_measured":measured,
                        "descriptive_anomaly_links":anomalous,"pump_confirmed":0,"buy_signals":0},
             "rules":["Anomaly flags are descriptive thresholds, not predictive evidence.",
                      "News timing association does not establish causation.",
                      "V2 does not have historical order-book/spread/trade-count snapshots.",
                      "Pump confirmation is intentionally disabled."],
             "authority":{"source_db_write":False,"v3_write":False,"execution_authority":False,"real_orders":False},
             "links":out}
    atomic(OUTJ,json.dumps(payload,ensure_ascii=False,indent=2))

    fields=["source_id","published_utc","asset","pair","timeframe","market_evidence_available",
            "return_30m_pct","return_60m_pct","volume_ratio","anomaly_flags","pump_confirmed","buy_signal","title"]
    tmp=OUTC.with_suffix(".csv.tmp")
    with tmp.open("w",encoding="utf-8-sig",newline="") as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader()
        for x in out:
            e=x.get("evidence",{})
            w.writerow({"source_id":x["source_id"],"published_utc":x["published_utc"],"asset":x["asset"],
              "pair":x["pair"],"timeframe":x.get("timeframe",""),"market_evidence_available":x["market_evidence_available"],
              "return_30m_pct":e.get("return_30m_pct"),"return_60m_pct":e.get("return_60m_pct"),
              "volume_ratio":e.get("volume_ratio"),"anomaly_flags":"|".join(e.get("anomaly_flags",[])),
              "pump_confirmed":"NO","buy_signal":"NO","title":x["title"]})
        h.flush()
        try:os.fsync(h.fileno())
        except OSError:pass
    tmp.replace(OUTC)

    print("="*112)
    print("ZITAR EVENT & NEWS RADAR V2.1 - MARKET BEFORE/AFTER EVIDENCE")
    print("="*112)
    print("SOURCE DB WRITE: NO | V3 WRITE: NO | LLM: NO | REAL ORDERS: NO")
    print("ASSET-EVENT LINKS :",len(out))
    print("MARKET MEASURED   :",measured)
    print("ANOMALY LINKS     :",anomalous)
    print("PUMP CONFIRMED    : 0")
    print("BUY SIGNALS       : 0")
    print("MISS NO_SOURCE    :",miss["NO_SOURCE"])
    print("MISS WINDOW       :",miss["INSUFFICIENT_WINDOW"])
    print("-"*112)
    for x in [z for z in out if z["market_evidence_available"]][:20]:
        e=x["evidence"]
        print(f"{x['pair']:<12} {x['timeframe']:<3} 30m={e['return_30m_pct']!s:<12} "
              f"60m={e['return_60m_pct']!s:<12} volx={e['volume_ratio']!s:<12} "
              f"{','.join(e['anomaly_flags']) or '-'}")
        print("  "+x["title"][:105])
    print("-"*112)
    print("JSON:",OUTJ)
    print("CSV :",OUTC)
    print("LIMIT: historical spread/order-book/trade-count are not claimed because current stored schema has not established them.")
    print("RULE : EVENT != CAUSATION; ANOMALY != PUMP; PUMP != BUY.")
    print("="*112)
if __name__=="__main__":main()
