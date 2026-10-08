from __future__ import annotations
import json, math, statistics, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAPSHOT = BASE / "zitar_universe_liquidity_snapshot_v1.py"
LOG = BASE / "zitar_liquidity_observations_v1.jsonl"
SUMMARY = BASE / "zitar_liquidity_profile_v1.json"

TICKER_URL = "https://api.binance.me/api/v3/ticker/24hr"
DEPTH_URL = "https://api.binance.me/api/v3/depth"
QUOTE = "TRY"
TOP_N = 20
DEPTH_LIMIT = 20
NOTIONALS = (1000.0, 5000.0, 10000.0)
RETRIES = 2

def get_json(url, timeout=20):
    last = None
    for attempt in range(RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"ZITAR-Liquidity-Observer-V1"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            if attempt < RETRIES:
                time.sleep(0.8 * (attempt + 1))
    raise last

def f(x, default=0.0):
    try: return float(x)
    except: return default

def impact(levels, notional_try, side):
    if not levels: return None
    best = f(levels[0][0])
    if best <= 0: return None
    target_base = notional_try / best
    remain, quote, filled = target_base, 0.0, 0.0
    for px_s, qty_s in levels:
        px, qty = f(px_s), f(qty_s)
        take = min(remain, qty)
        quote += take * px
        filled += take
        remain -= take
        if remain <= 1e-12: break
    if remain > 1e-12 or filled <= 0: return None
    avg = quote / filled
    if side == "BUY":
        bps = (avg / best - 1.0) * 10000
    else:
        bps = (best / avg - 1.0) * 10000
    return max(0.0, bps)

def pct(values, p):
    if not values: return None
    s=sorted(values)
    if len(s)==1: return s[0]
    k=(len(s)-1)*p
    lo,hi=math.floor(k),math.ceil(k)
    if lo==hi: return s[lo]
    return s[lo]*(hi-k)+s[hi]*(k-lo)

def load_log():
    out=[]
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try: out.append(json.loads(line))
                except: pass
    return out

def summarize(records):
    by={}
    for rec in records:
        for x in rec.get("symbols",[]):
            by.setdefault(x["symbol"],[]).append(x)
    result={}
    for sym, xs in by.items():
        spreads=[x["spread_bps"] for x in xs if x.get("spread_bps") is not None]
        ranks=[x["rank"] for x in xs if x.get("rank") is not None]
        d_ok=[x for x in xs if x.get("depth_ok")]
        item={
            "observations":len(xs),
            "depth_success_rate":len(d_ok)/len(xs) if xs else 0,
            "rank_median":statistics.median(ranks) if ranks else None,
            "rank_best":min(ranks) if ranks else None,
            "rank_worst":max(ranks) if ranks else None,
            "spread_bps_median":statistics.median(spreads) if spreads else None,
            "spread_bps_p95":pct(spreads,.95),
            "impact_bps":{}
        }
        for n in NOTIONALS:
            key=str(int(n))
            buys=[x["impact"][key]["buy"] for x in xs if x.get("impact",{}).get(key,{}).get("buy") is not None]
            sells=[x["impact"][key]["sell"] for x in xs if x.get("impact",{}).get(key,{}).get("sell") is not None]
            item["impact_bps"][key]={
                "buy_median":statistics.median(buys) if buys else None,
                "buy_p95":pct(buys,.95),
                "sell_median":statistics.median(sells) if sells else None,
                "sell_p95":pct(sells,.95),
            }
        result[sym]=item
    return result

def main():

    # -------------------------------------------------
    # HOURLY OBSERVATION GUARD
    # Aynı UTC saatinde ikinci likidite gözlemini yazma.
    # -------------------------------------------------

    existing_records = load_log()
    now_dt = datetime.now(timezone.utc)

    if existing_records:
        last_ts = existing_records[-1].get("observed_utc")

        if last_ts:
            try:
                last_dt = datetime.fromisoformat(last_ts)

                same_utc_hour = (
                    last_dt.year == now_dt.year
                    and last_dt.month == now_dt.month
                    and last_dt.day == now_dt.day
                    and last_dt.hour == now_dt.hour
                )

                if same_utc_hour:
                    print("ZİTAR TEMPORAL LIQUIDITY OBSERVER V1")
                    print("PUBLIC READ ONLY • NO API KEY • NO ORDER • NO V3 WRITE")
                    print("observation:", len(existing_records))
                    print("HOURLY GUARD: current UTC hour already observed")
                    print("NEW OBSERVATION: SKIPPED")
                    print("STATUS: PASS")
                    return

            except Exception:
                pass

    tickers=get_json(TICKER_URL)
    if isinstance(tickers,dict) and "data" in tickers: tickers=tickers["data"]
    universe=[]
    for t in tickers:
        sym=str(t.get("symbol",""))
        if not sym.endswith(QUOTE): continue
        qv=f(t.get("quoteVolume")); last=f(t.get("lastPrice"))
        bid=f(t.get("bidPrice")); ask=f(t.get("askPrice"))
        if qv<=0 or last<=0: continue
        spread=((ask-bid)/((ask+bid)/2)*10000) if bid>0 and ask>0 and ask>=bid else None
        universe.append({"symbol":sym,"quote_volume_24h_try":qv,"spread_bps":spread})
    universe.sort(key=lambda x:x["quote_volume_24h_try"], reverse=True)

    now=datetime.now(timezone.utc).isoformat()
    obs={"schema":"ZITAR_LIQUIDITY_OBSERVATION_V1","observed_utc":now,
         "top_n":TOP_N,"notionals_try":list(NOTIONALS),"symbols":[]}
    errors=[]

    for rank,t in enumerate(universe[:TOP_N],1):
        x={"symbol":t["symbol"],"rank":rank,
           "quote_volume_24h_try":t["quote_volume_24h_try"],
           "spread_bps":t["spread_bps"],"depth_ok":False,"impact":{}}
        try:
            url=DEPTH_URL+"?"+urllib.parse.urlencode({"symbol":t["symbol"],"limit":DEPTH_LIMIT})
            d=get_json(url)
            if isinstance(d,dict) and "data" in d: d=d["data"]
            bids,asks=d.get("bids",[]),d.get("asks",[])
            x["depth_ok"]=bool(bids and asks)
            x["bid_notional_top20_try"]=sum(f(a)*f(b) for a,b in bids)
            x["ask_notional_top20_try"]=sum(f(a)*f(b) for a,b in asks)
            for n in NOTIONALS:
                x["impact"][str(int(n))]={
                    "buy":impact(asks,n,"BUY"),
                    "sell":impact(bids,n,"SELL")
                }
        except Exception as e:
            errors.append(f"{t['symbol']}:{type(e).__name__}:{e}")
        obs["symbols"].append(x)

    with LOG.open("a",encoding="utf-8") as fh:
        fh.write(json.dumps(obs,ensure_ascii=False,separators=(",",":"))+"\n")

    records=load_log()
    profile={
        "schema":"ZITAR_LIQUIDITY_PROFILE_V1",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "observation_count":len(records),
        "policy_status":"MEASUREMENT_ONLY_NO_ELIGIBILITY_THRESHOLDS",
        "warning":"Do not infer stable liquidity from a small number of observations.",
        "symbols":summarize(records),
        "latest_errors":errors
    }
    SUMMARY.write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding="utf-8")

    print("ZİTAR TEMPORAL LIQUIDITY OBSERVER V1")
    print("PUBLIC READ ONLY • NO API KEY • NO ORDER • NO V3 WRITE")
    print("observation:",len(records))
    print("top symbols:",len(obs["symbols"]))
    print("depth success:",sum(1 for x in obs["symbols"] if x["depth_ok"]),"/",len(obs["symbols"]))
    print("errors:",len(errors))
    print("notionals TRY:",", ".join(str(int(x)) for x in NOTIONALS))
    print("policy: MEASUREMENT ONLY - thresholds NOT frozen")
    print("log:",LOG)
    print("profile:",SUMMARY)
    print("STATUS:","PASS" if obs["symbols"] else "FAIL")

if __name__=="__main__":
    main()
