#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR News + Market Evidence Join V1.1
Master Plan 18/26

Uses:
  zitar_news_intelligence_v1_1.json
  zitar_event_news_radar_v2_4.json

Rules:
- STRICT duplicate cluster may collapse to one cluster+asset evidence unit.
- RELATED_EVENT candidates NEVER collapse.
- Raw member evidence is preserved.
- Timing conflicts are exposed, never averaged away.
- No causal/pump/trading inference.

READ ONLY inputs. Writes only its own JSON/CSV.
NO V3 writes. NO LLM. NO orders.
"""
import csv, json, os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE=Path(__file__).resolve().parent
NEWS=BASE/"zitar_news_intelligence_v1_1.json"
RADAR=BASE/"zitar_event_news_radar_v2_4.json"
OUTJ=BASE/"zitar_news_market_join_v1_1.json"
OUTC=BASE/"zitar_news_market_join_v1_1.csv"

def load(p):
    if not p.exists(): raise SystemExit(f"Missing input: {p.name}")
    return json.loads(p.read_text(encoding="utf-8"))

def atomic_json(p,obj):
    q=p.with_suffix(p.suffix+".tmp")
    with q.open("w",encoding="utf-8") as h:
        json.dump(obj,h,ensure_ascii=False,indent=2);h.flush()
        try: os.fsync(h.fileno())
        except OSError: pass
    q.replace(p)

def main():
    news=load(NEWS)
    radar=load(RADAR)

    obs=news.get("observations",[])
    links=radar.get("links",[])
    by_source={str(x.get("source_id")):x for x in obs}

    # Related pairs are audit metadata only. They do NOT change evidence identity.
    related_pairs=set()
    for x in news.get("related_event_candidates",[]):
        a,b=str(x.get("left_source_id")),str(x.get("right_source_id"))
        related_pairs.add(tuple(sorted((a,b))))

    grouped=defaultdict(list)
    unmatched=[]

    for link in links:
        sid=str(link.get("source_id"))
        no=by_source.get(sid)
        if not no:
            unmatched.append(link)
            continue

        asset=link.get("asset")
        dup_cluster=no.get("duplicate_cluster")
        # V1.1 assigns a Dxxxx cluster to every row, but only clusters with >1 member
        # are true collapsible duplicate clusters. Build set from strict_duplicate_clusters.
        strict_ids={x.get("cluster_id") for x in news.get("strict_duplicate_clusters",[])}
        if dup_cluster in strict_ids:
            evidence_identity=f"STRICT:{dup_cluster}:{asset}"
        else:
            evidence_identity=f"ROW:{sid}:{asset}"
        grouped[evidence_identity].append((no,link))

    units=[]
    for eid,members in sorted(grouped.items()):
        source_ids=[str(x.get("source_id")) for _,x in members]
        titles=[]
        events=set()
        evrows=[]
        for no,link in members:
            if link.get("title") not in titles: titles.append(link.get("title"))
            events.update(no.get("event_types",[]))
            if link.get("market_evidence_available"):
                evrows.append({
                    "source_id":link.get("source_id"),
                    "published_utc":link.get("published_utc"),
                    "timeframe":link.get("timeframe"),
                    **link.get("evidence",{})
                })

        timings=[x.get("timing_class") for x in evrows if x.get("timing_class")]
        tc=Counter(timings)
        conflict=len(tc)>1

        related_to=[]
        for other in obs:
            oid=str(other.get("source_id"))
            if oid in source_ids: continue
            if any(tuple(sorted((sid,oid))) in related_pairs for sid in source_ids):
                related_to.append({"source_id":other.get("source_id"),"title":other.get("title")})

        units.append({
            "evidence_unit_id":eid,
            "identity_type":"STRICT_DUPLICATE_COLLAPSED" if eid.startswith("STRICT:") else "INDEPENDENT_ROW",
            "asset":members[0][1].get("asset"),
            "source_ids":source_ids,
            "headline_count":len(titles),
            "titles":titles,
            "event_types":sorted(events),
            "related_event_candidates_not_collapsed":related_to,
            "market_evidence_member_count":len(evrows),
            "timing_counts":dict(tc),
            "timing_conflict":conflict,
            "pump_confirmed":False,
            "buy_signal":False,
            "evidence":evrows,
        })

    collapsed=len(links)-len(units)
    related_units=sum(bool(u["related_event_candidates_not_collapsed"]) for u in units)
    conflicts=sum(u["timing_conflict"] for u in units)

    payload={
      "engine":"ZITAR_NEWS_MARKET_JOIN_V1_1",
      "generated_utc":datetime.now(timezone.utc).isoformat(),
      "summary":{
        "radar_links_input":len(links),
        "evidence_units":len(units),
        "strict_duplicate_evidence_collapsed":collapsed,
        "related_units_preserved_independently":related_units,
        "unmatched_radar_links":len(unmatched),
        "within_unit_timing_conflicts":conflicts,
        "pump_confirmed":0,
        "buy_signals":0
      },
      "integrity":{
        "v3_write":False,"llm_used":False,"execution_authority":False,"real_orders":False,
        "rules":[
          "Only strict duplicate clusters may collapse.",
          "Related-event candidates remain independent evidence rows.",
          "Raw temporal evidence is preserved.",
          "Timing conflicts are exposed.",
          "Temporal association does not establish causation.",
          "No news/evidence unit creates BUY/SELL authority."
        ]
      },
      "units":units,
      "unmatched_radar_links":unmatched
    }
    atomic_json(OUTJ,payload)

    fields=["evidence_unit_id","identity_type","asset","source_ids","headline_count","event_types",
            "related_count","market_evidence_member_count","timing_counts","timing_conflict",
            "pump_confirmed","buy_signal","titles"]
    q=OUTC.with_suffix(".csv.tmp")
    with q.open("w",encoding="utf-8-sig",newline="") as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader()
        for u in units:
            w.writerow({
              "evidence_unit_id":u["evidence_unit_id"],"identity_type":u["identity_type"],
              "asset":u["asset"],"source_ids":"|".join(u["source_ids"]),
              "headline_count":u["headline_count"],"event_types":"|".join(u["event_types"]),
              "related_count":len(u["related_event_candidates_not_collapsed"]),
              "market_evidence_member_count":u["market_evidence_member_count"],
              "timing_counts":json.dumps(u["timing_counts"],sort_keys=True),
              "timing_conflict":u["timing_conflict"],"pump_confirmed":"NO","buy_signal":"NO",
              "titles":" || ".join(u["titles"])
            })
        h.flush()
        try: os.fsync(h.fileno())
        except OSError: pass
    q.replace(OUTC)

    print("="*124)
    print("ZITAR NEWS + MARKET EVIDENCE JOIN V1.1 - STRICT/RELATED SAFE JOIN")
    print("="*124)
    print("READ ONLY INPUTS | V3 WRITE: NO | LLM: NO | REAL ORDERS: NO")
    print("RADAR LINKS INPUT                  :",len(links))
    print("EVIDENCE UNITS                     :",len(units))
    print("STRICT DUP EVIDENCE COLLAPSED      :",collapsed)
    print("RELATED UNITS PRESERVED            :",related_units)
    print("UNMATCHED RADAR LINKS              :",len(unmatched))
    print("WITHIN-UNIT TIMING CONFLICTS       :",conflicts)
    print("PUMP CONFIRMED                     : 0")
    print("BUY SIGNALS                        : 0")
    print("-"*124)
    print("RELATED EVENT RELATIONSHIPS PRESERVED, NOT COLLAPSED:")
    shown=0
    for u in units:
        if u["related_event_candidates_not_collapsed"]:
            shown+=1
            print(f"  {u['evidence_unit_id']} asset={u['asset']}")
            print("    THIS:",u["titles"][0][:105])
            for z in u["related_event_candidates_not_collapsed"][:3]:
                print("    RELATED:",z["title"][:102])
    if not shown: print("  NONE")
    print("-"*124)
    print("JSON:",OUTJ)
    print("CSV :",OUTC)
    print("RULE: STRICT DUPLICATE MAY COLLAPSE; RELATED EVENT MUST REMAIN INDEPENDENT.")
    print("="*124)

if __name__=="__main__":
    main()
