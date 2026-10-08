from pathlib import Path

p = Path("zitar_dashboard_api_v1.py")
s = p.read_text(encoding="utf-8-sig")

backup = Path("zitar_dashboard_api_v1_before_market_js_move.py")
backup.write_text(s, encoding="utf-8")

# =========================================================
# 1. CHAT ICINDEKI YANLIS MARKET BLOGUNU KALDIR
# =========================================================

chat_start = s.find("async function sendZitarMessage()")
if chat_start == -1:
    raise SystemExit("STOP: sendZitarMessage bulunamadi.")

wrong_start = s.find(
    "// LIVE MARKET INTELLIGENCE",
    chat_start
)

if wrong_start == -1:
    raise SystemExit(
        "STOP: Chat icindeki LIVE MARKET INTELLIGENCE blogu bulunamadi."
    )

wrong_end_marker = '''        addChatMessage(
            "assistant",'''

wrong_end = s.find(
    wrong_end_marker,
    wrong_start
)

if wrong_end == -1:
    raise SystemExit(
        "STOP: Chat market blogunun bitis noktasi bulunamadi."
    )

s = s[:wrong_start] + s[wrong_end:]

print("PASS: Chat icindeki yanlis market JS kaldirildi.")

# =========================================================
# 2. REFRESHSTATUS SINIRLARINI BUL
# =========================================================

refresh_start = s.find("async function refreshStatus()")

if refresh_start == -1:
    raise SystemExit(
        "STOP: refreshStatus bulunamadi."
    )

refresh_end = s.find(
    "\nrefreshStatus();",
    refresh_start
)

if refresh_end == -1:
    raise SystemExit(
        "STOP: refreshStatus bitisi bulunamadi."
    )

refresh_block = s[refresh_start:refresh_end]

anchor = "        const d = await r.json();"

anchor_pos = refresh_block.find(anchor)

if anchor_pos == -1:
    raise SystemExit(
        "STOP: refreshStatus JSON anchor bulunamadi."
    )

# =========================================================
# 3. DOGRU MARKET JS
# =========================================================

market_js = '''

        // -------------------------------------------------
        // LIVE MARKET INTELLIGENCE
        // -------------------------------------------------

        const mi = d.market_intelligence || {};

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

            const historical =
                mi.historical_only_symbols ?? 0;

            if (mi.selection_mode === "WARMUP") {

                marketModeExplanation.textContent =
                    `Seçim motoru veri biriktiriyor. ` +
                    `${candidates} aday seçildi, ` +
                    `${matched} futures eşleşmesi bulundu, ` +
                    `${complete}/${total} futures verisi tam, ` +
                    `${observable} aktif sembolde temporal kanıt yeterli, ` +
                    `${historical} sembol yalnızca geçmiş kayıtlarda.`;

            } else {

                marketModeExplanation.textContent =
                    `${candidates} aday, ` +
                    `${matched} futures eşleşmesi, ` +
                    `${complete}/${total} tam veri, ` +
                    `${observable} temporal olarak gözlemlenebilir sembol, ` +
                    `${historical} historical-only sembol.`;
            }
        }
'''

insert_at = anchor_pos + len(anchor)

refresh_block = (
    refresh_block[:insert_at]
    + market_js
    + refresh_block[insert_at:]
)

s = (
    s[:refresh_start]
    + refresh_block
    + s[refresh_end:]
)

p.write_text(s, encoding="utf-8")

# =========================================================
# 4. YAPISAL DOGRULAMA
# =========================================================

check = p.read_text(encoding="utf-8")

refresh_start = check.find(
    "async function refreshStatus()"
)

refresh_end = check.find(
    "\nrefreshStatus();",
    refresh_start
)

chat_start = check.find(
    "async function sendZitarMessage()"
)

refresh_final = check[
    refresh_start:refresh_end
]

chat_final = check[
    chat_start:
]

errors = []

if "// LIVE MARKET INTELLIGENCE" not in refresh_final:
    errors.append(
        "Market JS refreshStatus icinde degil"
    )

if "d.market_intelligence" not in refresh_final:
    errors.append(
        "d.market_intelligence refreshStatus icinde yok"
    )

if "// LIVE MARKET INTELLIGENCE" in chat_final:
    errors.append(
        "Market JS hala chat fonksiyonunda"
    )

if "data.market_intelligence" in chat_final:
    errors.append(
        "Chat hala market_intelligence kullaniyor"
    )

if errors:
    print("VERIFY FAIL")
    for e in errors:
        print(" -", e)
    raise SystemExit(1)

print()
print("MARKET JS MOVE PASS")
print("refreshStatus -> market_intelligence: YES")
print("sendZitarMessage -> market_intelligence: NO")
print("backup:", backup)
