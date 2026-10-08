# Online research and paper evaluation

This integration branch combines the modules from PRs #2–#6 with a standalone
online research runner, Gymnasium environment, PPO experiment and bounded
shadow observer. It is separate from the running ZITAR application: no service
or dashboard edits, no database access, no order credentials, no deployment.

## Install in an isolated environment

Use the tested Python 3.12 x64 setup in a dedicated virtual environment, then install the exact
tested dependencies from `research_requirements.txt`:

```text
python -m venv .research-venv
.research-venv/Scripts/python -m pip install -r research_requirements.txt
.research-venv/Scripts/python -m unittest -v test_online_research_pipeline test_causal_indicators test_online_finrl_data test_chronological_split test_historical_quality_report test_finrl_data_adapter
.research-venv/Scripts/python online_research_pipeline.py --symbol BTCUSDT --count 1000 --timesteps 2048 --paper-polls 2 --output-dir outputs/research-new-run
```

Use a NEW dedicated output folder on every run. The runner exclusively creates
it and refuses overwriting an existing path. It writes only snapshot.json,
report.json, scaler.json and ppo_model.zip there. The example is Windows; use
the equivalent bin/python path on Linux. No paid plugins/API keys are needed.

## What runs

1. Binance global public-only data host supplies up to 1000 closed hourly USDT
   candles for one explicitly selected symbol. All network behavior comes from
   the online adapter: bounded timeout/retries and immediate rate-limit stop.
2. The causal feature module validates OHLCV, fixed interval, continuity,
   closure and computes SMA/EMA/RSI/MACD/ATR. SMA50 is added causally for the
   baseline. Warmup rows are omitted; at least 150 ready rows are required.
3. Chronological timestamp boundaries split 60% train, 20% validation, 20% test
   (integer rounding before purge). One trailing timestamp is purged from
   train/validation; one leading timestamp embargoed from validation/test.
4. Standardization fits TRAIN ONLY and is frozen for validation/test/shadow.
   Observations contain 8 scaled features plus cash and position fractions.
   Observation clipping to [-10,10] is fixed and not fitted on held-out data.
5. Stable-Baselines3 PPO learns on train only, CPU, explicit seed, fixed small
   architecture, no hyperparameter search. Gymnasium's contract checker runs.
   This is a FinRL-style research environment using FinRL-compatible input
   records and its usual Gym/SB3 ecosystem; the full FinRL package is not
   installed and this does not claim compatibility with every FinRL environment.
6. Frozen PPO, buy-hold, SMA20>50 and cash baselines use the SAME simulator,
   starting cash, dates, next-open execution and fees/slippage. No shorting,
   leverage or simultaneous portfolios. Symbols are researched separately.
7. Bounded shadow polls make pending decisions on live closed candles. A prior
   decision is replay-filled at the next NEW bar's observed open, then marked
   at close. These are retrospective paper fills, not executable live quotes.
   Without a new closed candle there are no fills. Duplicate polls are ignored;
   historical revisions, disconnected grids and clock regressions stop.
   Connection errors are recorded; three failures or rate limiting stop polling.

## Timing and accounting

Action 0 targets cash; action 1 targets fully long. A close-time observation
produces an action filled at NEXT candle open, including any overnight gap.
Buy price is open*(1+slippage), quantity cash/(buy_price*(1+fee)). Sells use
price*(1-slippage)*(1-fee). The last evaluation candle liquidates at close with
the same costs. Reward is equity change / initial cash. Fee and slippage are
each 0.1% per side, hypothetical and not measured from the actual order book.
Report includes net return, peak-to-trough drawdown, trades and transitions.
The SMA baseline is a long/flat regime, not the old fixed-budget crossover bot.

## Reproducibility and limits

Saved snapshot and SHA256 identify exact input; seed, split boundaries, costs,
scaler and model are retained locally. The report records actual PPO steps
(rollout rounding may exceed requested steps). CPU/package/platform changes
can change training results even with a seed. Lockfile pins this tested setup.
Only a short initial experiment is intended, not a statistically established
model or evidence of profit. Validation and test are reported separately; no
selection uses test. Do not repeatedly tune against the same held-out report.

The rolling online input window is fixed initially for feature computation in
shadow mode; new rows append to retained history, avoiding repeated EMA reseeds.
At most 60 shadow polls per run. This is NOT a continuously deployed service.
Long-running monitoring, state recovery after process restart and reconnecting
across a history gap would need a separate deployment design. The live smoke
run may see no new hourly candle and cannot establish live paper performance.

Running-system integration remains a separate explicit deployment decision.
This PR supplies the research entry point and setup; no existing ZITAR file
is imported or altered. Review this combined PR instead of merging older PRs
blindly: it already contains their new files. Do not auto-merge.
