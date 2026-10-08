
import json
from pathlib import Path


def main():
    # Dosyanin bulundugu yere gore yol buluyoruz.
    # Boylece baska bilgisayara tasindiginda
    # C:\Users\... gibi sabit bir yola bagli kalmayiz.
    core_dir = Path(__file__).resolve().parent
    personal_ai_dir = core_dir.parent
    config_file = personal_ai_dir / "system_config.json"

    print("PERSONAL AI - SISTEM KONTROLU")
    print("----------------------------")

    if not config_file.is_file():
        print("[HATA] system_config.json bulunamadi.")
        return

    try:
        config = json.loads(
            config_file.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        print("[HATA] Yapilandirma okunamadi:", error)
        return

    print("[OK] Yapilandirma okundu.")
    print("Sistem:", config.get("system_name", "Belirtilmemis"))
    print("Surum:", config.get("version", "Belirtilmemis"))

    errors = []

    for name, relative_path in config.get("paths", {}).items():
        folder = personal_ai_dir / relative_path

        if folder.is_dir():
            print(f"[OK] {name}: {folder}")
        else:
            print(f"[HATA] {name} klasoru bulunamadi: {folder}")
            errors.append(name)

    portfolio = config.get("modules", {}).get("portfolio_ai", {})
    portfolio_dir = personal_ai_dir / portfolio.get("location", "..")

    if portfolio_dir.is_dir() and (portfolio_dir / "main.py").is_file():
        print("[OK] PortfolioAI Backend bulundu.")
    else:
        print("[HATA] PortfolioAI Backend veya main.py bulunamadi.")
        errors.append("portfolio_ai")

    if errors:
        print("\nSONUC: Kontrol tamamlandi, eksikler var.")
    else:
        print("\nSONUC: Tum kontroller basarili.")


if __name__ == "__main__":
    main()