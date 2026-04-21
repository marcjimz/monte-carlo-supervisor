# Databricks notebook source
# MAGIC %md
# MAGIC # 02 — Create UC Metric Views
# MAGIC
# MAGIC Creates the 4 Women's Health Unity Catalog Metric Views that provide pre-defined
# MAGIC measures and dimensions for Genie Space analytics.

# COMMAND ----------

dbutils.widgets.text("catalog", "lakebase_hls_workshop_catalog", "UC Catalog")
dbutils.widgets.text("schema", "hospital_data", "UC Schema")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

print(f"Target: {catalog}.{schema}")

# COMMAND ----------

# Add bundle root to sys.path so `src` package is importable
import sys
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_root = "/Workspace" + "/".join(_nb.split("/")[:-3])
if _root not in sys.path:
    sys.path.insert(0, _root)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create All Metric Views

# COMMAND ----------

from src.databricks.metric_views.definitions import (
    get_base_view_definitions,
    get_metric_view_definitions,
)

# --- Step 1: Create base SQL views (pre-joined tables for metric views) ---
base_views = get_base_view_definitions(catalog, schema)
print(f"Creating {len(base_views)} base views (pre-joined tables)...\n")

for bv in base_views:
    name = bv["name"]
    ddl = bv["sql"]
    print(f"  Creating {name} ... ", end="")
    spark.sql(ddl)
    print("done.")

print(f"\nAll {len(base_views)} base views created.\n")

# --- Step 2: Create metric views ---
metric_views = get_metric_view_definitions(catalog, schema)
print(f"Creating {len(metric_views)} metric views...\n")

for mv in metric_views:
    name = mv["name"]
    ddl = mv["sql"]
    print(f"  Creating {name} ... ", end="")
    spark.sql(ddl)
    print("done.")

print(f"\nAll {len(metric_views)} metric views created successfully.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify — List Views in Schema

# COMMAND ----------

spark.sql(f"USE CATALOG {catalog}")
display(
    spark.sql(
        f"SHOW VIEWS IN {catalog}.{schema}"
    ).filter("viewName LIKE 'mv_%' OR viewName LIKE 'v_wh_%'")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Metric View Summary
# MAGIC
# MAGIC | View | Purpose |
# MAGIC |------|---------|
# MAGIC | `mv_wh_cost_by_condition` | Cost KPIs by department, ICD-10 condition, encounter type, payer |
# MAGIC | `mv_wh_encounter_summary` | Encounter volume by type, department, and time |
# MAGIC | `mv_wh_diagnosis_prevalence` | Diagnosis prevalence by condition and time |
# MAGIC | `mv_wh_patient_demographics` | Population health by age, insurance, chronic conditions |

# COMMAND ----------

print("Metric view creation complete.")
