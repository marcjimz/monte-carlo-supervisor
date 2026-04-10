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
# MAGIC secret, and creates an OAuth M2M UC HTTP Connection.
# MAGIC
# MAGIC If account admin access is unavailable (e.g., the account_id cannot be
# MAGIC discovered or SP secret generation fails), the notebook falls back to a
# MAGIC Bearer Token (PAT) approach.
# MAGIC
# MAGIC Prerequisites:
# MAGIC - MC pipeline job deployed via `databricks bundle deploy`
# MAGIC - SQL warehouse supporting `http_request()` (serverless or DBR 16.2+)
# MAGIC - Account admin privileges (for OAuth M2M; PAT fallback works without)

# COMMAND ----------

dbutils.widgets.text("catalog", "monte_carlo_sim", "UC Catalog")
dbutils.widgets.text("schema", "hospital_data", "UC Schema")
dbutils.widgets.text("principal", "account users", "Grant Execute To")
dbutils.widgets.text("account_id", "", "Databricks Account ID (auto-detected if blank)")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
principal = dbutils.widgets.get("principal")
account_id_param = dbutils.widgets.get("account_id").strip()

print(f"Target    : {catalog}.{schema}")
print(f"Principal : {principal}")
print(f"Account ID: {account_id_param or '(auto-detect)'}")

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
# MAGIC Creates a Service Principal with OAuth credentials and a UC HTTP Connection
# MAGIC that uses OAuth Machine-to-Machine authentication. Falls back to Bearer
# MAGIC Token if account-level access is unavailable.

# COMMAND ----------

from databricks.sdk import WorkspaceClient
import requests

w = WorkspaceClient()

# Get workspace URL from the Spark config (reliable on Azure Databricks)
try:
    workspace_url = "https://" + spark.conf.get("spark.databricks.workspaceUrl")
except Exception:
    workspace_url = f"https://{w.config.host}" if not w.config.host.startswith("https://") else w.config.host
print(f"Workspace URL: {workspace_url}")

CONNECTION_NAME = "monte_carlo_ws"
SP_DISPLAY_NAME = "monte-carlo-sim-sp"

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 1: Discover Account ID

# COMMAND ----------

is_azure = "azuredatabricks.net" in workspace_url
account_host = "https://accounts.azuredatabricks.net" if is_azure else "https://accounts.cloud.databricks.com"
user_token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
headers = {"Authorization": f"Bearer {user_token}"}

account_id = account_id_param  # use widget value if provided

if not account_id:
    # Try to auto-detect: list accounts the user has access to
    try:
        resp = requests.get(f"{account_host}/api/2.0/accounts", headers=headers, timeout=10)
        if resp.status_code == 200:
            body = resp.json()
            accounts = body if isinstance(body, list) else body.get("accounts", [body] if "account_id" in body else [])
            if accounts:
                account_id = accounts[0].get("account_id", "")
    except Exception:
        pass

if not account_id:
    # Try Azure-specific: the account ID may be in the metastore info
    try:
        resp = requests.get(
            f"{workspace_url}/api/2.0/unity-catalog/metastores",
            headers=headers, timeout=10,
        )
        if resp.status_code == 200:
            metastores = resp.json().get("metastores", [])
            for m in metastores:
                mid = m.get("metastore_id", "")
                # Metastore IDs contain the account ID on some platforms
                if mid:
                    pass  # not reliable for extracting account_id
    except Exception:
        pass

if account_id:
    print(f"Account ID: {account_id}")
else:
    print("Could not discover account_id. OAuth M2M will be attempted; if SP secret generation fails, Bearer Token fallback will be used.")
    print("To provide the account_id explicitly, set the 'account_id' widget parameter.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 2: Create or Reuse Service Principal

# COMMAND ----------

# Check for existing SP at workspace level
sp = None
for existing_sp in w.service_principals.list(filter=f'displayName eq "{SP_DISPLAY_NAME}"'):
    sp = existing_sp
    print(f"Found existing workspace SP: {sp.display_name} (id={sp.id}, appId={sp.application_id})")
    break

if sp is None:
    sp = w.service_principals.create(display_name=SP_DISPLAY_NAME, active=True)
    print(f"Created workspace SP: {sp.display_name} (id={sp.id}, appId={sp.application_id})")

sp_client_id = sp.application_id

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 3: Generate OAuth Secret via Account API

# COMMAND ----------

oauth_secret = None

if account_id:
    try:
        # Find or create SP at account level (account-level IDs differ from workspace-level)
        resp = requests.get(
            f"{account_host}/api/2.0/accounts/{account_id}/scim/v2/ServicePrincipals",
            headers=headers,
            params={"filter": f'displayName eq "{SP_DISPLAY_NAME}"'},
            timeout=10,
        )
        resp.raise_for_status()
        account_sps = resp.json().get("Resources", [])

        if account_sps:
            account_sp_id = account_sps[0]["id"]
            sp_client_id = account_sps[0].get("applicationId", sp.application_id)
            print(f"Found account-level SP: id={account_sp_id}, appId={sp_client_id}")
        else:
            # Create SP at account level
            resp = requests.post(
                f"{account_host}/api/2.0/accounts/{account_id}/scim/v2/ServicePrincipals",
                headers={**headers, "Content-Type": "application/json"},
                json={
                    "displayName": SP_DISPLAY_NAME,
                    "active": True,
                    "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServicePrincipal"],
                },
                timeout=10,
            )
            resp.raise_for_status()
            account_sp = resp.json()
            account_sp_id = account_sp["id"]
            sp_client_id = account_sp.get("applicationId", sp.application_id)
            print(f"Created account-level SP: id={account_sp_id}, appId={sp_client_id}")

        # Generate OAuth secret
        resp = requests.post(
            f"{account_host}/api/2.0/accounts/{account_id}/service-principals/{account_sp_id}/credentials/secrets",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        secret_data = resp.json()
        oauth_secret = secret_data["secret"]
        print(f"Generated OAuth secret (id: {secret_data.get('id', 'n/a')[:16]}...)")

        # Ensure the account-level SP is assigned to this workspace
        workspace_id = spark.conf.get("spark.databricks.clusterUsageTags.orgId")
        try:
            resp = requests.put(
                f"{account_host}/api/2.0/accounts/{account_id}/workspaces/{workspace_id}/permissionassignments/principals/{account_sp_id}",
                headers={**headers, "Content-Type": "application/json"},
                json={"permissions": ["USER"]},
                timeout=10,
            )
            if resp.status_code in (200, 201):
                print(f"Assigned SP to workspace {workspace_id}")
            elif resp.status_code == 409:
                print(f"SP already assigned to workspace {workspace_id}")
            else:
                print(f"SP workspace assignment: {resp.status_code} — {resp.text[:200]}")
        except Exception as e:
            print(f"Warning assigning SP to workspace: {e}")

        print(f"\nOAuth M2M credentials ready: client_id={sp_client_id}")

    except Exception as e:
        print(f"Account-level OAuth setup failed: {e}")
        print("Falling back to Bearer Token authentication (PAT).")
        oauth_secret = None
else:
    print("No account_id available — skipping OAuth M2M setup.")
    print("Falling back to Bearer Token authentication (PAT).")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 4: Create UC HTTP Connection

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

if oauth_secret:
    # OAuth M2M — preferred
    conn_sql = WorkspaceConnection.get_create_oauth_m2m_sql(
        workspace_url=workspace_url,
        client_id=sp_client_id,
        client_secret=oauth_secret,
        connection_name=CONNECTION_NAME,
    )
    auth_method = "OAuth M2M (Service Principal)"
else:
    # Fallback: Bearer Token with PAT
    SECRET_SCOPE = "monte_carlo"
    SECRET_KEY = "workspace_token"

    try:
        w.secrets.create_scope(scope=SECRET_SCOPE)
        print(f"Created secret scope: {SECRET_SCOPE}")
    except Exception as e:
        if "RESOURCE_ALREADY_EXISTS" in str(e) or "already exists" in str(e).lower():
            pass

    try:
        token_info = w.tokens.create(
            comment="Monte Carlo UC Connection (auto-created by setup pipeline)",
            lifetime_seconds=86400 * 365,
        )
        token_value = token_info.token_value
        print(f"Created Databricks PAT (ID: {token_info.token_info.token_id[:16]}...)")
    except Exception as e:
        print(f"Could not create long-lived token ({e}). Using notebook context token.")
        token_value = user_token

    w.secrets.put_secret(scope=SECRET_SCOPE, key=SECRET_KEY, string_value=token_value)
    conn_sql = WorkspaceConnection.get_create_bearer_sql(
        workspace_url=workspace_url,
        connection_name=CONNECTION_NAME,
        secret_scope=SECRET_SCOPE,
        secret_key=SECRET_KEY,
    )
    auth_method = "Bearer Token (PAT)"

# Mask sensitive values in output
display_sql = conn_sql
if oauth_secret:
    display_sql = conn_sql.replace(oauth_secret, "****")
print(f"\nCreating connection ({auth_method}):")
print(f"  {display_sql}")

spark.sql(conn_sql)
print(f"\nConnection '{CONNECTION_NAME}' created with {auth_method}.")

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

if mc_job_id and mc_job_id != "0" and sp_client_id:
    try:
        from databricks.sdk.service.iam import AccessControlRequest, PermissionLevel
        w.permissions.update(
            "jobs", mc_job_id,
            access_control_list=[
                AccessControlRequest(
                    service_principal_name=sp_client_id,
                    permission_level=PermissionLevel.CAN_MANAGE_RUN,
                )
            ],
        )
        print(f"Granted CAN_MANAGE_RUN on job {mc_job_id} to SP {sp_client_id}")
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
print(f"  Auth method  : {'OAuth M2M' if oauth_secret else 'Bearer Token (PAT)'}")
print(f"  SP client_id : {sp_client_id}")
