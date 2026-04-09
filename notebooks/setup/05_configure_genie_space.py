# Databricks notebook source
# MAGIC %pip install "databricks-tools-core @ git+https://github.com/databricks-solutions/ai-dev-kit.git#subdirectory=databricks-tools-core" --quiet
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC # 05 — Create Genie Space
# MAGIC
# MAGIC Programmatically creates the Genie Space for hospital encounter analytics
# MAGIC using `AgentBricksManager` from `databricks-tools-core`.
# MAGIC
# MAGIC Adds all 20 tables (12 data + 6 metric views + 2 simulation), configures
# MAGIC instructions, and adds sample questions.
# MAGIC
# MAGIC Passes the `genie_space_id` to the next task via `dbutils.jobs.taskValues`.

# COMMAND ----------

dbutils.widgets.text("catalog", "monte_carlo_sim", "UC Catalog")
dbutils.widgets.text("schema", "hospital_data", "UC Schema")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

print(f"Catalog : {catalog}")
print(f"Schema  : {schema}")

# COMMAND ----------

# Add bundle root to sys.path so `src` package is importable
import sys
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_root = "/Workspace" + "/".join(_nb.split("/")[:-3])
if _root not in sys.path:
    sys.path.insert(0, _root)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load Configuration

# COMMAND ----------

from src.databricks.genie.space_config import get_genie_space_config
from src.databricks.genie.sample_questions import get_sample_questions

config = get_genie_space_config(catalog, schema)
sample_questions = get_sample_questions()

print(f"Display Name : {config['display_name']}")
print(f"Description  : {config['description'][:80]}...")
print(f"Tables       : {len(config['tables'])}")
print(f"Questions    : {len(sample_questions)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Auto-Detect SQL Warehouse

# COMMAND ----------

from databricks_tools_core.agent_bricks import AgentBricksManager

manager = AgentBricksManager()

warehouse_id = manager.get_best_warehouse_id()
if not warehouse_id:
    raise RuntimeError(
        "No SQL warehouse found. Please ensure at least one SQL warehouse "
        "is running or available in this workspace."
    )

print(f"Using warehouse: {warehouse_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Check for Existing Genie Space

# COMMAND ----------

existing = manager.genie_find_by_name(config["display_name"])
if existing:
    print(f"Found existing Genie Space: {existing}")
    print("Updating existing space...")
    genie_space_id = existing.space_id
    manager.genie_update(
        space_id=genie_space_id,
        display_name=config["display_name"],
        description=config["description"],
        warehouse_id=warehouse_id,
        table_identifiers=config["tables"],
    )
    print(f"Genie Space updated: {genie_space_id}")
else:
    print("Creating new Genie Space...")
    space = manager.genie_create(
        display_name=config["display_name"],
        warehouse_id=warehouse_id,
        table_identifiers=config["tables"],
        description=config["description"],
    )
    genie_space_id = space["id"]
    print(f"Genie Space created: {genie_space_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Add Sample Questions

# COMMAND ----------

questions_text = [sq["question"] for sq in sample_questions]

print(f"Adding {len(questions_text)} sample questions...")
manager.genie_add_sample_questions_batch(genie_space_id, questions_text)
print("Sample questions added.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Pass Genie Space ID to Next Task

# COMMAND ----------

dbutils.jobs.taskValues.set(key="genie_space_id", value=genie_space_id)
dbutils.jobs.taskValues.set(key="warehouse_id", value=warehouse_id)

print(f"\nGenie Space setup complete.")
print(f"  Space ID    : {genie_space_id}")
print(f"  Warehouse   : {warehouse_id}")
print(f"  Tables      : {len(config['tables'])}")
print(f"  Questions   : {len(questions_text)}")
