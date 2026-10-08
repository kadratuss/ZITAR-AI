import json
import os
import sys
import hashlib
import subprocess

from pathlib import Path
from datetime import datetime, timezone

ROOT = Path.cwd()

PYTHON = Path(sys.executable)

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
        "AI_RESEARCH_V1",
        ROOT / "ai_strategy_research_v1.py",
    ),
    (
        "RESEARCH_MEMORY_V1",
        ROOT / "strategy_research_memory_v1.py",
    ),
)

STATE_V3 = ROOT / "multistrategy_live_state_v3.json"
STATE_V1 = ROOT / "multistrategy_live_state_v1.json"

EVAL2 = ROOT / "strategy_evaluation_v2.json"
EVAL3 = ROOT / "strategy_evaluation_v3.json"
AI_OUT = ROOT / "ai_strategy_research_v1.json"
MEM_INDEX = ROOT / "strategy_research_memory_index_v1.json"

RUNS_JSONL = ROOT / "research_pipeline_runs_v1.jsonl"
STATUS_JSON = ROOT / "research_pipeline_status_v1.json"


def sha256_file(path):
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


def append_run_atomic(record):

    existing = []

    if RUNS_JSONL.exists():

        with RUNS_JSONL.open(
            "r",
            encoding="utf-8"
        ) as f:

            existing = [
                line.rstrip("\n")
                for line in f
                if line.strip()
            ]


    tmp = RUNS_JSONL.with_suffix(
        ".jsonl.tmp"
    )

    with tmp.open(
        "w",
        encoding="utf-8"
    ) as f:

        for line in existing:
            f.write(line + "\n")

        f.write(
            json.dumps(
                record,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )

        f.flush()
        os.fsync(f.fileno())

    os.replace(
        tmp,
        RUNS_JSONL
    )


def run_stage(name, script):

    if not script.exists():
        raise RuntimeError(
            f"{name}: missing script {script.name}"
        )

    print("")
    print("=" * 72)
    print("STAGE :", name)
    print("SCRIPT:", script.name)
    print("=" * 72)

    started = (
        datetime.now(timezone.utc)
        .isoformat()
    )

    result = subprocess.run(
        [
            str(PYTHON),
            str(script),
        ],
        cwd=str(ROOT),
        text=True,
    )

    finished = (
        datetime.now(timezone.utc)
        .isoformat()
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{name} failed with exit code "
            f"{result.returncode}"
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
            sha256_file(script),

        "started_at_utc":
            started,

        "finished_at_utc":
            finished,

        "exit_code":
            result.returncode,

        "status":
            "PASS",
    }


# ------------------------------------------------------------
# Preflight
# ------------------------------------------------------------

for path in (
    STATE_V3,
    STATE_V1,
):

    if not path.exists():
        raise RuntimeError(
            f"Missing state: {path.name}"
        )


v3_before = sha256_file(
    STATE_V3
)

v1_before = sha256_file(
    STATE_V1
)


pipeline_started = (
    datetime.now(timezone.utc)
    .isoformat()
)

stage_results = []


try:

    for name, script in STAGES:

        stage_results.append(
            run_stage(
                name,
                script,
            )
        )


    # --------------------------------------------------------
    # Validate expected outputs
    # --------------------------------------------------------

    for output in (
        EVAL2,
        EVAL3,
        AI_OUT,
        MEM_INDEX,
    ):

        if not output.exists():
            raise RuntimeError(
                f"Missing output: {output.name}"
            )


    eval3 = load_json(
        EVAL3
    )

    ai = load_json(
        AI_OUT
    )

    memory_index = load_json(
        MEM_INDEX
    )


    if (
        eval3.get("real_money")
        is not False
    ):
        raise RuntimeError(
            "Evaluation real_money boundary failed"
        )


    if (
        ai.get(
            "overall_evidence_status"
        )
        !=
        "INSUFFICIENT_FORWARD_EVIDENCE"
    ):
        raise RuntimeError(
            "Unexpected AI evidence status"
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
                f"AI authority violation: {key}"
            )


    if (
        memory_index.get(
            "hash_chain_valid"
        )
        is not True
    ):
        raise RuntimeError(
            "Memory hash chain invalid"
        )


    if (
        memory_index.get(
            "trading_authority"
        )
        is not False
    ):
        raise RuntimeError(
            "Memory trading authority violation"
        )


    # --------------------------------------------------------
    # Verify trading state did not change
    # --------------------------------------------------------

    v3_after = sha256_file(
        STATE_V3
    )

    v1_after = sha256_file(
        STATE_V1
    )


    if v3_before != v3_after:
        raise RuntimeError(
            "PIPELINE MODIFIED V3 TRADING STATE"
        )


    if v1_before != v1_after:
        raise RuntimeError(
            "PIPELINE MODIFIED V1 TRADING STATE"
        )


    finished = (
        datetime.now(timezone.utc)
        .isoformat()
    )


    record = {
        "pipeline_version":
            "research_pipeline_v1",

        "started_at_utc":
            pipeline_started,

        "finished_at_utc":
            finished,

        "status":
            "PASS",

        "stages":
            stage_results,

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

        "outputs": {
            "evaluation_v2_sha256":
                sha256_file(EVAL2),

            "evaluation_v3_sha256":
                sha256_file(EVAL3),

            "ai_research_sha256":
                sha256_file(AI_OUT),

            "memory_index_sha256":
                sha256_file(MEM_INDEX),
        },

        "evidence_status":
            ai[
                "overall_evidence_status"
            ],

        "memory_observation_count":
            memory_index[
                "observation_count"
            ],

        "flagged_ai_commentaries":
            memory_index[
                "flagged_ai_commentaries"
            ],

        "trading_authority":
            False,

        "real_money":
            False,
    }


    append_run_atomic(
        record
    )

    atomic_json(
        STATUS_JSON,
        record
    )


    print("")
    print("=" * 72)
    print("RESEARCH PIPELINE V1 : PASS")
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
        "AI FLAGS        :",
        record[
            "flagged_ai_commentaries"
        ]
    )

    print(
        "V1 STATE        : UNCHANGED"
    )

    print(
        "V3 STATE        : UNCHANGED"
    )

    print(
        "TRADING AUTHORITY: NONE"
    )

    print(
        "REAL MONEY       : NO"
    )

    print("=" * 72)


except Exception as exc:

    finished = (
        datetime.now(timezone.utc)
        .isoformat()
    )


    failure = {
        "pipeline_version":
            "research_pipeline_v1",

        "started_at_utc":
            pipeline_started,

        "finished_at_utc":
            finished,

        "status":
            "FAIL",

        "error":
            str(exc),

        "completed_stages":
            stage_results,

        "trading_authority":
            False,

        "real_money":
            False,
    }


    append_run_atomic(
        failure
    )

    atomic_json(
        STATUS_JSON,
        failure
    )


    print("")
    print("=" * 72)
    print("RESEARCH PIPELINE V1 : FAIL")
    print("ERROR:", exc)
    print("REAL MONEY : NO")
    print("=" * 72)

    raise
