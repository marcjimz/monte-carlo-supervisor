# Databricks notebook source
# MAGIC %md
# MAGIC # MC Step 1: Validate Parameters & Check Cache
# MAGIC
# MAGIC Validates incoming simulation parameters and checks whether a completed run
# MAGIC with the same configuration already exists in the cache.  If a cache hit is
# MAGIC found the downstream tasks can skip re-computation.

# COMMAND ----------

# Widget definitions -- values are injected by the Databricks job
dbutils.widgets.text("simulation_type", "", "Simulation Type")
dbutils.widgets.text("parameters", "{}", "Parameters JSON")
dbutils.widgets.text("num_simulations", "10000", "Number of Simulations")
dbutils.widgets.text("seed", "42", "Random Seed")
dbutils.widgets.text("catalog", "monte_carlo_sim", "Unity Catalog Name")
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
import uuid

from src.databricks.monte_carlo.engine import get_available_simulation_types
from src.databricks.monte_carlo.results import (
    check_cache,
    compute_cache_key,
    write_run_metadata,
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
print(f"Parameters      : {parameters_json}")
print(f"Num simulations : {num_simulations}")
print(f"Seed            : {seed}")
print(f"Catalog/Schema  : {catalog}.{schema}")

# COMMAND ----------

# ---------- Step 1: Validate simulation_type ----------

available_types = get_available_simulation_types()

if simulation_type not in available_types:
    msg = (
        f"Invalid simulation_type '{simulation_type}'. "
        f"Must be one of: {', '.join(available_types)}"
    )
    raise ValueError(msg)

print(f"[VALID] simulation_type '{simulation_type}' is recognised.")

# COMMAND ----------

# ---------- Step 2: Parse and validate the JSON parameters ----------

try:
    params_dict = json.loads(parameters_json)
    if not isinstance(params_dict, dict):
        raise TypeError(
            f"Parameters must be a JSON object, got {type(params_dict).__name__}"
        )
except json.JSONDecodeError as exc:
    raise ValueError(f"Failed to parse parameters JSON: {exc}") from exc

print(f"[VALID] Parsed {len(params_dict)} parameter(s): {list(params_dict.keys())}")

# COMMAND ----------

# ---------- Step 3: Compute cache key ----------

params_hash = compute_cache_key(simulation_type, parameters_json, seed, num_simulations)
print(f"Cache key (params_hash): {params_hash}")

# COMMAND ----------

# ---------- Step 4: Check cache ----------

cache_result = check_cache(spark, catalog, schema, params_hash)

if cache_result is not None:
    cached_run_id = cache_result["run_id"]
    print(f"[CACHE HIT] Found completed run: {cached_run_id}")
    print(f"  Created at: {cache_result['created_at']}")

    dbutils.jobs.taskValues.set(key="cache_hit", value= True)
    dbutils.jobs.taskValues.set(key="cached_run_id", value=cached_run_id)
    dbutils.jobs.taskValues.set(key="run_id", value= cached_run_id)
    dbutils.jobs.taskValues.set(key="params_hash", value= params_hash)

    print("Downstream tasks will reuse existing results. Exiting early.")
    dbutils.notebook.exit(json.dumps({"cache_hit": True, "run_id": cached_run_id}))

# COMMAND ----------

# ---------- Step 5: Cache miss -- create new run ----------

print("[CACHE MISS] No completed run found for this configuration.")

run_id = str(uuid.uuid4())
print(f"Generated new run_id: {run_id}")

try:
    write_run_metadata(
        spark=spark,
        catalog=catalog,
        schema=schema,
        run_id=run_id,
        simulation_type=simulation_type,
        parameters=parameters_json,
        params_hash=params_hash,
        seed=seed,
        num_simulations=num_simulations,
    )
    print(f"Run metadata written to {catalog}.{schema}.simulation_runs")
except Exception as exc:
    print(f"[ERROR] Failed to write run metadata: {exc}")
    raise

# COMMAND ----------

# ---------- Step 6: Set task values for downstream tasks ----------

dbutils.jobs.taskValues.set(key="cache_hit", value= False)
dbutils.jobs.taskValues.set(key="run_id", value= run_id)
dbutils.jobs.taskValues.set(key="params_hash", value= params_hash)

print("Task values set:")
print(f"  cache_hit   = False")
print(f"  run_id      = {run_id}")
print(f"  params_hash = {params_hash}")
print("\nValidation complete. Proceeding to simulation step.")
