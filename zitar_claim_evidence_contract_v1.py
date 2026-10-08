from __future__ import annotations
import json, hashlib, uuid
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "zitar_claim_evidence_contract_v1.json"

ALLOWED = {
    "MARKET_DATA","DERIVED_ANALYSIS","MEMORY",
    "EXTERNAL_EVIDENCE","INFERENCE","DECISION_EXECUTION"
}

def canonical_hash(obj):
    raw=json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def evidence(category, producer, locator, observed_at=None):
    if category not in ALLOWED:
        raise ValueError(f"Unknown category: {category}")
    return {
        "category": category,
        "producer": producer,
        "locator": locator,
        "observed_at": observed_at,
    }

def claim(text, claim_type, evidence_refs, limitations=None):
    return {
        "claim_id": str(uuid.uuid4()),
        "text": text,
        "claim_type": claim_type,
        "evidence_refs": evidence_refs,
        "limitations": limitations or [],
    }

def main():
    prov = json.loads((BASE/"zitar_provenance_v1.json").read_text(encoding="utf-8"))
    reg = json.loads((BASE/"zitar_provenance_registry_v1.json").read_text(encoding="utf-8"))

    sample_evidence = {
        "ev_mtf": evidence("DERIVED_ANALYSIS","zitar_mtf_research_v2.py","BTCTRY/timeframes"),
        "ev_mem": evidence("MEMORY","zitar_research_memory_v1.jsonl","BTCTRY/latest"),
        "ev_news": evidence("EXTERNAL_EVIDENCE","News Intelligence","BTCTRY/relevant"),
        "ev_event": evidence("EXTERNAL_EVIDENCE","Event Radar","BTCTRY/temporal-window"),
    }

    sample_claims = [
        claim(
            "BTC çoklu zaman dilimi görünümü karışık.",
            "DESCRIPTIVE",
            ["ev_mtf"],
            ["Yön tahmini değildir."]
        ),
        claim(
            "Mevcut kayıt tek başına kalıcı görüş değişimini desteklemiyor.",
            "INFERENCE",
            ["ev_mtf","ev_mem"],
            ["Memory geçmiş ZİTAR durumudur; doğruluğun bağımsız kanıtı değildir."]
        ),
        claim(
            "Haber ve fiyat hareketi arasında zamansal ilişki incelenebilir; bu tek başına nedensellik kanıtı değildir.",
            "CAUSALITY_LIMIT",
            ["ev_news","ev_event"],
            ["Temporal association != causation."]
        ),
    ]

    contract = {
        "schema":"ZITAR_CLAIM_EVIDENCE_CONTRACT_V1",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "provenance_schema_sha256":prov.get("schema_sha256"),
        "registry_sha256":reg.get("registry_sha256"),
        "requirements":{
            "claim_requires_evidence_refs":True,
            "evidence_requires_category":True,
            "evidence_requires_producer":True,
            "inference_must_be_labeled":True,
            "causality_requires_explicit_limitation":True,
            "execution_separate_from_research":True,
            "self_improvement_must_record_input_claims":True,
            "self_improvement_must_preserve_failed_candidates":True,
        },
        "sample":{
            "evidence":sample_evidence,
            "claims":sample_claims
        }
    }

    # Validation
    known={(x["category"],x["producer"]) for x in reg["entries"]}
    errors=[]
    for eid,e in sample_evidence.items():
        if (e["category"],e["producer"]) not in known:
            errors.append(f"UNREGISTERED:{eid}:{e['category']}:{e['producer']}")
    for c in sample_claims:
        if not c["evidence_refs"]:
            errors.append(f"NO_EVIDENCE:{c['claim_id']}")
        for ref in c["evidence_refs"]:
            if ref not in sample_evidence:
                errors.append(f"BROKEN_REF:{c['claim_id']}:{ref}")
        if c["claim_type"]=="INFERENCE" and not c["limitations"]:
            errors.append(f"UNLABELED_INFERENCE:{c['claim_id']}")
        if c["claim_type"]=="CAUSALITY_LIMIT" and not any("causation" in x.lower() for x in c["limitations"]):
            errors.append(f"CAUSALITY_LIMIT_MISSING:{c['claim_id']}")

    contract["contract_sha256"]=canonical_hash(contract["requirements"])
    contract["validation_errors"]=errors
    OUT.write_text(json.dumps(contract,ensure_ascii=False,indent=2),encoding="utf-8")

    print("ZİTAR CLAIM/EVIDENCE CONTRACT V1")
    print("READ ONLY • NO V3 WRITE • NO ORDER AUTHORITY")
    print("evidence:",len(sample_evidence))
    print("claims:",len(sample_claims))
    print("requirements:",len(contract["requirements"]))
    print("validation_errors:",len(errors))
    for e in errors: print(" ",e)
    print("contract_sha256:",contract["contract_sha256"])
    print("output:",OUT)
    print("STATUS:","PASS" if not errors else "FAIL")

if __name__=="__main__":
    main()
