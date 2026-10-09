# ZITAR hourly decision integration — first isolated comparison

Inspected main commit: 417ad1a2d6ea0a525128f7dafd76e1dc0d797c93.
The functions number/signals in vendor/zitar_hourly_signals.py are extracted
unchanged from zitar_futures_paper_engine_v1.py at that commit. Only Decimal is
imported; production runtime, process startup, files and exchange calls are absent.

## Scope

The selected spot RSI14 roster calls those signals on hourly candles, entering
long below RSI 30 and otherwise exiting. Futures reference here is the explicit
hourly ZITAR_V1 SMA/EMA/RSI confluence. The actual active futures roster can also
include discovery and 5m/15m strategies; those are NOT reproduced. Master V3 TRY
portfolio accounting is NOT converted to USDT. This is signal integration on a
common USDT simulator, not a complete clone of the production application.

An offline bridge now combines the pinned rule target with the trained PPO
ensemble. AI weights 25%, 50%, 75% are compared only on validation data, with
score = net return minus 0.5 * maximum drawdown. Final test is evaluated after
selection. All three arms have identical test bars, initial capital, costs and
next-open execution, with the same isolated account for futures. Models/scaler
and snapshots are hash verified before offline loading. No approvals are changed.

## Real saved BTCUSDT hourly replay

| Market | ZITAR hourly rule | PPO ensemble | Selected combination |
|---|---:|---:|---:|
| Spot | -4.3746% | -7.6089% | -7.6089% |
| Futures 3x isolated | -2.8755% | -0.4474% | -0.4474% |

Both selected 75% AI weight on validation. Under this discrete threshold that
weight follows the AI target; it supplies no extra decision improvement. Futures
loses less than its rule reference, but still loses. Spot is worse than its rule
reference. These results do NOT establish a stronger ZITAR AI.

The final period was previously inspected and reused. Every comparison is marked
ineligible with INTEGRATION_REPLAY_NOT_FRESH_HOLDOUT and
COMBINED_WALK_FORWARD_NOT_YET_VALIDATED. No strategy is accepted or activated.
The dashboard shows these comparisons separately from the production application.

## Reproduce

```text
python -m zitar_next.combination --root research_artifacts/next-release --run RUN_ID
python -m unittest discover -q
```

Next development: fresh disjoint comparison windows, earlier walk-forward
selection of the combiner, wider strategy diversity and symbols, then full
isolated runtime integration with an explicitly captured roster/configuration.
The currently running ZITAR must remain untouched until that evidence is reviewed.

