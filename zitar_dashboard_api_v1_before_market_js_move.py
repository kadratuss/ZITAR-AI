from pathlib import Path
import json
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["zitar"])

BASE = Path(__file__).resolve().parent

REGRESSION = BASE / "zitar_full_regression_suite_v1.json"
PROJECT_MEMORY = BASE / "zitar_core_project_memory_v1.jsonl"
LEARNING_JOURNAL = BASE / "zitar_core_learning_journal_v1.jsonl"
FINANCE_BRIDGE = BASE / "zitar_finance_unified_bridge_v1_1.json"

# MARKET INTELLIGENCE V1
MARKET_CYCLE = BASE / "zitar_market_intelligence_cycle_v1.json"
SELECTION_ENGINE = BASE / "zitar_selection_engine_v1.json"
FUTURES_UNIVERSE = BASE / "zitar_futures_universe_v1.json"
FUTURES_EVIDENCE = BASE / "zitar_futures_evidence_v1.json"
FUTURES_SNAPSHOT = BASE / "zitar_futures_intelligence_snapshot_v1_1.json"


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def count_jsonl(path):
    try:
        return len([
            x for x in path.read_text(
                encoding="utf-8-sig"
            ).splitlines()
            if x.strip()
        ])
    except Exception:
        return 0


def dashboard_state():

    regression = read_json(REGRESSION) or {}
    finance = read_json(FINANCE_BRIDGE) or {}

    # MARKET INTELLIGENCE
    market_cycle = read_json(MARKET_CYCLE) or {}
    market_summary = market_cycle.get("summary", {})
    selection = read_json(SELECTION_ENGINE) or {}
    futures_universe = read_json(FUTURES_UNIVERSE) or {}
    futures_evidence = read_json(FUTURES_EVIDENCE) or {}
    futures_snapshot = read_json(FUTURES_SNAPSHOT) or {}

    counts = regression.get("counts", {})

    total = regression.get("total", 0)
    passed = counts.get("PASS", 0)

    project_records = count_jsonl(PROJECT_MEMORY)
    learning_records = count_jsonl(LEARNING_JOURNAL)

    return {
        "zitar": "ONLINE",
        "core": {
            "status": regression.get(
                "overall_status",
                "UNKNOWN"
            ),
            "passed": passed,
            "total": total,
        },
        "memory": {
            "project_records": project_records,
            "learning_records": learning_records,
        },
        "finance": {
            "status": finance.get(
                "status",
                "UNKNOWN"
            ),
            "directional_allowed": finance.get(
                "directional_allowed",
                False
            ),
            "direction": finance.get(
                "direction",
                "NO_DIRECTIONAL_CONCLUSION"
            ),
        },
        "market_intelligence": {
            "status": market_cycle.get(
                "status",
                "UNKNOWN"
            ),
            "selection_mode": market_summary.get(
                "selection_mode",
                selection.get("mode", "UNKNOWN")
            ),
            "selection_candidates": market_summary.get(
                "selection_candidates",
                len(selection.get("analysis_candidates", []))
            ),
            "selection_rejected": market_summary.get(
                "selection_rejected",
                len(selection.get("rejected", []))
            ),
            "futures_matched": market_summary.get(
                "futures_matched",
                len(futures_universe.get("matched", []))
            ),
            "futures_unmatched": market_summary.get(
                "futures_unmatched",
                len(futures_universe.get("unmatched", []))
            ),
            "snapshot_symbols": market_summary.get(
                "snapshot_symbols",
                len(futures_snapshot.get("symbols", []))
            ),
            "snapshot_complete": market_summary.get(
                "snapshot_complete",
                sum(
                    1 for x in futures_snapshot.get("symbols", [])
                    if x.get("status") == "OK"
                )
            ),
            "active_evidence_symbols": market_summary.get(
                "active_evidence_symbols",
                sum(
                    1 for x in futures_evidence.get("symbols", [])
                    if x.get("universe_status") == "ACTIVE"
                )
            ),
            "observable_active_symbols": market_summary.get(
                "observable_active_symbols",
                sum(
                    1 for x in futures_evidence.get("symbols", [])
                    if x.get("universe_status") == "ACTIVE"
                    and x.get("temporal", {}).get("status") == "OBSERVABLE"
                )
            ),
            "historical_only_symbols": market_summary.get(
                "historical_only_symbols",
                sum(
                    1 for x in futures_evidence.get("symbols", [])
                    if x.get("universe_status") == "HISTORICAL_ONLY"
                )
            ),
        },
        "trading": {
            "mode": "PAPER_TRADING",
            "real_order_authority": False,
        },
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
    }


@router.get("/api/zitar/status")
def zitar_status():
    return dashboard_state()


@router.get("/zitar", response_class=HTMLResponse)
def zitar_dashboard():

    return r"""
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport"
      content="width=device-width,initial-scale=1">

<title>ZİTAR Control Center</title>

<style>

* { box-sizing:border-box; }

body {
    margin:0;
    background:#0B1020;
    color:#E5E7EB;
    font-family:Arial,Helvetica,sans-serif;
}

header {
    padding:26px 34px;
    border-bottom:1px solid #25304A;
    display:flex;
    justify-content:space-between;
    align-items:center;
}

.logo {
    font-size:28px;
    font-weight:800;
}

.subtitle {
    color:#94A3B8;
    margin-top:5px;
}

.online {
    color:#22C55E;
    font-weight:bold;
}

.container {
    padding:28px;
    max-width:1500px;
    margin:auto;
}

.grid {
    display:grid;
    grid-template-columns:
        repeat(auto-fit,minmax(260px,1fr));
    gap:18px;
}

.card {
    background:#172033;
    border:1px solid #25304A;
    border-radius:14px;
    padding:20px;
}

.card h2 {
    font-size:16px;
    margin-top:0;
    color:#CBD5E1;
}

.big {
    font-size:31px;
    font-weight:800;
    margin:12px 0;
}

.green { color:#22C55E; }
.red { color:#EF4444; }
.yellow { color:#F59E0B; }
.muted { color:#94A3B8; }

.section-title {
    margin:34px 0 15px;
    font-size:21px;
}

.pipeline {
    display:grid;
    grid-template-columns:
        repeat(auto-fit,minmax(150px,1fr));
    gap:10px;
}

.pipe {
    padding:17px;
    background:#111827;
    border:1px solid #334155;
    border-radius:10px;
    text-align:center;
}

table {
    width:100%;
    border-collapse:collapse;
}

td {
    padding:10px;
    border-bottom:1px solid #25304A;
}

.status-pass {
    color:#22C55E;
    font-weight:bold;
}

.status-wait {
    color:#F59E0B;
    font-weight:bold;
}

.chat {
    min-height:220px;
    background:#0F172A;
    border-radius:10px;
    padding:15px;
    color:#94A3B8;
}

.footer {
    color:#64748B;
    padding:30px 0;
    text-align:center;
}

</style>
</head>

<body>

<header>
<div>
    <div class="logo">ZİTAR</div>
    <div class="subtitle">
        Core Intelligence Control Center
    </div>
</div>

<div>
    SYSTEM:
    <span class="online">ONLINE</span>
</div>
</header>

<div class="container">

<div class="grid">

<div class="card">
<h2>CORE SAĞLIĞI</h2>
<div id="core" class="big">...</div>
<div class="muted">
Tam regression doğrulaması
</div>
</div>

<div class="card">
<h2>PROJECT MEMORY</h2>
<div id="projectMemory" class="big">...</div>
<div class="muted">
Kalıcı proje hafızası
</div>
</div>

<div class="card">
<h2>LEARNING JOURNAL</h2>
<div id="learningMemory" class="big">...</div>
<div class="muted">
Doğrulanmış öğrenmeler
</div>
</div>

<div class="card">
<h2>FINANCE SPECIALIST</h2>
<div id="finance" class="big">...</div>
<div class="muted">
Kanıta dayalı finans katmanı
</div>
</div>

<div class="card">
<h2>ÇALIŞMA MODU</h2>
<div class="big yellow">
PAPER TRADING
</div>
<div class="muted">
Gerçek emir yetkisi kapalı
</div>
</div>

</div>


<div class="section-title">
Canlı Piyasa Seçim Motoru
</div>

<div class="card">

<div style="
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:15px;
    margin-bottom:16px;
">

<div>
<strong>MARKET INTELLIGENCE CYCLE</strong><br>
<span class="muted">
Hacim • Likidite • Futures • Temporal Evidence
</span>
</div>

<div id="marketCycleStatus"
     class="status-wait">
YÜKLENİYOR
</div>

</div>

<div class="pipeline">

<div class="pipe">
<strong>1</strong><br><br>
Piyasa Tarama
<br><br>
<span class="muted">
Hacim + Likidite
</span>
</div>

<div class="pipe">
<strong>2</strong><br><br>
<span id="marketCandidates"
      style="font-size:18px;font-weight:700;">
-
</span>
Aday
<br><br>
<span class="muted">
Analiz Havuzu
</span>
</div>

<div class="pipe">
<strong>3</strong><br><br>
<span id="marketFuturesMatched"
      style="font-size:18px;font-weight:700;">
-
</span>
Futures
<br><br>
<span class="muted">
USDT Perpetual
</span>
</div>

<div class="pipe">
<strong>4</strong><br><br>
<span id="marketSnapshotComplete"
      style="font-size:18px;font-weight:700;">
-
</span>
/
<span id="marketSnapshotTotal"
      style="font-size:18px;font-weight:700;">
-
</span>
<br>
Veri Tam
<br><br>
<span class="muted">
5 Futures Kanalı
</span>
</div>

<div class="pipe">
<strong>5</strong><br><br>
<span id="marketObservable"
      style="font-size:18px;font-weight:700;">
-
</span>
Olgun
<br><br>
<span class="muted">
Temporal Evidence
</span>
</div>

<div class="pipe">
<strong>6</strong><br><br>
<span id="marketHistorical"
      style="font-size:18px;font-weight:700;">
-
</span>
Geçmiş
<br><br>
<span class="muted">
Historical Only
</span>
</div>

<div class="pipe">
<strong>7</strong><br><br>
KANIT
<br><br>
<span class="muted">
Sinyal / Emir Yok
</span>
</div>

</div>

<div style="
    margin-top:14px;
    border-top:1px solid #263550;
    padding-top:12px;
">

<strong id="marketMode"
        class="yellow">
YÜKLENİYOR
</strong>

<span class="muted">
 •
</span>

<span id="marketModeExplanation"
      class="muted">
Piyasa motoru durumu yükleniyor.
</span>

</div>

</div>


<div class="section-title">
ZİTAR Hafıza ve Öğrenme
</div>

<div class="grid">

<div class="card">
<h2>CONVERSATION CONTEXT</h2>
<div class="status-pass">
HAZIR
</div>
<p class="muted">
Aktif konuşmanın kısa süreli bağlamı.
</p>
</div>

<div class="card">
<h2>PROJECT MEMORY</h2>
<div class="status-pass">
HAZIR
</div>
<p class="muted">
Projelerin kabul edilmiş kalıcı bilgileri.
</p>
</div>

<div class="card">
<h2>LEARNING</h2>
<div class="status-pass">
HAZIR
</div>
<p class="muted">
Doğrulanmış araştırmalardan kontrollü öğrenme.
</p>
</div>

<div class="card">
<h2>KNOWLEDGE GAP</h2>
<div class="status-pass">
HAZIR
</div>
<p class="muted">
ZİTAR bilmediği konuyu bilgi gibi uydurmaz.
</p>
</div>

<div class="card">
<h2>GENERAL RESEARCH</h2>
<div class="status-pass">
TEMEL SİSTEM HAZIR
</div>
<p class="muted">
Yerel kanıt, araştırma planı ve dış kaynak zinciri.
</p>
</div>

<div class="card">
<h2>QWEN / OLLAMA</h2>
<div class="status-pass">
ENTEGRASYON TESTİ PASS
</div>
<p class="muted">
Doğal dil sentez katmanı.
</p>
</div>

</div>


<div class="section-title">
Finance / Vadeli İşlemler
</div>

<div class="card">

<table>
<tr>
<td>Funding</td>
<td>Finance Evidence</td>
</tr>

<tr>
<td>Basis</td>
<td>Finance Evidence</td>
</tr>

<tr>
<td>Open Interest</td>
<td>Finance Evidence</td>
</tr>

<tr>
<td>Long / Short</td>
<td>Finance Evidence</td>
</tr>

<tr>
<td>Taker Buy / Sell</td>
<td>Finance Evidence</td>
</tr>

<tr>
<td>Yön uydurma</td>
<td class="status-pass">ENGELLENDİ</td>
</tr>

<tr>
<td>Gerçek emir</td>
<td class="red">KAPALI</td>
</tr>

</table>

</div>


<div class="section-title">
Geliştirme Durumu
</div>

<div class="card">

<table>

<tr>
<td>Core / Router / Context</td>
<td class="status-pass">TAMAM</td>
</tr>

<tr>
<td>Project Memory</td>
<td class="status-pass">TAMAM</td>
</tr>

<tr>
<td>Learning Journal</td>
<td class="status-pass">TAMAM</td>
</tr>

<tr>
<td>Unified Recall</td>
<td class="status-pass">TAMAM</td>
</tr>

<tr>
<td>Knowledge Gap</td>
<td class="status-pass">TAMAM</td>
</tr>

<tr>
<td>Research altyapısı</td>
<td class="status-pass">TAMAM</td>
</tr>

<tr>
<td>Finance Bridge</td>
<td class="status-pass">TAMAM</td>
</tr>

<tr>
<td>Finance Grounded Renderer</td>
<td class="status-pass">TAMAM</td>
</tr>

<tr>
<td>Tek ZİTAR Runtime</td>
<td class="status-ok">TAMAM</td>
</tr>

<tr>
<td>Runtime Memory bağlantısı</td>
<td class="status-ok">TAMAM</td>
</tr>

<tr>
<td>Canlı genel araştırma</td>
<td class="status-wait">ENTEGRASYON</td>
</tr>

<tr>
<td>Tüm token tarayıcı</td>
<td class="status-wait">ENTEGRASYON</td>
</tr>

<tr>
<td>Hacim / likidite seçimi</td>
<td class="status-wait">ENTEGRASYON</td>
</tr>

<tr>
<td>ZİTAR Web Chat</td>
<td class="status-wait">SIRADA</td>
</tr>

</table>

</div>


<div class="section-title">
ZİTAR Chat
</div>

<div class="card">

<div class="chat">

    <div id="zitarChatMessages"
         style="
            min-height:220px;
            max-height:420px;
            overflow-y:auto;
            margin-bottom:16px;
            white-space:pre-wrap;
            line-height:1.55;
         ">

        <div class="muted">
            ZİTAR Runtime hazır. Project Memory, Learning Journal
            ve Finance Specialist bağlı.
        </div>

    </div>

    <div style="
        display:flex;
        gap:10px;
        align-items:center;
    ">

        <input
            id="zitarChatInput"
            type="text"
            placeholder="ZİTAR'a mesajını yaz..."
            autocomplete="off"
            style="
                flex:1;
                padding:13px 14px;
                border-radius:8px;
                border:1px solid #334155;
                background:#0f172a;
                color:#f8fafc;
                outline:none;
            "
        >

        <button
            id="zitarChatSend"
            onclick="sendZitarMessage()"
            style="
                padding:13px 20px;
                border:0;
                border-radius:8px;
                cursor:pointer;
                font-weight:700;
            "
        >
            Gönder
        </button>

    </div>

    <div
        id="zitarChatMeta"
        class="muted"
        style="margin-top:12px;"
    >
        Runtime bekliyor.
    </div>

</div>

</div>


<div class="footer">
ZİTAR • Core + Memory + Learning + Research + Finance
</div>

</div>


<script>

async function refreshStatus() {

    try {

        const r =
            await fetch("/api/zitar/status");

        const d = await r.json();

        const core =
            document.getElementById("core");

        core.textContent =
            d.core.passed + "/" +
            d.core.total + " PASS";

        core.className =
            "big " +
            (d.core.status === "PASS"
                ? "green"
                : "red");

        document.getElementById(
            "projectMemory"
        ).textContent =
            d.memory.project_records +
            " KAYIT";

        document.getElementById(
            "learningMemory"
        ).textContent =
            d.memory.learning_records +
            " KAYIT";

        document.getElementById(
            "finance"
        ).textContent =
            d.finance.status;

    }

    catch(e) {

        document.getElementById(
            "core"
        ).textContent = "OFFLINE";

    }
}

refreshStatus();

setInterval(
    refreshStatus,
    5000
);


const ZITAR_SESSION_ID =
    "dashboard-" + Math.random().toString(36).slice(2);

let zitarBusy = false;

function addChatMessage(role, text) {

    const box = document.getElementById("zitarChatMessages");
    const item = document.createElement("div");

    item.style.marginTop = "14px";

    const label = document.createElement("strong");
    label.textContent = role === "user" ? "Sen: " : "ZİTAR: ";

    const content = document.createElement("span");
    content.textContent = text;

    item.appendChild(label);
    item.appendChild(content);

    box.appendChild(item);
    box.scrollTop = box.scrollHeight;
}


async function sendZitarMessage() {

    if (zitarBusy) return;

    const input = document.getElementById("zitarChatInput");
    const button = document.getElementById("zitarChatSend");
    const meta = document.getElementById("zitarChatMeta");

    const message = input.value.trim();

    if (!message) return;

    addChatMessage("user", message);

    input.value = "";
    zitarBusy = true;
    button.disabled = true;
    meta.textContent = "ZİTAR düşünüyor...";

    try {

        const response = await fetch(
            "/api/zitar/chat",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    message: message,
                    session_id: ZITAR_SESSION_ID
                })
            }
        );

        if (!response.ok) {
            throw new Error("HTTP " + response.status);
        }

        const data = await response.json();

        // -------------------------------------------------
        // LIVE MARKET INTELLIGENCE
        // -------------------------------------------------

        const mi = data.market_intelligence || {};

        const marketCycleStatus =
            document.getElementById("marketCycleStatus");

        const marketCandidates =
            document.getElementById("marketCandidates");

        const marketFuturesMatched =
            document.getElementById("marketFuturesMatched");

        const marketSnapshotComplete =
            document.getElementById("marketSnapshotComplete");

        const marketSnapshotTotal =
            document.getElementById("marketSnapshotTotal");

        const marketObservable =
            document.getElementById("marketObservable");

        const marketHistorical =
            document.getElementById("marketHistorical");

        const marketMode =
            document.getElementById("marketMode");

        const marketModeExplanation =
            document.getElementById("marketModeExplanation");


        if (marketCycleStatus) {
            marketCycleStatus.textContent =
                mi.status || "UNKNOWN";

            marketCycleStatus.className =
                mi.status === "PASS"
                    ? "status-pass"
                    : "status-wait";
        }


        if (marketCandidates) {
            marketCandidates.textContent =
                mi.selection_candidates ?? "-";
        }


        if (marketFuturesMatched) {
            marketFuturesMatched.textContent =
                mi.futures_matched ?? "-";
        }


        if (marketSnapshotComplete) {
            marketSnapshotComplete.textContent =
                mi.snapshot_complete ?? "-";
        }


        if (marketSnapshotTotal) {
            marketSnapshotTotal.textContent =
                mi.snapshot_symbols ?? "-";
        }


        if (marketObservable) {
            marketObservable.textContent =
                mi.observable_active_symbols ?? "-";
        }


        if (marketHistorical) {
            marketHistorical.textContent =
                mi.historical_only_symbols ?? "-";
        }


        if (marketMode) {
            marketMode.textContent =
                mi.selection_mode || "UNKNOWN";

            marketMode.className =
                mi.selection_mode === "READY"
                    ? "status-pass"
                    : "yellow";
        }


        if (marketModeExplanation) {

            const candidates =
                mi.selection_candidates ?? 0;

            const matched =
                mi.futures_matched ?? 0;

            const complete =
                mi.snapshot_complete ?? 0;

            const total =
                mi.snapshot_symbols ?? 0;

            const observable =
                mi.observable_active_symbols ?? 0;

            if (mi.selection_mode === "WARMUP") {
                marketModeExplanation.textContent =
                    `Seçim motoru veri biriktiriyor. ` +
                    `${candidates} aday seçildi, ` +
                    `${matched} futures eşleşmesi bulundu, ` +
                    `${complete}/${total} futures verisi tam, ` +
                    `${observable} aktif sembolde temporal kanıt yeterli.`;
            }
            else {
                marketModeExplanation.textContent =
                    `${candidates} aday, ` +
                    `${matched} futures eşleşmesi, ` +
                    `${complete}/${total} tam veri, ` +
                    `${observable} temporal olarak gözlemlenebilir sembol.`;
            }
        }



        addChatMessage(
            "assistant",
            data.answer || "Cevap alınamadı."
        );

        meta.textContent =
            (data.route || "UNKNOWN") +
            " • " +
            (data.source || "UNKNOWN") +
            " • " +
            (data.grounded ? "GROUNDED" : "UNSUPPORTED");

    }
    catch (error) {

        addChatMessage(
            "assistant",
            "Runtime bağlantı hatası."
        );

        meta.textContent =
            "ERROR • " + error.message;
    }
    finally {

        zitarBusy = false;
        button.disabled = false;
        input.focus();
    }
}


document.addEventListener(
    "DOMContentLoaded",
    function () {

        const input =
            document.getElementById("zitarChatInput");

        if (!input) return;

        input.addEventListener(
            "keydown",
            function (event) {

                if (
                    event.key === "Enter" &&
                    !event.shiftKey
                ) {
                    event.preventDefault();
                    sendZitarMessage();
                }
            }
        );
    }
);

</script>

</body>
</html>
"""



