import json
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query


router = APIRouter(prefix="/api/agent", tags=["agent"])
ROOT = Path(__file__).resolve().parent
MEMORY_DB = ROOT / "agent_memory.db"
PORTFOLIO_DB = ROOT / "agent_portfolio.db"


def read_rows(path, sql, parameters=()):
    if not path.is_file():
        raise HTTPException(status_code=503, detail="Ajan veritabani bulunamadi")

    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(sql, parameters).fetchall()]
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Ajan kayitlari okunamadi")


def parse_indicators(raw):
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def find_trade_reasons(trades):
    needed = {
        str(trade["candle_id"])
        for trade in trades
        if trade["candle_id"] is not None
    }
    reasons = {}

    if not needed:
        return reasons

    if not MEMORY_DB.is_file():
        raise HTTPException(status_code=503, detail="Ajan veritabani bulunamadi")

    try:
        with sqlite3.connect(
            MEMORY_DB.resolve().as_uri() + "?mode=ro",
            uri=True,
        ) as db:
            for (raw,) in db.execute(
                "SELECT indicators FROM analyses ORDER BY id DESC"
            ):
                indicators = parse_indicators(raw)
                candle_id = indicators.get("candle_close_ms")

                if candle_id is None:
                    continue

                key = str(candle_id)
                if key in needed:
                    reasons[key] = indicators.get("reason")
                    needed.remove(key)

                if not needed:
                    break
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Ajan kayitlari okunamadi")

    return reasons


@router.get("/history")
def agent_history(limit: int = Query(default=50, ge=1, le=200)):
    analyses = read_rows(
        MEMORY_DB,
        """
        SELECT id, symbol, signal, indicators, created_at
        FROM analyses
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )

    trades = read_rows(
        PORTFOLIO_DB,
        """
        SELECT id, symbol, side, quantity, price, gross, fee,
               realized_pnl, created_at, candle_id
        FROM trades
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )

    decisions = []
    for analysis in analyses:
        indicators = parse_indicators(analysis["indicators"])

        decisions.append({
            "id": analysis["id"],
            "symbol": analysis["symbol"],
            "signal": analysis["signal"],
            "created_at": analysis["created_at"],
            "candle_id": indicators.get("candle_close_ms"),
            "price": indicators.get("price"),
            "ema9": indicators.get("ema9"),
            "ema21": indicators.get("ema21"),
            "reason": indicators.get("reason"),
        })

    reasons = find_trade_reasons(trades)

    for trade in trades:
        trade["reason"] = reasons.get(str(trade["candle_id"]))

    return {
        "mode": "paper_trading",
        "decisions": decisions,
        "trades": trades,
    }
