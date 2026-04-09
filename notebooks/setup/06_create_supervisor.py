# Databricks notebook source
# MAGIC %pip install "databricks-tools-core @ git+https://github.com/databricks-solutions/ai-dev-kit.git#subdirectory=databricks-tools-core" --quiet
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC # 06 — Create Multi-Agent Supervisor
# MAGIC
# MAGIC Programmatically creates the Agent Bricks Multi-Agent Supervisor (MAS) using
# MAGIC `AgentBricksManager` from `databricks-tools-core`.
# MAGIC
# MAGIC The MAS routes questions between:
# MAGIC - **encounter_analytics** (Genie Space) — historical data queries
# MAGIC - **simulation_checker** (UC Function) — check cached simulation results
# MAGIC - **simulation_trigger** (UC Function) — trigger new simulation jobs
# MAGIC
# MAGIC Retrieves the `genie_space_id` from the previous task via `dbutils.jobs.taskValues`.

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
# MAGIC ## Get Genie Space ID from Previous Task

# COMMAND ----------

try:
    genie_space_id = dbutils.jobs.taskValues.get(
        taskKey="configure_genie", key="genie_space_id"
    )
    print(f"Genie Space ID: {genie_space_id}")
except Exception as e:
    print(f"Could not get task value: {e}")
    print("Attempting to find Genie Space by name...")
    from databricks_tools_core.agent_bricks import AgentBricksManager as _mgr
    _m = _mgr()
    existing = _m.genie_find_by_name("Hospital Encounter Analytics")
    if existing:
        genie_space_id = existing.space_id
        print(f"Found Genie Space: {genie_space_id}")
    else:
        raise RuntimeError("Genie Space not found. Run notebook 05 first.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load Supervisor Configuration

# COMMAND ----------

from src.databricks.agentbricks.supervisor import (
    SUPERVISOR_NAME,
    SUPERVISOR_DESCRIPTION,
    SUPERVISOR_INSTRUCTIONS,
    get_supervisor_agents,
)
from src.databricks.agentbricks.examples import get_supervisor_examples

agents = get_supervisor_agents(genie_space_id, catalog, schema)
examples = get_supervisor_examples()

print(f"Supervisor : {SUPERVISOR_NAME}")
print(f"Agents     : {len(agents)}")
print(f"Examples   : {len(examples)}")
print()
for agent in agents:
    print(f"  {agent['name']} ({agent['agent_type']})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create or Update MAS

# COMMAND ----------

from databricks_tools_core.agent_bricks import AgentBricksManager

manager = AgentBricksManager()

def _extract_tile_id(response: dict) -> str:
    """Extract tile_id from mas_create/mas_get response (handles nested structure)."""
    # Try flat key first
    if "tile_id" in response:
        return response["tile_id"]
    # Try nested path: multi_agent_supervisor -> tile -> tile_id
    mas_obj = response.get("multi_agent_supervisor", {})
    tile = mas_obj.get("tile", {})
    if "tile_id" in tile:
        return tile["tile_id"]
    # Last resort — search recursively
    import json
    raise KeyError(f"Cannot find tile_id in response: {json.dumps(response, default=str)[:500]}")


# Check for existing MAS
existing = manager.mas_find_by_name(SUPERVISOR_NAME)
if existing:
    print(f"Found existing MAS: {existing}")
    tile_id = existing.tile_id
    manager.mas_update(
        tile_id=tile_id,
        name=SUPERVISOR_NAME,
        description=SUPERVISOR_DESCRIPTION,
        instructions=SUPERVISOR_INSTRUCTIONS,
        agents=agents,
    )
    print(f"MAS updated: {tile_id}")
else:
    print("Creating new MAS...")
    mas = manager.mas_create(
        name=SUPERVISOR_NAME,
        agents=agents,
        description=SUPERVISOR_DESCRIPTION,
        instructions=SUPERVISOR_INSTRUCTIONS,
    )
    print(f"MAS create response keys: {list(mas.keys()) if isinstance(mas, dict) else type(mas)}")
    tile_id = _extract_tile_id(mas)
    print(f"MAS created: {tile_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Add Training Examples

# COMMAND ----------

print(f"Adding {len(examples)} training examples...")

manager.mas_add_examples_batch(tile_id, examples)

print("Training examples added.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Wait for Endpoint to Come Online

# COMMAND ----------

import time


def _get_endpoint_status(mgr, tid: str) -> str:
    """Get endpoint status, handling both API variants."""
    # Try mas_get_endpoint_status first (if it exists)
    if hasattr(mgr, "mas_get_endpoint_status"):
        return mgr.mas_get_endpoint_status(tid)
    # Fall back to mas_get and extract from nested response
    resp = mgr.mas_get(tid)
    if isinstance(resp, dict):
        mas_obj = resp.get("multi_agent_supervisor", resp)
        status_obj = mas_obj.get("status", {})
        return status_obj.get("endpoint_status", "UNKNOWN")
    return "UNKNOWN"


print("Waiting for MAS endpoint to come online...")
print("(This may take several minutes while the serving endpoint provisions.)\n")

timeout_s = 600  # 10 minutes
poll_interval_s = 10
elapsed = 0
status = "UNKNOWN"

while elapsed < timeout_s:
    try:
        status = _get_endpoint_status(manager, tile_id)
    except Exception as e:
        status = f"ERROR: {e}"
    print(f"  [{elapsed:>3}s] Endpoint status: {status}")

    if status == "ONLINE":
        print(f"\nEndpoint is ONLINE after {elapsed}s.")
        break

    time.sleep(poll_interval_s)
    elapsed += poll_interval_s
else:
    print(f"\nWARNING: Endpoint did not reach ONLINE within {timeout_s}s.")
    print(f"Last status: {status}")
    print("The endpoint may still be provisioning. Check the workspace UI.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

print("=" * 60)
print("Multi-Agent Supervisor Setup Complete")
print("=" * 60)
print()
print(f"  Supervisor : {SUPERVISOR_NAME}")
print(f"  Tile ID    : {tile_id}")
print(f"  Agents     : {', '.join(a['name'] for a in agents)}")
print(f"  Examples   : {len(examples)}")
print()
print("Test the supervisor with questions like:")
print('  - "Show me total ER encounters by month"')
print('  - "Forecast ER patient volumes for the next 90 days"')
print('  - "What if we add 50 beds?"')
