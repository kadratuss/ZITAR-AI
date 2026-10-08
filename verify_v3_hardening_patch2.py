import ast
from pathlib import Path

p = Path(
    "multistrategy_live_runner_v3.py"
)

s = p.read_text(
    encoding="utf-8-sig"
)

ast.parse(s)


checks = {
    "Patch marker":
        "HARDENING PATCH 2" in s,

    "Gap guard":
        "candle gap detected" in s,

    "Target open guard":
        "target candle mismatch" in s,

    "Target close guard":
        "target close mismatch" in s,

    "1h interval":
        "ONE_HOUR_MS" in s,

    "Patch1 os.replace":
        "os.replace" in s,

    "Patch1 fsync":
        "os.fsync" in s,
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
    "PATCH 1 PRESERVED : PASS"
)

print(
    "PATCH 2 STATIC     : PASS"
)
