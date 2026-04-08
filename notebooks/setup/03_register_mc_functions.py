# Databricks notebook source
# MAGIC %md
# MAGIC # 03 — Register Monte Carlo UC Functions
# MAGIC
# MAGIC Registers the `run_simulation` Unity Catalog function and grants execution
# MAGIC permissions. The function checks for cached results and triggers a Databricks
# MAGIC Job for new simulations.

# COMMAND ----------

dbutils.widgets.text("catalog", "monte_carlo_sim", "UC Catalog")
dbutils.widgets.text("schema", "hospital_data", "UC Schema")
dbutils.widgets.text("mc_job_id", "", "Monte Carlo Job ID")
dbutils.widgets.text("principal", "account users", "Grant Execute To")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
mc_job_id = dbutils.widgets.get("mc_job_id")
principal = dbutils.widgets.get("principal")

print(f"Target     : {catalog}.{schema}")
print(f"MC Job ID  : {mc_job_id or '(not set — will use placeholder)'}")
print(f"Principal  : {principal}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Register UC Functions

# COMMAND ----------

from src.databricks.sql.functions.monte_carlo.registry import MonteCarloRegistry

registry = MonteCarloRegistry(
    catalog=catalog,
    schema=schema,
    mc_job_id=mc_job_id or "{{MC_JOB_ID}}",
)

registration_stmts = registry.get_all_registration_sql()

print(f"Registering {len(registration_stmts)} UC function(s)...\n")

for i, sql in enumerate(registration_stmts, 1):
    print(f"  [{i}/{len(registration_stmts)}] Registering function ... ", end="")
    spark.sql(sql)
    print("done.")

print(f"\nAll {len(registration_stmts)} function(s) registered.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Grant Execute Permissions

# COMMAND ----------

grant_stmts = registry.get_all_grant_sql(principal=principal)

print(f"Granting EXECUTE to '{principal}'...\n")

for i, sql in enumerate(grant_stmts, 1):
    print(f"  [{i}/{len(grant_stmts)}] {sql.strip()}")
    spark.sql(sql)

print("\nGrants applied.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify — Describe Function

# COMMAND ----------

display(spark.sql(f"DESCRIBE FUNCTION {catalog}.{schema}.run_simulation"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Notes
# MAGIC
# MAGIC - If the `mc_job_id` widget was left empty, the function body contains the
# MAGIC   placeholder `{{MC_JOB_ID}}`. You must update it once the Databricks Job is
# MAGIC   created (see the jobs notebook).
# MAGIC - Re-run this notebook with the correct `mc_job_id` to update the function.

# COMMAND ----------

print("UC function registration complete.")
