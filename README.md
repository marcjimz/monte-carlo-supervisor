<div align="center">
  <a href="https://www.databricks.com/">
    <img src="https://www.databricks.com/wp-content/uploads/2022/06/db-nav-logo.svg" alt="Databricks" width="300">
  </a>
  <h1>Women's Health Monte Carlo Supervisor</h1>
  <p><strong>Distribution-driven Monte Carlo simulation + conversational AI for evaluating virtual care partnerships.</strong></p>
</div>

---

## What It Does

An AI supervisor routes natural-language questions between:

- **Genie Space** -- historical women's health encounter data (costs, diagnoses, demographics)
- **Simulation Engine** -- Spark-distributed Monte Carlo simulations (patient volume, revenue, cost comparison, system ROI)
- **Distribution Catalog** -- fitted distribution specs with goodness-of-fit metrics

All backed by synthetic data (10K patients, 50K encounters, 12 tables) and a React UI with agent chat, simulation builder, and matrix views.

---

## Deploy

### Prerequisites

- Databricks workspace with Unity Catalog
- [Databricks CLI](https://docs.databricks.com/dev-tools/cli/install.html) v0.287+
- Python 3.10+

> **Note:** The repo includes pre-built artifacts (Python wheel + React frontend), so Node.js/npm are **not required** to deploy. Only needed if you modify frontend code.

### Steps

```bash
git clone <repo-url> && cd monte-carlo-supervisor

# --- Auth ---
databricks auth login --host https://my-workspace.cloud.databricks.com --profile my-workspace
PROFILE="--profile my-workspace"

# --- Set your catalog ---
# Edit databricks.yml → variables.catalog.default, or pass --var at deploy time
CATALOG_VAR='--var=catalog=my_catalog_name'

# 1. Deploy all resources (app, warehouse, jobs, Lakebase, dashboard)
databricks bundle deploy $PROFILE $CATALOG_VAR

# 2. Deploy app source code (first time only — subsequent bundle deploys auto-redeploy)
databricks apps deploy monte-carlo-ui \
  --source-code-path $(databricks bundle summary $PROFILE $CATALOG_VAR --output json | python3 -c "import sys,json; print(json.load(sys.stdin)['workspace']['file_path'] + '/app')") \
  $PROFILE

# 3. Load data, create tables/views, fit distributions, grant UC perms, unpause trigger
databricks bundle run data_pipeline $PROFILE $CATALOG_VAR
```

After these three commands, the app is fully functional:
- Lakebase self-provisions on boot (host discovery, role creation, database + migrations)
- SQL warehouse created with correct permissions for the app service principal
- UC grants (USE_CATALOG, USE_SCHEMA, SELECT, MODIFY) applied by the data pipeline

**Optional** -- Deploy Genie Space + dashboard publish:
```bash
databricks bundle run genie_import $PROFILE $CATALOG_VAR
```

### Subsequent deploys

After the first deploy, `bundle deploy` automatically redeploys the app when source code changes:

```bash
databricks bundle deploy $PROFILE $CATALOG_VAR
```

### Rebuild from source

If you modify the frontend or Python package, rebuild before deploying:

```bash
npm install --prefix app/frontend   # first time only
npm run build --prefix app/frontend
pip wheel --no-build-isolation --no-deps --no-cache-dir -w dist/ .
databricks bundle deploy $PROFILE $CATALOG_VAR
```

---

## What Gets Created

| Resource | Name | Created By |
|----------|------|------------|
| Lakebase (Postgres) | `monte-carlo-app` | `bundle deploy` |
| SQL Warehouse | Monte Carlo Warehouse (serverless) | `bundle deploy` |
| Databricks App | `monte-carlo-ui` | `bundle deploy` + `apps deploy` |
| AI/BI Dashboard | Women's Health Analytics | `bundle deploy` |
| Data Pipeline Job | `monte-carlo-data-pipeline` (5 tasks) | `bundle deploy` |
| Simulation Job | `monte-carlo-simulation-pipeline` (4 tasks) | `bundle deploy` |
| Genie Import Job | `monte-carlo-genie-import` | `bundle deploy` |
| Delta Tables | 12 data + 4 simulation tables | `data_pipeline` |
| UC Views | Base + metric views | `data_pipeline` |

---

## Verify

Open the app URL, then try:

```
"What is the average cost per encounter for OB/GYN patients?"
"Compare virtual vs in-person care costs for women's health"
"Project the 5-year system cost ROI at 8% encounter reduction"
```

---

## Project Structure

```
monte-carlo-supervisor/
├── app/                          # Databricks App (FastAPI + React)
│   ├── app.py                    #   Entry point
│   ├── server/                   #   Backend (CRUD, SSE, agent chat)
│   └── frontend/                 #   React SPA (Vite + TypeScript)
├── notebooks/
│   ├── setup/                    # 01-05: data pipeline + genie setup
│   └── jobs/                     # mc_00-03: simulation pipeline
├── src/mc_supervisor/
│   ├── monte_carlo/              # Engine, config, distribution sampler
│   ├── agentbricks/              # Supervisor + agent definitions
│   ├── genie/                    # Genie Space config + import/export
│   └── sql/functions/            # UC function definitions
├── infra/resources/              # Bundle resource definitions (apps, jobs, warehouse, lakebase)
├── dashboards/                   # Lakeview dashboard definition
├── data/                         # Synthetic CSV files
├── tests/                        # Unit tests
├── databricks.yml                # Bundle config
└── app.yaml                      # App runtime config (command + env)
```

---

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

---

## License

See [LICENSE.md](LICENSE.md) for details.

---

&copy; 2025 Databricks, Inc. All rights reserved.
