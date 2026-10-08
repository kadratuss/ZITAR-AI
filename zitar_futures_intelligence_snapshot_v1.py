from __future__ import annotations
import json, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "zitar_futures_intelligence_snapshot_v1.json"
API = "https://fapi.binance.com"
SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT"]

def get(path, params=None, timeout=20):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent":"ZITAR-Futures-Intelligence-V1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def f(v):
    try: return float(v)
    except: return None

def main():
    now = datetime.now(timezone.utc).isoformat()
    result = {
        "schema":"ZITAR_FUTURES_INTELLIGENCE_SNAPSHOT_V1",
        "generated_utc":now,
        "mode":"RESEARCH_ONLY",
        "execution_authority":False,
        "real_orders":False,
        "paper_orders":False,
        "venue":"Binance USD-M Futures public market data",
        "symbols":[],
        "errors":[]
    }

    premium_all = get("/fapi/v1/premiumIndex")
    premium_map = {x["symbol"]:x for x in premium_all if isinstance(x,dict) and x.get("symbol")}

    for symbol in SYMBOLS:
        row={"symbol":symbol}
        try:
            p=premium_map.get(symbol,{})
            mark=f(p.get("markPrice")); index=f(p.get("indexPrice"))
            row.update({
                "mark_price":mark,
                "index_price":index,
                "basis_bps": ((mark/index)-1)*10000 if mark and index else None,
                "last_funding_rate":f(p.get("lastFundingRate")),
                "next_funding_time_ms":p.get("nextFundingTime")
            })

            oi=get("/fapi/v1/openInterest",{"symbol":symbol})
            row["open_interest_contracts"]=f(oi.get("openInterest"))

            hist=get("/futures/data/openInterestHist",{"symbol":symbol,"period":"1h","limit":25})
            vals=[f(x.get("sumOpenInterestValue")) for x in hist if f(x.get("sumOpenInterestValue")) is not None]
            row["open_interest_value_latest"]=vals[-1] if vals else None
            row["open_interest_value_24h_ago"]=vals[0] if len(vals)>1 else None
            row["open_interest_value_change_pct_24h"]=(
                (vals[-1]/vals[0]-1)*100 if len(vals)>1 and vals[0] else None
            )

            ls=get("/futures/data/globalLongShortAccountRatio",{"symbol":symbol,"period":"1h","limit":2})
            latest_ls=ls[-1] if ls else {}
            row["global_long_short_ratio"]=f(latest_ls.get("longShortRatio"))
            row["global_long_account_share"]=f(latest_ls.get("longAccount"))
            row["global_short_account_share"]=f(latest_ls.get("shortAccount"))

            taker=get("/futures/data/takerlongshortRatio",{"symbol":symbol,"period":"1h","limit":2})
            latest_t=taker[-1] if taker else {}
            row["taker_buy_sell_ratio"]=f(latest_t.get("buySellRatio"))
            row["taker_buy_vol"]=f(latest_t.get("buyVol"))
            row["taker_sell_vol"]=f(latest_t.get("sellVol"))

            row["status"]="OK"
        except Exception as e:
            row["status"]="ERROR"
            result["errors"].append(f"{symbol}:{type(e).__name__}:{e}")
        result["symbols"].append(row)

    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")

    print("ZİTAR FUTURES INTELLIGENCE SNAPSHOT V1")
    print("RESEARCH ONLY • NO API KEY • NO ORDER • NO V3 WRITE")
    print("symbols:",len(result["symbols"]))
    print("ok:",sum(x.get("status")=="OK" for x in result["symbols"]))
    print("errors:",len(result["errors"]))
    for x in result["symbols"]:
        print(
            f"{x['symbol']:10} status={x.get('status')} "
            f"funding={x.get('last_funding_rate')} "
            f"basis={None if x.get('basis_bps') is None else round(x['basis_bps'],2)}bps "
            f"OI24h={None if x.get('open_interest_value_change_pct_24h') is None else round(x['open_interest_value_change_pct_24h'],2)}% "
            f"L/S={x.get('global_long_short_ratio')} "
            f"taker={x.get('taker_buy_sell_ratio')}"
        )
    if result["errors"]:
        print("\nERRORS")
        for e in result["errors"]: print(" ",e)
    print("output:",OUT)
    print("STATUS:","PASS" if any(x.get("status")=="OK" for x in result["symbols"]) else "FAIL")

if __name__=="__main__":
    main()
