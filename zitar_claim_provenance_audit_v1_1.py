from __future__ import annotations
import json, hashlib, urllib.request
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
URL = "http://127.0.0.1:5016/api/chat"
OUT = BASE / "zitar_claim_provenance_audit_v1_1.json"

TESTS = [
    ("BTC hakkında şu an ne görüyorsun?", "BTCTRY"),
    ("BTC hakkındaki görüşün değişti mi?", "BTCTRY"),
    ("Bu haberler BTC'yi düşürdü mü?", "BTCTRY"),
]

# A claim family may legitimately be supported by multiple registered producers.
RULES = [
    {
        "category": "DERIVED_ANALYSIS",
        "producers": ["zitar_mtf_research_v2.py"],
        "match": lambda s: any(x in s for x in ["kısa=", "orta=", "uzun=", "zaman dilimleri", "momentum"]),
    },
    {
        "category": "MEMORY",
        "producers": ["zitar_research_memory_v1.jsonl"],
        "match": lambda s: any(x in s for x in ["Memory v", "BASELINE_ONLY", "durable_change", "görüş değiş"]),
    },
    {
        "category": "EXTERNAL_EVIDENCE",
        "producers": ["News Intelligence", "Event Radar"],
        "match": lambda s: any(x in s for x in ["İlgili kayıt", "Haber/fiyat", "nedensellik", "zamansal"]),
    },
    {
        "category": "INFERENCE",
        "producers": ["ZITAR Chat canonical synthesis"],
        "match": lambda s: any(x in s for x in ["Mevcut kanıt", "Çelişkiler korunur", "tahmini değildir"]),
    },
]

def ask(q):
    body = json.dumps({"question": q, "use_qwen": True}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        URL, data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    reg_path = BASE / "zitar_provenance_registry_v1.json"
    if not reg_path.exists():
        raise SystemExit("FAIL: zitar_provenance_registry_v1.json bulunamadı.")

    registry = json.loads(reg_path.read_text(encoding="utf-8"))
    known = {(x["category"], x["producer"]) for x in registry["entries"]}

    runs, errors = [], []

    for question, expected_symbol in TESTS:
        response = ask(question)
        answer = str(response.get("answer") or "")
        claims = []

        for rule in RULES:
            if not rule["match"](answer):
                continue

            sources = []
            for producer in rule["producers"]:
                ok = (rule["category"], producer) in known
                sources.append({"producer": producer, "registered": ok})
                if not ok:
                    errors.append(
                        f"UNKNOWN_PRODUCER:{question}:{rule['category']}:{producer}"
                    )

            claims.append({
                "category": rule["category"],
                "sources": sources,
                "multi_source": len(sources) > 1,
            })

        if response.get("symbol") != expected_symbol:
            errors.append(
                f"SYMBOL:{question}:{response.get('symbol')}!=expected:{expected_symbol}"
            )
        if not claims:
            errors.append(f"NO_PROVENANCE:{question}")

        runs.append({
            "question": question,
            "symbol": response.get("symbol"),
            "intent": response.get("intent"),
            "mode": response.get("mode"),
            "guard": response.get("guard"),
            "claims": claims,
            "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
        })

        print("\nQUESTION:", question)
        print("symbol:", response.get("symbol"),
              "| intent:", response.get("intent"),
              "| mode:", response.get("mode"))
        for claim in claims:
            print(" ", claim["category"])
            for src in claim["sources"]:
                print("    ->", src["producer"], "|", "OK" if src["registered"] else "FAIL")

    payload = {
        "schema": "ZITAR_CLAIM_PROVENANCE_AUDIT_V1_1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "registry_sha256": registry.get("registry_sha256"),
        "tests": runs,
        "errors": errors,
        "rules": {
            "external_evidence_is_multi_source": True,
            "temporal_association_is_not_causation": True,
            "inference_is_not_primary_evidence": True,
        },
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nerrors:", len(errors))
    for e in errors:
        print(" ", e)
    print("output:", OUT)
    print("STATUS:", "PASS" if not errors else "FAIL")

if __name__ == "__main__":
    main()
