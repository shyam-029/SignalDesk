# Landing snapshot endpoint (work list item 13): every query the landing page
# needs, in one response. See app/services/landing_snapshot.py.

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.services import landing_snapshot

router = APIRouter(tags=["landing"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/landing")
async def landing(request: Request, session: SessionDep) -> dict[str, Any]:
    return await landing_snapshot.get_snapshot(session, request.app)
