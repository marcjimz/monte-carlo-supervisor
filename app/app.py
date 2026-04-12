"""FastAPI entry point for Monte Carlo Supervisor UI.

Serves API routes at /api/* and the built React SPA as static files.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from server.config import get_settings
from server.routes import api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    settings = get_settings()

    # Initialize Lakebase pool + run migrations
    if settings.pghost:
        from server.db import close_pool, init_pool, refresh_token_loop, run_migrations

        pool = await init_pool(settings)
        await run_migrations(pool)
        logger.info("Lakebase pool initialized and migrations applied")

        # Start token refresh background task
        refresh_task = asyncio.create_task(refresh_token_loop(settings))

        # Start periodic Delta sync
        from server.services.sync_service import periodic_sync

        sync_task = asyncio.create_task(periodic_sync())
    else:
        logger.warning("No PGHOST configured — running without Lakebase")
        refresh_task = None
        sync_task = None

    yield

    # Shutdown
    if refresh_task:
        refresh_task.cancel()
    if sync_task:
        sync_task.cancel()
    if settings.pghost:
        await close_pool()
        logger.info("Lakebase pool closed")


app = FastAPI(
    title="Monte Carlo Supervisor",
    version="0.1.0",
    lifespan=lifespan,
)

# API routes
app.include_router(api_router)

# Serve React SPA static files (only if built)
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")
