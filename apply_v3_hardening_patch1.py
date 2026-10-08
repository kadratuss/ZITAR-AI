import ast
from pathlib import Path

path = Path("multistrategy_live_runner_v3.py")

source = path.read_text(
    encoding="utf-8-sig"
)

tree = ast.parse(source)
lines = source.splitlines()


targets = {}

for node in tree.body:

    if isinstance(
        node,
        (
            ast.FunctionDef,
            ast.AsyncFunctionDef
        )
    ):

        if node.name in {
            "atomic_json",
            "append_unique",
        }:

            targets[node.name] = (
                node.lineno,
                node.end_lineno,
            )


required = {
    "atomic_json",
    "append_unique",
}

if set(targets) != required:
    raise RuntimeError(
        f"Expected functions not found: {targets}"
    )


new_atomic_json = r'''def atomic_json(path, obj):
    path = Path(path)

    tmp = path.with_name(
        path.name + ".tmp"
    )

    payload = json.dumps(
        obj,
        indent=2,
        ensure_ascii=False,
    )

    with tmp.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp, path)

    # Best-effort directory durability.
    # Windows may not permit directory fsync.
    if os.name != "nt":
        dir_fd = os.open(
            str(path.parent),
            os.O_RDONLY,
        )

        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)'''


new_append_unique = r'''def append_unique(path, fields, rows, id_field):
    if not rows:
        return

    path = Path(path)

    existing_rows = []
    ids = set()

    if path.exists() and path.stat().st_size > 0:
        with path.open(
            "r",
            newline="",
            encoding="utf-8",
        ) as f:

            reader = csv.DictReader(f)

            if reader.fieldnames != fields:
                raise RuntimeError(
                    f"CSV schema mismatch: {path.name}"
                )

            for row in reader:
                existing_rows.append(row)

                value = row.get(id_field)

                if value:
                    ids.add(value)

    new_rows = [
        row
        for row in rows
        if row[id_field] not in ids
    ]

    if not new_rows:
        return

    tmp = path.with_name(
        path.name + ".tmp"
    )

    with tmp.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )

        writer.writeheader()

        for row in existing_rows:
            writer.writerow(row)

        for row in new_rows:
            writer.writerow(row)

        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp, path)

    # Best-effort directory durability.
    if os.name != "nt":
        dir_fd = os.open(
            str(path.parent),
            os.O_RDONLY,
        )

        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)'''


replacements = {
    "atomic_json":
        new_atomic_json.splitlines(),

    "append_unique":
        new_append_unique.splitlines(),
}


# Replace from bottom upward so line numbers remain valid.
for name, (start, end) in sorted(
    targets.items(),
    key=lambda item: item[1][0],
    reverse=True,
):

    lines[
        start - 1:end
    ] = replacements[name]


new_source = "\n".join(lines) + "\n"

# Parse before touching original file.
ast.parse(new_source)

path.write_text(
    new_source,
    encoding="utf-8",
)

print("PATCHED FUNCTIONS:")
print(" atomic_json")
print(" append_unique")
