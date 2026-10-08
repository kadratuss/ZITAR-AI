import json
import os
import hashlib
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path.cwd()

AI_FILE = ROOT / "ai_strategy_research_v2_2.json"

MEMORY_FILE = ROOT / "strategy_research_memory_v2.jsonl"
INDEX_FILE = ROOT / "strategy_research_memory_index_v2.json"

STRATEGIES = (
    "SMA20_50",
    "EMA12_26",
    "RSI14",
)


def canonical(obj):
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def hash_object(obj):
    return hashlib.sha256(
        canonical(obj).encode("utf-8")
    ).hexdigest()


def hash_file(path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b""
        ):
            h.update(chunk)

    return h.hexdigest()


def load_json(path):
    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def read_memory():

    if not MEMORY_FILE.exists():
        return []

    entries = []

    with MEMORY_FILE.open(
        "r",
        encoding="utf-8"
    ) as f:

        for line_no, line in enumerate(
            f,
            start=1
        ):

            if not line.strip():
                continue

            try:
                entries.append(
                    json.loads(line)
                )

            except Exception as exc:
                raise RuntimeError(
                    f"Memory corrupt line "
                    f"{line_no}: {exc}"
                )

    return entries


def atomic_memory(entries):

    tmp = MEMORY_FILE.with_suffix(
        ".jsonl.tmp"
    )

    with tmp.open(
        "w",
        encoding="utf-8"
    ) as f:

        for entry in entries:
            f.write(
                canonical(entry)
                + "\n"
            )

        f.flush()
        os.fsync(f.fileno())

    os.replace(
        tmp,
        MEMORY_FILE
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


if not AI_FILE.exists():
    raise RuntimeError(
        "ai_strategy_research_v2_2.json missing"
    )


ai = load_json(AI_FILE)


# ------------------------------------------------------------
# Validate V2.2 architecture
# ------------------------------------------------------------

if (
    ai.get("agent_version")
    != "ai_strategy_research_v2_2"
):
    raise RuntimeError(
        "Wrong AI version"
    )


if (
    ai.get("overall_evidence_status")
    != "INSUFFICIENT_FORWARD_EVIDENCE"
):
    raise RuntimeError(
        "Unexpected evidence status"
    )


architecture = ai.get(
    "architecture",
    {}
)

if (
    architecture.get(
        "facts_generated_by"
    )
    != "deterministic_python"
):
    raise RuntimeError(
        "Facts are not deterministic"
    )


if (
    architecture.get(
        "factual_narrative_generated_by"
    )
    != "deterministic_python"
):
    raise RuntimeError(
        "Narrative is not deterministic"
    )


if (
    architecture.get("ai_role")
    !=
    "limitations_and_future_questions_only"
):
    raise RuntimeError(
        "Unexpected AI role"
    )


verification = ai.get(
    "verification",
    {}
)

if (
    verification.get("schema_guard")
    != "PASS"
):
    raise RuntimeError(
        "AI schema guard not PASS"
    )


if (
    verification.get("text_guard")
    != "PASS"
):
    raise RuntimeError(
        "AI text guard not PASS"
    )


authority = ai.get(
    "authority",
    {}
)

for key in (
    "strategy_selection",
    "capital_allocation",
    "trade_execution",
    "real_money",
):
    if authority.get(key) is not False:
        raise RuntimeError(
            f"Authority violation: {key}"
        )


rows = ai.get("strategies")

if not isinstance(rows, list):
    raise RuntimeError(
        "Strategies missing"
    )


strategy_map = {
    row.get("strategy"): row
    for row in rows
    if isinstance(row, dict)
}


if set(strategy_map) != set(STRATEGIES):
    raise RuntimeError(
        "Strategy set mismatch"
    )


# ------------------------------------------------------------
# Observation identity
#
# IMPORTANT:
# generated_at_utc is deliberately excluded.
#
# Identity comes from authoritative facts + deterministic
# summaries + AI research commentary.
# ------------------------------------------------------------

identity_payload = {
    "source_evaluation_version":
        ai.get(
            "source_evaluation_version"
        ),

    "overall_evidence_status":
        ai.get(
            "overall_evidence_status"
        ),

    "strategies":
        [
            {
                "strategy":
                    strategy,

                "authoritative_facts":
                    strategy_map[strategy][
                        "authoritative_facts"
                    ],

                "deterministic_summary":
                    strategy_map[strategy][
                        "deterministic_summary"
                    ],

                "ai_research_commentary":
                    strategy_map[strategy][
                        "ai_research_commentary"
                    ],
            }
            for strategy in STRATEGIES
        ],

    "cross_strategy_research_questions":
        ai.get(
            "cross_strategy_research_questions",
            []
        ),
}


observation_id = (
    "v2_"
    + hash_object(
        identity_payload
    )[:24]
)


existing = read_memory()


# ------------------------------------------------------------
# Validate existing chain BEFORE modification
# ------------------------------------------------------------

previous = None

for index, entry in enumerate(
    existing,
    start=1
):

    stored_hash = entry.get(
        "entry_hash"
    )

    if not stored_hash:
        raise RuntimeError(
            f"Existing entry {index}: "
            f"missing entry_hash"
        )

    material = dict(entry)
    del material["entry_hash"]

    calculated = hash_object(
        material
    )

    if calculated != stored_hash:
        raise RuntimeError(
            f"Existing entry {index}: "
            f"hash mismatch"
        )

    if (
        entry.get(
            "previous_entry_hash"
        )
        != previous
    ):
        raise RuntimeError(
            f"Existing entry {index}: "
            f"chain mismatch"
        )

    previous = stored_hash


existing_ids = {
    entry.get("observation_id")
    for entry in existing
}


if observation_id in existing_ids:

    added = False

else:

    entry = {
        "memory_version":
            "strategy_research_memory_v2",

        "observation_id":
            observation_id,

        "recorded_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "source_ai_file":
            AI_FILE.name,

        "source_ai_sha256":
            hash_file(AI_FILE),

        "previous_entry_hash":
            previous,

        "overall_evidence_status":
            "INSUFFICIENT_FORWARD_EVIDENCE",

        "architecture": {
            "facts":
                "deterministic",

            "factual_narrative":
                "deterministic",

            "ai_role":
                "limitations_and_future_questions_only",
        },

        "strategies":
            [
                {
                    "strategy":
                        strategy,

                    "authoritative_facts":
                        strategy_map[
                            strategy
                        ][
                            "authoritative_facts"
                        ],

                    "deterministic_summary":
                        strategy_map[
                            strategy
                        ][
                            "deterministic_summary"
                        ],

                    "ai_research_commentary":
                        strategy_map[
                            strategy
                        ][
                            "ai_research_commentary"
                        ],

                    "evidence_status":
                        "INSUFFICIENT_FORWARD_EVIDENCE",
                }
                for strategy in STRATEGIES
            ],

        "cross_strategy_research_questions":
            ai.get(
                "cross_strategy_research_questions",
                []
            ),

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


    entry["entry_hash"] = (
        hash_object(entry)
    )


    atomic_memory(
        existing + [entry]
    )

    added = True


# ------------------------------------------------------------
# Re-read + validate final chain
# ------------------------------------------------------------

memory = read_memory()

previous = None

for index, entry in enumerate(
    memory,
    start=1
):

    stored_hash = entry[
        "entry_hash"
    ]

    material = dict(entry)
    del material["entry_hash"]

    calculated = hash_object(
        material
    )

    if calculated != stored_hash:
        raise RuntimeError(
            f"Final entry {index}: "
            f"hash mismatch"
        )

    if (
        entry.get(
            "previous_entry_hash"
        )
        != previous
    ):
        raise RuntimeError(
            f"Final entry {index}: "
            f"chain mismatch"
        )

    previous = stored_hash


index = {
    "version":
        "strategy_research_memory_index_v2",

    "generated_at_utc":
        datetime.now(
            timezone.utc
        ).isoformat(),

    "observation_count":
        len(memory),

    "latest_observation_id":
        (
            memory[-1]["observation_id"]
            if memory
            else None
        ),

    "latest_entry_hash":
        (
            memory[-1]["entry_hash"]
            if memory
            else None
        ),

    "hash_chain_valid":
        True,

    "facts":
        "deterministic",

    "factual_narrative":
        "deterministic",

    "ai_role":
        "limitations_and_future_questions_only",

    "trading_authority":
        False,

    "real_money":
        False,
}


atomic_json(
    INDEX_FILE,
    index
)


print("")
print("=" * 72)
print("STRATEGY RESEARCH MEMORY V2")
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
    "FACTS          : DETERMINISTIC"
)

print(
    "AI ROLE        : LIMITED"
)

print("")
print("=" * 72)
print("MEMORY V2              : PASS")
print("DUPLICATE PROTECTION   : PASS")
print("TRADING AUTHORITY      : NO")
print("REAL MONEY             : NO")
print("=" * 72)
