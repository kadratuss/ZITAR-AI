from pathlib import Path

path = Path("zitar_market_intelligence_cycle_v1.py")
text = path.read_text(encoding="utf-8")

old = '''STAGES = [
    ("SELECTION_ENGINE", "zitar_selection_engine_v1.py"),'''

new = '''STAGES = [
    ("LIQUIDITY_OBSERVER", "zitar_liquidity_observer_v1.py"),
    ("SELECTION_ENGINE", "zitar_selection_engine_v1.py"),'''

if old not in text:
    raise SystemExit("STOP: STAGES anchor bulunamadi")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")

print("LIQUIDITY OBSERVER CYCLE PATCH PASS")
