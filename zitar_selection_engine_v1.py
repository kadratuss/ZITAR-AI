from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent

PROFILE = BASE / "zitar_liquidity_profile_v1.json"
SNAPSHOT = BASE / "zitar_universe_liquidity_snapshot_v1.json"
OUT = BASE / "zitar_selection_engine_v1.json"

MIN_OBSERVATIONS_FOR_STABLE = 20
MIN_DEPTH_SUCCESS = 0.80

CANDIDATE_LIMIT = 20


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def load_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():

    profile = load_json(PROFILE)
    snapshot = load_json(SNAPSHOT)

    observation_count = int(
        profile.get("observation_count", 0) or 0
    )

    mode = (
        "STABLE"
        if observation_count >= MIN_OBSERVATIONS_FOR_STABLE
        else "WARMUP"
    )

    latest = {}

    for row in snapshot.get("top20", []):
        symbol = row.get("symbol")
        if symbol:
            latest[symbol] = row

    candidates = []
    rejected = []

    for symbol, p in profile.get("symbols", {}).items():

        obs = int(p.get("observations", 0) or 0)

        depth_success = finite(
            p.get("depth_success_rate")
        )

        spread_median = finite(
            p.get("spread_bps_median")
        )

        spread_p95 = finite(
            p.get("spread_bps_p95")
        )

        impact = p.get("impact_bps", {})

        one = impact.get("1000", {})
        five = impact.get("5000", {})
        ten = impact.get("10000", {})

        buy1 = finite(one.get("buy_p95"))
        sell1 = finite(one.get("sell_p95"))

        buy5 = finite(five.get("buy_p95"))
        sell5 = finite(five.get("sell_p95"))

        buy10 = finite(ten.get("buy_p95"))
        sell10 = finite(ten.get("sell_p95"))

        reasons = []

        if depth_success is None:
            reasons.append("NO_DEPTH_HISTORY")

        elif depth_success < MIN_DEPTH_SUCCESS:
            reasons.append("LOW_DEPTH_SUCCESS")

        if spread_median is None:
            reasons.append("NO_SPREAD_HISTORY")

        if obs <= 0:
            reasons.append("NO_OBSERVATIONS")

        # WARMUP sırasında sabit trading threshold üretmiyoruz.
        # Yalnızca ölçüm kalitesi ve veri bulunabilirliği kontrol edilir.

        eligible = len(reasons) == 0

        live = latest.get(symbol, {})

        item = {
            "symbol": symbol,
            "observations": obs,
            "depth_success_rate": depth_success,
            "rank_median": finite(
                p.get("rank_median")
            ),
            "spread_bps_median": spread_median,
            "spread_bps_p95": spread_p95,

            "impact_p95_bps": {
                "1000_try": {
                    "buy": buy1,
                    "sell": sell1
                },
                "5000_try": {
                    "buy": buy5,
                    "sell": sell5
                },
                "10000_try": {
                    "buy": buy10,
                    "sell": sell10
                }
            },

            "latest_quote_volume_24h_try":
                finite(
                    live.get(
                        "quote_volume_24h_try"
                    )
                ),

            "eligible_for_analysis": eligible,

            "rejection_reasons": reasons
        }

        if eligible:
            candidates.append(item)
        else:
            rejected.append(item)

    # Öncelik:
    # 1 depth güvenilirliği
    # 2 median hacim sırası
    # 3 median spread
    #
    # Bu TRADING SCORE değildir.
    # Sadece araştırma/analiz önceliğidir.

    candidates.sort(
        key=lambda x: (
            -(x["depth_success_rate"] or 0),
            x["rank_median"]
            if x["rank_median"] is not None
            else 999999,
            x["spread_bps_median"]
            if x["spread_bps_median"] is not None
            else 999999
        )
    )

    candidates = candidates[:CANDIDATE_LIMIT]

    payload = {

        "schema":
            "ZITAR_SELECTION_ENGINE_V1",

        "created_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "mode":
            mode,

        "observation_count":
            observation_count,

        "stable_after_observations":
            MIN_OBSERVATIONS_FOR_STABLE,

        "policy": {
            "real_order": False,
            "paper_order": False,
            "directional_signal": False,
            "eligibility_is_trade_permission": False,
            "selection_is_research_priority_only": True
        },

        "pipeline": [
            "TRY_UNIVERSE",
            "24H_VOLUME",
            "TOP20",
            "TEMPORAL_LIQUIDITY",
            "ANALYSIS_ELIGIBILITY",
            "FUTURES_MATCH_PENDING"
        ],

        "candidate_count":
            len(candidates),

        "candidates":
            candidates,

        "rejected_count":
            len(rejected),

        "rejected":
            rejected
    }

    OUT.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print("ZITAR SELECTION ENGINE V1")
    print(
        "READ/ANALYSIS ONLY • "
        "NO ORDER • NO SIGNAL"
    )

    print("mode:", mode)

    print(
        "observations:",
        observation_count,
        "/",
        MIN_OBSERVATIONS_FOR_STABLE
    )

    print(
        "candidates:",
        len(candidates)
    )

    print(
        "rejected:",
        len(rejected)
    )

    print("\nANALYSIS CANDIDATES")

    for i, x in enumerate(
        candidates,
        1
    ):
        print(
            f"{i:02d} "
            f"{x['symbol']:<14} "
            f"obs={x['observations']:<3} "
            f"depth="
            f"{x['depth_success_rate']:.2f} "
            f"rank="
            f"{x['rank_median']} "
            f"spread="
            f"{x['spread_bps_median']}"
        )

    if rejected:

        print("\nREJECTED")

        for x in rejected:

            print(
                x["symbol"],
                ",".join(
                    x["rejection_reasons"]
                )
            )

    print("\noutput:", OUT)
    print(
        "STATUS:",
        "PASS"
        if candidates
        else "FAIL"
    )


if __name__ == "__main__":
    main()
