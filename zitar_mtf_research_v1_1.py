#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Multi-Timeframe Research Engine V1.1
- Read-only DB access
- No order/execution authority
- No V3 state writes
- Chooses the best available source per timeframe
- Can aggregate missing 5m/15m/30m/1h/4h from smaller local candles
"""

import argparse, json, math, os, sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB_HUB = BASE/"portfolio_hub.db"
DB_LAB = BASE/"learning_lab.db"
DB_LONG = BASE/"long_history.db"
OUT = BASE/"zitar_mtf_snapshot_v1_1.json"

TFS = ["1m","5m","15m","30m","1h","4h","1d","1w","1M"]
LIMIT = 250
MIN_GOOD = 50

MS = {
    "1m":60_000, "5m":300_000, "15m":900_000, "30m":1_800_000,
    "1h":3_600_000, "4h":14_400_000, "1d":86_400_000
}

SOURCES = [
    ("portfolio_hub.timeframe_candles", DB_HUB, "timeframe_candles", "timeframe"),
    ("learning_lab.candles", DB_LAB, "candles", "interval"),
    ("long_history.historical_candles", DB_LONG, "historical_candles", "interval"),
    ("long_history.aggregated_candles", DB_LONG, "aggregated_candles", "interval"),
]

def ro(p):
    return sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True) if p.exists() else None

def rows_to_candles(rows):
    out=[]
    for r in rows:
        try:
            x={"open_time_ms":int(r[0]),"open":float(r[1]),"high":float(r[2]),
               "low":float(r[3]),"close":float(r[4]),"volume":float(r[5])}
            if all(math.isfinite(x[k]) for k in ("open","high","low","close","volume")):
                out.append(x)
        except (TypeError,ValueError,OverflowError):
            pass
    return sorted(out,key=lambda x:x["open_time_ms"])

def query_source(spec,symbol,tf,limit=LIMIT):
    name,p,t,tfcol=spec
    con=ro(p)
    if not con:return []
    try:
        rows=con.execute(
            f"""SELECT open_time_ms,open_price,high_price,low_price,close_price,volume
                FROM {t} WHERE symbol=? AND {tfcol}=?
                ORDER BY open_time_ms DESC LIMIT ?""",
            (symbol,tf,limit)
        ).fetchall()
        return rows_to_candles(rows[::-1])
    except sqlite3.Error:
        return []
    finally:
        con.close()

def direct_candidates(symbol,tf):
    out=[]
    for spec in SOURCES:
        data=query_source(spec,symbol,tf)
        if data:
            out.append((spec[0],data))
    return out

def choose_best_direct(symbol,tf):
    cands=direct_candidates(symbol,tf)
    if not cands:return None,[]
    # Prefer sufficient history, then most candles. This avoids a short hub
    # history masking a much longer historical source.
    sufficient=[x for x in cands if len(x[1])>=MIN_GOOD]
    pool=sufficient if sufficient else cands
    return max(pool,key=lambda x:len(x[1]))

def aggregate(candles,target_tf):
    target_ms=MS[target_tf]
    buckets={}
    for c in candles:
        key=(c["open_time_ms"]//target_ms)*target_ms
        buckets.setdefault(key,[]).append(c)
    out=[]
    for key in sorted(buckets):
        g=sorted(buckets[key],key=lambda x:x["open_time_ms"])
        out.append({
            "open_time_ms":key,
            "open":g[0]["open"],
            "high":max(x["high"] for x in g),
            "low":min(x["low"] for x in g),
            "close":g[-1]["close"],
            "volume":sum(x["volume"] for x in g),
        })
    return out[-LIMIT:]

def best_aggregation_base(symbol,target_tf):
    if target_tf not in MS:return None,[]
    target=MS[target_tf]
    possibilities=[]
    for base_tf,base_ms in MS.items():
        if base_ms>=target or target%base_ms:continue
        # Need enough raw rows to create up to LIMIT target bars.
        ratio=target//base_ms
        need=min(5000, LIMIT*ratio+ratio)
        for spec in SOURCES:
            data=query_source(spec,symbol,base_tf,need)
            if data:
                agg=aggregate(data,target_tf)
                if agg:
                    possibilities.append((f"AGG[{spec[0]}:{base_tf}->{target_tf}]",agg))
    if not possibilities:return None,[]
    sufficient=[x for x in possibilities if len(x[1])>=MIN_GOOD]
    pool=sufficient if sufficient else possibilities
    return max(pool,key=lambda x:len(x[1]))

def load(symbol,tf):
    dname,ddata=choose_best_direct(symbol,tf)
    # If direct data is already research-sufficient, use it.
    if ddata and len(ddata)>=MIN_GOOD:
        return dname,ddata
    # Otherwise see whether local lower-TF data can produce a better history.
    aname,adata=best_aggregation_base(symbol,tf)
    if len(adata)>len(ddata):
        return aname,adata
    return dname,ddata

def sma(v,n): return sum(v[-n:])/n if len(v)>=n else None
def rsi(v,n=14):
    if len(v)<n+1:return None
    ds=[b-a for a,b in zip(v[-n-1:-1],v[-n:])]
    g=sum(max(x,0) for x in ds)/n
    l=sum(max(-x,0) for x in ds)/n
    if l==0:return 100.0 if g>0 else 50.0
    return 100-(100/(1+g/l))
def atr(c,n=14):
    if len(c)<n+1:return None
    p=c[-n-1:]; vals=[]
    for a,b in zip(p[:-1],p[1:]):
        vals.append(max(b["high"]-b["low"],abs(b["high"]-a["close"]),abs(b["low"]-a["close"])))
    return sum(vals)/len(vals)
def pc(a,b): return (b/a-1)*100 if a not in (None,0) and b is not None else None
def rr(x,n=4): return None if x is None or not math.isfinite(x) else round(x,n)

def continuity(c,tf):
    if tf not in MS or len(c)<2:return {"checked":False}
    step=MS[tf]; gaps=0
    for a,b in zip(c[:-1],c[1:]):
        if b["open_time_ms"]-a["open_time_ms"] != step:gaps+=1
    return {"checked":True,"gap_count":gaps,"continuous":gaps==0}

def analyze(symbol,tf,source,c):
    cl=[x["close"] for x in c]; vo=[x["volume"] for x in c]; last=c[-1]
    s20=sma(cl,20);s50=sma(cl,50);r=rsi(cl);a=atr(c)
    m1=pc(cl[-2],cl[-1]) if len(cl)>=2 else None
    m5=pc(cl[-6],cl[-1]) if len(cl)>=6 else None
    m20=pc(cl[-21],cl[-1]) if len(cl)>=21 else None
    av=sum(vo[-20:])/20 if len(vo)>=20 else None
    vr=last["volume"]/av if av not in (None,0) else None
    ap=a/last["close"]*100 if a is not None and last["close"] else None
    trend="INSUFFICIENT"
    if s20 is not None and s50 is not None:
        trend="UP" if last["close"]>s20>s50 else ("DOWN" if last["close"]<s20<s50 else "MIXED")
    mom="INSUFFICIENT"
    if r is not None and m5 is not None:
        mom="POSITIVE" if r>55 and m5>0 else ("NEGATIVE" if r<45 and m5<0 else "MIXED")
    qual="OK" if len(c)>=50 else ("LIMITED" if len(c)>=20 else "INSUFFICIENT")
    return {
        "symbol":symbol,"timeframe":tf,"source":source,"candle_count":len(c),
        "data_quality":qual,"continuity":continuity(c,tf),
        "last_open_time_ms":last["open_time_ms"],"last_close":rr(last["close"],10),
        "trend_observation":trend,"momentum_observation":mom,
        "sma20":rr(s20,10),"sma50":rr(s50,10),"rsi14_simple":rr(r,2),
        "momentum_1bar_pct":rr(m1,3),"momentum_5bar_pct":rr(m5,3),
        "momentum_20bar_pct":rr(m20,3),"atr14":rr(a,10),
        "atr14_pct":rr(ap,3),"volume_ratio_vs_20":rr(vr,3)
    }

def one(symbol):
    out=[];missing=[]
    for tf in TFS:
        source,c=load(symbol,tf)
        if not c:
            missing.append(tf)
            out.append({"symbol":symbol,"timeframe":tf,"source":None,"candle_count":0,
                        "data_quality":"MISSING","trend_observation":"INSUFFICIENT",
                        "momentum_observation":"INSUFFICIENT"})
        else:
            out.append(analyze(symbol,tf,source,c))
    usable=[x for x in out if x["data_quality"] not in ("MISSING","INSUFFICIENT")]
    up=sum(x["trend_observation"]=="UP" for x in usable)
    dn=sum(x["trend_observation"]=="DOWN" for x in usable)
    mx=sum(x["trend_observation"]=="MIXED" for x in usable)
    obs="INSUFFICIENT_DATA" if not usable else (
        "UP_DOMINANT" if up>dn and up>mx else (
        "DOWN_DOMINANT" if dn>up and dn>mx else "MIXED"))
    return {"symbol":symbol,"timeframes":out,"missing_timeframes":missing,
            "summary":{"research_structure_observation":obs,"usable_timeframes":len(usable),
                       "up_timeframes":up,"down_timeframes":dn,"mixed_timeframes":mx,
                       "warning":"Research observation only; not execution authority."}}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--symbol",default="BTCTRY")
    ap.add_argument("--output",default=str(OUT))
    a=ap.parse_args()
    payload={
        "engine":"ZITAR_MTF_RESEARCH_V1_1",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "mode":"READ_ONLY_RESEARCH","real_orders":False,
        "execution_authority":False,"v3_state_writes":False,
        "target_timeframes":TFS,
        "symbol":one(a.symbol.upper())
    }
    out=Path(a.output);tmp=out.with_suffix(out.suffix+".tmp")
    with tmp.open("w",encoding="utf-8") as h:
        json.dump(payload,h,ensure_ascii=False,indent=2);h.flush()
        try:os.fsync(h.fileno())
        except OSError:pass
    tmp.replace(out)
    z=payload["symbol"]
    print("="*76)
    print("ZITAR MULTI-TIMEFRAME RESEARCH V1.1")
    print("READ-ONLY | REAL ORDERS: NO | EXEC AUTHORITY: NO | V3 WRITE: NO")
    print("="*76)
    print(f"{z['symbol']} -> {z['summary']['research_structure_observation']}")
    for x in z["timeframes"]:
        cont=x.get("continuity",{})
        gap=f" gaps={cont.get('gap_count')}" if cont.get("checked") else ""
        print(f" {x['timeframe']:>3} | {x['data_quality']:12} | {x['trend_observation']:12} | "
              f"RSI={x.get('rsi14_simple','-')} | n={x['candle_count']:>3}{gap} | {x.get('source') or 'NO DATA'}")
    if z["missing_timeframes"]:print(" MISSING:",", ".join(z["missing_timeframes"]))
    print("OUTPUT:",out)
    print("RESEARCH ONLY - NOT A BUY/SELL SIGNAL")
    print("="*76)

if __name__=="__main__":
    main()
