# Databricks notebook source
# COMMAND ----------
# MAGIC %md
# MAGIC # 02 — Deploy Genie Space
# MAGIC
# MAGIC Deploys or updates the Women's Health Analytics Genie Space using a
# MAGIC serialized JSON export and the `genie_import_export` module.
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
dbutils.widgets.text("skip_genie", "false", "Skip Genie Space deployment (use existing)")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
warehouse_id = dbutils.widgets.get("warehouse_id")
target_genie_space_id = dbutils.widgets.get("target_genie_space_id")
skip_genie = dbutils.widgets.get("skip_genie").lower() in ("true", "1", "yes")

print(f"Catalog                : {catalog}")
print(f"Schema                 : {schema}")
print(f"Warehouse ID           : {warehouse_id}")
print(f"Target Genie Space ID  : {target_genie_space_id or '(will create new)'}")
print(f"Skip Genie deployment  : {skip_genie}")

# COMMAND ----------

if skip_genie:
    print(f"Skipping Genie deployment — using existing space: {target_genie_space_id}")
    dbutils.jobs.taskValues.set(key="genie_space_id", value=target_genie_space_id)
    dbutils.jobs.taskValues.set(key="warehouse_id", value=warehouse_id)
    dbutils.notebook.exit(f"SKIPPED: using existing Genie Space {target_genie_space_id}")

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
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"{host}/api/2.0/genie/spaces",
        headers=headers,
        params={"page_size": 100},
    )
    space_id = ""
    if resp.ok:
        for s in resp.json().get("spaces", []):
            if s.get("title") == space_json.get("title", "Women's Health Analytics"):
                space_id = s.get("space_id", "")
                break

print(f"Genie Space ID: {space_id}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Output

# COMMAND ----------

dbutils.jobs.taskValues.set(key="genie_space_id", value=space_id)
dbutils.jobs.taskValues.set(key="warehouse_id", value=warehouse_id)
print(f"\nGenie Space ID : {space_id}")
print(f"Warehouse ID   : {warehouse_id}")
