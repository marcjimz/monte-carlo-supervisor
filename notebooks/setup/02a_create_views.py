# Databricks notebook source
# COMMAND ----------
# MAGIC %md
# MAGIC # 02a — Create Base Views & Metric Views
# MAGIC
# MAGIC Wrapper that executes the SQL view-creation scripts, with a `skip_views`
# MAGIC flag for customer deployments that bring their own metric view.

# COMMAND ----------

dbutils.widgets.text("catalog", "monte_carlo_supervisor_catalog")
dbutils.widgets.text("schema", "hospital_data")
dbutils.widgets.text("warehouse_id", "")
dbutils.widgets.text("skip_views", "false", "Skip view creation (customer has own metric view)")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
warehouse_id = dbutils.widgets.get("warehouse_id")
skip_views = dbutils.widgets.get("skip_views").lower() in ("true", "1", "yes")

print(f"Catalog/Schema : {catalog}.{schema}")
print(f"Skip views     : {skip_views}")

# COMMAND ----------

if skip_views:
    print("Skipping view creation — customer provides their own metric view.")
    dbutils.notebook.exit("SKIPPED: skip_views=true")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Execute Base Views SQL

# COMMAND ----------

import os
from pathlib import Path

bundle_root = os.environ.get("BUNDLE_ROOT", "")

def _find_sql(relative_path):
    candidates = []
    if bundle_root:
        candidates.append(Path(bundle_root) / relative_path)
    candidates.extend([
        Path(f"../{relative_path}"),
        Path(f"../../{relative_path}"),
    ])
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(f"SQL file not found: {relative_path}")

# COMMAND ----------

base_views_path = _find_sql("infra/sql/create_base_views.sql")
print(f"Running: {base_views_path}")

sql_text = base_views_path.read_text()
# Replace :catalog and :schema parameters
sql_text = sql_text.replace(":catalog", f"'{catalog}'").replace(":schema", f"'{schema}'")

for stmt in sql_text.split(";"):
    stmt = stmt.strip()
    if stmt and not stmt.startswith("--"):
        spark.sql(stmt)

print("Base views created.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Execute Metric Views SQL

# COMMAND ----------

metric_views_path = _find_sql("infra/sql/create_metric_views.sql")
print(f"Running: {metric_views_path}")

sql_text = metric_views_path.read_text()
sql_text = sql_text.replace(":catalog", f"'{catalog}'").replace(":schema", f"'{schema}'")

for stmt in sql_text.split(";"):
    stmt = stmt.strip()
    if stmt and not stmt.startswith("--"):
        spark.sql(stmt)

print("Metric views created.")
