import csv
import json
import hashlib
from pathlib import Path

ROOT = Path.cwd()

files = [
    "multistrategy_live_state_v3.json",
    "multistrategy_live_signals_v3.csv",
    "multistrategy_live_trades_v3.csv",
    "multistrategy_live_runs_v3.csv",
]

snapshot = {}

for name in files:

    p = ROOT / name

    if p.exists():

        snapshot[name] = {
            "exists": True,
            "sha256":
                hashlib.sha256(
                    p.read_bytes()
                ).hexdigest(),
            "size":
                p.stat().st_size,
        }

    else:

        snapshot[name] = {
            "exists": False,
            "sha256": None,
            "size": 0,
        }


Path(
    "controlled_run_before.json"
).write_text(
    json.dumps(
        snapshot,
        indent=2,
    ),
    encoding="utf-8",
)


state = json.loads(
    (
        ROOT
        / "multistrategy_live_state_v3.json"
    ).read_text(
        encoding="utf-8-sig"
    )
)


print("")
print("=== BEFORE ===")

print(
    "Processed candles:",
    len(
        state.get(
            "processed_candle_closes",
            []
        )
    )
)

if state.get(
    "processed_candle_closes"
):
    print(
        "Last processed:",
        state[
            "processed_candle_closes"
        ][-1]
    )


for strategy, account in state[
    "accounts"
].items():

    print(
        strategy,
        "cash=",
        account.get("cash_try"),
        "positions=",
        len(
            account.get(
                "positions",
                {}
            )
        ),
    )
