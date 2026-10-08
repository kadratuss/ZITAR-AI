# Unified research console

Standalone preview:

```sh
python -m zitar_next.dashboard --root research_artifacts/next-release --history-root research_artifacts --port 8768
```

One menu combines current spot / isolated 3x futures learning, human strategy
decisions, historical spot experiments, benchmarks, candles and manual public
market checks. Historical metrics remain explicitly separate from current learning.
Opening this page never starts training. The existing independent worker continues.

## Future ZITAR dashboard installation (not applied)

For an ASGI / FastAPI host, after reviewing the actual dashboard and preserving
its authentication middleware, explicitly mount the component:

```python
from zitar_next.integration import mount_fastapi

mount_fastapi(app, root=NEXT_RESEARCH_DIRECTORY,
              history_root=HISTORICAL_REPORT_DIRECTORY,
              origin='http://127.0.0.1:YOUR_DASHBOARD_PORT',
              prefix='/zitar-next')
```

Replace the example port with the actual numeric local dashboard port. Add one
menu link to `/zitar-next/`: **Araştırma ve öğrenme**. No iframe, cross-origin
API permission or separate frontend port is required. Frontend requests honor
the mount prefix. Exact Host, Origin and CSRF checks remain enabled. Remote
hosting is intentionally unsupported by this loopback component.

This preparation does not modify the running ZITAR dashboard, main branch,
production databases or service settings. The mount starts no process and opens
only the dedicated Next registry plus explicitly selected report files. Historical
files are read-only. Decisions affect only Next paper; no broker/order API exists.
Accepting a strategy and activating it remain separate human decisions.
