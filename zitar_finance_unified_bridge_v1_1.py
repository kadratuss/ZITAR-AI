from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone

BASE=Path(__file__).resolve().parent
EVIDENCE=BASE/"zitar_futures_evidence_v1.json"
OUT=BASE/"zitar_finance_unified_bridge_v1_1.json"
TEST=BASE/"zitar_finance_unified_bridge_test_v1_1.json"

CHANNEL_MAP={
    "FUNDING":("funding","value"),
    "BASIS":("basis_bps","value_bps"),
    "OI_24H_CHANGE":("oi24h_pct","value_pct"),
    "GLOBAL_LONG_SHORT":("long_short_ratio","value"),
    "TAKER_BUY_SELL":("taker_ratio","value"),
}

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def build(symbol="BTCUSDT"):
    doc=read_json(EVIDENCE)
    rec=next((x for x in doc.get("symbols",[]) if x.get("symbol")==symbol),None)
    if not rec:
        return {"schema":"ZITAR_FINANCE_UNIFIED_BRIDGE_V1_1","requested_symbol":symbol,
                "status":"SYMBOL_NOT_FOUND","policy":{"real_order_authority":False}}

    metrics={k:None for k,_ in CHANNEL_MAP.values()}
    states={}
    for ev in rec.get("evidence",[]):
        ch=ev.get("channel")
        if ch in CHANNEL_MAP:
            out_key,value_key=CHANNEL_MAP[ch]
            metrics[out_key]=ev.get(value_key)
            states[out_key]=ev.get("state")

    temporal=rec.get("temporal") or {}
    conclusion=rec.get("conclusion")
    agreement=rec.get("agreement")
    temporal_ok=temporal.get("status") not in (None,"INSUFFICIENT_OBSERVATIONS")
    conclusion_ok=conclusion not in (None,"NO_LONG_SHORT_CONCLUSION")
    agreement_ok=agreement not in (None,"NOT_SCORED")
    directional_allowed=bool(temporal_ok and conclusion_ok and agreement_ok)

    return {
      "schema":"ZITAR_FINANCE_UNIFIED_BRIDGE_V1_1",
      "created_utc":datetime.now(timezone.utc).isoformat(),
      "requested_symbol":symbol,
      "status":"EVIDENCE_AVAILABLE" if any(v is not None for v in metrics.values()) else "NO_CURRENT_FINANCE_EVIDENCE",
      "source":{
        "file":str(EVIDENCE),
        "schema":doc.get("schema"),
        "generated_utc":doc.get("generated_utc"),
        "source_log":doc.get("source_log"),
        "global_observation_count":doc.get("observation_count"),
        "minimum_observations_for_temporal_assessment":doc.get("minimum_observations_for_temporal_assessment"),
        "latest_observed_utc":rec.get("latest_observed_utc"),
        "source_status":rec.get("source_status"),
      },
      "evidence":{**metrics,"states":states},
      "temporal":temporal,
      "agreement":agreement,
      "source_conclusion":conclusion,
      "policy":{
        "evidence_transport_only":True,
        "directional_allowed":directional_allowed,
        "directional_conclusion":conclusion if directional_allowed else "NO_DIRECTIONAL_CONCLUSION",
        "qwen_may_invent_missing_values":False,
        "qwen_may_upgrade_evidence_to_signal":False,
        "real_order_authority":False,
      }
    }

def main():
    b=build()
    OUT.write_text(json.dumps(b,ensure_ascii=False,indent=2),encoding="utf-8")
    ev=b.get("evidence",{})
    checks={
      "evidence_file_loaded":b.get("source",{}).get("schema")=="ZITAR_FUTURES_EVIDENCE_V1",
      "btc_metrics_complete":all(ev.get(k) is not None for k in ("funding","basis_bps","oi24h_pct","long_short_ratio","taker_ratio")),
      "temporal_observations_found":b.get("temporal",{}).get("observations")==2,
      "insufficient_temporal_blocks_direction":(
          b.get("temporal",{}).get("status")=="INSUFFICIENT_OBSERVATIONS"
          and b["policy"]["directional_allowed"] is False
          and b["policy"]["directional_conclusion"]=="NO_DIRECTIONAL_CONCLUSION"
      ),
      "no_signal_upgrade":b["policy"]["qwen_may_upgrade_evidence_to_signal"] is False,
      "no_order_authority":b["policy"]["real_order_authority"] is False,
      "status_evidence_available":b.get("status")=="EVIDENCE_AVAILABLE",
    }
    passed=sum(checks.values())
    TEST.write_text(json.dumps({"schema":"ZITAR_FINANCE_UNIFIED_BRIDGE_TEST_V1_1",
      "checks":checks,"passed":passed,"total":len(checks),"bundle":b},ensure_ascii=False,indent=2),encoding="utf-8")

    print("ZITAR FINANCE -> UNIFIED CORE BRIDGE V1.1")
    print("REAL EVIDENCE SCHEMA • EVIDENCE ONLY • NO ORDER")
    print("status:",b["status"])
    for k in ("funding","basis_bps","oi24h_pct","long_short_ratio","taker_ratio"):
        print(f"{k}: {ev.get(k)}")
    print("temporal status:",b.get("temporal",{}).get("status"))
    print("observations:",b.get("temporal",{}).get("observations"))
    print("agreement:",b.get("agreement"))
    print("source conclusion:",b.get("source_conclusion"))
    print("directional allowed:",b["policy"]["directional_allowed"])
    print("direction:",b["policy"]["directional_conclusion"])
    print(f"validation: {passed}/{len(checks)}")
    print("bridge:",OUT)
    print("test:",TEST)
    print("STATUS:","PASS" if passed==len(checks) else "FAIL")

if __name__=="__main__":
    main()
