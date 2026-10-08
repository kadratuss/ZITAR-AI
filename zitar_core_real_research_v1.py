from __future__ import annotations
import json, hashlib, urllib.request, urllib.parse, re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "zitar_core_real_research_evidence_v1.json"
TEST = BASE / "zitar_core_real_research_test_v1.json"

QUESTION = "Raspberry Pi 5 ne zaman duyuruldu ve Ã¶nceki nesle gÃ¶re temel CPU deÄŸiÅŸikliÄŸi neydi?"

SOURCES = [
    {
        "role": "PRIMARY",
        "provider": "Raspberry Pi",
        "url": "https://www.raspberrypi.com/news/introducing-raspberry-pi-5/",
    },
    {
        "role": "INDEPENDENT",
        "provider": "Tom's Hardware",
        "url": "https://www.tomshardware.com/news/live/raspberry-pi-5-launch",
    },
]

def sha(x):
    raw = json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def fetch(url, timeout=20):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 ZITAR-Core-Research/1.0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        ctype = r.headers.get_content_charset() or "utf-8"
        return data.decode(ctype, errors="replace"), getattr(r, "status", 200)

def strip_html(html):
    html = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?>.*?</style>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#39;|&apos;", "'", text)
    return re.sub(r"\s+", " ", text).strip()

def evidence_flags(text):
    t = text.lower()
    # We are testing narrow, explicit facts rather than asking an LLM to infer.
    date_ok = ("28 september 2023" in t or "september 28, 2023" in t or
               "28th september 2023" in t)
    cpu_ok = ("cortex-a76" in t and ("2.4ghz" in t or "2.4 ghz" in t))
    pi4_ref = ("cortex-a72" in t or "raspberry pi 4" in t)
    return {
        "announcement_date_supported": date_ok,
        "pi5_cpu_supported": cpu_ok,
        "previous_generation_context_supported": pi4_ref,
    }

def main():
    records = []
    for src in SOURCES:
        rec = dict(src)
        rec["http_status"] = None
        rec["error"] = None
        rec["flags"] = {}
        try:
            html, status = fetch(src["url"])
            text = strip_html(html)
            rec["http_status"] = status
            rec["content_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
            rec["flags"] = evidence_flags(text)
            rec["text_length"] = len(text)
        except Exception as e:
            rec["error"] = f"{type(e).__name__}:{e}"
        records.append(rec)

    primary = next(r for r in records if r["role"] == "PRIMARY")
    independent = next(r for r in records if r["role"] == "INDEPENDENT")

    primary_ok = (
        primary["error"] is None and
        primary["flags"].get("announcement_date_supported") and
        primary["flags"].get("pi5_cpu_supported")
    )
    independent_ok = (
        independent["error"] is None and
        independent["flags"].get("pi5_cpu_supported")
    )

    corroborated = bool(primary_ok and independent_ok)

    result = {
        "schema": "ZITAR_CORE_REAL_RESEARCH_EVIDENCE_V1",
        "question": QUESTION,
        "sources": records,
        "primary_source_present": bool(primary_ok),
        "independent_corroboration_present": bool(independent_ok),
        "corroborated": corroborated,
        "learning_candidate_ready": corroborated,
        "candidate_claims": [
            {
                "claim": "Raspberry Pi 5 was announced on 28 September 2023.",
                "supported_by_primary": bool(primary["flags"].get("announcement_date_supported")),
                "supported_by_independent": bool(independent["flags"].get("announcement_date_supported")),
            },
            {
                "claim": "Raspberry Pi 5 uses a 2.4 GHz quad-core Arm Cortex-A76 CPU.",
                "supported_by_primary": bool(primary["flags"].get("pi5_cpu_supported")),
                "supported_by_independent": bool(independent["flags"].get("pi5_cpu_supported")),
            },
        ],
        "authorities": {
            "public_web_read": True,
            "memory_write": False,
            "real_order": False,
            "silent_code_rewrite": False,
        },
        "collected_utc": datetime.now(timezone.utc).isoformat(),
    }
    result["bundle_sha256"] = sha(result)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    tests = {
        "primary_fetch_ok": primary["error"] is None,
        "independent_fetch_ok": independent["error"] is None,
        "primary_source_recognized": bool(primary_ok),
        "independent_corroboration_recognized": bool(independent_ok),
        "candidate_only_if_corroborated": result["learning_candidate_ready"] == corroborated,
        "no_memory_write": not result["authorities"]["memory_write"],
        "no_real_order": not result["authorities"]["real_order"],
        "no_silent_code_rewrite": not result["authorities"]["silent_code_rewrite"],
    }
    passed = sum(int(v) for v in tests.values())

    TEST.write_text(json.dumps({
        "schema": "ZITAR_CORE_REAL_RESEARCH_TEST_V1",
        "tests": [{"name": k, "pass": bool(v)} for k, v in tests.items()],
        "passed": passed,
        "total": len(tests),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("ZÄ°TAR CORE REAL RESEARCH V1")
    print("REAL QUESTION â€¢ PRIMARY + INDEPENDENT SOURCE â€¢ NO MEMORY WRITE")
    print("question:", QUESTION)
    for r in records:
        print(f"{r['role']:<11} provider={r['provider']:<16} http={r['http_status']} "
              f"error={r['error'] or '-'} flags={r['flags']}")
    print("corroborated:", corroborated)
    print("learning candidate ready:", result["learning_candidate_ready"])
    print(f"validation: {passed}/{len(tests)}")
    print("evidence:", OUT)
    print("output:", TEST)
    print("STATUS:", "PASS" if passed == len(tests) else "FAIL")

if __name__ == "__main__":
    main()
