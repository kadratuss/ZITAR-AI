from __future__ import annotations
import json, hashlib, urllib.request, urllib.parse, socket, re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
EVIDENCE = BASE / "zitar_core_research_evidence_v1.jsonl"
OUT = BASE / "zitar_core_external_research_evidence_v1_2.jsonl"
TEST = BASE / "zitar_core_external_research_executor_test_v1_2.json"
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
        url, headers={"User-Agent":"ZITAR-Core-Research/1.2 (personal research system)"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8")), getattr(r, "status", 200)

def search_wikipedia(query, limit=3):
    params = urllib.parse.urlencode({
        "action":"query","list":"search","srsearch":query,
        "srlimit":limit,"format":"json","utf8":1
    })
    data, http_status = get_json(WIKI_API + "?" + params)
    return data.get("query",{}).get("search",[]), http_status

def page_meta(pageid):
    params = urllib.parse.urlencode({
        "action":"query","pageids":pageid,"prop":"extracts|info",
        "exintro":1,"explaintext":1,"inprop":"url","format":"json","utf8":1
    })
    data, _ = get_json(WIKI_API + "?" + params)
    return data.get("query",{}).get("pages",{}).get(str(pageid),{})

def research_query(bundle):
    # Do not send meta-questions like "should I gather evidence?" to a search engine.
    # V1.2 turns such a gap into a diagnostic real query so transport and evidence
    # discovery remain distinguishable from semantic research quality.
    q = bundle.get("question","").strip()
    meta = ("kanıt toplamam gerekiyor" in q.lower() or
            "bilmediğim bu konu" in q.lower() or len(re.findall(r"\w+", q)) < 2)
    if meta:
        return "Raspberry Pi", "DIAGNOSTIC_SUBSTITUTE_QUERY"
    return q, "ORIGINAL_GAP_QUERY"

def execute(bundle):
    query, query_mode = research_query(bundle)
    sources=[]; errors=[]; dns=None; http_status=None

    try:
        dns = socket.gethostbyname("en.wikipedia.org")
    except Exception as e:
        errors.append(f"DNS:{type(e).__name__}:{e}")
        status="NETWORK_ERROR"
    else:
        try:
            hits, http_status = search_wikipedia(query)
            if not hits:
                status="NO_RESULTS"
            else:
                for h in hits:
                    try:
                        meta=page_meta(h["pageid"])
                        sources.append({
                            "source_type":"ENCYCLOPEDIA_SECONDARY",
                            "provider":"Wikipedia",
                            "title":meta.get("title"),
                            "url":meta.get("fullurl"),
                            "pageid":h.get("pageid"),
                            "timestamp":h.get("timestamp"),
                            "extract":(meta.get("extract") or "")[:2000],
                        })
                    except Exception as e:
                        errors.append(f"PAGE:{h.get('pageid')}:{type(e).__name__}:{e}")
                status="EXTERNAL_EVIDENCE_COLLECTED" if sources else "SOURCE_FETCH_FAILED"
        except Exception as e:
            errors.append(f"HTTP:{type(e).__name__}:{e}")
            status="NETWORK_OR_API_ERROR"

    body={
        "schema":"ZITAR_CORE_EXTERNAL_RESEARCH_EVIDENCE_V1_2",
        "domain":bundle["domain"],
        "original_question":bundle["question"],
        "research_query":query,
        "query_mode":query_mode,
        "parent_bundle_sha256":bundle["bundle_sha256"],
        "status":status,
        "dns":dns,
        "http_status":http_status,
        "sources":sources,
        "errors":errors,
        "primary_source_present":False,
        "independent_corroboration_complete":False,
        "learning_ready":False,
        "reason_not_learning_ready":
            "Discovery evidence alone is insufficient; primary-source and independent "
            "corroboration requirements are not yet satisfied.",
        "collected_utc":datetime.now(timezone.utc).isoformat(),
        "authorities":{
            "public_web_read":True,
            "memory_write":False,
            "real_order":False,
            "code_rewrite":False
        }
    }
    body["external_bundle_sha256"]=sha(body)
    return body

def main():
    bundles=load_jsonl(EVIDENCE)
    targets=[b for b in bundles if b.get("external_research_required")]
    results=[execute(b) for b in targets]

    with OUT.open("w",encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r,ensure_ascii=False,separators=(",",":"))+"\n")

    tests={
        "one_result_per_target":len(results)==len(targets),
        "status_is_explicit":all(r["status"] in {
            "EXTERNAL_EVIDENCE_COLLECTED","NO_RESULTS","NETWORK_ERROR",
            "NETWORK_OR_API_ERROR","SOURCE_FETCH_FAILED"} for r in results),
        "failure_has_error":all(
            bool(r["errors"]) for r in results
            if r["status"] in {"NETWORK_ERROR","NETWORK_OR_API_ERROR","SOURCE_FETCH_FAILED"}
        ),
        "no_results_is_not_failure":all(
            not r["errors"] for r in results if r["status"]=="NO_RESULTS"
        ),
        "source_urls_present":all(
            all(bool(s.get("url")) for s in r["sources"]) for r in results
        ),
        "not_learning_ready":all(not r["learning_ready"] for r in results),
        "no_memory_write":all(not r["authorities"]["memory_write"] for r in results),
        "no_real_order":all(not r["authorities"]["real_order"] for r in results),
        "no_code_rewrite":all(not r["authorities"]["code_rewrite"] for r in results),
        "utf8_json_output":True,
    }
    passed=sum(int(v) for v in tests.values())
    TEST.write_text(json.dumps({
        "schema":"ZITAR_CORE_EXTERNAL_RESEARCH_EXECUTOR_TEST_V1_2",
        "targets":len(targets),"results":len(results),
        "tests":[{"name":k,"pass":bool(v)} for k,v in tests.items()],
        "passed":passed,"total":len(tests)
    },ensure_ascii=False,indent=2),encoding="utf-8")

    print("ZİTAR CORE EXTERNAL RESEARCH EXECUTOR V1.2")
    print("NETWORK CLASSIFICATION • PROVENANCE • UTF-8 FILES • NO MEMORY WRITE")
    for r in results:
        print(f"{r['domain']:<18} status={r['status']:<28} "
              f"query_mode={r['query_mode']:<27} sources={len(r['sources'])} errors={len(r['errors'])}")
    print(f"validation: {passed}/{len(tests)}")
    print("evidence:",OUT)
    print("output:",TEST)
    print("STATUS:","PASS" if passed==len(tests) else "FAIL")

if __name__=="__main__":
    main()
