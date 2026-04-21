# Databricks notebook source
# MAGIC %md
# MAGIC # MC Step 2: Run Distributed Monte Carlo Simulation
# MAGIC
# MAGIC Executes the Monte Carlo simulation across Spark executors using
# MAGIC `applyInPandas`.  Writes raw trial-level results to the Bronze
# MAGIC `simulation_trials` table.  Skips execution when the validate step
# MAGIC reported a cache hit.

# COMMAND ----------

# Widget definitions -- values are injected by the Databricks job
dbutils.widgets.text("simulation_type", "", "Simulation Type")
dbutils.widgets.text("parameters", "{}", "Parameters JSON")
dbutils.widgets.text("num_simulations", "10000", "Number of Simulations")
dbutils.widgets.text("seed", "42", "Random Seed")
dbutils.widgets.text("catalog", "lakebase_hls_workshop_catalog", "Unity Catalog Name")
dbutils.widgets.text("schema", "hospital_data", "Schema Name")

# COMMAND ----------

# Add bundle root to sys.path so `src` package is importable
import sys
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_root = "/Workspace" + "/".join(_nb.split("/")[:-3])
if _root not in sys.path:
    sys.path.insert(0, _root)

# COMMAND ----------

import json

from src.databricks.monte_carlo.engine import run_distributed_simulation
from src.databricks.monte_carlo.results import update_run_status, write_bronze_trials

# COMMAND ----------

# Read widget values
simulation_type = dbutils.widgets.get("simulation_type")
parameters_json = dbutils.widgets.get("parameters")
num_simulations = int(dbutils.widgets.get("num_simulations"))
seed = int(dbutils.widgets.get("seed"))
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

print(f"Simulation type : {simulation_type}")
print(f"Num simulations : {num_simulations}")
print(f"Seed            : {seed}")
print(f"Catalog/Schema  : {catalog}.{schema}")

# COMMAND ----------

# ---------- Step 1: Check for cache hit from validate step ----------

cache_hit = dbutils.jobs.taskValues.get("validate_and_check_cache", "cache_hit", debugValue=False)
run_id = dbutils.jobs.taskValues.get("validate_and_check_cache", "run_id", debugValue="debug-run-id")

print(f"Cache hit : {cache_hit}")
print(f"Run ID    : {run_id}")

if cache_hit:
    print("[SKIP] Cache hit detected -- simulation already exists. Nothing to do.")
    dbutils.jobs.taskValues.set(key="trials_written", value=0)
    dbutils.notebook.exit(json.dumps({"skipped": True, "reason": "cache_hit"}))

# COMMAND ----------

# ---------- Step 2: Parse parameters (use enriched params from validate step) ----------

enriched_json = dbutils.jobs.taskValues.get(
    "validate_and_check_cache", "enriched_parameters", debugValue=parameters_json
)
params_dict = json.loads(enriched_json)
print(f"Parsed {len(params_dict)} parameter(s): {list(params_dict.keys())}")
if "distributions" in params_dict:
    print(f"Distribution specs: {list(params_dict['distributions'].keys())}")

# COMMAND ----------

# ---------- Step 3: Run distributed simulation ----------

try:
    print(f"Starting distributed simulation: {simulation_type}")
    print(f"  Trials  : {num_simulations}")
    print(f"  Seed    : {seed}")

    trials_df = run_distributed_simulation(
        spark=spark,
        simulation_type=simulation_type,
        params=params_dict,
        num_simulations=num_simulations,
        seed=seed,
    )

    print("Simulation DataFrame built. Writing to Bronze table...")

except Exception as exc:
    print(f"[ERROR] Simulation failed: {exc}")
    try:
        update_run_status(spark, catalog, schema, run_id, "FAILED")
        print(f"Run status updated to FAILED for run_id={run_id}")
    except Exception as status_exc:
        print(f"[ERROR] Additionally failed to update run status: {status_exc}")
    raise

# COMMAND ----------

# ---------- Step 4: Write Bronze trials ----------

try:
    print(f"Writing Bronze trials to {catalog}.{schema}.simulation_trials ...")

    write_bronze_trials(
        spark=spark,
        catalog=catalog,
        schema=schema,
        run_id=run_id,
        trials_df=trials_df,
        simulation_type=simulation_type,
    )

    # Count from the written table (avoids .cache() which is not supported on serverless)
    trials_count = (
        spark.read.table(f"{catalog}.{schema}.simulation_trials")
        .filter(f"run_id = '{run_id}'")
        .count()
    )
    print(f"Successfully wrote {trials_count} trial rows for run_id={run_id}")

except Exception as exc:
    print(f"[ERROR] Failed to write Bronze trials: {exc}")
    try:
        update_run_status(spark, catalog, schema, run_id, "FAILED")
        print(f"Run status updated to FAILED for run_id={run_id}")
    except Exception as status_exc:
        print(f"[ERROR] Additionally failed to update run status: {status_exc}")
    raise

# COMMAND ----------

# ---------- Step 5: Set task values and print summary ----------

dbutils.jobs.taskValues.set(key="trials_written", value=trials_count)

print("=" * 60)
print("Simulation Step Summary")
print("=" * 60)
print(f"  Run ID          : {run_id}")
print(f"  Simulation type : {simulation_type}")
print(f"  Trials written  : {trials_count}")
print(f"  Target table    : {catalog}.{schema}.simulation_trials")
print("=" * 60)
print("\nProceeding to aggregation step.")
