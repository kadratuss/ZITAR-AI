
import sqlite3
from pathlib import Path


def main():
    # data_check.py -> core -> personal_ai -> Backend
    backend_dir = Path(__file__).resolve().parents[2]

    databases = [
        "agent_memory.db",
        "research.db",
        "portfolio.db",
    ]

    print("PERSONAL AI - VERITABANI KONTROLU")
    print("--------------------------------")

    problems = []

    for name in databases:
        db_path = backend_dir / name

        if not db_path.is_file():
            print(f"[HATA] Dosya bulunamadi: {name}")
            problems.append(name)
            continue

        try:
            # mode=ro: Veritabani yoksa olusturmaz;
            # mevcut veritabanini salt okunur acar.
            with sqlite3.connect(
                db_path.as_uri() + "?mode=ro",
                uri=True,
                timeout=5,
            ) as connection:
                result = connection.execute(
                    "PRAGMA quick_check"
                ).fetchone()

                if not result or result[0] != "ok":
                    raise RuntimeError(
                        f"SQLite kontrol sonucu: {result}"
                    )

                tables = connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    ORDER BY name
                    """
                ).fetchall()

            print(f"[OK] {name}")
            print(f"     Tablo sayisi: {len(tables)}")

        except (sqlite3.Error, OSError, RuntimeError) as error:
            print(f"[HATA] {name}: {error}")
            problems.append(name)

    print("--------------------------------")

    if problems:
        print("SONUC: Kontrol tamamlandi, eksikler var.")
    else:
        print("SONUC: Uc veritabani da okunabiliyor.")


if __name__ == "__main__":
    main()