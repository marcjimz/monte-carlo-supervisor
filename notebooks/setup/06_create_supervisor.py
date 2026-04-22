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

dbutils.widgets.text("catalog", "lakebase_hls_workshop_catalog", "UC Catalog")
dbutils.widgets.text("schema", "hospital_data", "UC Schema")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

print(f"Catalog : {catalog}")
print(f"Schema  : {schema}")

# COMMAND ----------

# Install project package from bundled wheel
import subprocess, sys
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_root = "/Workspace" + "/".join(_nb.split("/")[:-3])
subprocess.check_call([sys.executable, "-m", "pip", "install", f"{_root}/dist/monte_carlo_supervisor-1.0.0-py3-none-any.whl", "-q", "--disable-pip-version-check"])

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
    existing = _m.genie_find_by_name("Women's Health Analytics")
    if existing:
        genie_space_id = existing.space_id
        print(f"Found Genie Space: {genie_space_id}")
    else:
        raise RuntimeError("Genie Space not found. Run notebook 05 first.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load Supervisor Configuration

# COMMAND ----------

from mc_supervisor.agentbricks.supervisor import (
    SUPERVISOR_NAME,
    SUPERVISOR_DESCRIPTION,
    get_supervisor_instructions,
    get_supervisor_agents,
)
from mc_supervisor.agentbricks.examples import get_supervisor_examples

agents = get_supervisor_agents(genie_space_id, catalog, schema)
supervisor_instructions = get_supervisor_instructions()
examples = get_supervisor_examples()

print(f"Supervisor : {SUPERVISOR_NAME}")
print(f"Agents     : {len(agents)}")
print(f"Examples   : {len(examples)}")
print()
for agent in agents:
    print(f"  {agent['name']} ({agent['agent_type']})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Clean Up Old MAS + Create/Update New MAS

# COMMAND ----------

from databricks_tools_core.agent_bricks import AgentBricksManager

manager = AgentBricksManager()

# --- Clean up old MAS from previous version (Hospital-Monte-Carlo-Supervisor) ---
_OLD_MAS_NAME = "Hospital-Monte-Carlo-Supervisor"
old_mas = manager.mas_find_by_name(_OLD_MAS_NAME)
if old_mas:
    print(f"Found old MAS '{_OLD_MAS_NAME}' (tile_id={old_mas.tile_id}). Deleting...")
    try:
        manager.mas_delete(old_mas.tile_id)
        print(f"  Deleted old MAS '{_OLD_MAS_NAME}'.")
    except Exception as e:
        print(f"  Warning deleting old MAS: {e}")
else:
    print(f"No old MAS '{_OLD_MAS_NAME}' found. Nothing to clean up.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create or Update MAS

# COMMAND ----------

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
        instructions=supervisor_instructions,
        agents=agents,
    )
    print(f"MAS updated: {tile_id}")
else:
    print("Creating new MAS...")
    mas = manager.mas_create(
        name=SUPERVISOR_NAME,
        agents=agents,
        description=SUPERVISOR_DESCRIPTION,
        instructions=supervisor_instructions,
    )
    print(f"MAS create response keys: {list(mas.keys()) if isinstance(mas, dict) else type(mas)}")
    tile_id = _extract_tile_id(mas)
    print(f"MAS created: {tile_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Wait for Endpoint to Come Online
# MAGIC
# MAGIC After create/update, the endpoint may reprovision. We wait for ONLINE with
# MAGIC an initial settle delay to avoid acting on stale status.

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

# Allow the API to process the create/update before polling
time.sleep(5)

timeout_s = 600  # 10 minutes
poll_interval_s = 10
elapsed = 0
status = "UNKNOWN"
saw_non_online = False

while elapsed < timeout_s:
    try:
        status = _get_endpoint_status(manager, tile_id)
    except Exception as e:
        status = f"ERROR: {e}"
    print(f"  [{elapsed:>3}s] Endpoint status: {status}")

    if status != "ONLINE":
        saw_non_online = True

    if status == "ONLINE" and (saw_non_online or elapsed >= 10):
        # Only trust ONLINE if we either saw it go through a non-ONLINE state
        # (confirming a reprovision cycle) or enough time has passed.
        print(f"\nEndpoint is ONLINE after {elapsed}s.")
        # Output endpoint name for downstream tasks (08_configure_app)
        endpoint_name = f"mas-{tile_id}-endpoint"
        dbutils.jobs.taskValues.set(key="mas_endpoint_name", value=endpoint_name)
        print(f"  Endpoint name: {endpoint_name}")
        break

    time.sleep(poll_interval_s)
    elapsed += poll_interval_s
else:
    print(f"\nWARNING: Endpoint did not reach ONLINE within {timeout_s}s.")
    print(f"Last status: {status}")
    print("The endpoint may still be provisioning. Check the workspace UI.")
    # Still output the endpoint name so downstream tasks can reference it
    endpoint_name = f"mas-{tile_id}-endpoint"
    dbutils.jobs.taskValues.set(key="mas_endpoint_name", value=endpoint_name)
    print(f"  Endpoint name (may not be ready): {endpoint_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Wait for Internal Resources
# MAGIC
# MAGIC The serving endpoint reaches ONLINE before the internal MAS resources
# MAGIC (example storage, agent registry) are fully ready.  If we add examples
# MAGIC during this window they are silently dropped.  Poll `mas_list_examples`
# MAGIC until it stops returning INTERNAL_ERROR — that confirms the MAS is truly
# MAGIC ready to accept examples.

# COMMAND ----------

print("Waiting for MAS internal resources to become ready...")
print("(Endpoint is ONLINE but example storage may still be initializing.)\n")

internal_timeout_s = 600  # 10 minutes
internal_poll_s = 15
internal_elapsed = 0
internal_ready = False

while internal_elapsed < internal_timeout_s:
    try:
        _ = manager.mas_list_examples(tile_id)
        # If we get here without exception, internal resources are ready
        internal_ready = True
        print(f"  [{internal_elapsed:>3}s] Internal resources READY.")
        break
    except Exception as e:
        err_msg = str(e)
        if "INTERNAL_ERROR" in err_msg or "Failed to fetch" in err_msg:
            print(f"  [{internal_elapsed:>3}s] Still initializing...")
        else:
            # Different error — might be ready but with an unexpected response
            print(f"  [{internal_elapsed:>3}s] Unexpected: {err_msg[:100]}")
            internal_ready = True
            break
    time.sleep(internal_poll_s)
    internal_elapsed += internal_poll_s

if not internal_ready:
    print(f"\nWARNING: Internal resources not ready after {internal_timeout_s}s.")
    print("Examples may not persist. Check the MAS UI and re-run if needed.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Add Training Examples
# MAGIC
# MAGIC Clear existing examples first to avoid duplicates on re-runs, then add
# MAGIC the current set. Examples must be added **after** internal resources are ready.

# COMMAND ----------

# Clear existing examples to handle re-runs cleanly
try:
    existing_examples = manager.mas_list_examples(tile_id)
    existing_list = existing_examples.get("examples", [])
    if existing_list:
        print(f"Clearing {len(existing_list)} existing examples...")
        for ex in existing_list:
            ex_id = ex.get("example_id")
            if ex_id:
                try:
                    manager.mas_delete_example(tile_id, ex_id)
                except Exception as e:
                    print(f"  Warning deleting example {ex_id}: {e}")
        print("  Existing examples cleared.")
    else:
        print("No existing examples to clear.")
except Exception as e:
    print(f"Warning listing existing examples: {e}")

# Add fresh examples
print(f"\nAdding {len(examples)} training examples...")
added = manager.mas_add_examples_batch(tile_id, examples)
print(f"Training examples added: {len(added)}/{len(examples)} succeeded.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify Examples Persisted

# COMMAND ----------

verified_list = []
max_verify_attempts = 3
for attempt in range(1, max_verify_attempts + 1):
    try:
        verification = manager.mas_list_examples(tile_id)
        verified_list = verification.get("examples", [])
        print(f"Verification (attempt {attempt}): {len(verified_list)} examples found in MAS.")

        if len(verified_list) >= len(examples):
            # All examples present
            for ex in verified_list:
                q = ex.get("question", "?")[:60]
                print(f"  - {q}")
            break

        if len(verified_list) == 0 and attempt < max_verify_attempts:
            # Examples were silently dropped — re-add
            print(f"  Examples were dropped. Re-adding (attempt {attempt + 1})...")
            time.sleep(10)
            added = manager.mas_add_examples_batch(tile_id, examples)
            print(f"  Re-added: {len(added)}/{len(examples)} succeeded.")
            time.sleep(5)  # Brief settle before re-verify
        else:
            print(f"  WARNING: Expected {len(examples)} but found {len(verified_list)}.")
            for ex in verified_list:
                q = ex.get("question", "?")[:60]
                print(f"  - {q}")
            break

    except Exception as e:
        print(f"Verification attempt {attempt} error: {e}")
        if attempt < max_verify_attempts:
            time.sleep(10)

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
print(f"  Examples   : {len(added)} added, {len(verified_list)} verified")
print()
print("Test the supervisor with questions like:")
print('  - "What is the average cost per encounter for OB/GYN patients?"')
print('  - "Compare virtual vs in-person care costs for women\'s health"')
print('  - "Project the 5-year system cost ROI at 8% encounter reduction"')
