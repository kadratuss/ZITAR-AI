from __future__ import annotations
import json, hashlib
from datetime import datetime, timezone
from pathlib import Path

BASE=Path(__file__).resolve().parent
CANDIDATE=BASE/"zitar_core_learning_candidate_v1.json"
JOURNAL=BASE/"zitar_core_learning_journal_v1.jsonl"
OUT=BASE/"zitar_core_learning_journal_write_test_v1_1.json"

def canonical(x):
    return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"))

def sha(x):
    return hashlib.sha256(canonical(x).encode("utf-8")).hexdigest()

def load_jsonl(path):
    if not path.exists(): return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def verify_mixed_chain(rows):
    errors=[]; prev=None
    for i,r in enumerate(rows,1):
        schema=r.get("schema")
        prev_field="previous_sha256" if schema=="ZITAR_CORE_LEARNING_JOURNAL_V1" else "previous_record_sha256"
        if r.get(prev_field)!=prev:
            errors.append(f"ROW_{i}:PREVIOUS_HASH_MISMATCH:{prev_field}")
        body=dict(r); claimed=body.pop("record_sha256",None)
        if claimed!=sha(body):
            errors.append(f"ROW_{i}:RECORD_HASH_MISMATCH")
        prev=claimed
    return errors

def main():
    candidate=json.loads(CANDIDATE.read_text(encoding="utf-8"))
    rows=load_jsonl(JOURNAL)
    before=len(rows)
    pre_errors=verify_mixed_chain(rows)

    eligible=(
        candidate.get("status")=="VALIDATED_CANDIDATE"
        and candidate.get("next_required_stage")=="CONTROLLED_LEARNING_JOURNAL_WRITE"
        and bool(candidate.get("candidate_sha256"))
        and len(candidate.get("claims") or [])>0
        and len(candidate.get("source_provenance") or [])>=2
    )
    duplicate=any(r.get("candidate_sha256")==candidate.get("candidate_sha256") for r in rows)
    added=0

    if eligible and not duplicate and not pre_errors:
        rec={
            "schema":"ZITAR_CORE_LEARNING_JOURNAL_V2",
            "domain":candidate.get("domain"),
            "lesson_type":"EXTERNAL_RESEARCH_LEARNING",
            "topic":candidate.get("topic"),
            "observation":candidate.get("question"),
            "claims":candidate.get("claims"),
            "source_provenance":candidate.get("source_provenance"),
            "evidence_bundle_sha256":candidate.get("evidence_bundle_sha256"),
            "candidate_sha256":candidate.get("candidate_sha256"),
            "outcome":"LEARNED_FROM_CORROBORATED_EXTERNAL_RESEARCH",
            "version":2,
            "created_utc":datetime.now(timezone.utc).isoformat(),
            "previous_record_sha256":rows[-1]["record_sha256"] if rows else None,
            "execution_authority":False,
            "silent_code_rewrite_authority":False,
        }
        rec["record_sha256"]=sha(rec)
        with JOURNAL.open("a",encoding="utf-8",newline="\n") as f:
            f.write(json.dumps(rec,ensure_ascii=False,separators=(",",":"))+"\n")
        added=1

    after=load_jsonl(JOURNAL)
    post_errors=verify_mixed_chain(after)
    matching=[r for r in after if r.get("candidate_sha256")==candidate.get("candidate_sha256")]

    tests={
        "candidate_eligible":eligible,
        "preexisting_chain_valid":not pre_errors,
        "exactly_one_candidate_record":len(matching)==1,
        "idempotent_write":(added==1 and not duplicate) or (added==0 and duplicate),
        "mixed_chain_valid":not post_errors,
        "evidence_hash_preserved":bool(matching) and matching[0].get("evidence_bundle_sha256")==candidate.get("evidence_bundle_sha256"),
        "provenance_preserved":bool(matching) and len(matching[0].get("source_provenance") or [])>=2,
        "no_execution_authority":bool(matching) and matching[0].get("execution_authority") is False,
        "no_silent_code_rewrite":bool(matching) and matching[0].get("silent_code_rewrite_authority") is False,
    }
    passed=sum(int(v) for v in tests.values())
    OUT.write_text(json.dumps({
        "schema":"ZITAR_CORE_LEARNING_JOURNAL_WRITE_TEST_V1_1",
        "records_before":before,"added":added,"records_after":len(after),
        "duplicate":duplicate,"pre_chain_errors":pre_errors,"post_chain_errors":post_errors,
        "tests":[{"name":k,"pass":bool(v)} for k,v in tests.items()],
        "passed":passed,"total":len(tests)
    },ensure_ascii=False,indent=2),encoding="utf-8")

    print("ZITAR CORE CONTROLLED LEARNING JOURNAL WRITE V1.1")
    print("BACKWARD COMPATIBLE V1->V2 • APPEND ONLY • HASH CHAINED")
    print("candidate eligible:",eligible)
    print("duplicate:",duplicate)
    print("records before:",before)
    print("added:",added)
    print("records after:",len(after))
    print("pre-chain errors:",len(pre_errors))
    print("post-chain errors:",len(post_errors))
    print(f"validation: {passed}/{len(tests)}")
    print("journal:",JOURNAL)
    print("output:",OUT)
    print("STATUS:","PASS" if passed==len(tests) else "FAIL")

if __name__=="__main__":
    main()
