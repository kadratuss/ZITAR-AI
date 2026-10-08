#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Event & News Radar V2.2
Fixes V2/V2.1 source discovery: timeframe values are normalized instead of assuming exact '1m'/'5m'.

READ ONLY source DBs. Writes only its own research JSON/CSV.
NO V3 writes. NO orders. NO LLM.
"""
import csv, json, os, sqlite3
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE=Path(__file__).resolve().parent
RADAR1=BASE/"zitar_event_news_radar_v1.json"
DBS=[BASE/"learning_lab.db",BASE/"long_history.db",BASE/"portfolio_hub.db"]
OUTJ=BASE/"zitar_event_news_radar_v2_2.json"
OUTC=BASE/"zitar_event_news_radar_v2_2.csv"

PAIR={"BTC":"BTCTRY","ETH":"ETHTRY","SOL":"SOLTRY","XRP":"XRPTRY","DOGE":"DOGETRY",
      "AVAX":"AVAXTRY","NEAR":"NEARTRY","PEPE":"PEPETRY","TRUMP":"TRUMPTRY",
      "PENGU":"PENGUTRY","SAGA":"SAGATRY","COTI":"COTITRY","MINA":"MINATRY",
      "MUBARAK":"MUBARAKTRY","PHA":"PHATRY","ENA":"ENATRY","FORM":"FORMTRY"}

TF_ALIASES={
 "1m":{"1m","1min","1minute","60s","60sec"},
 "5m":{"5m","5min","5minute","300s","300sec"}
}

def normtf(v):
    s=str(v or "").strip().lower().replace("_","").replace("-","").replace(" ","")
    for canonical, aliases in TF_ALIASES.items():
        if s in aliases: return canonical
    return None

def ro(p):
    c=sqlite3.connect(f"file:{p.as_posix()}?mode=ro",uri=True)
    c.row_factory=sqlite3.Row
    return c

def cols(c,t):
    return [r["name"] for r in c.execute(f'PRAGMA table_info("{t}")')]

def parse_dt(v):
    if not v:return None
    try:return parsedate_to_datetime(v).astimezone(timezone.utc)
    except Exception:pass
    try:
        d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
        if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:return None

def discover_source(symbol):
    candidates=[]
    debug=[]
    for db in DBS:
        if not db.exists(): continue
        c=ro(db)
        try:
            tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for t in tables:
                cs=set(cols(c,t))
                need={"symbol","open_time_ms","open","high","low","close","volume"}
                if not need.issubset(cs): continue
                tfcol="interval" if "interval" in cs else ("timeframe" if "timeframe" in cs else None)
                if not tfcol: continue

                vals=[r[0] for r in c.execute(
                    f'SELECT DISTINCT "{tfcol}" FROM "{t}" WHERE symbol=?',(symbol,)
                ).fetchall()]
                debug.append((db.name,t,tfcol,[str(x) for x in vals[:20]]))
                for raw in vals:
                    canonical=normtf(raw)
                    if canonical not in ("1m","5m"): continue
                    n=c.execute(
                        f'SELECT COUNT(*) FROM "{t}" WHERE symbol=? AND "{tfcol}"=?',
                        (symbol,raw)
                    ).fetchone()[0]
                    if n>=30:
                        rank=0 if canonical=="1m" else 1
                        candidates.append((rank,-n,db,t,tfcol,raw,canonical,n))
        finally:c.close()
    return (sorted(candidates,key=lambda x:(x[0],x[1]))[0] if candidates else None), debug

def fetch_window(src,symbol,center):
    _,_,db,t,tfcol,rawtf,canonical,n=src
    c=ro(db)
    try:
        rows=c.execute(
            f'SELECT CAST(open_time_ms AS INTEGER) AS open_time_ms,open,high,low,close,volume '
            f'FROM "{t}" WHERE symbol=? AND "{tfcol}"=? '
            f'AND CAST(open_time_ms AS INTEGER) BETWEEN ? AND ? '
            f'ORDER BY CAST(open_time_ms AS INTEGER)',
            (symbol,rawtf,center-3*3600000,center+3*3600000)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:c.close()

def num(x):
    try:return float(x)
    except:return None

def med(xs):
    xs=sorted(x for x in xs if x is not None)
    if not xs:return None
    m=len(xs)//2
    return xs[m] if len(xs)%2 else (xs[m-1]+xs[m])/2

def pc(a,b):
    return ((b/a)-1)*100 if a not in (None,0) and b is not None else None

def analyze(rows,pub_ms,tf):
    step=60000 if tf=="1m" else 300000
    before=[r for r in rows if int(r["open_time_ms"])+step<=pub_ms]
    after=[r for r in rows if int(r["open_time_ms"])>=pub_ms]
    if len(before)<12 or len(after)<6:
        return None,{"before":len(before),"after":len(after),"rows":len(rows)}
    pre=before[-12:]; post=after[:12]
    p0=num(pre[-1]["close"])
    r30=[r for r in post if int(r["open_time_ms"])<=pub_ms+30*60000]
    r60=[r for r in post if int(r["open_time_ms"])<=pub_ms+60*60000]
    m30=pc(p0,num(r30[-1]["close"])) if r30 else None
    m60=pc(p0,num(r60[-1]["close"])) if r60 else None
    pv=med([num(r["volume"]) for r in pre])
    av=med([num(r["volume"]) for r in post[:6]])
    vr=av/pv if pv not in (None,0) and av is not None else None
    flags=[]
    if vr is not None and vr>=2:flags.append("VOLUME_EXPANSION_2X")
    if m30 is not None and abs(m30)>=2:flags.append("ABS_MOVE_30M_GE_2PCT")
    if m60 is not None and abs(m60)>=3:flags.append("ABS_MOVE_60M_GE_3PCT")
    return {"return_30m_pct":m30,"return_60m_pct":m60,"volume_ratio":vr,
            "anomaly_flags":flags,"before_candles":len(pre),"after_candles":len(post)},None

def atomic_json(p,obj):
    tmp=p.with_suffix(p.suffix+".tmp")
    with tmp.open("w",encoding="utf-8") as h:
        json.dump(obj,h,ensure_ascii=False,indent=2);h.flush()
        try:os.fsync(h.fileno())
        except OSError:pass
    tmp.replace(p)

def main():
    if not RADAR1.exists():raise SystemExit("Run Radar V1 first.")
    r1=json.loads(RADAR1.read_text(encoding="utf-8"))
    cache={}; debug_cache={}; links=[]; miss={"NO_SOURCE":0,"WINDOW":0}
    for o in r1.get("observations",[]):
        pub=parse_dt(o.get("published_utc"))
        if not pub:continue
        for asset in o.get("assets",[]):
            pair=PAIR.get(asset)
            if not pair:continue
            if pair not in cache:
                cache[pair],debug_cache[pair]=discover_source(pair)
            src=cache[pair]
            x={"source_id":o.get("source_id"),"published_utc":pub.isoformat(),"title":o.get("title"),
               "asset":asset,"pair":pair,"market_evidence_available":False,
               "pump_confirmed":False,"buy_signal":False}
            if not src:
                miss["NO_SOURCE"]+=1;x["missing_reason"]="NO_SOURCE"
            else:
                center=int(pub.timestamp()*1000)
                rows=fetch_window(src,pair,center)
                ev,why=analyze(rows,center,src[6])
                x.update({"candle_source":src[2].name+"/"+src[3],
                          "timeframe":src[6],"raw_timeframe_value":str(src[5])})
                if ev:
                    x["market_evidence_available"]=True;x["evidence"]=ev
                else:
                    miss["WINDOW"]+=1;x["missing_reason"]="INSUFFICIENT_WINDOW";x["window_debug"]=why
            links.append(x)

    measured=sum(x["market_evidence_available"] for x in links)
    anomalous=sum(bool(x.get("evidence",{}).get("anomaly_flags")) for x in links)
    payload={"engine":"ZITAR_EVENT_NEWS_RADAR_V2_2","generated_utc":datetime.now(timezone.utc).isoformat(),
             "summary":{"asset_event_links":len(links),"market_evidence_measured":measured,
                        "descriptive_anomaly_links":anomalous,"miss_no_source":miss["NO_SOURCE"],
                        "miss_window":miss["WINDOW"],"pump_confirmed":0,"buy_signals":0},
             "source_discovery_debug":debug_cache,
             "rules":["Association is not causation.","Anomaly is not pump.","Pump is not BUY."],
             "authority":{"source_db_write":False,"v3_write":False,"execution_authority":False,"real_orders":False},
             "links":links}
    atomic_json(OUTJ,payload)

    fields=["source_id","published_utc","asset","pair","candle_source","timeframe","raw_timeframe_value",
            "market_evidence_available","return_30m_pct","return_60m_pct","volume_ratio",
            "anomaly_flags","missing_reason","pump_confirmed","buy_signal","title"]
    tmp=OUTC.with_suffix(".csv.tmp")
    with tmp.open("w",encoding="utf-8-sig",newline="") as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader()
        for x in links:
            e=x.get("evidence",{})
            w.writerow({**{k:x.get(k,"") for k in fields},
                        "return_30m_pct":e.get("return_30m_pct"),
                        "return_60m_pct":e.get("return_60m_pct"),
                        "volume_ratio":e.get("volume_ratio"),
                        "anomaly_flags":"|".join(e.get("anomaly_flags",[])),
                        "pump_confirmed":"NO","buy_signal":"NO"})
        h.flush()
        try:os.fsync(h.fileno())
        except OSError:pass
    tmp.replace(OUTC)

    print("="*116)
    print("ZITAR EVENT & NEWS RADAR V2.2 - SOURCE DISCOVERY FIX")
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
        if s:
            print(f"SOURCE {pair:<12}: {s[2].name}/{s[3]} tf={s[6]} raw={s[5]!r} n={s[7]}")
        else:
            print(f"SOURCE {pair:<12}: NOT FOUND | seen={debug_cache.get(pair)}")
    print("-"*116)
    for x in [z for z in links if z["market_evidence_available"]][:15]:
        e=x["evidence"]
        print(f"{x['pair']:<12} {x['timeframe']:<3} 30m={e['return_30m_pct']!s:<12} "
              f"60m={e['return_60m_pct']!s:<12} volx={e['volume_ratio']!s:<12} "
              f"{','.join(e['anomaly_flags']) or '-'}")
    print("-"*116)
    print("JSON:",OUTJ)
    print("CSV :",OUTC)
    print("RULE: EVENT != CAUSATION; ANOMALY != PUMP; PUMP != BUY.")
    print("="*116)

if __name__=="__main__":main()
