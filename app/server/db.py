"""Lakebase (Postgres) async connection pool with OAuth token refresh.

Uses asyncpg for async queries. In Databricks Apps, the password is an
OAuth token obtained from the Databricks SDK, refreshed every 45 minutes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import asyncpg

from .config import Settings, get_settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


def _get_workspace_client(settings: Settings):
    """Get a WorkspaceClient for the current environment."""
    from databricks.sdk import WorkspaceClient

    if settings.is_databricks_app:
        return WorkspaceClient()
    return WorkspaceClient(profile=settings.databricks_profile)


def _get_oauth_token(settings: Settings) -> str:
    """Get Lakebase Postgres credential via the Databricks SDK.

    Uses w.postgres.generate_database_credential() which returns a
    Postgres-specific JWT. Requires databricks-sdk>=0.81.0 and the
    databricks_auth extension + databricks_create_role() in Lakebase.
    """
    w = _get_workspace_client(settings)

    endpoint_path = (
        f"projects/{settings.lakebase_project}"
        f"/branches/{settings.lakebase_branch}"
        f"/endpoints/{settings.lakebase_endpoint}"
    )
    credential = w.postgres.generate_database_credential(endpoint=endpoint_path)
    logger.info("Generated Lakebase credential (expires=%s)", credential.expire_time)
    return credential.token


def _discover_pg_host(settings: Settings) -> str:
    """Discover Lakebase endpoint host via the REST API.

    Uses the WorkspaceClient to look up the Postgres endpoint host
    from the Lakebase project/branch/endpoint settings.
    """
    if settings.pghost:
        return settings.pghost

    w = _get_workspace_client(settings)
    endpoint_path = (
        f"projects/{settings.lakebase_project}"
        f"/branches/{settings.lakebase_branch}"
        f"/endpoints/{settings.lakebase_endpoint}"
    )

    resp = w.api_client.do(
        "GET", f"/api/2.0/postgres/{endpoint_path}"
    )
    host = resp.get("status", {}).get("hosts", {}).get("host", "")
    if not host:
        raise RuntimeError(
            f"Could not discover Lakebase host from endpoint {endpoint_path}. "
            "Response: " + str(resp)
        )
    logger.info("Discovered Lakebase host: %s", host)
    return host


def _poll_operation(w, resp, label: str = "operation") -> None:
    """Poll a Lakebase async operation until done (max ~100s)."""
    op_name = resp.get("name", "") if isinstance(resp, dict) else ""
    if not op_name:
        return
    for _ in range(20):
        time.sleep(5)
        try:
            check = w.api_client.do("GET", f"/api/2.0/postgres/{op_name}")
            if check.get("done"):
                logger.info("Lakebase %s completed", label)
                return
        except Exception:
            logger.warning("Error polling %s", label, exc_info=True)
    logger.warning("Lakebase %s still in progress after 100s", label)


def _ensure_postgres_role(settings: Settings) -> None:
    """Create Postgres role for the app SP with CREATEDB privilege.

    Posts to the Lakebase roles API to create a SERVICE_PRINCIPAL role
    matching the app's PGUSER (client ID) with createdb=true so the app
    can CREATE DATABASE on first boot.

    If the role already exists, PATCHes it to ensure CREATEDB is enabled.
    """
    w = _get_workspace_client(settings)
    branch_path = (
        f"projects/{settings.lakebase_project}"
        f"/branches/{settings.lakebase_branch}"
    )
    role_attributes = {
        "createdb": True,
        "createrole": False,
        "bypassrls": False,
    }

    try:
        resp = w.api_client.do(
            "POST",
            f"/api/2.0/postgres/{branch_path}/roles",
            body={
                "spec": {
                    "identity_type": "SERVICE_PRINCIPAL",
                    "postgres_role": settings.pguser,
                    "attributes": role_attributes,
                }
            },
        )
    except Exception as e:
        err_str = str(e).lower()
        if "409" in err_str or "already_exists" in err_str or "already exists" in err_str:
            logger.info("Postgres role already exists for %s — ensuring CREATEDB", settings.pguser)
            _ensure_role_createdb(w, settings, branch_path, role_attributes)
            return
        raise

    _poll_operation(w, resp, label=f"role creation for {settings.pguser}")
    logger.info("Postgres role created with CREATEDB for %s", settings.pguser)


def _ensure_role_createdb(w, settings: Settings, branch_path: str, attributes: dict) -> None:
    """Ensure an existing Postgres role has the CREATEDB attribute."""
    try:
        resp = w.api_client.do(
            "GET", f"/api/2.0/postgres/{branch_path}/roles"
        )
    except Exception:
        logger.warning("Failed to list roles for CREATEDB check", exc_info=True)
        return

    role_name = None
    for role in resp.get("roles", []):
        # GET response returns current state under "status", not "spec"
        status = role.get("status", {})
        if status.get("postgres_role") == settings.pguser:
            existing_attrs = status.get("attributes", {})
            if existing_attrs.get("createdb"):
                logger.info("Role %s already has CREATEDB", settings.pguser)
                return
            role_name = role.get("name", "")
            break

    if not role_name:
        logger.warning("Could not find role for %s to update CREATEDB", settings.pguser)
        return

    try:
        patch_resp = w.api_client.do(
            "PATCH",
            f"/api/2.0/postgres/{role_name}",
            query={"update_mask": "spec.attributes"},
            body={"spec": {"attributes": attributes}},
        )
        _poll_operation(w, patch_resp, label=f"CREATEDB update for {settings.pguser}")
        logger.info("Updated role %s with CREATEDB", settings.pguser)
    except Exception:
        logger.warning("Failed to PATCH CREATEDB on role %s", settings.pguser, exc_info=True)


async def _create_database_if_needed(settings: Settings) -> None:
    """Create the application database if it doesn't exist.

    Connects to `databricks_postgres` (the default Lakebase database) to
    CREATE DATABASE, then connects to the new database to set up schema
    privileges. Requires the SP role to have CREATEDB attribute.
    """
    password = _get_oauth_token(settings)

    # Connect to default database to check/create the app database
    conn = await asyncpg.connect(
        host=settings.pghost,
        port=settings.pgport,
        database="databricks_postgres",
        user=settings.pguser,
        password=password,
        ssl="require",
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            settings.pgdatabase,
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{settings.pgdatabase}"')
            logger.info("Created database '%s'", settings.pgdatabase)
        else:
            logger.info("Database '%s' already exists", settings.pgdatabase)
    finally:
        await conn.close()

    # Connect to the app database to ensure schema privileges
    conn = await asyncpg.connect(
        host=settings.pghost,
        port=settings.pgport,
        database=settings.pgdatabase,
        user=settings.pguser,
        password=password,
        ssl="require",
    )
    try:
        await conn.execute(
            f'GRANT ALL ON SCHEMA public TO "{settings.pguser}"'
        )
        await conn.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
            f'GRANT ALL ON TABLES TO "{settings.pguser}"'
        )
        logger.info("Schema privileges set in '%s'", settings.pgdatabase)
    finally:
        await conn.close()


async def _ensure_database(settings: Settings) -> None:
    """Full Lakebase self-provisioning: discover host, create role, create DB.

    Only runs when inside a Databricks App or PGHOST is already set.
    Skips gracefully in pure local dev. After this function completes,
    init_pool() can connect to the application database.
    """
    if not (settings.is_databricks_app or settings.pghost):
        logger.info("Not a Databricks App and no PGHOST — skipping Lakebase provisioning")
        return

    # 1. Discover PG host
    settings.pghost = _discover_pg_host(settings)

    # 2. Ensure Postgres role with CREATEDB
    _ensure_postgres_role(settings)

    # 3. Create database if it doesn't exist
    await _create_database_if_needed(settings)


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
