import csv
import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent

TRADES = BASE / "multistrategy_live_trades_v3.csv"
OUT = BASE / "zitar_master_trade_watermark_v1.json"


def main():

    if not TRADES.exists():
        raise SystemExit(
            "FAIL: multistrategy_live_trades_v3.csv not found"
        )

    with TRADES.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as fh:
        rows = list(csv.DictReader(fh))

    trade_ids = []

    for row in rows:

        trade_id = (
            row.get("trade_id") or ""
        ).strip()

        if trade_id:
            trade_ids.append(trade_id)

    unique_ids = list(dict.fromkeys(trade_ids))

    if len(unique_ids) != len(trade_ids):
        raise SystemExit(
            "FAIL: duplicate trade_id detected"
        )

    sell_ids = [
        row["trade_id"]
        for row in rows
        if (
            row.get("side") == "SELL"
            and row.get("trade_id")
        )
    ]

    payload = {
        "schema":
            "ZITAR_MASTER_TRADE_WATERMARK_V1",

        "created_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "source":
            TRADES.name,

        "baseline_policy":
            "EXISTING_V3_HISTORY_NOT_MASTER_PERFORMANCE",

        "baseline_trade_count":
            len(rows),

        "baseline_sell_count":
            len(sell_ids),

        "processed_trade_ids":
            unique_ids,

        "last_source_trade_id":
            unique_ids[-1]
            if unique_ids
            else None,

        "master_imported_trade_count":
            0,

        "master_imported_sell_count":
            0,

        "master_imported_realized_pnl_try":
            "0.00",

        "authorities": {
            "paper_order": False,
            "real_order": False,
            "modify_v3": False
        }
    }

    OUT.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print("ZITAR MASTER TRADE WATERMARK V1")
    print(
        "READ BASELINE ONLY • "
        "NO ORDER • NO V3 WRITE"
    )
    print()
    print(
        "baseline trades:",
        len(rows)
    )
    print(
        "baseline sells:",
        len(sell_ids)
    )
    print(
        "unique trade ids:",
        len(unique_ids)
    )
    print(
        "master imported:",
        0
    )
    print()
    print("output:", OUT)
    print("STATUS: PASS")


if __name__ == "__main__":
    main()
