from pathlib import Path

p = Path("zitar_master_realized_sync_test_v1.py")

text = p.read_text(
    encoding="utf-8-sig"
)

start_marker = '''    equity = D(
        account["equity_try"]
    )

    start_equity = D(
        period["start_equity_try"]
    )
'''

end_marker = '''    master_hash_after = file_hash(MASTER)
'''

start = text.find(start_marker)
end = text.find(end_marker)

if start == -1:
    raise SystemExit(
        "FAIL: manual sync start block not found"
    )

if end == -1:
    raise SystemExit(
        "FAIL: manual sync end block not found"
    )

replacement = '''    # Engine BUY/SELL işlemleri tamamlandı.
    # Bundan sonra period/equity değerlerine
    # test tarafından hiçbir müdahale yapılmaz.
    #
    # Amaç: Master period sync'in tamamen
    # engine tarafından üretildiğini doğrulamak.

    equity = D(
        account["equity_try"]
    )

'''

text = (
    text[:start]
    + replacement
    + text[end:]
)

p.write_text(
    text,
    encoding="utf-8"
)

print(
    "MASTER REALIZED AUTO-SYNC TEST PATCH PASS"
)
