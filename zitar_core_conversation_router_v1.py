from __future__ import annotations
import json, re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "zitar_core_router_test_v1.json"

# V1 is deterministic by design: no LLM, no execution, no memory write.
ROUTES = {
    "CONVERSATION": "Normal conversation. Do not invoke finance evidence by default.",
    "FINANCE_RESEARCH": "Route to finance research/evidence systems. No execution authority.",
    "WEB_RESEARCH": "Route to web/research tools with source/provenance requirements.",
    "MEMORY_RECALL": "Route to personal/project memory retrieval. Read-only.",
    "ACTION_REQUEST": "Potential tool/action request. Requires explicit capability/authority checks.",
    "TRADE_REQUEST": "Trading intent. Research may respond, but execution remains separately gated.",
    "UNKNOWN": "No confident route. Ask/resolve intent rather than inventing one."
}

PATTERNS = [
    ("TRADE_REQUEST", [
        r"\b(al|sat|işlem aç|pozisyon aç|long aç|short aç|emir ver|trade yap)\b",
        r"\b(alalım mı|satalım mı|long girelim|short girelim)\b",
    ]),
    ("WEB_RESEARCH", [
        r"\b(internette|internetten|webde|web'de|araştır|araştırsana|haberleri bul|kaynak bul)\b",
    ]),
    ("MEMORY_RECALL", [
        r"\b(hatırla|hatırlıyor musun|daha önce|önceki proje|geçen sefer|ne yapmıştık|konuşmuştuk)\b",
    ]),
    ("FINANCE_RESEARCH", [
        r"\b(btc|bitcoin|eth|ethereum|sol|xrp|doge|kripto|piyasa|funding|open interest|oi|futures|vadeli)\b",
    ]),
    ("ACTION_REQUEST", [
        r"\b(aç|kapat|başlat|durdur|çalıştır|oluştur|gönder|indir|yükle|kaydet)\b",
    ]),
    ("CONVERSATION", [
        r"\b(nasılsın|naber|ne haber|selam|merhaba|günaydın|iyi akşamlar|teşekkür|sağ ol)\b",
    ]),
]

def norm(text):
    return re.sub(r"\s+", " ", text.strip().lower())

def route(text):
    t = norm(text)
    matches = []
    for name, pats in PATTERNS:
        if any(re.search(p, t, flags=re.IGNORECASE) for p in pats):
            matches.append(name)

    # Explicit precedence: trade > web > memory > finance > action > conversation.
    # This is routing only, never permission.
    selected = matches[0] if matches else "UNKNOWN"
    return {
        "text": text,
        "route": selected,
        "matched_routes": matches,
        "execution_authority": False,
        "memory_write": False,
        "llm_used": False,
        "reason": ROUTES[selected]
    }

TESTS = [
    ("Nasılsın?", "CONVERSATION"),
    ("Selam baba, ne haber?", "CONVERSATION"),
    ("BTC hakkında şu an ne görüyorsun?", "FINANCE_RESEARCH"),
    ("BTC alalım mı?", "TRADE_REQUEST"),
    ("BTC için long aç", "TRADE_REQUEST"),
    ("NVIDIA'nın bugün duyurusu var mı, internette araştır", "WEB_RESEARCH"),
    ("Model tren projesinde daha önce ne yapmıştık?", "MEMORY_RECALL"),
    ("Geçen sefer BTC hakkında ne konuşmuştuk?", "MEMORY_RECALL"),
    ("Programı başlat", "ACTION_REQUEST"),
    ("Bundan ne öğrendin?", "UNKNOWN"),
]

def main():
    results = []
    passed = 0
    for text, expected in TESTS:
        r = route(text)
        ok = r["route"] == expected
        passed += int(ok)
        r["expected"] = expected
        r["pass"] = ok
        results.append(r)

    payload = {
        "schema": "ZITAR_CORE_CONVERSATION_ROUTER_TEST_V1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "DETERMINISTIC_ROUTING_TEST",
        "execution_authority": False,
        "memory_write": False,
        "tests": results,
        "passed": passed,
        "total": len(results)
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("ZİTAR CORE CONVERSATION ROUTER V1")
    print("DETERMINISTIC • NO LLM • NO ORDER • NO MEMORY WRITE")
    for r in results:
        print(f"{'PASS' if r['pass'] else 'FAIL':4} | {r['route']:16} | {r['text']}")
        if not r["pass"]:
            print(f"       expected={r['expected']} matched={r['matched_routes']}")
    print(f"\nRESULT: {passed}/{len(results)} PASS")
    print("output:", OUT)
    print("STATUS:", "PASS" if passed == len(results) else "FAIL")

if __name__ == "__main__":
    main()
