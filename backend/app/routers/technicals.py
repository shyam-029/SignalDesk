# Technicals endpoint — raw indicator values + the existing sub-scores.
#
# Phase 6 need: /alpha exposes only the technical sub-SCORES (trend/momentum/
# reversion), while the stock research page must show the underlying indicator
# readings (SMA20, EMA12, RSI14, MACD). This endpoint reuses the SAME pure
# functions from services/indicators.py — no duplicated math.
#
# A human-readable verdict ("Bearish", "Bullish", ...) is deliberately NOT
# computed here: it is presentation logic derived from the score band on the
# client. The backend provides the evidence; the frontend phrases it.

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.routers.common import resolve_stock
from app.repositories import prices as price_repo
from app.services import indicators

router = APIRouter(prefix="/stocks", tags=["technicals"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Enough closes for SMA20 + MACD(26) — mirrors the /alpha threshold.
MIN_CLOSES = 26


class MacdBlock(BaseModel):
    macd: float | None
    signal: float | None
    histogram: float | None


class TechnicalsResponse(BaseModel):
    symbol: str
    score: int | None
    # Existing sub-scores (0-100) from score_technicals().
    components: dict[str, float | None]  # trend / momentum / reversion
    # Raw latest indicator readings (None when insufficient data).
    sma20: float | None
    ema12: float | None
    rsi14: float | None
    macd: MacdBlock
    last_close: float | None
    closes_used: int
    insufficient_data: bool


@router.get("/{symbol}/technicals", response_model=TechnicalsResponse)
async def get_technicals(symbol: str, session: SessionDep) -> TechnicalsResponse:
    """Raw SMA20/EMA12/RSI14/MACD readings + trend/momentum/reversion scores."""
    stock = await resolve_stock(session, symbol)
    closes = await price_repo.get_close_series(session, stock.id, limit=200)

    if len(closes) < MIN_CLOSES:
        # Not enough history for the indicator set — say so, don't guess.
        return TechnicalsResponse(
            symbol=stock.symbol,
            score=None,
            components={"trend": None, "momentum": None, "reversion": None},
            sma20=None,
            ema12=None,
            rsi14=None,
            macd=MacdBlock(macd=None, signal=None, histogram=None),
            last_close=closes[-1] if closes else None,
            closes_used=len(closes),
            insufficient_data=True,
        )

    # Reuse the pure indicator functions (single source of truth).
    sma20 = indicators.sma(closes, 20)
    ema12 = indicators.ema(closes, 12)
    rsi14 = indicators.rsi(closes, 14)
    macd_vals = indicators.macd(closes)
    scored = indicators.score_technicals(closes)

    comps: dict[str, float | None] = {
        "trend": scored["components"].get("trend"),
        "momentum": scored["components"].get("momentum"),
        "reversion": scored["components"].get("reversion"),
    }

    return TechnicalsResponse(
        symbol=stock.symbol,
        score=scored["score"],
        components=comps,
        sma20=sma20,
        ema12=ema12,
        rsi14=rsi14,
        macd=MacdBlock(
            macd=macd_vals["macd"],
            signal=macd_vals["signal"],
            histogram=macd_vals["histogram"],
        ),
        last_close=closes[-1],
        closes_used=len(closes),
        insufficient_data=False,
    )
