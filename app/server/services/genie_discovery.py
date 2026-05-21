"""Runtime Genie Space discovery by title via Databricks REST API.

Finds the Genie Space matching EXPECTED_GENIE_TITLE so the app doesn't
need GENIE_SPACE_ID wired as an env var. Falls back to settings if set.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from server.config import get_settings

logger = logging.getLogger(__name__)

EXPECTED_GENIE_TITLE = "Encounter Analytics"


@lru_cache(maxsize=1)
def _discover_genie_space_id() -> str:
    """Search for a Genie Space by title using the Databricks REST API.

    Returns the space_id if found, empty string otherwise.
    Thread-safe via @lru_cache.
    """
    settings = get_settings()

    try:
        from databricks.sdk import WorkspaceClient

        if settings.is_databricks_app:
            w = WorkspaceClient()
        else:
            w = WorkspaceClient(profile=settings.databricks_profile)

        resp = w.api_client.do(
            "GET",
            "/api/2.0/genie/spaces",
            query={"page_size": 100},
        )
        for space in resp.get("spaces", []):
            if space.get("title") == EXPECTED_GENIE_TITLE:
                space_id = space.get("space_id", "")
                logger.info(
                    "Discovered Genie Space '%s' → %s",
                    EXPECTED_GENIE_TITLE,
                    space_id,
                )
                return space_id
    except Exception:
        logger.warning("Failed to discover Genie Space by title", exc_info=True)

    logger.info("Genie Space '%s' not found", EXPECTED_GENIE_TITLE)
    return ""


def get_genie_space_id() -> str:
    """Return the Genie Space ID — from settings if set, else discovered.

    Returns empty string if no Genie Space is available.
    """
    settings = get_settings()
    if settings.genie_space_id:
        return settings.genie_space_id
    return _discover_genie_space_id()
