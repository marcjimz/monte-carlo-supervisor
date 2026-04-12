"""FastAPI entry point for Monte Carlo Supervisor UI.

Serves API routes at /api/* and the built React SPA as static files.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
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
    refresh_task = None
    sync_task = None
    if settings.pghost:
        from server.db import close_pool, init_pool, refresh_token_loop, run_migrations

        try:
            pool = await init_pool(settings)
            await run_migrations(pool)
            logger.info("Lakebase pool initialized and migrations applied")

            refresh_task = asyncio.create_task(refresh_token_loop(settings))

            from server.services.sync_service import periodic_sync

            sync_task = asyncio.create_task(periodic_sync())
        except Exception:
            logger.exception("Failed to initialize Lakebase — DB routes will 500")
    else:
        logger.warning("No PGHOST configured — running without Lakebase")

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
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        from fastapi.responses import FileResponse

        return FileResponse(str(FRONTEND_DIR / "index.html"))
else:
    # Fallback: inline HTML that hits the API directly
    @app.get("/")
    async def fallback_ui():
        return HTMLResponse("""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Monte Carlo Supervisor</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#f8fafc;color:#0f172a}
.container{max-width:960px;margin:0 auto;padding:2rem}.header{background:#1e40af;color:white;padding:1.5rem 2rem;margin-bottom:2rem;border-radius:0.5rem}
h1{font-size:1.5rem;font-weight:600}h2{font-size:1.25rem;margin-bottom:1rem}.card{background:white;border:1px solid #e2e8f0;border-radius:0.5rem;padding:1.5rem;margin-bottom:1rem}
pre{background:#f1f5f9;padding:1rem;border-radius:0.375rem;overflow-x:auto;font-size:0.875rem}
.badge{display:inline-block;padding:0.25rem 0.75rem;border-radius:9999px;font-size:0.75rem;font-weight:600}
.badge-ok{background:#dcfce7;color:#166534}.badge-warn{background:#fef3c7;color:#92400e}
a{color:#1e40af}button{background:#1e40af;color:white;border:none;padding:0.5rem 1rem;border-radius:0.375rem;cursor:pointer;font-size:0.875rem}
button:hover{background:#1e3a8a}#results{margin-top:1rem}</style></head>
<body><div class="container">
<div class="header"><h1>Monte Carlo Supervisor</h1><p style="opacity:0.8;margin-top:0.25rem">API is running. Frontend build pending.</p></div>
<div class="card"><h2>API Status</h2><div id="health">Loading...</div></div>
<div class="card"><h2>Simulation Types</h2><div id="types">Loading...</div></div>
<div class="card"><h2>Quick Links</h2>
<p><a href="/api/health">/api/health</a> · <a href="/api/config/simulation-types">/api/config/simulation-types</a> · <a href="/api/simulations">/api/simulations</a> · <a href="/docs">/docs (Swagger UI)</a></p></div>
</div>
<script>
fetch('/api/health').then(r=>r.json()).then(d=>{
  document.getElementById('health').innerHTML='<span class="badge badge-ok">'+d.status+'</span>';
}).catch(()=>{document.getElementById('health').innerHTML='<span class="badge badge-warn">unreachable</span>';});
fetch('/api/config/simulation-types').then(r=>r.json()).then(d=>{
  const types=Object.entries(d.simulation_types||{});
  document.getElementById('types').innerHTML=types.map(([k,v])=>'<div class="card" style="margin-bottom:0.5rem"><strong>'+v.display_name+'</strong> ('+k+')<br><small>'+v.description+'</small></div>').join('');
}).catch(()=>{document.getElementById('types').innerHTML='<span class="badge badge-warn">Could not load</span>';});
</script></body></html>""")
