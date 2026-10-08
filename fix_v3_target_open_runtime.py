import ast
from pathlib import Path

path = Path(
    "multistrategy_live_runner_v3.py"
)

src = path.read_text(
    encoding="utf-8-sig"
)

tree = ast.parse(src)

fetch = None

for node in tree.body:

    if (
        isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node.name == "fetch_history"
    ):
        fetch = node
        break


if fetch is None:
    raise RuntimeError(
        "fetch_history not found"
    )


params = [
    a.arg
    for a in fetch.args.args
]

print(
    "fetch_history params:",
    params
)

if "target_open" not in params:
    raise RuntimeError(
        "target_open parameter not found"
    )


segment = ast.get_source_segment(
    src,
    fetch
)

if segment is None:
    raise RuntimeError(
        "Could not extract fetch_history"
    )


bad_count = segment.count(
    "target_open_ms"
)

print(
    "target_open_ms inside fetch_history:",
    bad_count
)


if bad_count == 0:
    raise RuntimeError(
        "Expected runtime bug not found"
    )


# Only patch fetch_history.
fixed_segment = segment.replace(
    "target_open_ms",
    "target_open"
)


# Verify bad identifier disappeared
# specifically from this function.
if "target_open_ms" in fixed_segment:
    raise RuntimeError(
        "target_open_ms remains in fetch_history"
    )


new_src = src.replace(
    segment,
    fixed_segment,
    1,
)


# Parse complete resulting runner before writing.
ast.parse(
    new_src
)


path.write_text(
    new_src,
    encoding="utf-8"
)


# Re-read and AST verify.
verify_src = path.read_text(
    encoding="utf-8"
)

verify_tree = ast.parse(
    verify_src
)

for node in verify_tree.body:

    if (
        isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node.name == "fetch_history"
    ):

        names = {
            n.id
            for n in ast.walk(node)
            if isinstance(
                n,
                ast.Name
            )
        }

        if "target_open_ms" in names:
            raise RuntimeError(
                "Undefined target_open_ms still present"
            )

        if "target_open" not in names:
            raise RuntimeError(
                "target_open missing after patch"
            )

        print(
            "FETCH_HISTORY RUNTIME FIX : PASS"
        )

        break

else:
    raise RuntimeError(
        "fetch_history missing after patch"
    )
