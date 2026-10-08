
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


# PortfolioAI - Guvenli Yedekleme
#
# Kaynak klasordeki dosyalari silmez veya degistirmez.
# Yedekler Documents/PortfolioAI-Backups icine yazilir.
# SQLite veritabanlarini backup API ile kopyalar.

SOURCE = Path(__file__).resolve().parent

BACKUP_ROOT = (
    Path.home()
    / "Documents"
    / "PortfolioAI-Backups"
)

EXCLUDED_DIRS = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    ".idea",
    ".pytest_cache"
}

EXCLUDED_FILES = {
    ".env",
    ".env.local",
    ".env.production"
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo"
}


def is_excluded(path):
    relative = path.relative_to(SOURCE)

    if any(
        part in EXCLUDED_DIRS
        for part in relative.parts[:-1]
    ):
        return True

    if path.name.lower() in EXCLUDED_FILES:
        return True

    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True

    # Gecici SQLite dosyalari ayri kopyalanmaz.
    if path.name.endswith((
        "-wal",
        "-shm",
        "-journal"
    )):
        return True

    return False


def sha256(path):
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def backup_database(source, destination):
    destination.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    source_db = sqlite3.connect(
        f"file:{source.as_posix()}?mode=ro",
        uri=True,
        timeout=15
    )

    destination_db = sqlite3.connect(
        destination,
        timeout=15
    )

    try:
        source_db.backup(destination_db)

        check = destination_db.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if check != "ok":
            raise RuntimeError(
                f"Veritabani kontrolu basarisiz: "
                f"{source.name}: {check}"
            )

    finally:
        destination_db.close()
        source_db.close()


def main():
    if not SOURCE.is_dir():
        raise RuntimeError(
            "Backend klasoru bulunamadi."
        )

    BACKUP_ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    destination = (
        BACKUP_ROOT
        / f"PortfolioAI_{timestamp}"
    )

    # Ayni isimli klasoru ezme.
    destination.mkdir(
        parents=False,
        exist_ok=False
    )

    manifest = {
        "source": str(SOURCE),
        "backup": str(destination),
        "created_at": datetime.now().isoformat(),
        "files": []
    }

    copied = 0
    databases = 0
    skipped = 0

    print("PORTFOLIOAI - YEDEKLEME")
    print("----------------------")
    print("Kaynak:", SOURCE)
    print("Hedef:", destination)
    print()

    try:
        for source_file in SOURCE.rglob("*"):

            if not source_file.is_file():
                continue

            if is_excluded(source_file):
                skipped += 1
                continue

            relative = source_file.relative_to(
                SOURCE
            )

            target_file = destination / relative

            target_file.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            if source_file.suffix.lower() in (
                ".db",
                ".sqlite",
                ".sqlite3"
            ):
                backup_database(
                    source_file,
                    target_file
                )

                databases += 1

            else:
                shutil.copy2(
                    source_file,
                    target_file
                )

                if (
                    sha256(source_file)
                    != sha256(target_file)
                ):
                    raise RuntimeError(
                        "Dosya dogrulamasi basarisiz: "
                        + str(relative)
                    )

            manifest["files"].append({
                "path": str(relative),
                "size": target_file.stat().st_size,
                "sha256": sha256(target_file)
            })

            copied += 1

            print("[OK]", relative)

        manifest_path = (
            destination
            / "backup_manifest.json"
        )

        manifest_path.write_text(
            json.dumps(
                manifest,
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

        print()
        print("YEDEKLEME TAMAMLANDI")
        print("--------------------")
        print("Kopyalanan dosya:", copied)
        print("SQLite veritabani:", databases)
        print("Atlanan dosya:", skipped)
        print("Yedek klasoru:", destination)
        print()
        print(
            "NOT: .venv ve .env dosyalari "
            "yedeklenmedi."
        )

    except Exception:
        print()
        print(
            "YEDEKLEME TAMAMLANAMADI. "
            "Hedef klasoru kontrol et."
        )
        raise


if __name__ == "__main__":
    main()