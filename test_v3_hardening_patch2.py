ONE_HOUR_MS = 60 * 60 * 1000


def validate(
    candles,
    target_open_ms,
):

    if len(candles) < 60:
        raise RuntimeError(
            "insufficient"
        )

    recent = candles[-60:]

    for previous, current in zip(
        recent,
        recent[1:],
    ):

        if (
            int(current[0])
            - int(previous[0])
            != ONE_HOUR_MS
        ):
            raise RuntimeError(
                "gap"
            )

    if (
        int(recent[-1][0])
        != int(target_open_ms)
    ):
        raise RuntimeError(
            "target open"
        )

    expected_close = (
        int(target_open_ms)
        + ONE_HOUR_MS
        - 1
    )

    if (
        int(recent[-1][6])
        != expected_close
    ):
        raise RuntimeError(
            "target close"
        )


base = 1_790_000_000_000

candles = []

for i in range(60):

    open_ms = (
        base
        + i * ONE_HOUR_MS
    )

    close_ms = (
        open_ms
        + ONE_HOUR_MS
        - 1
    )

    candles.append(
        [
            open_ms,
            "1",
            "1",
            "1",
            "1",
            "1",
            close_ms,
        ]
    )


target = candles[-1][0]


# Good series
validate(
    candles,
    target,
)

print(
    "CONTINUOUS SERIES : PASS"
)


# Gap must fail
broken = [
    row[:]
    for row in candles
]

broken[30][0] += ONE_HOUR_MS

try:
    validate(
        broken,
        target,
    )

    raise RuntimeError(
        "GAP TEST DID NOT FAIL"
    )

except RuntimeError as exc:

    if str(exc) == "GAP TEST DID NOT FAIL":
        raise

print(
    "GAP FAIL-CLOSED   : PASS"
)


# Wrong target must fail
try:
    validate(
        candles,
        target - ONE_HOUR_MS,
    )

    raise RuntimeError(
        "TARGET TEST DID NOT FAIL"
    )

except RuntimeError as exc:

    if str(exc) == "TARGET TEST DID NOT FAIL":
        raise

print(
    "TARGET FAIL-CLOSED: PASS"
)


# Wrong close must fail
bad_close = [
    row[:]
    for row in candles
]

bad_close[-1][6] -= 1000

try:
    validate(
        bad_close,
        target,
    )

    raise RuntimeError(
        "CLOSE TEST DID NOT FAIL"
    )

except RuntimeError as exc:

    if str(exc) == "CLOSE TEST DID NOT FAIL":
        raise

print(
    "CLOSE FAIL-CLOSED : PASS"
)


print("")
print(
    "SYNTHETIC GUARDS  : PASS"
)
