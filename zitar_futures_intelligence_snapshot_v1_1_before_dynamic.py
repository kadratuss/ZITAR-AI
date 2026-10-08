from __future__ import annotations
import json, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE=Path(__file__).resolve().parent
OUT=BASE/"zitar_futures_intelligence_snapshot_v1_1.json"
API="https://fapi.binance.com"
SYMBOLS=["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT"]
RETRIES=3

def get(path, params=None, timeout=20):
    url=API+path
    if params: url+="?"+urllib.parse.urlencode(params)
    last=None
    for n in range(RETRIES):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"ZITAR-Futures-Intelligence-V1.1"})
            with urllib.request.urlopen(req,timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last=e
            if n+1<RETRIES: time.sleep(1.0*(n+1))
    raise last

def f(v):
    try:return float(v)
    except:return None

def safe(path, params, errors, symbol, channel):
    try:return get(path,params)
    except Exception as e:
        errors.append(f"{symbol}:{channel}:{type(e).__name__}:{e}")
        return None

def main():
    result={"schema":"ZITAR_FUTURES_INTELLIGENCE_SNAPSHOT_V1_1",
            "generated_utc":datetime.now(timezone.utc).isoformat(),
            "mode":"RESEARCH_ONLY","execution_authority":False,
            "real_orders":False,"paper_orders":False,"symbols":[],"errors":[]}
    premium=safe("/fapi/v1/premiumIndex",None,result["errors"],"ALL","premiumIndex") or []
    pm={x.get("symbol"):x for x in premium if isinstance(x,dict)}

    for symbol in SYMBOLS:
        row={"symbol":symbol}
        p=pm.get(symbol,{})
        mark,index=f(p.get("markPrice")),f(p.get("indexPrice"))
        row["mark_price"]=mark; row["index_price"]=index
        row["basis_bps"]=((mark/index)-1)*10000 if mark and index else None
        row["last_funding_rate"]=f(p.get("lastFundingRate"))
        row["next_funding_time_ms"]=p.get("nextFundingTime")

        oi=safe("/fapi/v1/openInterest",{"symbol":symbol},result["errors"],symbol,"openInterest")
        row["open_interest_contracts"]=f(oi.get("openInterest")) if isinstance(oi,dict) else None

        hist=safe("/futures/data/openInterestHist",{"symbol":symbol,"period":"1h","limit":25},
                  result["errors"],symbol,"openInterestHist")
        vals=[f(x.get("sumOpenInterestValue")) for x in (hist or []) if f(x.get("sumOpenInterestValue")) is not None]
        row["open_interest_value_latest"]=vals[-1] if vals else None
        row["open_interest_value_24h_ago"]=vals[0] if len(vals)>1 else None
        row["open_interest_value_change_pct_24h"]=(vals[-1]/vals[0]-1)*100 if len(vals)>1 and vals[0] else None

        ls=safe("/futures/data/globalLongShortAccountRatio",{"symbol":symbol,"period":"1h","limit":2},
                result["errors"],symbol,"globalLongShortAccountRatio")
        z=ls[-1] if isinstance(ls,list) and ls else {}
        row["global_long_short_ratio"]=f(z.get("longShortRatio"))
        row["global_long_account_share"]=f(z.get("longAccount"))
        row["global_short_account_share"]=f(z.get("shortAccount"))

        tk=safe("/futures/data/takerlongshortRatio",{"symbol":symbol,"period":"1h","limit":2},
                result["errors"],symbol,"takerlongshortRatio")
        z=tk[-1] if isinstance(tk,list) and tk else {}
        row["taker_buy_sell_ratio"]=f(z.get("buySellRatio"))
        row["taker_buy_vol"]=f(z.get("buyVol")); row["taker_sell_vol"]=f(z.get("sellVol"))

        required=["mark_price","index_price","last_funding_rate","open_interest_contracts",
                  "open_interest_value_change_pct_24h","global_long_short_ratio","taker_buy_sell_ratio"]
        missing=[k for k in required if row.get(k) is None]
        row["missing_channels"]=missing
        row["status"]="OK" if not missing else "PARTIAL"
        result["symbols"].append(row)

    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("ZİTAR FUTURES INTELLIGENCE SNAPSHOT V1.1")
    print("RESEARCH ONLY • NO API KEY • NO ORDER • NO V3 WRITE")
    print("symbols:",len(result["symbols"]))
    print("complete:",sum(x["status"]=="OK" for x in result["symbols"]))
    print("partial:",sum(x["status"]=="PARTIAL" for x in result["symbols"]))
    print("channel errors:",len(result["errors"]))
    for x in result["symbols"]:
        print(f"{x['symbol']:10} {x['status']:7} funding={x.get('last_funding_rate')} "
              f"basis={None if x.get('basis_bps') is None else round(x['basis_bps'],2)}bps "
              f"OI24h={None if x.get('open_interest_value_change_pct_24h') is None else round(x['open_interest_value_change_pct_24h'],2)}% "
              f"L/S={x.get('global_long_short_ratio')} taker={x.get('taker_buy_sell_ratio')} "
              f"missing={','.join(x['missing_channels']) or '-'}")
    if result["errors"]:
        print("\nCHANNEL ERRORS")
        for e in result["errors"]: print(" ",e)
    print("output:",OUT)
    print("STATUS:","PASS" if result["symbols"] else "FAIL")

if __name__=="__main__":
    main()
