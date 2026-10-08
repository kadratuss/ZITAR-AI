from pathlib import Path

P = Path("zitar_master_paper_engine_v1.py")

text = P.read_text(encoding="utf-8-sig")

old = '''    if len(positions) >= MAX_POSITIONS:
        return "MAX_POSITIONS"
'''

new = '''    max_positions = int(
        state.get(
            "rules",
            {}
        ).get(
            "max_spot_positions",
            state.get(
                "rules",
                {}
            ).get(
                "max_positions",
                MAX_POSITIONS
            )
        )
    )

    if len(positions) >= max_positions:
        return "MAX_POSITIONS"
'''

count = text.count(old)

if count != 1:
    raise SystemExit(
        f"FAIL: expected exactly 1 MAX_POSITIONS block, found {count}"
    )

text = text.replace(
    old,
    new,
    1
)

P.write_text(
    text,
    encoding="utf-8"
)

print("MASTER PAPER DYNAMIC LIMIT PATCH PASS")
print("replacements:", count)
