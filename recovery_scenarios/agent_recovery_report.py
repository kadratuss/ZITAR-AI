import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def open_readonly(filename):
    path = BASE_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Veritabani bulunamadi: {path}")

    db = sqlite3.connect(
        f"file:{path.as_posix()}?mode=ro",
        uri=True,
        timeout=10,
    )
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout = 10000")
    return db


def format_time(value):
    if value is None:
        return "-"

    try:
        if isinstance(value, int):
            return datetime.fromtimestamp(
                value / 1000, tz=timezone.utc
            ).isoformat()
        return str(value)
    except (ValueError, OverflowError, OSError):
        return str(value)


def matching_analyses(memory, candle_id):
    matches = []

    for analysis in memory.execute(
        """
        SELECT id, signal, indicators, created_at
        FROM analyses
        ORDER BY id DESC
        """
    ):
        try:
            indicators = json.loads(analysis["indicators"])
        except (TypeError, ValueError):
            continue

        if (
            isinstance(indicators, dict)
            and str(indicators.get("candle_close_ms")) == str(candle_id)
        ):
            matches.append(analysis)

    return matches


def main():
    print("PORTFOLIOAI - SALT OKUNUR KURTARMA RAPORU")
    print("Rapor zamani (UTC):", datetime.now(timezone.utc).isoformat())
    print("Veritabanlari DEGISTIRILMEZ.")
    print("=" * 60)

    with (
        open_readonly("agent_runner_state.db") as state,
        open_readonly("agent_portfolio.db") as portfolio,
        open_readonly("agent_memory.db") as memory,
    ):
        trade_columns = {
            row["name"]
            for row in portfolio.execute("PRAGMA table_info(trades)")
        }
        if "candle_id" not in trade_columns:
            raise RuntimeError(
                "trades.candle_id bulunamadi; rapor icin sema gecisi gerekli."
            )

        statuses = state.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM candle_runs
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()

        print("\nTUR DURUMLARI")
        for row in statuses:
            print(f"{row['status']}: {row['total']}")

        pending = state.execute(
            """
            SELECT candle_id, status, signal, details, created_at
            FROM candle_runs
            WHERE status = 'PENDING'
            ORDER BY candle_id
            """
        ).fetchall()

        print("\nPENDING KAYITLAR:", len(pending))
        for row in pending:
            candle_id = row["candle_id"]
            linked_trades = portfolio.execute(
                """
                SELECT id, side, symbol, quantity, realized_pnl
                FROM trades
                WHERE candle_id = ?
                ORDER BY id
                """,
                (candle_id,),
            ).fetchall()

            print(
                "Mum:", format_time(candle_id),
                "| Sinyal:", row["signal"],
                "| Olusturulma:", row["created_at"],
                "| Detay:", row["details"],
            )

            if linked_trades:
                print(
                    "  UYARI: Bu PENDING mum icin",
                    len(linked_trades),
                    "kayitli sanal islem bulundu."
                )
                for trade in linked_trades:
                    print(
                        f"  Islem #{trade['id']} | {trade['side']} "
                        f"{trade['symbol']} | Miktar: {trade['quantity']} | "
                        f"K/Z: {trade['realized_pnl']}"
                    )
            else:
                print(
                    "  Bu candle_id ile kayitli sanal islem bulunamadi."
                )
                print(
                    "  NOT: Bu bulgu tek basina islemin "
                    "guvenle tekrarlanabilecegini kanitlamaz."
                )

            analyses = matching_analyses(memory, candle_id)
            print("  Eslesen analiz:", len(analyses))
            for analysis in analyses:
                print(
                    f"  Analiz #{analysis['id']} | "
                    f"{analysis['signal']} | {analysis['created_at']}"
                )

        print("\nISLEM KAYDI VAR, TUR DURUMU DONE DEGIL")
        linked_trades = portfolio.execute(
            """
            SELECT id, candle_id, side, symbol, quantity
            FROM trades
            WHERE candle_id IS NOT NULL
            ORDER BY id DESC
            """
        ).fetchall()

        mismatches = 0
        for trade in linked_trades:
            run = state.execute(
                """
                SELECT status, signal
                FROM candle_runs
                WHERE candle_id = ?
                """,
                (trade["candle_id"],),
            ).fetchone()

            if run is None or run["status"] != "DONE":
                mismatches += 1
                status = "TUR KAYDI YOK" if run is None else run["status"]
                print(
                    f"Islem #{trade['id']} | "
                    f"Mum: {format_time(trade['candle_id'])} | "
                    f"{trade['side']} {trade['symbol']} | "
                    f"Tur durumu: {status}"
                )

        if mismatches == 0:
            print("Uyumsuzluk bulunamadi.")

        legacy_count = portfolio.execute(
            """
            SELECT COUNT(*)
            FROM trades
            WHERE candle_id IS NULL
            """
        ).fetchone()[0]
        print(
            "\nESKI ISLEMLER (candle_id NULL):",
            legacy_count,
        )
        print(
            "Bu islemler mum kimligiyle geriye donuk "
            "eslestirilemez; kimlik uydurulmaz."
        )

        print("\nSON 5 TUR")
        for row in state.execute(
            """
            SELECT candle_id, status, signal, details
            FROM candle_runs
            ORDER BY candle_id DESC
            LIMIT 5
            """
        ):
            print(
                format_time(row["candle_id"]),
                "|", row["status"],
                "|", row["signal"],
                "|", row["details"],
            )

        print("\nSANAL HESAP")
        account = portfolio.execute(
            """
            SELECT balance, realized_pnl
            FROM account
            WHERE id = 1
            """
        ).fetchone()

        if account is None:
            print("Hesap kaydi bulunamadi.")
        else:
            print("Bakiye:", account["balance"], "TRY")
            print("Gerceklesen K/Z:", account["realized_pnl"], "TRY")

        print("\nACIK POZISYONLAR")
        positions = portfolio.execute(
            """
            SELECT symbol, quantity, cost_basis
            FROM positions
            ORDER BY symbol
            """
        ).fetchall()

        if not positions:
            print("Acik pozisyon yok.")

        for row in positions:
            print(
                row["symbol"],
                "| Miktar:", row["quantity"],
                "| Maliyet:", row["cost_basis"],
            )

        print("\nSON 10 SANAL ISLEM")
        trades = portfolio.execute(
            """
            SELECT id, candle_id, symbol, side, quantity,
                   price, fee, realized_pnl, created_at
            FROM trades
            ORDER BY id DESC
            LIMIT 10
            """
        ).fetchall()

        for row in trades:
            candle = (
                "ESKI / NULL"
                if row["candle_id"] is None
                else str(row["candle_id"])
            )
            print(
                f"#{row['id']} | {row['created_at']} | "
                f"{row['side']} {row['symbol']} | "
                f"Mum: {candle} | "
                f"Miktar: {row['quantity']} | "
                f"Fiyat: {row['price']} | "
                f"Komisyon: {row['fee']} | "
                f"K/Z: {row['realized_pnl']}"
            )

        print("\nSON 5 DENEYIM")
        experiences = memory.execute(
            """
            SELECT id, trade_id, symbol, realized_pnl, created_at
            FROM experiences
            ORDER BY id DESC
            LIMIT 5
            """
        ).fetchall()

        for row in experiences:
            print(
                f"Deneyim #{row['id']} | "
                f"Islem #{row['trade_id']} | "
                f"{row['symbol']} | "
                f"K/Z: {row['realized_pnl']} | "
                f"{row['created_at']}"
            )

    print("\nRAPOR TAMAMLANDI - HICBIR KAYIT DEGISTIRILMEDI")
    print(
        "NOT: Rapor otomatik kurtarma yapmaz. "
        "PENDING kayitlar elle incelenmeden tekrar calistirilmamalidir."
    )


if __name__ == "__main__":
    main()
