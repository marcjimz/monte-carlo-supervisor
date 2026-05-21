-- Monte Carlo simulation tables — 4 tables for run metadata, trial data, and results.
-- Parameters: :catalog, :schema (passed via DAB sql_task base_parameters)

USE CATALOG IDENTIFIER(:catalog);
USE SCHEMA IDENTIFIER(:schema);

-- 1. simulation_runs — run metadata and cache index
CREATE TABLE IF NOT EXISTS simulation_runs (
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
);

-- 2. simulation_trials — Bronze: raw trial-level results
CREATE TABLE IF NOT EXISTS simulation_trials (
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
);

-- 3. simulation_results — Gold: aggregated percentile distributions
CREATE TABLE IF NOT EXISTS simulation_results (
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
);

-- 4. distribution_specs — fitted distribution parameter store
CREATE TABLE IF NOT EXISTS distribution_specs (
    simulation_type     STRING      NOT NULL COMMENT 'Simulation type this spec belongs to',
    distribution_name   STRING      NOT NULL COMMENT 'Named distribution within the simulation type',
    version             INT         NOT NULL COMMENT 'Monotonically increasing version (higher = newer)',
    spec                STRING      NOT NULL COMMENT 'JSON distribution spec: {"type": "lognormal", "params": {...}}',
    fit_metadata        STRING               COMMENT 'JSON fitting metadata: source table, n_samples, ks_stat, p_value',
    created_at          STRING      NOT NULL COMMENT 'ISO-8601 UTC timestamp of spec creation'
)
USING DELTA
COMMENT 'Fitted distribution parameter store for Monte Carlo simulations'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true'
);
