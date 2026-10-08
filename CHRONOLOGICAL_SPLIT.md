# Offline chronological split

`chronological_split.split_records` accepts a sequence/iterator of FinRL-style
record mappings with `date` and `tic`. It performs no IO, DB access, network,
model fitting or trading. Python standard library only. This independent module
can target main while the adapter and quality-report PRs remain open.

```python
from chronological_split import split_records

parts = split_records(
    records,
    validation_start="2024-07-01 00:00:00",
    test_start="2024-09-01 00:00:00",
    label_horizon_steps=1,
    embargo_steps=1,
)
train, validation, test = (parts[k] for k in ("train", "validation", "test"))
```

Dates use the adapter's canonical UTC `YYYY-MM-DD HH:MM:SS` format. Timezone
conversion is the caller's responsibility; ambiguous/local/mixed date formats
are rejected. Boundaries are explicit, stable and half open:
train [start, validation_start), validation [validation_start, test_start),
test [test_start, end). Optional start/end bound the selected history.

All symbols at a timestamp stay together. Input order does not affect results;
output sorts date/tic. Duplicate date/tic rows and unequal symbol grids in the
selected window fail rather than silently dropping or filling data. Each
retained partition must contain at least one timestamp. This structural minimum
does not guarantee sufficient observations for a model. Extra fields are deep
copied and input is not mutated; OHLCV validity belongs to the adapter/audit.

`label_horizon_steps` removes the final N observed timestamps of train and
validation. For a forward target using the next N observed timestamps, this
keeps labels inside their original partition. Test tails remain available for
evaluation; the caller must drop test samples whose forward labels are absent.
`embargo_steps` removes the first N timestamps of validation and test, creating
an optional separation. Counts refer to observed timestamp steps, not elapsed
hours/days. Use only a single consistent interval and check continuity first.
Overlapping or variable-duration targets require caller-specific purging.

Return keys include train/validation/test record lists, excluded date/tic rows
with partition and reason, and metadata with boundaries, options, symbols and
raw/retained timestamp counts. Rows outside optional start/end are not returned
as excluded; excluded records describe only purge/embargo within the window.

This prevents partition overlap, not every form of information leakage. Fit
scalers, imputers, feature selection and models on train only. Compute causal
features without centered windows or future backfill. Validation may use prior
history as read-only indicator warmup; never score warmup rows or fit on it.
Choose hyperparameters on validation and reserve test for final evaluation.
Do not precompute features/labels from future data and assume splitting fixes
them. No indicators, warmup synthesis, resampling or random splitting occurs.

Run isolated tests: `python -m unittest -v test_chronological_split`.
The tests check temporal boundaries, grouped symbols, purging forward labels,
embargo, conservation, deterministic ordering, mutation isolation, malformed
inputs and that changing future values does not change earlier outputs.
