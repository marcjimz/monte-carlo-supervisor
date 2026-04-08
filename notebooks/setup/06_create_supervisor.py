# Databricks notebook source
# MAGIC %md
# MAGIC # 06 — Create Multi-Agent Supervisor
# MAGIC
# MAGIC Creates the Agent Bricks Multi-Agent Supervisor (MAS) that routes questions
# MAGIC between the Genie Space (historical analytics) and the Monte Carlo UC function
# MAGIC (simulations/forecasting).
# MAGIC
# MAGIC **Prerequisite:** The Genie Space must already be created (notebook 05) and
# MAGIC you need its Space ID.
# MAGIC
# MAGIC **Note:** This notebook requires the `databricks-agent-bricks` SDK package.

# COMMAND ----------

dbutils.widgets.text("catalog", "monte_carlo_sim", "UC Catalog")
dbutils.widgets.text("schema", "hospital_data", "UC Schema")
dbutils.widgets.text("genie_space_id", "", "Genie Space ID")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
genie_space_id = dbutils.widgets.get("genie_space_id")

print(f"Catalog        : {catalog}")
print(f"Schema         : {schema}")
print(f"Genie Space ID : {genie_space_id or '(not set)'}")

if not genie_space_id:
    print("\nWARNING: genie_space_id is required. Set it in the widget above.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Supervisor Configuration

# COMMAND ----------

from src.databricks.agentbricks.supervisor import get_supervisor_config
from src.databricks.agentbricks.examples import get_supervisor_examples

config = get_supervisor_config(genie_space_id, catalog, schema)

print(f"Supervisor Name : {config['name']}")
print(f"Description     : {config['description']}")
print(f"Agents          : {len(config['agents'])}")
print()

for agent in config["agents"]:
    print(f"  Agent: {agent['name']}")
    if "genie_space_id" in agent:
        print(f"    Type          : Genie Space")
        print(f"    Space ID      : {agent['genie_space_id']}")
    elif "uc_function_name" in agent:
        print(f"    Type          : UC Function")
        print(f"    Function      : {agent['uc_function_name']}")
    print(f"    Description   : {agent['description'][:80]}...")
    print()

print("Routing Instructions:")
print(config["instructions"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Routing Examples

# COMMAND ----------

examples = get_supervisor_examples()

print(f"Training examples ({len(examples)}):\n")
for i, ex in enumerate(examples, 1):
    print(f"  {i:>2}. Q: {ex['question']}")
    print(f"      -> {ex['guideline'][:100]}...")
    print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create the Supervisor
# MAGIC
# MAGIC The cell below creates the MAS using the Agent Bricks SDK.
# MAGIC Ensure `databricks-agent-bricks` is installed on your cluster.

# COMMAND ----------

assert genie_space_id, "Set the genie_space_id widget before running this cell."

from databricks_agent_bricks import manage_mas, mas_add_examples_batch

print("Creating Multi-Agent Supervisor...")

mas_response = manage_mas(action="create_or_update", config=config)
print(f"Supervisor created/updated: {mas_response}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Add Training Examples

# COMMAND ----------

print(f"Adding {len(examples)} training examples...")

examples_response = mas_add_examples_batch(
    supervisor_name=config["name"],
    examples=examples,
)
print(f"Examples added: {examples_response}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify

# COMMAND ----------

print("Multi-Agent Supervisor setup complete.")
print()
print(f"  Supervisor : {config['name']}")
print(f"  Agents     : {', '.join(a['name'] for a in config['agents'])}")
print(f"  Examples   : {len(examples)}")
print()
print("You can now test the supervisor by asking questions like:")
print('  - "Show me total ER encounters by month for 2024"')
print('  - "Forecast ER patient volumes for the next 90 days"')
print('  - "What was readmission rate last year, and simulate a 15% LOS reduction?"')

# COMMAND ----------

# MAGIC %md
# MAGIC ## Fallback: Manual Agent Bricks Setup
# MAGIC
# MAGIC If the `databricks-agent-bricks` SDK is not available, you can configure the
# MAGIC MAS manually using the Databricks UI:
# MAGIC
# MAGIC 1. Navigate to **Machine Learning > Agents** in the sidebar.
# MAGIC 2. Create a new **Multi-Agent Supervisor**.
# MAGIC 3. Set the name to `Hospital-Monte-Carlo-Supervisor`.
# MAGIC 4. Add two child agents:
# MAGIC    - **encounter_analytics** — point to the Genie Space created in notebook 05.
# MAGIC    - **monte_carlo_simulator** — point to the UC function `<catalog>.<schema>.run_simulation`.
# MAGIC 5. Paste the routing instructions from the config above.
# MAGIC 6. Add the training examples shown above.
