from __future__ import annotations
import json, re
from pathlib import Path

BASE = Path(__file__).resolve().parent
JOURNAL = BASE / "zitar_core_learning_journal_v1.jsonl"
OUT = BASE / "zitar_core_domain_learning_recall_test_v1.json"

def norm(s):
    return re.sub(r"\s+", " ", str(s).strip().lower())

def toks(s):
    return set(re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9_]+", norm(s)))

def load():
    if not JOURNAL.exists():
        raise FileNotFoundError(JOURNAL)
    return [json.loads(x) for x in JOURNAL.read_text(encoding="utf-8").splitlines() if x.strip()]

def searchable(r):
    return " ".join([
        r.get("domain",""), r.get("lesson_type",""), r.get("observation",""),
        " ".join(map(str,r.get("evidence") or [])),
        r.get("prior_state",""), r.get("updated_state",""), r.get("source","")
    ])

def retrieve(query, rows, active_domain=None, top_k=3):
    qt=toks(query)
    candidates=[]

    # Hard domain filter: a follow-up in MODEL_TRAIN must not receive
    # ZITAR_CORE learning records as if they belonged to MODEL_TRAIN.
    domain_rows = [r for r in rows if active_domain is None or r.get("domain")==active_domain]

    for r in domain_rows:
        score=len(qt & toks(searchable(r)))
        if "öğren" in norm(query):
            score += 3
        if score>0:
            candidates.append((score,r))

    candidates.sort(key=lambda x:(x[0],x[1].get("created_utc","")),reverse=True)
    return candidates[:top_k]

TESTS=[
    {
        "name":"model_train_no_cross_domain_leak",
        "query":"Peki bundan ne öğrendin?",
        "domain":"MODEL_TRAIN",
        "expect_hits":False
    },
    {
        "name":"zitar_core_learning_exists",
        "query":"Bundan ne öğrendin?",
        "domain":"ZITAR_CORE",
        "expect_hits":True
    },
    {
        "name":"unknown_domain_no_false_claim",
        "query":"Bundan ne öğrendin?",
        "domain":"NON_EXISTENT_DOMAIN",
        "expect_hits":False
    },
]

def main():
    rows=load()
    passed=0
    results=[]

    print("ZİTAR CORE DOMAIN-AWARE LEARNING RECALL V1")
    print("STRICT DOMAIN FILTER • READ ONLY • NO LLM • NO MEMORY WRITE")

    for t in TESTS:
        hits=retrieve(t["query"],rows,t["domain"])
        ok=(bool(hits)==t["expect_hits"])
        if hits:
            ok = ok and all(r.get("domain")==t["domain"] for _,r in hits)
        passed += int(ok)

        status="SUPPORTED" if hits else "NO_DOMAIN_LEARNING"
        print(
            f"{'PASS' if ok else 'FAIL':4} | domain={t['domain']:19} "
            f"status={status:18} hits={len(hits)} | {t['query']}"
        )
        results.append({
            **t,
            "status":status,
            "hits":[{
                "score":s,
                "domain":r.get("domain"),
                "lesson_type":r.get("lesson_type"),
                "observation":r.get("observation"),
                "outcome":r.get("outcome"),
                "source":r.get("source")
            } for s,r in hits],
            "pass":ok
        })

    payload={
        "schema":"ZITAR_CORE_DOMAIN_AWARE_LEARNING_RECALL_TEST_V1",
        "journal_records":len(rows),
        "tests":results,
        "passed":passed,
        "total":len(TESTS),
        "cross_domain_fallback":False,
        "llm_used":False,
        "memory_write":False,
        "execution_authority":False
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

    print(f"\nRESULT: {passed}/{len(TESTS)} PASS")
    print("output:",OUT)
    print("STATUS:","PASS" if passed==len(TESTS) else "FAIL")

if __name__=="__main__":
    main()
