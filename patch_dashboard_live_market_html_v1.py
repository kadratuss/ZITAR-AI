from pathlib import Path

p = Path("zitar_dashboard_api_v1.py")
s = p.read_text(encoding="utf-8-sig")

# Güvenlik yedeği
backup = Path("zitar_dashboard_api_v1_before_live_market_ui.py")
backup.write_text(s, encoding="utf-8")

start_marker = '''<div class="section-title">
Piyasa Seçim Motoru
</div>'''

end_marker = '''<div class="section-title">
ZİTAR Hafıza ve Öğrenme
</div>'''

start = s.find(start_marker)
end = s.find(end_marker, start)

if start == -1:
    raise SystemExit(
        "STOP: PIYASA SECIM MOTORU BASLANGICI BULUNAMADI"
    )

if end == -1:
    raise SystemExit(
        "STOP: HAFIZA BOLUMU SINIRI BULUNAMADI"
    )

new_market = '''<div class="section-title">
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


'''

s = s[:start] + new_market + s[end:]

p.write_text(s, encoding="utf-8")

# ---------------------------------------------------------
# PATCH VERIFICATION
# ---------------------------------------------------------

check = p.read_text(encoding="utf-8")

required = [
    'id="marketCycleStatus"',
    'id="marketCandidates"',
    'id="marketFuturesMatched"',
    'id="marketSnapshotComplete"',
    'id="marketSnapshotTotal"',
    'id="marketObservable"',
    'id="marketHistorical"',
    'id="marketMode"',
    'id="marketModeExplanation"',
]

missing = [x for x in required if x not in check]

if missing:
    raise SystemExit(
        "STOP: EKSIK UI ELEMENTLERI: " +
        ", ".join(missing)
    )

if "Canlı token tarayıcı Runtime entegrasyonunda" in check:
    raise SystemExit(
        "STOP: ESKI PLACEHOLDER HALA DOSYADA"
    )

print("LIVE MARKET HTML PATCH PASS")
print("required elements:", len(required), "/", len(required))
print("old placeholder removed: YES")
print("backup:", backup)
