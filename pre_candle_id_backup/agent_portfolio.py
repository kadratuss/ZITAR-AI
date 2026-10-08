
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

# PortfolioAI - Ajana ozel sanal portfoy
# Gercek borsa emri gondermez.
# Mevcut portfolio.db dosyasini kullanmaz.

BASE_DIR = Path(__file__).resolve().parent
AGENT_DB_PATH = BASE_DIR / "agent_portfolio.db"
PAPER_ENGINE_PATH = BASE_DIR / "paper_trading.py"


def load_agent_engine():
    if not PAPER_ENGINE_PATH.is_file():
        raise FileNotFoundError(
            f"Sanal islem motoru bulunamadi: {PAPER_ENGINE_PATH}"
        )

    spec = spec_from_file_location(
        "portfolioai_agent_paper_engine",
        PAPER_ENGINE_PATH
    )

    if spec is None or spec.loader is None:
        raise RuntimeError("Sanal islem motoru yuklenemedi")

    engine = module_from_spec(spec)
    spec.loader.exec_module(engine)

    # Bu motorun veritabani yalnizca ajana aittir.
    engine.DB_PATH = AGENT_DB_PATH

    return engine


_engine = load_agent_engine()


def init_database():
    """Ajanin ayri sanal veritabanini hazirlar."""
    _engine.init_database()


def get_portfolio():
    """Ajanin sanal bakiyesini ve islemlerini okur."""
    return _engine.get_portfolio()


def buy(symbol, amount_try, price):
    """Yalnizca ajan veritabaninda sanal alis yapar."""
    return _engine.buy(symbol, amount_try, price)


def sell(symbol, qty, price):
    """Yalnizca ajan veritabaninda sanal satis yapar."""
    return _engine.sell(symbol, qty, price)


if __name__ == "__main__":
    init_database()

    print("PortfolioAI - Ajan Sanal Portfoyu")
    print("--------------------------------")
    print("Veritabani:", AGENT_DB_PATH)
    print(get_portfolio())