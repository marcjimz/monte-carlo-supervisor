"""Simulation service — check/trigger via direct SQL, browse via Lakebase."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from server import db
from server.services.sql_client import execute_query

logger = logging.getLogger(__name__)


async def check_simulation(
    simulation_type: str,
    parameters: dict,
    num_simulations: int = 10000,
    seed: int = 42,
) -> dict:
    """Check for cached simulation results via direct Delta SQL.

    Strategy:
    1. Compute params_hash for exact match (same as submit_to_delta)
    2. Query Delta for a matching run — exact hash first, then fall back
       to most recent COMPLETED run of the same simulation_type
    3. If COMPLETED, fetch results from simulation_results table
    """
    import asyncio

    from server.config import get_settings

    settings = get_settings()
    catalog = settings.uc_catalog
    schema = settings.uc_schema

    params_json = json.dumps(parameters, sort_keys=True)
    payload = f"{simulation_type}|{params_json}|{seed}|{num_simulations}|default"
    params_hash = hashlib.sha256(payload.encode()).hexdigest()

    # First: try exact hash match
    run_sql = f"""
        SELECT run_id, simulation_type, parameters, status, seed, num_simulations
        FROM {catalog}.{schema}.simulation_runs
        WHERE params_hash = '{params_hash}'
          AND status IN ('COMPLETED', 'RUNNING', 'SUBMITTED', 'FAILED')
        ORDER BY created_at DESC
        LIMIT 1
    """
    rows = await asyncio.to_thread(execute_query, run_sql)

    # Fallback: most recent COMPLETED run of this simulation_type
    if not rows:
        fallback_sql = f"""
            SELECT run_id, simulation_type, parameters, status, seed, num_simulations
            FROM {catalog}.{schema}.simulation_runs
            WHERE simulation_type = '{simulation_type}'
              AND status = 'COMPLETED'
            ORDER BY created_at DESC
            LIMIT 1
        """
        rows = await asyncio.to_thread(execute_query, fallback_sql)

    if not rows:
        return {
            "status": "not_found",
            "simulation_type": simulation_type,
            "message": "No matching simulation found. Call trigger_simulation to start one.",
        }

    run = rows[0]
    run_id = run["run_id"]
    run_status = run["status"]

    if run_status == "COMPLETED":
        # Fetch aggregated results
        results_sql = f"""
            SELECT simulation_type, metric_name, group_key, group_value,
                   mean_value, std_value, p05, p10, p25, p50, p75, p90, p95
            FROM {catalog}.{schema}.simulation_results
            WHERE run_id = '{run_id}'
            ORDER BY metric_name, group_value
        """
        result_rows = await asyncio.to_thread(execute_query, results_sql)
        return {
            "status": "completed",
            "run_id": run_id,
            "simulation_type": simulation_type,
            "num_simulations": int(run.get("num_simulations", num_simulations)),
            "seed": int(run.get("seed", seed)),
            "results": result_rows,
        }

    if run_status == "RUNNING":
        return {
            "status": "running",
            "run_id": run_id,
            "simulation_type": simulation_type,
            "message": "Simulation is running. Call check_simulation again to poll.",
        }

    if run_status == "SUBMITTED":
        return {
            "status": "submitted",
            "run_id": run_id,
            "simulation_type": simulation_type,
            "message": "Simulation is queued. Keep polling with check_simulation.",
        }

    # FAILED
    return {
        "status": "failed",
        "run_id": run_id,
        "simulation_type": simulation_type,
        "message": "Simulation failed. Call trigger_simulation to retry.",
    }


async def submit_to_delta(
    simulation_type: str,
    parameters,
    num_simulations: int = 10000,
    seed: int = 42,
) -> dict:
    """Write a SUBMITTED row to Delta simulation_runs table.

    Called by the internal endpoint (from UC function http_request)
    and by trigger_simulation for direct App-side triggers.
    """
    import asyncio

    from server.config import get_settings
    from server.services.sql_client import execute_query

    settings = get_settings()
    catalog = settings.uc_catalog
    schema = settings.uc_schema

    params_json = json.dumps(parameters, sort_keys=True) if isinstance(parameters, dict) else str(parameters)
    run_id = uuid4().hex
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    payload = f"{simulation_type}|{params_json}|{seed}|{num_simulations}|default"
    params_hash = hashlib.sha256(payload.encode()).hexdigest()

    sql = f"""INSERT INTO {catalog}.{schema}.simulation_runs
    (run_id, simulation_type, parameters, params_hash, seed, num_simulations, status, created_at, updated_at)
    VALUES ('{run_id}', '{simulation_type}', '{params_json}', '{params_hash}', {seed}, {num_simulations}, 'SUBMITTED', '{now}', '{now}')"""

    await asyncio.to_thread(execute_query, sql)

    # Also insert Lakebase placeholder for UI
    try:
        await insert_submitted_placeholder(
            simulation_type,
            json.loads(params_json) if isinstance(params_json, str) else params_json,
            num_simulations, seed,
        )
    except Exception:
        logger.warning("Failed to insert Lakebase placeholder", exc_info=True)

    return {
        "status": "submitted",
        "run_id": run_id,
        "simulation_type": simulation_type,
        "message": "Simulation queued. Pipeline will start within ~2 minutes.",
    }


async def trigger_simulation(
    simulation_type: str,
    parameters: dict,
    num_simulations: int = 10000,
    seed: int = 42,
) -> dict:
    """Trigger a simulation by writing to Delta and launching the job."""
    import asyncio

    from server.config import get_settings
    from server.services.sql_client import _get_client

    result = await submit_to_delta(simulation_type, parameters, num_simulations, seed)

    # Explicitly launch the simulation job via SDK
    settings = get_settings()
    if settings.simulation_job_id:
        try:
            client = _get_client(settings)
            job_run = await asyncio.to_thread(
                client.jobs.run_now,
                job_id=int(settings.simulation_job_id),
            )
            result["job_run_id"] = str(job_run.run_id)
            logger.info("Launched simulation job run %s", job_run.run_id)
        except Exception:
            logger.exception("Failed to launch simulation job %s", settings.simulation_job_id)
    else:
        logger.warning("SIMULATION_JOB_ID not set — job not launched")

    return result


async def insert_submitted_placeholder(
    simulation_type: str,
    parameters: dict,
    num_simulations: int = 10000,
    seed: int = 42,
    job_run_id: str = "",
) -> dict:
    """Insert a SUBMITTED placeholder into Lakebase so the UI sees it immediately.

    Returns the placeholder metadata dict matching sync_simulation_runs schema.
    """
    canonical_params = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
    placeholder_run_id = uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    payload = f"{simulation_type}|{canonical_params}|{seed}|{num_simulations}|default"
    params_hash = hashlib.sha256(payload.encode()).hexdigest()

    await db.execute(
        """INSERT INTO sync_simulation_runs
           (run_id, simulation_type, parameters, params_hash, seed,
            num_simulations, status, job_run_id, created_at, updated_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
           ON CONFLICT (run_id) DO NOTHING""",
        placeholder_run_id, simulation_type, canonical_params, params_hash,
        seed, num_simulations, "SUBMITTED",
        str(job_run_id), now, now,
    )

    return {
        "run_id": placeholder_run_id,
        "simulation_type": simulation_type,
        "parameters": canonical_params,
        "params_hash": params_hash,
        "seed": seed,
        "num_simulations": num_simulations,
        "status": "SUBMITTED",
        "job_run_id": str(job_run_id),
        "created_at": now,
        "updated_at": now,
    }


async def list_simulations(
    simulation_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List simulation runs from Lakebase sync table."""
    conditions = []
    args = []
    idx = 1

    if simulation_type:
        conditions.append(f"simulation_type = ${idx}")
        args.append(simulation_type)
        idx += 1

    if status:
        conditions.append(f"status = ${idx}")
        args.append(status)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT run_id, simulation_type, parameters, params_hash,
               seed, num_simulations, status, job_run_id,
               created_at, updated_at
        FROM sync_simulation_runs
        {where}
        ORDER BY created_at DESC
        LIMIT ${idx}
    """
    args.append(limit)
    return await db.fetch_all(query, *args)


async def get_simulation(run_id: str) -> dict | None:
    """Get a single simulation run."""
    return await db.fetch_one(
        "SELECT * FROM sync_simulation_runs WHERE run_id = $1",
        run_id,
    )


async def get_simulation_by_hash(params_hash: str) -> dict | None:
    """Get the most recent non-placeholder simulation by params_hash."""
    return await db.fetch_one(
        """SELECT * FROM sync_simulation_runs
           WHERE params_hash = $1
           ORDER BY CASE WHEN status = 'SUBMITTED' THEN 1 ELSE 0 END, updated_at DESC
           LIMIT 1""",
        params_hash,
    )


async def get_simulation_results(run_id: str) -> list[dict]:
    """Get results for a simulation run."""
    return await db.fetch_all(
        """SELECT run_id, simulation_type, metric_name, group_key, group_value,
                  num_trials, mean_value, std_value, min_value, max_value,
                  p05, p10, p25, p50, p75, p90, p95, created_at
           FROM sync_simulation_results
           WHERE run_id = $1
           ORDER BY metric_name, group_value""",
        run_id,
    )
