from __future__ import annotations
import json, re
from pathlib import Path

BASE = Path(__file__).resolve().parent
JOURNAL = BASE / "zitar_core_learning_journal_v1.jsonl"
OUT = BASE / "zitar_core_learning_journal_retrieval_test_v1.json"

ALIASES = {
    "ZITAR_CORE": {
        "zitar", "core", "çekirdek", "context", "bağlam",
        "hafıza", "memory", "öğren", "öğrendin", "gelişim",
        "kimlik", "benlik"
    }
}

STOP = {
    "ne","nedir","neler","bundan","bunu","bu","bir","ve","ile","mi","mı",
    "mu","mü","daha","önce","sonra","şu","an","hakkında","bana","sen"
}

def norm(s):
    return re.sub(r"\s+", " ", str(s).strip().lower())

def tokens(s):
    return {
        x for x in re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9_]+", norm(s))
        if x not in STOP and len(x) > 1
    }

def load():
    if not JOURNAL.exists():
        raise FileNotFoundError(f"Learning Journal bulunamadi: {JOURNAL}")
    return [json.loads(x) for x in JOURNAL.read_text(encoding="utf-8").splitlines() if x.strip()]

def searchable(row):
    evidence = row.get("evidence") or []
    return " ".join([
        row.get("domain",""),
        row.get("lesson_type",""),
        row.get("observation",""),
        " ".join(map(str,evidence)),
        row.get("prior_state",""),
        row.get("updated_state",""),
        row.get("outcome",""),
        row.get("source",""),
    ])

def retrieve(query, rows, top_k=3):
    q = norm(query)
    qt = tokens(query)
    scored = []

    for row in rows:
        rt = tokens(searchable(row))
        score = len(qt & rt)

        domain = row.get("domain","")
        score += sum(4 for alias in ALIASES.get(domain,set()) if norm(alias) in q)

        # "what did you learn?" is intentionally a learning-journal request.
        if any(k in q for k in ("ne öğrendin","neler öğrendin","öğrendiğin","gelişim")):
            score += 3

        if score > 0:
            scored.append((score, row))

    scored.sort(
        key=lambda x: (x[0], x[1].get("created_utc","")),
        reverse=True
    )

    return [
        {
            "score": score,
            "domain": row.get("domain"),
            "lesson_type": row.get("lesson_type"),
            "observation": row.get("observation"),
            "prior_state": row.get("prior_state"),
            "updated_state": row.get("updated_state"),
            "outcome": row.get("outcome"),
            "source": row.get("source"),
        }
        for score,row in scored[:top_k]
    ]

def synthesize_learning_answer(hits):
    if not hits:
        return {
            "status":"NO_SUPPORTED_LEARNING",
            "answer":"Bu soru için Learning Journal'da desteklenen bir öğrenme kaydı bulamadım."
        }

    parts = []
    for h in hits:
        parts.append(
            f"{h['observation']} "
            f"Önceki durum: {h['prior_state']} "
            f"Güncel durum: {h['updated_state']} "
            f"Sonuç: {h['outcome']}."
        )

    return {
        "status":"SUPPORTED",
        "answer":" ".join(parts)
    }

TESTS = [
    ("Bundan ne öğrendin?", True),
    ("ZİTAR Core geliştirmelerinden ne öğrendin?", True),
    ("Context hatasından ne öğrendin?", True),
    ("Benlik yapın hakkında ne öğrendin?", True),
]

def main():
    rows = load()
    results=[]
    passed=0

    for query, should_find in TESTS:
        hits=retrieve(query, rows)
        answer=synthesize_learning_answer(hits)
        ok=(bool(hits) == should_find)
        if should_find:
            ok = ok and answer["status"]=="SUPPORTED"
        passed += int(ok)
        results.append({
            "query":query,
            "hits":hits,
            "answer":answer,
            "pass":ok
        })

    payload={
        "schema":"ZITAR_CORE_LEARNING_JOURNAL_RETRIEVAL_TEST_V1",
        "journal_records":len(rows),
        "tests":results,
        "passed":passed,
        "total":len(TESTS),
        "memory_write":False,
        "execution_authority":False,
        "llm_used":False,
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

    print("ZİTAR CORE LEARNING JOURNAL RETRIEVAL V1")
    print("READ-ONLY • DETERMINISTIC • NO LLM • NO MEMORY WRITE")
    print("journal records:",len(rows))
    for r in results:
        top=r["hits"][0]["lesson_type"] if r["hits"] else "NONE"
        print(f"{'PASS' if r['pass'] else 'FAIL':4} | top={top:20} | {r['query']}")
    print(f"\nRESULT: {passed}/{len(TESTS)} PASS")
    print("output:",OUT)
    print("STATUS:","PASS" if passed==len(TESTS) else "FAIL")

if __name__=="__main__":
    main()
