#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR News Intelligence V1
Master Plan 18/26

Deterministic, read-only news intelligence layer over portfolio_hub.db/news_intake.
Adds:
- source/time provenance
- conservative asset relevance
- context-aware event classification
- known false-positive hardening ("Hack VC" != cyber incident)
- exact + near-duplicate clustering
- cluster-level evidence preservation

NO LLM. NO trading authority. NO V3 writes. NO source DB writes. NO orders.
"""
import csv, json, os, re, sqlite3, hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

BASE=Path(__file__).resolve().parent
DB=BASE/"portfolio_hub.db"
OUTJ=BASE/"zitar_news_intelligence_v1.json"
OUTC=BASE/"zitar_news_intelligence_v1.csv"

ASSET_PATTERNS={
 "BTC":[r"\bbitcoin\b",r"\bbtc\b"],
 "ETH":[r"\bethereum\b",r"\bether\b",r"\beth\b"],
 "SOL":[r"\bsolana\b",r"\bsol\b"],
 "XRP":[r"\bxrp\b",r"\bxrp ledger\b"],
 "DOGE":[r"\bdogecoin\b",r"\bdoge\b"],
 "AVAX":[r"\bavalanche\b",r"\bavax\b"],
 "NEAR":[r"\bnear protocol\b",r"\bnear\b"],
 "PEPE":[r"\bpepe\b"],
 "TRUMP":[r"\btrump token\b",r"\bofficial trump\b",r"\$trump\b"],
 "PENGU":[r"\bpengu\b",r"\bpudgy penguins\b"],
 "SAGA":[r"\bsaga protocol\b",r"\bsaga\b"],
 "COTI":[r"\bcoti\b"],
 "MINA":[r"\bmina protocol\b",r"\bmina\b"],
 "MUBARAK":[r"\bmubarak\b"],
 "PHA":[r"\bphala\b",r"\bpha\b"],
 "ENA":[r"\bethena\b",r"\bena\b"],
 "FORM":[r"\bform network\b",r"\bform\b"],
}

EVENT_RULES={
 "LISTING_DELISTING":[
   r"\blist(?:s|ed|ing)?\b",r"\bdelist(?:s|ed|ing)?\b",r"\btrading pair\b"],
 "SECURITY_INCIDENT":[
   r"\bhacked\b",r"\bhack(?:ing)?\b",r"\bexploit(?:ed|s|ing)?\b",r"\bbreach\b",
   r"\bstolen\b",r"\bcyberattack\b",r"\bsecurity incident\b"],
 "REGULATION_LEGAL":[
   r"\bsec\b",r"\bcftc\b",r"\bregulat(?:or|ion|ory)\b",r"\blawsuit\b",
   r"\bcourt\b",r"\blegal\b",r"\bcongress\b"],
 "ETF_INSTITUTIONAL":[
   r"\betf\b",r"\binstitutional\b",r"\bblackrock\b",r"\bfidelity\b"],
 "LIQUIDATION_DERIVATIVES":[
   r"\bliquidation(?:s)?\b",r"\boptions\b",r"\bfutures\b",r"\bfunding rate\b",
   r"\bopen interest\b"],
 "PROTOCOL_TECH":[
   r"\bupgrade\b",r"\bmainnet\b",r"\btestnet\b",r"\bprotocol\b",r"\bfork\b",
   r"\bfinality\b",r"\bvalidator\b"],
 "TOKEN_SUPPLY_UNLOCK":[
   r"\btoken unlock\b",r"\bunlock(?:s|ed|ing)?\b",r"\bvesting\b",r"\bsupply\b"],
 "MACRO_MARKET":[
   r"\bfed\b",r"\brate hike\b",r"\brate cut\b",r"\btreasury\b",r"\bbond yield\b",
   r"\binflation\b",r"\bcpi\b"],
 "PARTNERSHIP_BUSINESS":[
   r"\bpartnership\b",r"\bpartners with\b",r"\bcollaboration\b",r"\bintegration\b"],
}

STOP=set("""a an the and or but if then than as at by for from in into on onto of to with without
is are was were be been being has have had do does did will would can could may might
this that these those it its their his her they them he she we our you your
crypto cryptocurrency blockchain token coin price market markets live update updates
says said new after before amid near over under more less up down""".split())

def ro():
    c=sqlite3.connect(f"file:{DB.as_posix()}?mode=ro",uri=True)
    c.row_factory=sqlite3.Row
    return c

def norm_title(s):
    s=(s or "").lower()
    s=re.sub(r"https?://\S+"," ",s)
    s=re.sub(r"[^a-z0-9$%]+"," ",s)
    toks=[x for x in s.split() if x not in STOP and len(x)>1]
    return " ".join(toks)

def tokens(s):
    return set(norm_title(s).split())

def classify_assets(title):
    t=(title or "").lower()
    found=[]
    for asset,pats in ASSET_PATTERNS.items():
        if any(re.search(p,t,re.I) for p in pats):
            found.append(asset)
    return found

def classify_events(title):
    t=(title or "").lower()
    out=[]
    for typ,pats in EVENT_RULES.items():
        if any(re.search(p,t,re.I) for p in pats):
            out.append(typ)

    # Known contextual false-positive hardening:
    # "Hack VC" is a venture-capital firm name, not proof of a security incident.
    if "SECURITY_INCIDENT" in out and "hack vc" in t:
        real_security=any(re.search(p,t,re.I) for p in [
            r"\bhacked\b",r"\bexploit(?:ed|s|ing)?\b",r"\bbreach\b",
            r"\bstolen\b",r"\bcyberattack\b",r"\bsecurity incident\b"])
        if not real_security:
            out.remove("SECURITY_INCIDENT")
    return out

def similarity(a,b):
    na,nb=norm_title(a),norm_title(b)
    if not na or not nb:return 0.0
    ta,tb=set(na.split()),set(nb.split())
    jac=len(ta&tb)/max(1,len(ta|tb))
    seq=SequenceMatcher(None,na,nb).ratio()
    return max(jac,seq)

def parse_time(v):
    if not v:return None
    try:
        d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
        if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except:return None

def atomic_json(p,obj):
    tmp=p.with_suffix(p.suffix+".tmp")
    with tmp.open("w",encoding="utf-8") as h:
        json.dump(obj,h,ensure_ascii=False,indent=2);h.flush()
        try:os.fsync(h.fileno())
        except OSError:pass
    tmp.replace(p)

def main():
    if not DB.exists():raise SystemExit("portfolio_hub.db not found")
    c=ro()
    try:
        cols={r["name"] for r in c.execute('PRAGMA table_info("news_intake")')}
        required={"source_id","collected_at","detected_at","published_at","title","intake_status"}
        if not required.issubset(cols):
            raise SystemExit("news_intake schema mismatch: "+str(sorted(cols)))
        rows=[dict(r) for r in c.execute(
            'SELECT source_id,collected_at,detected_at,published_at,title,intake_status '
            'FROM news_intake ORDER BY published_at, source_id'
        )]
    finally:c.close()

    obs=[]
    for i,r in enumerate(rows):
        pub=parse_time(r["published_at"])
        title=r["title"] or ""
        obs.append({
          "row_id":i+1,
          "source_id":r["source_id"],
          "published_utc":pub.isoformat() if pub else r["published_at"],
          "collected_at":r["collected_at"],
          "detected_at":r["detected_at"],
          "intake_status":r["intake_status"],
          "title":title,
          "normalized_title":norm_title(title),
          "assets":classify_assets(title),
          "event_types":classify_events(title),
          "cluster_id":None,
          "cluster_relation":"UNASSIGNED",
          "cluster_similarity":None,
        })

    # Conservative clustering: same/overlapping asset context OR both market-wide,
    # plus high title similarity. Prevent unrelated crypto headlines from merging.
    clusters=[]
    assigned=set()
    for i,a in enumerate(obs):
        if i in assigned:continue
        cid=f"N{len(clusters)+1:04d}"
        members=[i];assigned.add(i)
        for j in range(i+1,len(obs)):
            if j in assigned:continue
            b=obs[j]
            asset_compatible=bool(set(a["assets"]) & set(b["assets"])) or (not a["assets"] and not b["assets"])
            if not asset_compatible:continue
            sim=similarity(a["title"],b["title"])
            if sim>=0.72:
                members.append(j);assigned.add(j)
        clusters.append((cid,members))

    for cid,members in clusters:
        base=obs[members[0]]
        for k,idx in enumerate(members):
            x=obs[idx]
            sim=1.0 if k==0 else similarity(base["title"],x["title"])
            x["cluster_id"]=cid
            x["cluster_similarity"]=round(sim,4)
            x["cluster_relation"]="PRIMARY" if k==0 else ("EXACT_OR_VERY_NEAR" if sim>=0.90 else "NEAR_DUPLICATE")

    cluster_out=[]
    for cid,members in clusters:
        xs=[obs[i] for i in members]
        all_assets=sorted(set(a for x in xs for a in x["assets"]))
        all_events=sorted(set(e for x in xs for e in x["event_types"]))
        cluster_out.append({
          "cluster_id":cid,
          "member_count":len(xs),
          "assets":all_assets,
          "event_types":all_events,
          "first_published_utc":min((x["published_utc"] for x in xs if x["published_utc"]),default=None),
          "source_ids":[x["source_id"] for x in xs],
          "primary_title":xs[0]["title"],
          "titles":[x["title"] for x in xs],
        })

    event_counts=Counter(e for x in obs for e in x["event_types"])
    asset_counts=Counter(a for x in obs for a in x["assets"])
    duplicate_clusters=[x for x in cluster_out if x["member_count"]>1]
    unmapped=[x for x in obs if not x["assets"]]
    unclassified=[x for x in obs if not x["event_types"]]

    payload={
      "engine":"ZITAR_NEWS_INTELLIGENCE_V1",
      "generated_utc":datetime.now(timezone.utc).isoformat(),
      "summary":{
        "news_rows":len(obs),
        "clusters":len(cluster_out),
        "duplicate_or_near_duplicate_clusters":len(duplicate_clusters),
        "rows_in_duplicate_clusters":sum(x["member_count"] for x in duplicate_clusters),
        "asset_mapped_rows":len(obs)-len(unmapped),
        "asset_unmapped_rows":len(unmapped),
        "event_classified_rows":len(obs)-len(unclassified),
        "event_unclassified_rows":len(unclassified),
      },
      "asset_counts":dict(sorted(asset_counts.items())),
      "event_counts":dict(sorted(event_counts.items())),
      "integrity":{
        "source_db_write":False,
        "v3_write":False,
        "llm_used":False,
        "execution_authority":False,
        "real_orders":False,
        "rules":[
          "Classification is deterministic and descriptive.",
          "A headline match is not proof that the event caused a market move.",
          "Near-duplicate headlines are clustered so one event is not counted as independent evidence twice.",
          "Unmapped/unclassified news is preserved rather than forced into a category.",
          "Known phrase 'Hack VC' alone does not establish a security incident."
        ]
      },
      "clusters":cluster_out,
      "observations":obs,
    }
    atomic_json(OUTJ,payload)

    fields=["row_id","source_id","published_utc","cluster_id","cluster_relation","cluster_similarity",
            "assets","event_types","intake_status","title"]
    tmp=OUTC.with_suffix(".csv.tmp")
    with tmp.open("w",encoding="utf-8-sig",newline="") as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader()
        for x in obs:
            w.writerow({
              "row_id":x["row_id"],"source_id":x["source_id"],"published_utc":x["published_utc"],
              "cluster_id":x["cluster_id"],"cluster_relation":x["cluster_relation"],
              "cluster_similarity":x["cluster_similarity"],"assets":"|".join(x["assets"]),
              "event_types":"|".join(x["event_types"]),"intake_status":x["intake_status"],"title":x["title"]
            })
        h.flush()
        try:os.fsync(h.fileno())
        except OSError:pass
    tmp.replace(OUTC)

    print("="*120)
    print("ZITAR NEWS INTELLIGENCE V1 - MASTER PLAN 18/26")
    print("="*120)
    print("READ ONLY SOURCE | V3 WRITE: NO | LLM: NO | REAL ORDERS: NO")
    print("NEWS ROWS                  :",len(obs))
    print("CLUSTERS                   :",len(cluster_out))
    print("DUP/NEAR-DUP CLUSTERS      :",len(duplicate_clusters))
    print("ROWS IN DUP CLUSTERS       :",sum(x["member_count"] for x in duplicate_clusters))
    print("ASSET MAPPED               :",len(obs)-len(unmapped))
    print("ASSET UNMAPPED             :",len(unmapped))
    print("EVENT CLASSIFIED           :",len(obs)-len(unclassified))
    print("EVENT UNCLASSIFIED         :",len(unclassified))
    print("-"*120)
    print("EVENT COUNTS:")
    for k,v in event_counts.most_common():print(f"  {k:<28} {v}")
    print("-"*120)
    print("DUPLICATE / NEAR-DUPLICATE CLUSTERS:")
    if not duplicate_clusters:print("  NONE")
    for cl in duplicate_clusters[:20]:
        print(f"  {cl['cluster_id']} n={cl['member_count']} assets={','.join(cl['assets']) or 'MARKET_WIDE'}")
        for t in cl["titles"][:5]:print("    -",t[:105])
    print("-"*120)
    print("JSON:",OUTJ)
    print("CSV :",OUTC)
    print("RULE: NEWS != CAUSATION; DUPLICATE NEWS != INDEPENDENT EVIDENCE; NEWS != BUY/SELL.")
    print("="*120)

if __name__=="__main__":main()
