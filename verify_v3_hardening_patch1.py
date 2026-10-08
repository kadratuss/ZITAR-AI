import ast
from pathlib import Path

p = Path("multistrategy_live_runner_v3.py")

s = p.read_text(
    encoding="utf-8-sig"
)

ast.parse(s)

checks = {
    "os.replace":
        "os.replace" in s,

    "os.fsync":
        "os.fsync" in s,

    "CSV temp write":
        'path.name + ".tmp"' in s,

    "CSV schema guard":
        "CSV schema mismatch" in s,

    "direct append removed":
        'path.open(\n        "a",' not in s,
}

for name, ok in checks.items():
    print(
        f"{name:<24}:",
        "PASS" if ok else "FAIL"
    )

if not all(checks.values()):
    raise SystemExit(1)

print("")
print("STATIC HARDENING CHECK : PASS")
