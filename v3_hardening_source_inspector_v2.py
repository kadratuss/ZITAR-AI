import ast
import hashlib
import json
import re
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path.cwd()

RUNNER = ROOT / "multistrategy_live_runner_v3.py"
OUT_JSON = ROOT / "v3_hardening_source_inspector_v2.json"
OUT_TXT = ROOT / "v3_hardening_source_inspector_v2.txt"


if not RUNNER.exists():
    raise RuntimeError(
        "multistrategy_live_runner_v3.py missing"
    )


source = RUNNER.read_text(
    encoding="utf-8-sig"
)

lines = source.splitlines()

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


def snippet(start, end):
    start = max(1, start)
    end = min(len(lines), end)

    return "\n".join(
        f"{i:04d}: {lines[i - 1]}"
        for i in range(start, end + 1)
    )


# ------------------------------------------------------------
# Function inventory with complete source ranges
# ------------------------------------------------------------

functions = []

for node in ast.walk(tree):

    if isinstance(
        node,
        (
            ast.FunctionDef,
            ast.AsyncFunctionDef
        )
    ):

        functions.append({
            "name":
                node.name,

            "start_line":
                node.lineno,

            "end_line":
                getattr(
                    node,
                    "end_lineno",
                    node.lineno
                ),

            "source":
                snippet(
                    node.lineno,
                    getattr(
                        node,
                        "end_lineno",
                        node.lineno
                    )
                ),
        })


functions.sort(
    key=lambda x: x["start_line"]
)


# ------------------------------------------------------------
# Search exact implementation-sensitive patterns
# ------------------------------------------------------------

PATTERNS = {
    "append_write": [
        r"""open\s*\([^)]*,\s*["']a["']""",
        r"""mode\s*=\s*["']a["']""",
        r"""csv\.writer""",
        r"""csv\.DictWriter""",
        r"""append_unique""",
    ],

    "atomic_write": [
        r"os\.replace",
        r"os\.fsync",
        r"\.flush\(",
        r"atomic_json",
        r"atomic_",
    ],

    "journal": [
        r"journal",
        r"PREPARED",
        r"COMMITTED",
        r"rollback",
        r"recover",
    ],

    "state_commit": [
        r"STATE",
        r"state",
        r"save_state",
        r"write_state",
        r"atomic_json",
    ],

    "peak_drawdown": [
        r"peak",
        r"drawdown",
        r"equity",
    ],

    "data_freshness": [
        r"stale",
        r"age",
        r"max_age",
        r"data_age",
        r"fresh",
    ],

    "candle_integrity": [
        r"gap",
        r"missing",
        r"interval",
        r"open_time",
        r"close_time",
        r"closed",
    ],

    "freeze": [
        r"freeze",
        r"frozen",
        r"forward",
        r"manifest",
        r"start",
    ],

    "universe": [
        r"UNIVERSE",
        r"symbols",
        r"symbol",
        r"manifest",
    ],

    "book": [
        r"bookTicker",
        r"bidPrice",
        r"askPrice",
        r"book",
    ],

    "risk": [
        r"max_positions",
        r"daily",
        r"loss",
        r"risk",
        r"invested",
        r"drawdown",
    ],
}


matches = {}

for group, patterns in PATTERNS.items():

    group_matches = []

    for line_no, line in enumerate(
        lines,
        start=1
    ):

        for pattern in patterns:

            if re.search(
                pattern,
                line,
                re.IGNORECASE
            ):

                group_matches.append({
                    "line":
                        line_no,

                    "pattern":
                        pattern,

                    "text":
                        line.strip(),
                })

                break

    matches[group] = group_matches


# ------------------------------------------------------------
# Assignment inventory
# Useful for universe/config/risk constants.
# ------------------------------------------------------------

assignments = []

for node in ast.walk(tree):

    if isinstance(
        node,
        (
            ast.Assign,
            ast.AnnAssign
        )
    ):

        try:
            text = ast.get_source_segment(
                source,
                node
            )
        except Exception:
            text = None

        if text:

            low = text.lower()

            if any(
                token in low
                for token in (
                    "symbol",
                    "universe",
                    "manifest",
                    "risk",
                    "max_",
                    "fee",
                    "slip",
                    "order_budget",
                    "peak",
                    "state",
                    "journal",
                )
            ):

                assignments.append({
                    "line":
                        node.lineno,

                    "source":
                        text,
                })


assignments.sort(
    key=lambda x: x["line"]
)


# ------------------------------------------------------------
# Identify functions relevant to hardening
# ------------------------------------------------------------

keywords = (
    "append",
    "atomic",
    "journal",
    "recover",
    "state",
    "peak",
    "risk",
    "book",
    "candle",
    "kline",
    "signal",
    "trade",
    "commit",
    "run",
)


relevant_functions = []

for fn in functions:

    low = (
        fn["name"]
        + "\n"
        + fn["source"]
    ).lower()

    if any(
        word in low
        for word in keywords
    ):
        relevant_functions.append(fn)


result = {
    "inspector_version":
        "v3_hardening_source_inspector_v2",

    "generated_at_utc":
        datetime.now(
            timezone.utc
        ).isoformat(),

    "runner":
        RUNNER.name,

    "runner_sha256":
        sha256_file(RUNNER),

    "source_lines":
        len(lines),

    "functions":
        functions,

    "relevant_functions":
        relevant_functions,

    "pattern_matches":
        matches,

    "important_assignments":
        assignments,

    "read_only":
        True,
}


OUT_JSON.write_text(
    json.dumps(
        result,
        indent=2,
        ensure_ascii=False
    ),
    encoding="utf-8"
)


# ------------------------------------------------------------
# Human-readable report
# ------------------------------------------------------------

report = []

report.append(
    "=" * 78
)

report.append(
    "PORTFOLIOAI V3 HARDENING SOURCE INSPECTOR V2"
)

report.append(
    "=" * 78
)

report.append(
    f"RUNNER SHA256 : {result['runner_sha256']}"
)

report.append(
    f"SOURCE LINES  : {result['source_lines']}"
)

report.append(
    f"FUNCTIONS     : {len(functions)}"
)

report.append("")


report.append(
    "=" * 78
)

report.append(
    "FUNCTION INVENTORY"
)

report.append(
    "=" * 78
)

for fn in functions:

    report.append(
        f"{fn['start_line']:04d}-"
        f"{fn['end_line']:04d}  "
        f"{fn['name']}"
    )


report.append("")
report.append(
    "=" * 78
)

report.append(
    "IMPORTANT ASSIGNMENTS"
)

report.append(
    "=" * 78
)

for item in assignments:

    report.append(
        f"\nLINE {item['line']}"
    )

    report.append(
        item["source"]
    )


report.append("")
report.append(
    "=" * 78
)

report.append(
    "PATTERN MATCHES"
)

report.append(
    "=" * 78
)


for group, group_matches in matches.items():

    report.append("")
    report.append(
        f"[{group.upper()}]"
    )

    if not group_matches:

        report.append(
            "  NONE"
        )

        continue

    for match in group_matches:

        report.append(
            f"  L{match['line']:04d}: "
            f"{match['text']}"
        )


report.append("")
report.append(
    "=" * 78
)

report.append(
    "RELEVANT FUNCTION SOURCE"
)

report.append(
    "=" * 78
)


for fn in relevant_functions:

    report.append("")

    report.append(
        "-" * 78
    )

    report.append(
        f"FUNCTION {fn['name']} "
        f"[{fn['start_line']}-"
        f"{fn['end_line']}]"
    )

    report.append(
        "-" * 78
    )

    report.append(
        fn["source"]
    )


report.append("")
report.append(
    "=" * 78
)

report.append(
    "INSPECTION COMPLETE"
)

report.append(
    "RUNNER MODIFIED : NO"
)

report.append(
    "STATE MODIFIED  : NO"
)

report.append(
    "TRADE WRITE     : NO"
)

report.append(
    "REAL ORDER      : NO"
)

report.append(
    "=" * 78
)


OUT_TXT.write_text(
    "\n".join(report),
    encoding="utf-8"
)


print("")
print("=" * 78)
print("V3 HARDENING SOURCE INSPECTOR V2")
print("=" * 78)

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
    len(functions)
)

print(
    "RELEVANT FNS  :",
    len(relevant_functions)
)


print("")
print("FUNCTION INVENTORY")

for fn in functions:

    print(
        f"  {fn['start_line']:04d}-"
        f"{fn['end_line']:04d}",
        fn["name"]
    )


print("")
print("MATCH COUNTS")

for group, group_matches in matches.items():

    print(
        f"  {group:<20}:",
        len(group_matches)
    )


print("")
print("=" * 78)
print("SOURCE INSPECTION : PASS")
print("RUNNER MODIFIED   : NO")
print("STATE MODIFIED    : NO")
print("TRADE WRITE       : NO")
print("REAL ORDER        : NO")
print("=" * 78)
