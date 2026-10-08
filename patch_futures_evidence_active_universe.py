from pathlib import Path

p = Path("zitar_futures_evidence_v1.py")
txt = p.read_text(encoding="utf-8-sig")

old1 = '''LOG = BASE / "zitar_futures_intelligence_observations_v1.jsonl"
OUT = BASE / "zitar_futures_evidence_v1.json"
'''

new1 = '''LOG = BASE / "zitar_futures_intelligence_observations_v1.jsonl"
OUT = BASE / "zitar_futures_evidence_v1.json"
UNIVERSE = BASE / "zitar_futures_universe_v1.json"
'''

if old1 not in txt:
    raise SystemExit("STOP: PATH BLOKU BULUNAMADI")

txt = txt.replace(old1, new1, 1)

old2 = '''def finite(v):
'''

new2 = '''def load_active_universe():
    if not UNIVERSE.exists():
        return set()

    try:
        data = json.loads(
            UNIVERSE.read_text(encoding="utf-8-sig")
        )
    except Exception:
        return set()

    return {
        x.get("futures_symbol")
        for x in data.get("matched", [])
        if x.get("futures_symbol")
    }

def finite(v):
'''

if old2 not in txt:
    raise SystemExit("STOP: finite() MARKER BULUNAMADI")

txt = txt.replace(old2, new2, 1)

old3 = '''def main():
    history=load()
    by={}
'''

new3 = '''def main():
    history=load()
    active_universe=load_active_universe()
    by={}
'''

if old3 not in txt:
    raise SystemExit("STOP: main() BLOKU BULUNAMADI")

txt = txt.replace(old3, new3, 1)

old4 = '''        "symbols":[]
    }
'''

new4 = '''        "active_universe_source":UNIVERSE.name,
        "active_universe_count":len(active_universe),
        "historical_symbol_count":len(by),
        "symbols":[]
    }
'''

if old4 not in txt:
    raise SystemExit("STOP: REPORT BLOKU BULUNAMADI")

txt = txt.replace(old4, new4, 1)

old5 = '''        report["symbols"].append({
            "symbol":sym,
'''

new5 = '''        report["symbols"].append({
            "symbol":sym,
            "active":sym in active_universe,
            "universe_status":"ACTIVE" if sym in active_universe else "HISTORICAL_ONLY",
'''

if old5 not in txt:
    raise SystemExit("STOP: SYMBOL OUTPUT BLOKU BULUNAMADI")

txt = txt.replace(old5, new5, 1)

old6 = '''    print("symbols:",len(report["symbols"]))
    print("minimum temporal observations:",MIN_OBS_FOR_TEMPORAL)
'''

new6 = '''    print("historical symbols:",len(report["symbols"]))
    print("active universe:",len(active_universe))
    print("historical only:",
          sum(not x["active"] for x in report["symbols"]))
    print("minimum temporal observations:",MIN_OBS_FOR_TEMPORAL)
'''

if old6 not in txt:
    raise SystemExit("STOP: PRINT BLOKU BULUNAMADI")

txt = txt.replace(old6, new6, 1)

old7 = '''        print(f"{x['symbol']:10} obs={x['temporal']['observations']} "
              f"temporal={x['temporal']['status']} agreement={x['agreement']} "
              f"conclusion={x['conclusion']}")
'''

new7 = '''        print(f"{x['symbol']:12} "
              f"{x['universe_status']:15} "
              f"obs={x['temporal']['observations']} "
              f"temporal={x['temporal']['status']} "
              f"agreement={x['agreement']} "
              f"conclusion={x['conclusion']}")
'''

if old7 not in txt:
    raise SystemExit("STOP: DETAIL PRINT BLOKU BULUNAMADI")

txt = txt.replace(old7, new7, 1)

p.write_text(txt, encoding="utf-8")

print("EVIDENCE ACTIVE UNIVERSE PATCH PASS")
