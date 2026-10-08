from datetime import datetime, timezone


freeze = datetime.fromisoformat(
    "2026-09-23T16:06:17.498708+00:00"
)


def check(target):

    if target <= freeze:
        raise RuntimeError(
            "freeze violation"
        )


# First actual prospective close.
check(
    datetime.fromisoformat(
        "2026-09-23T18:00:00+00:00"
    )
)

print(
    "FIRST PROSPECTIVE : PASS"
)


# Exact freeze must fail.
try:

    check(freeze)

    raise RuntimeError(
        "EXACT FREEZE DID NOT FAIL"
    )

except RuntimeError as exc:

    if str(exc) == (
        "EXACT FREEZE DID NOT FAIL"
    ):
        raise

print(
    "EXACT FREEZE      : FAIL-CLOSED PASS"
)


# Pre-freeze close must fail.
try:

    check(
        datetime.fromisoformat(
            "2026-09-23T16:00:00+00:00"
        )
    )

    raise RuntimeError(
        "PRE-FREEZE DID NOT FAIL"
    )

except RuntimeError as exc:

    if str(exc) == (
        "PRE-FREEZE DID NOT FAIL"
    ):
        raise

print(
    "PRE-FREEZE        : FAIL-CLOSED PASS"
)


# Future close passes.
check(
    datetime.fromisoformat(
        "2026-09-24T00:00:00+00:00"
    )
)

print(
    "FUTURE CLOSE      : PASS"
)

print("")
print(
    "FREEZE TESTS      : PASS"
)
