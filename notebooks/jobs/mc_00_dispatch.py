# Databricks notebook source
# MAGIC %md
# MAGIC # MC 00 — Dispatch
# MAGIC Picks up SUBMITTED rows from simulation_runs (table-trigger mode)
# MAGIC or reads from job parameters (manual mode).

# COMMAND ----------

dbutils.widgets.text("catalog", "monte_carlo_supervisor_catalog", "UC Catalog")
dbutils.widgets.text("schema", "hospital_data", "UC Schema")
dbutils.widgets.text("simulation_type", "", "Simulation Type")
dbutils.widgets.text("parameters", "{}", "Parameters JSON")
dbutils.widgets.text("num_simulations", "10000", "Num Simulations")
dbutils.widgets.text("seed", "42", "Random Seed")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

# COMMAND ----------

from datetime import datetime, timezone

table = f"{catalog}.{schema}.simulation_runs"
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

submitted = spark.sql(f"""
    SELECT * FROM {table}
    WHERE status = 'SUBMITTED'
    ORDER BY created_at ASC
    LIMIT 1
""").collect()

if submitted:
    row = submitted[0]
    print(f"Table-trigger mode: dispatching run_id={row.run_id}")
    spark.sql(f"""
        UPDATE {table}
        SET status = 'RUNNING', updated_at = '{now}'
        WHERE run_id = '{row.run_id}'
    """)
    dbutils.jobs.taskValues.set(key="dispatch_mode", value="table_trigger")
    dbutils.jobs.taskValues.set(key="run_id", value=row.run_id)
    dbutils.jobs.taskValues.set(key="simulation_type", value=row.simulation_type)
    dbutils.jobs.taskValues.set(key="parameters", value=row.parameters)
    dbutils.jobs.taskValues.set(key="seed", value=str(row.seed))
    dbutils.jobs.taskValues.set(key="num_simulations", value=str(row.num_simulations))
    dbutils.jobs.taskValues.set(key="params_hash", value=row.params_hash)
else:
    sim_type = dbutils.widgets.get("simulation_type")
    if not sim_type:
        print("No SUBMITTED rows and no job parameters — nothing to dispatch.")
        dbutils.notebook.exit('{"dispatched": false, "reason": "no_work"}')
    print(f"Manual mode: dispatching simulation_type={sim_type}")
    dbutils.jobs.taskValues.set(key="dispatch_mode", value="manual")
    dbutils.jobs.taskValues.set(key="simulation_type", value=sim_type)
    dbutils.jobs.taskValues.set(key="parameters", value=dbutils.widgets.get("parameters"))
    dbutils.jobs.taskValues.set(key="seed", value=dbutils.widgets.get("seed"))
    dbutils.jobs.taskValues.set(key="num_simulations", value=dbutils.widgets.get("num_simulations"))

# COMMAND ----------

dbutils.notebook.exit('{"dispatched": true}')
