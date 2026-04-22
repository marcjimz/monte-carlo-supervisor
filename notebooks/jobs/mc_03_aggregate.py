# Databricks notebook source
# MAGIC %md
# MAGIC # MC Step 3: Aggregate Bronze to Gold
# MAGIC
# MAGIC Reads the raw trial-level results from the Bronze `simulation_trials` table,
# MAGIC computes percentile-based aggregations, and writes the Gold
# MAGIC `simulation_results` table.  Updates the run status to **COMPLETED** upon
# MAGIC success.

# COMMAND ----------

# Widget definitions -- values are injected by the Databricks job
dbutils.widgets.text("simulation_type", "", "Simulation Type")
dbutils.widgets.text("parameters", "{}", "Parameters JSON")
dbutils.widgets.text("num_simulations", "10000", "Number of Simulations")
dbutils.widgets.text("seed", "42", "Random Seed")
dbutils.widgets.text("catalog", "lakebase_hls_workshop_catalog", "Unity Catalog Name")
dbutils.widgets.text("schema", "hospital_data", "Schema Name")

# COMMAND ----------

# Install project package from bundled wheel and restart Python
# so that Spark workers pick up the package for any distributed ops
import subprocess, sys
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_root = "/Workspace" + "/".join(_nb.split("/")[:-3])
subprocess.check_call([sys.executable, "-m", "pip", "install", f"{_root}/dist/monte_carlo_supervisor-1.0.0-py3-none-any.whl", "-q", "--disable-pip-version-check"])

# COMMAND ----------

# Restart Python REPL to propagate installed package to Spark executors
dbutils.library.restartPython()

# COMMAND ----------

import json

from mc_supervisor.monte_carlo.results import (
    aggregate_to_gold,
    update_run_status,
)

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
    print("[SKIP] Cache hit detected -- Gold results already exist. Nothing to do.")
    dbutils.notebook.exit(json.dumps({"skipped": True, "reason": "cache_hit"}))

# COMMAND ----------

# ---------- Step 2: Aggregate to Gold ----------

try:
    print(f"Aggregating Bronze trials to Gold for run_id={run_id} ...")
    print(f"  Simulation type : {simulation_type}")
    print(f"  Source table    : {catalog}.{schema}.simulation_trials")
    print(f"  Target table    : {catalog}.{schema}.simulation_results")

    aggregate_to_gold(
        spark=spark,
        catalog=catalog,
        schema=schema,
        run_id=run_id,
        simulation_type=simulation_type,
    )

    print("Gold aggregation complete.")

except Exception as exc:
    print(f"[ERROR] Aggregation failed: {exc}")
    try:
        update_run_status(spark, catalog, schema, run_id, "FAILED")
        print(f"Run status updated to FAILED for run_id={run_id}")
    except Exception as status_exc:
        print(f"[ERROR] Additionally failed to update run status: {status_exc}")
    raise

# COMMAND ----------

# ---------- Step 3: Update run status to COMPLETED ----------

try:
    update_run_status(spark, catalog, schema, run_id, "COMPLETED")
    print(f"Run status updated to COMPLETED for run_id={run_id}")
except Exception as exc:
    print(f"[ERROR] Failed to update run status to COMPLETED: {exc}")
    raise

# COMMAND ----------

# ---------- Step 4: Display Gold results for verification ----------

results_table = f"{catalog}.{schema}.simulation_results"

print(f"\nGold results for run_id={run_id}:\n")

try:
    gold_df = spark.read.table(results_table).filter(
        f"run_id = '{run_id}'"
    )
    gold_count = gold_df.count()
    print(f"Total Gold rows: {gold_count}")
    gold_df.orderBy("group_value").show(50, truncate=False)
except Exception as exc:
    print(f"[WARNING] Could not display Gold results: {exc}")

# COMMAND ----------

# ---------- Step 5: Completion summary ----------

print("=" * 60)
print("Aggregation Step Summary")
print("=" * 60)
print(f"  Run ID          : {run_id}")
print(f"  Simulation type : {simulation_type}")
print(f"  Status          : COMPLETED")
print(f"  Gold table      : {results_table}")
print("=" * 60)
print("\nMonte Carlo simulation pipeline finished successfully.")
