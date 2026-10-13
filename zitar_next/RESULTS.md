# Independent Next acceptance trial — 8 October 2026

Inputs: separate public BTCUSDT spot and USD-M perpetual datasets, each 3000
closed hourly candles. Models: PPO, 2048 steps, fixed seeds 42 and 73; three
earlier disjoint walk-forward test windows. Final holdout excluded from folds.

| Market | Seed 42 test | Seed 73 test | Unanimous ensemble test | Eligible |
|---|---:|---:|---:|---|
| Spot | +4.9694% | +4.9694% | +4.9694% | No |
| Futures, 3x isolated | -1.5649% | -0.0678% | -0.0678% | No |

Spot merely matched the long baseline, exceeded the 5% drawdown budget and had
too few fills. Futures lacked baseline advantage, positive cost stress and
sufficient fills. Earlier walk-forward windows also failed eligibility checks.
No research candidate was accepted or activated by the agent. Current Next
registry has no active paper strategy. This is not a profitability claim and
cannot be compared directly to previous snapshots or to the production TRY
accounts. Full snapshot/model/scaler hashes remain in local trial artifacts.

All 110 isolated research tests passed: 25 Next tests plus 85 prior research
tests. Includes long/short funding sign, reserve isolation, terminal settlement,
next-bar shadow replay, single-writer lock, HTTP Origin/CSRF, immutable proposal
review, rollback, no model load before approval, walk-forward chronology, public
pagination, 503 retry, rate-limit stop and rejection of order endpoint paths.
Browser verified spot/futures cards, learning curve, latest worker state,
disabled accept/activate controls for insufficient candidates and no JS errors.

An opt-in Next worker checks every 300 seconds and trains on newly closed hourly
bars. It is separate from production and is not installed as a system service
or scheduled task. Transient public futures failure was observed; it produced
an error rather than substituting spot data. Later checks succeeded and both
markets reported WAITING_NEW_CANDLE. Bounded connection retries and per-market
status are included. No claim of uninterrupted future service availability.

Deferred by user instruction: production runtime inventory, active deployment
assets/configuration, DB verification, whole-ZİTAR regression, main menu hookup,
production installation, restart and final integration. FinRL-X integration is
limited to the official pinned strategy interface; its broker/platform is not
installed. Long-term forward evidence must accumulate over real elapsed time.
