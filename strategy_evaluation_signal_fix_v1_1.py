import csv
import json
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path.cwd()

FILES = [
    ROOT / "multistrategy_live_signals_v1.csv",
    ROOT / "multistrategy_live_signals_v3.csv",
]


def read_csv(path):
    if not path.exists():
        return [], []

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        return (
            list(reader),
            reader.fieldnames or [],
        )


v1, h1 = read_csv(FILES[0])
v3, h3 = read_csv(FILES[1])

print("")
print("=== V1 SIGNAL HEADER ===")
print(h1)

print("")
print("=== V3 SIGNAL HEADER ===")
print(h3)

print("")
print("RAW V1 :", len(v1))
print("RAW V3 :", len(v3))


# ------------------------------------------------------------
# Detect actual candle/time field
# ------------------------------------------------------------

candidates = [
    "signal_candle_close_utc",
    "candle_close_utc",
    "target_candle_close_utc",
    "candle_close",
    "close_time_utc",
    "observed_candle_close_utc",
    "timestamp_utc",
    "observed_at_utc",
]


def detect_time_field(rows, headers):

    for name in candidates:

        if name not in headers:
            continue

        populated = sum(
            1
            for r in rows
            if str(r.get(name, "")).strip()
        )

        unique = len({
            str(r.get(name, "")).strip()
            for r in rows
            if str(r.get(name, "")).strip()
        })

        if populated:
            return name, populated, unique

    # fallback: inspect any header containing time/close/candle
    possible = [
        h for h in headers
        if any(
            x in h.lower()
            for x in (
                "time",
                "candle",
                "close",
                "utc",
            )
        )
    ]

    for name in possible:

        populated = sum(
            1
            for r in rows
            if str(r.get(name, "")).strip()
        )

        unique = len({
            str(r.get(name, "")).strip()
            for r in rows
            if str(r.get(name, "")).strip()
        })

        if populated:
            return name, populated, unique

    return None, 0, 0


v1_time, v1_pop, v1_unique = detect_time_field(
    v1,
    h1,
)

v3_time, v3_pop, v3_unique = detect_time_field(
    v3,
    h3,
)

print("")
print("=== TIME FIELD DETECTION ===")

print(
    "V1:",
    v1_time,
    "| populated:",
    v1_pop,
    "| unique:",
    v1_unique,
)

print(
    "V3:",
    v3_time,
    "| populated:",
    v3_pop,
    "| unique:",
    v3_unique,
)


if v1 and not v1_time:
    raise RuntimeError(
        "V1 signal candle/time field could not be detected"
    )


# ------------------------------------------------------------
# Build collision-safe identity
# ------------------------------------------------------------

def identity(row, source, time_field):

    signal_id = str(
        row.get("signal_id", "")
    ).strip()

    if signal_id:
        return (
            "SIGNAL_ID",
            signal_id,
        )

    candle = str(
        row.get(time_field, "")
    ).strip()

    strategy = str(
        row.get("strategy", "")
    ).strip()

    symbol = str(
        row.get("symbol", "")
    ).strip()

    signal = str(
        row.get("signal", "")
    ).strip()

    if not candle:
        raise RuntimeError(
            f"{source}: empty candle identity"
        )

    if not strategy:
        raise RuntimeError(
            f"{source}: empty strategy"
        )

    if not symbol:
        raise RuntimeError(
            f"{source}: empty symbol"
        )

    return (
        "LEGACY",
        candle,
        strategy,
        symbol,
        signal,
    )


merged = []
seen = set()
duplicates = 0


for source, rows, time_field in (
    ("V1", v1, v1_time),
    ("V3", v3, v3_time),
):

    for row in rows:

        key = identity(
            row,
            source,
            time_field,
        )

        if key in seen:
            duplicates += 1
            continue

        seen.add(key)

        x = dict(row)
        x["_source"] = source

        merged.append(x)


print("")
print("=== MERGE ===")
print("RAW TOTAL     :", len(v1) + len(v3))
print("UNIQUE TOTAL  :", len(merged))
print("DUPLICATES    :", duplicates)


# ------------------------------------------------------------
# V1 integrity
# ------------------------------------------------------------

v1_keys = [
    identity(r, "V1", v1_time)
    for r in v1
]

v1_unique_count = len(set(v1_keys))

print("")
print("V1 UNIQUE     :", v1_unique_count)

if v1_unique_count != len(v1):
    raise RuntimeError(
        "Unexpected duplicate rows inside V1 signal ledger"
    )

if len(v1) != 189:
    print(
        "WARNING: V1 row count is no longer 189; current count:",
        len(v1),
    )
else:
    print("V1 189/189    : PASS")


# ------------------------------------------------------------
# Strategy counts
# ------------------------------------------------------------

stats = defaultdict(
    lambda: Counter()
)

for row in merged:

    strategy = str(
        row.get("strategy", "")
    )

    signal = str(
        row.get("signal", "")
    )

    stats[strategy]["TOTAL"] += 1
    stats[strategy][signal] += 1


print("")
print("=== CORRECTED SIGNAL COUNTS ===")

for strategy in (
    "SMA20_50",
    "EMA12_26",
    "RSI14",
):

    s = stats[strategy]

    print("")
    print(strategy)
    print("  TOTAL :", s["TOTAL"])
    print("  BUY   :", s["BUY"])
    print("  SELL  :", s["SELL"])
    print("  NONE  :", s["NONE"])


# ------------------------------------------------------------
# Verify expected V1 structure
# 3 runs * 21 symbols = 63 rows per strategy
# ------------------------------------------------------------

v1_stats = defaultdict(
    lambda: Counter()
)

for row in v1:

    strategy = row.get(
        "strategy",
        ""
    )

    signal = row.get(
        "signal",
        ""
    )

    v1_stats[strategy]["TOTAL"] += 1
    v1_stats[strategy][signal] += 1


print("")
print("=== V1 STRUCTURE ===")

for strategy in (
    "SMA20_50",
    "EMA12_26",
    "RSI14",
):

    total = v1_stats[
        strategy
    ]["TOTAL"]

    print(
        strategy,
        ":",
        total,
    )

    if len(v1) == 189 and total != 63:
        raise RuntimeError(
            f"{strategy}: expected 63 V1 rows, got {total}"
        )


# ------------------------------------------------------------
# Save metadata only.
# No live file modification.
# ------------------------------------------------------------

report = {
    "version":
        "strategy_evaluation_signal_fix_v1_1",

    "v1": {
        "rows":
            len(v1),

        "time_field":
            v1_time,

        "unique_rows":
            v1_unique_count,
    },

    "v3": {
        "rows":
            len(v3),

        "time_field":
            v3_time,
    },

    "merged": {
        "raw_rows":
            len(v1) + len(v3),

        "unique_rows":
            len(merged),

        "duplicates_removed":
            duplicates,
    },

    "strategy_counts": {
        strategy: {
            "total":
                stats[strategy]["TOTAL"],

            "buy":
                stats[strategy]["BUY"],

            "sell":
                stats[strategy]["SELL"],

            "none":
                stats[strategy]["NONE"],
        }
        for strategy in (
            "SMA20_50",
            "EMA12_26",
            "RSI14",
        )
    },
}


out = ROOT / (
    "strategy_evaluation_signal_fix_v1_1.json"
)

tmp = out.with_suffix(
    ".json.tmp"
)

tmp.write_text(
    json.dumps(
        report,
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

tmp.replace(out)


print("")
print("=" * 72)
print("SIGNAL LEDGER FIX V1.1 : PASS")
print("V1/V3 LIVE FILE WRITE  : NO")
print("REAL ORDERS            : NO")
print("=" * 72)
