# Causal indicators for online closed candles

Pure standard-library feature computation for the records returned by the
online Binance global/USDT adapter (PR #5). No paid package or plugin required.
This independent PR adds no application wiring and targets main separately.

```python
from online_finrl_data import fetch_latest_records
from causal_indicators import add_indicators

snapshot = fetch_latest_records(["BTCUSDT", "ETHUSDT"], "1h", 200)
featured = add_indicators(snapshot["records"],
                          as_of_ms=snapshot["server_time_ms"], interval="1h")
ready = [row for row in featured if row["features_ready"]]
```

The example needs both PRs available in the same checkout; this module itself
imports neither the online adapter nor any application module. Network reads
are performed explicitly by the online adapter. This feature function has no
IO/network, fitting, orders, database writes or background tasks.

Input must have canonical UTC YYYY-MM-DD HH:MM:SS date, tic, and valid OHLCV.
An explicit as_of_ms cutoff rejects any candle not yet closed. Supported
intervals are 1h/1d; each symbol must have contiguous timestamps and all symbols
must share a time grid. Input is sorted deterministically and deep copied.
Existing feature fields with reserved output names fail rather than overwrite.

Defaults and conventions:

| Field | Definition / first available zero-based row |
| --- | --- |
| sma | Trailing mean of 20 closes; row 19 |
| ema | EMA20, alpha=2/(20+1), seeded by initial SMA20; row 19 |
| rsi | Wilder RSI14, seeded from 14 close changes; row 14 |
| macd | SMA-seeded EMA12 minus EMA26; row 25 |
| macd_signal | SMA-seeded EMA9 of available MACD; row 33 |
| macd_hist | MACD minus signal; row 33 |
| atr | Wilder ATR14, initial average of 14 true ranges; row 13 |

RSI flat prices give 50, gains without losses give 100 and losses without gains
give 0. True range is max(high-low, abs(high-previous close),
abs(low-previous close)); the first candle uses high-low. Wilder smoothing
uses previous*(N-1)/N + current/N. All periods can be configured (1..10000,
MACD fast < slow). These explicit initialization conventions may differ from
other indicator libraries; this does not promise bit-for-bit stockstats/TA-Lib
equivalence. Returned field names are documented here and must be selected
explicitly in the later FinRL environment configuration.

Warmup values are None, never backfilled or replaced with zero. features_ready
becomes true only when every feature is available (row 33 by default). Dropping
warmup is caller-controlled. Repeated short online snapshots reseed recursive
indicators, so their values can differ from calculations over longer history;
use a fixed sufficient history or a future explicit stateful streaming layer.

Features include the current candle's close and are available only after that
candle closes. A signal using them must execute no earlier than the next candle.
Appending or changing future observations cannot affect earlier feature values.
Compute with historical warmup before chronological splitting; fit scalers and
models on train only. This module does not fit scalers or create forward labels.

Run isolated tests: `python -m unittest -v test_causal_indicators`.
Hand-calculated fixtures verify formulas/seeding; prefix invariance verifies
causality. Also tested: symbol isolation, warmup, gaps, invalid values, closure
boundaries, deterministic ordering and input-copy isolation.
