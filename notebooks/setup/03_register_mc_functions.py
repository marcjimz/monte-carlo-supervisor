# Databricks notebook source
# MAGIC %md
# MAGIC # 03 — Register Monte Carlo UC Functions
# MAGIC
# MAGIC Sets up the UC HTTP Connection for workspace REST API access and registers
# MAGIC the `check_simulation` and `trigger_simulation` Unity Catalog functions.
# MAGIC
# MAGIC - `check_simulation`: Read-only — checks cache by exact parameter match
# MAGIC - `trigger_simulation`: Write-only — calls `http_request()` to trigger Spark job
# MAGIC
# MAGIC **Authentication**: Uses **OAuth M2M** with a Databricks Service Principal.
# MAGIC No PATs required. The setup creates a service principal, generates an OAuth
# MAGIC secret via the workspace-level SDK, and creates an OAuth M2M UC HTTP Connection.
# MAGIC
# MAGIC Prerequisites:
# MAGIC - MC pipeline job deployed via `databricks bundle deploy`
# MAGIC - SQL warehouse supporting `http_request()` (serverless or DBR 16.2+)

# COMMAND ----------

dbutils.widgets.text("catalog", "lakebase_hls_workshop_catalog", "UC Catalog")
dbutils.widgets.text("schema", "hospital_data", "UC Schema")
dbutils.widgets.text("principal", "account users", "Grant Execute To")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
principal = dbutils.widgets.get("principal")

print(f"Target    : {catalog}.{schema}")
print(f"Principal : {principal}")

# COMMAND ----------

# Add bundle root to sys.path so `src` package is importable
import sys
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_root = "/Workspace" + "/".join(_nb.split("/")[:-3])
if _root not in sys.path:
    sys.path.insert(0, _root)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create UC HTTP Connection (OAuth M2M)
# MAGIC
# MAGIC Creates a Service Principal with OAuth credentials via the workspace-level
# MAGIC SDK and a UC HTTP Connection that uses OAuth Machine-to-Machine authentication.

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Get workspace URL from the Spark config (reliable on Azure Databricks)
try:
    workspace_url = "https://" + spark.conf.get("spark.databricks.workspaceUrl")
except Exception:
    workspace_url = f"https://{w.config.host}" if not w.config.host.startswith("https://") else w.config.host
print(f"Workspace URL: {workspace_url}")

CONNECTION_NAME = "monte_carlo_ws"
SP_DISPLAY_NAME = "monte-carlo-sim-sp"
SP_SCOPE = "monte_carlo"
SP_CLIENT_ID_KEY = "sp_client_id"
SP_CLIENT_SECRET_KEY = "sp_client_secret"

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 1: Create or Reuse Service Principal + OAuth Secret

# COMMAND ----------

# Try loading existing SP credentials from secret scope (handles re-runs)
stored_client_id = None
stored_client_secret = None

try:
    stored_client_id = dbutils.secrets.get(scope=SP_SCOPE, key=SP_CLIENT_ID_KEY)
    stored_client_secret = dbutils.secrets.get(scope=SP_SCOPE, key=SP_CLIENT_SECRET_KEY)
    print(f"Existing SP credentials found in scope '{SP_SCOPE}'")
except Exception:
    print(f"SP credentials not found — creating...")

    # Find or create SP at workspace level
    existing = [s for s in w.service_principals.list(filter=f'displayName eq "{SP_DISPLAY_NAME}"')]
    if existing:
        sp_obj = existing[0]
        print(f"Found existing SP: {sp_obj.display_name} (id={sp_obj.id}, appId={sp_obj.application_id})")
    else:
        sp_obj = w.service_principals.create(display_name=SP_DISPLAY_NAME, active=True)
        print(f"Created SP: {sp_obj.display_name} (id={sp_obj.id}, appId={sp_obj.application_id})")

    # Generate OAuth secret via WORKSPACE-LEVEL API (not account API)
    secret_resp = w.service_principal_secrets_proxy.create(service_principal_id=sp_obj.id)
    stored_client_id = sp_obj.application_id
    stored_client_secret = secret_resp.secret

    # Store in secret scope
    try:
        w.secrets.create_scope(scope=SP_SCOPE)
        print(f"Created secret scope: {SP_SCOPE}")
    except Exception as e:
        if "already exists" not in str(e).lower():
            raise
    w.secrets.put_secret(scope=SP_SCOPE, key=SP_CLIENT_ID_KEY, string_value=stored_client_id)
    w.secrets.put_secret(scope=SP_SCOPE, key=SP_CLIENT_SECRET_KEY, string_value=stored_client_secret)
    print(f"Stored SP credentials in scope '{SP_SCOPE}'")

# Verify SP can authenticate
sp_client = WorkspaceClient(host=workspace_url, client_id=stored_client_id, client_secret=stored_client_secret)
sp_me = sp_client.current_user.me()
print(f"SP authenticated as: {sp_me.display_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 2: Create UC HTTP Connection

# COMMAND ----------

from src.databricks.sql.connections.workspace import WorkspaceConnection

# Drop existing connection for clean state
drop_sql = WorkspaceConnection.get_drop_sql(connection_name=CONNECTION_NAME)
print(f"Dropping existing connection: {drop_sql}")
try:
    spark.sql(drop_sql)
    print(f"  Dropped '{CONNECTION_NAME}'.")
except Exception as e:
    print(f"  No existing connection to drop: {e}")

# Create OAuth M2M connection
conn_sql = WorkspaceConnection.get_create_oauth_m2m_sql(
    workspace_url=workspace_url,
    client_id=stored_client_id,
    client_secret=stored_client_secret,
    connection_name=CONNECTION_NAME,
)

# Mask sensitive values in output
display_sql = conn_sql.replace(stored_client_secret, "****")
print(f"\nCreating connection (OAuth M2M):")
print(f"  {display_sql}")

spark.sql(conn_sql)
print(f"\nConnection '{CONNECTION_NAME}' created with OAuth M2M.")

# COMMAND ----------

# Grant USE CONNECTION
grant_conn_sql = WorkspaceConnection.get_grant_sql(
    connection_name=CONNECTION_NAME,
    principal=principal,
)
print(f"Granting: {grant_conn_sql}")
try:
    spark.sql(grant_conn_sql)
    print("Connection grant applied.")
except Exception as e:
    print(f"Warning granting connection: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Resolve MC Pipeline Job ID

# COMMAND ----------

mc_job_id = None
for job in w.jobs.list(name="monte-carlo-simulation-pipeline"):
    mc_job_id = str(job.job_id)
    break

if mc_job_id:
    print(f"Found MC pipeline job: {mc_job_id}")
else:
    for job in w.jobs.list():
        if "monte-carlo-simulation-pipeline" in (job.settings.name or ""):
            mc_job_id = str(job.job_id)
            print(f"Found MC pipeline job (dev mode): {mc_job_id} — {job.settings.name}")
            break

if not mc_job_id:
    mc_job_id = "0"
    print("WARNING: MC pipeline job not found. Using placeholder '0'.")
    print("Re-run this notebook after `databricks bundle deploy`.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Grant SP permissions on MC pipeline job

# COMMAND ----------

if mc_job_id and mc_job_id != "0" and stored_client_id:
    try:
        from databricks.sdk.service.iam import AccessControlRequest, PermissionLevel
        w.permissions.update(
            "jobs", mc_job_id,
            access_control_list=[
                AccessControlRequest(
                    service_principal_name=stored_client_id,
                    permission_level=PermissionLevel.CAN_MANAGE_RUN,
                )
            ],
        )
        print(f"Granted CAN_MANAGE_RUN on job {mc_job_id} to SP {stored_client_id}")
    except Exception as e:
        print(f"Warning granting SP job permissions: {e}")
else:
    print("Skipping SP job permissions — no MC pipeline job found or no SP.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Register UC Functions

# COMMAND ----------

from src.databricks.sql.functions.monte_carlo.registry import MonteCarloRegistry

registry = MonteCarloRegistry(
    catalog=catalog,
    schema=schema,
    mc_job_id=mc_job_id,
    connection_name=CONNECTION_NAME,
)

registration_stmts = registry.get_all_registration_sql()

# Drop deprecated functions (handles migration from old run_simulation)
print("Dropping deprecated functions...")
for func_name in registry.get_deprecated_function_names():
    try:
        spark.sql(f"DROP FUNCTION IF EXISTS {catalog}.{schema}.{func_name}")
        print(f"  Dropped {func_name}")
    except Exception as e:
        print(f"  Skip drop {func_name}: {e}")

# Drop new function names for clean re-registration
print("Dropping current functions for clean re-registration...")
for func_cls in registry.FUNCTIONS:
    try:
        spark.sql(f"DROP FUNCTION IF EXISTS {catalog}.{schema}.{func_cls.name}")
        print(f"  Dropped {func_cls.name}")
    except Exception as e:
        print(f"  Skip drop {func_cls.name}: {e}")

print(f"\nRegistering {len(registration_stmts)} UC function(s)...\n")

for i, sql in enumerate(registration_stmts, 1):
    print(f"  [{i}/{len(registration_stmts)}] Registering function ... ", end="")
    spark.sql(sql)
    print("done.")

print(f"\nAll {len(registration_stmts)} function(s) registered.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Grant Execute Permissions

# COMMAND ----------

grant_stmts = registry.get_all_grant_sql(principal=principal)

print(f"Granting EXECUTE to '{principal}'...\n")

for i, sql in enumerate(grant_stmts, 1):
    print(f"  [{i}/{len(grant_stmts)}] {sql.strip()}")
    try:
        spark.sql(sql)
    except Exception as e:
        print(f"  Warning: {e}")

print("\nGrants applied.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify — Describe Functions

# COMMAND ----------

for func_cls in registry.FUNCTIONS:
    print(f"\n--- {func_cls.name} ---")
    display(spark.sql(f"DESCRIBE FUNCTION {catalog}.{schema}.{func_cls.name}"))

# COMMAND ----------

print(f"UC function registration complete.")
print(f"  Functions    : {', '.join(f.name for f in registry.FUNCTIONS)}")
print(f"  MC Job ID    : {mc_job_id}")
print(f"  Connection   : {CONNECTION_NAME}")
print(f"  Auth method  : OAuth M2M (Service Principal)")
print(f"  SP client_id : {stored_client_id}")
