from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent

SELECTION = BASE / "zitar_selection_engine_v1.json"
OUT = BASE / "zitar_futures_universe_v1.json"

API = "https://fapi.binance.com"

EXCLUDED_BASE_ASSETS = {
    "USDT", "USDC", "FDUSD", "TUSD", "DAI", "BUSD"
}


def load_json(path):
    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def get_exchange_info(timeout=20):
    req = urllib.request.Request(
        API + "/fapi/v1/exchangeInfo",
        headers={
            "User-Agent":
                "ZITAR-Futures-Universe-V1"
        }
    )

    with urllib.request.urlopen(
        req,
        timeout=timeout
    ) as r:
        return json.loads(
            r.read().decode("utf-8")
        )


def try_base_asset(spot_symbol):
    if not isinstance(spot_symbol, str):
        return None

    if not spot_symbol.endswith("TRY"):
        return None

    base = spot_symbol[:-3].strip()

    return base or None


def main():

    if not SELECTION.exists():
        raise SystemExit(
            "STOP: Selection Engine output bulunamadi."
        )

    selection = load_json(SELECTION)
    exchange = get_exchange_info()

    perpetual_by_base = {}

    for x in exchange.get("symbols", []):

        if x.get("contractType") != "PERPETUAL":
            continue

        if x.get("quoteAsset") != "USDT":
            continue

        if x.get("status") != "TRADING":
            continue

        base = x.get("baseAsset")
        symbol = x.get("symbol")

        if base and symbol:
            perpetual_by_base[base] = symbol

    matched = []
    unmatched = []

    for candidate in selection.get(
        "candidates",
        []
    ):

        spot_symbol = candidate.get("symbol")
        base = try_base_asset(spot_symbol)

        item = {
            "spot_symbol": spot_symbol,
            "base_asset": base,
            "selection_observations":
                candidate.get("observations"),
            "selection_depth_success_rate":
                candidate.get(
                    "depth_success_rate"
                ),
            "selection_rank_median":
                candidate.get("rank_median"),
            "selection_spread_bps_median":
                candidate.get(
                    "spread_bps_median"
                )
        }

        if not base:
            item["status"] = "INVALID_SPOT_SYMBOL"
            item["reason"] = "TRY_BASE_EXTRACTION_FAILED"
            unmatched.append(item)
            continue

        if base in EXCLUDED_BASE_ASSETS:
            item["status"] = "EXCLUDED_BASE_ASSET"
            item["reason"] = "STABLECOIN_BASE_EXCLUDED"
            unmatched.append(item)
            continue

        futures_symbol = perpetual_by_base.get(base)

        if not futures_symbol:
            item["status"] = "NO_PERPETUAL_MATCH"
            item["reason"] = (
                "NO_TRADING_USDT_PERPETUAL"
            )
            unmatched.append(item)
            continue

        item["futures_symbol"] = futures_symbol
        item["status"] = "MATCHED"

        matched.append(item)

    payload = {
        "schema":
            "ZITAR_FUTURES_UNIVERSE_V1",

        "generated_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "source":
            SELECTION.name,

        "selection_mode":
            selection.get("mode"),

        "policy": {
            "research_only": True,
            "real_order": False,
            "paper_order": False,
            "directional_signal": False
        },

        "rules": {
            "spot_quote": "TRY",
            "futures_quote": "USDT",
            "contract_type": "PERPETUAL",
            "required_status": "TRADING",
            "stablecoin_bases_excluded":
                sorted(EXCLUDED_BASE_ASSETS)
        },

        "input_candidates":
            len(
                selection.get(
                    "candidates",
                    []
                )
            ),

        "matched_count":
            len(matched),

        "unmatched_count":
            len(unmatched),

        "matched":
            matched,

        "unmatched":
            unmatched
    }

    OUT.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print("ZITAR FUTURES UNIVERSE V1")
    print(
        "SELECTION -> VERIFIED USDT PERPETUAL"
    )
    print(
        "RESEARCH ONLY • NO ORDER • NO SIGNAL"
    )

    print(
        "input candidates:",
        payload["input_candidates"]
    )

    print(
        "matched:",
        payload["matched_count"]
    )

    print(
        "unmatched:",
        payload["unmatched_count"]
    )

    print("\nMATCHED")

    for x in matched:
        print(
            f"{x['spot_symbol']:<14}"
            f" -> {x['futures_symbol']}"
        )

    if unmatched:

        print("\nUNMATCHED / EXCLUDED")

        for x in unmatched:
            print(
                f"{str(x['spot_symbol']):<14}"
                f" {x['status']:<22}"
                f" {x['reason']}"
            )

    print("\noutput:", OUT)

    print(
        "STATUS:",
        "PASS"
        if matched
        else "FAIL"
    )


if __name__ == "__main__":
    main()
