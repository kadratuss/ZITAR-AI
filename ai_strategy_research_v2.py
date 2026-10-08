import json
import os
import re
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path.cwd()

INPUT = ROOT / "strategy_evaluation_v3.json"
OUTPUT = ROOT / "ai_strategy_research_v2.json"

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5:7b"

STRATEGIES = (
    "SMA20_50",
    "EMA12_26",
    "RSI14",
)

FACT_FIELDS = (
    "historical_return_pct",
    "historical_max_drawdown_pct",
    "prospective_signal_rows",
    "prospective_buy_signals",
    "prospective_sell_signals",
    "prospective_none_signals",
    "prospective_trade_rows",
    "prospective_buy_trades",
    "prospective_sell_trades",
    "prospective_open_positions",
    "prospective_equity_try",
    "prospective_realized_pnl_try",
    "prospective_unrealized_pnl_try",
    "prospective_total_pnl_try",
    "prospective_return_pct",
    "prospective_drawdown_pct",
)


def atomic_json(path, obj):
    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    with tmp.open(
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            obj,
            f,
            indent=2,
            ensure_ascii=False
        )
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp, path)


def normalize(value):
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    s = str(value).strip()

    try:
        from decimal import Decimal
        return Decimal(s)
    except Exception:
        return s


def call_ollama(messages):
    payload = {
        "model": MODEL,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0
        },
        "messages": messages,
    }

    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(
            payload
        ).encode("utf-8"),
        headers={
            "Content-Type":
                "application/json"
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            req,
            timeout=180
        ) as response:
            raw = json.loads(
                response.read()
                .decode("utf-8")
            )

    except urllib.error.URLError as exc:
        raise RuntimeError(
            "Ollama connection failed: "
            + str(exc)
        )

    content = (
        raw.get("message", {})
        .get("content", "")
        .strip()
    )

    if not content:
        raise RuntimeError(
            "Empty AI response"
        )

    try:
        return json.loads(content)

    except json.JSONDecodeError:
        match = re.search(
            r"\{.*\}",
            content,
            re.DOTALL
        )

        if not match:
            raise RuntimeError(
                "AI response is not JSON"
            )

        return json.loads(
            match.group(0)
        )


if not INPUT.exists():
    raise RuntimeError(
        "strategy_evaluation_v3.json missing"
    )


evaluation = json.loads(
    INPUT.read_text(
        encoding="utf-8-sig"
    )
)

eval_rows = {
    row["strategy"]: row
    for row in evaluation[
        "strategies"
    ]
}

if set(eval_rows) != set(STRATEGIES):
    raise RuntimeError(
        "Evaluation strategy set mismatch"
    )


# ------------------------------------------------------------
# Authoritative machine facts
# ------------------------------------------------------------

facts = {}

for strategy in STRATEGIES:
    src = eval_rows[strategy]

    facts[strategy] = {
        key: src[key]
        for key in FACT_FIELDS
    }


system_prompt = """
You are PortfolioAI Research Agent V2.

You are an evidence interpretation component only.
You have ZERO trading authority.

The supplied deterministic facts are authoritative.

STRICT RULES:

1. Copy every deterministic fact into fact_echo exactly.
2. Never invent, alter, round, omit, or reinterpret fact_echo values.
3. Your prose MUST agree with fact_echo.
4. Historical backtests and prospective live-paper observations
   are separate evidence classes.
5. Historical profit does not prove future profitability.
6. Do not rank strategies.
7. Do not select a strategy.
8. Do not recommend capital allocation.
9. Do not issue BUY, SELL, HOLD, leverage, position sizing,
   or real-money instructions.
10. Zero trades does not establish quality.
11. One trade does not establish edge, win rate, robustness,
    or expected return.
12. Current evidence status for every strategy MUST be:
    INSUFFICIENT_FORWARD_EVIDENCE
13. Output JSON only.

Required structure:

{
  "agent_version": "ai_strategy_research_v2",
  "overall_evidence_status": "INSUFFICIENT_FORWARD_EVIDENCE",
  "strategies": [
    {
      "strategy": "SMA20_50",
      "evidence_status": "INSUFFICIENT_FORWARD_EVIDENCE",
      "fact_echo": { ... all supplied facts exactly ... },
      "historical_interpretation": "...",
      "prospective_interpretation": "...",
      "limitations": ["..."],
      "future_questions": ["..."]
    }
  ],
  "cross_strategy_observations": ["..."],
  "next_evidence_needed": ["..."]
}
"""


user_prompt = (
    "Interpret these deterministic facts. "
    "Do not change them.\n\n"
    + json.dumps(
        facts,
        indent=2,
        ensure_ascii=False
    )
)


print("")
print("=" * 72)
print("AI RESEARCH AGENT V2")
print("=" * 72)
print("MODEL      :", MODEL)
print("FACT SOURCE:", INPUT.name)
print("AUTHORITY  : RESEARCH ONLY")
print("REAL MONEY : NO")
print("")
print("Calling local Ollama...")


analysis = call_ollama([
    {
        "role": "system",
        "content": system_prompt,
    },
    {
        "role": "user",
        "content": user_prompt,
    },
])


if not isinstance(analysis, dict):
    raise RuntimeError(
        "AI root must be object"
    )


rows = analysis.get("strategies")

if not isinstance(rows, list):
    raise RuntimeError(
        "AI strategies must be list"
    )


ai_map = {
    row.get("strategy"): row
    for row in rows
    if isinstance(row, dict)
}


if set(ai_map) != set(STRATEGIES):
    raise RuntimeError(
        "AI strategy set mismatch"
    )


# ------------------------------------------------------------
# Deterministic fact verification
# ------------------------------------------------------------

verified = []

for strategy in STRATEGIES:
    expected = facts[strategy]
    item = ai_map[strategy]

    echo = item.get("fact_echo")

    if not isinstance(echo, dict):
        raise RuntimeError(
            f"{strategy}: fact_echo missing"
        )

    if set(echo.keys()) != set(FACT_FIELDS):
        raise RuntimeError(
            f"{strategy}: fact_echo field mismatch"
        )

    for key in FACT_FIELDS:
        if normalize(
            echo[key]
        ) != normalize(
            expected[key]
        ):
            raise RuntimeError(
                f"{strategy}: FACT MISMATCH "
                f"{key}: "
                f"AI={echo[key]} "
                f"SOURCE={expected[key]}"
            )

    if (
        item.get("evidence_status")
        !=
        "INSUFFICIENT_FORWARD_EVIDENCE"
    ):
        raise RuntimeError(
            f"{strategy}: evidence status mismatch"
        )

    verified.append(strategy)


if (
    analysis.get(
        "overall_evidence_status"
    )
    !=
    "INSUFFICIENT_FORWARD_EVIDENCE"
):
    raise RuntimeError(
        "Overall evidence status mismatch"
    )


# ------------------------------------------------------------
# Authority guard
# ------------------------------------------------------------

serialized = json.dumps(
    analysis,
    ensure_ascii=False
).lower()


forbidden = (
    "you should buy",
    "you should sell",
    "we should buy",
    "we should sell",
    "allocate capital to",
    "move capital to",
    "best strategy",
    "winning strategy",
    "use real money",
)


violations = [
    phrase
    for phrase in forbidden
    if phrase in serialized
]

if violations:
    raise RuntimeError(
        "AI authority violation: "
        + ", ".join(violations)
    )


# ------------------------------------------------------------
# Replace fact_echo with authoritative source facts.
# Even after successful equality check, stored numeric facts
# originate from Evaluation V3, not model serialization.
# ------------------------------------------------------------

for strategy in STRATEGIES:
    ai_map[strategy][
        "fact_echo"
    ] = facts[strategy]


analysis["agent_version"] = (
    "ai_strategy_research_v2"
)

analysis["overall_evidence_status"] = (
    "INSUFFICIENT_FORWARD_EVIDENCE"
)

analysis["fact_verification"] = {
    "status":
        "PASS",

    "source":
        INPUT.name,

    "verified_strategies":
        verified,

    "verified_fields_per_strategy":
        len(FACT_FIELDS),

    "total_verified_fields":
        len(FACT_FIELDS)
        * len(STRATEGIES),

    "mismatches":
        0,
}

analysis["authority"] = {
    "research":
        True,

    "strategy_selection":
        False,

    "capital_allocation":
        False,

    "trade_execution":
        False,

    "real_money":
        False,
}

analysis["generated_at_utc"] = (
    datetime.now(
        timezone.utc
    ).isoformat()
)

analysis["source_evaluation_version"] = (
    evaluation.get("version")
)


atomic_json(
    OUTPUT,
    analysis
)


print("")
print("FACT VERIFICATION")

for strategy in verified:
    print(
        " ",
        strategy,
        ": PASS"
    )

print("")
print(
    "FIELDS VERIFIED :",
    len(FACT_FIELDS)
    * len(STRATEGIES)
)

print(
    "MISMATCHES      : 0"
)


print("")
print("=" * 72)
print("AI INTERPRETATION")
print("=" * 72)

for strategy in STRATEGIES:
    item = ai_map[strategy]
    fact = facts[strategy]

    print("")
    print(strategy)

    print(
        "  SIGNALS B/S/N :",
        fact[
            "prospective_buy_signals"
        ],
        "/",
        fact[
            "prospective_sell_signals"
        ],
        "/",
        fact[
            "prospective_none_signals"
        ]
    )

    print(
        "  TRADES        :",
        fact[
            "prospective_trade_rows"
        ]
    )

    print(
        "  EQUITY        :",
        fact[
            "prospective_equity_try"
        ],
        "TRY"
    )

    print(
        "  STATUS        :",
        item[
            "evidence_status"
        ]
    )

    print(
        "  LIVE TEXT     :",
        item.get(
            "prospective_interpretation",
            ""
        )
    )


print("")
print("=" * 72)
print("AI RESEARCH AGENT V2 : PASS")
print("FACT CHECK           : PASS")
print("FACT MISMATCHES      : 0")
print("STRATEGY SELECTION   : NO")
print("CAPITAL ALLOCATION   : NO")
print("TRADE EXECUTION      : NO")
print("REAL MONEY           : NO")
print("=" * 72)
