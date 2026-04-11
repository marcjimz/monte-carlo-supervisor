"""Bronze/Silver/Gold results storage for Monte Carlo simulations."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    IntegerType,
    StringType,
    StructField,
    StructType,
)

from . import config_loader

# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------


def compute_cache_key(
    simulation_type: str,
    parameters: str,
    seed: int,
    num_simulations: int,
) -> str:
    """Compute a deterministic SHA-256 hash for cache lookup.

    The hash is derived from the simulation type, canonicalized JSON
    parameters, seed, and simulation count so that identical requests
    produce the same key regardless of dict ordering.

    Parameters
    ----------
    simulation_type : str
        The type of simulation (e.g. ``"patient_volume"``).
    parameters : str
        JSON string of simulation parameters.
    seed : int
        Random seed.
    num_simulations : int
        Total number of Monte Carlo trials.

    Returns
    -------
    str
        A 64-character hex digest (SHA-256).
    """
    # Canonicalize the parameters JSON so key order doesn't matter
    try:
        canonical_params = json.dumps(json.loads(parameters), sort_keys=True, separators=(",", ":"))
    except (json.JSONDecodeError, TypeError):
        canonical_params = parameters

    payload = f"{simulation_type}|{canonical_params}|{seed}|{num_simulations}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Cache check
# ---------------------------------------------------------------------------


def check_cache(
    spark: SparkSession,
    catalog: str,
    schema: str,
    params_hash: str,
) -> dict | None:
    """Check if a matching simulation run exists and is completed.

    Queries the ``simulation_runs`` table for the most recent COMPLETED run
    with a matching ``params_hash``.

    Returns
    -------
    dict or None
        A dict with ``run_id``, ``created_at``, and ``params_hash`` if a
        cache hit is found, otherwise ``None``.
    """
    table = f"{catalog}.{schema}.simulation_runs"

    try:
        result = spark.sql(
            f"""
            SELECT run_id, created_at, params_hash
            FROM {table}
            WHERE params_hash = '{params_hash}'
              AND status = 'COMPLETED'
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        rows = result.collect()
        if rows:
            row = rows[0]
            return {
                "run_id": row["run_id"],
                "created_at": str(row["created_at"]),
                "params_hash": row["params_hash"],
            }
    except Exception:
        # Table may not exist yet -- treat as cache miss
        pass

    return None


# ---------------------------------------------------------------------------
# Run metadata (simulation_runs table)
# ---------------------------------------------------------------------------


def write_run_metadata(
    spark: SparkSession,
    catalog: str,
    schema: str,
    run_id: str,
    simulation_type: str,
    parameters: str,
    params_hash: str,
    seed: int,
    num_simulations: int,
    job_run_id: str | None = None,
) -> None:
    """Write a row to the ``simulation_runs`` table.

    The row is inserted with ``status = 'RUNNING'`` and the current UTC
    timestamp.
    """
    table = f"{catalog}.{schema}.simulation_runs"
    now = datetime.now(timezone.utc).isoformat()

    run_schema = StructType(
        [
            StructField("run_id", StringType(), False),
            StructField("simulation_type", StringType(), False),
            StructField("parameters", StringType(), False),
            StructField("params_hash", StringType(), False),
            StructField("seed", IntegerType(), False),
            StructField("num_simulations", IntegerType(), False),
            StructField("status", StringType(), False),
            StructField("job_run_id", StringType(), True),
            StructField("created_at", StringType(), False),
            StructField("updated_at", StringType(), False),
        ]
    )

    data = [
        (
            run_id,
            simulation_type,
            parameters,
            params_hash,
            seed,
            num_simulations,
            "RUNNING",
            job_run_id,
            now,
            now,
        )
    ]

    df = spark.createDataFrame(data, schema=run_schema)
    df.write.format("delta").mode("append").saveAsTable(table)


# ---------------------------------------------------------------------------
# Bronze: raw trial results
# ---------------------------------------------------------------------------


def write_bronze_trials(
    spark: SparkSession,
    catalog: str,
    schema: str,
    run_id: str,
    trials_df: DataFrame,
    simulation_type: str = "",
) -> None:
    """Append raw trial results to the ``simulation_trials`` Bronze table.

    Adds ``run_id``, ``simulation_type``, and ``created_at`` columns before
    writing.  Uses ``mergeSchema`` so that type-specific columns (e.g.
    ``simulated_encounters``, ``department``) are added automatically via
    Delta schema evolution — no DDL changes needed for new simulation types.
    """
    table = f"{catalog}.{schema}.simulation_trials"
    now = datetime.now(timezone.utc).isoformat()

    enriched = (
        trials_df
        .withColumn("run_id", F.lit(run_id))
        .withColumn("simulation_type", F.lit(simulation_type))
        .withColumn("created_at", F.lit(now))
    )

    enriched.write.format("delta").option("mergeSchema", "true").mode("append").saveAsTable(table)


# ---------------------------------------------------------------------------
# Gold: aggregated percentile results
# ---------------------------------------------------------------------------

_PERCENTILES = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]


def aggregate_to_gold(
    spark: SparkSession,
    catalog: str,
    schema: str,
    run_id: str,
    simulation_type: str,
) -> None:
    """Read Bronze trials for *run_id*, compute percentiles, and write to
    the ``simulation_results`` Gold table.

    For each simulation type the aggregation groups by the natural dimension
    (e.g. ``month`` for patient_volume, ``care_model`` for cost_comparison)
    and computes mean, std-dev, and the 5th / 10th / 25th / 50th / 75th /
    90th / 95th percentiles of the simulated metric.

    If additional_metrics are configured (e.g. for cost_comparison or
    system_cost_roi), each metric is aggregated separately and written as
    distinct rows with a unique ``metric_name``.
    """
    trials_table = f"{catalog}.{schema}.simulation_trials"
    results_table = f"{catalog}.{schema}.simulation_results"

    all_metrics = config_loader.get_all_agg_metrics(simulation_type)
    trials_df = spark.read.table(trials_table).filter(F.col("run_id") == run_id)
    now = datetime.now(timezone.utc).isoformat()

    for value_col, group_col in all_metrics:
        # Build aggregation expressions
        agg_exprs = [
            F.count("*").alias("num_trials"),
            F.mean(value_col).alias("mean_value"),
            F.stddev(value_col).alias("std_value"),
            F.min(value_col).alias("min_value"),
            F.max(value_col).alias("max_value"),
        ]
        for p in _PERCENTILES:
            alias = f"p{int(p * 100):02d}"
            agg_exprs.append(F.percentile_approx(value_col, p).alias(alias))

        agg_df = trials_df.groupBy(group_col).agg(*agg_exprs)

        gold_df = (
            agg_df.withColumn("run_id", F.lit(run_id))
            .withColumn("simulation_type", F.lit(simulation_type))
            .withColumn("metric_name", F.lit(value_col))
            .withColumn("group_key", F.lit(group_col))
            .withColumnRenamed(group_col, "group_value")
            .withColumn("created_at", F.lit(now))
            .select(
                "run_id",
                "simulation_type",
                "metric_name",
                "group_key",
                F.col("group_value").cast(StringType()).alias("group_value"),
                "num_trials",
                "mean_value",
                "std_value",
                "min_value",
                "max_value",
                "p05",
                "p10",
                "p25",
                "p50",
                "p75",
                "p90",
                "p95",
                "created_at",
            )
        )

        gold_df.write.format("delta").mode("append").saveAsTable(results_table)


# ---------------------------------------------------------------------------
# Status update
# ---------------------------------------------------------------------------


def update_run_status(
    spark: SparkSession,
    catalog: str,
    schema: str,
    run_id: str,
    status: str,
) -> None:
    """Update the status of a simulation run.

    Typical transitions: ``RUNNING`` -> ``COMPLETED`` or ``RUNNING`` -> ``FAILED``.
    Also sets ``updated_at`` to the current UTC time.
    """
    table = f"{catalog}.{schema}.simulation_runs"
    now = datetime.now(timezone.utc).isoformat()

    spark.sql(
        f"""
        UPDATE {table}
        SET status = '{status}',
            updated_at = '{now}'
        WHERE run_id = '{run_id}'
        """
    )


# ---------------------------------------------------------------------------
# DDL for simulation tables
# ---------------------------------------------------------------------------


def get_simulation_tables_ddl(catalog: str, schema: str) -> list[str]:
    """Return CREATE TABLE IF NOT EXISTS DDL for the three simulation tables.

    Tables:
      - ``simulation_runs``    -- run metadata and status
      - ``simulation_trials``  -- Bronze raw trial-level results
      - ``simulation_results`` -- Gold aggregated percentile results

    All tables use Delta format and are placed in the given Unity Catalog
    location.
    """
    return [
        # ----- simulation_runs (metadata) -----
        f"""
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.simulation_runs (
    run_id              STRING      NOT NULL COMMENT 'Unique simulation run identifier (UUID)',
    simulation_type     STRING      NOT NULL COMMENT 'Type of simulation (patient_volume, revenue, etc.)',
    parameters          STRING      NOT NULL COMMENT 'JSON-encoded simulation parameters',
    params_hash         STRING      NOT NULL COMMENT 'SHA-256 hash for cache lookup',
    seed                INT         NOT NULL COMMENT 'Base random seed',
    num_simulations     INT         NOT NULL COMMENT 'Total number of Monte Carlo trials',
    status              STRING      NOT NULL COMMENT 'Run status: RUNNING, COMPLETED, FAILED',
    job_run_id          STRING               COMMENT 'Databricks job run ID (if triggered via Jobs)',
    created_at          STRING      NOT NULL COMMENT 'ISO-8601 UTC timestamp of run creation',
    updated_at          STRING      NOT NULL COMMENT 'ISO-8601 UTC timestamp of last status update'
)
USING DELTA
COMMENT 'Monte Carlo simulation run metadata and cache index'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true'
)
""".strip(),
        # ----- simulation_trials (Bronze) -----
        # Minimal base schema — type-specific columns are added automatically
        # via Delta mergeSchema when write_bronze_trials() appends data.
        f"""
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.simulation_trials (
    run_id              STRING      NOT NULL COMMENT 'FK to simulation_runs.run_id',
    simulation_type     STRING      NOT NULL COMMENT 'Type of simulation that produced this trial',
    batch_id            BIGINT      NOT NULL COMMENT 'Batch index (Spark partition)',
    trial_id            BIGINT      NOT NULL COMMENT 'Global trial index',
    created_at          STRING      NOT NULL COMMENT 'ISO-8601 UTC timestamp'
)
USING DELTA
PARTITIONED BY (run_id)
COMMENT 'Bronze: raw Monte Carlo trial-level results (schema evolves via mergeSchema)'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true'
)
""".strip(),
        # ----- simulation_results (Gold) -----
        f"""
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.simulation_results (
    run_id              STRING      NOT NULL COMMENT 'FK to simulation_runs.run_id',
    simulation_type     STRING      NOT NULL COMMENT 'Type of simulation',
    metric_name         STRING      NOT NULL COMMENT 'Name of the simulated metric column',
    group_key           STRING      NOT NULL COMMENT 'Dimension name used for grouping (month, department, etc.)',
    group_value         STRING      NOT NULL COMMENT 'Dimension value',
    num_trials          BIGINT      NOT NULL COMMENT 'Number of trials aggregated',
    mean_value          DOUBLE      NOT NULL COMMENT 'Mean of simulated metric',
    std_value           DOUBLE               COMMENT 'Standard deviation of simulated metric',
    min_value           DOUBLE               COMMENT 'Minimum value',
    max_value           DOUBLE               COMMENT 'Maximum value',
    p05                 DOUBLE               COMMENT '5th percentile',
    p10                 DOUBLE               COMMENT '10th percentile',
    p25                 DOUBLE               COMMENT '25th percentile',
    p50                 DOUBLE               COMMENT '50th percentile (median)',
    p75                 DOUBLE               COMMENT '75th percentile',
    p90                 DOUBLE               COMMENT '90th percentile',
    p95                 DOUBLE               COMMENT '95th percentile',
    created_at          STRING      NOT NULL COMMENT 'ISO-8601 UTC timestamp'
)
USING DELTA
PARTITIONED BY (run_id)
COMMENT 'Gold: aggregated Monte Carlo simulation results with percentile distributions'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true'
)
""".strip(),
    ]
