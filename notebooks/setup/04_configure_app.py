# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # 04 — Configure App
# MAGIC
# MAGIC Runtime setup that cannot be expressed declaratively in DABs:
# MAGIC 1. Lakebase: create database, Postgres role, grant SP permissions
# MAGIC 2. Wire Genie Space ID as app env var
# MAGIC 3. Enable dashboard embedding and publish
# MAGIC 4. Restart app with updated config
# MAGIC
# MAGIC **Handled by DABs** (no longer done here):
# MAGIC - App env vars: catalog, schema, model endpoints, warehouse ID, job ID, dashboard ID
# MAGIC - Job permissions: `CAN_MANAGE_RUN` via app resource binding
# MAGIC - SQL Warehouse permissions: `CAN_USE` via app resource binding
# MAGIC
# MAGIC **Dependencies**: `deploy_genie`, `fit_distributions`

# COMMAND ----------

dbutils.widgets.text("catalog", "monte_carlo_supervisor_catalog", "UC Catalog")
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
    try:
        return dbutils.jobs.taskValues.get(taskKey=task_key, key=key)
    except Exception as e:
        print(f"  WARNING: Could not read {task_key}.{key}: {e}")
        return fallback


genie_space_id = _get_task_value("deploy_genie", "genie_space_id")
warehouse_id = _get_task_value("deploy_genie", "warehouse_id")

print(f"Genie Space ID    : {genie_space_id}")
print(f"Warehouse ID      : {warehouse_id}")

if not genie_space_id:
    print("WARNING: No Genie Space ID — agent chat analytics queries will be limited")

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
# MAGIC ## Lakebase Setup
# MAGIC
# MAGIC 1. Grant SP workspace-level access to the Lakebase project
# MAGIC 2. Create Postgres role for the SP (required for OAuth login)
# MAGIC 3. Create `mcapp` database and grant schema privileges

# COMMAND ----------

# --- Grant workspace-level Lakebase access ---
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
    print("  Lakebase permission granted.")
else:
    print(f"  WARNING: {grant_resp.status_code}: {grant_resp.text}")

# COMMAND ----------

# --- Look up Lakebase endpoint host ---
print(f"Looking up Lakebase endpoint: {lakebase_project}/production/primary")
lb_resp = requests.get(
    f"{host}/api/2.0/postgres/projects/{lakebase_project}/branches/production/endpoints/primary",
    headers=headers,
)
lb_resp.raise_for_status()
pg_host = lb_resp.json().get("status", {}).get("hosts", {}).get("host", "")
print(f"Lakebase Host     : {pg_host}")

# COMMAND ----------

# --- Create Postgres role for SP ---
print(f"Creating Postgres role for SP {sp_client_id}...")

role_resp = requests.post(
    f"{host}/api/2.0/postgres/projects/{lakebase_project}/branches/production/roles",
    headers=headers,
    json={"spec": {"identity_type": "SERVICE_PRINCIPAL", "postgres_role": sp_client_id}},
)

if role_resp.ok:
    op_name = role_resp.json().get("name", "")
    for i in range(20):
        time.sleep(5)
        if op_name:
            check = requests.get(f"{host}/api/2.0/postgres/{op_name}", headers=headers)
            if check.ok and check.json().get("done"):
                print("  Postgres role created.")
                break
        else:
            print("  Postgres role created (sync).")
            break
    else:
        print("  WARNING: Role creation still in progress after 100s.")
elif role_resp.status_code == 409:
    print("  Postgres role already exists (OK).")
else:
    print(f"  WARNING: {role_resp.status_code}: {role_resp.text}")

# COMMAND ----------

# --- Create mcapp database + grant privileges ---
print("Setting up 'mcapp' database...")

import subprocess
subprocess.check_call(["pip", "install", "-q", "psycopg2-binary"])
import psycopg2

cred_resp = requests.post(
    f"{host}/api/2.0/postgres/credentials",
    headers=headers,
    json={"endpoint": f"projects/{lakebase_project}/branches/production/endpoints/primary"},
)
if cred_resp.ok:
    cred_token = cred_resp.json().get("token", "")
else:
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    cred_token = w.postgres.generate_database_credential(
        endpoint=f"projects/{lakebase_project}/branches/production/endpoints/primary"
    ).token

current_user = _ctx.userName().get()

conn = psycopg2.connect(
    host=pg_host, port=5432, dbname="databricks_postgres",
    user=current_user, password=cred_token, sslmode="require",
)
conn.autocommit = True
cur = conn.cursor()

cur.execute("SELECT 1 FROM pg_database WHERE datname = 'mcapp'")
if not cur.fetchone():
    cur.execute("CREATE DATABASE mcapp")
    print("  Created database 'mcapp'.")
else:
    print("  Database 'mcapp' already exists.")

cur.execute(f'GRANT ALL ON DATABASE mcapp TO "{sp_client_id}"')
print("  Granted database privileges to SP.")
cur.close()
conn.close()

conn = psycopg2.connect(
    host=pg_host, port=5432, dbname="mcapp",
    user=current_user, password=cred_token, sslmode="require",
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
# MAGIC ## Grant Delta Table & Genie Space Permissions
# MAGIC
# MAGIC The app SP needs MODIFY on simulation tables (for trigger_simulation)
# MAGIC and CAN_MANAGE on the Genie Space (for agent analytics queries).

# COMMAND ----------

# --- Delta table grants ---
sim_tables = ["simulation_runs", "simulation_results"]
for table in sim_tables:
    fqn = f"{catalog}.{schema}.{table}"
    try:
        spark.sql(f"GRANT MODIFY ON TABLE {fqn} TO `{sp_client_id}`")
        print(f"  MODIFY on {fqn}: granted")
    except Exception as e:
        if "already has" in str(e).lower() or "ALREADY_EXISTS" in str(e):
            print(f"  MODIFY on {fqn}: already granted")
        else:
            print(f"  MODIFY on {fqn}: WARNING: {e}")

# --- Genie Space CAN_MANAGE ---
if genie_space_id:
    genie_perm_resp = requests.patch(
        f"{host}/api/2.0/permissions/genie/{genie_space_id}",
        headers=headers,
        json={
            "access_control_list": [
                {
                    "service_principal_name": sp_client_id,
                    "permission_level": "CAN_MANAGE",
                }
            ]
        },
    )
    print(f"  Genie CAN_MANAGE: {'granted' if genie_perm_resp.ok else f'WARNING: {genie_perm_resp.status_code}'}")
else:
    print("  Genie CAN_MANAGE: skipped (no Genie Space ID)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Dashboard: Enable Embedding & Publish
# MAGIC
# MAGIC Dashboard ID is now wired via DAB interpolation in `apps.yml`
# MAGIC (`${resources.dashboards.wh_analytics.id}`). We still need to enable
# MAGIC embedding and publish at runtime since DABs don't support these.

# COMMAND ----------

# Look up dashboard ID from the DAB-deployed resource
dashboard_display_name = "Women's Health Analytics"
dashboard_id = ""

print(f"Looking up dashboard: {dashboard_display_name}")
page_token = ""
while True:
    params = {"page_size": 100}
    if page_token:
        params["page_token"] = page_token
    dash_resp = requests.get(f"{host}/api/2.0/lakeview/dashboards", headers=headers, params=params)
    if not dash_resp.ok:
        print(f"  WARNING: {dash_resp.status_code}: {dash_resp.text}")
        break
    dash_data = dash_resp.json()
    for d in dash_data.get("dashboards", []):
        name = d.get("display_name", "")
        if name == dashboard_display_name or name.startswith(f"{dashboard_display_name} ["):
            dashboard_id = d.get("dashboard_id", "")
            print(f"  Found: {name} (ID: {dashboard_id})")
            break
    if dashboard_id:
        break
    page_token = dash_data.get("next_page_token", "")
    if not page_token:
        break

if not dashboard_id:
    print("  WARNING: Dashboard not found — embedding/publish skipped.")
else:
    # Enable embedding (workspace setting — idempotent)
    embed_resp = requests.patch(
        f"{host}/api/2.0/settings/types/aibi_dash_embed_ws_acc_policy/names/default",
        headers=headers,
        json={
            "allow_missing": True,
            "field_mask": "aibi_dashboard_embedding_access_policy.access_policy_type",
            "setting": {
                "setting_name": "default",
                "aibi_dashboard_embedding_access_policy": {
                    "access_policy_type": "ALLOW_ALL_DOMAINS"
                }
            }
        },
    )
    print(f"  Embedding: {'enabled' if embed_resp.ok else f'WARNING: {embed_resp.status_code}'}")

    # Publish
    pub_resp = requests.post(
        f"{host}/api/2.0/lakeview/dashboards/{dashboard_id}/published",
        headers=headers,
        json={"embed_credentials": True, "warehouse_id": warehouse_id},
    )
    print(f"  Publish: {'OK' if pub_resp.ok else f'WARNING: {pub_resp.status_code}'}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Update Dynamic Env Vars & Restart App
# MAGIC
# MAGIC Only env vars that can't be resolved at DAB deploy time.
# MAGIC Dashboard ID is now DAB-resolved — only Genie Space ID + Lakebase
# MAGIC connection details remain dynamic.

# COMMAND ----------

# PGHOST/PGUSER: auto-populated by Lakebase resource binding in apps.yml
# GENIE_SPACE_ID: set in app.yaml (static for this workspace)
# Only inject Genie Space ID here if dynamically created by deploy_genie task
env_vars = []
if genie_space_id:
    env_vars.append({"name": "GENIE_SPACE_ID", "value": genie_space_id})

print("Dynamic env vars to inject:")
for ev in env_vars:
    print(f"  {ev['name']:25s} = {ev['value']}")

# COMMAND ----------

# Get current app state
refresh_resp = requests.get(f"{host}/api/2.0/apps/{app_name}", headers=headers)
refresh_resp.raise_for_status()
refreshed = refresh_resp.json()

current_config = refreshed.get("config", {})
current_command = current_config.get("command", [
    "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"
])

source_code_path = (
    refreshed.get("active_deployment", {}).get("source_code_path", "")
    or refreshed.get("default_source_code_path", "")
)
if not source_code_path:
    username = _ctx.userName().get()
    source_code_path = f"/Workspace/Users/{username}/.bundle/monte-carlo-supervisor/dev/files/app"

# Merge: keep existing env vars from DAB, override dynamic ones
existing_env = {e["name"]: e["value"] for e in current_config.get("env", [])}
for ev in env_vars:
    existing_env[ev["name"]] = ev["value"]
merged_env_vars = [{"name": k, "value": v} for k, v in existing_env.items()]

# Start compute if needed
compute_state = refreshed.get("compute_status", {}).get("state", "UNKNOWN")
if compute_state != "ACTIVE":
    print(f"App compute is {compute_state}, starting...")
    start_resp = requests.post(f"{host}/api/2.0/apps/{app_name}/start", headers=headers)
    if start_resp.ok:
        for _ in range(20):
            time.sleep(15)
            check = requests.get(f"{host}/api/2.0/apps/{app_name}", headers=headers)
            if check.ok and check.json().get("compute_status", {}).get("state") == "ACTIVE":
                print("  Compute is ACTIVE.")
                break

# Deploy with merged env vars
print(f"Creating deployment with {len(merged_env_vars)} env vars...")
deploy_resp = requests.post(
    f"{host}/api/2.0/apps/{app_name}/deployments",
    headers=headers,
    json={
        "source_code_path": source_code_path,
        "mode": "SNAPSHOT",
        "env_vars": merged_env_vars,
        "command": current_command,
    },
)
if deploy_resp.ok:
    print(f"Deployment created: {deploy_resp.json().get('deployment_id', '?')}")
else:
    print(f"ERROR: {deploy_resp.status_code}: {deploy_resp.text}")
    deploy_resp.raise_for_status()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Poll Until Running

# COMMAND ----------

print("Waiting for app to start...")
timeout_s, poll_s, elapsed = 600, 15, 0

while elapsed < timeout_s:
    try:
        status_resp = requests.get(f"{host}/api/2.0/apps/{app_name}", headers=headers)
        status_resp.raise_for_status()
        app_status = status_resp.json().get("app_status", {}).get("state", "UNKNOWN")
    except Exception as e:
        app_status = f"ERROR: {e}"

    print(f"  [{elapsed:>3}s] {app_status}")

    if app_status in ("RUNNING", "DEPLOYED"):
        print(f"\nApp is {app_status}.")
        break
    if app_status in ("CRASHED", "FAILED"):
        print(f"\nERROR: App {app_status}. Check logs.")
        break

    time.sleep(poll_s)
    elapsed += poll_s
else:
    print(f"\nWARNING: App did not reach RUNNING within {timeout_s}s.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

try:
    status_resp = requests.get(f"{host}/api/2.0/apps/{app_name}", headers=headers)
    app_url = status_resp.json().get("url", "") if status_resp.ok else ""
except Exception:
    app_url = ""

print("=" * 60)
print("App Configuration Complete")
print("=" * 60)
print()
print(f"  App URL          : {app_url}")
print(f"  App SP           : {sp_client_id}")
print(f"  Genie Space      : {genie_space_id}")
print(f"  Dashboard        : {dashboard_id}")
print(f"  Lakebase Host    : {pg_host}")
print()
print("DAB-managed (apps.yml):")
print("  UC_CATALOG, UC_SCHEMA, SUPERVISOR_ENDPOINT, EXECUTOR_ENDPOINT,")
print("  SQL_WAREHOUSE_ID, SIMULATION_JOB_ID, DASHBOARD_ID, SEED_DEMO_DATA")
print()
print("Runtime-injected (this notebook):")
print("  GENIE_SPACE_ID, PGHOST, PGUSER")
print()
print("Manual post-deploy steps:")
print("  1. Link Genie Space to dashboard (UI only — no REST API)")
print("  2. Verify dashboard embedding works in app")
