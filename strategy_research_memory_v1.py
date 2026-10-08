import csv
import json
import os
import hashlib

from pathlib import Path
from datetime import datetime, timezone

ROOT = Path.cwd()

EVAL_FILE = ROOT / "strategy_evaluation_v3.json"
AI_FILE   = ROOT / "ai_strategy_research_v1.json"

MEMORY_JSONL = ROOT / "strategy_research_memory_v1.jsonl"
INDEX_JSON   = ROOT / "strategy_research_memory_index_v1.json"

STRATEGIES = (
    "SMA20_50",
    "EMA12_26",
    "RSI14",
)


def sha256_file(path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b""
        ):
            h.update(chunk)

    return h.hexdigest()


def canonical_json(obj):
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def sha256_object(obj):
    return hashlib.sha256(
        canonical_json(obj).encode("utf-8")
    ).hexdigest()


def load_json(path):
    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def fsync_directory(path):
    if os.name == "nt":
        return

    fd = os.open(
        str(path),
        os.O_DIRECTORY
    )

    try:
        os.fsync(fd)
    finally:
        os.close(fd)


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
    fsync_directory(path.parent)


def read_memory():
    if not MEMORY_JSONL.exists():
        return []

    rows = []

    with MEMORY_JSONL.open(
        "r",
        encoding="utf-8"
    ) as f:

        for line_no, line in enumerate(
            f,
            start=1
        ):
            line = line.strip()

            if not line:
                continue

            try:
                rows.append(
                    json.loads(line)
                )

            except Exception as exc:
                raise RuntimeError(
                    f"Memory JSONL corrupt at line "
                    f"{line_no}: {exc}"
                )

    return rows


def atomic_write_memory(entries):
    tmp = MEMORY_JSONL.with_suffix(
        ".jsonl.tmp"
    )

    with tmp.open(
        "w",
        encoding="utf-8"
    ) as f:

        for entry in entries:
            f.write(
                canonical_json(entry)
                + "\n"
            )

        f.flush()
        os.fsync(f.fileno())

    os.replace(
        tmp,
        MEMORY_JSONL
    )

    fsync_directory(
        MEMORY_JSONL.parent
    )


if not EVAL_FILE.exists():
    raise RuntimeError(
        "strategy_evaluation_v3.json missing"
    )

if not AI_FILE.exists():
    raise RuntimeError(
        "ai_strategy_research_v1.json missing"
    )


evaluation = load_json(
    EVAL_FILE
)

ai = load_json(
    AI_FILE
)


# ------------------------------------------------------------
# Validate authority boundary
# ------------------------------------------------------------

authority = ai.get(
    "authority",
    {}
)

required_false = (
    "strategy_selection",
    "capital_allocation",
    "trade_execution",
    "real_money",
)

for key in required_false:

    if authority.get(key) is not False:
        raise RuntimeError(
            f"AI authority violation: {key}"
        )


if (
    ai.get("overall_evidence_status")
    != "INSUFFICIENT_FORWARD_EVIDENCE"
):
    raise RuntimeError(
        "Unexpected overall evidence status"
    )


# ------------------------------------------------------------
# Deterministic facts from Evaluation V3
# These facts are authoritative for the memory entry.
# AI prose is commentary only.
# ------------------------------------------------------------

eval_map = {
    x["strategy"]: x
    for x in evaluation["strategies"]
}

ai_map = {
    x["strategy"]: x
    for x in ai["strategies"]
}


if set(eval_map) != set(STRATEGIES):
    raise RuntimeError(
        "Evaluation strategy mismatch"
    )

if set(ai_map) != set(STRATEGIES):
    raise RuntimeError(
        "AI strategy mismatch"
    )


strategy_records = []


for strategy in STRATEGIES:

    e = eval_map[strategy]
    a = ai_map[strategy]

    deterministic = {
        "historical_return_pct":
            e["historical_return_pct"],

        "historical_max_drawdown_pct":
            e["historical_max_drawdown_pct"],

        "prospective_signal_rows":
            e["prospective_signal_rows"],

        "prospective_buy_signals":
            e["prospective_buy_signals"],

        "prospective_sell_signals":
            e["prospective_sell_signals"],

        "prospective_none_signals":
            e["prospective_none_signals"],

        "prospective_trade_rows":
            e["prospective_trade_rows"],

        "prospective_buy_trades":
            e["prospective_buy_trades"],

        "prospective_sell_trades":
            e["prospective_sell_trades"],

        "prospective_open_positions":
            e["prospective_open_positions"],

        "prospective_equity_try":
            e["prospective_equity_try"],

        "prospective_realized_pnl_try":
            e["prospective_realized_pnl_try"],

        "prospective_unrealized_pnl_try":
            e["prospective_unrealized_pnl_try"],

        "prospective_total_pnl_try":
            e["prospective_total_pnl_try"],

        "prospective_return_pct":
            e["prospective_return_pct"],

        "prospective_drawdown_pct":
            e["prospective_drawdown_pct"],

        "evidence_status":
            "INSUFFICIENT_FORWARD_EVIDENCE",
    }


    # --------------------------------------------------------
    # Detect contradiction:
    # AI saying no signal while deterministic ledger
    # says signals exist.
    # --------------------------------------------------------

    prose = (
        str(
            a.get(
                "prospective_observation",
                ""
            )
        )
        .lower()
    )

    contradictions = []

    signal_count = (
        int(
            e["prospective_buy_signals"]
        )
        +
        int(
            e["prospective_sell_signals"]
        )
    )


    no_signal_phrases = (
        "did not generate any buy or sell signals",
        "did not generate any signals",
        "no buy or sell signals",
        "no signals",
    )


    if signal_count > 0:

        for phrase in no_signal_phrases:

            if phrase in prose:

                contradictions.append({
                    "type":
                        "AI_PROSE_VS_LEDGER",

                    "field":
                        "prospective_signals",

                    "ai_claim":
                        phrase,

                    "ledger_buy_signals":
                        int(
                            e[
                                "prospective_buy_signals"
                            ]
                        ),

                    "ledger_sell_signals":
                        int(
                            e[
                                "prospective_sell_signals"
                            ]
                        ),
                })

                break


    strategy_records.append({
        "strategy":
            strategy,

        "deterministic_facts":
            deterministic,

        "ai_commentary": {
            "historical_observation":
                a.get(
                    "historical_observation",
                    ""
                ),

            "prospective_observation":
                a.get(
                    "prospective_observation",
                    ""
                ),

            "limitations":
                a.get(
                    "limitations",
                    []
                ),

            "questions_for_future_data":
                a.get(
                    "questions_for_future_data",
                    []
                ),
        },

        "detected_contradictions":
            contradictions,

        "commentary_trust":
            (
                "FLAGGED"
                if contradictions
                else
                "UNFLAGGED"
            ),
    })


# ------------------------------------------------------------
# Create immutable observation identity.
#
# Same evaluation + same AI output must NOT create another
# memory observation if script is rerun.
# ------------------------------------------------------------

source_hashes = {
    "evaluation_sha256":
        sha256_file(EVAL_FILE),

    "ai_research_sha256":
        sha256_file(AI_FILE),
}


observation_identity = {
    "evaluation_sha256":
        source_hashes[
            "evaluation_sha256"
        ],

    "ai_research_sha256":
        source_hashes[
            "ai_research_sha256"
        ],

    "evaluation_version":
        evaluation.get(
            "version"
        ),

    "ai_version":
        ai.get(
            "agent_version",
            "ai_strategy_research_v1"
        ),
}


observation_id = (
    "obs_"
    + sha256_object(
        observation_identity
    )[:24]
)


existing = read_memory()

existing_ids = {
    x.get("observation_id")
    for x in existing
}


if observation_id in existing_ids:

    print("")
    print(
        "OBSERVATION ALREADY STORED :",
        observation_id
    )

    print(
        "IDEMPOTENCY                : PASS"
    )

    added = False

else:

    previous_hash = (
        existing[-1].get(
            "entry_hash"
        )
        if existing
        else None
    )


    entry = {
        "memory_version":
            "strategy_research_memory_v1",

        "observation_id":
            observation_id,

        "recorded_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "source_hashes":
            source_hashes,

        "previous_entry_hash":
            previous_hash,

        "overall_evidence_status":
            "INSUFFICIENT_FORWARD_EVIDENCE",

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

        "strategies":
            strategy_records,

        "cross_strategy_observations":
            ai.get(
                "cross_strategy_observations",
                []
            ),

        "prohibited_conclusions":
            ai.get(
                "prohibited_conclusions",
                []
            ),

        "next_evidence_needed":
            ai.get(
                "next_evidence_needed",
                []
            ),
    }


    hash_material = dict(entry)

    entry_hash = sha256_object(
        hash_material
    )

    entry["entry_hash"] = (
        entry_hash
    )


    new_memory = (
        existing
        + [entry]
    )


    atomic_write_memory(
        new_memory
    )

    added = True


# ------------------------------------------------------------
# Re-read and validate full hash chain
# ------------------------------------------------------------

memory = read_memory()

previous = None


for index, entry in enumerate(
    memory,
    start=1
):

    stored_hash = entry.get(
        "entry_hash"
    )

    if not stored_hash:
        raise RuntimeError(
            f"Entry {index}: missing hash"
        )


    material = dict(entry)

    del material[
        "entry_hash"
    ]


    calculated = sha256_object(
        material
    )


    if calculated != stored_hash:

        raise RuntimeError(
            f"Entry {index}: hash mismatch"
        )


    if (
        entry.get(
            "previous_entry_hash"
        )
        != previous
    ):

        raise RuntimeError(
            f"Entry {index}: chain mismatch"
        )


    previous = stored_hash


# ------------------------------------------------------------
# Build read-only index
# ------------------------------------------------------------

flagged = 0

for entry in memory:

    for s in entry.get(
        "strategies",
        []
    ):

        if (
            s.get(
                "commentary_trust"
            )
            == "FLAGGED"
        ):
            flagged += 1


index = {
    "version":
        "strategy_research_memory_index_v1",

    "generated_at_utc":
        datetime.now(
            timezone.utc
        ).isoformat(),

    "observation_count":
        len(memory),

    "latest_observation_id":
        (
            memory[-1][
                "observation_id"
            ]
            if memory
            else None
        ),

    "latest_entry_hash":
        (
            memory[-1][
                "entry_hash"
            ]
            if memory
            else None
        ),

    "flagged_ai_commentaries":
        flagged,

    "hash_chain_valid":
        True,

    "trading_authority":
        False,

    "real_money":
        False,
}


atomic_json(
    INDEX_JSON,
    index
)


print("")
print("=" * 72)
print("STRATEGY RESEARCH MEMORY V1")
print("=" * 72)

print(
    "OBSERVATION ID :",
    observation_id
)

print(
    "NEW ENTRY      :",
    "YES" if added else "NO"
)

print(
    "TOTAL ENTRIES  :",
    len(memory)
)

print(
    "HASH CHAIN     : PASS"
)

print(
    "FLAGGED AI TEXT:",
    flagged
)


for entry in memory[-1:]:

    print("")
    print("LATEST OBSERVATION")

    for s in entry[
        "strategies"
    ]:

        facts = s[
            "deterministic_facts"
        ]

        print("")
        print(
            s["strategy"]
        )

        print(
            "  SIGNALS B/S/N :",
            facts[
                "prospective_buy_signals"
            ],
            "/",
            facts[
                "prospective_sell_signals"
            ],
            "/",
            facts[
                "prospective_none_signals"
            ],
        )

        print(
            "  TRADES        :",
            facts[
                "prospective_trade_rows"
            ]
        )

        print(
            "  EQUITY        :",
            facts[
                "prospective_equity_try"
            ],
            "TRY"
        )

        print(
            "  EVIDENCE      :",
            facts[
                "evidence_status"
            ]
        )

        print(
            "  AI COMMENTARY :",
            s[
                "commentary_trust"
            ]
        )

        if s[
            "detected_contradictions"
        ]:

            print(
                "  CONTRADICTION :",
                s[
                    "detected_contradictions"
                ]
            )


print("")
print("=" * 72)
print("MEMORY WRITE             : PASS")
print("HASH CHAIN               : PASS")
print("DUPLICATE PROTECTION     : PASS")
print("DETERMINISTIC FACTS      : AUTHORITATIVE")
print("AI COMMENTARY            : NON-AUTHORITATIVE")
print("STRATEGY SELECTION       : NO")
print("CAPITAL ALLOCATION       : NO")
print("TRADE EXECUTION          : NO")
print("REAL MONEY               : NO")
print("=" * 72)
