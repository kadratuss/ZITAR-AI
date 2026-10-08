# FinRL-X research integration validation

Pinned source: AI4Finance-Foundation/FinRL-Trading commit
4409abe925c904e570be78ebfb5e77ac3491dff8. See vendor/NOTICE.md for the
offline boundary changes and included Apache-2.0 license.

## Completed flow

Public Binance snapshot -> causal indicators / chronological split -> PPO
training -> unanimous model decisions -> official StrategyResult -> official
BacktestEngine / bt -> dedicated report -> unified console -> existing human
approval gate. Each new training round binds its FinRL-X report hash into the
immutable proposal. Existing models can be replayed without modifying proposals.

## Actual saved model replay

These are real recorded BTCUSDT hourly snapshots, not synthetic UI data.

| Market / run | FinRL-X weight test | Authoritative ZITAR net test | Eligible |
|---|---:|---:|---|
| Spot / spot-329acadb414b423db54562f0ae5169fc | -4.7952% | -7.6089% | No |
| Futures / futures-8d5832a5f17a4249856f2d33e23527b8 | -0.4311% | -0.4474% | No |

The weight test rebalances every bar, uses next-open prices plus terminal close,
and applies risky-asset fees. It does not model intrabar mark excursions,
slippage, funding or isolated liquidation. The net test includes the configured
costs and, for futures, the isolated account model. The two metrics must remain
separate; FinRL-X diagnostic results cannot override eligibility.

## New training end to end

A separate marked workspace research_artifacts/finrlx-validation trained two
fixed seeds for 128 steps each on the saved real snapshots for each market,
including earlier walk-forward folds and final evaluation. Both markets
produced FinRL-X reports and hash-bound proposal summaries automatically.
This short run verifies integration, not learning quality or profitability.
Neither candidate was eligible, accepted or activated.

118 unittest tests passed. New tests run the actual upstream backtest engine,
cover signed partial futures exposure, flat spot, causal next-open mapping and
input rejection. Network connects are forbidden during these backtests. Existing
worker, approval, isolated loss, funding, data-quality and HTTP tests still pass.
pip check found no broken requirements. The console displayed both reports
without browser console errors. The independent worker was restarted with the
new pipeline; it is waiting for a new closed hourly candle.

No production dashboard installation, broker execution, production database
change, main merge or automatic strategy activation was performed. Full upstream
stock-selection, Alpaca execution and upstream web applications are outside the
requested Binance crypto research workflow.

