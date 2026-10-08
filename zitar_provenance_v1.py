from __future__ import annotations
import json, hashlib
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "zitar_provenance_v1.json"

SCHEMA = {
    "schema": "ZITAR_PROVENANCE_V1",
    "principle": "FACT != DERIVED != MEMORY != EXTERNAL_EVIDENCE != INFERENCE != DECISION",
    "categories": {
        "MARKET_DATA": {
            "meaning": "Ham/ölçülmüş piyasa verisi",
            "examples": ["OHLCV", "bookTicker", "timeframe candle"]
        },
        "DERIVED_ANALYSIS": {
            "meaning": "Ham veriden deterministik hesaplanan analiz",
            "examples": ["MTF trend", "momentum", "ATR/volatility", "timeframe agreement"]
        },
        "MEMORY": {
            "meaning": "ZİTAR'ın sürümlenmiş geçmiş gözlem/görüş kayıtları",
            "examples": ["research memory", "opinion version", "change status"]
        },
        "EXTERNAL_EVIDENCE": {
            "meaning": "Dış kaynaktan alınmış kanıt",
            "examples": ["news", "event", "web research"]
        },
        "INFERENCE": {
            "meaning": "Kanıtlardan türetilen yorum; kaynak veri değildir",
            "examples": ["causality limitation", "evidence synthesis", "hypothesis"]
        },
        "DECISION_EXECUTION": {
            "meaning": "Karar/emir katmanı; araştırma kanıtından ayrı tutulur",
            "examples": ["paper decision", "risk gate", "execution action"]
        }
    },
    "hard_rules": [
        "Every claim must be traceable to one or more provenance categories.",
        "Inference must never be relabeled as measured fact.",
        "Temporal association must never be relabeled as causation without evidence.",
        "Memory is evidence of prior ZITAR state, not proof that the prior view was correct.",
        "AI-generated wording is presentation/inference, not a primary evidence source.",
        "Execution authority must remain separate from research provenance.",
        "Self-improvement candidates may not erase provenance or audit history."
    ]
}

def canonical_hash(obj):
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def main():
    payload = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        **SCHEMA
    }
    payload["schema_sha256"] = canonical_hash(SCHEMA)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("ZİTAR PROVENANCE V1")
    print("READ ONLY • NO V3 WRITE • NO ORDER AUTHORITY")
    print("schema:", payload["schema"])
    print("categories:", len(payload["categories"]))
    for k, v in payload["categories"].items():
        print(f"  {k:<20} -> {v['meaning']}")
    print("hard_rules:", len(payload["hard_rules"]))
    print("sha256:", payload["schema_sha256"])
    print("output:", OUT)
    print("STATUS: PASS")

if __name__ == "__main__":
    main()
