from __future__ import annotations
import json, re
from pathlib import Path

BASE = Path(__file__).resolve().parent
STORE = BASE / "zitar_core_project_memory_v1.jsonl"
OUT = BASE / "zitar_core_project_memory_retrieval_test_v1.json"

def norm(s):
    return re.sub(r"\s+", " ", str(s).strip().lower())

def tokens(s):
    # Lightweight deterministic Turkish-friendly tokenization.
    return set(re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9_]+", norm(s)))

ALIASES = {
    "ZITAR_CORE": {"zitar", "core", "çekirdek", "hafıza", "memory", "mimari"},
    "MODEL_TRAIN": {"tren", "model tren", "lokomotif", "vagon", "ray", "makas", "istasyon"},
}

def load_records():
    if not STORE.exists():
        raise FileNotFoundError(f"Store bulunamadi: {STORE}")
    return [json.loads(x) for x in STORE.read_text(encoding="utf-8").splitlines() if x.strip()]

def retrieve(query, records, top_k=3):
    q = norm(query)
    qt = tokens(query)
    scored=[]
    for r in records:
        project=r.get("project","")
        text=" ".join([
            project,
            r.get("memory_type",""),
            r.get("content",""),
            r.get("source",""),
            r.get("reason_for_persistence","")
        ])
        score=len(qt & tokens(text))
        alias_hits=sum(1 for a in ALIASES.get(project,set()) if norm(a) in q)
        score += alias_hits * 5
        if score > 0:
            scored.append((score, r))
    scored.sort(key=lambda x:(x[0], x[1].get("created_utc","")), reverse=True)
    return [{"score":s,"project":r["project"],"memory_type":r["memory_type"],
             "content":r["content"],"source":r["source"],"record_sha256":r["record_sha256"]}
            for s,r in scored[:top_k]]

TESTS = [
    ("ZİTAR Core mimarisi hakkında ne hatırlıyorsun?", "ZITAR_CORE", True),
    ("Finance ZİTAR'ın tamamı mı?", "ZITAR_CORE", True),
    ("Hafıza türlerini nasıl ayırmıştık?", "ZITAR_CORE", True),
    # After controlled MODEL_TRAIN seeding, retrieval must find the project.
    ("Model tren projesinde en son ne yapmıştık?", "MODEL_TRAIN", True),
]

def main():
    records=load_records()
    results=[]
    passed=0
    for query, expected_project, should_find in TESTS:
        hits=retrieve(query,records)
        found=bool(hits)
        top_project=hits[0]["project"] if hits else None
        if should_find:
            ok=found and top_project==expected_project
        else:
            ok=not any(h["project"]==expected_project for h in hits)
        passed += int(ok)
        results.append({
            "query":query,
            "expected_project":expected_project,
            "should_find":should_find,
            "hits":hits,
            "pass":ok
        })

    payload={
        "schema":"ZITAR_CORE_PROJECT_MEMORY_RETRIEVAL_TEST_V2",
        "store_records":len(records),
        "tests":results,
        "passed":passed,
        "total":len(TESTS),
        "execution_authority":False,
        "memory_write":False,
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

    print("ZİTAR CORE PROJECT MEMORY RETRIEVAL V2")
    print("READ-ONLY • DETERMINISTIC • NO LLM • NO MEMORY WRITE")
    print("store records:",len(records))
    for r in results:
        top=r["hits"][0]["project"] if r["hits"] else "NONE"
        print(f"{'PASS' if r['pass'] else 'FAIL':4} | top={top:12} | {r['query']}")
    print(f"\nRESULT: {passed}/{len(TESTS)} PASS")
    print("output:",OUT)
    print("STATUS:","PASS" if passed==len(TESTS) else "FAIL")

if __name__=="__main__":
    main()
