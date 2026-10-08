#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR News + Market Evidence Join V1
Master Plan 18/26

Joins:
  zitar_news_intelligence_v1.json
  zitar_event_news_radar_v2_4.json

Purpose:
- one evidence unit per news CLUSTER + asset
- duplicate headlines do not multiply independent market evidence
- preserve provenance and temporal measurements
- expose disagreements/inconsistencies instead of hiding them

READ ONLY inputs. Writes only its own JSON/CSV.
NO V3 writes. NO LLM. NO orders.
"""
import csv, json, os
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path

BASE=Path(__file__).resolve().parent
NEWS=BASE/"zitar_news_intelligence_v1.json"
RADAR=BASE/"zitar_event_news_radar_v2_4.json"
OUTJ=BASE/"zitar_news_market_join_v1.json"
OUTC=BASE/"zitar_news_market_join_v1.csv"

def load(p):
    if not p.exists(): raise SystemExit(f"Missing input: {p.name}")
    return json.loads(p.read_text(encoding="utf-8"))

def atomic_json(p,obj):
    tmp=p.with_suffix(p.suffix+".tmp")
    with tmp.open("w",encoding="utf-8") as h:
        json.dump(obj,h,ensure_ascii=False,indent=2);h.flush()
        try: os.fsync(h.fileno())
        except OSError: pass
    tmp.replace(p)

def main():
    n=load(NEWS); r=load(RADAR)
    obs=n.get("observations",[])
    links=r.get("links",[])

    # source_id may be integer/string across files: normalize to string.
    by_source={}
    for x in obs:
        by_source[str(x.get("source_id"))]=x

    grouped=defaultdict(list)
    unmatched=[]
    for x in links:
        no=by_source.get(str(x.get("source_id")))
        if not no:
            unmatched.append(x); continue
        asset=x.get("asset")
        key=(no.get("cluster_id"),asset)
        grouped[key].append((no,x))

    units=[]
    for (cluster_id,asset),members in sorted(grouped.items(), key=lambda z:(str(z[0][0]),str(z[0][1]))):
        # Keep all headline/evidence members, but produce ONE unit.
        primary_news=members[0][0]
        measured=[x for _,x in members if x.get("market_evidence_available")]
        timings=[x.get("evidence",{}).get("timing_class") for x in measured
                 if x.get("evidence",{}).get("timing_class")]
        timing_counts=Counter(timings)
        dominant=timing_counts.most_common(1)[0][0] if timing_counts else None
        timing_conflict=len(timing_counts)>1

        event_types=sorted(set(e for no,_ in members for e in no.get("event_types",[])))
        source_ids=[]
        titles=[]
        evidence=[]
        for no,x in members:
            sid=x.get("source_id")
            if sid not in source_ids: source_ids.append(sid)
            if x.get("title") not in titles: titles.append(x.get("title"))
            if x.get("market_evidence_available"):
                evidence.append({
                    "source_id":sid,
                    "published_utc":x.get("published_utc"),
                    "timeframe":x.get("timeframe"),
                    **x.get("evidence",{})
                })

        units.append({
            "evidence_unit_id":f"{cluster_id}:{asset}",
            "cluster_id":cluster_id,
            "asset":asset,
            "headline_count":len(titles),
            "source_ids":source_ids,
            "titles":titles,
            "event_types":event_types,
            "market_evidence_member_count":len(evidence),
            "timing_summary":dominant,
            "timing_conflict_within_cluster_asset":timing_conflict,
            "timing_counts":dict(timing_counts),
            "pump_confirmed":False,
            "buy_signal":False,
            "evidence":evidence,
        })

    duplicate_collapsed=sum(max(0,u["headline_count"]-1) for u in units)
    conflicts=sum(u["timing_conflict_within_cluster_asset"] for u in units)
    payload={
        "engine":"ZITAR_NEWS_MARKET_JOIN_V1",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "summary":{
            "radar_links_input":len(links),
            "cluster_asset_evidence_units":len(units),
            "duplicate_headline_evidence_collapsed":duplicate_collapsed,
            "unmatched_radar_links":len(unmatched),
            "within_unit_timing_conflicts":conflicts,
            "pump_confirmed":0,
            "buy_signals":0,
        },
        "integrity":{
            "v3_write":False,"llm_used":False,"execution_authority":False,"real_orders":False,
            "rules":[
                "One cluster+asset is one evidence unit.",
                "Duplicate/near-duplicate headlines do not count as independent evidence.",
                "All member headlines and measurements remain preserved for audit.",
                "Timing disagreement inside a cluster is exposed, not averaged away.",
                "Temporal association does not establish causation.",
                "News evidence does not create BUY/SELL authority."
            ]
        },
        "units":units,
        "unmatched_radar_links":unmatched,
    }
    atomic_json(OUTJ,payload)

    fields=["evidence_unit_id","cluster_id","asset","headline_count","source_ids","event_types",
            "market_evidence_member_count","timing_summary","timing_conflict_within_cluster_asset",
            "timing_counts","pump_confirmed","buy_signal","titles"]
    tmp=OUTC.with_suffix(".csv.tmp")
    with tmp.open("w",encoding="utf-8-sig",newline="") as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader()
        for u in units:
            w.writerow({
                "evidence_unit_id":u["evidence_unit_id"],"cluster_id":u["cluster_id"],
                "asset":u["asset"],"headline_count":u["headline_count"],
                "source_ids":"|".join(map(str,u["source_ids"])),"event_types":"|".join(u["event_types"]),
                "market_evidence_member_count":u["market_evidence_member_count"],
                "timing_summary":u["timing_summary"],
                "timing_conflict_within_cluster_asset":u["timing_conflict_within_cluster_asset"],
                "timing_counts":json.dumps(u["timing_counts"],ensure_ascii=False,sort_keys=True),
                "pump_confirmed":"NO","buy_signal":"NO","titles":" || ".join(u["titles"])
            })
        h.flush()
        try: os.fsync(h.fileno())
        except OSError: pass
    tmp.replace(OUTC)

    print("="*122)
    print("ZITAR NEWS + MARKET EVIDENCE JOIN V1 - MASTER PLAN 18/26")
    print("="*122)
    print("READ ONLY INPUTS | V3 WRITE: NO | LLM: NO | REAL ORDERS: NO")
    print("RADAR LINKS INPUT              :",len(links))
    print("CLUSTER+ASSET EVIDENCE UNITS   :",len(units))
    print("DUP HEADLINE EVIDENCE COLLAPSED:",duplicate_collapsed)
    print("UNMATCHED RADAR LINKS          :",len(unmatched))
    print("WITHIN-UNIT TIMING CONFLICTS   :",conflicts)
    print("PUMP CONFIRMED                 : 0")
    print("BUY SIGNALS                    : 0")
    print("-"*122)
    for u in units:
        if u["headline_count"]>1 or u["timing_conflict_within_cluster_asset"]:
            print(f"{u['evidence_unit_id']:<18} headlines={u['headline_count']} "
                  f"measurements={u['market_evidence_member_count']} timing={u['timing_summary']} "
                  f"conflict={u['timing_conflict_within_cluster_asset']}")
            for t in u["titles"]: print("  -",t[:108])
    print("-"*122)
    print("JSON:",OUTJ)
    print("CSV :",OUTC)
    print("RULE: ONE CLUSTER+ASSET = ONE EVIDENCE UNIT; DUPLICATE NEWS != INDEPENDENT EVIDENCE.")
    print("="*122)

if __name__=="__main__":
    main()
