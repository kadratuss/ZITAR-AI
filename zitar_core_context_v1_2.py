from __future__ import annotations
import json, re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "zitar_core_context_test_v1.json"

# Lab-only short-term context. Nothing is persisted as personal memory.
DOMAIN_PATTERNS = {
    "FINANCE": [
        r"\b(btc|bitcoin|eth|ethereum|sol|xrp|doge|kripto|piyasa|funding|open interest|oi|futures|vadeli)\b"
    ],
    "MODEL_TRAIN": [
        r"\b(model tren|tren projes|lokomotif|vagon|makas|ray|istasyon|g scale|g skala)\b"
    ],
}

FOLLOWUP_PATTERNS = [
    r"\b(bundan|bunun|peki|o zaman|sonra|devam|en son|ne öğrendin|ne dusunuyorsun|ne düşünüyorsun)\b",
    r"^(neden|niye|nasıl|nasil|peki)\b",
]

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())

def detect_domain(text: str):
    t = norm(text)
    for domain, pats in DOMAIN_PATTERNS.items():
        if any(re.search(p, t, re.I) for p in pats):
            return domain
    return None

def is_followup(text: str):
    t = norm(text)
    return any(re.search(p, t, re.I) for p in FOLLOWUP_PATTERNS)

def base_route(text: str):
    t = norm(text)
    if re.search(r"\b(alalım mı|satalım mı|long aç|short aç|işlem aç|pozisyon aç|emir ver)\b", t, re.I):
        return "TRADE_REQUEST"
    if re.search(r"\b(internette|internetten|webde|web'de|araştır|haberleri bul|kaynak bul)\b", t, re.I):
        return "WEB_RESEARCH"
    # Explicit memory request only. Generic follow-ups such as
    # "En son ne yapmıştık?" must be resolved by conversation context,
    # otherwise we would falsely claim the current sentence itself
    # contains enough domain information.
    if re.search(r"\b(hatırla|hatırlıyor musun|daha önce|önceki proje|geçen sefer)\b", t, re.I):
        return "MEMORY_RECALL"
    if detect_domain(text) == "FINANCE":
        return "FINANCE_RESEARCH"
    if re.search(r"\b(nasılsın|naber|ne haber|selam|merhaba|günaydın|iyi akşamlar)\b", t, re.I):
        return "CONVERSATION"
    return "UNKNOWN"

class ConversationContext:
    def __init__(self):
        self.active_domain = None
        self.last_route = None
        self.turn = 0

    def resolve(self, text: str):
        self.turn += 1
        explicit_domain = detect_domain(text)
        raw_route = base_route(text)
        inherited = False

        previous_domain = self.active_domain

        if explicit_domain:
            self.active_domain = explicit_domain

        resolved_route = raw_route

        # An explicit domain mention is NOT inheritance. Even if the sentence
        # itself is otherwise ambiguous, the user has explicitly switched or
        # selected the domain in the current turn.
        if raw_route == "UNKNOWN" and explicit_domain:
            if explicit_domain == "FINANCE":
                resolved_route = "FINANCE_RESEARCH"
            elif explicit_domain == "MODEL_TRAIN":
                resolved_route = "MEMORY_RECALL"

        # Only a genuinely domain-ambiguous follow-up may inherit prior context.
        elif raw_route == "UNKNOWN" and is_followup(text) and previous_domain:
            inherited = True
            self.active_domain = previous_domain
            if previous_domain == "FINANCE":
                resolved_route = "FINANCE_RESEARCH"
            elif previous_domain == "MODEL_TRAIN":
                resolved_route = "MEMORY_RECALL"

        # Explicit ordinary conversation must not be hijacked by stale finance context.
        if raw_route == "CONVERSATION":
            inherited = False

        self.last_route = resolved_route
        return {
            "turn": self.turn,
            "text": text,
            "raw_route": raw_route,
            "resolved_route": resolved_route,
            "explicit_domain": explicit_domain,
            "active_domain": self.active_domain,
            "context_inherited": inherited,
            "execution_authority": False,
            "persistent_memory_write": False,
        }

SCENARIOS = [
    {
        "name": "finance_followup",
        "turns": [
            ("BTC hakkında ne görüyorsun?", "FINANCE_RESEARCH", "FINANCE", False),
            ("Peki bundan ne öğrendin?", "FINANCE_RESEARCH", "FINANCE", True),
        ],
    },
    {
        "name": "train_followup",
        "turns": [
            ("Model tren projesini hatırlıyor musun?", "MEMORY_RECALL", "MODEL_TRAIN", False),
            ("En son ne yapmıştık?", "MEMORY_RECALL", "MODEL_TRAIN", True),
        ],
    },
    {
        "name": "conversation_not_hijacked",
        "turns": [
            ("BTC nasıl?", "FINANCE_RESEARCH", "FINANCE", False),
            ("Nasılsın?", "CONVERSATION", "FINANCE", False),
        ],
    },
    {
        "name": "no_context_no_guess",
        "turns": [
            ("Bundan ne öğrendin?", "UNKNOWN", None, False),
        ],
    },
    {
        "name": "explicit_domain_switch",
        "turns": [
            ("BTC hakkında ne görüyorsun?", "FINANCE_RESEARCH", "FINANCE", False),
            ("Model tren projesinde en son ne yapmıştık?", "MEMORY_RECALL", "MODEL_TRAIN", False),
            ("Peki sonra ne yapacağız?", "MEMORY_RECALL", "MODEL_TRAIN", True),
        ],
    },
]

def main():
    results=[]
    passed=0
    total=0

    for scenario in SCENARIOS:
        ctx=ConversationContext()
        sr={"scenario":scenario["name"],"turns":[]}
        for text, exp_route, exp_domain, exp_inherited in scenario["turns"]:
            total += 1
            r=ctx.resolve(text)
            ok=(r["resolved_route"]==exp_route and
                r["active_domain"]==exp_domain and
                r["context_inherited"]==exp_inherited)
            passed += int(ok)
            r["expected_route"]=exp_route
            r["expected_domain"]=exp_domain
            r["expected_inherited"]=exp_inherited
            r["pass"]=ok
            sr["turns"].append(r)
        results.append(sr)

    payload={
        "schema":"ZITAR_CORE_CONTEXT_TEST_V1_2",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "mode":"SHORT_TERM_CONTEXT_LAB",
        "persistent_memory_write":False,
        "execution_authority":False,
        "scenarios":results,
        "passed":passed,
        "total":total,
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

    print("ZİTAR CORE CONTEXT V1.2")
    print("SHORT-TERM CONTEXT • NO LLM • NO ORDER • NO PERSISTENT MEMORY WRITE")
    for s in results:
        print(f"\n[{s['scenario']}]")
        for r in s["turns"]:
            print(f"{'PASS' if r['pass'] else 'FAIL':4} | "
                  f"raw={r['raw_route']:16} resolved={r['resolved_route']:16} "
                  f"domain={str(r['active_domain']):11} inherited={r['context_inherited']} | {r['text']}")
    print(f"\nRESULT: {passed}/{total} PASS")
    print("output:",OUT)
    print("STATUS:","PASS" if passed==total else "FAIL")

if __name__=="__main__":
    main()
