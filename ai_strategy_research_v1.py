import json
import os
import re
import urllib.request
import urllib.error

from pathlib import Path
from datetime import datetime, timezone

ROOT = Path.cwd()

INPUT = ROOT / "strategy_evaluation_v3.json"

OUTPUT = ROOT / "ai_strategy_research_v1.json"

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5:7b"

STRATEGIES = (
    "SMA20_50",
    "EMA12_26",
    "RSI14",
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
            ensure_ascii=False,
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
            "temperature": 0.1,
        },
        "messages": messages,
    }

    data = json.dumps(
        payload
    ).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=data,
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
            "Ollama returned empty content"
        )

    try:
        return json.loads(content)

    except json.JSONDecodeError:

        # Defensive extraction if model
        # unexpectedly wraps JSON.
        match = re.search(
            r"\{.*\}",
            content,
            re.DOTALL,
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


# ------------------------------------------------------------
# Build a deliberately constrained evidence packet.
# AI sees measurements, but has no authority.
# ------------------------------------------------------------

evidence = {
    "evaluation_version":
        evaluation.get("version"),

    "mode":
        evaluation.get("mode"),

    "real_money":
        evaluation.get("real_money"),

    "source_counts":
        evaluation.get("source_counts"),

    "historical_warning":
        evaluation.get(
            "historical_warning"
        ),

    "prospective_warning":
        evaluation.get(
            "prospective_warning"
        ),

    "strategies":
        evaluation.get(
            "strategies"
        ),
}


system_prompt = """
You are PortfolioAI Research Agent V1.

You are a research and evidence-analysis component.
You have ZERO trading authority.

STRICT RULES:

1. Historical backtest evidence and prospective live-paper
   evidence are different evidence classes.

2. Never treat historical profitability as proof of future
   profitability.

3. Never select a winning strategy.

4. Never rank strategies.

5. Never recommend reallocating capital.

6. Never issue BUY, SELL, HOLD, position-size, leverage,
   or real-money instructions.

7. Do not modify strategy parameters.

8. Do not infer performance that is absent from the supplied
   evidence.

9. If prospective evidence is too small to support a meaningful
   performance conclusion, the strategy's evidence_status MUST be:

   INSUFFICIENT_FORWARD_EVIDENCE

10. Zero trades does NOT mean a strategy is good or bad.

11. A single trade does NOT establish a win rate, edge,
    robustness, or expected return.

12. Explain discrepancies between historical and prospective
    observations only as observations. Do not claim causality
    without evidence.

13. Output JSON only.

Required JSON structure:

{
  "agent_version": "ai_strategy_research_v1",
  "overall_evidence_status": "...",
  "strategies": [
    {
      "strategy": "...",
      "evidence_status": "...",
      "historical_observation": "...",
      "prospective_observation": "...",
      "limitations": ["..."],
      "questions_for_future_data": ["..."]
    }
  ],
  "cross_strategy_observations": ["..."],
  "prohibited_conclusions": ["..."],
  "next_evidence_needed": ["..."]
}
"""


user_prompt = (
    "Analyze ONLY the following PortfolioAI evidence.\n\n"
    + json.dumps(
        evidence,
        ensure_ascii=False,
        indent=2,
    )
)


print("")
print("INPUT      :", INPUT.name)
print("MODEL      :", MODEL)
print("AUTHORITY  : RESEARCH ONLY")
print("REAL MONEY : NO")
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


# ------------------------------------------------------------
# Deterministic safety / evidence validation
# Do not blindly trust model output.
# ------------------------------------------------------------

if not isinstance(
    analysis,
    dict
):
    raise RuntimeError(
        "AI root must be object"
    )


ai_strategies = analysis.get(
    "strategies"
)

if not isinstance(
    ai_strategies,
    list
):
    raise RuntimeError(
        "AI strategies must be list"
    )


names = {
    str(x.get("strategy", ""))
    for x in ai_strategies
    if isinstance(x, dict)
}

if names != set(STRATEGIES):

    raise RuntimeError(
        "AI strategy set mismatch: "
        + str(names)
    )


# Current sample is objectively tiny:
# only 3 V1 runs + current V3 run count,
# and only one trade overall.
#
# Therefore V1 agent is not permitted
# to claim sufficient forward evidence.

for item in ai_strategies:

    item[
        "evidence_status"
    ] = (
        "INSUFFICIENT_FORWARD_EVIDENCE"
    )


analysis[
    "overall_evidence_status"
] = (
    "INSUFFICIENT_FORWARD_EVIDENCE"
)


# Explicit machine-readable authority boundary.

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


analysis[
    "generated_at_utc"
] = (
    datetime.now(
        timezone.utc
    ).isoformat()
)

analysis[
    "source_file"
] = INPUT.name

analysis[
    "source_evaluation_version"
] = evaluation.get(
    "version"
)


# ------------------------------------------------------------
# Simple forbidden action-language guard.
# We are guarding trading directives,
# not ordinary discussion of historical BUY/SELL counts.
# ------------------------------------------------------------

serialized = json.dumps(
    analysis,
    ensure_ascii=False,
).lower()


forbidden_phrases = (
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
    for phrase in forbidden_phrases
    if phrase in serialized
]


if violations:

    raise RuntimeError(
        "AI authority violation: "
        + ", ".join(violations)
    )


atomic_json(
    OUTPUT,
    analysis
)


print("")
print("=" * 72)
print("AI RESEARCH RESULT")
print("=" * 72)

print(
    "OVERALL :",
    analysis[
        "overall_evidence_status"
    ]
)


for item in analysis[
    "strategies"
]:

    print("")
    print(
        item["strategy"]
    )

    print(
        "  STATUS :",
        item[
            "evidence_status"
        ]
    )

    print(
        "  HIST   :",
        item.get(
            "historical_observation",
            ""
        )
    )

    print(
        "  LIVE   :",
        item.get(
            "prospective_observation",
            ""
        )
    )


print("")
print("AUTHORITY")
print(
    json.dumps(
        analysis["authority"],
        ensure_ascii=False,
        indent=2,
    )
)

print("")
print("=" * 72)
print("AI RESEARCH AGENT V1 : PASS")
print("STRATEGY SELECTION   : NO")
print("CAPITAL ALLOCATION   : NO")
print("TRADE EXECUTION      : NO")
print("REAL MONEY           : NO")
print("=" * 72)
