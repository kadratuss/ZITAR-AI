
from fastapi import FastAPI, HTTPException
from datetime import datetime, timezone

from binance_data import get_btc_price
from market_engine import get_market_data

from paper_trading import (
    init_database,
    get_portfolio
)

from portfolio_valuation import (
    get_portfolio_valuation
)

from research_api import router as research_router
from agent_api import router as agent_router
from agent_chat_api import router as agent_chat_router


# PORTFOLIO AI - BACKEND

APP_ID = "portfolioai-backend-pars-v1"

app = FastAPI(
    title="PortfolioAI API",
    version="0.4.0",
    description="PortfolioAI sanal yatirim sistemi"
)

# ARASTIRMA API
app.include_router(research_router)
app.include_router(agent_router)
app.include_router(agent_chat_router)


# VERITABANINI HAZIRLA

init_database()


# ANA SAYFA

@app.get("/")
def home():

    return {
        "application": "PortfolioAI",
        "status": "online",
        "mode": "paper_trading",
        "real_trading": False,
        "version": "0.4.0"
    }


# SISTEM DURUMU

@app.get("/api/status")
def system_status():

    try:

        portfolio = get_portfolio()

        open_positions = len(
            portfolio["positions"]
        )

    except Exception as error:

        print("Portfoy durum hatasi:", error)

        raise HTTPException(
            status_code=503,
            detail="Portfoy durumu alinamadi"
        )

    return {
        "server": "online",
        "agent": "not_started",
        "market": "Binance TR Spot",
        "initial_capital_try": 10000,
        "capital_is_demo": True,
        "monitored_pairs_target": 20,
        "strategy_count_target": 3,
        "max_positions": 10,
        "open_positions": open_positions,
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat()
    }


# BTC FIYATI

@app.get("/api/market/btc")
def btc_market():

    try:

        return get_btc_price()

    except Exception as error:

        print("BTC API hatasi:", error)

        raise HTTPException(
            status_code=503,
            detail="Binance TR BTC verisi alinamadi"
        )


# EN LIKIT 20 PARITE

@app.get("/api/market/top20")
def top20_market():

    try:

        return get_market_data()

    except Exception as error:

        print("Piyasa motoru hatasi:", error)

        raise HTTPException(
            status_code=503,
            detail="Binance TR piyasa verileri alinamadi"
        )


# SANAL PORTFOY

@app.get("/api/portfolio")
def portfolio():

    try:

        return get_portfolio()

    except Exception as error:

        print("Portfoy API hatasi:", error)

        raise HTTPException(
            status_code=503,
            detail="Sanal portfoy verileri alinamadi"
        )


# GUNCEL PORTFOY DEGERLEME

@app.get("/api/portfolio/valuation")
def portfolio_valuation():

    try:

        return get_portfolio_valuation()

    except Exception as error:

        print(
            "Portfoy degerleme hatasi:",
            error
        )

        raise HTTPException(
            status_code=503,
            detail="Portfoy degerleme verileri alinamadi"
        )


# SAGLIK KONTROLU

@app.get("/api/health")
def health():

    return {
        "status": "ok",
        "service": "PortfolioAI Backend",
        "app_id": APP_ID,
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat()
    }

