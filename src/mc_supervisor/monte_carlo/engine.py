"""Distributed Monte Carlo simulation engine using Spark applyInPandas.

Simulation types are loaded from config.yaml. Each type maps to a model
template function (in model_templates.py) that implements the statistical
logic. Adding a new simulation type that fits an existing template requires
only a config.yaml change -- zero Python code.
"""

from __future__ import annotations

from typing import Callable

import pandas as pd
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, lit

from . import config_loader, model_templates

# ---------------------------------------------------------------------------
# Config-driven simulation registry
# ---------------------------------------------------------------------------

_SIMULATION_REGISTRY: dict[str, tuple[Callable, str]] = {}


def _ensure_registry() -> None:
    """Populate registry from config if not already done."""
    if _SIMULATION_REGISTRY:
        return
    config = config_loader.load_config()
    for sim_type, sim_config in config["simulation_types"].items():
        template_fn = model_templates.get_template(sim_config["model_template"])
        schema = sim_config["schema"]
        _SIMULATION_REGISTRY[sim_type] = (template_fn, schema)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_simulation_model(simulation_type: str) -> tuple[Callable, str]:
    """Return (simulation_function, output_schema) for the given type.

    Raises
    ------
    ValueError
        If *simulation_type* is not in the registry.
    """
    _ensure_registry()
    if simulation_type not in _SIMULATION_REGISTRY:
        available = ", ".join(sorted(_SIMULATION_REGISTRY.keys()))
        raise ValueError(
            f"Unknown simulation type '{simulation_type}'. "
            f"Available types: {available}"
        )
    return _SIMULATION_REGISTRY[simulation_type]


def get_available_simulation_types() -> list[str]:
    """Return a sorted list of all registered simulation type names."""
    _ensure_registry()
    return sorted(_SIMULATION_REGISTRY.keys())


def create_seed_dataframe(spark: SparkSession, num_batches: int, base_seed: int) -> DataFrame:
    """Create a DataFrame with one row per batch, each with a unique seed.

    Returns a Spark DataFrame with columns ``id`` (batch index) and
    ``batch_seed`` (deterministic seed derived from *base_seed*).
    """
    return spark.range(num_batches).withColumn("batch_seed", col("id") + lit(base_seed))


def run_distributed_simulation(
    spark: SparkSession,
    simulation_type: str,
    params: dict,
    num_simulations: int = 10_000,
    seed: int = 42,
    num_batches: int = 50,
) -> DataFrame:
    """Run a Monte Carlo simulation distributed across Spark executors.

    The workflow:
      1. Creates a seed DataFrame (one row per batch).
      2. Merges config defaults with caller-provided *params*.
      3. Runs ``groupBy("id").applyInPandas(...)`` with the appropriate
         model template so that each batch executes in parallel.
      4. Returns the raw trials DataFrame.

    Parameters
    ----------
    spark : SparkSession
        Active Spark session.
    simulation_type : str
        One of the registered simulation types (e.g. ``"patient_volume"``).
    params : dict
        Model-specific parameters.  Merged with config defaults (caller
        values take precedence).  A ``trials_per_batch`` key is injected
        automatically to split *num_simulations* evenly across batches.
    num_simulations : int
        Total number of Monte Carlo trials to run (default 10 000).
    seed : int
        Base random seed for reproducibility (default 42).
    num_batches : int
        Number of Spark partitions / batches (default 50).

    Returns
    -------
    pyspark.sql.DataFrame
        Raw trial-level results whose schema depends on *simulation_type*.
    """
    model_fn, output_schema = get_simulation_model(simulation_type)

    # Merge config defaults with caller-provided params (caller wins)
    default_params = config_loader.get_default_params(simulation_type)
    merged_params = {**default_params, **params}

    # Validate that distribution specs are present if required
    required_dists = config_loader.get_required_distributions(simulation_type)
    if required_dists and "distributions" not in merged_params:
        raise ValueError(
            f"Simulation type '{simulation_type}' requires distribution specs "
            f"({', '.join(required_dists.keys())}). Pass them via params['distributions']."
        )

    # Compute how many trials each batch should run
    trials_per_batch = max(1, num_simulations // num_batches)
    merged_params["trials_per_batch"] = trials_per_batch

    # Seed DataFrame -- one row per batch
    seed_df = create_seed_dataframe(spark, num_batches, base_seed=seed)

    # Wrapper that captures params via closure (serverless-compatible —
    # spark.sparkContext.broadcast is not available on Spark Connect).
    def _apply_fn(pdf: pd.DataFrame) -> pd.DataFrame:
        return model_fn(pdf, merged_params)

    # Execute across executors via applyInPandas
    trials_df = seed_df.groupBy("id").applyInPandas(_apply_fn, schema=output_schema)

    return trials_df


def run_local_simulation(
    simulation_type: str,
    params: dict,
    num_simulations: int = 10_000,
    seed: int = 42,
    num_batches: int = 50,
) -> pd.DataFrame:
    """Run a Monte Carlo simulation locally on the driver (no Spark workers).

    Produces the same results as :func:`run_distributed_simulation` but
    executes entirely in the driver process using pandas. This avoids
    cloudpickle serialisation issues on serverless compute where workers
    cannot import custom packages.

    Returns
    -------
    pandas.DataFrame
        Raw trial-level results.
    """
    model_fn, _output_schema = get_simulation_model(simulation_type)

    default_params = config_loader.get_default_params(simulation_type)
    merged_params = {**default_params, **params}

    required_dists = config_loader.get_required_distributions(simulation_type)
    if required_dists and "distributions" not in merged_params:
        raise ValueError(
            f"Simulation type '{simulation_type}' requires distribution specs "
            f"({', '.join(required_dists.keys())}). Pass them via params['distributions']."
        )

    trials_per_batch = max(1, num_simulations // num_batches)
    merged_params["trials_per_batch"] = trials_per_batch

    all_dfs: list[pd.DataFrame] = []
    for i in range(num_batches):
        batch_pdf = pd.DataFrame({"id": [i], "batch_seed": [i + seed]})
        result = model_fn(batch_pdf, merged_params)
        all_dfs.append(result)

    return pd.concat(all_dfs, ignore_index=True)
