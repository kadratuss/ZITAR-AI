import csv
import json
import os
import shutil
import tempfile
import hashlib
from pathlib import Path


ROOT = Path.cwd()

RUNNER = ROOT / "multistrategy_live_runner_v3.py"

EXPECTED = (
    "9CD3814A39E339383DF1E8B7EF43FA2904C7BC2665AA312FF565642FE53155AC"
)


def sha(path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest().upper()


if sha(RUNNER) != EXPECTED:
    raise RuntimeError(
        "Runner hash mismatch"
    )


# ------------------------------------------------------------
# Generic durable helpers matching hardened semantics.
# ------------------------------------------------------------

def atomic_json(path, obj):

    path = Path(path)

    tmp = path.with_name(
        path.name + ".tmp"
    )

    with tmp.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:

        json.dump(
            obj,
            f,
            indent=2,
            ensure_ascii=False,
        )

        f.flush()
        os.fsync(
            f.fileno()
        )

    os.replace(
        tmp,
        path,
    )


def append_unique(
    path,
    fields,
    rows,
    id_field,
):

    path = Path(path)

    existing = []
    ids = set()

    if (
        path.exists()
        and path.stat().st_size > 0
    ):

        with path.open(
            "r",
            newline="",
            encoding="utf-8",
        ) as f:

            reader = csv.DictReader(f)

            if reader.fieldnames != fields:
                raise RuntimeError(
                    "schema mismatch"
                )

            for row in reader:

                existing.append(row)

                if row.get(id_field):
                    ids.add(
                        row[id_field]
                    )

    new_rows = [
        row
        for row in rows
        if row[id_field] not in ids
    ]

    if not new_rows:
        return

    tmp = path.with_name(
        path.name + ".tmp"
    )

    with tmp.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )

        writer.writeheader()

        for row in existing:
            writer.writerow(row)

        for row in new_rows:
            writer.writerow(row)

        f.flush()
        os.fsync(
            f.fileno()
        )

    os.replace(
        tmp,
        path,
    )


SIGNAL_FIELDS = [
    "signal_id",
    "strategy",
    "symbol",
    "signal",
]

TRADE_FIELDS = [
    "trade_id",
    "strategy",
    "symbol",
    "side",
]

RUN_FIELDS = [
    "commit_id",
    "status",
]


def read_csv(path):

    if not path.exists():
        return []

    with path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as f:
        return list(
            csv.DictReader(f)
        )


# ------------------------------------------------------------
# Test transaction.
# ------------------------------------------------------------

def fresh_case(base):

    if base.exists():
        shutil.rmtree(base)

    base.mkdir(
        parents=True
    )

    state = {
        "cash": "10000",
        "processed_candle_closes": [],
    }

    peaks = {
        "equity_peak": "10000",
    }

    atomic_json(
        base / "state.json",
        state,
    )

    atomic_json(
        base / "peaks.json",
        peaks,
    )

    journal = {
        "version": 3,
        "commit_id": "TEST_COMMIT_001",
        "status": "PREPARED",

        "signals": [
            {
                "signal_id":
                    "SIG_001",
                "strategy":
                    "RSI14",
                "symbol":
                    "MINATRY",
                "signal":
                    "BUY",
            }
        ],

        "trades": [
            {
                "trade_id":
                    "TRADE_001",
                "strategy":
                    "RSI14",
                "symbol":
                    "MINATRY",
                "side":
                    "BUY",
            }
        ],

        "run": {
            "commit_id":
                "TEST_COMMIT_001",
            "status":
                "OK",
        },

        "new_state": {
            "cash":
                "9000",
            "processed_candle_closes": [
                "TEST_CLOSE"
            ],
        },

        "new_peaks": {
            "equity_peak":
                "10025",
        },
    }

    atomic_json(
        base / "journal.json",
        journal,
    )

    return journal


def commit(
    base,
    crash_after=None,
):

    jp = base / "journal.json"

    journal = json.loads(
        jp.read_text(
            encoding="utf-8"
        )
    )

    if journal["status"] == "COMMITTED":
        return

    journal["status"] = "COMMITTING"

    atomic_json(
        jp,
        journal,
    )

    if crash_after == "journal":
        raise RuntimeError(
            "SIMULATED CRASH"
        )

    append_unique(
        base / "signals.csv",
        SIGNAL_FIELDS,
        journal["signals"],
        "signal_id",
    )

    if crash_after == "signals":
        raise RuntimeError(
            "SIMULATED CRASH"
        )

    append_unique(
        base / "trades.csv",
        TRADE_FIELDS,
        journal["trades"],
        "trade_id",
    )

    if crash_after == "trades":
        raise RuntimeError(
            "SIMULATED CRASH"
        )

    append_unique(
        base / "runs.csv",
        RUN_FIELDS,
        [journal["run"]],
        "commit_id",
    )

    if crash_after == "runs":
        raise RuntimeError(
            "SIMULATED CRASH"
        )

    atomic_json(
        base / "state.json",
        journal["new_state"],
    )

    if crash_after == "state":
        raise RuntimeError(
            "SIMULATED CRASH"
        )

    atomic_json(
        base / "peaks.json",
        journal["new_peaks"],
    )

    if crash_after == "peaks":
        raise RuntimeError(
            "SIMULATED CRASH"
        )

    journal["status"] = "COMMITTED"

    atomic_json(
        jp,
        journal,
    )


def assert_final(base):

    signals = read_csv(
        base / "signals.csv"
    )

    trades = read_csv(
        base / "trades.csv"
    )

    runs = read_csv(
        base / "runs.csv"
    )

    state = json.loads(
        (
            base / "state.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    peaks = json.loads(
        (
            base / "peaks.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    journal = json.loads(
        (
            base / "journal.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert len(signals) == 1
    assert len(trades) == 1
    assert len(runs) == 1

    assert (
        signals[0]["signal_id"]
        == "SIG_001"
    )

    assert (
        trades[0]["trade_id"]
        == "TRADE_001"
    )

    assert (
        runs[0]["commit_id"]
        == "TEST_COMMIT_001"
    )

    assert state["cash"] == "9000"

    assert (
        state[
            "processed_candle_closes"
        ]
        == ["TEST_CLOSE"]
    )

    assert (
        peaks["equity_peak"]
        == "10025"
    )

    assert (
        journal["status"]
        == "COMMITTED"
    )


# ------------------------------------------------------------
# Execute crash matrix.
# ------------------------------------------------------------

crash_points = [
    None,
    "journal",
    "signals",
    "trades",
    "runs",
    "state",
    "peaks",
]


with tempfile.TemporaryDirectory(
    prefix="portfolioai_v3_torture_"
) as td:

    root = Path(td)

    passed = 0

    for point in crash_points:

        label = (
            "NO_CRASH"
            if point is None
            else point.upper()
        )

        case = root / label

        fresh_case(
            case
        )

        if point is None:

            commit(
                case
            )

        else:

            try:
                commit(
                    case,
                    crash_after=point,
                )

            except RuntimeError as exc:

                if (
                    str(exc)
                    != "SIMULATED CRASH"
                ):
                    raise

            # Startup recovery:
            # replay exact same journal.
            commit(
                case
            )

        assert_final(
            case
        )

        # Replay recovery a SECOND time.
        # Must remain exactly idempotent.
        commit(
            case
        )

        assert_final(
            case
        )

        print(
            f"{label:<12}: PASS"
        )

        passed += 1


    print("")
    print(
        "CRASH CASES :",
        passed,
        "/",
        len(crash_points),
        "PASS",
    )

    print(
        "DUP SIGNALS : 0"
    )

    print(
        "DUP TRADES  : 0"
    )

    print(
        "DUP RUNS    : 0"
    )

    print(
        "RECOVERY    : IDEMPOTENT"
    )


print("")
print(
    "ISOLATED TORTURE TEST : PASS"
)

print(
    "LIVE RUNNER EXECUTED  : NO"
)

print(
    "REAL ORDER             : NO"
)
