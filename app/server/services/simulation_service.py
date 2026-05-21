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


def normalize_parameters(simulation_type: str, parameters: dict) -> dict:
    """Merge user-supplied parameters with defaults, strip unknown keys, cast types.

    Ensures that ``{}`` and ``{"growth_rate": 0.02, "cost_inflation": 0.035}``
    produce the exact same dict (and therefore the same hash) for ``encounter_margin``.
    """
    try:
        from mc_supervisor.monte_carlo import config_loader

        defaults = config_loader.get_default_params(simulation_type)
    except (ImportError, ValueError):
        # Config not available — return as-is (e.g. during tests)
        return parameters

    merged: dict = {}
    for key, default_value in defaults.items():
        raw = parameters.get(key, default_value)
        # Cast to the same type as the default
        if isinstance(default_value, bool):
            merged[key] = bool(raw)
        elif isinstance(default_value, int):
            merged[key] = int(raw)
        elif isinstance(default_value, float):
            merged[key] = float(raw)
        else:
            merged[key] = raw
    return merged


def compute_params_hash(
    simulation_type: str,
    parameters: dict,
    num_simulations: int = 10000,
    seed: int = 42,
) -> str:
    """Compute the deterministic params_hash for a simulation config."""
    params_json = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
    payload = f"{simulation_type}|{params_json}|{seed}|{num_simulations}|default"
    return hashlib.sha256(payload.encode()).hexdigest()


async def check_simulation(
    simulation_type: str,
    parameters: dict,
    num_simulations: int = 10000,
    seed: int = 42,
) -> dict:
    """Check for cached simulation results via direct Delta SQL.

    Strategy:
    1. Compute params_hash for exact match (same as submit_to_delta)
    2. Query Delta for a matching run by exact hash
    3. If COMPLETED, fetch results from simulation_results table
    """
    import asyncio

    from server.config import get_settings

    parameters = normalize_parameters(simulation_type, parameters)

    settings = get_settings()
    catalog = settings.uc_catalog
    schema = settings.uc_schema

    params_hash = compute_params_hash(simulation_type, parameters, num_simulations, seed)

    # Exact hash match — only look at COMPLETED or fresh RUNNING runs.
    # SUBMITTED/FAILED are ignored so caller can re-trigger.
    # RUNNING rows older than 30 min are treated as stale (job likely failed).
    run_sql = f"""
        SELECT run_id, simulation_type, parameters, status, seed, num_simulations
        FROM {catalog}.{schema}.simulation_runs
        WHERE params_hash = '{params_hash}'
          AND (
              status = 'COMPLETED'
              OR (status = 'RUNNING'
                  AND updated_at >= (current_timestamp() - INTERVAL 30 MINUTES))
          )
        ORDER BY
          CASE status WHEN 'COMPLETED' THEN 0 ELSE 1 END,
          created_at DESC
        LIMIT 1
    """
    rows = await asyncio.to_thread(execute_query, run_sql)

    if not rows:
        return {
            "status": "not_found",
            "simulation_type": simulation_type,
            "message": "No matching simulation found.",
        }

    run = rows[0]
    run_id = run["run_id"]
    run_status = run["status"]

    if run_status == "COMPLETED":
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

    # RUNNING
    return {
        "status": "running",
        "run_id": run_id,
        "simulation_type": simulation_type,
        "message": "Simulation is currently running.",
    }


async def check_simulations_batch(
    cells: list[dict],
) -> dict[str, dict]:
    """Batch-check multiple simulation hashes in a single SQL query.

    Args:
        cells: List of dicts with keys: params_hash, simulation_type, num_simulations, seed

    Returns:
        Dict keyed by params_hash with check results (same shape as check_simulation).
    """
    import asyncio

    from server.config import get_settings

    if not cells:
        return {}

    settings = get_settings()
    catalog = settings.uc_catalog
    schema = settings.uc_schema

    hashes = [c["params_hash"] for c in cells]
    hash_list = ", ".join(f"'{h}'" for h in hashes)

    # Single query for all hashes — COMPLETED or fresh RUNNING (same staleness guard as check_simulation)
    run_sql = f"""
        WITH ranked AS (
            SELECT run_id, params_hash, simulation_type, parameters, status,
                   seed, num_simulations,
                   ROW_NUMBER() OVER (
                       PARTITION BY params_hash
                       ORDER BY
                           CASE status WHEN 'COMPLETED' THEN 0 ELSE 1 END,
                           created_at DESC
                   ) AS rn
            FROM {catalog}.{schema}.simulation_runs
            WHERE params_hash IN ({hash_list})
              AND (
                  status = 'COMPLETED'
                  OR (status = 'RUNNING'
                      AND updated_at >= (current_timestamp() - INTERVAL 30 MINUTES))
              )
        )
        SELECT run_id, params_hash, simulation_type, parameters, status,
               seed, num_simulations
        FROM ranked WHERE rn = 1
    """
    rows = await asyncio.to_thread(execute_query, run_sql)

    # Index by params_hash
    run_by_hash: dict[str, dict] = {}
    for row in rows:
        run_by_hash[row["params_hash"]] = row

    # Collect completed run_ids for batch results fetch
    completed_run_ids = [
        row["run_id"] for row in rows if row["status"] == "COMPLETED"
    ]

    # Single query for ALL completed results
    results_by_run: dict[str, list[dict]] = {}
    if completed_run_ids:
        run_id_list = ", ".join(f"'{rid}'" for rid in completed_run_ids)
        results_sql = f"""
            SELECT run_id, simulation_type, metric_name, group_key, group_value,
                   mean_value, std_value, p05, p10, p25, p50, p75, p90, p95
            FROM {catalog}.{schema}.simulation_results
            WHERE run_id IN ({run_id_list})
            ORDER BY run_id, metric_name, group_value
        """
        result_rows = await asyncio.to_thread(execute_query, results_sql)
        for r in result_rows:
            results_by_run.setdefault(r["run_id"], []).append(r)

    # Build response keyed by params_hash
    output: dict[str, dict] = {}
    cell_lookup = {c["params_hash"]: c for c in cells}

    for h in hashes:
        cell_info = cell_lookup[h]
        sim_type = cell_info["simulation_type"]

        if h not in run_by_hash:
            output[h] = {
                "status": "not_found",
                "simulation_type": sim_type,
                "message": "No matching simulation found.",
            }
            continue

        run = run_by_hash[h]
        run_id = run["run_id"]
        run_status = run["status"]

        if run_status == "COMPLETED":
            output[h] = {
                "status": "completed",
                "run_id": run_id,
                "simulation_type": sim_type,
                "num_simulations": int(run.get("num_simulations", 10000)),
                "seed": int(run.get("seed", 42)),
                "results": results_by_run.get(run_id, []),
            }
        else:  # RUNNING
            output[h] = {
                "status": "running",
                "run_id": run_id,
                "simulation_type": sim_type,
                "message": "Simulation is currently running.",
            }

    return output


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

    if isinstance(parameters, dict):
        parameters = normalize_parameters(simulation_type, parameters)

    settings = get_settings()
    catalog = settings.uc_catalog
    schema = settings.uc_schema

    # Canonical compact JSON — must match results.py:compute_cache_key()
    params_json = json.dumps(parameters, sort_keys=True, separators=(",", ":")) if isinstance(parameters, dict) else str(parameters)
    run_id = uuid4().hex
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    params_hash = compute_params_hash(simulation_type, parameters if isinstance(parameters, dict) else json.loads(params_json), num_simulations, seed)

    sql = f"""INSERT INTO {catalog}.{schema}.simulation_runs
    (run_id, simulation_type, parameters, params_hash, seed, num_simulations, status, created_at, updated_at)
    VALUES ('{run_id}', '{simulation_type}', '{params_json}', '{params_hash}', {seed}, {num_simulations}, 'SUBMITTED', '{now}', '{now}')"""

    # Retry on Delta concurrent append conflicts with exponential backoff
    max_retries = 10
    for attempt in range(max_retries):
        try:
            await asyncio.to_thread(execute_query, sql)
            break
        except Exception as e:
            if "DELTA_CONCURRENT_APPEND" in str(e) and attempt < max_retries - 1:
                delay = min(2 ** attempt, 30)  # 1, 2, 4, 8, 16, 30, 30...
                logger.warning("Delta concurrent append conflict (attempt %d/%d), retrying in %ds...", attempt + 1, max_retries, delay)
                await asyncio.sleep(delay)
            else:
                raise

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
    """Trigger a simulation by writing to Delta and launching the job.

    Cache guard: if a COMPLETED or RUNNING run exists, return it.
    SUBMITTED rows are ignored (may be stale) — a new job is always launched.
    """
    cached = await check_simulation(simulation_type, parameters, num_simulations, seed)
    cached_status = cached.get("status")
    if cached_status == "completed":
        logger.info("Cache guard: returning existing completed run %s", cached.get("run_id"))
        cached["message"] = "Simulation already completed (cache hit)."
        return cached
    if cached_status == "running":
        logger.info("Cache guard: run %s already running — not re-triggering", cached.get("run_id"))
        return cached

    import asyncio

    from server.config import get_settings
    from server.services.sql_client import _get_client

    # Normalize before submit so we can pass the same values to the job
    normalized = normalize_parameters(simulation_type, parameters)
    result = await submit_to_delta(simulation_type, normalized, num_simulations, seed)

    # Explicitly launch the simulation job via SDK
    settings = get_settings()
    if settings.simulation_job_id:
        try:
            client = _get_client(settings)
            params_json = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
            job_run = await asyncio.to_thread(
                client.jobs.run_now,
                job_id=int(settings.simulation_job_id),
                job_parameters={
                    "simulation_type": simulation_type,
                    "parameters": params_json,
                    "num_simulations": str(num_simulations),
                    "seed": str(seed),
                },
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
    params_hash = compute_params_hash(simulation_type, parameters, num_simulations, seed)

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
