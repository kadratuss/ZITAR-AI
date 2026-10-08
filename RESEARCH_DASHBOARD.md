# ZİTAR research dashboard

Read-only local dashboard for the standalone research pipeline merged in PR #7.
It does not modify or import the production dashboard, portfolio, DB or service
modules. It contains no order, reset, training-start or deployment controls.
Python standard library only; no UI package installation or paid plugin.

```text
python research_dashboard.py --research-root research_artifacts --port 8767
```

Open http://127.0.0.1:8767 in a browser. Only loopback is bound; no public
hosting, authentication service or remote access is configured. Stop the panel
with Ctrl+C. Use a separate port from any existing ZİTAR services. Importing
the module does not start the server or make external requests.

The selected research root must contain direct child directories with both
report.json and snapshot.json produced by the research pipeline. Empty/missing,
invalid or unfinished runs show an explicit empty/error state. JSON size is
bounded and run identifiers cannot traverse paths. Symbol candle closure,
continuity and OHLCV are revalidated before displaying the selected snapshot.
This validates that stored symbol only, not every database or training result.

The Turkish UI provides:

- Run selection and manual report refresh; no automatic experiment changes.
- Test return, drawdown, training steps and actual shadow simulated-fill count.
- Saved close/SMA20 chart (last 180 candles), clearly labeled as saved data.
- Validation/test benchmark switch, with hypothetical cost stress row.
- Chronological partition dates/counts, data validation summary and seed/hash.
- Shadow decisions/events with explicit no-new-candle/no-fill state.
- Manual online check of the latest closed hourly USDT candle via the public
  data adapter. The endpoint caches successful responses per symbol for 60s;
  UI labels cache status and server verification time separately from candle
  time. Online refresh never changes a recorded experiment or trains a model.

Errors never substitute a fictitious live price or cached historical success.
The interface emphasizes when PPO underperformed baselines; a dashboard is not
evidence that the model is fit for real money. UTC is used for candle/partition
times; online verification time is displayed in Europe/Istanbul.

All routes are GET only: /, /api/runs, /api/run?id=RUN, /api/market?symbol=SYMBOL.
There is no arbitrary file-serving route; model ZIPs, credentials and DB files
are not exposed. No CORS access is enabled; Host and anti-framing checks keep
the local tool separate. Untrusted report text is inserted via textContent.

Tests: `python -m unittest -v test_research_dashboard` checks payload validation,
nonmutation, invalid JSON/metrics, path traversal, caching/errors, HTTP routing,
loopback Host restriction and rejection of POST.

This PR prepares the dashboard before installation. Production ZİTAR deployment,
embedding in its existing dashboard and any public hosting remain separate.

## Learning and action visibility

New runs record deterministic train and validation evaluations at step 0,
every 512 steps after completed PPO updates, and at the final step. No test
partition is accessed by the callback and no best checkpoint is selected.
Training episode rewards are recorded separately, including exploration.
The dashboard shows both curves, the checkpoint values and the last 20 test
decisions. Old runs explicitly show missing-history states.

This research runner uses 1h BTCUSDT candles by default: one decision per
closed hour, executed at the next open in simulation. Action 1 targets fully
long; action 0 targets cash (selling existing holdings). Repeating a target
does not create another fill. No shorts, leverage or real orders. Terminal
liquidation is labeled in the decision trace. This is a completed bounded
experiment, not continuous training or a running model service.

Example longer bounded trial: --timesteps 8192 --paper-polls 0 with a new
--output-dir. More steps are not guaranteed to improve unseen performance.
