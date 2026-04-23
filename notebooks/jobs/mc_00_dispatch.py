# Databricks notebook source
# MAGIC %md
# MAGIC # MC 00 — Dispatch
# MAGIC Reads job parameters first (from jobs.run_now). Falls back to picking
# MAGIC up the matching SUBMITTED row from simulation_runs for status tracking.

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

import hashlib
import json
from datetime import datetime, timezone

table = f"{catalog}.{schema}.simulation_runs"
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

sim_type = dbutils.widgets.get("simulation_type")

if sim_type:
    # --- Job-parameter mode (from jobs.run_now with job_parameters) ---
    parameters_json = dbutils.widgets.get("parameters")
    seed = dbutils.widgets.get("seed")
    num_sims = dbutils.widgets.get("num_simulations")

    # Compute params_hash to find the matching SUBMITTED row
    canonical = json.dumps(json.loads(parameters_json), sort_keys=True, separators=(",", ":"))
    payload = f"{sim_type}|{canonical}|{seed}|{num_sims}|default"
    params_hash = hashlib.sha256(payload.encode()).hexdigest()

    # Try to find and claim the matching SUBMITTED row
    submitted = spark.sql(f"""
        SELECT run_id FROM {table}
        WHERE params_hash = '{params_hash}' AND status = 'SUBMITTED'
        ORDER BY created_at DESC LIMIT 1
    """).collect()

    if submitted:
        run_id = submitted[0].run_id
        spark.sql(f"""
            UPDATE {table}
            SET status = 'RUNNING', updated_at = '{now}'
            WHERE run_id = '{run_id}'
        """)
        print(f"Job-parameter mode: claimed SUBMITTED run_id={run_id}")
        dbutils.jobs.taskValues.set(key="dispatch_mode", value="table_trigger")
        dbutils.jobs.taskValues.set(key="run_id", value=run_id)
        dbutils.jobs.taskValues.set(key="params_hash", value=params_hash)
    else:
        print(f"Job-parameter mode: no matching SUBMITTED row (will create new run)")
        dbutils.jobs.taskValues.set(key="dispatch_mode", value="manual")

    dbutils.jobs.taskValues.set(key="simulation_type", value=sim_type)
    dbutils.jobs.taskValues.set(key="parameters", value=parameters_json)
    dbutils.jobs.taskValues.set(key="seed", value=seed)
    dbutils.jobs.taskValues.set(key="num_simulations", value=num_sims)

else:
    # --- No job parameters — pick up oldest SUBMITTED row ---
    submitted = spark.sql(f"""
        SELECT * FROM {table}
        WHERE status = 'SUBMITTED'
        ORDER BY created_at ASC LIMIT 1
    """).collect()

    if not submitted:
        print("No SUBMITTED rows and no job parameters — nothing to dispatch.")
        dbutils.notebook.exit('{"dispatched": false, "reason": "no_work"}')

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

# COMMAND ----------

dbutils.notebook.exit('{"dispatched": true}')
