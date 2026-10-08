import json
import os
import sys
import hashlib
import subprocess

from pathlib import Path
from datetime import datetime, timezone

ROOT = Path.cwd()
PYTHON = Path(sys.executable)

STATE_V1 = ROOT / "multistrategy_live_state_v1.json"
STATE_V3 = ROOT / "multistrategy_live_state_v3.json"

STATUS = ROOT / "research_pipeline_status_v2.json"
RUNS = ROOT / "research_pipeline_runs_v2.jsonl"

STAGES = (
    (
        "EVALUATION_V2",
        ROOT / "strategy_evaluation_v2.py",
    ),
    (
        "EVALUATION_V3",
        ROOT / "strategy_evaluation_v3.py",
    ),
    (
        "AI_RESEARCH_V2_2",
        ROOT / "ai_strategy_research_v2_2.py",
    ),
    (
        "RESEARCH_MEMORY_V2",
        ROOT / "strategy_research_memory_v2.py",
    ),
)

EXPECTED_OUTPUTS = (
    ROOT / "strategy_evaluation_v2.json",
    ROOT / "strategy_evaluation_v3.json",
    ROOT / "ai_strategy_research_v2_2.json",
    ROOT / "strategy_research_memory_index_v2.json",
)


def hash_file(path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b""
        ):
            h.update(chunk)

    return h.hexdigest()


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


def append_run(record):

    old = []

    if RUNS.exists():

        with RUNS.open(
            "r",
            encoding="utf-8"
        ) as f:

            old = [
                line.rstrip("\n")
                for line in f
                if line.strip()
            ]


    tmp = RUNS.with_suffix(
        ".jsonl.tmp"
    )

    with tmp.open(
        "w",
        encoding="utf-8"
    ) as f:

        for line in old:
            f.write(line + "\n")

        f.write(
            json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )

        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp, RUNS)


def run_stage(name, script):

    if not script.exists():
        raise RuntimeError(
            f"{name}: script missing"
        )

    print("")
    print("=" * 72)
    print("STAGE :", name)
    print("=" * 72)

    started = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    result = subprocess.run(
        [
            str(PYTHON),
            str(script),
        ],
        cwd=str(ROOT),
    )

    finished = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{name}: FAIL "
            f"exit={result.returncode}"
        )

    print(
        name,
        ": PASS"
    )

    return {
        "stage":
            name,

        "script":
            script.name,

        "script_sha256":
            hash_file(script),

        "started_at_utc":
            started,

        "finished_at_utc":
            finished,

        "status":
            "PASS",

        "exit_code":
            0,
    }


for state in (
    STATE_V1,
    STATE_V3,
):

    if not state.exists():
        raise RuntimeError(
            f"Missing state: {state.name}"
        )


v1_before = hash_file(
    STATE_V1
)

v3_before = hash_file(
    STATE_V3
)

started = (
    datetime.now(
        timezone.utc
    ).isoformat()
)

completed = []


try:

    for name, script in STAGES:

        completed.append(
            run_stage(
                name,
                script
            )
        )


    for output in EXPECTED_OUTPUTS:

        if not output.exists():
            raise RuntimeError(
                f"Missing output: "
                f"{output.name}"
            )


    ai = json.loads(
        (
            ROOT
            / "ai_strategy_research_v2_2.json"
        ).read_text(
            encoding="utf-8-sig"
        )
    )


    memory = json.loads(
        (
            ROOT
            / "strategy_research_memory_index_v2.json"
        ).read_text(
            encoding="utf-8-sig"
        )
    )


    if (
        ai.get("agent_version")
        != "ai_strategy_research_v2_2"
    ):
        raise RuntimeError(
            "Wrong AI output version"
        )


    if (
        ai.get(
            "overall_evidence_status"
        )
        !=
        "INSUFFICIENT_FORWARD_EVIDENCE"
    ):
        raise RuntimeError(
            "Unexpected evidence status"
        )


    if (
        ai.get(
            "verification",
            {}
        ).get(
            "schema_guard"
        )
        != "PASS"
    ):
        raise RuntimeError(
            "AI schema guard failed"
        )


    if (
        ai.get(
            "verification",
            {}
        ).get(
            "text_guard"
        )
        != "PASS"
    ):
        raise RuntimeError(
            "AI text guard failed"
        )


    if (
        memory.get(
            "hash_chain_valid"
        )
        is not True
    ):
        raise RuntimeError(
            "Memory hash chain failed"
        )


    if (
        memory.get(
            "trading_authority"
        )
        is not False
    ):
        raise RuntimeError(
            "Memory authority violation"
        )


    v1_after = hash_file(
        STATE_V1
    )

    v3_after = hash_file(
        STATE_V3
    )


    if v1_before != v1_after:
        raise RuntimeError(
            "PIPELINE MODIFIED V1 STATE"
        )


    if v3_before != v3_after:
        raise RuntimeError(
            "PIPELINE MODIFIED V3 STATE"
        )


    finished = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )


    record = {
        "pipeline_version":
            "research_pipeline_v2",

        "started_at_utc":
            started,

        "finished_at_utc":
            finished,

        "status":
            "PASS",

        "stages":
            completed,

        "evidence_status":
            ai[
                "overall_evidence_status"
            ],

        "memory_observation_count":
            memory[
                "observation_count"
            ],

        "architecture": {
            "facts":
                "deterministic",

            "factual_narrative":
                "deterministic",

            "ai_role":
                "limitations_and_future_questions_only",
        },

        "state_integrity": {
            "v1_unchanged":
                True,

            "v3_unchanged":
                True,

            "v1_sha256":
                v1_after,

            "v3_sha256":
                v3_after,
        },

        "trading_authority":
            False,

        "real_money":
            False,
    }


    append_run(record)
    atomic_json(
        STATUS,
        record
    )


    print("")
    print("=" * 72)
    print("RESEARCH PIPELINE V2 : PASS")
    print("=" * 72)

    print(
        "EVIDENCE STATUS :",
        record[
            "evidence_status"
        ]
    )

    print(
        "MEMORY ENTRIES  :",
        record[
            "memory_observation_count"
        ]
    )

    print(
        "FACTS           : DETERMINISTIC"
    )

    print(
        "FACTUAL TEXT    : DETERMINISTIC"
    )

    print(
        "AI ROLE         : LIMITED"
    )

    print(
        "V1 STATE        : UNCHANGED"
    )

    print(
        "V3 STATE        : UNCHANGED"
    )

    print(
        "REAL MONEY      : NO"
    )

    print("=" * 72)


except Exception as exc:

    failure = {
        "pipeline_version":
            "research_pipeline_v2",

        "started_at_utc":
            started,

        "finished_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "status":
            "FAIL",

        "error":
            str(exc),

        "completed_stages":
            completed,

        "trading_authority":
            False,

        "real_money":
            False,
    }

    append_run(failure)

    atomic_json(
        STATUS,
        failure
    )

    raise
