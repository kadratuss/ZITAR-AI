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

HOST = "127.0.0.1"
PORT = 5013

BOOK_URL = "https://api.binance.me/api/v3/ticker/bookTicker"

book_cache = {
    "time": 0.0,
    "data": {},
    "error": None,
}

book_lock = threading.Lock()


RESEARCH_API = "http://127.0.0.1:5012"

def research_api_get(path):
    """Read-only proxy to the local ZİTAR Research/RAG API."""
    req = urllib.request.Request(
        RESEARCH_API + path,
        headers={"User-Agent": "ZITAR-Control-Center/2.2"}
    )
    with urllib.request.urlopen(req, timeout=4) as r:
        return json.loads(r.read().decode("utf-8"))


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
                    "ZITAR-Control-Center/2.0"
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


def build_snapshot():
    state = read_json(STATE)
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


HTML = r'''<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ZİTAR Control Center</title>
<style>
:root{--bg:#070b14;--panel:#101827;--panel2:#151f31;--line:#26344c;--text:#eef4ff;--muted:#94a3b8;--green:#22c55e;--red:#ef4444;--yellow:#f59e0b;--blue:#60a5fa;--purple:#a78bfa}*{box-sizing:border-box}body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:radial-gradient(circle at top,#14203a 0,var(--bg) 42%);color:var(--text)}button{font:inherit}.wrap{max-width:1600px;margin:auto;padding:20px}.top{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:14px}.brand h1{margin:0;font-size:34px;letter-spacing:1px}.brand small{color:var(--muted)}.actions,.badges{display:flex;gap:9px;flex-wrap:wrap;align-items:center}.badge,.btn{padding:8px 12px;border-radius:999px;font-size:12px;font-weight:800;border:1px solid var(--line);background:#111827;color:var(--text)}.btn{cursor:pointer}.btn:hover{border-color:var(--blue)}.btn.disabled{opacity:.5;cursor:not-allowed}.green{color:var(--green)}.red{color:var(--red)}.yellow{color:var(--yellow)}.blue{color:var(--blue)}.purple{color:var(--purple)}.muted{color:var(--muted)}.nav{display:flex;gap:7px;overflow:auto;padding:9px 0 16px}.nav button{white-space:nowrap}.hero{display:grid;grid-template-columns:1.4fr 1fr;gap:14px}.panel,.stat,.card,.module{background:rgba(16,24,39,.94);border:1px solid var(--line);border-radius:16px}.panel{padding:18px}.total{font-size:34px;font-weight:900;margin-top:6px}.subgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:14px}.mini{background:#0b1220;border:1px solid #202d43;border-radius:12px;padding:11px}.label{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.7px}.value{margin-top:6px;font-size:18px;font-weight:800}.health{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:12px}.healthitem{display:flex;justify-content:space-between;gap:10px;background:#0b1220;border:1px solid #202d43;border-radius:10px;padding:10px;font-size:12px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-top:14px}.stat{padding:14px}.section{margin-top:20px}.section h2{font-size:17px;margin:0 0 11px}.strategies{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.card{padding:16px;background:linear-gradient(180deg,rgba(21,31,49,.96),rgba(12,18,30,.96))}.card h3{margin:0 0 12px}.metrics{display:grid;grid-template-columns:1fr 1fr;gap:9px}.metric{background:#0b1220;border:1px solid #202d43;border-radius:11px;padding:10px}.metric .v{font-weight:800;font-size:16px;margin-top:4px}.position{margin-top:11px;background:#0a111e;border:1px solid #26344c;border-radius:12px;padding:12px}.position-title{display:flex;justify-content:space-between;gap:8px;font-weight:800;margin-bottom:8px}.posgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}.positem{font-size:11px;color:var(--muted)}.positem strong{display:block;color:var(--text);font-size:13px;margin-top:2px}.modules{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.module{padding:15px}.modulehead{display:flex;justify-content:space-between;align-items:center;gap:8px}.module h3{font-size:14px;margin:0}.module p{color:var(--muted);font-size:12px;line-height:1.5;margin:9px 0 0}.tables{display:grid;grid-template-columns:1fr 1fr;gap:12px}.tablebox{overflow:auto;background:rgba(16,24,39,.94);border:1px solid var(--line);border-radius:14px}table{width:100%;border-collapse:collapse;min-width:560px}th,td{padding:10px 11px;border-bottom:1px solid #202c40;text-align:left;font-size:12px;white-space:nowrap}th{color:var(--muted);background:#0d1524;position:sticky;top:0}.signal-buy{color:var(--green);font-weight:900}.signal-sell{color:var(--red);font-weight:900}.signal-none{color:var(--muted)}.controlnote{font-size:11px;color:var(--yellow);margin-top:8px}.footer{margin:18px 0 5px;text-align:center;color:var(--muted);font-size:11px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--green);margin-right:6px;box-shadow:0 0 10px var(--green)}
.research-toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px}.research-toolbar select{background:#0b1220;color:var(--text);border:1px solid var(--line);border-radius:10px;padding:9px 12px}.research-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.research-wide{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}.evidence-list,.change-list{max-height:330px;overflow:auto}.research-row{padding:9px 0;border-bottom:1px solid #202c40;font-size:12px}.research-row:last-child{border-bottom:0}.research-k{color:var(--muted);font-size:11px}.research-v{font-weight:800;margin-top:3px}.conflict{color:var(--yellow)}.research-status{font-size:12px;margin-left:auto}@media(max-width:1100px){.research-grid{grid-template-columns:1fr 1fr}.research-wide{grid-template-columns:1fr}.hero{grid-template-columns:1fr}.grid,.modules{grid-template-columns:1fr 1fr}.strategies{grid-template-columns:1fr}.tables{grid-template-columns:1fr}}@media(max-width:650px){.research-grid{grid-template-columns:1fr}.wrap{padding:12px}.top{align-items:flex-start;flex-direction:column}.grid,.modules,.subgrid{grid-template-columns:1fr}.posgrid{grid-template-columns:1fr 1fr}.total{font-size:28px}}
</style></head><body><div class="wrap">
<div class="top"><div class="brand"><h1>ZİTAR</h1><small data-i18n="subtitle">Personal Market Intelligence • Control Center V2.2.2</small></div><div class="actions"><span class="badge green">● PAPER</span><span class="badge red" data-i18n="realoff">REAL ORDERS: OFF</span><button class="btn" id="langBtn">TR | EN</button><span class="badge blue" id="clock">--</span></div></div>
<div class="nav"><button class="btn" id="dashBtn" data-i18n="navDash">Dashboard</button><button class="btn disabled" data-i18n="navMarkets">Markets</button><button class="btn" id="researchBtn" data-i18n="navResearch">Research</button><button class="btn disabled" data-i18n="navExperiments">Experiments</button><button class="btn disabled">AI</button><button class="btn disabled" data-i18n="navSystem">System</button></div>
<div id="dashboardView"><div class="hero"><div class="panel"><div class="label" data-i18n="totalPortfolio">TOTAL PAPER PORTFOLIO</div><div class="total" id="totalEquity">--</div><div class="subgrid"><div class="mini"><div class="label" data-i18n="totalPnl">Total P/L</div><div class="value" id="totalPnl">--</div></div><div class="mini"><div class="label" data-i18n="return">Return</div><div class="value" id="totalReturn">--</div></div><div class="mini"><div class="label" data-i18n="positions">Open Positions</div><div class="value" id="totalPositions">--</div></div></div></div>
<div class="panel"><div class="modulehead"><div><div class="label" data-i18n="master">ZİTAR MASTER CONTROL</div><div class="value" id="systemState">MONITORING</div></div><div class="actions"><button class="btn disabled" title="Preview only">▶ <span data-i18n="start">START</span></button><button class="btn disabled" title="Preview only">■ <span data-i18n="safeStop">SAFE STOP</span></button></div></div><div class="controlnote" data-i18n="preview">Preview only — controls are intentionally not connected to execution yet.</div><div class="health"><div class="healthitem"><span data-i18n="marketData">Market Data</span><strong id="marketHealth">--</strong></div><div class="healthitem"><span>V3 Paper Engine</span><strong id="engineHealth">--</strong></div><div class="healthitem"><span>Scheduler</span><strong id="schedulerHealth">--</strong></div><div class="healthitem"><span>Binance TR API</span><strong id="apiHealth">--</strong></div></div></div></div>
<div class="grid"><div class="stat"><div class="label">V3 Status</div><div class="value" id="status">--</div></div><div class="stat"><div class="label" data-i18n="lastCandle">Last Processed Candle</div><div class="value" id="candle">--</div></div><div class="stat"><div class="label" data-i18n="runs">Prospective Runs</div><div class="value" id="runs">--</div></div><div class="stat"><div class="label" data-i18n="nextRun">Next Scheduled Run</div><div class="value" id="nextRun">--</div></div></div>
<div class="section"><h2 data-i18n="strategyAccounts">Strategy Accounts</h2><div class="strategies" id="strategies"></div></div>
<div class="section"><h2 data-i18n="modules">ZİTAR Intelligence Modules</h2><div class="modules"><div class="module"><div class="modulehead"><h3>Multi-Timeframe Research</h3><span class="badge yellow">PLANNED</span></div><p data-i18n="mtfDesc">1m → 1M market structure and cross-timeframe research layer.</p></div><div class="module"><div class="modulehead"><h3>AI Research + Memory/RAG</h3><span class="badge yellow">PLANNED</span></div><p data-i18n="aiDesc">Versioned hypotheses, evidence, forward validation and research memory.</p></div><div class="module"><div class="modulehead"><h3>Event & Pump Radar</h3><span class="badge yellow">PLANNED</span></div><p data-i18n="radarDesc">News, volume velocity and anomaly watch beyond the core universe.</p></div><div class="module"><div class="modulehead"><h3>Futures Intelligence</h3><span class="badge yellow">PLANNED</span></div><p data-i18n="futuresDesc">OI, funding, basis, liquidations and spot/futures divergence research.</p></div><div class="module"><div class="modulehead"><h3>Voice ZİTAR</h3><span class="badge purple">NEXT</span></div><p data-i18n="voiceDesc">Local voice conversation focused on explaining ZİTAR's research development.</p></div><div class="module"><div class="modulehead"><h3>Research Integrity</h3><span class="badge yellow">PLANNED</span></div><p data-i18n="integrityDesc">Overfitting, small-sample, look-ahead and experiment-integrity warnings.</p></div><div class="module"><div class="modulehead"><h3>Liquidity Intelligence</h3><span class="badge yellow">PLANNED</span></div><p data-i18n="liqDesc">Volume, spread, trades, depth, price impact and liquidity persistence.</p></div><div class="module"><div class="modulehead"><h3>Multi-Agent Intelligence</h3><span class="badge blue">NEXT LEVEL</span></div><p data-i18n="agentsDesc">Specialist agents behind one ZİTAR interface after the Master Plan.</p></div></div></div>
<div class="section"><h2 data-i18n="activeSignals">Latest Candle — Active Signals</h2><div class="tablebox"><table><thead><tr><th data-i18n="strategy">Strategy</th><th data-i18n="pair">Pair</th><th data-i18n="signal">Signal</th><th data-i18n="candle">Candle</th></tr></thead><tbody id="activeSignals"></tbody></table></div></div>
<div class="section"><div class="tables"><div><h2 data-i18n="tradeHistory">Paper Trade History</h2><div class="tablebox"><table><thead><tr><th data-i18n="strategy">Strategy</th><th data-i18n="pair">Pair</th><th data-i18n="trade">Trade</th><th data-i18n="time">Time</th></tr></thead><tbody id="trades"></tbody></table></div></div><div><h2 data-i18n="runHistory">V3 Run History</h2><div class="tablebox"><table><thead><tr><th data-i18n="candle">Candle</th><th data-i18n="signal">Signal</th><th>Trade</th><th>Status</th></tr></thead><tbody id="runHistory"></tbody></table></div></div></div></div>

</div>
<div id="researchView" style="display:none">
  <div class="section">
    <div class="panel">
      <div class="modulehead">
        <div><div class="label">ZİTAR RESEARCH / RAG</div><div class="value">Cross-Timeframe Research Memory</div></div>
        <span class="badge green">READ ONLY</span>
      </div>
      <div class="research-toolbar">
        <label class="muted">Parite / Symbol</label>
        <select id="researchSymbol"></select>
        <button class="btn" id="researchRefresh">↻ Yenile / Refresh</button>
        <span id="researchApiStatus" class="research-status muted">5012: --</span>
      </div>
      <div class="research-grid">
        <div class="mini"><div class="label">SHORT · 1m–30m</div><div class="value" id="rShort">--</div></div>
        <div class="mini"><div class="label">MEDIUM · 1h–4h</div><div class="value" id="rMedium">--</div></div>
        <div class="mini"><div class="label">LONG · 1d–1w</div><div class="value" id="rLong">--</div></div>
        <div class="mini"><div class="label">MONTHLY · AUX</div><div class="value" id="rMonthly">--</div></div>
        <div class="mini"><div class="label">AGREEMENT</div><div class="value" id="rAgree">--</div></div>
        <div class="mini"><div class="label">DATA CONFIDENCE</div><div class="value" id="rConfidence">--</div></div>
        <div class="mini"><div class="label">MEMORY VERSION</div><div class="value" id="rVersion">--</div></div>
        <div class="mini"><div class="label">CONFLICTS</div><div class="value" id="rConflictCount">--</div></div>
      </div>
      <div class="research-wide">
        <div class="card"><h3>Evidence / Provenance</h3><div id="rEvidence" class="evidence-list"></div></div>
        <div class="card"><h3>Ne değişti? / What changed?</h3><div id="rChanges" class="change-list"></div></div>
      </div>
      <div class="research-wide">
        <div class="card"><h3>Explicit Conflicts</h3><div id="rConflicts"></div></div>
        <div class="card"><h3>Research Integrity</h3><div class="muted" style="line-height:1.6">Bu ekran betimleyici araştırmadır. BUY/SELL sinyali değildir. HIGH confidence yalnızca veri kalitesini ifade eder. Aylık 1M bağlam çekirdek agreement hesabına dahil edilmez. Eski hafıza sürümleri overwrite edilmez.</div></div>
      </div>
    </div>
  </div>
</div>
<div class="footer"><span class="dot"></span><span data-i18n="footer">ZİTAR V2.2 • read-only • no order endpoint • auto refresh 5s</span></div></div>
<script>
let lang=localStorage.getItem('zitar_lang')||'tr';
const I={tr:{subtitle:'Personal Market Intelligence • Kontrol Merkezi V2.2',realoff:'GERÇEK EMİRLER: KAPALI',navDash:'Panel',navMarkets:'Piyasalar',navResearch:'Araştırma',navExperiments:'Deneyler',navSystem:'Sistem',totalPortfolio:'TOPLAM PAPER PORTFÖY',totalPnl:'Toplam K/Z',return:'Getiri',positions:'Açık Pozisyon',master:'ZİTAR ANA KONTROL',start:'BAŞLAT',safeStop:'GÜVENLİ DURDUR',preview:'Önizleme — kontrol tuşları henüz execution sistemine bilinçli olarak bağlı değil.',marketData:'Piyasa Verisi',lastCandle:'Son İşlenen Mum',runs:'Prospective Tur',nextRun:'Sonraki Otomatik Çalışma',strategyAccounts:'Strateji Hesapları',modules:'ZİTAR Zeka Modülleri',mtfDesc:'1m → 1M piyasa yapısı ve zaman dilimleri arası araştırma katmanı.',aiDesc:'Versiyonlu hipotezler, kanıtlar, forward doğrulama ve araştırma hafızası.',radarDesc:'Ana evren dışındaki haber, hacim ivmesi ve anomali takibi.',futuresDesc:'OI, funding, basis, likidasyon ve spot/futures ayrışma araştırması.',voiceDesc:'ZİTAR’ın araştırma gelişimini açıklamaya odaklı yerel sesli iletişim.',integrityDesc:'Overfitting, küçük örneklem, look-ahead ve deney bütünlüğü uyarıları.',liqDesc:'Hacim, spread, işlem sayısı, derinlik, price impact ve likidite sürekliliği.',agentsDesc:'Master Plan sonrasında tek ZİTAR arayüzünün arkasındaki uzman ajanlar.',activeSignals:'Son Mum — Aktif Sinyaller',strategy:'Strateji',pair:'Parite',signal:'Sinyal',candle:'Mum',tradeHistory:'Paper İşlem Geçmişi',trade:'İşlem',time:'Zaman',runHistory:'V3 Çalışma Geçmişi',footer:'ZİTAR V2.2 • salt-okunur • emir endpoint’i yok • 5 sn otomatik yenileme',noPos:'Açık pozisyon yok',cost:'Maliyet',entry:'Model Giriş',bid:'Canlı Bid',ask:'Canlı Ask',posValue:'Pozisyon Değeri',qty:'Miktar',cash:'Nakit',equity:'Equity',unreal:'Gerçekleşmemiş K/Z',realized:'Gerçekleşmiş K/Z',noSignal:'Aktif BUY/SELL sinyali yok',noTrade:'Henüz V3 paper işlem yok',noRun:'Çalışma kaydı yok'},en:{subtitle:'Personal Market Intelligence • Control Center V2.2',realoff:'REAL ORDERS: OFF',navDash:'Dashboard',navMarkets:'Markets',navResearch:'Research',navExperiments:'Experiments',navSystem:'System',totalPortfolio:'TOTAL PAPER PORTFOLIO',totalPnl:'Total P/L',return:'Return',positions:'Open Positions',master:'ZİTAR MASTER CONTROL',start:'START',safeStop:'SAFE STOP',preview:'Preview only — controls are intentionally not connected to execution yet.',marketData:'Market Data',lastCandle:'Last Processed Candle',runs:'Prospective Runs',nextRun:'Next Scheduled Run',strategyAccounts:'Strategy Accounts',modules:'ZİTAR Intelligence Modules',mtfDesc:'1m → 1M market structure and cross-timeframe research layer.',aiDesc:'Versioned hypotheses, evidence, forward validation and research memory.',radarDesc:'News, volume velocity and anomaly watch beyond the core universe.',futuresDesc:'OI, funding, basis, liquidations and spot/futures divergence research.',voiceDesc:"Local voice conversation focused on explaining ZİTAR's research development.",integrityDesc:'Overfitting, small-sample, look-ahead and experiment-integrity warnings.',liqDesc:'Volume, spread, trades, depth, price impact and liquidity persistence.',agentsDesc:'Specialist agents behind one ZİTAR interface after the Master Plan.',activeSignals:'Latest Candle — Active Signals',strategy:'Strategy',pair:'Pair',signal:'Signal',candle:'Candle',tradeHistory:'Paper Trade History',trade:'Trade',time:'Time',runHistory:'V3 Run History',footer:'ZİTAR V2.2 • read-only • no order endpoint • auto refresh 5s',noPos:'No open position',cost:'Cost',entry:'Modeled Entry',bid:'Live Bid',ask:'Live Ask',posValue:'Position Value',qty:'Quantity',cash:'Cash',equity:'Equity',unreal:'Unrealized P/L',realized:'Realized P/L',noSignal:'No active BUY/SELL signal',noTrade:'No V3 paper trade yet',noRun:'No run record'}};
function tr(k){return (I[lang]&&I[lang][k])||k}function applyLang(){document.documentElement.lang=lang;document.querySelectorAll('[data-i18n]').forEach(e=>e.textContent=tr(e.dataset.i18n));document.getElementById('langBtn').textContent=lang==='tr'?'TR | EN':'EN | TR';refresh()}document.getElementById('langBtn').onclick=()=>{lang=lang==='tr'?'en':'tr';localStorage.setItem('zitar_lang',lang);applyLang()};
const fmt=n=>Number(n||0).toLocaleString(lang==='tr'?'tr-TR':'en-US',{minimumFractionDigits:2,maximumFractionDigits:2});const pct=n=>Number(n||0).toFixed(2)+'%';const pc=n=>Number(n||0)>=0?'green':'red';const get=(o,ks,f='')=>{for(const k of ks){if(o&&o[k]!==undefined&&o[k]!==null&&o[k]!=='')return o[k]}return f};const strategyName=r=>get(r,['strategy','strategy_name']);const symbolName=r=>get(r,['symbol','pair']);const signalName=r=>String(get(r,['signal','action'],'NONE')).toUpperCase();const candleName=r=>get(r,['candle_close_utc','signal_candle_close_utc']);
function renderStrategy(name,s){let p=!s.positions.length?`<div class="position muted">${tr('noPos')}</div>`:s.positions.map(x=>`<div class="position"><div class="position-title"><span>${x.symbol}</span><span class="${pc(x.unrealized_try)}">${fmt(x.unrealized_try)} TRY (${pct(x.unrealized_pct)})</span></div><div class="posgrid"><div class="positem">${tr('cost')}<strong>${fmt(x.cost_try)} TRY</strong></div><div class="positem">${tr('entry')}<strong>${x.modeled_entry}</strong></div><div class="positem">${tr('bid')}<strong class="blue">${x.bid}</strong></div><div class="positem">${tr('ask')}<strong>${x.ask}</strong></div><div class="positem">${tr('posValue')}<strong>${fmt(x.value_try)} TRY</strong></div><div class="positem">${tr('qty')}<strong>${x.quantity}</strong></div></div></div>`).join('');return `<div class="card"><h3>${name}</h3><div class="metrics"><div class="metric"><div class="label">${tr('equity')}</div><div class="v">${fmt(s.equity)} TRY</div></div><div class="metric"><div class="label">${tr('cash')}</div><div class="v">${fmt(s.cash)} TRY</div></div><div class="metric"><div class="label">${tr('unreal')}</div><div class="v ${pc(s.unrealized)}">${fmt(s.unrealized)} TRY</div></div><div class="metric"><div class="label">${tr('return')}</div><div class="v ${pc(s.return_pct)}">${pct(s.return_pct)}</div></div><div class="metric"><div class="label">${tr('realized')}</div><div class="v ${pc(s.realized)}">${fmt(s.realized)} TRY</div></div><div class="metric"><div class="label">${tr('positions')}</div><div class="v">${s.positions.length}</div></div></div>${p}</div>`}
function signalRow(r){const s=signalName(r),c=s==='BUY'?'signal-buy':s==='SELL'?'signal-sell':'signal-none';return `<tr><td>${strategyName(r)}</td><td>${symbolName(r)}</td><td class="${c}">${s}</td><td>${candleName(r)}</td></tr>`}
async function refresh(){
  try {
    const response = await fetch('/api/dashboard', {cache:'no-store'});
    const d = await response.json();

    document.getElementById('clock').textContent = new Date().toLocaleTimeString(
      lang === 'tr' ? 'tr-TR' : 'en-US', {timeZone:'Europe/Istanbul'}
    );
    document.getElementById('status').textContent = d.state_status || 'OK';
    document.getElementById('status').className = 'value green';
    document.getElementById('candle').textContent = d.latest_candle || '--';
    document.getElementById('runs').textContent = d.runs_total || 0;

    const sc = d.scheduler || {};
    const ss = sc.State || 'UNKNOWN';
    document.getElementById('nextRun').textContent = sc.NextRunTime || '--';
    document.getElementById('schedulerHealth').textContent = ss;
    document.getElementById('schedulerHealth').className = ss === 'Ready' ? 'green' : 'yellow';
    document.getElementById('engineHealth').textContent = (d.protocol || 'V3') + ' ' + (d.state_status || 'UNKNOWN');
    document.getElementById('engineHealth').className = d.state_status ? 'green' : 'yellow';
    document.getElementById('marketHealth').textContent = String(d.universe_count || 0) + '/21';
    document.getElementById('marketHealth').className = d.universe_count === 21 ? 'green' : 'yellow';
    document.getElementById('apiHealth').textContent = d.book_error ? 'DEGRADED' : 'ONLINE';
    document.getElementById('apiHealth').className = d.book_error ? 'yellow' : 'green';

    let init = 0, eq = 0, pos = 0;
    Object.values(d.strategies || {}).forEach(function(s){
      init += Number(s.initial || 0);
      eq += Number(s.equity || 0);
      pos += (s.positions || []).length;
    });
    const pl = eq - init;
    const ret = init ? (pl / init * 100) : 0;
    document.getElementById('totalEquity').textContent = fmt(eq) + ' TRY';
    document.getElementById('totalPnl').textContent = fmt(pl) + ' TRY';
    document.getElementById('totalPnl').className = 'value ' + pc(pl);
    document.getElementById('totalReturn').textContent = pct(ret);
    document.getElementById('totalReturn').className = 'value ' + pc(ret);
    document.getElementById('totalPositions').textContent = pos;
    document.getElementById('systemState').textContent = 'MONITORING';
    document.getElementById('systemState').className = 'green';

    const order = ['SMA20_50','EMA12_26','RSI14'];
    document.getElementById('strategies').innerHTML = order
      .filter(function(x){ return d.strategies && d.strategies[x]; })
      .map(function(x){ return renderStrategy(x, d.strategies[x]); })
      .join('');

    const active = d.active_signals || [];
    document.getElementById('activeSignals').innerHTML = active.length
      ? active.map(signalRow).join('')
      : '<tr><td colspan="4" class="muted">' + tr('noSignal') + '</td></tr>';

    const trades = d.recent_trades || [];
    document.getElementById('trades').innerHTML = trades.length
      ? trades.map(function(r){
          return '<tr><td>' + strategyName(r) + '</td><td>' + symbolName(r) +
                 '</td><td>' + get(r,['side','action','signal']) + '</td><td>' +
                 get(r,['executed_at_utc','execution_utc','run_utc']) + '</td></tr>';
        }).join('')
      : '<tr><td colspan="4" class="muted">' + tr('noTrade') + '</td></tr>';

    const runs = d.recent_runs || [];
    document.getElementById('runHistory').innerHTML = runs.length
      ? runs.map(function(r){
          return '<tr><td>' + get(r,['candle_close_utc']) + '</td><td>' +
                 get(r,['signal_rows']) + '</td><td>' + get(r,['paper_trades']) +
                 '</td><td class="green">' + get(r,['status']) + '</td></tr>';
        }).join('')
      : '<tr><td colspan="4" class="muted">' + tr('noRun') + '</td></tr>';
  } catch(e) {
    console.error('ZITAR refresh error:', e);
    document.getElementById('status').textContent = 'DASHBOARD ERROR';
    document.getElementById('status').className = 'value red';
  }
}

let researchLoaded=false;
function esc(v){return String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
async function apiJson(url){const r=await fetch(url,{cache:'no-store'});const j=await r.json();if(!r.ok)throw new Error(j.detail||j.error||('HTTP '+r.status));return j}
function ctxObs(c,k){return c&&c[k]&&c[k].observation?c[k].observation:'--'}
async function loadResearchSymbols(){
  const h=await apiJson('/api/research-proxy/health');
  const x=await apiJson('/api/research-proxy/symbols');
  const sel=document.getElementById('researchSymbol');
  const old=sel.value||'BTCTRY';
  sel.innerHTML=(x.symbols||[]).map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');
  sel.value=(x.symbols||[]).includes(old)?old:((x.symbols||[]).includes('BTCTRY')?'BTCTRY':(x.symbols||[])[0]||'');
  document.getElementById('researchApiStatus').textContent='5012: '+(h.status||'UNKNOWN')+' · chain '+(h.chain_valid?'OK':'FAIL');
  document.getElementById('researchApiStatus').className='research-status '+(h.chain_valid?'green':'red');
  researchLoaded=true;
}
async function loadResearch(){
  try{
    if(!researchLoaded)await loadResearchSymbols();
    const symbol=document.getElementById('researchSymbol').value;
    if(!symbol)return;
    const d=await apiJson('/api/research-proxy/context?symbol='+encodeURIComponent(symbol));
    const m=d.current_mtf_research||{}, c=m.contexts||{}, latest=d.latest_memory||{};
    document.getElementById('rShort').textContent=ctxObs(c,'SHORT');
    document.getElementById('rMedium').textContent=ctxObs(c,'MEDIUM');
    document.getElementById('rLong').textContent=ctxObs(c,'LONG');
    document.getElementById('rMonthly').textContent=ctxObs(c,'MONTHLY_CONTEXT');
    document.getElementById('rAgree').textContent=get(m.cross_timeframe_agreement||{},['level'],'--');
    document.getElementById('rConfidence').textContent=get(m.data_confidence||{},['level'],'--');
    document.getElementById('rVersion').textContent='v'+String(latest.symbol_version||d.memory_versions||0);
    const conflicts=m.explicit_conflicts||[];
    document.getElementById('rConflictCount').textContent=conflicts.length;
    document.getElementById('rConflicts').innerHTML=conflicts.length?conflicts.map(x=>`<div class="research-row conflict">${esc(x.timeframe_a)} ${esc(x.observation_a)} ↔ ${esc(x.timeframe_b)} ${esc(x.observation_b)}</div>`).join(''):'<div class="muted">Açık UP/DOWN çatışması yok.</div>';
    const ev=m.evidence||[];
    document.getElementById('rEvidence').innerHTML=ev.length?ev.map(x=>`<div class="research-row"><div><strong>${esc(x.timeframe)}</strong> · ${esc(x.trend)} · RSI ${esc(x.rsi14_simple??'--')}</div><div class="research-k">${esc(x.source)} · quality=${esc(x.quality)} · n=${esc(x.candle_count)}</div></div>`).join(''):'<div class="muted">Evidence yok.</div>';
    const vh=d.version_history||[];
    document.getElementById('rChanges').innerHTML=vh.length?vh.slice().reverse().map(x=>{const ch=x.change||{};const fs=(ch.changed_fields||[]).map(y=>y.field).join(', ');return `<div class="research-row"><strong>v${esc(x.version)}</strong> · ${esc(ch.change_type||'--')}<div class="research-k">${esc(x.observed_utc||'')} ${fs?'· '+esc(fs):''}</div></div>`}).join(''):'<div class="muted">Memory history yok.</div>';
  }catch(e){
    console.error('Research error',e);
    document.getElementById('researchApiStatus').textContent='5012: OFFLINE / ERROR';
    document.getElementById('researchApiStatus').className='research-status red';
  }
}
function showView(v){
  document.getElementById('dashboardView').style.display=v==='dashboard'?'block':'none';
  document.getElementById('researchView').style.display=v==='research'?'block':'none';
  if(v==='research')loadResearch();
}
document.getElementById('dashBtn').onclick=()=>showView('dashboard');
document.getElementById('researchBtn').onclick=()=>showView('research');
document.getElementById('researchRefresh').onclick=loadResearch;
document.getElementById('researchSymbol').onchange=loadResearch;

applyLang();setInterval(refresh,5000);
</script></body></html>
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


        if self.path.startswith("/api/research-proxy/"):
            try:
                upstream = self.path.replace("/api/research-proxy", "/api/research", 1)
                data = research_api_get(upstream)
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                return self.send_bytes(body, "application/json; charset=utf-8")
            except Exception as e:
                body = json.dumps({
                    "error": "research_api_unavailable",
                    "detail": str(e),
                    "execution_authority": False
                }, ensure_ascii=False).encode("utf-8")
                return self.send_bytes(body, "application/json; charset=utf-8", 503)

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
    print("ZITAR CONTROL CENTER V2.2")
    print("=" * 70)
    print(
        f"URL         : http://{HOST}:{PORT}"
    )
    print(
        "MODE        : PAPER / CONTROL CENTER V2.2 + RESEARCH"
    )
    print(
        "REAL ORDERS : NO"
    )
    print(
        "REFRESH     : 5 seconds / TR-EN UI"
    )
    print("=" * 70)

    server = ThreadingHTTPServer(
        (HOST, PORT),
        Handler
    )

    server.serve_forever()
