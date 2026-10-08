from __future__ import annotations

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

BASE = Path(__file__).resolve().parent

EVENTS = BASE / "zitar_master_trade_events_v1.jsonl"
MASTER_STATE = BASE / "zitar_master_portfolio_v1.json"
BRIDGE_STATE = BASE / "zitar_master_execution_bridge_v1.json"
ENGINE_PATH = BASE / "zitar_master_paper_engine_v1.py"


def load_json(path: Path) -> dict:

    if not path.exists():
        return {}

    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def atomic_save_json(
    path: Path,
    data: dict
) -> None:

    payload = json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    )

    temp = path.with_name(
        path.name + ".tmp"
    )

    temp.write_text(
        payload,
        encoding="utf-8"
    )

    temp.replace(path)


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

    price = Decimal(
        str(event["reference_price"])
    )

    if price <= 0:
        raise RuntimeError(
            "FAIL: reference_price <= 0"
        )


def load_engine():

    if not ENGINE_PATH.exists():
        raise RuntimeError(
            "FAIL: paper engine not found"
        )

    spec = importlib.util.spec_from_file_location(
        "zitar_master_paper_engine_runtime",
        ENGINE_PATH
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            "FAIL: paper engine import failed"
        )

    engine = importlib.util.module_from_spec(
        spec
    )

    spec.loader.exec_module(
        engine
    )

    # KRİTİK:
    # Engine kaynak kodundaki test STATE'e dokunmuyoruz.
    # Sadece bu Bridge process'i içinde
    # gerçek Master paper state'e yönlendiriyoruz.
    engine.STATE = MASTER_STATE

    return engine


def main():

    print(
        "ZITAR MASTER EXECUTION BRIDGE V1"
    )

    print(
        "MASTER PAPER EXECUTION ENABLED • "
        "NO REAL ORDER • NO V3 WRITE"
    )

    print()

    if not MASTER_STATE.exists():
        raise SystemExit(
            "FAIL: master portfolio state not found"
        )

    master_before = load_json(
        MASTER_STATE
    )

    if master_before.get("schema") != \
            "ZITAR_MASTER_PORTFOLIO_V1":

        raise SystemExit(
            "FAIL: unexpected master state schema"
        )

    # Master execution için gereken alanlar.
    if "processed_event_ids" not in master_before:
        raise SystemExit(
            "FAIL: Master missing processed_event_ids"
        )

    if "account" not in master_before:
        raise SystemExit(
            "FAIL: Master missing account"
        )

    bridge = load_json(
        BRIDGE_STATE
    )

    bridge_processed = set(
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

        eid = event_id(event)

        if eid not in bridge_processed:
            pending.append(event)

    print(
        "master period:",
        master_before.get(
            "current_period",
            {}
        ).get(
            "period_id"
        )
    )

    print(
        "master equity before:",
        master_before[
            "account"
        ].get(
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
        len(bridge_processed)
    )

    print(
        "pending:",
        len(pending)
    )

    # Event yoksa Engine'i bile çalıştırmaya gerek yok.
    if not pending:

        print()
        print(
            "No pending Master events."
        )
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
        print(
            "Real order:",
            False
        )
        print(
            "STATUS: PASS"
        )

        return

    engine = load_engine()

    applied = 0

    for event in pending:

        eid = event_id(event)

        side = event["side"]
        strategy = event["strategy"]
        symbol = event["symbol"]

        price = Decimal(
            str(
                event["reference_price"]
            )
        )

        # Her event öncesinde diskten gerçek
        # Master state yeniden okunur.
        state = engine.load()

        if state.get("schema") != \
                "ZITAR_MASTER_PORTFOLIO_V1":

            raise RuntimeError(
                "FAIL: engine loaded "
                "unexpected Master schema"
            )

        if side == "BUY":

            result = engine.buy(
                state=state,
                symbol=symbol,
                strategy=strategy,
                reference_price=price,
                event_id=eid
            )

        else:

            result = \
                engine.remove_support_or_sell(
                    state=state,
                    symbol=symbol,
                    strategy=strategy,
                    reference_price=price,
                    event_id=eid
                )

        print(
            "EXECUTED:",
            side,
            strategy,
            symbol,
            eid[:12],
            "->",
            result
        )

        # Engine sonucu ne olursa olsun ancak
        # event gerçekten processed_event_ids'e
        # girdiyse Bridge tamamlanmış sayar.
        state_after = engine.load()

        master_processed = set(
            state_after.get(
                "processed_event_ids",
                []
            )
        )

        if eid not in master_processed:

            # MAX_POSITIONS / INSUFFICIENT_CASH gibi
            # işlenmemiş event'leri sessizce yutma.
            raise RuntimeError(
                "MASTER EVENT NOT COMMITTED: "
                f"{eid} result={result}"
            )

        # Önce Master commit edildi.
        # Şimdi Bridge watermark ilerleyebilir.
        bridge_processed.add(eid)

        bridge[
            "processed_event_ids"
        ] = sorted(
            bridge_processed
        )

        bridge[
            "last_processed_event_id"
        ] = eid

        bridge[
            "last_result"
        ] = result

        atomic_save_json(
            BRIDGE_STATE,
            bridge
        )

        applied += 1

    final_master = load_json(
        MASTER_STATE
    )

    print()
    print(
        "applied:",
        applied
    )

    print(
        "master cash:",
        final_master[
            "account"
        ].get(
            "cash_try"
        ),
        "TRY"
    )

    print(
        "master positions:",
        final_master[
            "account"
        ].get(
            "open_position_count"
        )
    )

    print(
        "master realized P/L:",
        final_master[
            "account"
        ].get(
            "realized_pnl_try"
        ),
        "TRY"
    )

    print(
        "master equity:",
        final_master[
            "account"
        ].get(
            "equity_try"
        ),
        "TRY"
    )

    print()
    print(
        "Master paper modified:",
        applied > 0
    )

    print(
        "V3 modified:",
        False
    )

    print(
        "Real order:",
        False
    )

    print(
        "STATUS: PASS"
    )


if __name__ == "__main__":
    main()
