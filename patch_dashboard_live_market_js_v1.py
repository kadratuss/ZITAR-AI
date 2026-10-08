from pathlib import Path

p = Path("zitar_dashboard_api_v1.py")
s = p.read_text(encoding="utf-8-sig")

backup = Path("zitar_dashboard_api_v1_before_market_js.py")
backup.write_text(s, encoding="utf-8")

# refreshStatus() içinde status JSON'u alındıktan sonra
# ekleyebileceğimiz güvenli noktayı bul.
candidates = [
    "const data = await response.json();",
    "const data = await r.json();",
    "const d = await response.json();",
    "const d = await r.json();",
]

anchor = None
data_var = None

for c in candidates:
    if c in s:
        anchor = c
        if "const data =" in c:
            data_var = "data"
        else:
            data_var = "d"
        break

if anchor is None:
    raise SystemExit(
        "STOP: refreshStatus JSON anchor bulunamadi."
    )

js = f'''

        // -------------------------------------------------
        // LIVE MARKET INTELLIGENCE
        // -------------------------------------------------

        const mi = {data_var}.market_intelligence || {{}};

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


        if (marketCycleStatus) {{
            marketCycleStatus.textContent =
                mi.status || "UNKNOWN";

            marketCycleStatus.className =
                mi.status === "PASS"
                    ? "status-pass"
                    : "status-wait";
        }}


        if (marketCandidates) {{
            marketCandidates.textContent =
                mi.selection_candidates ?? "-";
        }}


        if (marketFuturesMatched) {{
            marketFuturesMatched.textContent =
                mi.futures_matched ?? "-";
        }}


        if (marketSnapshotComplete) {{
            marketSnapshotComplete.textContent =
                mi.snapshot_complete ?? "-";
        }}


        if (marketSnapshotTotal) {{
            marketSnapshotTotal.textContent =
                mi.snapshot_symbols ?? "-";
        }}


        if (marketObservable) {{
            marketObservable.textContent =
                mi.observable_active_symbols ?? "-";
        }}


        if (marketHistorical) {{
            marketHistorical.textContent =
                mi.historical_only_symbols ?? "-";
        }}


        if (marketMode) {{
            marketMode.textContent =
                mi.selection_mode || "UNKNOWN";

            marketMode.className =
                mi.selection_mode === "READY"
                    ? "status-pass"
                    : "yellow";
        }}


        if (marketModeExplanation) {{

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

            if (mi.selection_mode === "WARMUP") {{
                marketModeExplanation.textContent =
                    `Seçim motoru veri biriktiriyor. ` +
                    `${{candidates}} aday seçildi, ` +
                    `${{matched}} futures eşleşmesi bulundu, ` +
                    `${{complete}}/${{total}} futures verisi tam, ` +
                    `${{observable}} aktif sembolde temporal kanıt yeterli.`;
            }}
            else {{
                marketModeExplanation.textContent =
                    `${{candidates}} aday, ` +
                    `${{matched}} futures eşleşmesi, ` +
                    `${{complete}}/${{total}} tam veri, ` +
                    `${{observable}} temporal olarak gözlemlenebilir sembol.`;
            }}
        }}

'''

# Aynı patch ikinci kez çalıştırılmasın.
if "// LIVE MARKET INTELLIGENCE" in s:
    raise SystemExit(
        "STOP: LIVE MARKET JS zaten dosyada mevcut."
    )

s = s.replace(anchor, anchor + js, 1)

p.write_text(s, encoding="utf-8")

# -------------------------------------------------
# VERIFY
# -------------------------------------------------

check = p.read_text(encoding="utf-8")

required = [
    '// LIVE MARKET INTELLIGENCE',
    'document.getElementById("marketCycleStatus")',
    'document.getElementById("marketCandidates")',
    'document.getElementById("marketFuturesMatched")',
    'document.getElementById("marketSnapshotComplete")',
    'document.getElementById("marketSnapshotTotal")',
    'document.getElementById("marketObservable")',
    'document.getElementById("marketHistorical")',
    'document.getElementById("marketMode")',
    'document.getElementById("marketModeExplanation")',
    '.market_intelligence',
]

missing = [x for x in required if x not in check]

if missing:
    raise SystemExit(
        "STOP: MARKET JS EKSIK: " +
        ", ".join(missing)
    )

print("LIVE MARKET JS PATCH PASS")
print("required:", len(required), "/", len(required))
print("data variable:", data_var)
print("backup:", backup)
