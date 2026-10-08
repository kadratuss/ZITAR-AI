#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Event & News Radar V2.4
Temporal attribution + false-positive hardening.

Fixes an important V2.3 measurement flaw:
V2.3 post sample was capped at 12 x 1m candles, so 30m and 60m returns could become identical.
V2.4 explicitly measures pre-30m, pre-60m, post-30m, post-60m and classifies timing.

READ ONLY source DBs. Writes only its own JSON/CSV research artifacts.
NO source DB writes. NO V3 writes. NO LLM. NO orders.
"""
import csv, json, os, sqlite3, re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE=Path(__file__).resolve().parent
R1=BASE/"zitar_event_news_radar_v1.json"
OUTJ=BASE/"zitar_event_news_radar_v2_4.json"
OUTC=BASE/"zitar_event_news_radar_v2_4.csv"

PAIR={"BTC":"BTCTRY","ETH":"ETHTRY","SOL":"SOLTRY","XRP":"XRPTRY","DOGE":"DOGETRY",
      "AVAX":"AVAXTRY","NEAR":"NEARTRY","PEPE":"PEPETRY","TRUMP":"TRUMPTRY",
      "PENGU":"PENGUTRY","SAGA":"SAGATRY","COTI":"COTITRY","MINA":"MINATRY",
      "MUBARAK":"MUBARAKTRY","PHA":"PHATRY","ENA":"ENATRY","FORM":"FORMTRY"}

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
    except:return None
def F(x):
    try:return float(x)
    except:return None
def pct(a,b):
    return ((b/a)-1)*100 if a not in (None,0) and b is not None else None
def med(xs):
    xs=sorted(x for x in xs if x is not None)
    if not xs:return None
    m=len(xs)//2
    return xs[m] if len(xs)%2 else (xs[m-1]+xs[m])/2

def source(pair):
    for dbn,t,tfcol,tf,step in [
        ("learning_lab.db","candles","interval","1m",60000),
        ("portfolio_hub.db","timeframe_candles","timeframe","5m",300000)]:
        db=BASE/dbn
        if not db.exists():continue
        c=ro(db)
        try:
            n=c.execute(f'SELECT COUNT(*) FROM "{t}" WHERE symbol=? AND "{tfcol}"=?',(pair,tf)).fetchone()[0]
            if n>=120:return db,t,tfcol,tf,step,n
        except sqlite3.Error:pass
        finally:c.close()
    return None

def fetch(src,pair,pub):
    db,t,tfcol,tf,step,n=src;c=ro(db)
    try:
        rs=c.execute(
          f'SELECT CAST(open_time_ms AS INTEGER) open_time_ms, open_price AS open, high_price AS high, '
          f'low_price AS low, close_price AS close, volume FROM "{t}" '
          f'WHERE symbol=? AND "{tfcol}"=? AND CAST(open_time_ms AS INTEGER) BETWEEN ? AND ? '
          f'ORDER BY CAST(open_time_ms AS INTEGER)',
          (pair,tf,pub-75*60000,pub+75*60000)).fetchall()
        return [dict(x) for x in rs]
    finally:c.close()

def last_close_at_or_before(rows,ms,step):
    x=[r for r in rows if int(r["open_time_ms"])+step<=ms]
    return F(x[-1]["close"]) if x else None

def first_close_at_or_after_target(rows,target,step):
    # close of first candle ending at/after target
    x=[r for r in rows if int(r["open_time_ms"])+step>=target]
    return F(x[0]["close"]) if x else None

def analyze(rows,pub,step):
    p0=last_close_at_or_before(rows,pub,step)
    pre30=last_close_at_or_before(rows,pub-30*60000,step)
    pre60=last_close_at_or_before(rows,pub-60*60000,step)
    post30=first_close_at_or_after_target(rows,pub+30*60000,step)
    post60=first_close_at_or_after_target(rows,pub+60*60000,step)
    if None in (p0,pre30,pre60,post30,post60):return None

    pre30r=pct(pre30,p0); pre60r=pct(pre60,p0)
    post30r=pct(p0,post30); post60r=pct(p0,post60)

    pre=[r for r in rows if pub-30*60000 <= int(r["open_time_ms"]) < pub]
    post=[r for r in rows if pub <= int(r["open_time_ms"]) < pub+30*60000]
    pv=med([F(r["volume"]) for r in pre]); av=med([F(r["volume"]) for r in post])
    vr=av/pv if pv not in (None,0) and av is not None else None

    pre_mag=max(abs(pre30r or 0),abs(pre60r or 0))
    post_mag=max(abs(post30r or 0),abs(post60r or 0))
    if pre_mag>=1.5*max(post_mag,0.05): timing="PRE_EVENT_DOMINANT"
    elif post_mag>=1.5*max(pre_mag,0.05): timing="POST_EVENT_DOMINANT"
    else: timing="MIXED_TIMING"

    flags=[]
    if vr is not None and vr>=2:flags.append("POST_VOLUME_EXPANSION_2X")
    if abs(post30r or 0)>=2:flags.append("POST_ABS_MOVE_30M_GE_2PCT")
    if abs(post60r or 0)>=3:flags.append("POST_ABS_MOVE_60M_GE_3PCT")
    if abs(pre30r or 0)>=2:flags.append("PRE_ABS_MOVE_30M_GE_2PCT")
    if abs(pre60r or 0)>=3:flags.append("PRE_ABS_MOVE_60M_GE_3PCT")
    return {"pre_30m_pct":pre30r,"pre_60m_pct":pre60r,
            "post_30m_pct":post30r,"post_60m_pct":post60r,
            "post_vs_pre_volume_ratio":vr,"timing_class":timing,"anomaly_flags":flags}

def relevance(title,event_types):
    t=(title or "").lower()
    # Harden the known false positive: "Hack VC" person/firm name is not a cyber incident.
    hardened=[e for e in event_types if not (e=="SECURITY_INCIDENT" and "hack vc" in t and
              not any(w in t for w in ("hacked","exploit","breach","stolen","cyberattack","attack on")))]
    return hardened

def atomic_json(p,o):
    tmp=p.with_suffix(p.suffix+".tmp")
    with tmp.open("w",encoding="utf-8") as h:
        json.dump(o,h,ensure_ascii=False,indent=2);h.flush()
        try:os.fsync(h.fileno())
        except OSError:pass
    tmp.replace(p)

def main():
    if not R1.exists():raise SystemExit("Run Radar V1 first.")
    r=json.loads(R1.read_text(encoding="utf-8")); cache={}; links=[]; misses=0
    for o in r.get("observations",[]):
        pub=pdt(o.get("published_utc"))
        if not pub:continue
        original=[x.get("type") for x in o.get("event_matches",[])]
        hardened=relevance(o.get("title",""),original)
        for asset in o.get("assets",[]):
            pair=PAIR.get(asset)
            if not pair:continue
            if pair not in cache:cache[pair]=source(pair)
            src=cache[pair]
            x={"source_id":o.get("source_id"),"published_utc":pub.isoformat(),"title":o.get("title"),
               "asset":asset,"pair":pair,"original_event_types":original,
               "hardened_event_types":hardened,"market_evidence_available":False,
               "pump_confirmed":False,"buy_signal":False}
            if src:
                ev=analyze(fetch(src,pair,int(pub.timestamp()*1000)),int(pub.timestamp()*1000),src[4])
                x["candle_source"]=src[0].name+"/"+src[1];x["timeframe"]=src[3]
                if ev:x["market_evidence_available"]=True;x["evidence"]=ev
                else:misses+=1;x["missing_reason"]="TEMPORAL_WINDOW_INCOMPLETE"
            else:misses+=1;x["missing_reason"]="NO_SOURCE"
            links.append(x)

    measured=sum(x["market_evidence_available"] for x in links)
    anomaly=sum(bool(x.get("evidence",{}).get("anomaly_flags")) for x in links)
    pre=sum(x.get("evidence",{}).get("timing_class")=="PRE_EVENT_DOMINANT" for x in links)
    post=sum(x.get("evidence",{}).get("timing_class")=="POST_EVENT_DOMINANT" for x in links)
    mixed=sum(x.get("evidence",{}).get("timing_class")=="MIXED_TIMING" for x in links)
    payload={"engine":"ZITAR_EVENT_NEWS_RADAR_V2_4","generated_utc":datetime.now(timezone.utc).isoformat(),
      "summary":{"links":len(links),"measured":measured,"anomaly_links":anomaly,
                 "pre_event_dominant":pre,"post_event_dominant":post,"mixed_timing":mixed,
                 "missing":misses,"pump_confirmed":0,"buy_signals":0},
      "integrity_notes":[
        "V2.3 30m/60m equality was a sampling-window defect; V2.4 corrects it.",
        "Temporal dominance is descriptive and does not prove news causation.",
        "Known 'Hack VC' false-positive is context-hardened.",
        "No historical spread/order-book/trade-count claims.",
        "No anomaly is promoted to pump or trading signal."
      ],
      "authority":{"source_db_write":False,"v3_write":False,"llm_used":False,
                   "execution_authority":False,"real_orders":False},
      "links":links}
    atomic_json(OUTJ,payload)

    fields=["source_id","published_utc","asset","pair","timeframe","pre_30m_pct","pre_60m_pct",
            "post_30m_pct","post_60m_pct","post_vs_pre_volume_ratio","timing_class","anomaly_flags",
            "original_event_types","hardened_event_types","pump_confirmed","buy_signal","title"]
    tmp=OUTC.with_suffix(".csv.tmp")
    with tmp.open("w",encoding="utf-8-sig",newline="") as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader()
        for x in links:
            e=x.get("evidence",{})
            w.writerow({"source_id":x["source_id"],"published_utc":x["published_utc"],"asset":x["asset"],
              "pair":x["pair"],"timeframe":x.get("timeframe",""),
              "pre_30m_pct":e.get("pre_30m_pct"),"pre_60m_pct":e.get("pre_60m_pct"),
              "post_30m_pct":e.get("post_30m_pct"),"post_60m_pct":e.get("post_60m_pct"),
              "post_vs_pre_volume_ratio":e.get("post_vs_pre_volume_ratio"),
              "timing_class":e.get("timing_class"),"anomaly_flags":"|".join(e.get("anomaly_flags",[])),
              "original_event_types":"|".join(x["original_event_types"]),
              "hardened_event_types":"|".join(x["hardened_event_types"]),
              "pump_confirmed":"NO","buy_signal":"NO","title":x["title"]})
        h.flush()
        try:os.fsync(h.fileno())
        except OSError:pass
    tmp.replace(OUTC)

    print("="*118)
    print("ZITAR EVENT & NEWS RADAR V2.4 - TEMPORAL ATTRIBUTION")
    print("="*118)
    print("SOURCE DB WRITE: NO | V3 WRITE: NO | LLM: NO | REAL ORDERS: NO")
    print("LINKS               :",len(links))
    print("MARKET MEASURED     :",measured)
    print("ANOMALY LINKS       :",anomaly)
    print("PRE-EVENT DOMINANT  :",pre)
    print("POST-EVENT DOMINANT :",post)
    print("MIXED TIMING        :",mixed)
    print("MISSING             :",misses)
    print("PUMP CONFIRMED      : 0")
    print("BUY SIGNALS         : 0")
    print("-"*118)
    for x in [z for z in links if z["market_evidence_available"]][:20]:
        e=x["evidence"]
        print(f"{x['pair']:<10} pre30={e['pre_30m_pct']:+.3f}% pre60={e['pre_60m_pct']:+.3f}% "
              f"post30={e['post_30m_pct']:+.3f}% post60={e['post_60m_pct']:+.3f}% "
              f"volx={e['post_vs_pre_volume_ratio']:.2f} {e['timing_class']}")
    print("-"*118)
    print("JSON:",OUTJ)
    print("CSV :",OUTC)
    print("RULE: TIMING ASSOCIATION != CAUSATION; ANOMALY != PUMP; PUMP != BUY.")
    print("="*118)

if __name__=="__main__":main()
