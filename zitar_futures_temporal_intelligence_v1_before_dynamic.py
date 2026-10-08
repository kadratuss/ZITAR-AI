from __future__ import annotations
import json, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG = BASE / "zitar_futures_intelligence_observations_v1.jsonl"
PROFILE = BASE / "zitar_futures_intelligence_profile_v1.json"

API = "https://fapi.binance.com"
SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT"]
RETRIES = 3

def get(path, params=None, timeout=20):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    last = None
    for n in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"ZITAR-Futures-Temporal-V1"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            if n + 1 < RETRIES:
                time.sleep(n + 1)
    raise last

def f(v):
    try: return float(v)
    except: return None

def safe(path, params, errors, symbol, channel):
    try:
        return get(path, params)
    except Exception as e:
        errors.append(f"{symbol}:{channel}:{type(e).__name__}:{e}")
        return None

def load_log():
    rows = []
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try: rows.append(json.loads(line))
                except: pass
    return rows

def stats(vals):
    vals = [x for x in vals if x is not None]
    if not vals: return {"n":0,"min":None,"max":None,"mean":None,"latest":None}
    return {
        "n":len(vals), "min":min(vals), "max":max(vals),
        "mean":sum(vals)/len(vals), "latest":vals[-1]
    }

def main():
    errors = []
    premium = safe("/fapi/v1/premiumIndex", None, errors, "ALL", "premiumIndex") or []
    pm = {x.get("symbol"):x for x in premium if isinstance(x,dict)}

    obs = {
        "schema":"ZITAR_FUTURES_TEMPORAL_OBSERVATION_V1",
        "observed_utc":datetime.now(timezone.utc).isoformat(),
        "mode":"RESEARCH_ONLY",
        "execution_authority":False,
        "real_orders":False,
        "paper_orders":False,
        "symbols":[],
        "errors":errors
    }

    for symbol in SYMBOLS:
        row = {"symbol":symbol}
        p = pm.get(symbol,{})
        mark,index = f(p.get("markPrice")),f(p.get("indexPrice"))
        row["funding_rate"] = f(p.get("lastFundingRate"))
        row["basis_bps"] = ((mark/index)-1)*10000 if mark and index else None

        hist = safe("/futures/data/openInterestHist",
                    {"symbol":symbol,"period":"1h","limit":25},
                    errors,symbol,"openInterestHist")
        vals = [f(x.get("sumOpenInterestValue")) for x in (hist or [])
                if f(x.get("sumOpenInterestValue")) is not None]
        row["oi_value"] = vals[-1] if vals else None
        row["oi_change_24h_pct"] = ((vals[-1]/vals[0])-1)*100 if len(vals)>1 and vals[0] else None

        ls = safe("/futures/data/globalLongShortAccountRatio",
                  {"symbol":symbol,"period":"1h","limit":2},
                  errors,symbol,"globalLongShortAccountRatio")
        z = ls[-1] if isinstance(ls,list) and ls else {}
        row["long_short_ratio"] = f(z.get("longShortRatio"))

        tk = safe("/futures/data/takerlongshortRatio",
                  {"symbol":symbol,"period":"1h","limit":2},
                  errors,symbol,"takerlongshortRatio")
        z = tk[-1] if isinstance(tk,list) and tk else {}
        row["taker_buy_sell_ratio"] = f(z.get("buySellRatio"))

        required = ["funding_rate","basis_bps","oi_value","oi_change_24h_pct",
                    "long_short_ratio","taker_buy_sell_ratio"]
        row["missing_channels"] = [k for k in required if row.get(k) is None]
        row["status"] = "OK" if not row["missing_channels"] else "PARTIAL"
        obs["symbols"].append(row)

    obs["errors"] = errors
    with LOG.open("a",encoding="utf-8") as fh:
        fh.write(json.dumps(obs,ensure_ascii=False,separators=(",",":")) + "\n")

    history = load_log()
    by_symbol = {}
    for rec in history:
        for row in rec.get("symbols",[]):
            by_symbol.setdefault(row["symbol"],[]).append(row)

    profile = {
        "schema":"ZITAR_FUTURES_INTELLIGENCE_PROFILE_V1",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "observation_count":len(history),
        "policy_status":"MEASUREMENT_ONLY_NO_DIRECTIONAL_RULES",
        "warning":"Funding, basis, OI, long/short and taker ratios are evidence channels, not standalone LONG/SHORT signals.",
        "symbols":{}
    }

    fields = ["funding_rate","basis_bps","oi_value","oi_change_24h_pct",
              "long_short_ratio","taker_buy_sell_ratio"]
    for symbol, rows in by_symbol.items():
        profile["symbols"][symbol] = {
            "observations":len(rows),
            "complete_rate":sum(r.get("status")=="OK" for r in rows)/len(rows),
            "channels":{field:stats([r.get(field) for r in rows]) for field in fields}
        }

    PROFILE.write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding="utf-8")

    print("ZİTAR FUTURES TEMPORAL INTELLIGENCE V1")
    print("RESEARCH ONLY • NO API KEY • NO ORDER • NO V3 WRITE")
    print("observation:",len(history))
    print("symbols:",len(obs["symbols"]))
    print("complete:",sum(x["status"]=="OK" for x in obs["symbols"]))
    print("partial:",sum(x["status"]=="PARTIAL" for x in obs["symbols"]))
    print("channel errors:",len(errors))
    print("policy: MEASUREMENT ONLY - NO DIRECTIONAL RULES")
    print("log:",LOG)
    print("profile:",PROFILE)
    print("STATUS:","PASS" if obs["symbols"] else "FAIL")

if __name__ == "__main__":
    main()
