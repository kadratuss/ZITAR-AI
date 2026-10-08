# Offline FinRL data adapter

This independent module reads an existing, checkpointed **offline snapshot** of
`long_history.db`. Do not point it at a live WAL database: immutable SQLite reads
assume no concurrent writes and may not include uncheckpointed WAL contents.
Prepare the snapshot separately; this module never copies or checkpoints a DB.

The schema comes from `long_history_collector.initialize`: `historical_candles`
has symbol, interval, open/close millisecond timestamps, text OHLCV, fetched_at,
and a primary key on (symbol, interval, open_time_ms). Existing historical CSV
collection and SMA backtests are unchanged. No database is shipped in the repo,
so validation uses temporary fixtures matching that schema.

```python
from finrl_data_adapter import load_finrl_dataframe

df = load_finrl_dataframe(
    "/path/to/offline_snapshot.db", ["BTCTRY", "ETHTRY"], "1h",
    start_ms=0, end_ms=1700000000000, as_of_ms=1700000000000,
)
```

Output columns: date, tic, open, high, low, close, volume, day. `date` is UTC
opening time formatted YYYY-MM-DD HH:MM:SS, preserving intraday timestamps;
`day` is Monday=0. Rows sort by date/tic and share a factorized date index, as in
[FinRL data_split](https://github.com/AI4Finance-Foundation/FinRL/blob/master/finrl/meta/preprocessor/preprocessors.py).
Only the collector's fixed 1h/1d intervals are supported. Start is inclusive,
end exclusive on opening time; close must be strictly earlier than as_of_ms.
Omitting as_of_ms uses current UTC time. There is no filling, resampling, symbol
renaming, currency conversion, indicator generation, training or trading.
Different quote currencies require caller-side selection and interpretation.
Invalid selected closed candles, duplicate times, gaps and mismatched symbol
grids raise ValueError. A wholly empty window returns empty output.

The reader uses SQLite mode=ro plus immutable=1 and query_only, closes connections
on all paths, and never imports application modules. Core record output uses
only Python's standard library. The DataFrame wrapper additionally needs free
`pandas` installed locally; it performs no installation or network calls.
FinRL itself and API credentials are unnecessary. This is an OHLCV input adapter,
not a complete FinRL environment or feature pipeline.

Run only the isolated suite (other repository tests may start application code):

```text
python -m unittest -v test_finrl_data_adapter
```
