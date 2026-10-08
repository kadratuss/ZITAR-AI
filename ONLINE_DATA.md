# Binance global / USDT online adapter

The online requirement replaces the earlier offline-only data-source choice.
Existing SQLite adapters, services and databases remain separate. This module
reads Binance global USDT markets, not Binance TR/TRY; do not mix their prices.

## Setup

Python 3.10+ and outbound HTTPS to `data-api.binance.vision:443` are sufficient.
No third-party package, paid plugin, FinRL installation or exchange API key is
needed. The client uses Python's standard-library HTTPS/JSON libraries. The
optional pandas/FinRL training stack is separate from this market-data client.

```text
python online_finrl_data.py BTCUSDT ETHUSDT --interval 1h --count 100
```

This opt-in command performs a bounded live REST fetch and prints JSON to stdout.
It does not launch a polling service, persist data or change any database. Call
`fetch_latest_records(["BTCUSDT"], count=100)` for the same snapshot in memory.
The returned `records` list uses the offline adapter's date/tic/OHLCV/day schema
and can be passed to the chronological splitter after choosing boundaries.

## Contract

- Explicit global USDT symbols; 1..20 unique symbols, 1h/1d intervals, 1..1000
  recent closed candles per symbol. Larger history pagination is out of scope.
- Server time fixes one common cutoff before fetching symbols. Each response
  must contain the entire requested contiguous grid. Unlisted/new markets with
  insufficient history fail instead of silently returning a partial snapshot.
- UTC dates preserve hours. Values must be finite, prices positive, volume
  nonnegative and OHLC relationships valid. No filling or resampling occurs.
- GET only, fixed public-data host, only time/klines endpoints. Redirects are
  refused. No API credentials or order/account endpoints are implemented.
- 15 second per-request timeout; at most three attempts for network/5xx errors,
  exponential short backoff. HTTP 418/429 stops immediately and exposes
  Retry-After; callers must respect it. Symbol requests are spaced 250 ms.
  This is not an account-wide rate limiter; coordinate any future polling.
- No fallback to offline data or another exchange on errors. CLI returns 1 on
  validation/connectivity failures. Importing the module never makes requests.

Tests use mocked responses to be reproducible and avoid API load:
`python -m unittest -v test_online_finrl_data`.
Live connectivity must be checked separately; geographic/network restrictions
can prevent access. A successful one-shot fetch does not deploy continuous
monitoring, training or integration into the running ZITAR application.

References: [public market-data endpoint](https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md),
[Binance market-data API](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints).
