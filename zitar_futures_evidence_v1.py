from __future__ import annotations
import json, math, statistics
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG = BASE / "zitar_futures_intelligence_observations_v1.jsonl"
OUT = BASE / "zitar_futures_evidence_v1.json"
UNIVERSE = BASE / "zitar_futures_universe_v1.json"

MIN_OBS_FOR_TEMPORAL = 6

def load():
    rows=[]
    if not LOG.exists():
        return rows
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try: rows.append(json.loads(line))
            except: pass
    return rows

def load_active_universe():
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
    return isinstance(v,(int,float)) and math.isfinite(v)

def delta(a,b):
    return (b-a) if finite(a) and finite(b) else None

def sign_label(v, eps=1e-12):
    if not finite(v): return "UNKNOWN"
    if v > eps: return "POSITIVE"
    if v < -eps: return "NEGATIVE"
    return "NEUTRAL"

def ratio_label(v):
    if not finite(v): return "UNKNOWN"
    if v > 1: return "ABOVE_1"
    if v < 1: return "BELOW_1"
    return "AT_1"

def main():
    history=load()
    active_universe=load_active_universe()
    by={}
    for rec in history:
        ts=rec.get("observed_utc")
        for x in rec.get("symbols",[]):
            y=dict(x); y["_observed_utc"]=ts
            by.setdefault(x.get("symbol"),[]).append(y)

    report={
        "schema":"ZITAR_FUTURES_EVIDENCE_V1",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "source_log":LOG.name,
        "observation_count":len(history),
        "raw_observation_count":len(history),
        "temporal_counting_policy":"UNIQUE_UTC_HOUR_LAST_OBSERVATION",
        "mode":"EVIDENCE_ONLY",
        "execution_authority":False,
        "directional_signal":False,
        "minimum_observations_for_temporal_assessment":MIN_OBS_FOR_TEMPORAL,
        "active_universe_source":UNIVERSE.name,
        "active_universe_count":len(active_universe),
        "historical_symbol_count":len(by),
        "symbols":[]
    }

    for sym, rows in sorted(by.items()):

        # -------------------------------------------------
        # UNIQUE UTC HOUR TEMPORAL VIEW
        # Ham log korunur.
        # Aynı UTC saatindeki birden fazla ölçümden
        # yalnızca o saatin SON ölçümü temporal analizde kullanılır.
        # -------------------------------------------------

        hourly = {}

        for row in rows:
            ts = row.get("_observed_utc")

            if not ts:
                continue

            try:
                dt = datetime.fromisoformat(ts)

                hour_key = (
                    dt.year,
                    dt.month,
                    dt.day,
                    dt.hour
                )

                hourly[hour_key] = row

            except Exception:
                continue

        temporal_rows = [
            hourly[key]
            for key in sorted(hourly)
        ]

        if not temporal_rows:
            continue

        latest=temporal_rows[-1]
        first=temporal_rows[0]

        raw_n=len(rows)
        n=len(temporal_rows)

        funding=latest.get("funding_rate")
        basis=latest.get("basis_bps")
        oi24=latest.get("oi_change_24h_pct")
        ls=latest.get("long_short_ratio")
        taker=latest.get("taker_buy_sell_ratio")

        evidence=[
            {"channel":"FUNDING","value":funding,"state":sign_label(funding),
             "meaning":"Funding sign only; not a directional trade signal."},
            {"channel":"BASIS","value_bps":basis,"state":sign_label(basis),
             "meaning":"Mark-index basis sign only; not a directional trade signal."},
            {"channel":"OI_24H_CHANGE","value_pct":oi24,"state":sign_label(oi24),
             "meaning":"Open-interest expansion/contraction evidence only."},
            {"channel":"GLOBAL_LONG_SHORT","value":ls,"state":ratio_label(ls),
             "meaning":"Account ratio positioning evidence; not taker flow."},
            {"channel":"TAKER_BUY_SELL","value":taker,"state":ratio_label(taker),
             "meaning":"Aggressive buy/sell volume ratio evidence only."},
        ]

        temporal = {
            "status":"INSUFFICIENT_OBSERVATIONS" if n < MIN_OBS_FOR_TEMPORAL else "OBSERVABLE",
            "observations":n,
            "raw_observations":raw_n,
            "unique_utc_hours":n,
            "deduplication":"LAST_OBSERVATION_PER_UTC_HOUR",
            "funding_delta":delta(first.get("funding_rate"), latest.get("funding_rate")),
            "basis_bps_delta":delta(first.get("basis_bps"), latest.get("basis_bps")),
            "oi_value_delta":delta(first.get("oi_value"), latest.get("oi_value")),
            "long_short_ratio_delta":delta(first.get("long_short_ratio"), latest.get("long_short_ratio")),
            "taker_buy_sell_ratio_delta":delta(first.get("taker_buy_sell_ratio"), latest.get("taker_buy_sell_ratio")),
        }

        known_states=[e["state"] for e in evidence if e["state"]!="UNKNOWN"]
        diversity=len(set(known_states))
        agreement="NOT_SCORED"
        if n >= MIN_OBS_FOR_TEMPORAL:
            agreement="MIXED_EVIDENCE" if diversity > 1 else "SAME_STATE_LABELS"

        report["symbols"].append({
            "symbol":sym,
            "active":sym in active_universe,
            "universe_status":"ACTIVE" if sym in active_universe else "HISTORICAL_ONLY",
            "latest_observed_utc":latest.get("_observed_utc"),
            "source_status":latest.get("status"),
            "missing_channels":latest.get("missing_channels",[]),
            "evidence":evidence,
            "temporal":temporal,
            "agreement":agreement,
            "conclusion":"NO_LONG_SHORT_CONCLUSION"
        })

    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")

    print("ZİTAR FUTURES EVIDENCE ENGINE V1")
    print("EVIDENCE ONLY • NO LONG/SHORT SIGNAL • NO ORDER • NO V3 WRITE")
    print("source observations:",len(history))
    print("historical symbols:",len(report["symbols"]))
    print("active universe:",len(active_universe))
    print("historical only:",
          sum(not x["active"] for x in report["symbols"]))
    print("minimum temporal observations:",MIN_OBS_FOR_TEMPORAL)
    for x in report["symbols"]:
        print(f"{x['symbol']:12} "
              f"{x['universe_status']:15} "
              f"obs={x['temporal']['observations']} "
              f"temporal={x['temporal']['status']} "
              f"agreement={x['agreement']} "
              f"conclusion={x['conclusion']}")
    print("output:",OUT)
    print("STATUS:","PASS" if report["symbols"] else "FAIL")

if __name__=="__main__":
    main()
