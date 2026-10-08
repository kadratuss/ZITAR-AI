#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZİTAR News Intelligence Final Integrity Audit V1.1 - loader bugfix."""
import json, hashlib
from pathlib import Path

B=Path(__file__).resolve().parent
FILES={
 "news":B/"zitar_news_intelligence_v1_1.json",
 "radar":B/"zitar_event_news_radar_v2_4.json",
 "join":B/"zitar_news_market_join_v1_1.json",
}

def load(p):
    if not p.exists(): raise SystemExit(f"MISSING: {p.name}")
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise SystemExit(f"INVALID ROOT TYPE: {p.name} -> {type(x).__name__}")
    return x
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    # BUGFIX: do not unpack dict iteration (which returns keys/strings).
    docs={k:load(v) for k,v in FILES.items()}
    n,r,j=docs["news"],docs["radar"],docs["join"]
    checks=[]
    def ck(name,ok,detail): checks.append((name,bool(ok),detail))

    ns=n.get("summary",{}); rs=r.get("summary",{}); js=j.get("summary",{})
    ck("NEWS_ROWS_75",ns.get("rows")==75,f"rows={ns.get('rows')}")
    ck("RADAR_LINKS_24",rs.get("links")==24,f"links={rs.get('links')}")
    ck("RADAR_MEASURED_ALL",rs.get("measured")==rs.get("links"),f"measured={rs.get('measured')}/{rs.get('links')}")
    ck("RADAR_MISSING_ZERO",rs.get("missing")==0,f"missing={rs.get('missing')}")
    ck("JOIN_INPUT_24",js.get("radar_links_input")==24,f"input={js.get('radar_links_input')}")
    ck("JOIN_UNMATCHED_ZERO",js.get("unmatched_radar_links")==0,f"unmatched={js.get('unmatched_radar_links')}")
    ck("JOIN_CONFLICT_ZERO",js.get("within_unit_timing_conflicts")==0,f"conflicts={js.get('within_unit_timing_conflicts')}")
    ck("NO_STRICT_COLLAPSE_CURRENT_SAMPLE",js.get("strict_duplicate_evidence_collapsed")==0,f"collapsed={js.get('strict_duplicate_evidence_collapsed')}")
    ck("EVIDENCE_CONSERVATION",
       js.get("evidence_units",0)+js.get("strict_duplicate_evidence_collapsed",0)==js.get("radar_links_input"),
       f"units={js.get('evidence_units')} collapsed={js.get('strict_duplicate_evidence_collapsed')} input={js.get('radar_links_input')}")
    ck("PUMP_ZERO",rs.get("pump_confirmed")==0 and js.get("pump_confirmed")==0,
       f"radar={rs.get('pump_confirmed')} join={js.get('pump_confirmed')}")
    ck("BUY_ZERO",rs.get("buy_signals")==0 and js.get("buy_signals")==0,
       f"radar={rs.get('buy_signals')} join={js.get('buy_signals')}")

    ni=n.get("integrity",{}); ji=j.get("integrity",{})
    ck("NO_EXECUTION_AUTHORITY",ni.get("execution_authority") is False and ji.get("execution_authority") is False,
       f"news={ni.get('execution_authority')} join={ji.get('execution_authority')}")
    ck("NO_REAL_ORDERS",ni.get("real_orders") is False and ji.get("real_orders") is False,
       f"news={ni.get('real_orders')} join={ji.get('real_orders')}")
    ck("NO_V3_WRITE",ni.get("v3_write") is False and ji.get("v3_write") is False,
       f"news={ni.get('v3_write')} join={ji.get('v3_write')}")
    ck("NO_LLM_AUTHORITY",ni.get("llm_used") is False and ji.get("llm_used") is False,
       f"news_llm={ni.get('llm_used')} join_llm={ji.get('llm_used')}")

    units=j.get("units",[])
    ck("ALL_UNITS_NON_TRADING",
       all(u.get("pump_confirmed") is False and u.get("buy_signal") is False for u in units),
       f"units={len(units)}")
    related=js.get("related_units_preserved_independently",0)
    ck("RELATED_PRESERVED",related>=1 and js.get("evidence_units")==24,
       f"related_units={related} evidence_units={js.get('evidence_units')}")

    passed=sum(ok for _,ok,_ in checks)
    print("="*120)
    print("ZITAR NEWS INTELLIGENCE - FINAL INTEGRITY AUDIT V1.1")
    print("="*120)
    for name,ok,detail in checks:
        print(f"{'PASS' if ok else 'FAIL':<5} {name:<38} {detail}")
    print("-"*120)
    print(f"RESULT: {passed}/{len(checks)} PASS")
    print("ARTIFACT HASHES:")
    for k,q in FILES.items(): print(f"  {k:<6} {sha(q)}  {q.name}")
    print("-"*120)
    print("SUPERSEDED: zitar_news_integrity_audit_v1.py -> V1.1 (loader bug)")
    print("SUPERSEDED: zitar_news_market_join_v1.json -> V1.1 (cluster semantics)")
    print("RULE: NEWS != CAUSATION; RELATED != DUPLICATE; ANOMALY != PUMP; PUMP != BUY.")
    print("="*120)
    if passed != len(checks): raise SystemExit(1)

if __name__=="__main__": main()
