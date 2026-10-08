
from fastapi import FastAPI, HTTPException
from paper_trading import init_database, get_portfolio
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from decimal import Decimal
from contextlib import asynccontextmanager

from binance_data import get_btc_price
from market_engine import get_market_data

from paper_trading import (
    init_database,
    get_portfolio,
    buy,
    sell
)


# PORTFOLIO AI - BACKEND


@asynccontextmanager
async def lifespan(app: FastAPI):

    init_database()

    print("PortfolioAI veritabani hazir")

    yield


app = FastAPI(
    title="PortfolioAI API",
    version="0.4.0",
    description="PortfolioAI sanal yatirim sistemi",
    lifespan=lifespan
)


# SANAL ISLEM MODELLERI


class BuyRequest(BaseModel):

    symbol: str = Field(min_length=4, max_length=30)

    amount_try: Decimal = Field(gt=0)

    price: Decimal = Field(gt=0)


class SellRequest(BaseModel):

    symbol: str = Field(min_length=4, max_length=30)

    quantity: Decimal = Field(gt=0)

    price: Decimal = Field(gt=0)


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
        "open_positions": len(
            portfolio["positions"]
        ),
        "paper_balance_try": portfolio["balance"],
        "realized_pnl_try": portfolio["realized_pnl"],
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
            detail="Sanal portfoy alinamadi"
        )


# SANAL ALIS


@app.post("/api/paper/buy")
def paper_buy(request: BuyRequest):

    try:

        return buy(
            request.symbol,
            request.amount_try,
            request.price
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception as error:

        print("Sanal alis hatasi:", error)

        raise HTTPException(
            status_code=500,
            detail="Sanal alis gerceklestirilemedi"
        )


# SANAL SATIS


@app.post("/api/paper/sell")
def paper_sell(request: SellRequest):

    try:

        return sell(
            request.symbol,
            request.quantity,
            request.price
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception as error:

        print("Sanal satis hatasi:", error)

        raise HTTPException(
            status_code=500,
            detail="Sanal satis gerceklestirilemedi"
        )


# SAGLIK KONTROLU


@app.get("/api/health")
def health():

    return {
        "status": "ok",
        "service": "PortfolioAI Backend",
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat()

# SANAL PORTFOY

@app.get("/api/portfolio")
def portfolio():

    try:
        init_database()
        return get_portfolio()

    except Exception as error:

        print("Portfoy hatasi:", error)

        raise HTTPException(
            status_code=500,
            detail="Sanal portfoy verileri alinamadi"
        )
    }