import ast
from pathlib import Path

P = Path(
    "multistrategy_live_runner_v3.py"
)

source = P.read_text(
    encoding="utf-8-sig"
)


# ------------------------------------------------------------
# Exact anchor 1:
# We KNOW this exists from inspector.
# ------------------------------------------------------------

state_anchor = '''    state = read_json(STATE)
    peaks = load_peaks()
'''

state_replacement = '''    state = read_json(STATE)
    peaks = load_peaks()

    # HARDENING PATCH 2B
    # Immutable forward-only experiment boundary.
    freeze_raw = state.get(
        "created_at_utc"
    )

    if not freeze_raw:
        raise RuntimeError(
            "Forward freeze boundary missing: "
            "created_at_utc"
        )

    freeze_dt = datetime.fromisoformat(
        str(freeze_raw).replace(
            "Z",
            "+00:00",
        )
    )

    if freeze_dt.tzinfo is None:
        raise RuntimeError(
            "Forward freeze boundary must "
            "be timezone-aware"
        )

    freeze_ms = int(
        freeze_dt.timestamp() * 1000
    )
'''


if source.count(state_anchor) != 1:
    raise RuntimeError(
        "STATE ANCHOR COUNT != 1"
    )


source = source.replace(
    state_anchor,
    state_replacement,
    1,
)


# ------------------------------------------------------------
# Exact anchor 2:
# target_close is integer epoch milliseconds.
# Therefore compare milliseconds directly.
# No datetime guessing.
# ------------------------------------------------------------

target_anchor = '''    close_key = iso(target_close)

    if close_key in state.get(
'''

target_replacement = '''    close_key = iso(target_close)

    # HARDENING PATCH 2B - FREEZE ENFORCEMENT
    #
    # Only candles closing strictly AFTER the immutable
    # experiment creation boundary may be processed.
    if target_close <= freeze_ms:
        raise RuntimeError(
            "Forward-only freeze violation: "
            f"target_close={close_key} "
            f"freeze={freeze_dt.isoformat()}"
        )

    if close_key in state.get(
'''


if source.count(target_anchor) != 1:
    raise RuntimeError(
        "TARGET ANCHOR COUNT != 1"
    )


source = source.replace(
    target_anchor,
    target_replacement,
    1,
)


# ------------------------------------------------------------
# Verify all previous hardening survived.
# ------------------------------------------------------------

required = (
    "HARDENING PATCH 2B",
    "Forward-only freeze violation",
    "freeze_ms",
    "created_at_utc",
    "candle gap detected",
    "target candle mismatch",
    "target close mismatch",
    "os.replace",
    "os.fsync",
)


for token in required:

    if token not in source:
        raise RuntimeError(
            f"Required token missing: {token}"
        )


# Compile AST BEFORE touching runner.
ast.parse(source)


P.write_text(
    source,
    encoding="utf-8",
)


print(
    "PATCH 2B SOURCE PATCH : PASS"
)
print(
    "STATE SOURCE          : read_json(STATE)"
)
print(
    "FREEZE SOURCE         : created_at_utc"
)
print(
    "COMPARISON            : target_close_ms > freeze_ms"
)
