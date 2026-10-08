import ast
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path.cwd()

RUNNER = ROOT / "multistrategy_live_runner_v3.py"
OUTPUT = ROOT / "v3_hardening_audit_v1.json"

if not RUNNER.exists():
    raise RuntimeError("V3 runner missing")


source = RUNNER.read_text(
    encoding="utf-8-sig"
)

tree = ast.parse(
    source,
    filename=str(RUNNER)
)


def sha256_file(path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b""
        ):
            h.update(chunk)

    return h.hexdigest()


def atomic_json(path, obj):
    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            obj,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    tmp.replace(path)


functions = {
    node.name: node
    for node in ast.walk(tree)
    if isinstance(
        node,
        (
            ast.FunctionDef,
            ast.AsyncFunctionDef
        )
    )
}


names = {
    node.id
    for node in ast.walk(tree)
    if isinstance(node, ast.Name)
}


string_literals = [
    node.value
    for node in ast.walk(tree)
    if isinstance(node, ast.Constant)
    and isinstance(node.value, str)
]


# ------------------------------------------------------------
# Detect patterns conservatively.
#
# This audit reports evidence from source.
# It does NOT automatically declare safety.
# ------------------------------------------------------------

def contains_text(*parts):
    low = source.lower()

    return all(
        part.lower() in low
        for part in parts
    )


def any_text(*parts):
    low = source.lower()

    return any(
        part.lower() in low
        for part in parts
    )


checks = []


def add(
    check_id,
    description,
    detected,
    evidence,
    desired,
):
    checks.append({
        "id":
            check_id,

        "description":
            description,

        "detected":
            bool(detected),

        "evidence":
            evidence,

        "desired_state":
            desired,
    })


# 1. CSV append behavior
append_mode_detected = (
    'open(' in source
    and (
        '"a"' in source
        or "'a'" in source
        or 'mode="a"' in source
        or "mode='a'" in source
    )
)

add(
    "CSV_APPEND_MODE",
    "Direct append-mode CSV writes",
    append_mode_detected,
    "Source contains append-mode file open"
    if append_mode_detected
    else
    "No obvious append-mode open detected",
    "No in-place append for transaction-critical ledgers",
)


# 2. os.replace atomic replacement
replace_detected = (
    "os.replace" in source
)

add(
    "OS_REPLACE",
    "Atomic replacement primitive present",
    replace_detected,
    "os.replace found"
    if replace_detected
    else
    "os.replace not found",
    "Atomic replacement for committed files",
)


# 3. fsync
fsync_detected = (
    "fsync" in source.lower()
)

add(
    "FSYNC",
    "Durability flush present",
    fsync_detected,
    "fsync found"
    if fsync_detected
    else
    "fsync not found",
    "Flush + fsync before replace",
)


# 4. Journal
journal_detected = (
    "journal" in source.lower()
)

prepared_detected = (
    "PREPARED" in source
)

committed_detected = (
    "COMMITTED" in source
)

add(
    "JOURNAL",
    "Transaction journal present",
    journal_detected,
    {
        "journal_text":
            journal_detected,

        "PREPARED":
            prepared_detected,

        "COMMITTED":
            committed_detected,
    },
    "PREPARED -> durable writes -> COMMITTED",
)


# 5. Recovery
recovery_detected = (
    "recover" in source.lower()
    or "recovery" in source.lower()
)

add(
    "RECOVERY",
    "Startup recovery logic present",
    recovery_detected,
    "Recovery-related source text found"
    if recovery_detected
    else
    "No recovery-related source text found",
    "Deterministic startup recovery",
)


# 6. Data age
data_age_detected = any_text(
    "data_age",
    "data age",
    "max_age",
    "max data age",
    "stale",
)

add(
    "DATA_AGE",
    "Stale market-data protection",
    data_age_detected,
    "Possible data-age/staleness logic found"
    if data_age_detected
    else
    "No obvious data-age/staleness guard",
    "Fail closed on stale candles/book data",
)


# 7. Gap detection
gap_detected = any_text(
    "gap",
    "missing candle",
    "missing_candle",
    "expected candle",
)

add(
    "CANDLE_GAP",
    "Missing-candle/gap protection",
    gap_detected,
    "Possible gap logic found"
    if gap_detected
    else
    "No obvious candle-gap guard",
    "Fail closed on incomplete candle history",
)


# 8. Freeze boundary
freeze_detected = any_text(
    "freeze",
    "frozen",
    "start_after",
    "forward_start",
)

add(
    "FREEZE_BOUNDARY",
    "Forward-only freeze boundary enforcement",
    freeze_detected,
    "Possible freeze logic found"
    if freeze_detected
    else
    "No obvious freeze-boundary guard",
    "Never process pre-freeze candles",
)


# 9. Hard-coded universe
symbol_literals = []

for literal in string_literals:
    if (
        literal.endswith("TRY")
        and literal.upper() == literal
        and 4 <= len(literal) <= 30
    ):
        symbol_literals.append(
            literal
        )


unique_symbol_literals = sorted(
    set(symbol_literals)
)


hardcoded_universe_detected = (
    len(unique_symbol_literals) >= 10
)

add(
    "HARDCODED_UNIVERSE",
    "Large hard-coded TRY symbol set",
    hardcoded_universe_detected,
    unique_symbol_literals,
    "Universe loaded from frozen manifest/state",
)


# 10. Peak / drawdown state
peak_detected = any_text(
    "peak",
    "drawdown",
)

add(
    "PEAK_DRAWDOWN",
    "Peak/drawdown state logic present",
    peak_detected,
    "Peak/drawdown source text found"
    if peak_detected
    else
    "No obvious peak/drawdown logic",
    "Peak initialized and updated from book-valued equity",
)


# 11. Common book snapshot
book_ticker_detected = (
    "bookTicker" in source
    or "bookticker" in source.lower()
)

add(
    "BOOK_TICKER",
    "Bid/ask bookTicker execution source",
    book_ticker_detected,
    "bookTicker reference found"
    if book_ticker_detected
    else
    "No bookTicker reference found",
    "Single common all-symbol snapshot per run",
)


# 12. Real order endpoints
danger_tokens = (
    "/api/v3/order",
    "/api/v3/order/test",
    "create_order",
    "new_order",
)

real_order_tokens = [
    token
    for token in danger_tokens
    if token.lower() in source.lower()
]

add(
    "REAL_ORDER_CODE",
    "Real-order API/code tokens",
    bool(real_order_tokens),
    real_order_tokens,
    "Must remain absent in paper runner",
)


# ------------------------------------------------------------
# Function inventory
# ------------------------------------------------------------

function_inventory = sorted(
    functions.keys()
)


result = {
    "audit_version":
        "v3_hardening_audit_v1",

    "generated_at_utc":
        datetime.now(
            timezone.utc
        ).isoformat(),

    "runner":
        RUNNER.name,

    "runner_sha256":
        sha256_file(RUNNER),

    "source_lines":
        len(source.splitlines()),

    "function_count":
        len(function_inventory),

    "functions":
        function_inventory,

    "checks":
        checks,

    "real_order_tokens":
        real_order_tokens,

    "read_only":
        True,
}


atomic_json(
    OUTPUT,
    result
)


print("")
print("=" * 76)
print("V3 RUNNER HARDENING AUDIT V1")
print("=" * 76)

print(
    "RUNNER SHA256 :",
    result["runner_sha256"]
)

print(
    "SOURCE LINES  :",
    result["source_lines"]
)

print(
    "FUNCTIONS     :",
    result["function_count"]
)

print("")


for check in checks:

    print(
        f"{check['id']:<22}",
        ":",
        "DETECTED"
        if check["detected"]
        else "NOT DETECTED"
    )


print("")
print("HARDCODED SYMBOL LITERALS:")

for symbol in unique_symbol_literals:
    print(
        " ",
        symbol
    )


print("")
print("REAL ORDER TOKENS:")

if real_order_tokens:
    for token in real_order_tokens:
        print(
            " ",
            token
        )
else:
    print(
        " NONE"
    )


print("")
print("=" * 76)
print("AUDIT COMPLETE")
print("RUNNER MODIFIED : NO")
print("STATE MODIFIED  : NO")
print("TRADE WRITE     : NO")
print("REAL ORDER      : NO")
print("=" * 76)
