"""Simulation service — check/trigger via UC functions, browse via Lakebase."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from server import db
from server.services.sql_client import execute_uc_function

logger = logging.getLogger(__name__)


async def check_simulation(
    simulation_type: str,
    parameters: dict,
    num_simulations: int = 10000,
    seed: int = 42,
) -> dict:
    """Call check_simulation UC function."""
    import asyncio

    result_str = await asyncio.to_thread(
        execute_uc_function,
        "check_simulation",
        {
            "p_simulation_type": simulation_type,
            "p_parameters": json.dumps(parameters, sort_keys=True),
            "p_num_simulations": num_simulations,
            "p_seed": seed,
        },
    )
    return json.loads(result_str)


async def trigger_simulation(
    simulation_type: str,
    parameters: dict,
    num_simulations: int = 10000,
    seed: int = 42,
) -> dict:
    """Call trigger_simulation UC function."""
    import asyncio

    result_str = await asyncio.to_thread(
        execute_uc_function,
        "trigger_simulation",
        {
            "p_simulation_type": simulation_type,
            "p_parameters": json.dumps(parameters, sort_keys=True),
            "p_num_simulations": num_simulations,
            "p_seed": seed,
        },
    )
    result = json.loads(result_str)

    # Extract job_run_id from nested job_response (Jobs API returns {"run_id": N})
    job_resp = result.get("job_response")
    if isinstance(job_resp, str):
        try:
            job_resp = json.loads(job_resp)
        except (json.JSONDecodeError, TypeError):
            job_resp = None
    if isinstance(job_resp, dict) and "run_id" in job_resp:
        result["job_run_id"] = job_resp["run_id"]

    # Insert a SUBMITTED placeholder into Lakebase so the UI sees it immediately
    try:
        placeholder = await insert_submitted_placeholder(
            simulation_type, parameters, num_simulations, seed,
            job_run_id=str(result.get("job_run_id", "")),
        )
        if placeholder:
            result["run_id"] = placeholder["run_id"]
    except Exception:
        logger.warning("Failed to insert SUBMITTED placeholder", exc_info=True)

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
