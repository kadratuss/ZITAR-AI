# Initial online research result — 2026-10-08

The combined research pipeline was run locally on the public Binance global
BTCUSDT endpoint. No existing application code, service, dashboard, main branch,
database or real account was changed. This is an initial research experiment,
not a production deployment or a profitable-model claim.

- Input: 1000 closed 1h candles; feature/SMA50 warmup leaves 951 timestamps.
- Retained train/validation/test: 569 / 188 / 190 timestamps, after purge/embargo.
- Training: PPO, CPU, seed 42, 2048 actual training steps, train-only scaler.
- Snapshot SHA256: `9fbfc317e62c6da8e04efae29ec7bcbfb3dea0674f222a1577dd2dd66a8bc6a5`.
- Costs: 0.1% commission and hypothetical 0.1% slippage per side; next-open
  simulated fills and final liquidation applied consistently to all strategies.
- Validation: 2026-09-22 23:00 through 2026-09-30 18:00 UTC.
- Test: 2026-09-30 21:00 through 2026-10-08 18:00 UTC. No test-based tuning.

| Strategy | Validation net return | Test net return | Test max drawdown |
| --- | ---: | ---: | ---: |
| PPO | +0.65% | -3.80% | 4.51% |
| Buy and hold | -3.01% | -3.07% | 6.98% |
| SMA20 > SMA50 long/flat | -8.25% | -0.69% | 3.99% |
| Cash | 0.00% | 0.00% | 0.00% |
| PPO at double costs | -0.15% | -4.18% | 4.70% |

PPO underperformed buy-and-hold, SMA and cash on this test window. The initial
model is therefore not a candidate for real-money deployment. There is only
one seed and a short window; no statistical robustness claim is made.

The bounded live shadow observer made two additional polls. No new closed
hourly candle appeared, so there were ZERO paper fills and no live paper PnL.
The pending action was long. Simulator tests separately verify filling a prior
decision at a new bar's open, costs, deduplication and rate-limit/failure stops.
An extended live trial is still needed to measure paper performance over time.

Local artifacts are in `research_artifacts/initial-online-run/`:
snapshot.json, report.json, scaler.json and ppo_model.zip. They are excluded
from Git; this summary is the reviewable experiment evidence. Exact package
versions are pinned in research_requirements.txt. Packages passed pip check.

The integration PR includes earlier new modules from PRs #2–#6, avoiding a
need to merge them individually. It also adds the standalone research runner
and environment; running ZITAR integration remains intentionally unexecuted.

Validation: all 76 isolated tests passed in the dedicated environment,
including the Gymnasium environment checker, a small actual PPO training,
model save/load equivalence, causal features, split isolation, accounting,
historical revisions, duplicate polls, connection failures and rate-limit stops.
