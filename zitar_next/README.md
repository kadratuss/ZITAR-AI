# ZİTAR Next — independent research and human review

This package is separate from the currently running ZİTAR test. It imports no
production runtime, dashboard, portfolio, supervisor or database module. All
mutable state belongs to a newly created, marked Next workspace. Never point
it at a production directory. Source files under sources/ are not used.

## Run in a dedicated virtual environment

Use Python 3.12 and install the pinned requirements.txt into that environment.
The existing research virtual environment already contains these dependencies;
FinRL-X backtest dependencies are installed only in that research environment; no global or production installation is performed. The lock now includes bt, scipy and matplotlib and their transitive dependencies.

From the repository root:

```text
python -m zitar_next.worker --root research_artifacts/next-demo --init --steps 2048 --cycles 1
python -m zitar_next.dashboard --root research_artifacts/next-demo --port 8768
```

--init exclusively creates a NEW folder and refuses an existing folder.
To continue learning in the same dedicated workspace, omit --init:

```text
python -m zitar_next.worker --root research_artifacts/next-demo --steps 2048 --cycles 0 --pause 300
```

cycles=0 is an explicitly started ongoing process, not a Windows service,
scheduled task or production integration. Stop this worker with Ctrl+C. Its OS
file lock prevents two workers from writing the same workspace and is released
on process death. Restarting keeps cursors and checks overlapping history.
Each public request has a timeout; network errors are recorded, not replaced
with fictitious data. No automatic activation or real broker capability exists.

The default fetch is 3000 closed 1h candles, with bounded 1000-candle pages and
one fixed server-time cutoff per market. Spot and USD-M perpetual histories are
different datasets. Futures uses public trade candles, mark-price candles and
funding history. Missing/truncated funding or a >8h gap (+60s timestamp tolerance)
rejects the snapshot. Symbols with more frequent funding may exceed the bounded
funding response and are deliberately rejected instead of silently truncated.

Polling happens every five minutes; model retraining happens on a newly closed
hourly candle, or when explicitly expanding the initial history window. This is
periodic retraining from scratch, not gradient updates on each price tick. Two
fixed seeds are trained; their unanimous action is used by the paper ensemble,
otherwise cash is selected. Neither best seed nor best checkpoint is selected.

## Evaluation and proposal gate

- Train-only scaling; chronological train/validation/test with purge/embargo.
- Training reward and train/validation curves are persisted during main training.
- Final held-out test evaluated after training, including doubled costs.
- Three disjoint earlier walk-forward test windows; each model trained only on
  earlier data. The final holdout is excluded from these folds.
- Both individual seeds and the actual unanimous ensemble are assessed.
- Fixed eligibility: at least two seeds, >=150 test bars, >=20 fills, <=5% modeled
  drawdown, >=1 percentage point advantage over cash/long/SMA, positive stressed
  return and no modeled liquidations. Same criteria apply to each walk-forward
  fold. Thresholds are research policy assumptions, not investment guarantees.
- A subsequent round with overlapping final test dates is marked ineligible;
  repeatedly testing the same period never counts as fresh validation.
- Every candidate links hypothesis hash, immutable proposal hash, snapshot,
  scaler and model hashes, seed results and fold evidence. These are candidate
  learned parameters within a fixed PPO strategy family, not automatically
  invented executable code or novel trading rules.

Pending proposals never load into paper execution. Human acceptance and separate
human paper activation are both required. Rejection is final for that proposal;
changed content requires a new identity and new approval. Previously accepted
versions can be restored with an explicit rollback. Every decision is logged in
the Next-only SQLite registry with transactional state transitions.

The dashboard provides deliberate buttons for these actions with Host, Origin
and CSRF checks. These actions have NOT been taken on real research candidates
by the agent. Acceptance tests exercise disposable temporary fixture proposals.

## Spot and isolated 3x futures

Spot targets cash or fully long. Futures targets cash, long or short. Futures
allocates at most 10% of current cash to one isolated collateral account with
fixed 3x leverage; remaining cash is reserved. Losses on that position cannot
consume the reserve. Fees and funding are charged; maintenance=.005 and modeled
liquidation fee=.005 are explicit assumptions, not Binance account/tier rules.

Signals use candle close and fills use next trade-candle open plus modeled
slippage. Futures liquidation checks use adverse mark OHLC, with pessimistic
intrabar ordering before intrabar funding. Funding at the exact open is charged
to carried positions before new entries. Backtests close at the final candle;
shadow accounts retain positions. A version switch archives the old Next
shadow state and starts a new flat experimental account; it does not transfer
positions or balance, and the archive may contain an unclosed position.

Approved shadow replay only processes newer closed candles. It records the
previous decision at the next bar's historical open after observing that bar's
close; these are simulated after-the-fact fills, not exchange executions.
No fresh candle means no fill. All models/scalers are hash-checked before loading.

## FinRL-X and OpenClaw

ZitarWeightStrategy subclasses the pinned official BaseStrategy. Model decisions
now pass through StrategyResult into the official FinRL-X BacktestEngine / bt.
Every new train_round writes a hash-bound finrlx.json and includes its summary
in the proposal. The dashboard displays separate FinRL-X and authoritative net
metrics. Existing immutable candidates can be replayed without changing their
proposal, approval or model files:

```text
python -m zitar_next.finrl_pipeline --root research_artifacts/next-release --run RUN_ID
```

The engine is vendored with documented offline boundary modifications and the
Apache-2.0 license. Data-provider imports, sys.path changes and example CLI startup
are removed. The ZITAR subclass supplies local data, disables benchmark downloads,
uses fractional positions and avoids stock-specific daily annualization. A cash
leg preserves 0/1 spot and 0/+.3/-.3 futures entry exposure through upstream weight
normalization. It runs a separate per-bar weight-rebalanced diagnostic; it is not
execution-equivalent to the discrete-position net simulator. Futures margin,
funding, slippage and liquidation are still evaluated in FuturesEnv. Strategy
eligibility and human approval use those authoritative net tests. Upstream equity
broker execution and daily stock selection modules are outside this crypto
research integration; no claim is made that they support isolated crypto margin.

No upstream paid data or Alpaca broker is installed or imported. OpenClaw is not
needed for this bounded worker, approval registry and loopback console; adding
another orchestration layer currently duplicates functionality. Reconsider it
only for a demonstrated remaining need.

## Integration intentionally deferred

GET /api/summary and next_summary.json expose a read-only contract identifying
ZİTAR as coordinator. The production consumer is NOT connected. Static source
inventory tooling is available with python -m zitar_next.preflight SOURCE; it
hashes/parses source and does not import it, enumerate processes or open DBs.

Per the user's instruction, these remain the FINAL phase after the running test:
active service/task/entrypoint inventory, runtime config and DB verification,
full production dependency/asset packaging, actual order-off verification,
whole-application regression, main menu integration, deployment and recovery
rehearsal. These cannot truthfully be called complete from repository source
alone. No main merge, production restart or production installation is included.

## Tests

```text
python -m unittest -q test_zitar_next test_research_dashboard test_online_research_pipeline test_causal_indicators test_online_finrl_data test_chronological_split test_historical_quality_report test_finrl_data_adapter
```

This tests the standalone research stack, not the complete production ZİTAR.
Model files, source snapshots, registry DB and mutable state are not committed.

