import json
import os
import re
import urllib.request
import urllib.error

from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal

ROOT = Path.cwd()

INPUT = ROOT / "strategy_evaluation_v3.json"
OUTPUT = ROOT / "ai_strategy_research_v2_1.json"

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

    try:
        return Decimal(
            str(value).strip()
        )

    except Exception:
        return str(value).strip()


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

    request = urllib.request.Request(
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
            request,
            timeout=180
        ) as response:

            result = json.loads(
                response.read()
                .decode("utf-8")
            )

    except urllib.error.URLError as exc:

        raise RuntimeError(
            "Ollama connection failed: "
            + str(exc)
        )


    content = (
        result
        .get("message", {})
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


eval_map = {
    row["strategy"]: row
    for row in evaluation[
        "strategies"
    ]
}


if set(eval_map) != set(STRATEGIES):

    raise RuntimeError(
        "Evaluation strategy mismatch"
    )


facts = {}

for strategy in STRATEGIES:

    source = eval_map[strategy]

    facts[strategy] = {
        key: source[key]
        for key in FACT_FIELDS
    }


# ------------------------------------------------------------
# V2.1 prompt:
# Ask the model to discuss interpretation WITHOUT repeating
# ledger counts in free prose.
#
# Exact measurements belong to deterministic_fact_summary.
# ------------------------------------------------------------

system_prompt = """
You are PortfolioAI Research Agent V2.1.

You are a research interpretation component only.
You have ZERO trading authority.

The deterministic facts supplied by the program are authoritative.

STRICT RULES:

1. fact_echo must copy every supplied fact exactly.

2. Do NOT restate signal counts, trade counts, equity, PnL,
   return, or drawdown values in free-form interpretation text.
   Those measurements are already stored separately.

3. prospective_interpretation may discuss ONLY what can
   cautiously be inferred from the amount of evidence.

4. Do not say a strategy generated no signals if any BUY or
   SELL signal exists in fact_echo.

5. Do not say there were no trades if prospective_trade_rows
   is greater than zero.

6. Do not say there are no positions if
   prospective_open_positions is greater than zero.

7. Do not claim profitability, robustness, edge, win rate,
   expected return, or market suitability from this small sample.

8. Historical and prospective evidence are separate.

9. Historical profitability does not prove future profitability.

10. Do not rank strategies.

11. Do not select a strategy.

12. Do not recommend capital allocation.

13. Do not issue BUY, SELL, HOLD, leverage, position-size,
    or real-money instructions.

14. evidence_status for every strategy must be:
    INSUFFICIENT_FORWARD_EVIDENCE

15. Output JSON only.

Required structure:

{
  "agent_version": "ai_strategy_research_v2_1",
  "overall_evidence_status": "INSUFFICIENT_FORWARD_EVIDENCE",
  "strategies": [
    {
      "strategy": "...",
      "evidence_status": "INSUFFICIENT_FORWARD_EVIDENCE",
      "fact_echo": { ... },
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
    "Analyze the evidence conservatively. "
    "Copy fact_echo exactly. "
    "Do not repeat measurements in prose.\n\n"
    + json.dumps(
        facts,
        ensure_ascii=False,
        indent=2
    )
)


print("")
print("=" * 72)
print("AI RESEARCH AGENT V2.1")
print("FACT + SEMANTIC CONSISTENCY")
print("=" * 72)

print(
    "MODEL      :",
    MODEL
)

print(
    "FACT SOURCE:",
    INPUT.name
)

print(
    "AUTHORITY  : RESEARCH ONLY"
)

print(
    "REAL MONEY : NO"
)

print("")
print("Calling local Ollama...")


analysis = call_ollama(
    [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]
)


if not isinstance(
    analysis,
    dict
):

    raise RuntimeError(
        "AI root must be object"
    )


rows = analysis.get(
    "strategies"
)

if not isinstance(
    rows,
    list
):

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
# Exact fact verification
# ------------------------------------------------------------

verified_fields = 0


for strategy in STRATEGIES:

    expected = facts[strategy]
    item = ai_map[strategy]

    echo = item.get(
        "fact_echo"
    )

    if not isinstance(
        echo,
        dict
    ):

        raise RuntimeError(
            f"{strategy}: fact_echo missing"
        )


    if set(echo.keys()) != set(FACT_FIELDS):

        raise RuntimeError(
            f"{strategy}: fact fields mismatch"
        )


    for key in FACT_FIELDS:

        if (
            normalize(echo[key])
            !=
            normalize(expected[key])
        ):

            raise RuntimeError(
                f"{strategy}: FACT MISMATCH "
                f"{key}: AI={echo[key]} "
                f"SOURCE={expected[key]}"
            )

        verified_fields += 1


    if (
        item.get(
            "evidence_status"
        )
        !=
        "INSUFFICIENT_FORWARD_EVIDENCE"
    ):

        raise RuntimeError(
            f"{strategy}: evidence status mismatch"
        )


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
# Semantic contradiction guard
#
# This does NOT try to understand all English.
# It catches dangerous/basic contradictions between
# deterministic ledger facts and free-form AI commentary.
# ------------------------------------------------------------

semantic_checks = []


for strategy in STRATEGIES:

    item = ai_map[strategy]
    fact = facts[strategy]

    text = " ".join([
        str(
            item.get(
                "historical_interpretation",
                ""
            )
        ),
        str(
            item.get(
                "prospective_interpretation",
                ""
            )
        ),
        " ".join(
            map(
                str,
                item.get(
                    "limitations",
                    []
                )
            )
        ),
    ]).lower()


    buy_signals = int(
        fact[
            "prospective_buy_signals"
        ]
    )

    sell_signals = int(
        fact[
            "prospective_sell_signals"
        ]
    )

    trades = int(
        fact[
            "prospective_trade_rows"
        ]
    )

    positions = int(
        fact[
            "prospective_open_positions"
        ]
    )


    contradictions = []


    no_signal_patterns = (
        "no prospective buy or sell signals",
        "not generated any prospective buy or sell signals",
        "did not generate any prospective buy or sell signals",
        "no buy or sell signals",
        "did not generate any signals",
        "has not generated any signals",
        "no signals were generated",
    )


    if (
        buy_signals
        + sell_signals
        > 0
    ):

        for phrase in no_signal_patterns:

            if phrase in text:

                contradictions.append(
                    "CLAIMED_NO_SIGNALS"
                )

                break


    no_trade_patterns = (
        "no prospective trades",
        "no trades recorded",
        "there are no prospective trades",
        "there were no prospective trades",
        "no trades were recorded",
        "zero trades",
    )


    if trades > 0:

        for phrase in no_trade_patterns:

            if phrase in text:

                contradictions.append(
                    "CLAIMED_NO_TRADES"
                )

                break


    no_position_patterns = (
        "no open positions",
        "there are no open positions",
        "has no open positions",
        "zero open positions",
    )


    if positions > 0:

        for phrase in no_position_patterns:

            if phrase in text:

                contradictions.append(
                    "CLAIMED_NO_POSITIONS"
                )

                break


    semantic_checks.append({
        "strategy":
            strategy,

        "status":
            (
                "PASS"
                if not contradictions
                else "FAIL"
            ),

        "contradictions":
            contradictions,
    })


failed = [
    row
    for row in semantic_checks
    if row["status"] != "PASS"
]


if failed:

    raise RuntimeError(
        "SEMANTIC CONTRADICTION: "
        + json.dumps(
            failed,
            ensure_ascii=False
        )
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
        + ", ".join(
            violations
        )
    )


# ------------------------------------------------------------
# Stored facts are replaced with source facts after validation.
# ------------------------------------------------------------

for strategy in STRATEGIES:

    ai_map[strategy][
        "fact_echo"
    ] = facts[strategy]


analysis[
    "agent_version"
] = (
    "ai_strategy_research_v2_1"
)


analysis[
    "overall_evidence_status"
] = (
    "INSUFFICIENT_FORWARD_EVIDENCE"
)


analysis[
    "verification"
] = {
    "fact_check":
        "PASS",

    "semantic_check":
        "PASS",

    "verified_fields":
        verified_fields,

    "fact_mismatches":
        0,

    "semantic_contradictions":
        0,

    "strategy_checks":
        semantic_checks,
}


analysis[
    "authority"
] = {
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


analysis[
    "generated_at_utc"
] = (
    datetime.now(
        timezone.utc
    ).isoformat()
)


analysis[
    "source_evaluation_version"
] = evaluation.get(
    "version"
)


atomic_json(
    OUTPUT,
    analysis
)


print("")
print("FACT CHECK")

for strategy in STRATEGIES:

    print(
        " ",
        strategy,
        ": PASS"
    )


print("")
print(
    "FIELDS VERIFIED       :",
    verified_fields
)

print(
    "FACT MISMATCHES       : 0"
)

print(
    "SEMANTIC CONTRADICTION: 0"
)


print("")
print("=" * 72)
print("SEMANTIC CHECK")
print("=" * 72)


for check in semantic_checks:

    print(
        check["strategy"],
        ":",
        check["status"]
    )


print("")
print("=" * 72)
print("AUTHORITATIVE FACT SUMMARY")
print("=" * 72)


for strategy in STRATEGIES:

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
        "  POSITIONS     :",
        fact[
            "prospective_open_positions"
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
        "INSUFFICIENT_FORWARD_EVIDENCE"
    )

    print(
        "  AI TEXT       :",
        ai_map[strategy].get(
            "prospective_interpretation",
            ""
        )
    )


print("")
print("=" * 72)
print("AI RESEARCH V2.1       : PASS")
print("FACT CHECK             : PASS")
print("SEMANTIC CHECK         : PASS")
print("STRATEGY SELECTION     : NO")
print("CAPITAL ALLOCATION     : NO")
print("TRADE EXECUTION        : NO")
print("REAL MONEY             : NO")
print("=" * 72)
