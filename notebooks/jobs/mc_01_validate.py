# Databricks notebook source
# MAGIC %md
# MAGIC # MC Step 1: Validate Parameters & Check Cache
# MAGIC
# MAGIC Validates incoming simulation parameters and checks whether a completed run
# MAGIC with the same configuration already exists in the cache.  If a cache hit is
# MAGIC found the downstream tasks can skip re-computation.
# MAGIC
# MAGIC Also resolves distribution specs — fitted from historical data if available,
# MAGIC falling back to config.yaml defaults.

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
import uuid

from src.databricks.monte_carlo.engine import get_available_simulation_types
from src.databricks.monte_carlo.config_loader import (
    get_required_distributions,
    get_default_distribution_specs,
)
from src.databricks.monte_carlo.results import (
    check_cache,
    compute_cache_key,
    get_latest_distribution_version,
    resolve_distribution_specs,
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

# ---------- Step 3: Resolve distribution specs ----------

required = get_required_distributions(simulation_type)
dist_version = get_latest_distribution_version(spark, catalog, schema, simulation_type)

if dist_version is not None:
    dist_specs = resolve_distribution_specs(spark, catalog, schema, simulation_type, dist_version)
    print(f"[FITTED] Using distribution version {dist_version}")
else:
    dist_specs = get_default_distribution_specs(simulation_type)
    dist_version = "default"
    print("[DEFAULT] No fitted distributions found, using config defaults")

# Apply user-provided distribution overrides (if any)
dist_overrides = params_dict.pop("distribution_overrides", {})
if dist_overrides:
    from monte_carlo.distribution_sampler import validate_spec
    for dist_name, override_spec in dist_overrides.items():
        validate_spec(override_spec)  # Raises ValueError if malformed
        dist_specs[dist_name] = override_spec
        print(f"[OVERRIDE] {dist_name} → {override_spec['type']}({override_spec['params']})")

# Build enriched params for downstream simulation (includes distributions)
enriched_params = {**params_dict, "distributions": dist_specs, "distribution_version": dist_version}
enriched_json = json.dumps(enriched_params)

# IMPORTANT: parameters_json stays as the ORIGINAL user params (no distributions)
# so that check_simulation UC function can match on the same string the user passes.

print(f"Distribution specs resolved: {list(dist_specs.keys())}")

# COMMAND ----------

# ---------- Step 4: Compute cache key ----------

params_hash = compute_cache_key(
    simulation_type, parameters_json, seed, num_simulations,
    distribution_version=dist_version,
)
print(f"Cache key (params_hash): {params_hash}")

# COMMAND ----------

# ---------- Step 5: Check cache ----------

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

# ---------- Step 6: Cache miss -- create new run ----------

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

# ---------- Step 7: Set task values for downstream tasks ----------

dbutils.jobs.taskValues.set(key="cache_hit", value= False)
dbutils.jobs.taskValues.set(key="run_id", value= run_id)
dbutils.jobs.taskValues.set(key="params_hash", value= params_hash)
dbutils.jobs.taskValues.set(key="enriched_parameters", value=enriched_json)

print("Task values set:")
print(f"  cache_hit   = False")
print(f"  run_id      = {run_id}")
print(f"  params_hash = {params_hash}")
print(f"  enriched_parameters includes distributions: {list(dist_specs.keys())}")
print("\nValidation complete. Proceeding to simulation step.")
