# Databricks notebook source
# MAGIC %md
# MAGIC # 00 — Setup Unity Catalog & Schema
# MAGIC
# MAGIC Creates the Unity Catalog catalog and schema used by the Monte Carlo Supervisor project.
# MAGIC Run this notebook first before any other setup notebook.

# COMMAND ----------

dbutils.widgets.text("catalog", "lakebase_hls_workshop_catalog", "UC Catalog")
dbutils.widgets.text("schema", "hospital_data", "UC Schema")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

print(f"Catalog : {catalog}")
print(f"Schema  : {schema}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Catalog

# COMMAND ----------

try:
    spark.sql(f"CREATE CATALOG IF NOT EXISTS {catalog}")
    print(f"Catalog '{catalog}' created (or already existed).")
except Exception as e:
    err_msg = str(e).lower()
    if "already exists" in err_msg:
        print(f"Catalog '{catalog}' already exists — using it as-is.")
    elif "permission_denied" in err_msg or "unauthorized" in err_msg or "create catalog" in err_msg:
        # No CREATE CATALOG permission — catalog must already exist
        print(f"No CREATE CATALOG permission. Assuming '{catalog}' already exists.")
    elif "metastore storage root" in err_msg or "default storage" in err_msg:
        # Azure: Default Storage enabled but no metastore root — use external location
        print(f"Metastore has no storage root. Trying with MANAGED LOCATION...")
        try:
            rows = spark.sql("SHOW EXTERNAL LOCATIONS").collect()
            if rows:
                loc_url = rows[0]["url"].rstrip("/")
                managed_loc = f"{loc_url}/{catalog}"
                spark.sql(f"CREATE CATALOG IF NOT EXISTS {catalog} MANAGED LOCATION '{managed_loc}'")
                print(f"Catalog '{catalog}' created with managed location: {managed_loc}")
            else:
                raise RuntimeError("No external locations available for catalog storage.")
        except Exception as e2:
            if "already exists" in str(e2).lower():
                print(f"Catalog '{catalog}' already exists — using it as-is.")
            else:
                raise
    else:
        raise

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
