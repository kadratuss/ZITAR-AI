from __future__ import annotations
import json, re
from pathlib import Path
from datetime import datetime, timezone

BASE=Path(__file__).resolve().parent
SPOT=BASE/"zitar_liquidity_profile_v1.json"
FUTURES=BASE/"zitar_futures_intelligence_profile_v1.json"
FUTURES_SNAPSHOT=BASE/"zitar_futures_intelligence_snapshot_v1_1.json"
EVIDENCE=BASE/"zitar_futures_evidence_v1.json"
OUT=BASE/"zitar_finance_unified_bridge_v1.json"
TEST=BASE/"zitar_finance_unified_bridge_test_v1.json"

def read_json(path):
    if not path.exists(): return None
    try: return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception: return None

def walk(obj):
    if isinstance(obj,dict):
        yield obj
        for v in obj.values(): yield from walk(v)
    elif isinstance(obj,list):
        for v in obj: yield from walk(v)

def symbol_hits(obj,symbol):
    out=[]
    for d in walk(obj):
        if str(d.get("symbol","")).upper()==symbol:
            out.append(d)
    return out

def first_value(dicts,keys):
    for d in dicts:
        for k in keys:
            if k in d and d[k] is not None: return d[k]
    return None

def build(symbol="BTCUSDT"):
    futures=read_json(FUTURES) or read_json(FUTURES_SNAPSHOT)
    evidence=read_json(EVIDENCE)
    spot=read_json(SPOT)
    fh=symbol_hits(futures,symbol) if futures else []
    eh=symbol_hits(evidence,symbol) if evidence else []
    sh=symbol_hits(spot,"BTCTRY") if spot else []

    funding=first_value(fh,("funding","funding_rate","last_funding_rate"))
    basis=first_value(fh,("basis_bps","basis","basisBps"))
    oi=first_value(fh,("oi24h_pct","oi_24h_pct","open_interest_change_24h_pct"))
    ls=first_value(fh,("long_short_ratio","ls_ratio","global_long_short_ratio"))
    taker=first_value(fh,("taker","taker_ratio","taker_buy_sell_ratio"))
    conclusion=first_value(eh,("conclusion","directional_conclusion"))
    temporal=first_value(eh,("temporal_status","temporal"))
    observations=first_value(eh,("observations","observation_count","obs"))

    metrics={"funding":funding,"basis_bps":basis,"oi24h_pct":oi,
             "long_short_ratio":ls,"taker_ratio":taker}
    available=sum(v is not None for v in metrics.values())

    # V1 bridge transports evidence only. It must not manufacture LONG/SHORT.
    directional_allowed = bool(
        conclusion and str(conclusion).upper() not in
        ("NO_LONG_SHORT_CONCLUSION","NOT_SCORED","INSUFFICIENT_OBSERVATIONS")
    )

    status="EVIDENCE_AVAILABLE" if available else "NO_CURRENT_FINANCE_EVIDENCE"
    if not directional_allowed:
        direction="NO_DIRECTIONAL_CONCLUSION"
    else:
        direction=str(conclusion)

    return {
      "schema":"ZITAR_FINANCE_UNIFIED_BRIDGE_V1",
      "created_utc":datetime.now(timezone.utc).isoformat(),
      "requested_symbol":symbol,
      "status":status,
      "source_files":{
        "futures":str(FUTURES if FUTURES.exists() else FUTURES_SNAPSHOT),
        "evidence":str(EVIDENCE),
        "spot_liquidity":str(SPOT)
      },
      "evidence":{
        **metrics,
        "temporal_status":temporal,
        "observation_count":observations,
        "spot_liquidity_records_found":len(sh)
      },
      "policy":{
        "evidence_transport_only":True,
        "directional_allowed":directional_allowed,
        "directional_conclusion":direction,
        "qwen_may_invent_missing_values":False,
        "real_order_authority":False
      }
    }

def main():
    bundle=build()
    OUT.write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding="utf-8")

    checks={
      "schema":bundle["schema"]=="ZITAR_FINANCE_UNIFIED_BRIDGE_V1",
      "no_order_authority":bundle["policy"]["real_order_authority"] is False,
      "no_missing_value_invention":bundle["policy"]["qwen_may_invent_missing_values"] is False,
      "direction_guard":(
          bundle["policy"]["directional_allowed"]
          or bundle["policy"]["directional_conclusion"]=="NO_DIRECTIONAL_CONCLUSION"
      ),
      "source_provenance_present":all(bundle["source_files"].values()),
      "status_valid":bundle["status"] in ("EVIDENCE_AVAILABLE","NO_CURRENT_FINANCE_EVIDENCE"),
    }
    passed=sum(checks.values())
    TEST.write_text(json.dumps({"schema":"ZITAR_FINANCE_UNIFIED_BRIDGE_TEST_V1",
      "checks":checks,"passed":passed,"total":len(checks),"bundle":bundle},
      ensure_ascii=False,indent=2),encoding="utf-8")

    print("ZITAR FINANCE -> UNIFIED CORE BRIDGE V1")
    print("EVIDENCE TRANSPORT ONLY • NO ORDER • NO INVENTED DIRECTION")
    print("status:",bundle["status"])
    for k,v in bundle["evidence"].items(): print(f"{k}: {v}")
    print("directional allowed:",bundle["policy"]["directional_allowed"])
    print("direction:",bundle["policy"]["directional_conclusion"])
    print(f"validation: {passed}/{len(checks)}")
    print("bridge:",OUT)
    print("test:",TEST)
    print("STATUS:","PASS" if passed==len(checks) else "FAIL")

if __name__=="__main__":
    main()
