# Databricks notebook source
# MAGIC %md
# MAGIC # 02 — Create UC Metric Views
# MAGIC
# MAGIC Creates the 6 Unity Catalog Metric Views that provide pre-defined measures and
# MAGIC dimensions for Genie Space analytics.

# COMMAND ----------

dbutils.widgets.text("catalog", "monte_carlo_sim", "UC Catalog")
dbutils.widgets.text("schema", "hospital_data", "UC Schema")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

print(f"Target: {catalog}.{schema}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create All Metric Views

# COMMAND ----------

from src.databricks.metric_views.definitions import get_metric_view_definitions

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

display(
    spark.sql(
        f"SHOW VIEWS IN {catalog}.{schema}"
    ).filter("viewName LIKE 'mv_%'")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Metric View Summary
# MAGIC
# MAGIC | View | Purpose |
# MAGIC |------|---------|
# MAGIC | `mv_encounter_summary` | Encounter KPIs by department, type, and time |
# MAGIC | `mv_revenue_by_payer` | Revenue and reimbursement by payer and claim status |
# MAGIC | `mv_readmission_rates` | 30-day readmission rates by diagnosis and department |
# MAGIC | `mv_daily_census` | Daily inpatient census and bed utilization |
# MAGIC | `mv_department_throughput` | Department-level volume and procedure counts |
# MAGIC | `mv_patient_demographics` | Population health by age, gender, insurance type |

# COMMAND ----------

print("Metric view creation complete.")
