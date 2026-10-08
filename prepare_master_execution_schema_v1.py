import json
from pathlib import Path

P = Path("zitar_master_portfolio_v1.json")

d = json.loads(
    P.read_text(encoding="utf-8-sig")
)

if d.get("schema") != "ZITAR_MASTER_PORTFOLIO_V1":
    raise SystemExit("FAIL: unexpected Master schema")

account = d.get("account", {})

if account.get("equity_try") != "10000.00":
    raise SystemExit("FAIL: Master equity not clean")

if int(account.get("open_position_count", -1)) != 0:
    raise SystemExit("FAIL: Master has open positions")

# Master artık kendi execution idempotency bilgisini taşır.
d.setdefault("processed_event_ids", [])

# Execution modelinin açıkça state'te kayıtlı olması.
d["rules"]["fee_rate"] = "0.001"
d["rules"]["slippage_rate"] = "0.001"

# Geçiş döneminde Engine uyumluluğu.
d["rules"]["max_positions"] = int(
    d["rules"]["max_spot_positions"]
)

tmp = P.with_name(P.name + ".tmp")

tmp.write_text(
    json.dumps(
        d,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

tmp.replace(P)

print("MASTER EXECUTION SCHEMA PREP PASS")
print("processed events:", len(d["processed_event_ids"]))
print("max positions:", d["rules"]["max_positions"])
print("fee:", d["rules"]["fee_rate"])
print("slippage:", d["rules"]["slippage_rate"])
print("equity:", d["account"]["equity_try"])
