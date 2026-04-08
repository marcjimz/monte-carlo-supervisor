# Databricks notebook source
# MAGIC %md
# MAGIC # 05 — Configure Genie Space
# MAGIC
# MAGIC Displays the Genie Space configuration for the Hospital Encounter Analytics space.
# MAGIC
# MAGIC **Note:** Programmatic Genie Space creation may not be available in all workspaces.
# MAGIC This notebook displays the full configuration and provides instructions for
# MAGIC manual setup via the Databricks UI.

# COMMAND ----------

dbutils.widgets.text("catalog", "monte_carlo_sim", "UC Catalog")
dbutils.widgets.text("schema", "hospital_data", "UC Schema")
dbutils.widgets.text("warehouse_id", "", "SQL Warehouse ID")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
warehouse_id = dbutils.widgets.get("warehouse_id")

print(f"Catalog      : {catalog}")
print(f"Schema       : {schema}")
print(f"Warehouse ID : {warehouse_id or '(not set)'}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Genie Space Configuration

# COMMAND ----------

from src.databricks.genie.space_config import get_genie_space_config
from src.databricks.genie.sample_questions import get_sample_questions

config = get_genie_space_config(catalog, schema)

# Override warehouse_id if provided
if warehouse_id:
    config["warehouse_id"] = warehouse_id

print(f"Display Name : {config['display_name']}")
print(f"Description  : {config['description']}")
print(f"Warehouse ID : {config['warehouse_id']}")
print(f"Tables       : {len(config['tables'])}")
print()
print("Instructions:")
print(config["instructions"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Table List
# MAGIC
# MAGIC The following tables should be added to the Genie Space.

# COMMAND ----------

print("Tables to include in the Genie Space:\n")
for i, table in enumerate(config["tables"], 1):
    print(f"  {i:>2}. {table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Sample Questions

# COMMAND ----------

sample_questions = get_sample_questions()

print(f"Sample questions ({len(sample_questions)}):\n")
for i, sq in enumerate(sample_questions, 1):
    print(f"  {i:>2}. {sq['question']}")
    print(f"      -> {sq['description']}")
    print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Manual Setup Instructions
# MAGIC
# MAGIC To create the Genie Space in the Databricks UI:
# MAGIC
# MAGIC 1. Navigate to **SQL > Genie Spaces** in the left sidebar.
# MAGIC 2. Click **New Genie Space**.
# MAGIC 3. Set the **Name** to: `Hospital Encounter Analytics`
# MAGIC 4. Set the **Description** to the text shown above.
# MAGIC 5. Select your **SQL Warehouse** from the dropdown.
# MAGIC 6. Add all **20 tables** listed above (12 data tables + 6 metric views + 2 simulation tables).
# MAGIC 7. Paste the **Instructions** text into the General Instructions field.
# MAGIC 8. Add the **Sample Questions** listed above.
# MAGIC 9. Click **Save**.
# MAGIC
# MAGIC After creation, copy the **Genie Space ID** from the URL — you will need it
# MAGIC for notebook `06_create_supervisor.py`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Programmatic Creation (Optional)
# MAGIC
# MAGIC If your workspace supports programmatic Genie Space creation via the SDK,
# MAGIC uncomment and run the cell below.

# COMMAND ----------

# NOTE: Uncomment the following block if programmatic creation is supported.
#
# from databricks.sdk import WorkspaceClient
#
# w = WorkspaceClient()
#
# # Create the Genie Space (API availability varies by workspace)
# try:
#     space = w.genie.create_space(
#         display_name=config["display_name"],
#         description=config["description"],
#         warehouse_id=config["warehouse_id"],
#         table_identifiers=config["tables"],
#     )
#     print(f"Genie Space created successfully!")
#     print(f"Space ID: {space.space_id}")
#     print(f"URL: Open the Genie Spaces page in your workspace to access it.")
# except Exception as e:
#     print(f"Programmatic creation not available: {e}")
#     print("Please follow the manual setup instructions above.")

# COMMAND ----------

print("Genie Space configuration complete.")
print("Record the Genie Space ID for use in notebook 06_create_supervisor.py.")
