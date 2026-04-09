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
# MAGIC Prerequisites:
# MAGIC - MC pipeline job deployed via `databricks bundle deploy`
# MAGIC - SQL warehouse supporting `http_request()` (serverless or DBR 16.2+)

# COMMAND ----------

dbutils.widgets.text("catalog", "monte_carlo_sim", "UC Catalog")
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
# MAGIC ## Create UC HTTP Connection
# MAGIC
# MAGIC Creates a Unity Catalog HTTP connection to the workspace REST API.
# MAGIC Credentials are stored in Databricks Secrets — no tokens in code.

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Get workspace URL from the Spark config (reliable on Azure Databricks)
# The SDK's config.host may return the regional endpoint instead of the
# workspace-specific URL, so we prefer the Spark config.
try:
    workspace_url = "https://" + spark.conf.get("spark.databricks.workspaceUrl")
except Exception:
    workspace_url = f"https://{w.config.host}" if not w.config.host.startswith("https://") else w.config.host
print(f"Workspace URL: {workspace_url}")

# Connection settings
CONNECTION_NAME = "monte_carlo_ws"
SECRET_SCOPE = "monte_carlo"
SECRET_KEY = "workspace_token"

# COMMAND ----------

# Step 1: Create secret scope (idempotent)
try:
    w.secrets.create_scope(scope=SECRET_SCOPE)
    print(f"Created secret scope: {SECRET_SCOPE}")
except Exception as e:
    if "RESOURCE_ALREADY_EXISTS" in str(e) or "already exists" in str(e).lower():
        print(f"Secret scope '{SECRET_SCOPE}' already exists.")
    else:
        print(f"Warning creating scope: {e}")

# COMMAND ----------

# Step 2: Create a long-lived token and store in secrets
# The notebook context token is short-lived (Azure AD), so we create a
# Databricks token with 1-year lifetime via the SDK.
try:
    token_info = w.tokens.create(
        comment="Monte Carlo UC Connection (auto-created by setup pipeline)",
        lifetime_seconds=86400 * 365,  # 1 year
    )
    token_value = token_info.token_value
    print(f"Created Databricks token (ID: {token_info.token_info.token_id[:16]}...)")
except Exception as e:
    # Fallback: use notebook context token (short-lived, good for testing)
    print(f"Could not create long-lived token ({e}). Using notebook context token.")
    token_value = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

w.secrets.put_secret(scope=SECRET_SCOPE, key=SECRET_KEY, string_value=token_value)
print(f"Stored workspace token in {SECRET_SCOPE}/{SECRET_KEY}")

# COMMAND ----------

# Step 3: Create UC HTTP Connection
from src.databricks.sql.connections.workspace import WorkspaceConnection

conn_sql = WorkspaceConnection.get_create_sql(
    workspace_url=workspace_url,
    connection_name=CONNECTION_NAME,
    secret_scope=SECRET_SCOPE,
    secret_key=SECRET_KEY,
)
print(f"Creating connection: {CONNECTION_NAME}")
print(f"  SQL: {conn_sql}")

try:
    spark.sql(conn_sql)
    print(f"Connection '{CONNECTION_NAME}' created/verified.")
except Exception as e:
    print(f"Warning creating connection: {e}")
    print("If the connection already exists with different options, drop and recreate it.")

# COMMAND ----------

# Step 4: Grant USE CONNECTION
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

# Find the monte-carlo-simulation-pipeline job deployed by the bundle
mc_job_id = None
for job in w.jobs.list(name="monte-carlo-simulation-pipeline"):
    mc_job_id = str(job.job_id)
    break

if mc_job_id:
    print(f"Found MC pipeline job: {mc_job_id}")
else:
    # Fallback: check for dev-mode prefixed name
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
print(f"  Secret scope : {SECRET_SCOPE}/{SECRET_KEY}")
