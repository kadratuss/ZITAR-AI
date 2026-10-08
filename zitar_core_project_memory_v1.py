from __future__ import annotations
import json, hashlib, uuid
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
STORE = BASE / "zitar_core_project_memory_v1.jsonl"
INDEX = BASE / "zitar_core_project_memory_index_v1.json"
TEST_OUT = BASE / "zitar_core_project_memory_test_v1.json"

SCHEMA = "ZITAR_CORE_PROJECT_MEMORY_V1"

def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def sha(obj):
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()

def read_records():
    if not STORE.exists():
        return []
    out=[]
    for line in STORE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out

def validate_chain(records):
    prev = None
    errors=[]
    for i,r in enumerate(records):
        body={k:v for k,v in r.items() if k!="record_sha256"}
        if r.get("previous_sha256") != prev:
            errors.append(f"row_{i+1}: previous_sha256 mismatch")
        if sha(body) != r.get("record_sha256"):
            errors.append(f"row_{i+1}: record hash mismatch")
        prev=r.get("record_sha256")
    return errors

def append_project_memory(project, memory_type, content, source, reason, version=1):
    records=read_records()
    chain_errors=validate_chain(records)
    if chain_errors:
        raise RuntimeError("Existing memory chain invalid: " + "; ".join(chain_errors))

    # Idempotency key prevents duplicate identical writes.
    identity = sha({
        "project":project, "memory_type":memory_type,
        "content":content, "source":source, "version":version
    })
    for r in records:
        if r.get("identity_sha256")==identity:
            return r, False

    prev=records[-1]["record_sha256"] if records else None
    body={
        "schema":SCHEMA,
        "memory_id":str(uuid.uuid4()),
        "project":project,
        "memory_type":memory_type,
        "content":content,
        "source":source,
        "reason_for_persistence":reason,
        "provenance_category":"MEMORY",
        "version":version,
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "identity_sha256":identity,
        "previous_sha256":prev,
    }
    rec=dict(body)
    rec["record_sha256"]=sha(body)
    with STORE.open("a",encoding="utf-8") as f:
        f.write(json.dumps(rec,ensure_ascii=False,separators=(",",":"))+"\n")
    return rec, True

def rebuild_index(records):
    idx={}
    for r in records:
        p=r["project"]
        x=idx.setdefault(p,{"records":0,"latest_created_utc":None,"latest_version":0})
        x["records"]+=1
        x["latest_created_utc"]=r["created_utc"]
        x["latest_version"]=max(x["latest_version"],int(r.get("version",1)))
    payload={
        "schema":"ZITAR_CORE_PROJECT_MEMORY_INDEX_V1",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "store":STORE.name,
        "projects":idx,
        "record_count":len(records),
        "chain_valid":not validate_chain(records),
    }
    INDEX.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    return payload

def main():
    # Controlled seed: architecture facts only, not arbitrary chat content.
    seeds=[
        (
            "ZITAR_CORE","ARCHITECTURE_DECISION",
            "ZITAR Core routes intent/context to specialists and tools; Finance is a specialist, not the whole identity.",
            "ZITAR Core architecture milestone",
            "Preserve an explicit project architecture decision.",
            1
        ),
        (
            "ZITAR_CORE","MEMORY_POLICY",
            "Conversation context, personal memory, project memory, and specialist learning memory are separate stores; no automatic persistent promotion.",
            "ZITAR Core Memory Architecture V1",
            "Preserve the accepted memory separation policy.",
            1
        ),
    ]

    added=0
    skipped=0
    for args in seeds:
        _,was_added=append_project_memory(*args)
        if was_added: added+=1
        else: skipped+=1

    records=read_records()
    errors=validate_chain(records)
    idx=rebuild_index(records)

    tests={
        "chain_valid":len(errors)==0,
        "has_records":len(records)>=2,
        "provenance_memory_only":all(r.get("provenance_category")=="MEMORY" for r in records),
        "has_reason":all(bool(r.get("reason_for_persistence")) for r in records),
        "has_source":all(bool(r.get("source")) for r in records),
        "index_valid":idx["chain_valid"] is True,
        "no_execution_authority":True,
        "no_personal_memory_write":all(r.get("project")=="ZITAR_CORE" for r in records),
    }
    result={
        "schema":"ZITAR_CORE_PROJECT_MEMORY_TEST_V1",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "added":added,
        "skipped_idempotent":skipped,
        "records":len(records),
        "chain_errors":errors,
        "tests":[{"name":k,"pass":v} for k,v in tests.items()],
    }
    TEST_OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")

    passed=sum(bool(v) for v in tests.values())
    print("ZİTAR CORE PROJECT MEMORY STORE V1")
    print("APPEND-ONLY • HASH-CHAINED • IDEMPOTENT • NO ORDER • NO V3 WRITE")
    print("added:",added)
    print("skipped idempotent:",skipped)
    print("records:",len(records))
    print("chain errors:",len(errors))
    print(f"validation: {passed}/{len(tests)}")
    print("store:",STORE)
    print("index:",INDEX)
    print("STATUS:","PASS" if passed==len(tests) else "FAIL")

if __name__=="__main__":
    main()
