import ast
from pathlib import Path

s = Path(
    "multistrategy_live_runner_v3.py"
).read_text(
    encoding="utf-8-sig"
)

ast.parse(s)

checks = {
    "Patch1 replace":
        "os.replace" in s,

    "Patch1 fsync":
        "os.fsync" in s,

    "Patch2 gap":
        "candle gap detected" in s,

    "Patch2 target open":
        "target candle mismatch" in s,

    "Patch2 target close":
        "target close mismatch" in s,

    "Patch2B marker":
        "HARDENING PATCH 2B" in s,

    "Freeze source":
        '"created_at_utc"' in s,

    "Freeze violation":
        "Forward-only freeze violation" in s,
}


for name, ok in checks.items():

    print(
        f"{name:<24}:",
        "PASS" if ok else "FAIL"
    )


if not all(checks.values()):
    raise SystemExit(1)


print("")
print(
    "PATCH 1 PRESERVED  : PASS"
)
print(
    "PATCH 2 PRESERVED  : PASS"
)
print(
    "PATCH 2B STATIC     : PASS"
)
