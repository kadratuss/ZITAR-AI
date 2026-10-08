from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent

TRADES = BASE / "multistrategy_live_trades_v3.csv"
WATERMARK = BASE / "zitar_master_trade_watermark_v1.json"
EVENTS = BASE / "zitar_master_trade_events_v1.jsonl"


def now_utc():
    return datetime.now(timezone.utc)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}

    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def save_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def read_trades() -> list[dict]:

    if not TRADES.exists():
        raise SystemExit(
            "FAIL: V3 trade CSV not found"
        )

    with TRADES.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as fh:
        return list(csv.DictReader(fh))


def append_event(event: dict) -> None:

    with EVENTS.open(
        "a",
        encoding="utf-8"
    ) as fh:
        fh.write(
            json.dumps(
                event,
                ensure_ascii=False,
                separators=(",", ":")
            )
            + "\n"
        )


def main():

    if not WATERMARK.exists():
        raise SystemExit(
            "FAIL: watermark not initialized"
        )

    watermark = load_json(WATERMARK)
    rows = read_trades()

    processed = set(
        watermark.get(
            "processed_trade_ids",
            []
        )
    )

    source_ids = []

    for row in rows:

        trade_id = (
            row.get("trade_id") or ""
        ).strip()

        if trade_id:
            source_ids.append(trade_id)

    if len(source_ids) != len(set(source_ids)):
        raise SystemExit(
            "FAIL: duplicate trade_id in V3 CSV"
        )

    new_rows = []

    for row in rows:

        trade_id = (
            row.get("trade_id") or ""
        ).strip()

        if not trade_id:
            continue

        if trade_id not in processed:
            new_rows.append(row)

    print("ZITAR MASTER TRADE DETECTOR V1")
    print(
        "EVENT DETECTION ONLY • "
        "NO PAPER ORDER • NO REAL ORDER • "
        "NO V3 WRITE"
    )
    print()

    print("source trades:", len(rows))
    print("already processed:", len(processed))
    print("new trades:", len(new_rows))

    imported_sells = 0

    for row in new_rows:

        trade_id = row["trade_id"]

        event = {
            "schema":
                "ZITAR_MASTER_TRADE_EVENT_V1",

            "detected_utc":
                now_utc().isoformat(),

            "source":
                TRADES.name,

            "source_trade_id":
                trade_id,

            "executed_at_utc":
                row.get("executed_at_utc"),

            "signal_candle_close_utc":
                row.get(
                    "signal_candle_close_utc"
                ),

            "strategy":
                row.get("strategy"),

            "symbol":
                row.get("symbol"),

            "side":
                row.get("side"),

            "reference_price":
                row.get("reference_price"),

            "modeled_fill_price":
                row.get("modeled_fill_price"),

            "source_quantity":
                row.get("quantity"),

            "source_realized_pnl_try":
                row.get("realized_pnl_try"),

            "policy": {
                "event_is_master_execution":
                    False,

                "source_pnl_is_master_pnl":
                    False,

                "master_order_authority":
                    False
            }
        }

        append_event(event)

        processed.add(trade_id)

        if row.get("side") == "SELL":
            imported_sells += 1

        print(
            "NEW:",
            row.get("side"),
            row.get("strategy"),
            row.get("symbol"),
            trade_id[:12]
        )

    watermark[
        "processed_trade_ids"
    ] = sorted(processed)

    watermark[
        "last_detector_run_utc"
    ] = now_utc().isoformat()

    watermark[
        "last_detector_source_trade_count"
    ] = len(rows)

    watermark[
        "last_detector_new_trade_count"
    ] = len(new_rows)

    watermark[
        "master_imported_trade_count"
    ] = int(
        watermark.get(
            "master_imported_trade_count",
            0
        )
    ) + len(new_rows)

    watermark[
        "master_imported_sell_count"
    ] = int(
        watermark.get(
            "master_imported_sell_count",
            0
        )
    ) + imported_sells

    if source_ids:
        watermark[
            "last_source_trade_id"
        ] = source_ids[-1]

    save_json(
        WATERMARK,
        watermark
    )

    print()
    print(
        "events written:",
        len(new_rows)
    )
    print(
        "V3 modified:",
        False
    )
    print(
        "Master portfolio modified:",
        False
    )
    print("STATUS: PASS")


if __name__ == "__main__":
    main()
