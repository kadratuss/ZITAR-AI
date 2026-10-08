from pathlib import Path

P = Path("zitar_master_paper_engine_v1.py")

text = P.read_text(encoding="utf-8-sig")

old = '''def save(state: dict) -> None:

    state["last_updated_utc"] = now_utc()

    STATE.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )
'''

new = '''def save(state: dict) -> None:

    state["last_updated_utc"] = now_utc()

    payload = json.dumps(
        state,
        ensure_ascii=False,
        indent=2
    )

    temp = STATE.with_name(
        STATE.name + ".tmp"
    )

    temp.write_text(
        payload,
        encoding="utf-8"
    )

    # Atomic replacement:
    # tamamlanmamış JSON'un gerçek state olarak
    # kalma riskini azaltır.
    temp.replace(STATE)
'''

if old not in text:
    raise SystemExit(
        "FAIL: original save() block not found"
    )

text = text.replace(old, new, 1)

P.write_text(
    text,
    encoding="utf-8"
)

print("MASTER PAPER ENGINE ATOMIC SAVE PATCH PASS")
