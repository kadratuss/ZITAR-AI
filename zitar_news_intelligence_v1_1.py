#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR News Intelligence V1.1 - Cluster Quality Hardening
Master Plan 18/26

Purpose:
- distinguish TRUE near-duplicate headline candidates from merely RELATED_EVENT candidates
- require stronger title similarity for duplicate collapse
- preserve looser same-event relationships separately
- audit SECURITY_INCIDENT headlines after false-positive hardening

READ ONLY portfolio_hub.db. Writes only its own JSON/CSV.
NO LLM. NO V3 writes. NO orders.
"""
import csv,json,os,re,sqlite3
from collections import Counter
from datetime import datetime,timezone
from difflib import SequenceMatcher
from pathlib import Path

BASE=Path(__file__).resolve().parent
DB=BASE/"portfolio_hub.db"
OUTJ=BASE/"zitar_news_intelligence_v1_1.json"
OUTC=BASE/"zitar_news_intelligence_v1_1.csv"

ASSETS={
"BTC":[r"\bbitcoin\b",r"\bbtc\b"],"ETH":[r"\bethereum\b",r"\bether\b",r"\beth\b"],
"SOL":[r"\bsolana\b",r"\bsol\b"],"XRP":[r"\bxrp\b",r"\bxrp ledger\b"],
"DOGE":[r"\bdogecoin\b",r"\bdoge\b"],"AVAX":[r"\bavalanche\b",r"\bavax\b"],
"NEAR":[r"\bnear protocol\b"],"PEPE":[r"\bpepe\b"],"TRUMP":[r"\bofficial trump\b",r"\$trump\b"],
"PENGU":[r"\bpengu\b",r"\bpudgy penguins\b"],"SAGA":[r"\bsaga protocol\b"],
"COTI":[r"\bcoti\b"],"MINA":[r"\bmina protocol\b"],"MUBARAK":[r"\bmubarak\b"],
"PHA":[r"\bphala\b"],"ENA":[r"\bethena\b"],"FORM":[r"\bform network\b"]}

EVENTS={
"LISTING_DELISTING":[r"\bdelist(?:s|ed|ing)?\b",r"\btrading pair\b",r"\blisting\b"],
"SECURITY_INCIDENT":[r"\bhacked\b",r"\bexploit(?:ed|s|ing)?\b",r"\bbreach\b",r"\bstolen\b",
                     r"\bcyberattack\b",r"\bsecurity incident\b"],
"REGULATION_LEGAL":[r"\bsec\b",r"\bcftc\b",r"\bregulat(?:or|ion|ory)\b",r"\blawsuit\b",r"\bcourt\b",r"\blegal\b"],
"ETF_INSTITUTIONAL":[r"\betf\b",r"\bblackrock\b",r"\bfidelity\b",r"\binstitutional\b"],
"LIQUIDATION_DERIVATIVES":[r"\bliquidation(?:s)?\b",r"\boptions\b",r"\bfutures\b",r"\bfunding rate\b",r"\bopen interest\b"],
"PROTOCOL_TECH":[r"\bupgrade\b",r"\bmainnet\b",r"\btestnet\b",r"\bprotocol\b",r"\bfork\b",r"\bfinality\b",r"\bvalidator\b"],
"TOKEN_SUPPLY_UNLOCK":[r"\btoken unlock\b",r"\bvesting\b"],
"MACRO_MARKET":[r"\bfed\b",r"\brate hike\b",r"\brate cut\b",r"\btreasury\b",r"\bbond yield\b",r"\binflation\b",r"\bcpi\b"],
"PARTNERSHIP_BUSINESS":[r"\bpartnership\b",r"\bpartners with\b",r"\bcollaboration\b",r"\bintegration\b"]}

STOP=set("""a an the and or but if then than as at by for from in into on onto of to with without is are was were be been
being has have had do does did will would can could may might this that these those it its their his her they them he she
we our you your crypto cryptocurrency blockchain token coin price market markets live update updates says said new after
before amid near over under more less up down""".split())

def norm(s):
    s=re.sub(r"[^a-z0-9$%]+"," ",(s or "").lower())
    return " ".join(x for x in s.split() if x not in STOP and len(x)>1)
def sim(a,b):
    a,b=norm(a),norm(b)
    if not a or not b:return 0.0
    A,B=set(a.split()),set(b.split())
    jac=len(A&B)/max(1,len(A|B))
    seq=SequenceMatcher(None,a,b).ratio()
    return max(jac,seq)
def assets(t):
    return [a for a,ps in ASSETS.items() if any(re.search(p,t,re.I) for p in ps)]
def events(t):
    out=[e for e,ps in EVENTS.items() if any(re.search(p,t,re.I) for p in ps)]
    # "Hack VC" alone cannot trigger SECURITY_INCIDENT; current rules already require actual incident verbs.
    return out
def ro():
    c=sqlite3.connect(f"file:{DB.as_posix()}?mode=ro",uri=True);c.row_factory=sqlite3.Row;return c
def atomic(p,o):
    q=p.with_suffix(p.suffix+".tmp")
    with q.open("w",encoding="utf-8") as h:
        json.dump(o,h,ensure_ascii=False,indent=2);h.flush()
        try:os.fsync(h.fileno())
        except OSError:pass
    q.replace(p)

def main():
    c=ro()
    try:
        rows=[dict(x) for x in c.execute(
          "SELECT source_id,published_at,title,intake_status FROM news_intake ORDER BY published_at,source_id")]
    finally:c.close()

    obs=[]
    for i,r in enumerate(rows):
        obs.append({"row_id":i+1,"source_id":r["source_id"],"published_at":r["published_at"],
                    "title":r["title"] or "","assets":assets(r["title"] or ""),
                    "event_types":events(r["title"] or ""),"duplicate_cluster":None})

    # Strict duplicate collapse:
    # 0.86 similarity AND asset context must be identical (or both market-wide).
    clusters=[];used=set()
    for i,a in enumerate(obs):
        if i in used:continue
        members=[i];used.add(i)
        for j in range(i+1,len(obs)):
            if j in used:continue
            b=obs[j]
            same_assets=set(a["assets"])==set(b["assets"])
            if same_assets and sim(a["title"],b["title"])>=0.86:
                members.append(j);used.add(j)
        cid=f"D{len(clusters)+1:04d}"
        for k in members:obs[k]["duplicate_cluster"]=cid
        clusters.append((cid,members))

    # Looser related-event candidates are NOT collapsed.
    related=[]
    for i in range(len(obs)):
        for j in range(i+1,len(obs)):
            if obs[i]["duplicate_cluster"]==obs[j]["duplicate_cluster"]:continue
            s=sim(obs[i]["title"],obs[j]["title"])
            common_assets=sorted(set(obs[i]["assets"]) & set(obs[j]["assets"]))
            if s>=0.68 and (common_assets or (not obs[i]["assets"] and not obs[j]["assets"])):
                related.append({"left_source_id":obs[i]["source_id"],"right_source_id":obs[j]["source_id"],
                                "similarity":round(s,4),"common_assets":common_assets,
                                "left_title":obs[i]["title"],"right_title":obs[j]["title"]})

    dup=[(cid,m) for cid,m in clusters if len(m)>1]
    security=[x for x in obs if "SECURITY_INCIDENT" in x["event_types"]]
    payload={"engine":"ZITAR_NEWS_INTELLIGENCE_V1_1","generated_utc":datetime.now(timezone.utc).isoformat(),
      "summary":{"rows":len(obs),"strict_duplicate_clusters":len(dup),
                 "rows_in_strict_duplicate_clusters":sum(len(m) for _,m in dup),
                 "related_event_candidates":len(related),
                 "security_incident_rows":len(security)},
      "method":{"strict_duplicate_similarity":0.86,"strict_duplicate_requires_identical_asset_set":True,
                "related_candidate_similarity":0.68,"related_candidates_are_not_collapsed":True},
      "integrity":{"source_db_write":False,"v3_write":False,"llm_used":False,
                   "execution_authority":False,"real_orders":False},
      "strict_duplicate_clusters":[{"cluster_id":cid,"source_ids":[obs[i]["source_id"] for i in m],
                                    "titles":[obs[i]["title"] for i in m]} for cid,m in dup],
      "related_event_candidates":related,"security_incident_audit":security,"observations":obs}
    atomic(OUTJ,payload)

    fields=["row_id","source_id","published_at","duplicate_cluster","assets","event_types","title"]
    q=OUTC.with_suffix(".csv.tmp")
    with q.open("w",encoding="utf-8-sig",newline="") as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader()
        for x in obs:w.writerow({**x,"assets":"|".join(x["assets"]),"event_types":"|".join(x["event_types"])})
        h.flush()
        try:os.fsync(h.fileno())
        except OSError:pass
    q.replace(OUTC)

    print("="*122)
    print("ZITAR NEWS INTELLIGENCE V1.1 - CLUSTER QUALITY HARDENING")
    print("="*122)
    print("READ ONLY SOURCE | V3 WRITE: NO | LLM: NO | REAL ORDERS: NO")
    print("NEWS ROWS                     :",len(obs))
    print("STRICT DUP CLUSTERS            :",len(dup))
    print("ROWS IN STRICT DUP CLUSTERS    :",sum(len(m) for _,m in dup))
    print("RELATED EVENT CANDIDATES       :",len(related))
    print("SECURITY INCIDENT ROWS         :",len(security))
    print("-"*122)
    print("STRICT DUPLICATES:")
    if not dup:print("  NONE")
    for cid,m in dup:
        print(f"  {cid} n={len(m)}")
        for i in m:print("    -",obs[i]["title"][:108])
    print("-"*122)
    print("RELATED BUT NOT COLLAPSED:")
    if not related:print("  NONE")
    for x in related[:20]:
        print(f"  sim={x['similarity']:.3f} assets={','.join(x['common_assets']) or 'MARKET_WIDE'}")
        print("    A:",x["left_title"][:104])
        print("    B:",x["right_title"][:104])
    print("-"*122)
    print("SECURITY INCIDENT AUDIT:")
    if not security:print("  NONE")
    for x in security:print("  -",x["title"][:112])
    print("-"*122)
    print("JSON:",OUTJ)
    print("CSV :",OUTC)
    print("RULE: STRICT DUPLICATE MAY COLLAPSE; RELATED EVENT CANDIDATE MUST NOT.")
    print("="*122)

if __name__=="__main__":main()
