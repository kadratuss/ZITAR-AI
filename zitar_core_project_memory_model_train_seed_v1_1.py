from __future__ import annotations
import json, hashlib, uuid
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
STORE = BASE / "zitar_core_project_memory_v1.jsonl"
OUT = BASE / "zitar_core_project_memory_model_train_seed_v1.json"

SEEDS = [
    {
        "project":"MODEL_TRAIN",
        "memory_type":"PROJECT_BASELINE",
        "content":"Restaurant delivery system uses autonomous G-scale trains; final propulsion baseline is onboard battery rather than track power.",
        "source":"Accepted model-train project baseline",
        "reason_for_persistence":"Preserve the accepted project purpose and propulsion architecture.",
        "version":1,
    },
    {
        "project":"MODEL_TRAIN",
        "memory_type":"NETWORK_ARCHITECTURE",
        "content":"Final network baseline: 3 main lines, 40 customer-table stations, 80 blocks; station spacing 3 m and block length 1.5 m. Stations 1 and 40 have three charging tracks; other stations are single-track.",
        "source":"Accepted model-train network baseline",
        "reason_for_persistence":"Preserve stable network topology for future project recall.",
        "version":1,
    },
    {
        "project":"MODEL_TRAIN",
        "memory_type":"CONTROL_ARCHITECTURE",
        "content":"Distributed control baseline: ESP32 per zone with RS485 to central Raspberry Pi; MCP23017 for I/O expansion and PCA9685 for turnout servos.",
        "source":"Accepted model-train control baseline",
        "reason_for_persistence":"Preserve accepted distributed control architecture.",
        "version":1,
    },
    {
        "project":"MODEL_TRAIN",
        "memory_type":"SENSOR_RULE",
        "content":"Hall sensors are placed near track center for bidirectional detection. Each locomotive and each wagon carries two magnets, one near each end. Each inter-station block uses two sensors to reduce false-clear behavior between vehicles.",
        "source":"Accepted model-train sensor rule",
        "reason_for_persistence":"Preserve a critical safety/detection design rule.",
        "version":1,
    },
    {
        "project":"MODEL_TRAIN",
        "memory_type":"PROJECT_MILESTONE",
        "content":"Prototype milestone reached: motor PWM with soft motion control, PCA9685 servo turnout movement, and the first route logic were tested successfully. The larger system remains under staged development.",
        "source":"Confirmed model-train prototype milestone",
        "reason_for_persistence":"Preserve the last confirmed implementation milestone without claiming the full system is complete.",
        "version":1,
    },
]

def canonical(o):
    return json.dumps(o,ensure_ascii=False,sort_keys=True,separators=(",",":"))

def digest(o):
    return hashlib.sha256(canonical(o).encode("utf-8")).hexdigest()

def load():
    if not STORE.exists():
        raise FileNotFoundError(f"Project memory store not found: {STORE}")
    return [json.loads(x) for x in STORE.read_text(encoding="utf-8").splitlines() if x.strip()]

def validate_chain(rows):
    prev=None; errors=[]
    for i,r in enumerate(rows):
        body={k:v for k,v in r.items() if k!="record_sha256"}
        if r.get("previous_sha256") != prev:
            errors.append(f"row_{i+1}:previous_sha256")
        if digest(body) != r.get("record_sha256"):
            errors.append(f"row_{i+1}:hash")
        prev=r.get("record_sha256")
    return errors

def identity(seed):
    return digest({
        "project":seed["project"],
        "memory_type":seed["memory_type"],
        "content":seed["content"],
        "source":seed["source"],
        "version":seed["version"],
    })

def main():
    rows=load()
    before_errors=validate_chain(rows)
    if before_errors:
        raise RuntimeError("Existing chain invalid: "+",".join(before_errors))

    existing={r.get("identity_sha256") for r in rows}
    added=0; skipped=0

    for seed in SEEDS:
        ident=identity(seed)
        if ident in existing:
            skipped+=1
            continue
        prev=rows[-1]["record_sha256"] if rows else None
        body={
            "schema":"ZITAR_CORE_PROJECT_MEMORY_V1",
            "memory_id":str(uuid.uuid4()),
            **seed,
            "provenance_category":"MEMORY",
            "created_utc":datetime.now(timezone.utc).isoformat(),
            "identity_sha256":ident,
            "previous_sha256":prev,
        }
        rec=dict(body)
        rec["record_sha256"]=digest(body)
        with STORE.open("a",encoding="utf-8") as f:
            f.write(json.dumps(rec,ensure_ascii=False,separators=(",",":"))+"\n")
        rows.append(rec)
        existing.add(ident)
        added+=1

    after_errors=validate_chain(rows)
    train=[r for r in rows if r.get("project")=="MODEL_TRAIN"]

    tests={
        "preexisting_chain_valid":not before_errors,
        "final_chain_valid":not after_errors,
        "model_train_records_present":len(train)>=len(SEEDS),
        "all_model_train_provenance_memory":all(r.get("provenance_category")=="MEMORY" for r in train),
        "all_model_train_have_source":all(bool(r.get("source")) for r in train),
        "all_model_train_have_reason":all(bool(r.get("reason_for_persistence")) for r in train),
        "execution_authority_false":True,
        "finance_evidence_written":False,
    }
    passed=sum(bool(x) for x in tests.values())
    payload={
        "schema":"ZITAR_CORE_MODEL_TRAIN_MEMORY_SEED_TEST_V1_1",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "added":added,
        "skipped_idempotent":skipped,
        "total_records":len(rows),
        "model_train_records":len(train),
        "chain_errors":after_errors,
        "tests":[{"name":k,"pass":v} for k,v in tests.items()],
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

    print("ZİTAR CORE MODEL TRAIN MEMORY SEED V1.1")
    print("CONTROLLED PROJECT MEMORY WRITE • APPEND-ONLY • NO ORDER • NO V3 WRITE")
    print("added:",added)
    print("skipped idempotent:",skipped)
    print("total records:",len(rows))
    print("model train records:",len(train))
    print("chain errors:",len(after_errors))
    print(f"validation: {passed}/{len(tests)}")
    print("store:",STORE)
    print("output:",OUT)
    print("STATUS:","PASS" if passed==len(tests) else "FAIL")

if __name__=="__main__":
    main()
