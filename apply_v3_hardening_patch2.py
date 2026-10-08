import ast
from pathlib import Path

RUNNER = Path(
    "multistrategy_live_runner_v3.py"
)

source = RUNNER.read_text(
    encoding="utf-8-sig"
)

tree = ast.parse(source)
lines = source.splitlines()


# ------------------------------------------------------------
# Locate fetch_history dynamically.
# No hard-coded line numbers.
# ------------------------------------------------------------

fetch = None

for node in tree.body:

    if (
        isinstance(node, ast.FunctionDef)
        and node.name == "fetch_history"
    ):
        fetch = node
        break


if fetch is None:
    raise RuntimeError(
        "fetch_history not found"
    )


old_function = "\n".join(
    lines[
        fetch.lineno - 1:
        fetch.end_lineno
    ]
)


# ------------------------------------------------------------
# Safety:
# Preserve existing function signature exactly.
# We insert validation immediately before every successful
# return of the existing fetch_history function.
#
# Therefore existing API/network/history logic remains intact.
# ------------------------------------------------------------

function_tree = ast.parse(
    old_function
)

fn = function_tree.body[0]


returns = [
    node
    for node in ast.walk(fn)
    if isinstance(node, ast.Return)
    and node.value is not None
]


if len(returns) != 1:
    raise RuntimeError(
        "Expected exactly one value-return "
        f"in fetch_history, found {len(returns)}"
    )


ret = returns[0]

return_line_index = (
    fetch.lineno
    + ret.lineno
    - 2
)


original_return = lines[
    return_line_index
]


indent = (
    original_return[
        :len(original_return)
        - len(original_return.lstrip())
    ]
)


validation = f'''
{indent}# --------------------------------------------------------
{indent}# HARDENING PATCH 2
{indent}# Closed 1h candle continuity + exact target validation
{indent}# --------------------------------------------------------

{indent}if len(closed) < 60:
{indent}    raise RuntimeError(
{indent}        f"{{symbol}}: insufficient closed candles: "
{indent}        f"{{len(closed)}}"
{indent}    )

{indent}# Only the final 60 candles used by the strategy are
{indent}# required here. Each adjacent open time must differ
{indent}# by exactly one hour.
{indent}recent = closed[-60:]

{indent}ONE_HOUR_MS = 60 * 60 * 1000

{indent}for previous, current in zip(
{indent}    recent,
{indent}    recent[1:],
{indent}):
{indent}    previous_open = int(previous[0])
{indent}    current_open = int(current[0])

{indent}    if (
{indent}        current_open
{indent}        - previous_open
{indent}        != ONE_HOUR_MS
{indent}    ):
{indent}        raise RuntimeError(
{indent}            f"{{symbol}}: candle gap detected: "
{indent}            f"{{previous_open}} -> "
{indent}            f"{{current_open}}"
{indent}        )

{indent}# Target candle must be the final candle in the
{indent}# validated strategy window.
{indent}last_open = int(recent[-1][0])

{indent}if last_open != int(target_open_ms):
{indent}    raise RuntimeError(
{indent}        f"{{symbol}}: target candle mismatch: "
{indent}        f"expected={{target_open_ms}} "
{indent}        f"actual={{last_open}}"
{indent}    )

{indent}# Binance 1h kline close time is normally
{indent}# open + 1h - 1 ms. Accept that exact convention.
{indent}last_close = int(recent[-1][6])

{indent}expected_close = (
{indent}    int(target_open_ms)
{indent}    + ONE_HOUR_MS
{indent}    - 1
{indent})

{indent}if last_close != expected_close:
{indent}    raise RuntimeError(
{indent}        f"{{symbol}}: target close mismatch: "
{indent}        f"expected={{expected_close}} "
{indent}        f"actual={{last_close}}"
{indent}    )
'''.strip("\n").splitlines()


lines[
    return_line_index:
    return_line_index
] = validation


patched = "\n".join(lines) + "\n"


# ------------------------------------------------------------
# Compile-level AST verification before writing.
# ------------------------------------------------------------

ast.parse(patched)


required_tokens = (
    "HARDENING PATCH 2",
    "candle gap detected",
    "target candle mismatch",
    "target close mismatch",
    "ONE_HOUR_MS",
)


for token in required_tokens:

    if token not in patched:
        raise RuntimeError(
            f"Patch token missing: {token}"
        )


RUNNER.write_text(
    patched,
    encoding="utf-8"
)


print("")
print("PATCH 2 INSERTED")
print(
    "TARGET FUNCTION : fetch_history"
)

print(
    "CONTINUITY      : 60 CLOSED 1H CANDLES"
)

print(
    "TARGET OPEN     : EXACT"
)

print(
    "TARGET CLOSE    : EXACT"
)
