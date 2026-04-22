# Databricks notebook source
# MAGIC %md
# MAGIC # 04 — Create Simulation Delta Tables
# MAGIC
# MAGIC Creates the 4 Delta tables used to store Monte Carlo simulation metadata,
# MAGIC raw trial results, aggregated Gold results, and fitted distribution specs.
# MAGIC
# MAGIC | Table | Layer | Purpose |
# MAGIC |-------|-------|---------|
# MAGIC | `simulation_runs` | Metadata | Run tracking, status, cache index |
# MAGIC | `simulation_trials` | Bronze | Raw trial-level simulation output |
# MAGIC | `simulation_results` | Gold | Aggregated percentile distributions |
# MAGIC | `distribution_specs` | Feature Store | Versioned fitted distribution parameters |

# COMMAND ----------

dbutils.widgets.text("catalog", "lakebase_hls_workshop_catalog", "UC Catalog")
dbutils.widgets.text("schema", "hospital_data", "UC Schema")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

print(f"Target: {catalog}.{schema}")

# COMMAND ----------

# Install project package from bundled wheel
import subprocess, sys
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_root = "/Workspace" + "/".join(_nb.split("/")[:-3])
subprocess.check_call([sys.executable, "-m", "pip", "install", f"{_root}/dist/monte_carlo_supervisor-1.0.0-py3-none-any.whl", "-q", "--disable-pip-version-check"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Tables

# COMMAND ----------

from mc_supervisor.monte_carlo.results import get_simulation_tables_ddl

ddl_statements = get_simulation_tables_ddl(catalog, schema)

TABLE_NAMES = ["simulation_runs", "simulation_trials", "simulation_results", "distribution_specs"]

print(f"Creating {len(ddl_statements)} simulation tables...\n")

for name, ddl in zip(TABLE_NAMES, ddl_statements):
    print(f"  Creating {name} ... ", end="")
    spark.sql(ddl)
    print("done.")

print(f"\nAll {len(ddl_statements)} simulation tables created.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify — Describe Tables

# COMMAND ----------

for name in TABLE_NAMES:
    full_name = f"{catalog}.{schema}.{name}"
    print(f"\n--- {full_name} ---")
    display(spark.sql(f"DESCRIBE TABLE {full_name}"))

# COMMAND ----------

print("Simulation table creation complete.")
