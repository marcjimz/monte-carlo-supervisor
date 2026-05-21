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

import os, re
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

def _run_simple_sql(sql_path, catalog, schema):
    """Run a SQL file with simple CREATE VIEW statements."""
    sql_text = sql_path.read_text()
    # Set catalog/schema context
    spark.sql(f"USE CATALOG {catalog}")
    spark.sql(f"USE SCHEMA {schema}")
    # Strip USE CATALOG/SCHEMA and parameter comments, then run each statement
    for stmt in sql_text.split(";"):
        stmt = stmt.strip()
        if not stmt or stmt.startswith("--"):
            continue
        if stmt.upper().startswith("USE CATALOG") or stmt.upper().startswith("USE SCHEMA"):
            continue
        spark.sql(stmt)

# COMMAND ----------

base_views_path = _find_sql("infra/sql/create_base_views.sql")
print(f"Running: {base_views_path}")
_run_simple_sql(base_views_path, catalog, schema)
print("Base views created.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Execute Metric Views SQL

# COMMAND ----------

metric_views_path = _find_sql("infra/sql/create_metric_views.sql")
print(f"Running: {metric_views_path}")

# The metric views SQL uses DECLARE/SET VAR/EXECUTE IMMEDIATE which only
# works on SQL Warehouses, not via spark.sql(). Extract the view DDL
# strings and execute them directly.
sql_text = metric_views_path.read_text()

# Replace :catalog and :schema with actual values in the concatenation context
# The SQL has patterns like: "CREATE ... " || :catalog || "." || :schema || ".view_name ..."
# After replacement: "CREATE ... " || 'actual_catalog' || "." || 'actual_schema' || ".view_name ..."
sql_text = sql_text.replace(":catalog", f"'{catalog}'").replace(":schema", f"'{schema}'")

# Extract the DDL strings from SET VAR statements and execute them
# Pattern: SET VAR qry_N = "CREATE OR REPLACE VIEW ...$$";
pattern = r'SET\s+VAR\s+\w+\s*=\s*\n?\s*(".*?")\s*;'
matches = re.findall(pattern, sql_text, re.DOTALL)

for i, match in enumerate(matches, 1):
    # The match is a SQL string concatenation like "..." || 'catalog' || "..." etc.
    # Evaluate the concatenation by replacing || with Python +
    # The pieces are: "string" || 'value' || "string" ...
    parts = [p.strip().strip('"').strip("'") for p in match.split("||")]
    ddl = "".join(parts)
    print(f"  Creating metric view {i}...")
    try:
        spark.sql(ddl)
    except Exception as e:
        # project_accelerate_encounters may not exist in demo deployments
        if "TABLE_OR_VIEW_NOT_FOUND" in str(e) or "does not exist" in str(e).lower():
            print(f"  Skipped (source table not found): {e}")
        else:
            raise

print("Metric views created.")
