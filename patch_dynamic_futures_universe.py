from pathlib import Path

FILES = [
    Path("zitar_futures_intelligence_snapshot_v1_1.py"),
    Path("zitar_futures_temporal_intelligence_v1.py"),
]

OLD = 'SYMBOLS=["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT"]'
OLD_SPACED = 'SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT"]'

NEW = '''FUTURES_UNIVERSE = BASE / "zitar_futures_universe_v1.json"

def load_symbols():
    if not FUTURES_UNIVERSE.exists():
        raise FileNotFoundError(
            f"Futures universe bulunamadi: {FUTURES_UNIVERSE}"
        )

    data = json.loads(
        FUTURES_UNIVERSE.read_text(
            encoding="utf-8-sig"
        )
    )

    symbols = []

    for row in data.get("matched", []):
        symbol = row.get("futures_symbol")

        if symbol and symbol not in symbols:
            symbols.append(symbol)

    if not symbols:
        raise RuntimeError(
            "Futures universe icinde MATCHED sembol yok."
        )

    return symbols
'''

for path in FILES:

    text = path.read_text(encoding="utf-8-sig")

    if OLD in text:
        text = text.replace(OLD, NEW, 1)
    elif OLD_SPACED in text:
        text = text.replace(OLD_SPACED, NEW, 1)
    else:
        raise SystemExit(
            f"STOP: SYMBOLS sabit listesi bulunamadi: {path}"
        )

    # Her iki dosyada da main() basinda dinamik listeyi yukle.
    marker = "def main():"

    if marker not in text:
        raise SystemExit(
            f"STOP: main() bulunamadi: {path}"
        )

    text = text.replace(
        marker,
        marker + "\n    symbols = load_symbols()",
        1
    )

    # Sadece iteration kaynagini degistir.
    text = text.replace(
        "for symbol in SYMBOLS:",
        "for symbol in symbols:"
    )

    path.write_text(
        text,
        encoding="utf-8"
    )

    print("PATCH PASS:", path)

print("DYNAMIC FUTURES UNIVERSE PATCH COMPLETE")
