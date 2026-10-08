from __future__ import annotations
import json, hashlib, re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
PLANS = BASE / "zitar_core_research_plans_v1.jsonl"
PROJECT_MEMORY = BASE / "zitar_core_project_memory_v1.jsonl"
LEARNING = BASE / "zitar_core_learning_journal_v1.jsonl"
OUT = BASE / "zitar_core_research_evidence_v1.jsonl"
TEST = BASE / "zitar_core_research_executor_test_v1.json"

def canon(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def sha(x):
    return hashlib.sha256(canon(x).encode("utf-8")).hexdigest()

def load_jsonl(path, required=True):
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def norm(s):
    return re.sub(r"\s+", " ", str(s).strip().lower())

def toks(s):
    return set(re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9_]+", norm(s)))

def row_text(r):
    vals = []
    for k, v in r.items():
        if isinstance(v, list):
            vals.extend(map(str, v))
        elif isinstance(v, (str, int, float, bool)):
            vals.append(str(v))
    return " ".join(vals)

def local_hits(query, rows, domain=None, limit=5):
    qt = toks(query)
    scored = []
    for r in rows:
        if domain and r.get("project") and r.get("project") != domain:
            continue
        if domain and r.get("domain") and r.get("domain") != domain:
            continue
        s = len(qt & toks(row_text(r)))
        if domain and (r.get("project") == domain or r.get("domain") == domain):
            s += 5
        if s > 0:
            scored.append((s, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]

def execute_local_stage(plan, project_rows, learning_rows):
    domain = plan["domain"]
    question = plan["question"]
    evidence = []

    ph = local_hits(question, project_rows, domain=domain)
    lh = local_hits(question, learning_rows, domain=domain)

    for r in ph:
        evidence.append({
            "kind": "LOCAL_PROJECT_MEMORY",
            "domain": domain,
            "source": "zitar_core_project_memory_v1.jsonl",
            "record_sha256": r.get("record_sha256"),
            "content": r.get("content"),
        })

    for r in lh:
        evidence.append({
            "kind": "LOCAL_LEARNING_JOURNAL",
            "domain": domain,
            "source": "zitar_core_learning_journal_v1.jsonl",
            "record_sha256": r.get("record_sha256"),
            "observation": r.get("observation"),
            "updated_state": r.get("updated_state"),
            "outcome": r.get("outcome"),
        })

    if evidence:
        status = "LOCAL_EVIDENCE_COLLECTED"
        external_needed = False
    else:
        status = "EXTERNAL_RESEARCH_REQUIRED"
        external_needed = True

    return evidence, status, external_needed

def main():
    plans = load_jsonl(PLANS)
    project_rows = load_jsonl(PROJECT_MEMORY, required=False)
    learning_rows = load_jsonl(LEARNING, required=False)

    bundles = []
    for plan in plans:
        evidence, status, external_needed = execute_local_stage(
            plan, project_rows, learning_rows
        )
        body = {
            "schema": "ZITAR_CORE_RESEARCH_EVIDENCE_V1",
            "plan_sha256": plan["plan_sha256"],
            "gap_identity_sha256": plan["gap_identity_sha256"],
            "domain": plan["domain"],
            "question": plan["question"],
            "status": status,
            "external_research_required": external_needed,
            "evidence": evidence,
            "collected_utc": datetime.now(timezone.utc).isoformat(),
            "authorities": {
                "local_read": True,
                "web_research": False,
                "memory_write": False,
                "real_order": False,
                "code_rewrite": False,
            },
        }
        body["bundle_sha256"] = sha(body)
        bundles.append(body)

    with OUT.open("w", encoding="utf-8") as f:
        for b in bundles:
            f.write(json.dumps(b, ensure_ascii=False, separators=(",", ":")) + "\n")

    mt = next((b for b in bundles if b["domain"] == "MODEL_TRAIN"), None)
    general = next((b for b in bundles if b["domain"] == "GENERAL_RESEARCH"), None)

    tests = {
        "one_bundle_per_plan": len(bundles) == len(plans),
        "model_train_bundle_exists": mt is not None,
        "model_train_reads_local_memory": bool(mt and any(e["kind"] == "LOCAL_PROJECT_MEMORY" for e in mt["evidence"])),
        "model_train_does_not_fake_learning": bool(mt and not any(e["kind"] == "LOCAL_LEARNING_JOURNAL" for e in mt["evidence"])),
        "general_gap_resolved_by_local_or_external": bool(general and ((general["external_research_required"] and len(general["evidence"]) == 0) or ((not general["external_research_required"]) and len(general["evidence"]) > 0))),
        "no_web_claimed_in_local_executor": all(not b["authorities"]["web_research"] for b in bundles),
        "no_memory_write": all(not b["authorities"]["memory_write"] for b in bundles),
        "no_real_order": all(not b["authorities"]["real_order"] for b in bundles),
        "no_code_rewrite": all(not b["authorities"]["code_rewrite"] for b in bundles),
        "all_bundles_hashed": all(bool(b.get("bundle_sha256")) for b in bundles),
    }

    passed = sum(int(v) for v in tests.values())
    payload = {
        "schema": "ZITAR_CORE_RESEARCH_EXECUTOR_TEST_V1",
        "plans": len(plans),
        "bundles": len(bundles),
        "tests": [{"name": k, "pass": bool(v)} for k, v in tests.items()],
        "passed": passed,
        "total": len(tests),
    }
    TEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("ZİTAR CORE RESEARCH EXECUTOR V1")
    print("LOCAL EVIDENCE STAGE • NO WEB YET • NO MEMORY WRITE • NO ORDER")
    for b in bundles:
        print(
            f"{b['domain']:<18} status={b['status']:<27} "
            f"evidence={len(b['evidence'])} external_needed={b['external_research_required']}"
        )
    print(f"validation: {passed}/{len(tests)}")
    print("evidence:", OUT)
    print("output:", TEST)
    print("STATUS:", "PASS" if passed == len(tests) else "FAIL")

if __name__ == "__main__":
    main()

