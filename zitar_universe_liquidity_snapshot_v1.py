from __future__ import annotations
import json, math, statistics, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "zitar_universe_liquidity_snapshot_v1.json"

TICKER_URL = "https://api.binance.me/api/v3/ticker/24hr"
DEPTH_URL = "https://api.binance.me/api/v3/depth"
QUOTE = "TRY"
DEPTH_LIMIT = 20
TARGET_NOTIONAL_TRY = 1000.0

def get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent":"ZITAR-Universe-Liquidity-V1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def f(x, default=0.0):
    try: return float(x)
    except: return default

def vwap_fill(levels, target_try, side):
    # BUY consumes asks: quote cost / base qty.
    # SELL consumes bids: measure achievable quote proceeds for base qty equivalent
    # to target_try at best price. This is an observational model, not execution.
    if not levels: return None
    best = f(levels[0][0])
    if best <= 0: return None
    target_base = target_try / best
    remain = target_base
    quote = 0.0
    filled = 0.0
    for px_s, qty_s in levels:
        px, qty = f(px_s), f(qty_s)
        take = min(remain, qty)
        quote += take * px
        filled += take
        remain -= take
        if remain <= 1e-12: break
    if remain > 1e-12 or filled <= 0: return None
    avg = quote / filled
    bps = ((avg / best) - 1.0) * 10000 if side == "BUY" else ((best / avg) - 1.0) * 10000
    return {"avg_price":avg, "impact_bps":bps, "filled_base":filled}

def main():
    tickers = get_json(TICKER_URL)
    if isinstance(tickers, dict) and "data" in tickers:
        tickers = tickers["data"]
    rows=[]
    for t in tickers:
        sym=str(t.get("symbol",""))
        if not sym.endswith(QUOTE): continue
        qv=f(t.get("quoteVolume"))
        last=f(t.get("lastPrice"))
        bid=f(t.get("bidPrice")); ask=f(t.get("askPrice"))
        if last <= 0 or qv <= 0: continue
        spread_bps=((ask-bid)/((ask+bid)/2)*10000) if bid>0 and ask>0 and ask>=bid else None
        rows.append({"symbol":sym,"quote_volume_24h_try":qv,"last":last,
                     "bid":bid,"ask":ask,"spread_bps":spread_bps})
    rows.sort(key=lambda x:x["quote_volume_24h_try"], reverse=True)

    # Depth is deliberately sampled only for top 20 by 24h quote volume.
    # This avoids pretending 24h volume alone proves executability.
    top=rows[:20]
    errors=[]
    for r in top:
        try:
            u=DEPTH_URL+"?"+urllib.parse.urlencode({"symbol":r["symbol"],"limit":DEPTH_LIMIT})
            d=get_json(u)
            if isinstance(d,dict) and "data" in d: d=d["data"]
            bids=d.get("bids",[]); asks=d.get("asks",[])
            r["depth"]={
                "best_bid":f(bids[0][0]) if bids else None,
                "best_ask":f(asks[0][0]) if asks else None,
                "bid_notional_top20_try":sum(f(x[0])*f(x[1]) for x in bids),
                "ask_notional_top20_try":sum(f(x[0])*f(x[1]) for x in asks),
                "buy_1000_try":vwap_fill(asks,TARGET_NOTIONAL_TRY,"BUY"),
                "sell_1000_try":vwap_fill(bids,TARGET_NOTIONAL_TRY,"SELL"),
            }
        except Exception as e:
            r["depth"]=None
            errors.append(f"{r['symbol']}:{type(e).__name__}:{e}")

    payload={
        "schema":"ZITAR_UNIVERSE_LIQUIDITY_SNAPSHOT_V1",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "source":{
            "exchange":"Binance TR",
            "ticker_endpoint":TICKER_URL,
            "depth_endpoint":DEPTH_URL,
            "public_market_data_only":True,
        },
        "method":{
            "universe":"TRY pairs with positive last price and 24h quote volume",
            "ranking":"24h quote volume descending",
            "depth_sample":"top 20 only",
            "depth_levels":DEPTH_LIMIT,
            "modeled_notional_try":TARGET_NOTIONAL_TRY,
            "important":"24h volume, spread and snapshot depth are separate measurements; none alone proves future executability."
        },
        "all_try_pairs":rows,
        "top20":top,
        "errors":errors,
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

    print("ZİTAR UNIVERSE & LIQUIDITY SNAPSHOT V1")
    print("PUBLIC READ ONLY • NO API KEY • NO ORDER • NO V3 WRITE")
    print("TRY pairs:",len(rows))
    print("depth sampled:",sum(1 for x in top if x.get("depth")))
    print("errors:",len(errors))
    print("\nTOP 20")
    for i,r in enumerate(top,1):
        d=r.get("depth")
        sp="NA" if r["spread_bps"] is None else f"{r['spread_bps']:.2f}"
        bi="NA"; si="NA"
        if d and d.get("buy_1000_try"): bi=f"{d['buy_1000_try']['impact_bps']:.2f}"
        if d and d.get("sell_1000_try"): si=f"{d['sell_1000_try']['impact_bps']:.2f}"
        print(f"{i:02d} {r['symbol']:<14} vol24h={r['quote_volume_24h_try']:>14.0f} TRY spread={sp:>8} bps buy1kImpact={bi:>8} sell1kImpact={si:>8}")
    if errors:
        print("\nDEPTH ERRORS")
        for e in errors: print(" ",e)
    print("\noutput:",OUT)
    print("STATUS:","PASS" if rows and len(top)>0 else "FAIL")

if __name__=="__main__":
    main()
