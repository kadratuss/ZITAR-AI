#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Event & News Radar V1
Deterministic, read-only news observation layer.

Reads:
  portfolio_hub.db / news_intake

Writes only its own research artifacts:
  zitar_event_news_radar_v1.json
  zitar_event_news_radar_v1.csv

NO source DB writes. NO V3 writes. NO orders. NO LLM.
Important: event detection != pump confirmation != BUY signal.
"""
import csv, json, os, re, sqlite3
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE=Path(__file__).resolve().parent
DB=BASE/"portfolio_hub.db"
OUT_JSON=BASE/"zitar_event_news_radar_v1.json"
OUT_CSV=BASE/"zitar_event_news_radar_v1.csv"

# Conservative title-only entity aliases. Ambiguous one-letter/short tickers are excluded.
ALIASES={
 "BTC":["bitcoin","btc"], "ETH":["ethereum","ether","eth"],
 "SOL":["solana"], "XRP":["xrp","ripple"], "DOGE":["dogecoin"],
 "AVAX":["avalanche","avax"], "NEAR":["near protocol"],
 "PEPE":["pepe"], "TRUMP":["official trump","trump token","trump coin","$trump"],
 "PENGU":["pudgy penguins","pengu"], "SAGA":["saga protocol"],
 "COTI":["coti"], "MINA":["mina protocol"], "MUBARAK":["mubarak"],
 "PHA":["phala","pha network"], "ENA":["ethena"], "FORM":["four","form network"],
}
EVENT_RULES={
 "REGULATION_LEGAL":["sec","cftc","regulat","lawmakers","court","scotus","lawsuit","case","agency"],
 "LISTING_DELISTING":["listing","listed","delist","delisting"],
 "SECURITY_INCIDENT":["hack","hacked","exploit","breach","stolen","attack"],
 "TOKEN_UNLOCK":["token unlock","unlock"],
 "PROTOCOL_UPDATE":["upgrade","mainnet","testnet","protocol update","hard fork"],
 "ETF_INSTITUTIONAL":["etf","institutional","treasury","stock purchase"],
 "EXCHANGE_MARKET":["exchange","binance","coinbase","kraken","trading activity"],
}
MARKET_WIDE=["crypto","cryptocurrency","bitcoin","ethereum","sec","cftc","stablecoin","digital asset"]

def parse_time(v):
    if not v: return None
    try:
        d=parsedate_to_datetime(v)
        return d.astimezone(timezone.utc)
    except Exception: pass
    try:
        d=datetime.fromisoformat(v.replace("Z","+00:00"))
        if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception: return None

def norm(s): return re.sub(r"\s+"," ",(s or "").strip()).lower()

def detect_assets(title):
    t=norm(title); found=[]
    for asset,aliases in ALIASES.items():
        for a in aliases:
            # word-ish boundary avoids matching ENA inside unrelated words etc.
            if re.search(r"(?<![a-z0-9])"+re.escape(a.lower())+r"(?![a-z0-9])",t):
                found.append(asset); break
    return sorted(set(found))

def detect_events(title):
    t=norm(title); hits=[]
    for typ,words in EVENT_RULES.items():
        matched=[w for w in words if w in t]
        if matched: hits.append({"type":typ,"matched_terms":matched})
    return hits

def atomic_json(path,obj):
    tmp=path.with_suffix(path.suffix+".tmp")
    with tmp.open("w",encoding="utf-8",newline="\n") as f:
        json.dump(obj,f,ensure_ascii=False,indent=2)
        f.flush()
        try: os.fsync(f.fileno())
        except OSError: pass
    tmp.replace(path)

def atomic_csv(path,rows):
    fields=["source_id","published_utc","title","assets","scope","event_types",
            "intake_status","observation_level","pump_confirmed","buy_signal"]
    tmp=path.with_suffix(path.suffix+".tmp")
    with tmp.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
        f.flush()
        try: os.fsync(f.fileno())
        except OSError: pass
    tmp.replace(path)

def main():
    if not DB.exists(): raise SystemExit("portfolio_hub.db not found")
    con=sqlite3.connect(f"file:{DB.as_posix()}?mode=ro",uri=True)
    con.row_factory=sqlite3.Row
    try:
        src=[dict(r) for r in con.execute(
          "SELECT source_id,collected_at,detected_at,published_at,title,intake_status "
          "FROM news_intake ORDER BY published_at DESC"
        )]
    finally: con.close()

    observations=[]
    for r in src:
        title=r.get("title") or ""
        assets=detect_assets(title)
        events=detect_events(title)
        market_wide=any(x in norm(title) for x in MARKET_WIDE)
        scope="ASSET_SPECIFIC" if assets else ("MARKET_WIDE" if market_wide else "UNMAPPED")
        # Title-only evidence is intentionally weak. It can flag an event candidate, not impact.
        level="EVENT_CANDIDATE" if events else ("NEWS_OBSERVATION" if scope!="UNMAPPED" else "UNMAPPED_NEWS")
        dt=parse_time(r.get("published_at"))
        observations.append({
          "source_id":r.get("source_id"),
          "published_utc":dt.isoformat() if dt else r.get("published_at"),
          "collected_at":r.get("collected_at"),
          "detected_at":r.get("detected_at"),
          "title":title,
          "assets":assets,
          "scope":scope,
          "event_matches":events,
          "intake_status":r.get("intake_status"),
          "observation_level":level,
          "market_impact_measured":False,
          "pump_confirmed":False,
          "buy_signal":False,
          "limitations":[
            "news_intake contains title/source_id/time/status only",
            "no canonical publisher/url field",
            "no source-provided symbol/asset field",
            "no price/volume/trade-count/spread/order-book linkage in V1",
            "title keyword/entity mapping can produce false positives or miss aliases"
          ]
        })

    asset_specific=sum(o["scope"]=="ASSET_SPECIFIC" for o in observations)
    market_wide=sum(o["scope"]=="MARKET_WIDE" for o in observations)
    unmapped=sum(o["scope"]=="UNMAPPED" for o in observations)
    event_candidates=sum(o["observation_level"]=="EVENT_CANDIDATE" for o in observations)

    payload={
      "engine":"ZITAR_EVENT_NEWS_RADAR_V1",
      "generated_utc":datetime.now(timezone.utc).isoformat(),
      "mode":"DETERMINISTIC_READ_ONLY_RESEARCH",
      "source_db":"portfolio_hub.db/news_intake",
      "source_rows":len(src),
      "summary":{
        "asset_specific":asset_specific,
        "market_wide":market_wide,
        "unmapped":unmapped,
        "event_candidates":event_candidates,
        "pump_confirmed":0,
        "buy_signals":0
      },
      "authority":{
        "llm_used":False,"source_db_write":False,"v3_write":False,
        "execution_authority":False,"real_orders":False
      },
      "observations":observations
    }
    atomic_json(OUT_JSON,payload)
    rows=[]
    for o in observations:
        rows.append({
          "source_id":o["source_id"],"published_utc":o["published_utc"],"title":o["title"],
          "assets":"|".join(o["assets"]),"scope":o["scope"],
          "event_types":"|".join(x["type"] for x in o["event_matches"]),
          "intake_status":o["intake_status"],"observation_level":o["observation_level"],
          "pump_confirmed":"NO","buy_signal":"NO"
        })
    atomic_csv(OUT_CSV,rows)

    print("="*108)
    print("ZITAR EVENT & NEWS RADAR V1")
    print("="*108)
    print("DETERMINISTIC: YES | LLM: NO | SOURCE DB WRITE: NO | V3 WRITE: NO | REAL ORDERS: NO")
    print(f"SOURCE ROWS      : {len(src)}")
    print(f"ASSET SPECIFIC   : {asset_specific}")
    print(f"MARKET WIDE      : {market_wide}")
    print(f"UNMAPPED         : {unmapped}")
    print(f"EVENT CANDIDATES : {event_candidates}")
    print("PUMP CONFIRMED   : 0  (V1 intentionally cannot confirm pump)")
    print("BUY SIGNALS      : 0")
    print("-"*108)
    for o in observations[:15]:
        a=",".join(o["assets"]) or "-"
        e=",".join(x["type"] for x in o["event_matches"]) or "-"
        print(f"{str(o['source_id']):>7} | {o['scope']:<14} | assets={a:<12} | event={e}")
        print("        "+o["title"][:96])
    print("-"*108)
    print("JSON:",OUT_JSON)
    print("CSV :",OUT_CSV)
    print("NEXT GATE: add market-before/after evidence (price/volume/trade count/spread/order book).")
    print("RULE: EVENT CANDIDATE != PUMP CONFIRMED != BUY.")
    print("="*108)

if __name__=="__main__":
    main()
