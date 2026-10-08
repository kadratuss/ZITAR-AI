import json
import os
import re
import urllib.request
import urllib.error

from pathlib import Path
from datetime import datetime, timezone

ROOT = Path.cwd()

INPUT = ROOT / "strategy_evaluation_v3.json"
OUTPUT = ROOT / "ai_strategy_research_v2_2.json"

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
            "Empty Ollama response"
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
    for row in evaluation["strategies"]
}

if set(eval_map) != set(STRATEGIES):
    raise RuntimeError(
        "Evaluation strategy mismatch"
    )


# ------------------------------------------------------------
# AUTHORITATIVE FACTS
# ------------------------------------------------------------

facts = {}

for strategy in STRATEGIES:
    source = eval_map[strategy]

    facts[strategy] = {
        key: source[key]
        for key in FACT_FIELDS
    }


# ------------------------------------------------------------
# DETERMINISTIC NARRATIVE
#
# AI does NOT write these factual statements.
# ------------------------------------------------------------

deterministic_summary = {}

for strategy in STRATEGIES:
    f = facts[strategy]

    deterministic_summary[strategy] = {
        "historical":
            (
                f"Historical research return: "
                f"{f['historical_return_pct']}%; "
                f"historical max drawdown: "
                f"{f['historical_max_drawdown_pct']}%. "
                f"Historical evidence is separate from "
                f"prospective evidence."
            ),

        "prospective":
            (
                f"Prospective ledger contains "
                f"{f['prospective_buy_signals']} BUY, "
                f"{f['prospective_sell_signals']} SELL, "
                f"{f['prospective_none_signals']} NONE "
                f"signal rows; "
                f"{f['prospective_trade_rows']} trade rows; "
                f"{f['prospective_open_positions']} open "
                f"positions; equity "
                f"{f['prospective_equity_try']} TRY; "
                f"total PnL "
                f"{f['prospective_total_pnl_try']} TRY; "
                f"prospective return "
                f"{f['prospective_return_pct']}%."
            ),

        "evidence_status":
            "INSUFFICIENT_FORWARD_EVIDENCE",
    }


# ------------------------------------------------------------
# AI receives facts for context, but is allowed to produce
# ONLY limitations and future research questions.
# ------------------------------------------------------------

system_prompt = """
You are PortfolioAI Research Agent V2.2.

You are a limited research assistant.

The program already owns all factual summaries.
You are NOT allowed to produce performance summaries.

Your only job is to produce:
- limitations
- future_questions
- cross_strategy_research_questions

STRICT RULES:

1. Do not state signal counts.
2. Do not state trade counts.
3. Do not state position counts.
4. Do not state equity.
5. Do not state PnL.
6. Do not state returns.
7. Do not state drawdown.
8. Do not state that signals/trades/positions exist or do not exist.
9. Do not rank strategies.
10. Do not select strategies.
11. Do not recommend capital allocation.
12. Do not issue BUY, SELL, HOLD, leverage, position-size,
    or real-money instructions.
13. Do not claim profitability, edge, robustness, expected return,
    win rate, or future performance.
14. Focus on sample-size limitations, regime coverage,
    execution realism, spread/liquidity, duration,
    and questions that future evidence should answer.
15. Output JSON only.

Required structure:

{
  "agent_version": "ai_strategy_research_v2_2",
  "strategies": [
    {
      "strategy": "...",
      "limitations": ["..."],
      "future_questions": ["..."]
    }
  ],
  "cross_strategy_research_questions": ["..."]
}
"""


user_prompt = (
    "Generate research limitations and future questions only.\n\n"
    + json.dumps(
        facts,
        ensure_ascii=False,
        indent=2
    )
)


print("")
print("=" * 72)
print("AI RESEARCH AGENT V2.2")
print("=" * 72)
print("MODEL      :", MODEL)
print("FACT SOURCE:", INPUT.name)
print("AI ROLE    : LIMITATIONS + QUESTIONS ONLY")
print("AUTHORITY  : RESEARCH ONLY")
print("REAL MONEY : NO")
print("")
print("Calling local Ollama...")


ai = call_ollama([
    {
        "role": "system",
        "content": system_prompt,
    },
    {
        "role": "user",
        "content": user_prompt,
    },
])


if not isinstance(ai, dict):
    raise RuntimeError(
        "AI root must be object"
    )


rows = ai.get("strategies")

if not isinstance(rows, list):
    raise RuntimeError(
        "AI strategies missing"
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
# Validate allowed AI schema.
# No hidden extra prose fields.
# ------------------------------------------------------------

ALLOWED_STRATEGY_KEYS = {
    "strategy",
    "limitations",
    "future_questions",
}

for strategy in STRATEGIES:
    row = ai_map[strategy]

    extra = (
        set(row.keys())
        - ALLOWED_STRATEGY_KEYS
    )

    if extra:
        raise RuntimeError(
            f"{strategy}: forbidden AI fields: "
            + str(sorted(extra))
        )

    if not isinstance(
        row.get("limitations"),
        list
    ):
        raise RuntimeError(
            f"{strategy}: limitations must be list"
        )

    if not isinstance(
        row.get("future_questions"),
        list
    ):
        raise RuntimeError(
            f"{strategy}: future_questions must be list"
        )


allowed_root = {
    "agent_version",
    "strategies",
    "cross_strategy_research_questions",
}

root_extra = (
    set(ai.keys())
    - allowed_root
)

if root_extra:
    raise RuntimeError(
        "Forbidden root AI fields: "
        + str(sorted(root_extra))
    )


# ------------------------------------------------------------
# Conservative text guard.
#
# Since AI is not supposed to state measurements at all,
# reject obvious measurement/performance language.
# ------------------------------------------------------------

ai_text = json.dumps(
    ai,
    ensure_ascii=False
).lower()


forbidden_phrases = (
    "you should buy",
    "you should sell",
    "we should buy",
    "we should sell",
    "allocate capital",
    "move capital",
    "best strategy",
    "winning strategy",
    "use real money",
    "generated no signals",
    "generated no trades",
    "no signals",
    "no trades",
    "zero trades",
    "open positions",
    "profit of",
    "loss of",
)


violations = [
    phrase
    for phrase in forbidden_phrases
    if phrase in ai_text
]

if violations:
    raise RuntimeError(
        "AI TEXT GUARD FAIL: "
        + ", ".join(violations)
    )


# ------------------------------------------------------------
# Build final object.
#
# All measurements and factual narratives are produced by
# deterministic Python, not by Qwen.
# ------------------------------------------------------------

strategies_out = []

for strategy in STRATEGIES:
    strategies_out.append({
        "strategy":
            strategy,

        "evidence_status":
            "INSUFFICIENT_FORWARD_EVIDENCE",

        "authoritative_facts":
            facts[strategy],

        "deterministic_summary":
            deterministic_summary[
                strategy
            ],

        "ai_research_commentary": {
            "limitations":
                ai_map[strategy][
                    "limitations"
                ],

            "future_questions":
                ai_map[strategy][
                    "future_questions"
                ],
        },
    })


result = {
    "agent_version":
        "ai_strategy_research_v2_2",

    "generated_at_utc":
        datetime.now(
            timezone.utc
        ).isoformat(),

    "source_file":
        INPUT.name,

    "source_evaluation_version":
        evaluation.get("version"),

    "overall_evidence_status":
        "INSUFFICIENT_FORWARD_EVIDENCE",

    "architecture": {
        "facts_generated_by":
            "deterministic_python",

        "factual_narrative_generated_by":
            "deterministic_python",

        "ai_role":
            "limitations_and_future_questions_only",
    },

    "strategies":
        strategies_out,

    "cross_strategy_research_questions":
        ai.get(
            "cross_strategy_research_questions",
            []
        ),

    "verification": {
        "fact_source":
            INPUT.name,

        "fact_fields_per_strategy":
            len(FACT_FIELDS),

        "total_authoritative_fact_fields":
            len(FACT_FIELDS)
            * len(STRATEGIES),

        "ai_factual_summary_allowed":
            False,

        "schema_guard":
            "PASS",

        "text_guard":
            "PASS",
    },

    "authority": {
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
    },
}


atomic_json(
    OUTPUT,
    result
)


print("")
print("=" * 72)
print("AUTHORITATIVE FACT SUMMARY")
print("=" * 72)


for strategy in STRATEGIES:
    f = facts[strategy]

    print("")
    print(strategy)

    print(
        "  SIGNALS B/S/N :",
        f["prospective_buy_signals"],
        "/",
        f["prospective_sell_signals"],
        "/",
        f["prospective_none_signals"]
    )

    print(
        "  TRADES        :",
        f["prospective_trade_rows"]
    )

    print(
        "  POSITIONS     :",
        f["prospective_open_positions"]
    )

    print(
        "  EQUITY        :",
        f["prospective_equity_try"],
        "TRY"
    )

    print(
        "  STATUS        :",
        "INSUFFICIENT_FORWARD_EVIDENCE"
    )


print("")
print("=" * 72)
print("AI RESEARCH V2.2       : PASS")
print("FACT SOURCE             : DETERMINISTIC")
print("FACTUAL NARRATIVE       : DETERMINISTIC")
print("AI FACTUAL PROSE        : DISABLED")
print("AI ROLE                 : LIMITATIONS / QUESTIONS")
print("SCHEMA GUARD            : PASS")
print("TEXT GUARD              : PASS")
print("STRATEGY SELECTION      : NO")
print("CAPITAL ALLOCATION      : NO")
print("TRADE EXECUTION         : NO")
print("REAL MONEY              : NO")
print("=" * 72)
