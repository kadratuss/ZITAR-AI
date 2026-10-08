# Offline historical data quality report

Run `python historical_quality_report.py /path/to/offline_snapshot.db
--as-of-ms 1700000000000` as a single command. JSON is printed to stdout; the
tool never creates a report file. Optionally capture stdout to a separate file
in your own analysis folder, never to a database or application file.

Use a separately prepared, checkpointed offline SQLite snapshot. The tool
refuses paths with -wal, -shm or -journal sidecars. SQLite opens with mode=ro,
immutable=1 and query_only. This requires no concurrent writers; the sidecar
check cannot prove a file is offline. The tool does not copy, checkpoint or
repair any database, start services, import application modules or use network.
Only Python's standard library is required; no paid service or credentials.

Schema is based on `long_history_collector.py`'s historical_candles table.
All groups are audited, including unsupported intervals. Fixed 1h/1d intervals
use the existing collector's timestamp rules. Prices must be finite and
positive; volume finite and nonnegative; low <= open/close <= high.

The report contains:

- Total stored rows, symbol/interval groups and reproducible as_of_ms.
- Invalid identity, unsupported interval, malformed timestamps, OHLCV and
  duplicate opening-time counts. A row can contribute to multiple issue counts.
- Unclosed/future row counts, excluded from valid coverage; close == as_of_ms
  is still unclosed, matching the adapter.
- Unique valid closed candles, first/last opening millisecond timestamps,
  longest contiguous run, expected/missing candles and coverage ratio **within
  the observed valid span only**. This does not measure missing leading/trailing
  history, freshness or a requested external date window. Zero valid candles
  gives null bounds/coverage, not a misleading 100% result.
- Per-interval union/common valid timestamps and identical-grid flag for all
  stored symbols. This does not choose a trading universe or convert currencies.
- Bounded examples (default 20 per issue/group, set --sample-limit); exact
  counts remain unchanged. Large gaps are represented as ranges, not expanded.

Exit codes: 0 = nonempty groups with valid closed data, no issues/gaps and
matching grids; 1 = attention (including empty data); 2 = input/schema/SQLite
failure. Unclosed rows alone do not fail otherwise healthy closed history.
Duplicate counts are extra rows after the first occurrence, even when values
agree. The first valid occurrence can count toward unique coverage; duplicate
issues still make the report require attention. The report is diagnostic and
does not certify training readiness or backtest profitability.

Memory scales with distinct stored timestamps for coverage/alignment, not gap
length. Rows stream from SQLite; example lists are capped per group. FinRL
adapter and this tool are independent, allowing this PR to target main while
the adapter PR remains open.

Validation: `python -m unittest -v test_historical_quality_report` uses only
temporary fixtures, including a relaxed schema to exercise duplicates and
malformed legacy data. No production database is available in this repository;
actual production quality has not been measured. Avoid running unrelated test
discovery because existing tests may import or operate application services.
