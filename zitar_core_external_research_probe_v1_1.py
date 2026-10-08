from __future__ import annotations
import json, urllib.request, urllib.parse, socket
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "zitar_core_external_research_probe_v1_1.json"

WIKI_API = "https://en.wikipedia.org/w/api.php"
TEST_QUERY = "Raspberry Pi"

def get_json(url, timeout=15):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ZITAR-Core-Research/1.1 (personal research system)"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw.decode("utf-8")), getattr(r, "status", 200)

def main():
    result = {
        "schema": "ZITAR_CORE_EXTERNAL_RESEARCH_PROBE_V1_1",
        "query": TEST_QUERY,
        "utc": datetime.now(timezone.utc).isoformat(),
        "dns": None,
        "http_status": None,
        "search_count": 0,
        "status": None,
        "errors": [],
    }

    try:
        result["dns"] = socket.gethostbyname("en.wikipedia.org")
    except Exception as e:
        result["status"] = "NETWORK_ERROR"
        result["errors"].append(f"DNS:{type(e).__name__}:{e}")

    if not result["errors"]:
        try:
            params = urllib.parse.urlencode({
                "action": "query",
                "list": "search",
                "srsearch": TEST_QUERY,
                "srlimit": 3,
                "format": "json",
                "utf8": 1,
            })
            data, status = get_json(WIKI_API + "?" + params)
            result["http_status"] = status
            hits = data.get("query", {}).get("search", [])
            result["search_count"] = len(hits)

            if hits:
                result["status"] = "EXTERNAL_EVIDENCE_DISCOVERED"
                result["titles"] = [h.get("title") for h in hits]
            else:
                result["status"] = "NO_RESULTS"
                result["titles"] = []
        except Exception as e:
            result["status"] = "NETWORK_OR_API_ERROR"
            result["errors"].append(f"HTTP:{type(e).__name__}:{e}")

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    transport_ok = result["status"] in {"EXTERNAL_EVIDENCE_DISCOVERED", "NO_RESULTS"}
    classification_ok = not (
        result["status"] == "NETWORK_OR_API_ERROR" and not result["errors"]
    )

    print("ZİTAR EXTERNAL RESEARCH PROBE V1.1")
    print("REAL QUERY • NETWORK DIAGNOSTIC • NO MEMORY WRITE • NO ORDER")
    print("query:", result["query"])
    print("dns:", result["dns"])
    print("http status:", result["http_status"])
    print("search count:", result["search_count"])
    print("status:", result["status"])
    print("errors:", len(result["errors"]))
    for e in result["errors"]:
        print(" ", e)
    print("transport validation:", "PASS" if transport_ok else "FAIL")
    print("classification validation:", "PASS" if classification_ok else "FAIL")
    print("output:", OUT)
    print("STATUS:", "PASS" if transport_ok and classification_ok else "FAIL")

if __name__ == "__main__":
    main()
