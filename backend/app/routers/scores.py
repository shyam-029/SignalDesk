# Scores endpoint — profitability + solvency scores with per-component breakdown.

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.routers.common import resolve_stock
from app.services import analysis

router = APIRouter(prefix="/stocks", tags=["scores"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class ScoreComponent(BaseModel):
    name: str
    value: float
    score: float


class ScoreCardResponse(BaseModel):
    symbol: str
    profitability: int | None
    solvency: int | None
    profitability_components: list[ScoreComponent]
    solvency_components: list[ScoreComponent]
    explanation: str


@router.get("/{symbol}/scores", response_model=ScoreCardResponse)
async def get_scores(symbol: str, session: SessionDep) -> ScoreCardResponse:
    """Compute profitability and solvency scores for a stock."""
    stock = await resolve_stock(session, symbol)
    profit, solvency, text = await analysis.compute_stock_scores(session, stock)

    return ScoreCardResponse(
        symbol=stock.symbol,
        profitability=profit.score,
        solvency=solvency.score,
        profitability_components=[
            ScoreComponent(name=c.name, value=c.value, score=c.score)
            for c in profit.components
        ],
        solvency_components=[
            ScoreComponent(name=c.name, value=c.value, score=c.score)
            for c in solvency.components
        ],
        explanation=text,
    )