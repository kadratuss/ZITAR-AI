from pathlib import Path

p = Path("zitar_dashboard_api_v1.py")
s = p.read_text(encoding="utf-8-sig")

# ---------------------------------------------------------
# 1. STATIC MARKET FLOW -> LIVE MARKET FLOW
# ---------------------------------------------------------

old = '''<div class="section-title">
Piyasa Seçim Zinciri
</div>

<div class="card">

<div class="flow">

<div class="flow-step">
<div class="flow-number">1</div>
<div>
<strong>Token Tarama</strong><br>
<span class="muted">
Binance TR evreni
</span>
</div>
</div>

<div class="flow-step">
<div class="flow-number">2</div>
<div>
<strong>Hacim Filtresi</strong><br>
<span class="muted">
24 saat hacim
</span>
</div>
</div>

<div class="flow-step">
<div class="flow-number">3</div>
<div>
<strong>Likidite</strong><br>
<span class="muted">
Spread + orderbook
</span>
</div>
</div>

<div class="flow-step">
<div class="flow-number">4</div>
<div>
<strong>Top 20</strong><br>
<span class="muted">
Analiz evreni
</span>
</div>
</div>

<div class="flow-step">
<div class="flow-number">5</div>
<div>
<strong>Vadeli İşlem</strong><br>
<span class="muted">
Funding • OI • Basis
</span>
</div>
</div>

<div class="flow-step">
<div class="flow-number">6</div>
<div>
<strong>Strateji</strong><br>
<span class="muted">
Çoklu strateji
</span>
</div>
</div>

<div class="flow-step">
<div class="flow-number">7</div>
<div>
<strong>Risk</strong><br>
<span class="muted">
Pozisyon kontrolü
</span>
</div>
</div>

</div>

<p class="muted">
Canlı token tarayıcı Runtime entegrasyonunda
bağlanacaktır. Dashboard sahte piyasa sayısı üretmez.
</p>

</div>'''

new = '''<div class="section-title">
Canlı Piyasa Seçim Zinciri
</div>

<div class="card">

<div style="
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:16px;
    flex-wrap:wrap;
    margin-bottom:18px;
">

<div>
<strong>Market Intelligence Cycle</strong><br>
<span class="muted">
Hacim • Likidite • Futures • Temporal Evidence
</span>
</div>

<div id="marketCycleStatus"
     class="status status-wait">
YÜKLENİYOR
</div>

</div>

<div class="flow">

<div class="flow-step">
<div class="flow-number">1</div>
<div>
<strong>Piyasa Taraması</strong><br>
<span class="muted">
Hacim + likidite filtresi
</span>
</div>
</div>

<div class="flow-step">
<div class="flow-number">2</div>
<div>
<strong id="marketCandidates">-</strong> Aday<br>
<span class="muted">
Analiz evreni
</span>
</div>
</div>

<div class="flow-step">
<div class="flow-number">3</div>
<div>
<strong id="marketFuturesMatched">-</strong> Futures<br>
<span class="muted">
USDT perpetual eşleşmesi
</span>
</div>
</div>

<div class="flow-step">
<div class="flow-number">4</div>
<div>
<strong id="marketSnapshotComplete">-</strong>
/
<strong id="marketSnapshotTotal">-</strong>
Veri Tam<br>
<span class="muted">
Funding • OI • Basis • L/S • Taker
</span>
</div>
</div>

<div class="flow-step">
<div class="flow-number">5</div>
<div>
<strong id="marketObservable">-</strong> Olgun<br>
<span class="muted">
Temporal kanıt yeterli
</span>
</div>
</div>

<div class="flow-step">
<div class="flow-number">6</div>
<div>
<strong id="marketHistorical">-</strong> Geçmiş<br>
<span class="muted">
Aktif evren dışında korunan
</span>
</div>
</div>

</div>

<div style="
    margin-top:18px;
    padding:14px 16px;
    border:1px solid var(--border);
    border-radius:12px;
    background:#11182a;
">

<strong id="marketMode">WARMUP</strong>

<div id="marketModeExplanation"
     class="muted"
     style="margin-top:5px;">
Piyasa verileri yükleniyor.
</div>

</div>

</div>'''

if old not in s:
    raise SystemExit(
        "STOP: PIYASA SECIM ZINCIRI BLOKU BULUNAMADI"
    )

s = s.replace(old, new, 1)

# ---------------------------------------------------------
# 2. DEVELOPMENT TABLE: THESE TWO ARE NOW ACTIVE
# ---------------------------------------------------------

s = s.replace(
'''<td>Token Tarayıcı</td>
<td class="status-wait">ENTEGRASYON</td>''',
'''<td>Token Tarayıcı</td>
<td class="status-ok">AKTİF</td>''',
1
)

s = s.replace(
'''<td>Hacim + Likidite seçimi</td>
<td class="status-wait">ENTEGRASYON</td>''',
'''<td>Hacim + Likidite seçimi</td>
<td class="status-ok">AKTİF</td>''',
1
)

# ---------------------------------------------------------
# 3. ADD MARKET DATA TO refreshStatus()
# ---------------------------------------------------------

marker = '''        document.getElementById("realOrder").textContent =
            data.trading.real_order_authority
            ? "AÇIK"
            : "KAPALI";
'''

addition = '''        document.getElementById("realOrder").textContent =
            data.trading.real_order_authority
            ? "AÇIK"
            : "KAPALI";

        const market = data.market_intelligence || {};

        document.getElementById(
            "marketCandidates"
        ).textContent =
            market.selection_candidates ?? "-";

        document.getElementById(
            "marketFuturesMatched"
        ).textContent =
            market.futures_matched ?? "-";

        document.getElementById(
            "marketSnapshotComplete"
        ).textContent =
            market.snapshot_complete ?? "-";

        document.getElementById(
            "marketSnapshotTotal"
        ).textContent =
            market.snapshot_symbols ?? "-";

        document.getElementById(
            "marketObservable"
        ).textContent =
            market.observable_active_symbols ?? "-";

        document.getElementById(
            "marketHistorical"
        ).textContent =
            market.historical_only_symbols ?? "-";

        const marketStatus =
            document.getElementById(
                "marketCycleStatus"
            );

        marketStatus.textContent =
            market.status || "UNKNOWN";

        marketStatus.className =
            market.status === "PASS"
            ? "status status-ok"
            : "status status-wait";

        const mode =
            market.selection_mode || "UNKNOWN";

        document.getElementById(
            "marketMode"
        ).textContent = mode;

        document.getElementById(
            "marketModeExplanation"
        ).textContent =
            mode === "WARMUP"
            ? "Likidite geçmişi biriktiriliyor. Sistem çalışıyor; yeterli gözlem oluşmadan erken karar üretmiyor."
            : "Piyasa seçim motoru aktif ve mevcut gözlem geçmişiyle çalışıyor.";
'''

if marker not in s:
    raise SystemExit(
        "STOP: refreshStatus REAL ORDER MARKER BULUNAMADI"
    )

s = s.replace(marker, addition, 1)

p.write_text(s, encoding="utf-8")

print("DASHBOARD MARKET UI V2 PATCH PASS")
