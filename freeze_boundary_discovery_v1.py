import csv
import json
import hashlib
from pathlib import Path

ROOT = Path.cwd()

FILES = [
    "multistrategy_live_state_v1.json",
    "multistrategy_live_state_v3.json",
    "multistrategy_live_signals_v1.csv",
    "multistrategy_live_signals_v3.csv",
    "multistrategy_live_runs_v3.csv",
]

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


before = {}

for name in FILES:
    p = ROOT / name
    if p.exists():
        before[name] = sha(p)


print("")
print("=== V3 STATE ===")

state_path = ROOT / "multistrategy_live_state_v3.json"

state = json.loads(
    state_path.read_text(
        encoding="utf-8-sig"
    )
)

# Show only time/freeze/processed related top-level data.
for key, value in state.items():

    low = key.lower()

    if any(
        word in low
        for word in (
            "freeze",
            "start",
            "created",
            "processed",
            "candle",
            "time",
            "migrat",
        )
    ):
        print(
            f"{key}: {value}"
        )


print("")
print("=== STATE STRUCTURE ===")

print(
    "TOP LEVEL KEYS:",
    sorted(state.keys())
)


def inspect_csv(name):

    p = ROOT / name

    print("")
    print(
        f"=== {name} ==="
    )

    if not p.exists():
        print("MISSING")
        return

    with p.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as f:

        reader = csv.DictReader(f)

        print(
            "HEADER:",
            reader.fieldnames
        )

        rows = []

        for row in reader:
            rows.append(row)

    print(
        "ROWS:",
        len(rows)
    )

    if not rows:
        return

    print("")
    print("FIRST ROW:")

    for k, v in rows[0].items():
        print(
            f"  {k}: {v}"
        )

    print("")
    print("LAST ROW:")

    for k, v in rows[-1].items():
        print(
            f"  {k}: {v}"
        )


inspect_csv(
    "multistrategy_live_signals_v1.csv"
)

inspect_csv(
    "multistrategy_live_signals_v3.csv"
)

inspect_csv(
    "multistrategy_live_runs_v3.csv"
)


print("")
print("=== IMMUTABILITY ===")

for name, old_hash in before.items():

    p = ROOT / name

    new_hash = sha(p)

    ok = (
        old_hash == new_hash
    )

    print(
        f"{name}:",
        "PASS" if ok else "FAIL"
    )

    if not ok:
        raise RuntimeError(
            f"{name} changed"
        )


print("")
print("============================================================")
print("FREEZE DISCOVERY : PASS")
print("STATE WRITE      : NO")
print("TRADE WRITE      : NO")
print("RUNNER EXECUTED  : NO")
print("REAL ORDER       : NO")
print("============================================================")
