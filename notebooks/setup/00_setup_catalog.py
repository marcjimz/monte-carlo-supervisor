# Databricks notebook source
# MAGIC %md
# MAGIC # 00 — Setup Unity Catalog & Schema
# MAGIC
# MAGIC Creates the Unity Catalog catalog and schema used by the Monte Carlo Supervisor project.
# MAGIC Run this notebook first before any other setup notebook.

# COMMAND ----------

dbutils.widgets.text("catalog", "monte_carlo_sim", "UC Catalog")
dbutils.widgets.text("schema", "hospital_data", "UC Schema")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

print(f"Catalog : {catalog}")
print(f"Schema  : {schema}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Catalog

# COMMAND ----------

spark.sql(f"CREATE CATALOG IF NOT EXISTS {catalog}")
print(f"Catalog '{catalog}' is ready.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Set Active Catalog & Create Schema

# COMMAND ----------

spark.sql(f"USE CATALOG {catalog}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {schema}")
spark.sql(f"USE SCHEMA {schema}")

print(f"Schema '{catalog}.{schema}' is ready.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify

# COMMAND ----------

display(spark.sql(f"SHOW SCHEMAS IN {catalog}"))
print("Setup complete.")
