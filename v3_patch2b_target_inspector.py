import ast
import hashlib
from pathlib import Path

P = Path(
    "multistrategy_live_runner_v3.py"
)

EXPECTED = (
    "4BCBB202C29FC1B3ADC5DAFDDB85E96C8"
    "BAF98CE2BE69257BBBEE7782F74B142"
)


def sha256(path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest().upper()


before = sha256(P)

print(
    "RUNNER HASH:",
    before
)

if before != EXPECTED:
    raise RuntimeError(
        "Unexpected runner version"
    )


source = P.read_text(
    encoding="utf-8-sig"
)

lines = source.splitlines()

tree = ast.parse(source)


main = next(
    (
        node
        for node in tree.body
        if isinstance(
            node,
            ast.FunctionDef
        )
        and node.name == "main"
    ),
    None,
)

if main is None:
    raise RuntimeError(
        "main() not found"
    )


print("")
print(
    "MAIN RANGE:",
    main.lineno,
    "-",
    main.end_lineno,
)


# ------------------------------------------------------------
# Print relevant main() source lines.
# We want exact state / target / candle / processed structure.
# ------------------------------------------------------------

keywords = (
    "state",
    "target",
    "candle",
    "processed",
    "created_at",
    "close_dt",
    "close_utc",
    "open_ms",
    "close_ms",
    "load",
)


hits = set()

for lineno in range(
    main.lineno,
    main.end_lineno + 1,
):

    text = lines[
        lineno - 1
    ]

    low = text.lower()

    if any(
        key in low
        for key in keywords
    ):
        # Include surrounding context.
        for n in range(
            max(main.lineno, lineno - 3),
            min(main.end_lineno, lineno + 3)
            + 1,
        ):
            hits.add(n)


print("")
print(
    "=== RELEVANT MAIN SOURCE ==="
)

last = None

for n in sorted(hits):

    if (
        last is not None
        and n > last + 1
    ):
        print(
            "..."
        )

    print(
        f"{n:04d}: "
        + lines[n - 1]
    )

    last = n


# ------------------------------------------------------------
# AST inventory of calls and assignments in main.
# ------------------------------------------------------------

print("")
print(
    "=== ASSIGNMENTS ==="
)

for node in ast.walk(main):

    if isinstance(
        node,
        (
            ast.Assign,
            ast.AnnAssign,
        )
    ):

        try:
            snippet = ast.get_source_segment(
                source,
                node,
            )
        except Exception:
            snippet = None

        if not snippet:
            continue

        low = snippet.lower()

        if any(
            key in low
            for key in keywords
        ):
            print(
                f"L{node.lineno}-"
                f"{node.end_lineno}: "
                + snippet.replace(
                    "\n",
                    " ",
                )
            )


print("")
print(
    "=== CALLS ==="
)

seen = set()

for node in ast.walk(main):

    if not isinstance(
        node,
        ast.Call,
    ):
        continue

    try:
        call = ast.get_source_segment(
            source,
            node,
        )
    except Exception:
        call = None

    if not call:
        continue

    compact = " ".join(
        call.split()
    )

    low = compact.lower()

    if any(
        key in low
        for key in (
            "state",
            "json",
            "load",
            "candle",
            "target",
        )
    ):

        item = (
            node.lineno,
            node.end_lineno,
            compact,
        )

        if item not in seen:
            seen.add(item)

            print(
                f"L{node.lineno}-"
                f"{node.end_lineno}: "
                f"{compact}"
            )


after = sha256(P)

print("")
print(
    "RUNNER AFTER:",
    after
)

if before != after:
    raise RuntimeError(
        "INSPECTOR MODIFIED RUNNER"
    )


print("")
print(
    "RUNNER IMMUTABLE : PASS"
)
print(
    "RUNNER EXECUTED  : NO"
)
print(
    "STATE WRITE      : NO"
)
print(
    "TRADE WRITE      : NO"
)
print(
    "REAL ORDER       : NO"
)
print(
    "============================================================"
)
