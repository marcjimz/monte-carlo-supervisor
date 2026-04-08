"""UC Function definition for run_simulation — entry point for MAS to trigger MC simulations."""


class RunSimulationFunction:
    """UC Function that checks cache and triggers Monte Carlo simulation jobs."""

    name = "run_simulation"
    description = (
        "Runs or retrieves a Monte Carlo simulation. "
        "Checks cache first; triggers a Databricks Job if not cached. "
        "Supports: patient_volume, revenue, readmission_risk, capacity, length_of_stay."
    )

    @classmethod
    def get_registration_sql(cls, catalog: str, schema: str, mc_job_id: str = "{{MC_JOB_ID}}") -> str:
        return f"""
CREATE OR REPLACE FUNCTION {catalog}.{schema}.{cls.name}(
    simulation_type STRING COMMENT 'One of: patient_volume, revenue, readmission_risk, capacity, length_of_stay',
    parameters STRING COMMENT 'JSON parameters for the simulation, e.g. {{"department": "Emergency", "forecast_days": 90}}',
    num_simulations INT DEFAULT 10000 COMMENT 'Number of Monte Carlo trials',
    seed INT DEFAULT 42 COMMENT 'Random seed for reproducibility'
)
RETURNS STRING
LANGUAGE PYTHON
COMMENT '{cls.description}'
AS $$
import json
import hashlib
from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()
CATALOG = "{catalog}"
SCHEMA = "{schema}"
MC_JOB_ID = "{mc_job_id}"

# Validate simulation type
VALID_TYPES = ["patient_volume", "revenue", "readmission_risk", "capacity", "length_of_stay"]
if simulation_type not in VALID_TYPES:
    return json.dumps({{"error": f"Invalid simulation_type '{{simulation_type}}'. Must be one of: {{VALID_TYPES}}"}})

# Validate parameters JSON
try:
    params = json.loads(parameters)
except json.JSONDecodeError as e:
    return json.dumps({{"error": f"Invalid JSON in parameters: {{str(e)}}"}})

# Compute cache key
cache_input = f"{{simulation_type}}:{{parameters}}:{{seed}}:{{num_simulations}}"
params_hash = hashlib.sha256(cache_input.encode()).hexdigest()

# Check cache
try:
    cached = spark.sql(f\"\"\"
        SELECT run_id, created_at
        FROM {{CATALOG}}.{{SCHEMA}}.simulation_runs
        WHERE params_hash = '{{params_hash}}' AND status = 'COMPLETED'
        ORDER BY created_at DESC LIMIT 1
    \"\"\").collect()

    if cached:
        run_id = cached[0]["run_id"]
        results = spark.sql(f\"\"\"
            SELECT simulation_type, metric_name, group_key, group_value,
                   mean_value, std_value, p10, p25, p50, p75, p90
            FROM {{CATALOG}}.{{SCHEMA}}.simulation_results
            WHERE run_id = '{{run_id}}'
        \"\"\").toPandas().to_dict(orient="records")
        return json.dumps({{
            "status": "cached",
            "run_id": run_id,
            "simulation_type": simulation_type,
            "parameters": params,
            "results": results
        }})
except Exception:
    pass  # Table may not exist yet on first run

# Trigger new job run
try:
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    run = w.jobs.run_now(
        job_id=int(MC_JOB_ID),
        notebook_params={{
            "simulation_type": simulation_type,
            "parameters": parameters,
            "num_simulations": str(num_simulations),
            "seed": str(seed),
            "catalog": CATALOG,
            "schema": SCHEMA,
        }}
    )
    return json.dumps({{
        "status": "triggered",
        "job_run_id": str(run.run_id),
        "simulation_type": simulation_type,
        "parameters": params,
        "num_simulations": num_simulations,
        "seed": seed,
        "message": f"Monte Carlo simulation job triggered (run_id: {{run.run_id}}). Results will be written to {{CATALOG}}.{{SCHEMA}}.simulation_results."
    }})
except Exception as e:
    return json.dumps({{"status": "error", "message": str(e)}})
$$;"""

    @classmethod
    def get_grant_sql(cls, catalog: str, schema: str, principal: str = "account users") -> str:
        return f"GRANT EXECUTE ON FUNCTION {catalog}.{schema}.{cls.name} TO `{principal}`;"
