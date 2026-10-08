from __future__ import annotations
import json, hashlib, urllib.request, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
EVIDENCE = BASE / "zitar_core_research_evidence_v1.jsonl"
OUT = BASE / "zitar_core_external_research_evidence_v1.jsonl"
TEST = BASE / "zitar_core_external_research_executor_test_v1.json"

# V1 intentionally supports a bounded public-source research adapter.
# It does not search arbitrary web pages yet; it proves the external
# evidence pipeline with Wikipedia REST/search metadata and preserves
# provenance. Later adapters can add general web/news/search providers.
WIKI_API = "https://en.wikipedia.org/w/api.php"

def canonical(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def sha(x):
    return hashlib.sha256(canonical(x).encode("utf-8")).hexdigest()

def load_jsonl(path):
    if not path.exists():
        raise FileNotFoundError(path)
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def get_json(url, timeout=15):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ZITAR-Core-Research/1.0 (personal research system)"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def wiki_search(query, limit=3):
    params = urllib.parse.urlencode({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "format": "json",
        "utf8": 1,
    })
    data = get_json(WIKI_API + "?" + params)
    return data.get("query", {}).get("search", [])

def wiki_page_meta(pageid):
    params = urllib.parse.urlencode({
        "action": "query",
        "pageids": pageid,
        "prop": "extracts|info",
        "exintro": 1,
        "explaintext": 1,
        "inprop": "url",
        "format": "json",
        "utf8": 1,
    })
    data = get_json(WIKI_API + "?" + params)
    return data.get("query", {}).get("pages", {}).get(str(pageid), {})

def execute(bundle):
    if not bundle.get("external_research_required"):
        return None

    question = bundle["question"]
    domain = bundle["domain"]
    sources = []
    errors = []

    try:
        hits = wiki_search(question, limit=3)
        for hit in hits:
            try:
                meta = wiki_page_meta(hit["pageid"])
                sources.append({
                    "source_type": "ENCYCLOPEDIA_SECONDARY",
                    "provider": "Wikipedia",
                    "title": meta.get("title"),
                    "url": meta.get("fullurl"),
                    "pageid": hit.get("pageid"),
                    "timestamp": hit.get("timestamp"),
                    "snippet": hit.get("snippet"),
                    "extract": (meta.get("extract") or "")[:2000],
                })
            except Exception as e:
                errors.append(f"PAGE:{hit.get('pageid')}:{type(e).__name__}:{e}")
    except Exception as e:
        errors.append(f"SEARCH:{type(e).__name__}:{e}")

    # This adapter alone can collect external evidence, but cannot satisfy
    # a requirement for primary + independent corroboration.
    status = "EXTERNAL_EVIDENCE_COLLECTED" if sources else "EXTERNAL_RESEARCH_FAILED"
    corroboration_complete = False
    primary_source_present = False

    body = {
        "schema": "ZITAR_CORE_EXTERNAL_RESEARCH_EVIDENCE_V1",
        "domain": domain,
        "question": question,
        "parent_bundle_sha256": bundle["bundle_sha256"],
        "status": status,
        "sources": sources,
        "errors": errors,
        "primary_source_present": primary_source_present,
        "independent_corroboration_complete": corroboration_complete,
        "learning_ready": False,
        "reason_not_learning_ready":
            "V1 external adapter provides secondary-source discovery only; "
            "primary-source and independent corroboration requirements are not yet satisfied.",
        "collected_utc": datetime.now(timezone.utc).isoformat(),
        "authorities": {
            "public_web_read": True,
            "memory_write": False,
            "real_order": False,
            "code_rewrite": False,
        },
    }
    body["external_bundle_sha256"] = sha(body)
    return body

def main():
    bundles = load_jsonl(EVIDENCE)
    external_targets = [b for b in bundles if b.get("external_research_required")]
    results = [r for r in (execute(b) for b in external_targets) if r is not None]

    with OUT.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")

    tests = {
        "one_result_per_external_target": len(results) == len(external_targets),
        "all_results_hashed": all(bool(r.get("external_bundle_sha256")) for r in results),
        "provenance_urls_present_if_sources": all(
            all(bool(s.get("url")) for s in r["sources"]) for r in results
        ),
        "source_type_explicit": all(
            all(bool(s.get("source_type")) for s in r["sources"]) for r in results
        ),
        "does_not_claim_primary_source": all(not r["primary_source_present"] for r in results),
        "does_not_claim_corroboration": all(not r["independent_corroboration_complete"] for r in results),
        "not_learning_ready": all(not r["learning_ready"] for r in results),
        "no_memory_write": all(not r["authorities"]["memory_write"] for r in results),
        "no_real_order": all(not r["authorities"]["real_order"] for r in results),
        "no_code_rewrite": all(not r["authorities"]["code_rewrite"] for r in results),
    }

    passed = sum(int(v) for v in tests.values())
    payload = {
        "schema": "ZITAR_CORE_EXTERNAL_RESEARCH_EXECUTOR_TEST_V1",
        "external_targets": len(external_targets),
        "results": len(results),
        "tests": [{"name": k, "pass": bool(v)} for k, v in tests.items()],
        "passed": passed,
        "total": len(tests),
    }
    TEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("ZİTAR CORE EXTERNAL RESEARCH EXECUTOR V1")
    print("PUBLIC WEB READ • PROVENANCE PRESERVED • NO MEMORY WRITE • NO ORDER")
    print("external targets:", len(external_targets))
    for r in results:
        print(
            f"{r['domain']:<18} status={r['status']:<28} "
            f"sources={len(r['sources'])} errors={len(r['errors'])} "
            f"learning_ready={r['learning_ready']}"
        )
    print(f"validation: {passed}/{len(tests)}")
    print("evidence:", OUT)
    print("output:", TEST)
    print("STATUS:", "PASS" if passed == len(tests) else "FAIL")

if __name__ == "__main__":
    main()
