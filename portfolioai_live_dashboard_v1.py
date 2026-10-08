import csv
import json
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent

STATE = BASE / "multistrategy_live_state_v3.json"
SIGNALS = BASE / "multistrategy_live_signals_v3.csv"
TRADES = BASE / "multistrategy_live_trades_v3.csv"
RUNS = BASE / "multistrategy_live_runs_v3.csv"

MASTER_STATE = BASE / "zitar_master_portfolio_v1.json"
MASTER_EVENTS = BASE / "zitar_master_trade_events_v1.jsonl"
MASTER_BRIDGE = BASE / "zitar_master_execution_bridge_v1.json"
MASTER_WATERMARK = BASE / "zitar_master_trade_watermark_v1.json"

HOST = "127.0.0.1"
PORT = 5010

BOOK_URL = "https://api.binance.me/api/v3/ticker/bookTicker"

book_cache = {
    "time": 0.0,
    "data": {},
    "error": None,
}

book_lock = threading.Lock()


def D(value, default="0"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def f2(value):
    try:
        return f"{D(value):,.2f}"
    except Exception:
        return "0.00"


def read_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def read_csv(path):
    if not path.exists():
        return []

    try:
        with path.open(
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def get_book():
    now = time.time()

    with book_lock:
        if (
            book_cache["data"]
            and now - book_cache["time"] < 5
        ):
            return (
                book_cache["data"],
                book_cache["error"]
            )

    try:
        req = urllib.request.Request(
            BOOK_URL,
            headers={
                "User-Agent":
                    "PortfolioAI-Live-Paper-Dashboard/1.0"
            }
        )

        with urllib.request.urlopen(
            req,
            timeout=10
        ) as r:
            raw = json.loads(
                r.read().decode("utf-8")
            )

        data = {}

        for item in raw:
            symbol = item.get("symbol")

            if not symbol:
                continue

            data[symbol] = {
                "bid": item.get("bidPrice"),
                "ask": item.get("askPrice"),
            }

        with book_lock:
            book_cache["time"] = now
            book_cache["data"] = data
            book_cache["error"] = None

        return data, None

    except Exception as e:

        with book_lock:
            # Keep last known book if available.
            book_cache["time"] = now
            book_cache["error"] = str(e)

            return (
                book_cache["data"],
                book_cache["error"]
            )


def task_status():
    try:
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            (
                "$t=Get-ScheduledTask "
                "-TaskName 'PortfolioAI_MultiStrategy_Live';"
                "$i=Get-ScheduledTaskInfo "
                "-TaskName 'PortfolioAI_MultiStrategy_Live';"
                "[pscustomobject]@{"
                "State=[string]$t.State;"
                "LastRunTime=[string]$i.LastRunTime;"
                "LastTaskResult=[int]$i.LastTaskResult;"
                "NextRunTime=[string]$i.NextRunTime"
                "}|ConvertTo-Json -Compress"
            )
        ]

        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=(
                subprocess.CREATE_NO_WINDOW
                if hasattr(subprocess, "CREATE_NO_WINDOW")
                else 0
            )
        )

        if p.returncode == 0 and p.stdout.strip():
            return json.loads(p.stdout.strip())

    except Exception:
        pass

    return {
        "State": "UNKNOWN",
        "LastRunTime": "",
        "LastTaskResult": None,
        "NextRunTime": "",
    }



def build_master_snapshot():

    master = read_json(MASTER_STATE)
    bridge = read_json(MASTER_BRIDGE)
    watermark = read_json(MASTER_WATERMARK)

    account = master.get("account", {})
    period = master.get("current_period", {})
    lifetime = master.get("lifetime", {})

    positions_out = []

    for symbol, pos in account.get(
        "positions",
        {}
    ).items():

        positions_out.append({
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

    event_count = 0
    recent_events = []

    if MASTER_EVENTS.exists():

        lines = [
            x
            for x in MASTER_EVENTS.read_text(
                encoding="utf-8-sig"
            ).splitlines()
            if x.strip()
        ]

        event_count = len(lines)

        for line in lines[-10:][::-1]:
            try:
                recent_events.append(
                    json.loads(line)
                )
            except Exception:
                pass

    return {
        "status":
            "PASS"
            if master.get("schema")
            == "ZITAR_MASTER_PORTFOLIO_V1"
            else "MISSING",

        "period":
            period.get(
                "period_id",
                ""
            ),

        "equity":
            account.get(
                "equity_try",
                "0"
            ),

        "cash":
            account.get(
                "cash_try",
                "0"
            ),

        "position_value":
            account.get(
                "position_market_value_try",
                "0"
            ),

        "unrealized":
            account.get(
                "unrealized_pnl_try",
                "0"
            ),

        "realized":
            account.get(
                "realized_pnl_try",
                "0"
            ),

        "daily_realized":
            period.get(
                "daily_realized_pnl_try",
                "0"
            ),

        "daily_return_pct":
            period.get(
                "daily_return_pct",
                "0"
            ),

        "lifetime_realized":
            lifetime.get(
                "total_realized_pnl_try",
                "0"
            ),

        "open_positions":
            account.get(
                "open_position_count",
                len(positions_out)
            ),

        "slot_budget":
            period.get(
                "spot_slot_budget_try",
                "0"
            ),

        "positions":
            positions_out,

        "event_count":
            event_count,

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
            ),

        "detector_processed":
            len(
                watermark.get(
                    "processed_trade_ids",
                    []
                )
            ),

        "baseline_trades":
            watermark.get(
                "baseline_trade_count",
                0
            ),

        "recent_events":
            recent_events
    }


def build_snapshot():
    state = read_json(STATE)
    master = build_master_snapshot()
    signals = read_csv(SIGNALS)
    trades = read_csv(TRADES)
    runs = read_csv(RUNS)

    book, book_error = get_book()

    strategies = {}

    for name, account in state.get(
        "strategies",
        {}
    ).items():

        initial = D(
            account.get(
                "initial_cash_try",
                "10000"
            )
        )

        cash = D(
            account.get(
                "cash_try",
                "0"
            )
        )

        realized = D(
            account.get(
                "realized_pnl_try",
                "0"
            )
        )

        positions_out = []
        positions_value = Decimal("0")
        unrealized = Decimal("0")

        for symbol, pos in account.get(
            "positions",
            {}
        ).items():

            qty = D(
                pos.get(
                    "quantity",
                    "0"
                )
            )

            cost = D(
                pos.get(
                    "total_cost_try",
                    "0"
                )
            )

            b = book.get(
                symbol,
                {}
            )

            bid = D(
                b.get(
                    "bid",
                    pos.get(
                        "observed_entry_price",
                        "0"
                    )
                )
            )

            ask = D(
                b.get(
                    "ask",
                    bid
                )
            )

            value = qty * bid
            pnl = value - cost

            positions_value += value
            unrealized += pnl

            pnl_pct = (
                pnl / cost * Decimal("100")
                if cost > 0
                else Decimal("0")
            )

            positions_out.append({
                "symbol": symbol,
                "quantity": str(qty),
                "observed_entry":
                    pos.get(
                        "observed_entry_price",
                        ""
                    ),
                "modeled_entry":
                    pos.get(
                        "modeled_entry_price",
                        ""
                    ),
                "cost_try": str(cost),
                "bid": str(bid),
                "ask": str(ask),
                "value_try": str(value),
                "unrealized_try": str(pnl),
                "unrealized_pct": str(pnl_pct),
                "signal_close":
                    pos.get(
                        "signal_candle_close_utc",
                        ""
                    ),
                "executed_at":
                    pos.get(
                        "executed_at_utc",
                        ""
                    ),
            })

        equity = cash + positions_value

        total_return = (
            (equity - initial)
            / initial
            * Decimal("100")
            if initial > 0
            else Decimal("0")
        )

        strategies[name] = {
            "initial": str(initial),
            "cash": str(cash),
            "positions_value":
                str(positions_value),
            "equity": str(equity),
            "realized": str(realized),
            "unrealized": str(unrealized),
            "return_pct":
                str(total_return),
            "trade_count":
                account.get(
                    "trade_count",
                    0
                ),
            "positions":
                positions_out,
        }

    latest_candle = ""

    processed = state.get(
        "processed_candle_closes",
        []
    )

    if processed:
        latest_candle = processed[-1]

    latest_signals = []

    if signals:
        latest_signal_candle = signals[-1].get(
            "candle_close_utc",
            ""
        )

        if not latest_signal_candle:
            # tolerate alternate column naming
            latest_signal_candle = signals[-1].get(
                "signal_candle_close_utc",
                ""
            )

        for row in signals:
            c = (
                row.get("candle_close_utc")
                or row.get(
                    "signal_candle_close_utc"
                )
                or ""
            )

            if c == latest_signal_candle:
                latest_signals.append(row)

    active_signals = []

    for row in latest_signals:
        sig = (
            row.get("signal")
            or row.get("action")
            or ""
        ).upper()

        if sig in ("BUY", "SELL"):
            active_signals.append(row)

    latest_run = runs[-1] if runs else {}

    return {
        "generated_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),
        "mode": "PAPER",
        "real_orders": False,
        "state_status":
            state.get(
                "status",
                "UNKNOWN"
            ),
        "protocol":
            state.get(
                "active_protocol",
                "V3"
            ),
        "processed_count":
            len(processed),
        "latest_candle":
            latest_candle,
        "last_successful_run_utc":
            state.get(
                "last_successful_run_utc",
                ""
            ),
        "universe_count":
            len(
                state.get(
                    "universe",
                    []
                )
            ),
        "strategies":
            strategies,

        "master":
            master,

        "signals_total":
            len(signals),
        "trades_total":
            len(trades),
        "runs_total":
            len(runs),
        "latest_signals":
            latest_signals,
        "active_signals":
            active_signals,
        "recent_trades":
            trades[-20:][::-1],
        "recent_runs":
            runs[-10:][::-1],
        "latest_run":
            latest_run,
        "book_error":
            book_error,
        "scheduler":
            task_status(),
    }


HTML = r'''<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width,initial-scale=1">
<title>PortfolioAI Live Paper</title>

<style>
:root{
  --bg:#070b14;
  --panel:#101827;
  --panel2:#151f31;
  --line:#26344c;
  --text:#eef4ff;
  --muted:#94a3b8;
  --green:#22c55e;
  --red:#ef4444;
  --yellow:#f59e0b;
  --blue:#60a5fa;
  --purple:#a78bfa;
}

*{box-sizing:border-box}

body{
  margin:0;
  font-family:
    Inter,Segoe UI,Arial,sans-serif;
  background:
    radial-gradient(
      circle at top,
      #14203a 0,
      var(--bg) 42%
    );
  color:var(--text);
}

.wrap{
  max-width:1500px;
  margin:auto;
  padding:24px;
}

.top{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:20px;
  margin-bottom:20px;
}

.brand h1{
  margin:0;
  font-size:30px;
}

.brand small{
  color:var(--muted);
}

.badges{
  display:flex;
  gap:10px;
  flex-wrap:wrap;
  justify-content:flex-end;
}

.badge{
  padding:8px 12px;
  border-radius:999px;
  font-size:12px;
  font-weight:800;
  border:1px solid var(--line);
  background:#111827;
}

.green{color:var(--green)}
.red{color:var(--red)}
.yellow{color:var(--yellow)}
.blue{color:var(--blue)}
.muted{color:var(--muted)}

.grid{
  display:grid;
  grid-template-columns:
    repeat(4,minmax(0,1fr));
  gap:14px;
}

.stat{
  background:rgba(16,24,39,.92);
  border:1px solid var(--line);
  border-radius:16px;
  padding:16px;
}

.label{
  color:var(--muted);
  font-size:12px;
  text-transform:uppercase;
  letter-spacing:.7px;
}

.value{
  margin-top:7px;
  font-size:20px;
  font-weight:800;
}

.section{
  margin-top:22px;
}

.section h2{
  margin:0 0 12px;
  font-size:18px;
}

.strategies{
  display:grid;
  grid-template-columns:
    repeat(3,minmax(0,1fr));
  gap:14px;
}

.card{
  background:
    linear-gradient(
      180deg,
      rgba(21,31,49,.96),
      rgba(12,18,30,.96)
    );
  border:1px solid var(--line);
  border-radius:18px;
  padding:18px;
}

.card h3{
  margin:0 0 15px;
  font-size:20px;
}

.metrics{
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:12px;
}

.metric{
  background:#0b1220;
  border:1px solid #202d43;
  border-radius:12px;
  padding:12px;
}

.metric .v{
  font-weight:800;
  font-size:18px;
  margin-top:5px;
}

.position{
  margin-top:14px;
  background:#0a111e;
  border:1px solid #26344c;
  border-radius:14px;
  padding:14px;
}

.position-title{
  display:flex;
  justify-content:space-between;
  font-weight:800;
  margin-bottom:10px;
}

.posgrid{
  display:grid;
  grid-template-columns:
    repeat(3,1fr);
  gap:8px;
}

.positem{
  font-size:12px;
}

.positem strong{
  display:block;
  margin-top:3px;
  font-size:14px;
}

.tables{
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:14px;
}

.tablebox{
  overflow:auto;
  background:rgba(16,24,39,.94);
  border:1px solid var(--line);
  border-radius:16px;
}

table{
  width:100%;
  border-collapse:collapse;
  min-width:600px;
}

th,td{
  padding:11px 12px;
  border-bottom:1px solid #202c40;
  text-align:left;
  font-size:12px;
  white-space:nowrap;
}

th{
  color:var(--muted);
  background:#0d1524;
  position:sticky;
  top:0;
}

.signal-buy{
  color:var(--green);
  font-weight:900;
}

.signal-sell{
  color:var(--red);
  font-weight:900;
}

.signal-none{
  color:var(--muted);
}

.footer{
  margin-top:20px;
  text-align:center;
  color:var(--muted);
  font-size:12px;
}

.dot{
  display:inline-block;
  width:8px;
  height:8px;
  border-radius:50%;
  background:var(--green);
  margin-right:6px;
  box-shadow:0 0 10px var(--green);
}

@media(max-width:1000px){
  .grid{grid-template-columns:1fr 1fr}
  .strategies{grid-template-columns:1fr}
  .tables{grid-template-columns:1fr}
}

@media(max-width:600px){
  .grid{grid-template-columns:1fr}
  .top{align-items:flex-start;flex-direction:column}
  .badges{justify-content:flex-start}
}
</style>
</head>

<body>
<div class="wrap">

<div class="top">
  <div class="brand">
    <h1>PortfolioAI</h1>
    <small>
      Multi-Strategy Live Paper Dashboard
    </small>
  </div>

  <div class="badges">
    <span class="badge green">
      ● PAPER MODE
    </span>
    <span class="badge red">
      REAL ORDERS: OFF
    </span>
    <span class="badge blue" id="clock">
      --
    </span>
  </div>
</div>

<div class="grid">
  <div class="stat">
    <div class="label">V3 Status</div>
    <div class="value" id="status">--</div>
  </div>

  <div class="stat">
    <div class="label">Son İşlenen Mum</div>
    <div class="value" id="candle">--</div>
  </div>

  <div class="stat">
    <div class="label">Prospective Runs</div>
    <div class="value" id="runs">--</div>
  </div>

  <div class="stat">
    <div class="label">Scheduler</div>
    <div class="value" id="scheduler">--</div>
  </div>
</div>


<div class="section">
  <h2>Strateji Hesapları</h2>
  <div class="strategies" id="strategies">
  </div>
</div>


<div class="section">
  <h2>Son Mum — Aktif Sinyaller</h2>
  <div class="tablebox">
    <table>
      <thead>
        <tr>
          <th>Strateji</th>
          <th>Parite</th>
          <th>Sinyal</th>
          <th>Mum</th>
        </tr>
      </thead>
      <tbody id="activeSignals"></tbody>
    </table>
  </div>
</div>


<div class="section">
  <h2>Son 63 Sinyal</h2>
  <div class="tablebox"
       style="max-height:390px">
    <table>
      <thead>
        <tr>
          <th>Strateji</th>
          <th>Parite</th>
          <th>Sinyal</th>
          <th>Mum</th>
        </tr>
      </thead>
      <tbody id="signals"></tbody>
    </table>
  </div>
</div>


<div class="section">
  <div class="tables">

    <div>
      <h2>Paper Trade Geçmişi</h2>
      <div class="tablebox">
        <table>
          <thead>
            <tr>
              <th>Strateji</th>
              <th>Parite</th>
              <th>İşlem</th>
              <th>Zaman</th>
            </tr>
          </thead>
          <tbody id="trades"></tbody>
        </table>
      </div>
    </div>

    <div>
      <h2>V3 Run Geçmişi</h2>
      <div class="tablebox">
        <table>
          <thead>
            <tr>
              <th>Mum</th>
              <th>Sinyal</th>
              <th>Trade</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody id="runHistory"></tbody>
        </table>
      </div>
    </div>

  </div>
</div>


<div class="footer">
  <span class="dot"></span>
  Read-only dashboard •
  Binance TR market data •
  No order endpoint •
  Auto refresh: 5 seconds
</div>

</div>


<script>
const fmt = n => {
  const x = Number(n || 0);
  return x.toLocaleString(
    'tr-TR',
    {
      minimumFractionDigits:2,
      maximumFractionDigits:2
    }
  );
};

const pct = n =>
  Number(n || 0).toFixed(2) + '%';

const pnlClass = n =>
  Number(n || 0) >= 0 ? 'green' : 'red';

const get = (o, keys, fallback='') => {
  for(const k of keys){
    if(o && o[k] !== undefined &&
       o[k] !== null &&
       o[k] !== ''){
      return o[k];
    }
  }
  return fallback;
};

function strategyName(row){
  return get(
    row,
    ['strategy','strategy_name'],
    ''
  );
}

function symbolName(row){
  return get(
    row,
    ['symbol','pair'],
    ''
  );
}

function signalName(row){
  return String(
    get(
      row,
      ['signal','action'],
      'NONE'
    )
  ).toUpperCase();
}

function candleName(row){
  return get(
    row,
    [
      'candle_close_utc',
      'signal_candle_close_utc'
    ],
    ''
  );
}

function renderMaster(m){
  if(!m || !m.exists){
    return `
      <div class="card">
        <div class="red">
          Master state bulunamad?
        </div>
      </div>
    `;
  }

  const positions = m.positions || [];

  let positionHtml = '';

  if(!positions.length){
    positionHtml = `
      <div class="position muted">
        A??k Master pozisyonu yok
      </div>
    `;
  } else {
    positionHtml = positions.map(p => `
      <div class="position">

        <div class="position-title">
          <span>${p.symbol}</span>
          <span class="${pnlClass(p.unrealized_try)}">
            ${fmt(p.unrealized_try)} TRY
          </span>
        </div>

        <div class="posgrid">

          <div class="positem">
            Stratejiler
            <strong>
              ${(p.strategies || []).join(', ') || '--'}
            </strong>
          </div>

          <div class="positem">
            Miktar
            <strong>${p.quantity}</strong>
          </div>

          <div class="positem">
            Entry Reference
            <strong>${p.entry_reference}</strong>
          </div>

          <div class="positem">
            Entry Fill
            <strong>${p.entry_fill}</strong>
          </div>

          <div class="positem">
            Last Mark
            <strong class="blue">
              ${p.last_mark}
            </strong>
          </div>

          <div class="positem">
            Pozisyon De?eri
            <strong>
              ${fmt(p.market_value_try)} TRY
            </strong>
          </div>

        </div>
      </div>
    `).join('');
  }

  return `
    <div class="card">

      <h3>
        ZITAR MASTER
        <span class="green">
          ? ${m.mode || '--'}
        </span>
      </h3>

      <div class="metrics">

        <div class="metric">
          <div class="label">Equity</div>
          <div class="v">
            ${fmt(m.equity)} TRY
          </div>
        </div>

        <div class="metric">
          <div class="label">Cash</div>
          <div class="v">
            ${fmt(m.cash)} TRY
          </div>
        </div>

        <div class="metric">
          <div class="label">Position Value</div>
          <div class="v">
            ${fmt(m.position_value)} TRY
          </div>
        </div>

        <div class="metric">
          <div class="label">Unrealized P/L</div>
          <div class="v ${pnlClass(m.unrealized)}">
            ${fmt(m.unrealized)} TRY
          </div>
        </div>

        <div class="metric">
          <div class="label">Daily Realized P/L</div>
          <div class="v ${pnlClass(m.daily_realized)}">
            ${fmt(m.daily_realized)} TRY
          </div>
        </div>

        <div class="metric">
          <div class="label">Daily Return</div>
          <div class="v ${pnlClass(m.daily_return_pct)}">
            ${pct(m.daily_return_pct)}
          </div>
        </div>

        <div class="metric">
          <div class="label">Lifetime Realized</div>
          <div class="v ${pnlClass(m.lifetime_realized)}">
            ${fmt(m.lifetime_realized)} TRY
          </div>
        </div>

        <div class="metric">
          <div class="label">Open Positions</div>
          <div class="v">
            ${m.open_positions || 0}
          </div>
        </div>

        <div class="metric">
          <div class="label">Daily Slot</div>
          <div class="v">
            ${fmt(m.slot_budget)} TRY
          </div>
        </div>

        <div class="metric">
          <div class="label">Period</div>
          <div class="v">
            ${m.period_id || '--'}
          </div>
        </div>

      </div>

      ${positionHtml}

      <div class="position">
        <div class="position-title">
          <span>Master Pipeline</span>
          <span class="green">ACTIVE</span>
        </div>

        <div class="posgrid">

          <div class="positem">
            Baseline Trades
            <strong>${m.baseline_trades || 0}</strong>
          </div>

          <div class="positem">
            Detector Processed
            <strong>${m.detector_processed || 0}</strong>
          </div>

          <div class="positem">
            Master Events
            <strong>${m.master_events || 0}</strong>
          </div>

          <div class="positem">
            Bridge Processed
            <strong>${m.bridge_processed || 0}</strong>
          </div>

          <div class="positem">
            Master Processed
            <strong>${m.master_processed || 0}</strong>
          </div>

          <div class="positem">
            Real Orders
            <strong class="red">
              ${m.real_order_authority ? 'ON' : 'OFF'}
            </strong>
          </div>

        </div>
      </div>

    </div>
  `;
}


function renderStrategy(name,s){
  let positions = '';

  if(!s.positions.length){
    positions = `
      <div class="position muted">
        Açık pozisyon yok
      </div>
    `;
  } else {
    positions = s.positions.map(p => `
      <div class="position">

        <div class="position-title">
          <span>${p.symbol}</span>
          <span class="${pnlClass(p.unrealized_try)}">
            ${fmt(p.unrealized_try)} TRY
            (${pct(p.unrealized_pct)})
          </span>
        </div>

        <div class="posgrid">

          <div class="positem">
            Maliyet
            <strong>
              ${fmt(p.cost_try)} TRY
            </strong>
          </div>

          <div class="positem">
            Modeled Entry
            <strong>
              ${p.modeled_entry}
            </strong>
          </div>

          <div class="positem">
            Canlı Bid
            <strong class="blue">
              ${p.bid}
            </strong>
          </div>

          <div class="positem">
            Canlı Ask
            <strong>
              ${p.ask}
            </strong>
          </div>

          <div class="positem">
            Pozisyon Değeri
            <strong>
              ${fmt(p.value_try)} TRY
            </strong>
          </div>

          <div class="positem">
            Miktar
            <strong>
              ${p.quantity}
            </strong>
          </div>

        </div>
      </div>
    `).join('');
  }

  return `
    <div class="card">
      <h3>${name}</h3>

      <div class="metrics">

        <div class="metric">
          <div class="label">Equity</div>
          <div class="v">
            ${fmt(s.equity)} TRY
          </div>
        </div>

        <div class="metric">
          <div class="label">Cash</div>
          <div class="v">
            ${fmt(s.cash)} TRY
          </div>
        </div>

        <div class="metric">
          <div class="label">Unrealized PnL</div>
          <div class="v ${pnlClass(s.unrealized)}">
            ${fmt(s.unrealized)} TRY
          </div>
        </div>

        <div class="metric">
          <div class="label">Return</div>
          <div class="v ${pnlClass(s.return_pct)}">
            ${pct(s.return_pct)}
          </div>
        </div>

        <div class="metric">
          <div class="label">Realized PnL</div>
          <div class="v ${pnlClass(s.realized)}">
            ${fmt(s.realized)} TRY
          </div>
        </div>

        <div class="metric">
          <div class="label">Positions</div>
          <div class="v">
            ${s.positions.length}
          </div>
        </div>

      </div>

      ${positions}
    </div>
  `;
}


function signalRow(r){
  const sig = signalName(r);

  let cls = 'signal-none';

  if(sig === 'BUY') cls = 'signal-buy';
  if(sig === 'SELL') cls = 'signal-sell';

  return `
    <tr>
      <td>${strategyName(r)}</td>
      <td>${symbolName(r)}</td>
      <td class="${cls}">
        ${sig}
      </td>
      <td>${candleName(r)}</td>
    </tr>
  `;
}


async function refresh(){
  try{
    const response = await fetch(
      '/api/dashboard',
      {cache:'no-store'}
    );

    const d = await response.json();

    document.getElementById(
      'clock'
    ).textContent =
      new Date().toLocaleTimeString('tr-TR');

    document.getElementById(
      'status'
    ).innerHTML =
      `<span class="green">
         ${d.state_status || 'OK'}
       </span>`;

    document.getElementById(
      'candle'
    ).textContent =
      d.latest_candle || '--';

    document.getElementById(
      'runs'
    ).textContent =
      d.runs_total;

    const sched = d.scheduler || {};

    const schedState =
      sched.State || 'UNKNOWN';

    const schedClass =
      schedState === 'Ready'
      ? 'green'
      : 'yellow';

    document.getElementById(
      'scheduler'
    ).innerHTML =
      `<span class="${schedClass}">
         ${schedState}
       </span>`;

    document.getElementById(
      'masterPortfolio'
    ).innerHTML =
      renderMaster(d.master);

    const order = [
      'SMA20_50',
      'EMA12_26',
      'RSI14'
    ];

    document.getElementById(
      'strategies'
    ).innerHTML =
      order
      .filter(x => d.strategies[x])
      .map(
        x => renderStrategy(
          x,
          d.strategies[x]
        )
      )
      .join('');

    const active =
      d.active_signals || [];

    document.getElementById(
      'activeSignals'
    ).innerHTML =
      active.length
      ? active.map(signalRow).join('')
      : `<tr>
           <td colspan="4"
               class="muted">
             Aktif BUY/SELL sinyali yok
           </td>
         </tr>`;

    document.getElementById(
      'signals'
    ).innerHTML =
      (d.latest_signals || [])
      .map(signalRow)
      .join('');

    const trades =
      d.recent_trades || [];

    document.getElementById(
      'trades'
    ).innerHTML =
      trades.length
      ? trades.map(r => `
          <tr>
            <td>
              ${strategyName(r)}
            </td>
            <td>
              ${symbolName(r)}
            </td>
            <td>
              ${get(
                r,
                ['side','action','signal'],
                ''
              )}
            </td>
            <td>
              ${get(
                r,
                [
                  'executed_at_utc',
                  'execution_utc',
                  'run_utc'
                ],
                ''
              )}
            </td>
          </tr>
        `).join('')
      : `<tr>
           <td colspan="4"
               class="muted">
             Henüz V3 paper trade yok
           </td>
         </tr>`;

    const runs =
      d.recent_runs || [];

    document.getElementById(
      'runHistory'
    ).innerHTML =
      runs.length
      ? runs.map(r => `
          <tr>
            <td>
              ${get(
                r,
                ['candle_close_utc'],
                ''
              )}
            </td>
            <td>
              ${get(
                r,
                ['signal_rows'],
                ''
              )}
            </td>
            <td>
              ${get(
                r,
                ['paper_trades'],
                ''
              )}
            </td>
            <td class="green">
              ${get(
                r,
                ['status'],
                ''
              )}
            </td>
          </tr>
        `).join('')
      : `<tr>
           <td colspan="4"
               class="muted">
             Run kaydı yok
           </td>
         </tr>`;

  }catch(e){
    document.getElementById(
      'status'
    ).innerHTML =
      `<span class="red">
         DASHBOARD ERROR
       </span>`;
  }
}

refresh();
setInterval(refresh,5000);
</script>

</body>
</html>
'''


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        return

    def send_bytes(
        self,
        body,
        content_type,
        status=200
    ):
        self.send_response(status)

        self.send_header(
            "Content-Type",
            content_type
        )

        self.send_header(
            "Cache-Control",
            "no-store"
        )

        self.send_header(
            "Content-Length",
            str(len(body))
        )

        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):

        if self.path in (
            "/",
            "/index.html"
        ):
            body = HTML.encode("utf-8")

            return self.send_bytes(
                body,
                "text/html; charset=utf-8"
            )

        if self.path.startswith(
            "/api/dashboard"
        ):
            try:
                snapshot = build_snapshot()

                body = json.dumps(
                    snapshot,
                    ensure_ascii=False
                ).encode("utf-8")

                return self.send_bytes(
                    body,
                    "application/json; charset=utf-8"
                )

            except Exception as e:

                body = json.dumps(
                    {
                        "error": str(e),
                        "real_orders": False
                    },
                    ensure_ascii=False
                ).encode("utf-8")

                return self.send_bytes(
                    body,
                    "application/json; charset=utf-8",
                    500
                )

        self.send_bytes(
            b"Not Found",
            "text/plain",
            404
        )


if __name__ == "__main__":

    print("=" * 70)
    print("PORTFOLIOAI LIVE PAPER DASHBOARD")
    print("=" * 70)
    print(
        f"URL         : http://{HOST}:{PORT}"
    )
    print(
        "MODE        : PAPER / READ ONLY"
    )
    print(
        "REAL ORDERS : NO"
    )
    print(
        "REFRESH     : 5 seconds"
    )
    print("=" * 70)

    server = ThreadingHTTPServer(
        (HOST, PORT),
        Handler
    )

    server.serve_forever()
