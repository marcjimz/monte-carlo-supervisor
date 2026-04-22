# Databricks notebook source
# MAGIC %md
# MAGIC # 01 — Load Synthetic Data into Unity Catalog
# MAGIC
# MAGIC Reads pre-generated CSV files from the repository's `/data/` directory and loads
# MAGIC them into Delta tables in the configured Unity Catalog schema.

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
print("Synthetic data load complete.")
