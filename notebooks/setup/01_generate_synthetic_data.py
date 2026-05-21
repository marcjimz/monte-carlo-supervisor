# Databricks notebook source
# MAGIC %md
# MAGIC # 01 — Load Synthetic Data into Unity Catalog
# MAGIC
# MAGIC Reads pre-generated CSV files from the repository's `/data/` directory and loads
# MAGIC them into Delta tables in the configured Unity Catalog schema.
# MAGIC
# MAGIC **Customer deployments**: Set `skip_synthetic=true` to skip synthetic data
# MAGIC generation entirely. The customer provides their own `project_accelerate_encounters`
# MAGIC table and this notebook only creates the schema.

# COMMAND ----------

dbutils.widgets.text("catalog", "monte_carlo_supervisor_catalog", "UC Catalog")
dbutils.widgets.text("schema", "hospital_data", "UC Schema")
dbutils.widgets.text("skip_synthetic", "false", "Skip synthetic data generation")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
skip_synthetic = dbutils.widgets.get("skip_synthetic").lower() in ("true", "1", "yes")

print(f"Target: {catalog}.{schema}")
print(f"Skip synthetic data: {skip_synthetic}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Schema (if needed)

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
print(f"Schema {catalog}.{schema} ready.")

# Grant UC privileges to app service principal (needed for SQL warehouse queries)
try:
    app_sp = dbutils.widgets.get("app_sp_client_id")
except Exception:
    app_sp = ""
if app_sp:
    spark.sql(f"GRANT USE CATALOG ON CATALOG {catalog} TO `{app_sp}`")
    spark.sql(f"GRANT USE SCHEMA ON SCHEMA {catalog}.{schema} TO `{app_sp}`")
    spark.sql(f"GRANT SELECT ON SCHEMA {catalog}.{schema} TO `{app_sp}`")
    spark.sql(f"GRANT MODIFY ON SCHEMA {catalog}.{schema} TO `{app_sp}`")
    print(f"Granted USE CATALOG, USE SCHEMA, SELECT, MODIFY to {app_sp}")

# COMMAND ----------

if skip_synthetic:
    print("Skipping synthetic data generation — customer provides their own data.")
    dbutils.notebook.exit("SKIPPED: skip_synthetic=true")

# COMMAND ----------

# Install project package from bundled wheel
import subprocess, sys
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_root = "/Workspace" + "/".join(_nb.split("/")[:-3])
subprocess.check_call([sys.executable, "-m", "pip", "install", f"{_root}/dist/monte_carlo_supervisor-1.0.0-py3-none-any.whl", "-q", "--disable-pip-version-check"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load All Tables

# COMMAND ----------

from mc_supervisor.synthetic_data.loader import load_all_tables

results = load_all_tables(spark, catalog=catalog, schema=schema, data_dir=f"{_root}/data")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Row Counts Summary

# COMMAND ----------

print(f"\n{'Table':<25} {'Rows':>10}")
print("-" * 37)
for table_name, count in results.items():
    print(f"{table_name:<25} {count:>10,}")
print("-" * 37)
print(f"{'TOTAL':<25} {sum(results.values()):>10,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify — Sample from encounters table

# COMMAND ----------

display(spark.table(f"{catalog}.{schema}.encounters").limit(5))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load Accelerate Encounters (nested struct — direct Spark generation)

# COMMAND ----------

from mc_supervisor.synthetic_data.loader import load_accelerate_encounters

accel_count = load_accelerate_encounters(spark, catalog=catalog, schema=schema)
print(f"Accelerate encounters: {accel_count:,} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify — Sample from accelerate encounters

# COMMAND ----------

display(spark.table(f"{catalog}.{schema}.project_accelerate_encounters").limit(5))
print("Synthetic data load complete.")
