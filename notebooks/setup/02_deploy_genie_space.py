# Databricks notebook source
# COMMAND ----------
# MAGIC %md
# MAGIC # 02 — Deploy Genie Space + Dashboard Publish
# MAGIC
# MAGIC Deploys or updates the Encounter Analytics Genie Space using a
# MAGIC serialized JSON export and the `genie_import_export` module.
# MAGIC Then grants the app SP CAN_MANAGE on the Genie Space and
# MAGIC enables dashboard embedding + publish.
# MAGIC
# MAGIC **Pattern**: [Reusable IP — Genie Import/Export](https://github.com/databricks-field-eng/reusable-ip-ai)
# MAGIC
# MAGIC **Inputs**: `infra/genie/wh_analytics_space.json` (version-controlled export)
# MAGIC **Outputs**: `genie_space_id` → passed to downstream tasks via `taskValues`

# COMMAND ----------

dbutils.widgets.text("catalog", "monte_carlo_supervisor_catalog")
dbutils.widgets.text("schema", "hospital_data")
dbutils.widgets.text("warehouse_id", "")
dbutils.widgets.text("target_genie_space_id", "")
dbutils.widgets.text("app_sp_client_id", "", "App Service Principal Client ID")
dbutils.widgets.text("lakebase_project", "", "Lakebase Project ID (unused — app self-provisions)")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
warehouse_id = dbutils.widgets.get("warehouse_id")
target_genie_space_id = dbutils.widgets.get("target_genie_space_id")
app_sp_client_id = dbutils.widgets.get("app_sp_client_id")
print(f"Catalog                : {catalog}")
print(f"Schema                 : {schema}")
print(f"Warehouse ID           : {warehouse_id}")
print(f"Target Genie Space ID  : {target_genie_space_id or '(will create new)'}")
print(f"App SP Client ID       : {app_sp_client_id or '(not set)'}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Locate Exported JSON

# COMMAND ----------

import json
import os
from pathlib import Path

# DAB bundles deploy files relative to the bundle root
bundle_root = os.environ.get("BUNDLE_ROOT", "")

json_candidates = []
if bundle_root:
    json_candidates.append(Path(bundle_root) / "infra" / "genie" / "wh_analytics_space.json")
json_candidates.extend([
    Path("../infra/genie/wh_analytics_space.json"),
    Path("../../infra/genie/wh_analytics_space.json"),
])

json_path = None
for p in json_candidates:
    if p.exists():
        json_path = str(p)
        print(f"Found Genie Space JSON: {json_path}")
        break

if json_path is None:
    print("WARNING: Genie Space JSON not found — skipping deployment")
    dbutils.jobs.taskValues.set(key="genie_space_id", value="")
    dbutils.jobs.taskValues.set(key="warehouse_id", value=warehouse_id)
    dbutils.notebook.exit("SKIPPED — no exported JSON found")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Replace Catalog/Schema References

# COMMAND ----------

with open(json_path) as f:
    space_json = json.load(f)

# Replace hardcoded catalog.schema refs in the serialized_space string
if "serialized_space" in space_json:
    ss = space_json["serialized_space"]
    # serialized_space can be a JSON string or dict
    if isinstance(ss, str):
        ss = ss.replace("monte_carlo_supervisor_catalog.hospital_data", f"{catalog}.{schema}")
        ss = ss.replace("lakebase_hls_workshop_catalog.hospital_data", f"{catalog}.{schema}")
        space_json["serialized_space"] = ss
    elif isinstance(ss, dict):
        ss_str = json.dumps(ss)
        ss_str = ss_str.replace("monte_carlo_supervisor_catalog.hospital_data", f"{catalog}.{schema}")
        ss_str = ss_str.replace("lakebase_hls_workshop_catalog.hospital_data", f"{catalog}.{schema}")
        space_json["serialized_space"] = ss_str

# Write the patched JSON to a temp file for ImportGenie
patched_path = "/tmp/wh_analytics_space_patched.json"
with open(patched_path, "w") as f:
    json.dump(space_json, f)

print(f"Patched catalog/schema → {catalog}.{schema}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Import or Update Genie Space

# COMMAND ----------

import sys
# genie_import_export is synced as part of the bundle under src/mc_supervisor/genie/
if bundle_root:
    sys.path.insert(0, str(Path(bundle_root) / "src" / "mc_supervisor" / "genie"))
else:
    sys.path.insert(0, str(Path("../../src/mc_supervisor/genie")))

from genie_import_export import ImportGenie

_ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
host = _ctx.apiUrl().get()
username = _ctx.userName().get()

import_genie = ImportGenie(
    host=host,
    dbutils=dbutils,
    json_path=patched_path,
    target_genie_dir=f"/Users/{username}",
    target_genie_space_id=target_genie_space_id or None,
    warehouse_id=warehouse_id or None,
)

status_code = import_genie.import_or_update()
print(f"Genie API returned: {status_code}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Resolve Space ID

# COMMAND ----------

# If we updated, space ID is the target; if we created, extract from response
if target_genie_space_id and str(target_genie_space_id).lower() != "none":
    space_id = target_genie_space_id
else:
    # Re-read the import result — ImportGenie.create_genie returns the response
    # We need to find the new space by listing
    import requests
    token = _ctx.apiToken().get()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.get(
        f"{host}/api/2.0/genie/spaces",
        headers=headers,
        params={"page_size": 100},
    )
    space_id = ""
    if resp.ok:
        for s in resp.json().get("spaces", []):
            if s.get("title") == space_json.get("title", "Encounter Analytics"):
                space_id = s.get("space_id", "")
                break

print(f"Genie Space ID: {space_id}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Grant Genie CAN_MANAGE to App SP

# COMMAND ----------

if not "headers" in dir():
    token = _ctx.apiToken().get()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

if space_id and app_sp_client_id:
    genie_perm_resp = requests.patch(
        f"{host}/api/2.0/permissions/genie/{space_id}",
        headers=headers,
        json={
            "access_control_list": [
                {
                    "service_principal_name": app_sp_client_id,
                    "permission_level": "CAN_MANAGE",
                }
            ]
        },
    )
    print(f"Genie CAN_MANAGE for app SP: {'granted' if genie_perm_resp.ok else f'WARNING: {genie_perm_resp.status_code}: {genie_perm_resp.text}'}")
else:
    if not space_id:
        print("Genie CAN_MANAGE: skipped (no Genie Space ID)")
    if not app_sp_client_id:
        print("Genie CAN_MANAGE: skipped (no app SP client ID)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Grant UC Permissions to App SP
# MAGIC
# MAGIC The app SP needs USE_CATALOG, USE_SCHEMA, SELECT (for reads) and
# MAGIC MODIFY (for simulation_runs/results writes).

# COMMAND ----------

if app_sp_client_id:
    for grant_stmt in [
        f"GRANT USE CATALOG ON CATALOG {catalog} TO `{app_sp_client_id}`",
        f"GRANT USE SCHEMA ON SCHEMA {catalog}.{schema} TO `{app_sp_client_id}`",
        f"GRANT SELECT ON SCHEMA {catalog}.{schema} TO `{app_sp_client_id}`",
    ]:
        try:
            spark.sql(grant_stmt)
            print(f"  {grant_stmt.split('GRANT ')[1].split(' TO')[0]}: granted")
        except Exception as e:
            if "already has" in str(e).lower() or "ALREADY_EXISTS" in str(e):
                print(f"  {grant_stmt.split('GRANT ')[1].split(' TO')[0]}: already granted")
            else:
                print(f"  WARNING: {e}")

    for table in ["simulation_runs", "simulation_results"]:
        fqn = f"{catalog}.{schema}.{table}"
        try:
            spark.sql(f"GRANT MODIFY ON TABLE {fqn} TO `{app_sp_client_id}`")
            print(f"  MODIFY on {fqn}: granted")
        except Exception as e:
            if "already has" in str(e).lower() or "ALREADY_EXISTS" in str(e):
                print(f"  MODIFY on {fqn}: already granted")
            else:
                print(f"  MODIFY on {fqn}: WARNING: {e}")
else:
    print("UC grants: skipped (no app SP client ID)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Dashboard: Enable Embedding & Publish
# MAGIC
# MAGIC Look up the DAB-deployed dashboard by name, enable workspace-level
# MAGIC embedding, and publish with embed credentials.

# COMMAND ----------

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
# MAGIC ## Output

# COMMAND ----------

dbutils.jobs.taskValues.set(key="genie_space_id", value=space_id)
dbutils.jobs.taskValues.set(key="warehouse_id", value=warehouse_id)
print(f"\nGenie Space ID : {space_id}")
print(f"Warehouse ID   : {warehouse_id}")
print(f"Dashboard ID   : {dashboard_id}")
