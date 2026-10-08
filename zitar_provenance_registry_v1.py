from __future__ import annotations
import json, hashlib
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
OUT = BASE / "zitar_provenance_registry_v1.json"

# Existing ZİTAR evidence producers -> provenance categories.
# Read-only registry: does not modify any producer or database.
REGISTRY = [
    {
        "producer": "portfolio_hub.db/timeframe_candles",
        "category": "MARKET_DATA",
        "role": "Stored multi-timeframe OHLCV observations",
        "primary": True,
    },
    {
        "producer": "learning_lab.db/candles",
        "category": "MARKET_DATA",
        "role": "Stored research OHLCV observations",
        "primary": True,
    },
    {
        "producer": "long_history.db/historical_candles",
        "category": "MARKET_DATA",
        "role": "Historical OHLCV observations",
        "primary": True,
    },
    {
        "producer": "zitar_mtf_research_v2.py",
        "category": "DERIVED_ANALYSIS",
        "role": "Deterministic timeframe trend/momentum/volatility synthesis",
        "primary": False,
    },
    {
        "producer": "zitar_research_memory_v1.jsonl",
        "category": "MEMORY",
        "role": "Append-only versioned research memory",
        "primary": False,
    },
    {
        "producer": "zitar_research_opinion_v1.py",
        "category": "MEMORY",
        "role": "Versioned deterministic opinion state/change status",
        "primary": False,
    },
    {
        "producer": "Event Radar",
        "category": "EXTERNAL_EVIDENCE",
        "role": "Measured event/price temporal evidence; not causality",
        "primary": False,
    },
    {
        "producer": "News Intelligence",
        "category": "EXTERNAL_EVIDENCE",
        "role": "News evidence and deduplication/relationship metadata",
        "primary": False,
    },
    {
        "producer": "ZITAR Chat canonical synthesis",
        "category": "INFERENCE",
        "role": "Evidence-grounded synthesis/presentation; not primary evidence",
        "primary": False,
    },
    {
        "producer": "Qwen narrator",
        "category": "INFERENCE",
        "role": "Language/presentation candidate subject to guards",
        "primary": False,
    },
    {
        "producer": "V3 paper risk/execution",
        "category": "DECISION_EXECUTION",
        "role": "Paper decision/risk/execution state, isolated from research evidence",
        "primary": False,
    },
]

def sha(obj):
    raw=json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
    return hashlib.sha256(raw).hexdigest()

def main():
    schema_path=BASE/"zitar_provenance_v1.json"
    if not schema_path.exists():
        raise SystemExit("FAIL: zitar_provenance_v1.json bulunamadı.")
    schema=json.loads(schema_path.read_text(encoding="utf-8"))
    allowed=set(schema["categories"])
    errors=[]
    for x in REGISTRY:
        if x["category"] not in allowed:
            errors.append(f"UNKNOWN_CATEGORY:{x['producer']}:{x['category']}")
    payload={
        "schema":"ZITAR_PROVENANCE_REGISTRY_V1",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "provenance_schema_sha256":schema.get("schema_sha256"),
        "entries":REGISTRY,
        "hard_separations":[
            "MARKET_DATA != DERIVED_ANALYSIS",
            "EXTERNAL_EVIDENCE != CAUSATION",
            "MEMORY != VERIFIED_TRUTH",
            "INFERENCE != PRIMARY_EVIDENCE",
            "DECISION_EXECUTION != RESEARCH_EVIDENCE",
        ],
    }
    payload["registry_sha256"]=sha(payload["entries"])
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

    counts={}
    for x in REGISTRY: counts[x["category"]]=counts.get(x["category"],0)+1
    print("ZİTAR PROVENANCE REGISTRY V1")
    print("READ ONLY • NO V3 WRITE • NO ORDER AUTHORITY")
    print("entries:",len(REGISTRY))
    for k in sorted(allowed): print(f"  {k:<20}: {counts.get(k,0)}")
    print("schema_sha256:",payload["provenance_schema_sha256"])
    print("registry_sha256:",payload["registry_sha256"])
    print("errors:",len(errors))
    for e in errors: print(" ",e)
    print("output:",OUT)
    print("STATUS:","PASS" if not errors else "FAIL")

if __name__=="__main__":
    main()
