"""Tool definitions wrapping existing services for the LangGraph agent.

Each tool is a plain async function decorated with @tool. The agent calls
these directly — no UC functions or MCP indirection.
"""

from __future__ import annotations

import asyncio
import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Polling config for run_simulation
_POLL_INTERVAL_SECONDS = 15
_MAX_POLL_ATTEMPTS = 40  # 40 × 15s = 10 minutes max wait


@tool
async def run_simulation(
    simulation_type: str,
    parameters: str = "{}",
    num_simulations: int = 10000,
    seed: int = 42,
) -> str:
    """Run a Monte Carlo simulation and return results.

    This is a long-running tool. It:
    1. Normalizes parameters (fills in defaults for omitted values).
    2. Checks for a cached COMPLETED run with the same parameters.
    3. If cached, returns results immediately.
    4. If not cached, triggers a new simulation job and polls until completion.

    Do NOT call this in a loop. Call it once — it handles polling internally
    and returns only when results are ready (or after timeout).

    Args:
        simulation_type: The type of simulation (e.g. cost_comparison, system_cost_roi).
        parameters: JSON string of simulation parameters. Use '{}' for defaults.
        num_simulations: Number of Monte Carlo trials (default 10000).
        seed: Random seed for reproducibility (default 42).
    """
    from server.services import simulation_service

    params = json.loads(parameters) if isinstance(parameters, str) else parameters

    # Trigger (or get cached result)
    result = await simulation_service.trigger_simulation(
        simulation_type, params, num_simulations, seed,
    )

    # If already completed (cache hit), return immediately
    if result.get("status") == "completed":
        return json.dumps(result)

    # Poll until completion
    logger.info("Simulation %s — polling for results (status: %s)", simulation_type, result.get("status"))
    for attempt in range(1, _MAX_POLL_ATTEMPTS + 1):
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        check = await simulation_service.check_simulation(
            simulation_type, params, num_simulations, seed,
        )
        status = check.get("status")
        logger.info("Poll %d/%d for %s: status=%s", attempt, _MAX_POLL_ATTEMPTS, simulation_type, status)

        if status == "completed":
            return json.dumps(check)

        if status == "failed":
            return json.dumps(check)

    # Timeout — return last known status
    return json.dumps({
        "status": "timeout",
        "simulation_type": simulation_type,
        "message": "Simulation did not complete within 10 minutes. Check the Simulation Builder for results.",
    })


@tool
async def create_matrix(
    simulation_type: str,
    row_parameter: str,
    row_values: str,
    col_parameter: str,
    col_values: str,
    base_parameters: str = "{}",
    name: str = "",
    num_simulations: int = 10000,
    seed: int = 42,
) -> str:
    """Create a parameter sweep matrix for sensitivity analysis.

    Creates a grid of simulations varying two parameters. Cell simulations
    are automatically triggered after creation.

    Args:
        simulation_type: The type of simulation.
        row_parameter: Parameter name for rows.
        row_values: JSON array of values for the row parameter.
        col_parameter: Parameter name for columns.
        col_values: JSON array of values for the column parameter.
        base_parameters: JSON string of non-swept parameters.
        name: Optional matrix name.
        num_simulations: Trials per cell (default 10000).
        seed: Random seed (default 42).
    """
    row_vals = json.loads(row_values) if isinstance(row_values, str) else row_values
    col_vals = json.loads(col_values) if isinstance(col_values, str) else col_values
    base_params = json.loads(base_parameters) if isinstance(base_parameters, str) else base_parameters

    if not name:
        name = f"{simulation_type} — {row_parameter} vs {col_parameter}"

    return json.dumps({
        "status": "validated",
        "simulation_type": simulation_type,
        "row_parameter": row_parameter,
        "row_values": row_vals,
        "col_parameter": col_parameter,
        "col_values": col_vals,
        "base_parameters": base_params,
        "name": name,
        "num_simulations": num_simulations,
        "seed": seed,
        "total_cells": len(row_vals) * len(col_vals),
    })


@tool
async def list_distributions(simulation_type: str = "") -> str:
    """List fitted distribution specs for simulation types.

    Optionally filter by simulation_type. Returns JSON array of distribution
    specs with parameters and goodness-of-fit metrics.

    Args:
        simulation_type: Optional filter — leave empty for all types.
    """
    from server.services import distribution_service

    result = await distribution_service.list_distribution_specs(simulation_type or None)
    return json.dumps(result, default=str)


@tool
async def query_analytics(question: str) -> str:
    """Ask a natural language question about hospital data via Genie.

    Use for historical data queries: costs, trends, volumes, demographics,
    diagnosis prevalence, payer mix, department throughput, and past
    simulation results.

    Args:
        question: Natural language question about women's health data.
    """
    # Genie integration is handled by the genie node, not this tool.
    # This tool returns a marker that the graph routes to the genie node.
    return json.dumps({"route": "genie", "question": question})


def get_all_tools() -> list:
    """Return all tools for the agent."""
    return [
        run_simulation,
        create_matrix,
        list_distributions,
        query_analytics,
    ]
