"""Delta to Lakebase sync routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from server.auth import User, get_current_user
from server.services import sync_service

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/trigger")
async def trigger_sync(user: User = Depends(get_current_user)):
    result = await sync_service.run_full_sync()
    return result


@router.get("/status")
async def sync_status(user: User = Depends(get_current_user)):
    status = await sync_service.get_sync_status()
    return {"tables": status}
