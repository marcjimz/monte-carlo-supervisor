# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # 08 — Configure App
# MAGIC
# MAGIC Final orchestration task that closes the deployment loop:
# MAGIC 1. Reads dynamic IDs from upstream taskValues (Genie Space, MAS endpoint, warehouse)
# MAGIC 2. Looks up the app's service principal and Lakebase endpoint host
# MAGIC 3. Grants the app SP access to the Lakebase project
# MAGIC 4. Updates the app's environment variables with all resolved values
# MAGIC 5. Triggers an app restart so the new config takes effect
# MAGIC
# MAGIC **Dependencies**: `configure_genie`, `create_supervisor`, `fit_distributions`, `register_functions`

# COMMAND ----------

dbutils.widgets.text("catalog", "lakebase_hls_workshop_catalog", "UC Catalog")
dbutils.widgets.text("schema", "hospital_data", "UC Schema")
dbutils.widgets.text("app_name", "monte-carlo-ui", "App Name")
dbutils.widgets.text("lakebase_project", "monte-carlo-app", "Lakebase Project")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
app_name = dbutils.widgets.get("app_name")
lakebase_project = dbutils.widgets.get("lakebase_project")

print(f"Catalog          : {catalog}")
print(f"Schema           : {schema}")
print(f"App Name         : {app_name}")
print(f"Lakebase Project : {lakebase_project}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Auth Setup

# COMMAND ----------

import json
import time

import requests

_ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
host = _ctx.apiUrl().get()
token = _ctx.apiToken().get()
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

print(f"Workspace: {host}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Read Dynamic IDs from Upstream Tasks

# COMMAND ----------

def _get_task_value(task_key: str, key: str, fallback: str = "") -> str:
    """Read a taskValue from an upstream job task, with fallback."""
    try:
        return dbutils.jobs.taskValues.get(taskKey=task_key, key=key)
    except Exception as e:
        print(f"  WARNING: Could not read {task_key}.{key}: {e}")
        return fallback


genie_space_id = _get_task_value("configure_genie", "genie_space_id")
warehouse_id = _get_task_value("configure_genie", "warehouse_id")
mas_endpoint_name = _get_task_value("create_supervisor", "mas_endpoint_name")

print(f"Genie Space ID    : {genie_space_id}")
print(f"Warehouse ID      : {warehouse_id}")
print(f"MAS Endpoint Name : {mas_endpoint_name}")

if not genie_space_id or not mas_endpoint_name:
    raise RuntimeError(
        "Missing required taskValues. Ensure configure_genie and create_supervisor "
        "tasks completed successfully before running this task."
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Look Up App Service Principal

# COMMAND ----------

print(f"Looking up app: {app_name}")
app_resp = requests.get(f"{host}/api/2.0/apps/{app_name}", headers=headers)
app_resp.raise_for_status()
app_data = app_resp.json()

sp_client_id = app_data.get("service_principal_client_id", "")
source_code_path = (
    app_data.get("active_deployment", {}).get("source_code_path", "")
    or app_data.get("default_source_code_path", "")
)

print(f"App SP Client ID  : {sp_client_id}")
print(f"Source Code Path  : {source_code_path}")

if not sp_client_id:
    raise RuntimeError(
        f"App '{app_name}' has no service_principal_client_id. "
        "Ensure the app was created via 'databricks bundle deploy'."
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Look Up Lakebase Endpoint Host

# COMMAND ----------

print(f"Looking up Lakebase endpoint: {lakebase_project}/production/primary")
lb_resp = requests.get(
    f"{host}/api/2.0/postgres/projects/{lakebase_project}/branches/production/endpoints/primary",
    headers=headers,
)
lb_resp.raise_for_status()
lb_data = lb_resp.json()

pg_host = lb_data.get("status", {}).get("hosts", {}).get("host", "")
print(f"Lakebase Host     : {pg_host}")

if not pg_host:
    print("WARNING: Lakebase endpoint host is empty. The endpoint may still be provisioning.")
    print(f"Full response: {json.dumps(lb_data, indent=2)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Grant App SP Access to Lakebase
# MAGIC
# MAGIC Uses the Databricks permissions API to grant the app's service principal
# MAGIC `CAN_MANAGE` on the Lakebase project.

# COMMAND ----------

print(f"Granting SP {sp_client_id} access to Lakebase project {lakebase_project}...")

grant_resp = requests.patch(
    f"{host}/api/2.0/permissions/postgres-projects/{lakebase_project}",
    headers=headers,
    json={
        "access_control_list": [
            {
                "service_principal_name": sp_client_id,
                "all_permissions": [{"permission_level": "CAN_MANAGE"}],
            }
        ]
    },
)

if grant_resp.ok:
    print("  Lakebase permission granted successfully.")
else:
    print(f"  WARNING: Permission grant returned {grant_resp.status_code}: {grant_resp.text}")
    print("  The app may still work if permissions were granted via resource binding.")
    print("  If the app cannot connect to Lakebase, manually grant access:")
    print(f"    SP: {sp_client_id}")
    print(f"    Project: {lakebase_project}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Lakebase Database & Postgres Role for App SP
# MAGIC
# MAGIC The workspace permission grant (`CAN_MANAGE`) lets the SP call the Lakebase API,
# MAGIC but Postgres also needs an internal role for the SP to authenticate via OAuth.
# MAGIC We use the REST API (`POST .../roles`) and psycopg2 for database creation.

# COMMAND ----------

# --- Step 1: Create Postgres role for the SP via REST API ---
print(f"Creating Postgres role for SP {sp_client_id}...")

role_resp = requests.post(
    f"{host}/api/2.0/postgres/projects/{lakebase_project}/branches/production/roles",
    headers=headers,
    json={
        "spec": {
            "identity_type": "SERVICE_PRINCIPAL",
            "postgres_role": sp_client_id,
        }
    },
)

if role_resp.ok:
    # This returns a long-running operation — poll until done
    op = role_resp.json()
    op_name = op.get("name", "")
    print(f"  Role creation started (operation: {op_name})")

    # Poll the operation
    for i in range(20):
        time.sleep(5)
        if op_name:
            check = requests.get(f"{host}/api/2.0/postgres/{op_name}", headers=headers)
            if check.ok and check.json().get("done"):
                print("  Postgres role created successfully.")
                break
        else:
            # No operation name means it completed synchronously
            print("  Postgres role created (sync).")
            break
    else:
        print("  WARNING: Role creation still in progress after 100s.")
elif role_resp.status_code == 409:
    print("  Postgres role already exists (OK).")
else:
    print(f"  WARNING: Role creation returned {role_resp.status_code}: {role_resp.text}")
    print("  Will attempt to continue — the role may already exist.")

# --- Step 2: Create the 'mcapp' database via psycopg2 ---
# The default database is 'databricks_postgres'; we need 'mcapp' for the app.
print("\nSetting up 'mcapp' database...")

import subprocess
subprocess.check_call(["pip", "install", "-q", "psycopg2-binary"])
import psycopg2

# Generate credential for the current user (notebook runner = project owner)
cred_resp = requests.post(
    f"{host}/api/2.0/postgres/credentials",
    headers=headers,
    json={"endpoint": f"projects/{lakebase_project}/branches/production/endpoints/primary"},
)
if not cred_resp.ok:
    print(f"  Credential generation failed: {cred_resp.status_code} {cred_resp.text}")
    print("  Trying SDK fallback...")
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    cred_token = w.postgres.generate_database_credential(
        endpoint=f"projects/{lakebase_project}/branches/production/endpoints/primary"
    ).token
else:
    cred_token = cred_resp.json().get("token", "")

# Get current user identity for the Postgres connection
_ctx2 = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
current_user = _ctx2.userName().get()

# Connect to default database
print(f"  Connecting to {pg_host} as {current_user}...")
conn = psycopg2.connect(
    host=pg_host,
    port=5432,
    dbname="databricks_postgres",
    user=current_user,
    password=cred_token,
    sslmode="require",
)
conn.autocommit = True
cur = conn.cursor()

# Create mcapp database if it doesn't exist
cur.execute("SELECT 1 FROM pg_database WHERE datname = 'mcapp'")
if not cur.fetchone():
    cur.execute("CREATE DATABASE mcapp")
    print("  Created database 'mcapp'.")
else:
    print("  Database 'mcapp' already exists.")

# Grant privileges to the app SP
cur.execute(f'GRANT ALL ON DATABASE mcapp TO "{sp_client_id}"')
print(f"  Granted database privileges to SP.")

cur.close()
conn.close()

# Now connect to mcapp and grant schema privileges
conn = psycopg2.connect(
    host=pg_host,
    port=5432,
    dbname="mcapp",
    user=current_user,
    password=cred_token,
    sslmode="require",
)
conn.autocommit = True
cur = conn.cursor()

cur.execute(f'GRANT ALL ON SCHEMA public TO "{sp_client_id}"')
cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "{sp_client_id}"')
print("  Granted schema privileges to SP.")

cur.close()
conn.close()
print("Lakebase setup complete.\n")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Update App Environment Variables

# COMMAND ----------

# Get the current app config to preserve the command
current_config = app_data.get("config", {})
current_command = current_config.get("command", [
    "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"
])

env_vars = [
    {"name": "UC_CATALOG", "value": catalog},
    {"name": "UC_SCHEMA", "value": schema},
    {"name": "MAS_ENDPOINT_NAME", "value": mas_endpoint_name},
    {"name": "GENIE_SPACE_ID", "value": genie_space_id},
    {"name": "SQL_WAREHOUSE_ID", "value": warehouse_id},
    {"name": "DASHBOARD_ID", "value": ""},
    {"name": "PGHOST", "value": pg_host},
    {"name": "PGPORT", "value": "5432"},
    {"name": "PGDATABASE", "value": "mcapp"},
    {"name": "PGUSER", "value": sp_client_id},
    {"name": "SEED_DEMO_DATA", "value": "true"},
]

print("Updating app environment variables:")
for ev in env_vars:
    val = ev["value"]
    display = val if len(val) < 40 else f"{val[:37]}..."
    print(f"  {ev['name']:25s} = {display}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Trigger App Restart
# MAGIC
# MAGIC Pass `env_vars` and `command` directly in the deployment body.
# MAGIC These override whatever is in `app.yaml` at the source path.
# MAGIC (API field is `env_vars`, not `env` — per SDK docs.)

# COMMAND ----------

# Get the source_code_path from the active deployment
refresh_resp = requests.get(f"{host}/api/2.0/apps/{app_name}", headers=headers)
refresh_resp.raise_for_status()
refreshed = refresh_resp.json()

source_code_path = (
    refreshed.get("active_deployment", {}).get("source_code_path", "")
    or refreshed.get("default_source_code_path", "")
)

if not source_code_path:
    _ctx2 = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
    username = _ctx2.userName().get()
    source_code_path = f"/Workspace/Users/{username}/.bundle/monte-carlo-supervisor/dev/files/app"

print(f"Source code path: {source_code_path}")

# Check if the app compute is started — if not, start it first
compute_state = refreshed.get("compute_status", {}).get("state", "UNKNOWN")
if compute_state != "ACTIVE":
    print(f"  App compute is {compute_state}, starting...")
    start_resp = requests.post(f"{host}/api/2.0/apps/{app_name}/start", headers=headers)
    if start_resp.ok:
        print("  Start request sent. Waiting for compute to become active...")
        for _ in range(20):
            time.sleep(15)
            check = requests.get(f"{host}/api/2.0/apps/{app_name}", headers=headers)
            if check.ok and check.json().get("compute_status", {}).get("state") == "ACTIVE":
                print("  Compute is ACTIVE.")
                break
    else:
        print(f"  WARNING: Start returned {start_resp.status_code}: {start_resp.text}")

print("Creating new deployment with env_vars...")

deploy_body = {
    "source_code_path": source_code_path,
    "mode": "SNAPSHOT",
    "env_vars": env_vars,
    "command": current_command,
}

deploy_resp = requests.post(
    f"{host}/api/2.0/apps/{app_name}/deployments",
    headers=headers,
    json=deploy_body,
)
if not deploy_resp.ok:
    print(f"  Deployment API error {deploy_resp.status_code}: {deploy_resp.text}")
    deploy_resp.raise_for_status()
else:
    deployment = deploy_resp.json()
    deployment_id = deployment.get("deployment_id", "unknown")
    # Verify env_vars were accepted
    dep_env = deployment.get("env_vars", [])
    print(f"Deployment created: {deployment_id}")
    print(f"  env_vars in response: {len(dep_env)} variables")
    if not dep_env:
        print("  WARNING: API returned no env_vars — they may not have been applied!")
    for ev in dep_env:
        print(f"    {ev.get('name', '?')}: {ev.get('value', '?')[:40]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Poll Until Running

# COMMAND ----------

print("Waiting for app to start...")
timeout_s = 600  # 10 minutes
poll_s = 15
elapsed = 0

while elapsed < timeout_s:
    try:
        status_resp = requests.get(f"{host}/api/2.0/apps/{app_name}", headers=headers)
        status_resp.raise_for_status()
        status_data = status_resp.json()
        app_status = status_data.get("app_status", {}).get("state", "UNKNOWN")
    except Exception as e:
        app_status = f"ERROR: {e}"

    print(f"  [{elapsed:>3}s] App status: {app_status}")

    if app_status in ("RUNNING", "DEPLOYED"):
        print(f"\nApp is {app_status} after {elapsed}s.")
        break

    if app_status in ("CRASHED", "FAILED"):
        print(f"\nERROR: App entered {app_status} state.")
        print("Check the app logs for details.")
        break

    time.sleep(poll_s)
    elapsed += poll_s
else:
    print(f"\nWARNING: App did not reach RUNNING within {timeout_s}s.")
    print(f"Last status: {app_status}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

# Build the app URL from the workspace host
workspace_id = host.split("//")[1].split(".")[0].replace("fevm-lakebase-hls-workshop", "")
app_url = f"https://{app_name}-*.databricksapps.com"

# Try to get the actual URL from the app status
try:
    status_resp = requests.get(f"{host}/api/2.0/apps/{app_name}", headers=headers)
    if status_resp.ok:
        app_info = status_resp.json()
        actual_url = app_info.get("url", app_url)
        if actual_url:
            app_url = actual_url
except Exception:
    pass

print("=" * 60)
print("App Configuration Complete")
print("=" * 60)
print()
print(f"  App Name         : {app_name}")
print(f"  App URL          : {app_url}")
print(f"  App SP           : {sp_client_id}")
print(f"  Genie Space      : {genie_space_id}")
print(f"  MAS Endpoint     : {mas_endpoint_name}")
print(f"  SQL Warehouse    : {warehouse_id}")
print(f"  Lakebase Host    : {pg_host}")
print(f"  Catalog          : {catalog}")
print(f"  Schema           : {schema}")
print()
print("The app should now be fully functional.")
print("Open the URL above to verify.")
