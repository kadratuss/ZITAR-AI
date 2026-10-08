from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from flask import Flask, jsonify, render_template_string

BASE = Path(__file__).resolve().parent

MASTER = BASE / "zitar_master_portfolio_v1.json"
EVENTS = BASE / "zitar_master_trade_events_v1.jsonl"
WATERMARK = BASE / "zitar_master_trade_watermark_v1.json"
BRIDGE = BASE / "zitar_master_execution_bridge_v1.json"

app = Flask(__name__)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}

    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def read_events() -> list[dict]:
    if not EVENTS.exists():
        return []

    result = []

    for line in EVENTS.read_text(
        encoding="utf-8-sig"
    ).splitlines():

        if not line.strip():
            continue

        result.append(json.loads(line))

    return result


def D(value) -> Decimal:
    return Decimal(str(value or "0"))


def master_payload() -> dict:

    if not MASTER.exists():
        return {
            "status": "FAIL",
            "error": "Master state not found"
        }

    master = load_json(MASTER)

    if master.get("schema") != \
            "ZITAR_MASTER_PORTFOLIO_V1":
        return {
            "status": "FAIL",
            "error": "Unexpected Master schema"
        }

    account = master.get("account", {})
    period = master.get("current_period", {})
    lifetime = master.get("lifetime", {})
    positions = account.get("positions", {})

    watermark = load_json(WATERMARK)
    bridge = load_json(BRIDGE)
    events = read_events()

    position_rows = []

    for symbol, pos in positions.items():

        position_rows.append({
            "symbol":
                symbol,

            "strategies":
                pos.get(
                    "strategy_support",
                    []
                ),

            "quantity":
                pos.get(
                    "quantity",
                    "0"
                ),

            "entry_reference":
                pos.get(
                    "entry_reference_price",
                    "0"
                ),

            "entry_fill":
                pos.get(
                    "entry_fill_price",
                    "0"
                ),

            "last_mark":
                pos.get(
                    "last_mark_price",
                    "0"
                ),

            "market_value_try":
                pos.get(
                    "market_value_try",
                    "0"
                ),

            "unrealized_pnl_try":
                pos.get(
                    "unrealized_pnl_try",
                    "0"
                ),

            "opened_utc":
                pos.get(
                    "opened_utc",
                    ""
                )
        })

    recent_events = []

    for event in events[-20:][::-1]:

        recent_events.append({
            "time":
                event.get(
                    "executed_at_utc",
                    ""
                ),

            "side":
                event.get(
                    "side",
                    ""
                ),

            "strategy":
                event.get(
                    "strategy",
                    ""
                ),

            "symbol":
                event.get(
                    "symbol",
                    ""
                ),

            "reference_price":
                event.get(
                    "reference_price",
                    ""
                ),

            "trade_id":
                event.get(
                    "source_trade_id",
                    ""
                )
        })

    return {
        "status":
            "PASS",

        "generated_local":
            datetime.now().isoformat(
                timespec="seconds"
            ),

        "mode":
            master.get(
                "mode",
                "paper"
            ),

        "period": {
            "id":
                period.get(
                    "period_id",
                    ""
                ),

            "start_equity_try":
                period.get(
                    "start_equity_try",
                    "0"
                ),

            "current_equity_try":
                period.get(
                    "current_equity_try",
                    account.get(
                        "equity_try",
                        "0"
                    )
                ),

            "daily_realized_pnl_try":
                period.get(
                    "daily_realized_pnl_try",
                    "0"
                ),

            "daily_return_pct":
                period.get(
                    "daily_return_pct",
                    "0"
                ),

            "spot_slot_budget_try":
                period.get(
                    "spot_slot_budget_try",
                    "0"
                ),

            "closed_trade_count":
                period.get(
                    "closed_trade_count",
                    0
                )
        },

        "account": {
            "cash_try":
                account.get(
                    "cash_try",
                    "0"
                ),

            "equity_try":
                account.get(
                    "equity_try",
                    "0"
                ),

            "position_market_value_try":
                account.get(
                    "position_market_value_try",
                    "0"
                ),

            "realized_pnl_try":
                account.get(
                    "realized_pnl_try",
                    "0"
                ),

            "unrealized_pnl_try":
                account.get(
                    "unrealized_pnl_try",
                    "0"
                ),

            "open_position_count":
                account.get(
                    "open_position_count",
                    len(positions)
                )
        },

        "lifetime": {
            "realized_pnl_try":
                lifetime.get(
                    "total_realized_pnl_try",
                    "0"
                ),

            "closed_trade_count":
                lifetime.get(
                    "closed_trade_count",
                    0
                )
        },

        "positions":
            position_rows,

        "pipeline": {
            "baseline_trades":
                watermark.get(
                    "baseline_trade_count",
                    0
                ),

            "detector_processed":
                len(
                    watermark.get(
                        "processed_trade_ids",
                        []
                    )
                ),

            "events":
                len(events),

            "bridge_processed":
                len(
                    bridge.get(
                        "processed_event_ids",
                        []
                    )
                ),

            "master_processed":
                len(
                    master.get(
                        "processed_event_ids",
                        []
                    )
                )
        },

        "events":
            recent_events,

        "safety": {
            "paper_execution":
                True,

            "real_orders":
                False,

            "v3_write":
                False
        }
    }


@app.get("/api/master")
def api_master():
    return jsonify(master_payload())


HTML = r'''
<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width,initial-scale=1">

<title>ZITAR Master</title>

<style>

:root{
  --bg:#07101f;
  --panel:#0d192b;
  --panel2:#101f34;
  --line:#253752;
  --text:#eef4ff;
  --muted:#8ea0ba;
  --green:#20d987;
  --red:#ff5570;
  --blue:#49a8ff;
  --yellow:#ffc857;
}

*{
  box-sizing:border-box;
}

body{
  margin:0;
  background:var(--bg);
  color:var(--text);
  font-family:
    Inter,
    Segoe UI,
    Arial,
    sans-serif;
}

.wrap{
  max-width:1500px;
  margin:auto;
  padding:28px;
}

.top{
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:20px;
  margin-bottom:24px;
}

.brand h1{
  margin:0;
  font-size:32px;
  letter-spacing:1px;
}

.brand small{
  color:var(--muted);
}

.badges{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
}

.badge{
  border:1px solid var(--line);
  padding:8px 12px;
  border-radius:999px;
  font-size:12px;
  font-weight:800;
}

.green{
  color:var(--green);
}

.red{
  color:var(--red);
}

.blue{
  color:var(--blue);
}

.yellow{
  color:var(--yellow);
}

.grid{
  display:grid;
  grid-template-columns:
    repeat(4,minmax(0,1fr));
  gap:14px;
}

.stat{
  background:var(--panel);
  border:1px solid var(--line);
  border-radius:16px;
  padding:17px;
}

.label{
  color:var(--muted);
  font-size:11px;
  text-transform:uppercase;
  letter-spacing:.7px;
}

.value{
  margin-top:7px;
  font-size:22px;
  font-weight:800;
}

.section{
  margin-top:24px;
}

.section h2{
  font-size:18px;
  margin:0 0 12px;
}

.position-grid{
  display:grid;
  grid-template-columns:
    repeat(2,minmax(0,1fr));
  gap:14px;
}

.position{
  background:var(--panel);
  border:1px solid var(--line);
  border-radius:16px;
  padding:18px;
}

.position-head{
  display:flex;
  justify-content:space-between;
  gap:10px;
  align-items:center;
}

.symbol{
  font-size:22px;
  font-weight:900;
}

.support{
  margin-top:7px;
  color:var(--blue);
  font-weight:700;
}

.posdata{
  margin-top:15px;
  display:grid;
  grid-template-columns:
    repeat(3,minmax(0,1fr));
  gap:10px;
}

.item{
  background:#091425;
  border:1px solid #1d304c;
  border-radius:10px;
  padding:10px;
  font-size:12px;
  color:var(--muted);
}

.item strong{
  display:block;
  margin-top:5px;
  color:var(--text);
  font-size:14px;
}

.pipeline{
  display:grid;
  grid-template-columns:
    repeat(5,minmax(0,1fr));
  gap:12px;
}

.pipe{
  background:var(--panel);
  border:1px solid var(--line);
  border-radius:14px;
  padding:15px;
}

.pipe strong{
  display:block;
  font-size:22px;
  margin-top:6px;
}

.tablebox{
  overflow:auto;
  border:1px solid var(--line);
  border-radius:14px;
  background:var(--panel);
}

table{
  width:100%;
  border-collapse:collapse;
}

th,td{
  padding:12px 14px;
  border-bottom:1px solid #1d2d45;
  text-align:left;
  font-size:13px;
}

th{
  color:var(--muted);
  font-size:11px;
  text-transform:uppercase;
}

.footer{
  margin-top:25px;
  color:var(--muted);
  font-size:12px;
}

@media(max-width:900px){
  .grid{
    grid-template-columns:1fr 1fr;
  }

  .pipeline{
    grid-template-columns:1fr 1fr;
  }

  .position-grid{
    grid-template-columns:1fr;
  }
}

</style>
</head>

<body>

<div class="wrap">

<div class="top">

  <div class="brand">
    <h1>ZITAR MASTER</h1>
    <small>
      PortfolioAI Master Execution & Accounting
    </small>
  </div>

  <div class="badges">
    <span class="badge green">
      ● MASTER ONLINE
    </span>

    <span class="badge blue">
      PAPER EXECUTION
    </span>

    <span class="badge red">
      REAL ORDERS OFF
    </span>

    <span class="badge"
          id="clock">
      --
    </span>
  </div>

</div>


<div class="grid">

  <div class="stat">
    <div class="label">Master Equity</div>
    <div class="value"
         id="equity">--</div>
  </div>

  <div class="stat">
    <div class="label">Cash</div>
    <div class="value"
         id="cash">--</div>
  </div>

  <div class="stat">
    <div class="label">Position Value</div>
    <div class="value"
         id="positionValue">--</div>
  </div>

  <div class="stat">
    <div class="label">Open Positions</div>
    <div class="value"
         id="openPositions">--</div>
  </div>

  <div class="stat">
    <div class="label">Unrealized P/L</div>
    <div class="value"
         id="unrealized">--</div>
  </div>

  <div class="stat">
    <div class="label">Daily Realized</div>
    <div class="value"
         id="dailyRealized">--</div>
  </div>

  <div class="stat">
    <div class="label">Daily Return</div>
    <div class="value"
         id="dailyReturn">--</div>
  </div>

  <div class="stat">
    <div class="label">Daily Slot</div>
    <div class="value"
         id="slot">--</div>
  </div>

</div>


<div class="section">

  <h2>MASTER OPEN POSITIONS</h2>

  <div class="position-grid"
       id="positions">
  </div>

</div>


<div class="section">

  <h2>MASTER PIPELINE</h2>

  <div class="pipeline">

    <div class="pipe">
      <span class="label">
        V3 Baseline
      </span>
      <strong id="baseline">--</strong>
    </div>

    <div class="pipe">
      <span class="label">
        Detector
      </span>
      <strong id="detector">--</strong>
    </div>

    <div class="pipe">
      <span class="label">
        Events
      </span>
      <strong id="eventsCount">--</strong>
    </div>

    <div class="pipe">
      <span class="label">
        Bridge
      </span>
      <strong id="bridge">--</strong>
    </div>

    <div class="pipe">
      <span class="label">
        Master
      </span>
      <strong id="masterProcessed">--</strong>
    </div>

  </div>

</div>


<div class="section">

<h2>RECENT MASTER EVENTS</h2>

<div class="tablebox">

<table>

<thead>
<tr>
  <th>Time</th>
  <th>Side</th>
  <th>Strategy</th>
  <th>Symbol</th>
  <th>Reference</th>
  <th>Trade ID</th>
</tr>
</thead>

<tbody id="eventRows"></tbody>

</table>

</div>
</div>


<div class="footer">
  ZITAR Master • Auto refresh 3 seconds •
  Paper execution enabled •
  Real order authority OFF •
  V3 write authority OFF
</div>

</div>


<script>

const money = value =>
  Number(value || 0).toLocaleString(
    'tr-TR',
    {
      minimumFractionDigits:2,
      maximumFractionDigits:2
    }
  ) + ' TRY';


const pnlClass = value =>
  Number(value || 0) >= 0
  ? 'green'
  : 'red';


function renderPositions(rows){

  const root =
    document.getElementById(
      'positions'
    );

  if(!rows.length){
    root.innerHTML = `
      <div class="position">
        <span class="green">
          Açık Master pozisyonu yok.
        </span>
      </div>
    `;
    return;
  }

  root.innerHTML =
    rows.map(p => `

      <div class="position">

        <div class="position-head">

          <span class="symbol">
            ${p.symbol}
          </span>

          <span class="
            ${pnlClass(
              p.unrealized_pnl_try
            )}
          ">
            ${money(
              p.unrealized_pnl_try
            )}
          </span>

        </div>

        <div class="support">
          ${p.strategies.join(', ')}
        </div>

        <div class="posdata">

          <div class="item">
            Quantity
            <strong>
              ${p.quantity}
            </strong>
          </div>

          <div class="item">
            Entry Reference
            <strong>
              ${p.entry_reference}
            </strong>
          </div>

          <div class="item">
            Entry Fill
            <strong>
              ${p.entry_fill}
            </strong>
          </div>

          <div class="item">
            Last Mark
            <strong>
              ${p.last_mark}
            </strong>
          </div>

          <div class="item">
            Market Value
            <strong>
              ${money(
                p.market_value_try
              )}
            </strong>
          </div>

          <div class="item">
            Opened UTC
            <strong>
              ${p.opened_utc}
            </strong>
          </div>

        </div>

      </div>

    `).join('');
}


async function refresh(){

  try{

    const r = await fetch(
      '/api/master',
      {
        cache:'no-store'
      }
    );

    const d = await r.json();

    if(d.status !== 'PASS'){
      throw new Error(
        d.error || 'Master API failed'
      );
    }

    document.getElementById(
      'clock'
    ).textContent =
      new Date().toLocaleTimeString(
        'tr-TR'
      );

    const a = d.account;
    const p = d.period;

    document.getElementById(
      'equity'
    ).textContent =
      money(a.equity_try);

    document.getElementById(
      'cash'
    ).textContent =
      money(a.cash_try);

    document.getElementById(
      'positionValue'
    ).textContent =
      money(
        a.position_market_value_try
      );

    document.getElementById(
      'openPositions'
    ).textContent =
      a.open_position_count;

    const u =
      document.getElementById(
        'unrealized'
      );

    u.textContent =
      money(a.unrealized_pnl_try);

    u.className =
      'value ' +
      pnlClass(
        a.unrealized_pnl_try
      );

    const dr =
      document.getElementById(
        'dailyRealized'
      );

    dr.textContent =
      money(
        p.daily_realized_pnl_try
      );

    dr.className =
      'value ' +
      pnlClass(
        p.daily_realized_pnl_try
      );

    const ret =
      document.getElementById(
        'dailyReturn'
      );

    ret.textContent =
      Number(
        p.daily_return_pct || 0
      ).toFixed(4) + ' %';

    ret.className =
      'value ' +
      pnlClass(
        p.daily_return_pct
      );

    document.getElementById(
      'slot'
    ).textContent =
      money(
        p.spot_slot_budget_try
      );

    renderPositions(
      d.positions || []
    );

    const pipe = d.pipeline;

    document.getElementById(
      'baseline'
    ).textContent =
      pipe.baseline_trades;

    document.getElementById(
      'detector'
    ).textContent =
      pipe.detector_processed;

    document.getElementById(
      'eventsCount'
    ).textContent =
      pipe.events;

    document.getElementById(
      'bridge'
    ).textContent =
      pipe.bridge_processed;

    document.getElementById(
      'masterProcessed'
    ).textContent =
      pipe.master_processed;

    document.getElementById(
      'eventRows'
    ).innerHTML =
      (d.events || [])
      .map(e => `

        <tr>

          <td>
            ${e.time}
          </td>

          <td class="${
            e.side === 'BUY'
            ? 'green'
            : 'red'
          }">
            ${e.side}
          </td>

          <td>
            ${e.strategy}
          </td>

          <td>
            ${e.symbol}
          </td>

          <td>
            ${e.reference_price}
          </td>

          <td>
            ${e.trade_id.slice(0,12)}
          </td>

        </tr>

      `).join('');

  }
  catch(err){

    console.error(err);

  }

}


refresh();

setInterval(
  refresh,
  3000
);

</script>

</body>
</html>
'''


@app.get("/")
def index():
    return render_template_string(HTML)


if __name__ == "__main__":

    print("ZITAR MASTER WEB DASHBOARD V1")
    print("MASTER READ ONLY WEB UI")
    print("REAL ORDERS: OFF")
    print("V3 WRITE: OFF")
    print()
    print("OPEN:")
    print("http://127.0.0.1:5010")
    print()

    app.run(
        host="127.0.0.1",
        port=5010,
        debug=False
    )
