from pathlib import Path

p = Path("zitar_dashboard_api_v1.py")
s = p.read_text(encoding="utf-8-sig")

old = '''    market_cycle = read_json(MARKET_CYCLE) or {}
    selection = read_json(SELECTION_ENGINE) or {}
'''

new = '''    market_cycle = read_json(MARKET_CYCLE) or {}
    market_summary = market_cycle.get("summary", {})
    selection = read_json(SELECTION_ENGINE) or {}
'''

if old not in s:
    raise SystemExit("STOP: MARKET CYCLE READ BLOKU BULUNAMADI")

s = s.replace(old, new, 1)

# Cycle özet değerleri summary altında.
# Dashboard'daki market_cycle.get(...) çağrılarını market_summary.get(...) yap.
keys = [
    "selection_mode",
    "selection_candidates",
    "selection_rejected",
    "futures_matched",
    "futures_unmatched",
    "snapshot_symbols",
    "snapshot_complete",
    "active_evidence_symbols",
    "observable_active_symbols",
    "historical_only_symbols",
]

for key in keys:
    s = s.replace(
        f'market_cycle.get(\n                "{key}",',
        f'market_summary.get(\n                "{key}",'
    )

p.write_text(s, encoding="utf-8")

print("DASHBOARD MARKET SUMMARY PATCH PASS")
