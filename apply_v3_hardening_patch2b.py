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
# Locate main() dynamically.
# ------------------------------------------------------------

main = None

for node in tree.body:

    if (
        isinstance(node, ast.FunctionDef)
        and node.name == "main"
    ):
        main = node
        break


if main is None:
    raise RuntimeError(
        "main() not found"
    )


# ------------------------------------------------------------
# We need the state load statement inside main.
#
# Find assignment containing load_state(...)
# and insert freeze derivation immediately after it.
# ------------------------------------------------------------

state_load_node = None
state_variable = None

for node in ast.walk(main):

    if isinstance(
        node,
        (
            ast.Assign,
            ast.AnnAssign,
        )
    ):

        value = (
            node.value
            if hasattr(node, "value")
            else None
        )

        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "load_state"
        ):

            state_load_node = node

            if isinstance(node, ast.Assign):
                if (
                    len(node.targets) == 1
                    and isinstance(
                        node.targets[0],
                        ast.Name
                    )
                ):
                    state_variable = (
                        node.targets[0].id
                    )

            elif isinstance(
                node,
                ast.AnnAssign
            ):
                if isinstance(
                    node.target,
                    ast.Name
                ):
                    state_variable = (
                        node.target.id
                    )

            break


if (
    state_load_node is None
    or state_variable is None
):
    raise RuntimeError(
        "Could not locate state = load_state(...)"
    )


insert_after = (
    state_load_node.end_lineno
)


state_line = lines[
    state_load_node.lineno - 1
]

indent = (
    state_line[
        :len(state_line)
        - len(state_line.lstrip())
    ]
)


freeze_block = f'''
{indent}# --------------------------------------------------------
{indent}# HARDENING PATCH 2B
{indent}# Forward-only freeze boundary.
{indent}# The experiment's immutable creation timestamp is the
{indent}# earliest permitted prospective boundary.
{indent}# --------------------------------------------------------

{indent}freeze_raw = {state_variable}.get(
{indent}    "created_at_utc"
{indent})

{indent}if not freeze_raw:
{indent}    raise RuntimeError(
{indent}        "Forward freeze boundary missing: "
{indent}        "created_at_utc"
{indent}    )

{indent}freeze_dt = datetime.fromisoformat(
{indent}    str(freeze_raw).replace(
{indent}        "Z",
{indent}        "+00:00",
{indent}    )
{indent})

{indent}if freeze_dt.tzinfo is None:
{indent}    raise RuntimeError(
{indent}        "Forward freeze boundary must "
{indent}        "be timezone-aware"
{indent}    )
'''.strip("\n").splitlines()


lines[
    insert_after:
    insert_after
] = freeze_block


patched = "\n".join(lines) + "\n"


# ------------------------------------------------------------
# Now locate main again in patched source.
# Find target_close assignment/use.
#
# We insert the actual comparison immediately after the
# target candle timestamps have been established.
# ------------------------------------------------------------

patched_tree = ast.parse(patched)
patched_lines = patched.splitlines()

patched_main = next(
    node
    for node in patched_tree.body
    if (
        isinstance(node, ast.FunctionDef)
        and node.name == "main"
    )
)


target_node = None
target_name = None

preferred = (
    "target_close_dt",
    "target_close_utc",
    "candle_close_dt",
    "candle_close_utc",
    "target_close",
)


assignments = []

for node in ast.walk(patched_main):

    if isinstance(node, ast.Assign):

        for target in node.targets:

            if isinstance(target, ast.Name):

                assignments.append(
                    (
                        target.id,
                        node,
                    )
                )


for preferred_name in preferred:

    for name, node in assignments:

        if name == preferred_name:
            target_name = name
            target_node = node
            break

    if target_node is not None:
        break


if target_node is None:

    # Conservative fallback:
    # assignment name containing both target/candle and close.
    for name, node in assignments:

        low = name.lower()

        if (
            "close" in low
            and (
                "target" in low
                or "candle" in low
            )
        ):
            target_name = name
            target_node = node
            break


if target_node is None:
    raise RuntimeError(
        "Could not locate target candle close variable"
    )


target_line = patched_lines[
    target_node.lineno - 1
]

target_indent = (
    target_line[
        :len(target_line)
        - len(target_line.lstrip())
    ]
)


guard = f'''
{target_indent}# HARDENING PATCH 2B - FREEZE ENFORCEMENT
{target_indent}freeze_compare = {target_name}

{target_indent}if isinstance(
{target_indent}    freeze_compare,
{target_indent}    str,
{target_indent}):
{target_indent}    freeze_compare = datetime.fromisoformat(
{target_indent}        freeze_compare.replace(
{target_indent}            "Z",
{target_indent}            "+00:00",
{target_indent}        )
{target_indent}    )

{target_indent}if not isinstance(
{target_indent}    freeze_compare,
{target_indent}    datetime,
{target_indent}):
{target_indent}    raise RuntimeError(
{target_indent}        "Target candle close is not datetime"
{target_indent}    )

{target_indent}if freeze_compare.tzinfo is None:
{target_indent}    raise RuntimeError(
{target_indent}        "Target candle close must "
{target_indent}        "be timezone-aware"
{target_indent}    )

{target_indent}if freeze_compare <= freeze_dt:
{target_indent}    raise RuntimeError(
{target_indent}        "Forward-only freeze violation: "
{target_indent}        f"target_close={{freeze_compare.isoformat()}} "
{target_indent}        f"freeze={{freeze_dt.isoformat()}}"
{target_indent}    )
'''.strip("\n").splitlines()


patched_lines[
    target_node.end_lineno:
    target_node.end_lineno
] = guard


final_source = (
    "\n".join(patched_lines)
    + "\n"
)


# Parse BEFORE replacing runner.
ast.parse(final_source)


required = (
    "HARDENING PATCH 2B",
    "Forward-only freeze violation",
    "created_at_utc",
    "freeze_dt",
)


for token in required:

    if token not in final_source:
        raise RuntimeError(
            f"Missing patch token: {token}"
        )


RUNNER.write_text(
    final_source,
    encoding="utf-8",
)


print("")
print("PATCH 2B INSERTED")
print(
    "FREEZE SOURCE : state.created_at_utc"
)
print(
    "POLICY        : target close > freeze"
)
