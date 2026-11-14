# GET /screener/underrated: companies in good shape whose price assumes
# little and which the market has not yet re-rated (services/underrated.py).
# Read-only, from stored data. A research screen, not a recommendation.

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.repositories import underrated as repo
from app.services import underrated as svc

router = APIRouter(prefix="/screener", tags=["screener"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class CheckOut(BaseModel):
    key: str
    label: str
    passed: bool | None
    detail: str


class UnderratedItem(BaseModel):
    symbol: str
    name: str
    sector: str | None
    passes: int
    needed_growth_pct: float | None
    own_growth_pct: float | None
    gap_points: float | None
    low_base: bool
    fundamental: float | None
    strength: float | None
    from_high_pct: float | None
    checks: list[CheckOut]


class UnderratedResponse(BaseModel):
    items: list[UnderratedItem]
    matches: int  # pass all four checks
    near_misses: int  # pass exactly three
    scanned: int
    thresholds: dict[str, float]


@router.get("/underrated", response_model=UnderratedResponse)
async def underrated(
    session: SessionDep,
    min_checks: int = Query(3, ge=1, le=4),
    sector: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> UnderratedResponse:
    """Stocks passing at least `min_checks` of the four checks, best first.

    Ranked by checks passed, then by how far the company's own earnings
    growth is ahead of what its price needs.
    """
    everything = await repo.scan(session)
    shown = [
        r for r in everything
        if r.passes >= min_checks and (sector is None or r.sector == sector)
    ]
    return UnderratedResponse(
        items=[
            UnderratedItem(
                symbol=r.symbol, name=r.name, sector=r.sector, passes=r.passes,
                needed_growth_pct=r.needed_growth_pct, own_growth_pct=r.own_growth_pct,
                gap_points=r.gap_points, low_base=r.low_base, fundamental=r.fundamental, strength=r.strength,
                from_high_pct=None if r.from_high_pct is None else round(r.from_high_pct, 1),
                checks=[CheckOut(key=c.key, label=c.label, passed=c.passed, detail=c.detail)
                        for c in r.checks],
            )
            for r in shown[:limit]
        ],
        matches=sum(1 for r in everything if r.passes == 4),
        near_misses=sum(1 for r in everything if r.passes == 3),
        scanned=len(everything),
        thresholds={
            "min_fundamental": svc.MIN_FUNDAMENTAL,
            "min_solvency": svc.MIN_SOLVENCY,
            "max_needed_growth_pct": svc.MAX_NEEDED_GROWTH_PCT,
            "min_growth_gap_points": svc.MIN_GROWTH_GAP_POINTS,
            "max_strength": svc.MAX_STRENGTH,
            "min_below_high_pct": svc.MIN_BELOW_HIGH_PCT,
        },
    )
