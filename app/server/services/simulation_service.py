"""Simulation service — check/trigger via UC functions, browse via Lakebase."""

from __future__ import annotations

import json
import logging

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
    result_str = execute_uc_function(
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
    result_str = execute_uc_function(
        "trigger_simulation",
        {
            "p_simulation_type": simulation_type,
            "p_parameters": json.dumps(parameters, sort_keys=True),
            "p_num_simulations": num_simulations,
            "p_seed": seed,
        },
    )
    return json.loads(result_str)


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
