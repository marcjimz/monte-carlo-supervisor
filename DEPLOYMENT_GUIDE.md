# Monte Carlo Supervisor — Deployment Guide

Deploy the app from the `feat/langgraph` branch into a target Databricks workspace where resources (catalog, schema, warehouse, Lakebase, Genie Space) already exist.

## Prerequisites

| Resource | Required | Notes |
|----------|----------|-------|
| Unity Catalog + Schema | Yes | e.g. `monte_carlo_supervisor_catalog.hospital_data` |
| SQL Warehouse | Yes | Serverless recommended; note the warehouse ID |
| Lakebase Project | Yes | With `production` branch and `primary` endpoint |
| Genie Space | Yes | Deployed via `02_deploy_genie_space.py` or manually |
| Simulation Job | Yes | The multi-task job (dispatch → validate → simulate → aggregate) |
| Dashboard (optional) | No | AI/BI Lakeview dashboard for "Explore Data" tab |
| FMAPI Endpoints | Yes | `databricks-claude-opus-4-7` and `databricks-claude-sonnet-4` |

## Step 1: Update `app/app.yaml`

This is the **primary config file** you must update. It controls all runtime env vars for the app. DAB's `apps.yml` `config.env` does **not** populate this file — you must maintain it manually for direct deploys.

```yaml
command:
  - uvicorn
  - app:app
  - --host
  - 0.0.0.0
  - --port
  - "8000"

env:
  - name: UC_CATALOG
    value: "<your-catalog>"                    # e.g. monte_carlo_supervisor_catalog
  - name: UC_SCHEMA
    value: "<your-schema>"                     # e.g. hospital_data
  - name: SEED_DEMO_DATA
    value: "true"                              # Seeds Lakebase tables on first boot
  - name: SUPERVISOR_ENDPOINT
    value: "databricks-claude-opus-4-7"        # FMAPI serving endpoint (supervisor LLM)
  - name: EXECUTOR_ENDPOINT
    value: "databricks-claude-sonnet-4"        # FMAPI serving endpoint (tool executor LLM)
  - name: SQL_WAREHOUSE_ID
    value: "<your-warehouse-id>"               # SQL warehouse for Delta queries
  - name: SIMULATION_JOB_ID
    value: "<your-simulation-job-id>"          # Databricks Job ID for MC pipeline
  - name: PGDATABASE
    value: "mcapp"                             # Lakebase database name
  - name: GENIE_SPACE_ID
    value: "<your-genie-space-id>"             # Genie Space for analytics queries
```

### Env vars you do NOT set (auto-injected by the platform)

| Var | Source |
|-----|--------|
| `DATABRICKS_HOST` | Platform injects hostname (app prepends `https://`) |
| `DATABRICKS_APP_PORT` | Platform sets this; presence = "running as Databricks App" |
| `DATABRICKS_CLIENT_ID` | App service principal UUID; used as `PGUSER` for Lakebase |
| `PGHOST` | Auto-populated by Lakebase resource binding |
| `PGUSER` | Falls back to `DATABRICKS_CLIENT_ID` if not set |

## Step 2: Update `app/server/config.py` defaults (optional)

Only needed if your workspace defaults differ. The `Settings` class reads from env vars, so `app.yaml` takes precedence. But check these defaults match your workspace if you're running locally:

```python
uc_catalog: str = "monte_carlo_supervisor_catalog"
uc_schema: str = "hospital_data"
supervisor_endpoint: str = "databricks-claude-opus-4-7"
executor_endpoint: str = "databricks-claude-sonnet-4"
sql_warehouse_id: str = "39aeb4605bfae41b"          # ← update for your warehouse
lakebase_project: str = "monte-carlo-app"            # ← update for your project
databricks_profile: str = "mc-supervisor"            # ← update for local dev profile
```

## Step 3: Sync & Deploy

```bash
# 1. Sync local code to workspace
databricks sync app /Workspace/Users/<you>/monte-carlo-supervisor/app --profile <profile>

# 2. Deploy
databricks apps deploy <app-name> \
  --profile <profile> \
  --source-code-path /Workspace/Users/<you>/monte-carlo-supervisor/app
```

## Step 4: Verify Permissions

The app's service principal needs these permissions (usually set up by `04_configure_app.py` or DAB resource bindings):

| Permission | Target | How |
|------------|--------|-----|
| `CAN_USE` | SQL Warehouse | DAB resource binding or manual grant |
| `CAN_MANAGE_RUN` | Simulation Job | DAB resource binding or manual grant |
| `MODIFY` | `simulation_runs` table | `GRANT MODIFY ON TABLE ... TO \`<sp-id>\`` |
| `MODIFY` | `simulation_results` table | Same |
| `CAN_MANAGE` | Genie Space | `PATCH /api/2.0/permissions/genie/<space-id>` |
| `CAN_CONNECT_AND_CREATE` | Lakebase | DAB resource binding or Lakebase permissions API |
| Lakebase Postgres role | SP client ID | `POST /api/2.0/postgres/projects/<project>/branches/production/roles` |
| `mcapp` database access | Lakebase | `GRANT ALL ON DATABASE mcapp TO "<sp-id>"` |

## Things to Watch Out For

### DATABRICKS_HOST needs `https://`
In Databricks Apps, `DATABRICKS_HOST` is injected as a bare hostname (e.g. `adb-12345.azuredatabricks.net`). The app's `sql_client.py` prepends `https://` automatically, but if you override it in `app.yaml`, include the protocol.

### FMAPI Claude does NOT support `temperature`
The Databricks Foundation Model API proxy for Claude models rejects requests with a `temperature` parameter. The agent config already omits it — don't add it back.

### Stale simulation rows in Delta
If you see matrix cells stuck as "running" forever, check for stale rows:
```sql
SELECT run_id, simulation_type, status, updated_at
FROM <catalog>.<schema>.simulation_runs
WHERE status = 'RUNNING'
  AND updated_at < (current_timestamp() - INTERVAL 30 MINUTES)
```
The app now has a 30-minute staleness guard — RUNNING rows older than 30 minutes are ignored. But if you're migrating from an older version, clean them up:
```sql
UPDATE <catalog>.<schema>.simulation_runs
SET status = 'FAILED', updated_at = current_timestamp()
WHERE status = 'RUNNING'
  AND updated_at < (current_timestamp() - INTERVAL 30 MINUTES)
```

### Simulation Job must have `job_parameters`
The simulation job definition needs a `parameters` block so `jobs.run_now()` can pass simulation config:
```yaml
parameters:
  - name: simulation_type
    default: "patient_volume"
  - name: parameters
    default: "{}"
  - name: num_simulations
    default: "10000"
  - name: seed
    default: "42"
```
The dispatch notebook (`mc_00_dispatch.py`) reads these via `dbutils.widgets.get()`.

### Genie Space linking is manual
After deploying the Genie Space and dashboard, you must manually link the Genie Space to the dashboard in the Databricks UI. There is no REST API for this.

### Lakebase tables are auto-created on first boot
When `SEED_DEMO_DATA=true`, the app creates all Lakebase (Postgres) tables on startup and syncs data from Delta. No manual migration needed.

### Chart inference is disabled
Inline chart generation in agent chat is currently disabled (`thread_service.py`). The code is preserved as comments — re-enable when chart rendering is stable.

## Config Files Summary

| File | Must Update | What |
|------|-------------|------|
| `app/app.yaml` | **Yes** | All runtime env vars (catalog, schema, warehouse, job ID, genie, endpoints) |
| `app/server/config.py` | Maybe | Default values; only matters for local dev if env vars aren't set |
| `databricks.yml` | Maybe | DAB bundle config — only if deploying via `databricks bundle deploy` |
| `infra/resources/apps.yml` | Maybe | DAB app resource — only if deploying via DAB (has variable interpolation) |
| `infra/resources/jobs.yml` | Maybe | DAB job resource — only if deploying via DAB |
| `infra/resources/lakebase.yml` | Maybe | DAB Lakebase resource — only if deploying via DAB |
| `infra/resources/dashboards.yml` | Maybe | DAB dashboard resource — only if deploying via DAB |
| `app/server/config.yaml` | No | Simulation type config (parameter definitions, distributions) — portable as-is |

## Quick Deploy Checklist

- [ ] Update `app/app.yaml` with your workspace's IDs (warehouse, job, genie space, catalog/schema)
- [ ] Verify FMAPI endpoints exist (`databricks-claude-opus-4-7`, `databricks-claude-sonnet-4`)
- [ ] Verify simulation job exists and has `parameters` block
- [ ] Verify app SP has permissions (Delta MODIFY, Genie CAN_MANAGE, Warehouse CAN_USE, Job CAN_MANAGE_RUN)
- [ ] Verify Lakebase project exists with `mcapp` database and SP role
- [ ] Sync and deploy: `databricks sync` + `databricks apps deploy`
- [ ] Check app logs after deploy: `databricks apps get-logs <app-name> --profile <profile>`
- [ ] Clean up stale RUNNING/SUBMITTED rows in Delta if migrating from older version
- [ ] Manually link Genie Space to dashboard in UI (one-time)
