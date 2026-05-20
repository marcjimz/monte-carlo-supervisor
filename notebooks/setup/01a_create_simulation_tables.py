# Databricks notebook source
# COMMAND ----------
# MAGIC %md
# MAGIC # 01a — Create Simulation Tables
# MAGIC
# MAGIC Creates the four Monte Carlo simulation tables in the target
# MAGIC catalog/schema if they don't already exist.

# COMMAND ----------

dbutils.widgets.text("catalog", "monte_carlo_supervisor_catalog", "UC Catalog")
dbutils.widgets.text("schema", "hospital_data", "UC Schema")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

print(f"Target: {catalog}.{schema}")

# COMMAND ----------

spark.sql(f"USE CATALOG {catalog}")
spark.sql(f"USE SCHEMA {schema}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Tables

# COMMAND ----------

import os
from pathlib import Path

bundle_root = os.environ.get("BUNDLE_ROOT", "")
sql_candidates = []
if bundle_root:
    sql_candidates.append(Path(bundle_root) / "infra" / "sql" / "create_simulation_tables.sql")
sql_candidates.extend([
    Path("../../infra/sql/create_simulation_tables.sql"),
    Path("../infra/sql/create_simulation_tables.sql"),
])

sql_path = None
for p in sql_candidates:
    if p.exists():
        sql_path = p
        break

if sql_path:
    sql_text = sql_path.read_text()
    # Remove the USE CATALOG/SCHEMA lines (we already set them above)
    statements = [
        s.strip() for s in sql_text.split(";")
        if s.strip()
        and not s.strip().upper().startswith("USE CATALOG")
        and not s.strip().upper().startswith("USE SCHEMA")
        and not s.strip().startswith("--")
    ]
    for stmt in statements:
        # Skip pure comment blocks
        lines = [l for l in stmt.split("\n") if not l.strip().startswith("--")]
        clean = "\n".join(lines).strip()
        if clean:
            spark.sql(clean)
            # Extract table name for logging
            if "CREATE TABLE" in clean.upper():
                tbl = clean.split("EXISTS")[-1].strip().split("(")[0].strip() if "EXISTS" in clean else "?"
                print(f"Created table: {tbl}")
else:
    print("WARNING: create_simulation_tables.sql not found — creating inline")
    # Fallback: create tables inline
    spark.sql("""
    CREATE TABLE IF NOT EXISTS simulation_runs (
        run_id STRING NOT NULL, simulation_type STRING NOT NULL,
        parameters STRING NOT NULL, params_hash STRING NOT NULL,
        seed INT NOT NULL, num_simulations INT NOT NULL,
        status STRING NOT NULL, job_run_id STRING,
        created_at STRING NOT NULL, updated_at STRING NOT NULL
    ) USING DELTA
    """)
    print("Created table: simulation_runs")

print("Done.")
