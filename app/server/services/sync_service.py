"""Delta to Lakebase sync service.

Periodically syncs simulation_runs, simulation_results, and distribution_specs
from Delta tables to Lakebase for fast UI reads.
"""

from __future__ import annotations

import asyncio
import json
import logging

from server import db
from server.services.sql_client import execute_query
from server.config import get_settings

logger = logging.getLogger(__name__)

SYNC_INTERVAL_SECONDS = 5 * 60  # 5 minutes


async def sync_simulation_runs():
    """Incremental sync of simulation_runs by updated_at."""
    settings = get_settings()
    catalog = settings.uc_catalog
    schema = settings.uc_schema

    # Get last sync time
    meta = await db.fetch_one(
        "SELECT last_synced_at FROM sync_metadata WHERE table_name = 'simulation_runs'"
    )

    table = f"{catalog}.{schema}.simulation_runs"

    if meta:
        # Incremental: only rows updated after last sync
        sql = f"SELECT * FROM {table} WHERE updated_at > '{meta['last_synced_at'].isoformat()}' ORDER BY updated_at"
    else:
        sql = f"SELECT * FROM {table} ORDER BY updated_at"

    try:
        rows = execute_query(sql)
    except Exception as e:
        logger.warning(f"Failed to sync simulation_runs: {e}")
        return 0

    count = 0
    for row in rows:
        await db.execute(
            """INSERT INTO sync_simulation_runs
               (run_id, simulation_type, parameters, params_hash, seed,
                num_simulations, status, job_run_id, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
               ON CONFLICT (run_id) DO UPDATE SET
                 status = EXCLUDED.status,
                 job_run_id = EXCLUDED.job_run_id,
                 updated_at = EXCLUDED.updated_at,
                 synced_at = NOW()""",
            row.get("run_id"), row.get("simulation_type"),
            row.get("parameters"), row.get("params_hash"),
            int(row.get("seed", 0)), int(row.get("num_simulations", 0)),
            row.get("status"), row.get("job_run_id"),
            row.get("created_at"), row.get("updated_at"),
        )
        count += 1

    # Update sync metadata
    await db.execute(
        """INSERT INTO sync_metadata (table_name, last_synced_at)
           VALUES ('simulation_runs', NOW())
           ON CONFLICT (table_name) DO UPDATE SET last_synced_at = NOW()"""
    )

    logger.info(f"Synced {count} simulation_runs")
    return count


async def sync_simulation_results():
    """Sync results for newly completed runs."""
    settings = get_settings()
    catalog = settings.uc_catalog
    schema = settings.uc_schema

    # Find completed runs that we haven't synced results for
    new_runs = await db.fetch_all(
        """SELECT r.run_id FROM sync_simulation_runs r
           WHERE r.status = 'COMPLETED'
             AND NOT EXISTS (
               SELECT 1 FROM sync_simulation_results sr WHERE sr.run_id = r.run_id
             )"""
    )

    count = 0
    for run in new_runs:
        run_id = run["run_id"]
        table = f"{catalog}.{schema}.simulation_results"
        sql = f"SELECT * FROM {table} WHERE run_id = '{run_id}'"

        try:
            rows = execute_query(sql)
        except Exception as e:
            logger.warning(f"Failed to sync results for run {run_id}: {e}")
            continue

        for row in rows:
            await db.execute(
                """INSERT INTO sync_simulation_results
                   (run_id, simulation_type, metric_name, group_key, group_value,
                    num_trials, mean_value, std_value, min_value, max_value,
                    p05, p10, p25, p50, p75, p90, p95, created_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)""",
                row.get("run_id"), row.get("simulation_type"),
                row.get("metric_name"), row.get("group_key"),
                row.get("group_value"), int(row.get("num_trials", 0)),
                _to_float(row.get("mean_value")), _to_float(row.get("std_value")),
                _to_float(row.get("min_value")), _to_float(row.get("max_value")),
                _to_float(row.get("p05")), _to_float(row.get("p10")),
                _to_float(row.get("p25")), _to_float(row.get("p50")),
                _to_float(row.get("p75")), _to_float(row.get("p90")),
                _to_float(row.get("p95")), row.get("created_at"),
            )
            count += 1

    await db.execute(
        """INSERT INTO sync_metadata (table_name, last_synced_at)
           VALUES ('simulation_results', NOW())
           ON CONFLICT (table_name) DO UPDATE SET last_synced_at = NOW()"""
    )

    logger.info(f"Synced {count} simulation_results")
    return count


async def sync_distribution_specs():
    """Full replace sync of distribution_specs (small table)."""
    settings = get_settings()
    catalog = settings.uc_catalog
    schema = settings.uc_schema

    table = f"{catalog}.{schema}.distribution_specs"
    sql = f"SELECT * FROM {table}"

    try:
        rows = execute_query(sql)
    except Exception as e:
        logger.warning(f"Failed to sync distribution_specs: {e}")
        return 0

    # Full replace
    await db.execute("DELETE FROM sync_distribution_specs")

    count = 0
    for row in rows:
        await db.execute(
            """INSERT INTO sync_distribution_specs
               (simulation_type, distribution_name, version, spec, fit_metadata, created_at)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            row.get("simulation_type"), row.get("distribution_name"),
            int(row.get("version", 0)), row.get("spec"),
            row.get("fit_metadata"), row.get("created_at"),
        )
        count += 1

    await db.execute(
        """INSERT INTO sync_metadata (table_name, last_synced_at)
           VALUES ('distribution_specs', NOW())
           ON CONFLICT (table_name) DO UPDATE SET last_synced_at = NOW()"""
    )

    logger.info(f"Synced {count} distribution_specs")
    return count


async def run_full_sync() -> dict:
    """Run all sync operations."""
    runs = await sync_simulation_runs()
    results = await sync_simulation_results()
    specs = await sync_distribution_specs()
    return {
        "simulation_runs": runs,
        "simulation_results": results,
        "distribution_specs": specs,
    }


async def get_sync_status() -> list[dict]:
    """Get last sync times."""
    return await db.fetch_all(
        "SELECT table_name, last_synced_at FROM sync_metadata ORDER BY table_name"
    )


async def periodic_sync():
    """Background task: run sync every 5 minutes."""
    while True:
        try:
            await run_full_sync()
        except Exception:
            logger.exception("Periodic sync failed")
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)


def _to_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
