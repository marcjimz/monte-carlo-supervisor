"""Distribution specs routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from server.auth import User, get_current_user
from server.services import distribution_service

router = APIRouter(prefix="/distributions", tags=["distributions"])


@router.get("")
async def list_distributions(user: User = Depends(get_current_user)):
    specs = await distribution_service.list_distribution_specs()
    return {"distributions": specs}
