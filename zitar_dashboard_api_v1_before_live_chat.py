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
Piyasa Seçim Motoru
</div>

<div class="card">

<div class="pipeline">

<div class="pipe">
<strong>1</strong><br><br>
Tüm Tokenlar
</div>

<div class="pipe">
<strong>2</strong><br><br>
Hacim Filtresi
</div>

<div class="pipe">
<strong>3</strong><br><br>
Likidite Filtresi
</div>

<div class="pipe">
<strong>4</strong><br><br>
Aday Havuzu
</div>

<div class="pipe">
<strong>5</strong><br><br>
Derin Analiz
</div>

<div class="pipe">
<strong>6</strong><br><br>
Risk Kontrolü
</div>

<div class="pipe">
<strong>7</strong><br><br>
Spot / Vadeli
</div>

</div>

<p class="muted">
Canlı token tarayıcı Runtime entegrasyonunda
bağlanacaktır. Dashboard sahte piyasa sayısı üretmez.
</p>

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
<td class="status-wait">ENTEGRASYON</td>
</tr>

<tr>
<td>Runtime Memory bağlantısı</td>
<td class="status-wait">ENTEGRASYON</td>
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
Chat Runtime bir sonraki bağlantı aşamasında
burada aktif olacaktır.
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

</script>

</body>
</html>
"""
