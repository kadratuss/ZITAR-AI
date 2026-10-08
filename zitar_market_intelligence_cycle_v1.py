from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
PYTHON = sys.executable

OUT = BASE / "zitar_market_intelligence_cycle_v1.json"

STAGES = [
    ("LIQUIDITY_OBSERVER", "zitar_liquidity_observer_v1.py"),
    ("SELECTION_ENGINE", "zitar_selection_engine_v1.py"),
    ("FUTURES_UNIVERSE", "zitar_futures_universe_v1.py"),
    ("FUTURES_SNAPSHOT", "zitar_futures_intelligence_snapshot_v1_1.py"),
    ("FUTURES_TEMPORAL", "zitar_futures_temporal_intelligence_v1.py"),
    ("FUTURES_EVIDENCE", "zitar_futures_evidence_v1.py"),
]


def read_json(name):
    path = BASE / name

    if not path.exists():
        return {}

    try:
        return json.loads(
            path.read_text(encoding="utf-8-sig")
        )
    except Exception:
        return {}


def run_stage(name, filename):
    path = BASE / filename
    started = time.perf_counter()

    if not path.exists():
        return {
            "name": name,
            "file": filename,
            "status": "MISSING",
            "returncode": None,
            "seconds": 0,
            "tail": ""
        }

    p = subprocess.run(
        [PYTHON, "-u", str(path)],
        cwd=str(BASE),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    seconds = round(
        time.perf_counter() - started,
        2
    )

    combined = "\n".join(
        x for x in [p.stdout, p.stderr] if x
    ).strip()

    lines = combined.splitlines()

    status = "PASS" if (
        p.returncode == 0
        and any(
            line.strip() == "STATUS: PASS"
            for line in lines
        )
    ) else "FAIL"

    return {
        "name": name,
        "file": filename,
        "status": status,
        "returncode": p.returncode,
        "seconds": seconds,
        "tail": "\n".join(lines[-12:])
    }


def main():

    print("ZITAR MARKET INTELLIGENCE CYCLE V1")
    print(
        "RESEARCH / MEASUREMENT ONLY "
        "• NO SIGNAL • NO PAPER ORDER • NO REAL ORDER"
    )
    print()

    results = []

    for name, filename in STAGES:

        result = run_stage(name, filename)
        results.append(result)

        print(
            f"{result['status']:<8} | "
            f"{name:<20} | "
            f"{result['seconds']}s"
        )

        if result["status"] != "PASS":
            print()
            print(result["tail"])
            print()
            print(
                "STOP: downstream stages "
                "will not be trusted."
            )
            break

    selection = read_json(
        "zitar_selection_engine_v1.json"
    )

    universe = read_json(
        "zitar_futures_universe_v1.json"
    )

    snapshot = read_json(
        "zitar_futures_intelligence_snapshot_v1_1.json"
    )

    evidence = read_json(
        "zitar_futures_evidence_v1.json"
    )

    active_evidence = [
        x for x in evidence.get("symbols", [])
        if x.get("active") is True
    ]

    observable_active = [
        x for x in active_evidence
        if (
            x.get("temporal", {}).get("status")
            == "OBSERVABLE"
        )
    ]

    all_pass = (
        len(results) == len(STAGES)
        and all(
            x["status"] == "PASS"
            for x in results
        )
    )

    report = {
        "schema":
            "ZITAR_MARKET_INTELLIGENCE_CYCLE_V1",

        "generated_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "mode":
            "RESEARCH_MEASUREMENT_ONLY",

        "authorities": {
            "directional_signal": False,
            "paper_order": False,
            "real_order": False,
            "memory_promotion": False
        },

        "status":
            "PASS" if all_pass else "FAIL",

        "stages": results,

        "summary": {
            "selection_mode":
                selection.get("mode"),

            "selection_candidates":
                len(
                    selection.get(
                        "candidates",
                        []
                    )
                ),

            "selection_rejected":
                len(
                    selection.get(
                        "rejected",
                        []
                    )
                ),

            "futures_matched":
                universe.get(
                    "matched_count",
                    0
                ),

            "futures_unmatched":
                universe.get(
                    "unmatched_count",
                    0
                ),

            "snapshot_symbols":
                len(
                    snapshot.get(
                        "symbols",
                        []
                    )
                ),

            "snapshot_complete":
                sum(
                    x.get("status") == "OK"
                    for x in snapshot.get(
                        "symbols",
                        []
                    )
                ),

            "snapshot_partial":
                sum(
                    x.get("status") == "PARTIAL"
                    for x in snapshot.get(
                        "symbols",
                        []
                    )
                ),

            "active_evidence_symbols":
                len(active_evidence),

            "observable_active_symbols":
                len(observable_active),

            "historical_only_symbols":
                sum(
                    x.get("active") is False
                    for x in evidence.get(
                        "symbols",
                        []
                    )
                )
        }
    }

    OUT.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print()
    print("SUMMARY")

    for k, v in report["summary"].items():
        print(f"{k}: {v}")

    print()
    print("output:", OUT)
    print("STATUS:", report["status"])


if __name__ == "__main__":
    main()
