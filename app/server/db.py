"""Lakebase (Postgres) async connection pool with OAuth token refresh.

Uses asyncpg for async queries. In Databricks Apps, the password is an
OAuth token obtained from the Databricks SDK, refreshed every 45 minutes.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import asyncpg

from .config import Settings, get_settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


def _get_oauth_token(settings: Settings) -> str:
    """Get Lakebase Postgres credential via the Databricks SDK.

    Uses w.postgres.generate_database_credential() which returns a
    Postgres-specific JWT. Requires databricks-sdk>=0.81.0 and the
    databricks_auth extension + databricks_create_role() in Lakebase.
    """
    from databricks.sdk import WorkspaceClient

    if settings.is_databricks_app:
        w = WorkspaceClient()
    else:
        w = WorkspaceClient(profile=settings.databricks_profile)

    endpoint_path = (
        f"projects/{settings.lakebase_project}"
        f"/branches/{settings.lakebase_branch}"
        f"/endpoints/{settings.lakebase_endpoint}"
    )
    credential = w.postgres.generate_database_credential(endpoint=endpoint_path)
    logger.info("Generated Lakebase credential (expires=%s)", credential.expire_time)
    return credential.token


async def init_pool(settings: Settings | None = None) -> asyncpg.Pool:
    """Create and cache the asyncpg connection pool."""
    global _pool
    if _pool is not None:
        return _pool

    s = settings or get_settings()
    password = _get_oauth_token(s)

    logger.info(
        "Connecting to Lakebase: host=%s port=%s db=%s user=%s",
        s.pghost, s.pgport, s.pgdatabase, s.pguser[:8] + "..." if s.pguser else "unset",
    )

    _pool = await asyncpg.create_pool(
        host=s.pghost,
        port=s.pgport,
        database=s.pgdatabase,
        user=s.pguser,
        password=password,
        min_size=2,
        max_size=10,
        ssl="require",
    )
    return _pool


async def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def get_pool() -> asyncpg.Pool:
    """Get the current pool, initializing if needed."""
    if _pool is None:
        return await init_pool()
    return _pool


async def refresh_token_loop(settings: Settings | None = None):
    """Background task to refresh the OAuth token every 45 minutes.

    Recreates the pool with a fresh token since asyncpg pools
    don't support updating the password on existing connections.
    """
    s = settings or get_settings()
    while True:
        await asyncio.sleep(45 * 60)
        try:
            await close_pool()
            await init_pool(s)
            logger.info("Refreshed Lakebase OAuth token (pool recreated)")
        except Exception:
            logger.exception("Failed to refresh Lakebase OAuth token")


async def run_migrations(pool: asyncpg.Pool | None = None):
    """Execute migration SQL files."""
    p = pool or await get_pool()
    migrations_dir = Path(__file__).parent.parent / "migrations"

    for sql_file in sorted(migrations_dir.glob("*.sql")):
        sql = sql_file.read_text()
        async with p.acquire() as conn:
            await conn.execute(sql)
        logger.info(f"Applied migration: {sql_file.name}")


async def fetch_one(query: str, *args: Any) -> dict | None:
    """Execute a query and return a single row as a dict."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None


async def fetch_all(query: str, *args: Any) -> list[dict]:
    """Execute a query and return all rows as dicts."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *args)
        return [dict(r) for r in rows]


async def execute(query: str, *args: Any) -> str:
    """Execute a query and return the status string."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)
