import json
from datetime import datetime
from pathlib import Path


state = json.loads(
    Path(
        "multistrategy_live_state_v3.json"
    ).read_text(
        encoding="utf-8-sig"
    )
)


freeze_dt = datetime.fromisoformat(
    state[
        "created_at_utc"
    ].replace(
        "Z",
        "+00:00",
    )
)

freeze_ms = int(
    freeze_dt.timestamp() * 1000
)


def guard(close_ms):

    if close_ms <= freeze_ms:
        raise RuntimeError(
            "freeze violation"
        )


# First real prospective close from V1 history.
first_prospective = datetime.fromisoformat(
    "2026-09-23T18:00:00+00:00"
)

guard(
    int(
        first_prospective.timestamp()
        * 1000
    )
)

print(
    "FIRST PROSPECTIVE     : PASS"
)


# Exact freeze.
try:

    guard(freeze_ms)

    raise AssertionError(
        "EXACT FREEZE ACCEPTED"
    )

except RuntimeError:
    pass

print(
    "EXACT FREEZE          : BLOCKED PASS"
)


# One millisecond before.
try:

    guard(
        freeze_ms - 1
    )

    raise AssertionError(
        "PRE FREEZE ACCEPTED"
    )

except RuntimeError:
    pass

print(
    "PRE FREEZE            : BLOCKED PASS"
)


# One millisecond after.
guard(
    freeze_ms + 1
)

print(
    "POST FREEZE           : PASS"
)


print("")
print(
    "REAL STATE FREEZE     :",
    state["created_at_utc"]
)

print(
    "FREEZE BOUNDARY TESTS : PASS"
)
