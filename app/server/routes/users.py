"""User search endpoint via Databricks SCIM API."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from server.auth import User, get_current_user
from server.services.sql_client import _get_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/search")
async def search_users(
    q: str = Query(..., min_length=2),
    user: User = Depends(get_current_user),
):
    """Search workspace users by email via SCIM."""
    try:
        w = _get_client()
        results = []
        for u in w.users.list(filter=f'userName co "{q}"', count=10):
            email = u.user_name
            display = u.display_name or email.split("@")[0]
            results.append({"email": email, "display_name": display})
        return {"users": results}
    except Exception:
        logger.exception("SCIM user search failed")
        return {"users": []}
