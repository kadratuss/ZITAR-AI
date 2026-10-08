from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent

EVENTS = BASE / "zitar_master_trade_events_v1.jsonl"
STATE = BASE / "zitar_master_portfolio_v1.json"
BRIDGE_STATE = BASE / "zitar_master_execution_bridge_v1.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}

    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def read_events() -> list[dict]:

    if not EVENTS.exists():
        return []

    rows = []

    for line in EVENTS.read_text(
        encoding="utf-8-sig"
    ).splitlines():

        if not line.strip():
            continue

        rows.append(
            json.loads(line)
        )

    return rows


def event_id(event: dict) -> str:

    value = (
        event.get("source_trade_id")
        or ""
    ).strip()

    if not value:
        raise RuntimeError(
            "FAIL: event without source_trade_id"
        )

    return value


def validate_event(event: dict) -> None:

    if event.get("schema") != \
            "ZITAR_MASTER_TRADE_EVENT_V1":
        raise RuntimeError(
            "FAIL: unexpected event schema"
        )

    if event.get("side") not in {
        "BUY",
        "SELL"
    }:
        raise RuntimeError(
            "FAIL: invalid event side"
        )

    for key in (
        "strategy",
        "symbol",
        "reference_price"
    ):
        if not event.get(key):
            raise RuntimeError(
                f"FAIL: missing {key}"
            )


def main():

    print("ZITAR MASTER EXECUTION BRIDGE V1")
    print(
        "DRY RUN ONLY • "
        "NO MASTER WRITE • "
        "NO PAPER ORDER • "
        "NO REAL ORDER • "
        "NO V3 WRITE"
    )
    print()

    if not STATE.exists():
        raise SystemExit(
            "FAIL: master portfolio state not found"
        )

    master = load_json(STATE)

    if master.get("schema") != \
            "ZITAR_MASTER_PORTFOLIO_V1":
        raise SystemExit(
            "FAIL: unexpected master state schema"
        )

    bridge = load_json(BRIDGE_STATE)

    processed = set(
        bridge.get(
            "processed_event_ids",
            []
        )
    )

    events = read_events()

    ids = [
        event_id(x)
        for x in events
    ]

    if len(ids) != len(set(ids)):
        raise SystemExit(
            "FAIL: duplicate source_trade_id "
            "in event log"
        )

    pending = []

    for event in events:

        validate_event(event)

        if event_id(event) not in processed:
            pending.append(event)

    print(
        "master period:",
        master.get(
            "current_period",
            {}
        ).get(
            "period_id"
        )
    )

    print(
        "master equity:",
        master.get(
            "account",
            {}
        ).get(
            "equity_try"
        ),
        "TRY"
    )

    print(
        "events:",
        len(events)
    )

    print(
        "bridge processed:",
        len(processed)
    )

    print(
        "pending:",
        len(pending)
    )

    for event in pending:

        print(
            "PENDING:",
            event["side"],
            event["strategy"],
            event["symbol"],
            event_id(event)[:12],
            "price=",
            event["reference_price"]
        )

    print()
    print(
        "Master modified:",
        False
    )

    print(
        "Bridge state modified:",
        False
    )

    print(
        "V3 modified:",
        False
    )

    print("STATUS: PASS")


if __name__ == "__main__":
    main()
