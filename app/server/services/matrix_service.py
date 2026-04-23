"""Matrix service — create, execute, and poll parameter sweep matrices."""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from server import db
from server.services import analysis_service, simulation_service

logger = logging.getLogger(__name__)

MAX_CONCURRENT_TRIGGERS = 10


async def create_matrix(
    analysis_id: UUID,
    name: str,
    simulation_type: str,
    row_parameter: str,
    row_values: list[float],
    col_parameter: str,
    col_values: list[float],
    base_parameters: dict,
    output_metric: str,
    output_group_key: str | None,
    output_group_value: str | None,
    num_simulations: int,
    seed: int,
) -> dict:
    """Create a matrix with all its cells."""
    matrix = await db.fetch_one(
        """INSERT INTO analysis_matrices
           (analysis_id, name, simulation_type, row_parameter, row_values,
            col_parameter, col_values, base_parameters, output_metric,
            output_group_key, output_group_value, num_simulations, seed)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
           RETURNING *""",
        analysis_id, name, simulation_type, row_parameter,
        json.dumps(row_values), col_parameter, json.dumps(col_values),
        json.dumps(base_parameters), output_metric,
        output_group_key, output_group_value, num_simulations, seed,
    )

    # Create cells for every row/col combination
    for rv in row_values:
        for cv in col_values:
            await db.execute(
                """INSERT INTO matrix_cells (matrix_id, row_value, col_value)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (matrix_id, row_value, col_value) DO NOTHING""",
                matrix["id"], rv, cv,
            )

    return matrix


async def get_matrix(matrix_id: UUID) -> dict | None:
    """Get a matrix with all its cells."""
    matrix = await db.fetch_one(
        "SELECT * FROM analysis_matrices WHERE id = $1",
        matrix_id,
    )
    if not matrix:
        return None

    cells = await db.fetch_all(
        "SELECT * FROM matrix_cells WHERE matrix_id = $1 ORDER BY row_value, col_value",
        matrix_id,
    )
    # Parse JSONB fields
    result = dict(matrix)
    result["row_values"] = json.loads(result["row_values"]) if isinstance(result["row_values"], str) else result["row_values"]
    result["col_values"] = json.loads(result["col_values"]) if isinstance(result["col_values"], str) else result["col_values"]
    result["base_parameters"] = json.loads(result["base_parameters"]) if isinstance(result["base_parameters"], str) else result["base_parameters"]
    result["cells"] = [dict(c) for c in cells]
    return result


async def update_matrix(matrix_id: UUID, name: str | None, description: str | None) -> dict | None:
    """Update matrix name and/or description."""
    fields = []
    args = []
    idx = 1

    if name is not None:
        fields.append(f"name = ${idx}")
        args.append(name)
        idx += 1

    if description is not None:
        fields.append(f"description = ${idx}")
        args.append(description)
        idx += 1

    if not fields:
        return await get_matrix(matrix_id)

    fields.append("updated_at = NOW()")
    args.append(matrix_id)

    await db.fetch_one(
        f"UPDATE analysis_matrices SET {', '.join(fields)} WHERE id = ${idx} RETURNING *",
        *args,
    )
    return await get_matrix(matrix_id)


async def delete_matrix(matrix_id: UUID) -> bool:
    """Delete a matrix and cascade to cells."""
    result = await db.execute(
        "DELETE FROM analysis_matrices WHERE id = $1",
        matrix_id,
    )
    return result != "DELETE 0"


async def list_matrices(analysis_id: UUID) -> list[dict]:
    """List matrices for an analysis."""
    matrices = await db.fetch_all(
        "SELECT * FROM analysis_matrices WHERE analysis_id = $1 ORDER BY created_at DESC",
        analysis_id,
    )
    result = []
    for m in matrices:
        m = dict(m)
        m["row_values"] = json.loads(m["row_values"]) if isinstance(m["row_values"], str) else m["row_values"]
        m["col_values"] = json.loads(m["col_values"]) if isinstance(m["col_values"], str) else m["col_values"]
        m["base_parameters"] = json.loads(m["base_parameters"]) if isinstance(m["base_parameters"], str) else m["base_parameters"]
        result.append(m)
    return result


async def _build_cell_params(matrix: dict, row_value: float, col_value: float) -> dict:
    """Build the full parameters dict for a matrix cell."""
    params = dict(matrix["base_parameters"]) if isinstance(matrix["base_parameters"], dict) else json.loads(matrix["base_parameters"])
    params[matrix["row_parameter"]] = row_value
    params[matrix["col_parameter"]] = col_value
    return params


async def _link_run_to_analysis(matrix: dict, run_id: str | None) -> None:
    """Link a simulation run_id to the matrix's parent analysis (idempotent)."""
    if not run_id:
        return
    try:
        await analysis_service.link_simulation(
            matrix["analysis_id"], run_id, "system:matrix",
        )
    except Exception:
        logger.debug("Could not link run %s to analysis (may already exist)", run_id)


async def _cleanup_stale_placeholder(old_run_id: str | None, new_run_id: str | None, matrix: dict) -> None:
    """Remove stale placeholder row and analysis link when the real run_id arrives."""
    if not old_run_id or not new_run_id or old_run_id == new_run_id:
        return
    try:
        await db.execute(
            "DELETE FROM sync_simulation_runs WHERE run_id = $1 AND status = 'SUBMITTED'",
            old_run_id,
        )
        await db.execute(
            "DELETE FROM analysis_simulations WHERE analysis_id = $1 AND run_id = $2",
            matrix["analysis_id"], old_run_id,
        )
    except Exception:
        logger.debug("Placeholder cleanup for %s failed (non-critical)", old_run_id)


async def _process_cell(matrix: dict, cell: dict) -> dict:
    """Check or trigger a single cell simulation."""
    params = await _build_cell_params(matrix, cell["row_value"], cell["col_value"])
    old_run_id = cell.get("run_id")

    # First check if simulation exists (queries Delta — source of truth)
    result = await simulation_service.check_simulation(
        matrix["simulation_type"], params, matrix["num_simulations"], matrix["seed"],
    )

    status = result.get("status", "not_found")
    logger.info(
        "Matrix cell %s: check_simulation(%s, %s) → status=%s, results_count=%d",
        cell["id"], matrix["simulation_type"], json.dumps(params, sort_keys=True)[:120],
        status, len(result.get("results", [])),
    )

    if status == "completed":
        run_id = result.get("run_id")
        # Extract the target metric from results
        mean_val, p05_val, p50_val, p95_val = _extract_metric(
            result.get("results", []),
            matrix["output_metric"],
            matrix.get("output_group_key"),
            matrix.get("output_group_value"),
        )
        logger.info(
            "Matrix cell %s: extracted metric=%s → mean=%s, p05=%s, p50=%s, p95=%s",
            cell["id"], matrix["output_metric"], mean_val, p05_val, p50_val, p95_val,
        )

        # Guard: if check_simulation says "completed" but results are empty,
        # keep cell as 'running' so polling retries later.
        if mean_val is None and p05_val is None and p50_val is None and p95_val is None:
            logger.warning(
                "Cell %s: status=completed but no metrics extracted (results_count=%d). "
                "Keeping as 'running' for retry.",
                cell["id"], len(result.get("results", [])),
            )
            await db.execute(
                "UPDATE matrix_cells SET status = 'running', run_id = $1, updated_at = NOW() WHERE id = $2",
                run_id, cell["id"],
            )
            await _link_run_to_analysis(matrix, run_id)
            return {"status": "running", "cell_id": str(cell["id"])}

        await db.execute(
            """UPDATE matrix_cells
               SET status = 'completed', run_id = $1,
                   result_mean = $2, result_p05 = $3, result_p50 = $4, result_p95 = $5,
                   updated_at = NOW()
               WHERE id = $6""",
            run_id, mean_val, p05_val, p50_val, p95_val, cell["id"],
        )
        await _link_run_to_analysis(matrix, run_id)
        await _cleanup_stale_placeholder(old_run_id, run_id, matrix)
        return {"status": "completed", "cell_id": str(cell["id"])}

    elif status in ("running", "submitted"):
        run_id = result.get("run_id")
        await db.execute(
            "UPDATE matrix_cells SET status = 'running', run_id = $1, updated_at = NOW() WHERE id = $2",
            run_id, cell["id"],
        )
        await _link_run_to_analysis(matrix, run_id)
        await _cleanup_stale_placeholder(old_run_id, run_id, matrix)
        return {"status": "running", "cell_id": str(cell["id"])}

    elif status == "not_found":
        # Trigger a new simulation (writes to Delta + launches job)
        await simulation_service.trigger_simulation(
            matrix["simulation_type"], params, matrix["num_simulations"], matrix["seed"],
        )
        await db.execute(
            "UPDATE matrix_cells SET status = 'running', updated_at = NOW() WHERE id = $1",
            cell["id"],
        )
        return {"status": "triggered", "cell_id": str(cell["id"])}

    else:
        await db.execute(
            "UPDATE matrix_cells SET status = 'failed', updated_at = NOW() WHERE id = $1",
            cell["id"],
        )
        return {"status": "failed", "cell_id": str(cell["id"])}


def _extract_metric(
    results: list[dict],
    metric_name: str,
    group_key: str | None,
    group_value: str | None,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Extract mean, p05, p50, p95 for a specific metric from results."""
    if not results:
        logger.warning("_extract_metric: empty results list for metric=%s", metric_name)
        return None, None, None, None

    # Log available metrics for debugging
    available = [(r.get("metric_name"), r.get("group_key"), r.get("group_value")) for r in results[:10]]
    logger.debug(
        "_extract_metric: looking for metric=%s, group_key=%s, group_value=%s. Available: %s",
        metric_name, group_key, group_value, available,
    )

    for r in results:
        if r.get("metric_name") != metric_name:
            continue
        if group_key and group_value:
            if r.get("group_key") != group_key or str(r.get("group_value")) != str(group_value):
                continue
        mean_val = _to_float(r.get("mean_value"))
        p05_val = _to_float(r.get("p05"))
        p50_val = _to_float(r.get("p50"))
        p95_val = _to_float(r.get("p95"))
        return mean_val, p05_val, p50_val, p95_val

    # If group filter didn't match, try without filter (take first matching metric)
    for r in results:
        if r.get("metric_name") == metric_name:
            return (
                _to_float(r.get("mean_value")),
                _to_float(r.get("p05")),
                _to_float(r.get("p50")),
                _to_float(r.get("p95")),
            )

    logger.warning(
        "_extract_metric: no match for metric=%s among %d results. Metric names found: %s",
        metric_name, len(results), list(set(r.get("metric_name") for r in results)),
    )
    return None, None, None, None


def _to_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


async def run_matrix(matrix_id: UUID) -> dict:
    """Run all pending/failed cells in a matrix (max concurrent triggers)."""
    matrix = await get_matrix(matrix_id)
    if not matrix:
        return {"error": "Matrix not found"}

    # Get cells that need processing: pending, failed, or stuck running (no results)
    cells = [
        c for c in matrix["cells"]
        if c["status"] in ("pending", "failed")
        or (c["status"] in ("running", "queued") and c.get("result_mean") is None)
    ]

    if not cells:
        return {"message": "No cells to run", "total": len(matrix["cells"])}

    # Mark all as queued
    for cell in cells:
        await db.execute(
            "UPDATE matrix_cells SET status = 'queued', updated_at = NOW() WHERE id = $1",
            cell["id"],
        )

    # Process in batches
    results = []
    for i in range(0, len(cells), MAX_CONCURRENT_TRIGGERS):
        batch = cells[i:i + MAX_CONCURRENT_TRIGGERS]
        batch_results = await asyncio.gather(
            *[_process_cell(matrix, cell) for cell in batch],
            return_exceptions=True,
        )
        for r in batch_results:
            if isinstance(r, Exception):
                results.append({"status": "error", "error": str(r)})
            else:
                results.append(r)

    return {
        "total": len(matrix["cells"]),
        "triggered": len(results),
        "results": results,
    }


async def run_cell(matrix_id: UUID, cell_id: UUID) -> dict:
    """Run a single cell."""
    matrix = await get_matrix(matrix_id)
    if not matrix:
        return {"error": "Matrix not found"}

    cell = next((c for c in matrix["cells"] if str(c["id"]) == str(cell_id)), None)
    if not cell:
        return {"error": "Cell not found"}

    return await _process_cell(matrix, cell)


async def poll_status(matrix_id: UUID) -> dict | None:
    """Re-check all non-completed cells and return updated matrix."""
    matrix = await get_matrix(matrix_id)
    if not matrix:
        return None

    # Check running, queued, AND pending cells (not just running)
    active_cells = [
        c for c in matrix["cells"]
        if c["status"] in ("running", "queued", "pending")
    ]

    for cell in active_cells:
        try:
            await _process_cell(matrix, cell)
        except Exception as e:
            logger.warning("Error polling cell %s: %s", cell["id"], e)

    # Return refreshed matrix
    return await get_matrix(matrix_id)
