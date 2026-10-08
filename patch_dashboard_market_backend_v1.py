from pathlib import Path

p = Path("zitar_dashboard_api_v1.py")
s = p.read_text(encoding="utf-8-sig")

old = '''FINANCE_BRIDGE = BASE / "zitar_finance_unified_bridge_v1_1.json"'''

new = '''FINANCE_BRIDGE = BASE / "zitar_finance_unified_bridge_v1_1.json"

# MARKET INTELLIGENCE V1
MARKET_CYCLE = BASE / "zitar_market_intelligence_cycle_v1.json"
SELECTION_ENGINE = BASE / "zitar_selection_engine_v1.json"
FUTURES_UNIVERSE = BASE / "zitar_futures_universe_v1.json"
FUTURES_EVIDENCE = BASE / "zitar_futures_evidence_v1.json"
FUTURES_SNAPSHOT = BASE / "zitar_futures_intelligence_snapshot_v1_1.json"'''

if old not in s:
    raise SystemExit("STOP: FINANCE_BRIDGE SATIRI BULUNAMADI")

s = s.replace(old, new, 1)

old = '''    finance = read_json(FINANCE_BRIDGE) or {}'''

new = '''    finance = read_json(FINANCE_BRIDGE) or {}

    # MARKET INTELLIGENCE
    market_cycle = read_json(MARKET_CYCLE) or {}
    selection = read_json(SELECTION_ENGINE) or {}
    futures_universe = read_json(FUTURES_UNIVERSE) or {}
    futures_evidence = read_json(FUTURES_EVIDENCE) or {}
    futures_snapshot = read_json(FUTURES_SNAPSHOT) or {}'''

if old not in s:
    raise SystemExit("STOP: FINANCE READ SATIRI BULUNAMADI")

s = s.replace(old, new, 1)

old = '''        "trading": {
            "mode": "PAPER_TRADING",
            "real_order_authority": False,
        },'''

new = '''        "market_intelligence": {
            "status": market_cycle.get(
                "status",
                "UNKNOWN"
            ),
            "selection_mode": market_cycle.get(
                "selection_mode",
                selection.get("mode", "UNKNOWN")
            ),
            "selection_candidates": market_cycle.get(
                "selection_candidates",
                len(selection.get("analysis_candidates", []))
            ),
            "selection_rejected": market_cycle.get(
                "selection_rejected",
                len(selection.get("rejected", []))
            ),
            "futures_matched": market_cycle.get(
                "futures_matched",
                len(futures_universe.get("matched", []))
            ),
            "futures_unmatched": market_cycle.get(
                "futures_unmatched",
                len(futures_universe.get("unmatched", []))
            ),
            "snapshot_symbols": market_cycle.get(
                "snapshot_symbols",
                len(futures_snapshot.get("symbols", []))
            ),
            "snapshot_complete": market_cycle.get(
                "snapshot_complete",
                sum(
                    1 for x in futures_snapshot.get("symbols", [])
                    if x.get("status") == "OK"
                )
            ),
            "active_evidence_symbols": market_cycle.get(
                "active_evidence_symbols",
                sum(
                    1 for x in futures_evidence.get("symbols", [])
                    if x.get("universe_status") == "ACTIVE"
                )
            ),
            "observable_active_symbols": market_cycle.get(
                "observable_active_symbols",
                sum(
                    1 for x in futures_evidence.get("symbols", [])
                    if x.get("universe_status") == "ACTIVE"
                    and x.get("temporal", {}).get("status") == "OBSERVABLE"
                )
            ),
            "historical_only_symbols": market_cycle.get(
                "historical_only_symbols",
                sum(
                    1 for x in futures_evidence.get("symbols", [])
                    if x.get("universe_status") == "HISTORICAL_ONLY"
                )
            ),
        },
        "trading": {
            "mode": "PAPER_TRADING",
            "real_order_authority": False,
        },'''

if old not in s:
    raise SystemExit("STOP: TRADING BLOKU BULUNAMADI")

s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")

print("DASHBOARD MARKET BACKEND PATCH PASS")
