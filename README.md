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

- **Genie Space** — historical women's health encounter data (costs, diagnoses, demographics)
- **Simulation Engine** — Spark-distributed Monte Carlo simulations (patient volume, revenue, cost comparison, system ROI)
- **Distribution Catalog** — fitted distribution specs with goodness-of-fit metrics

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

# --- Set your catalog in databricks.yml ---
# Edit databricks.yml → variables.catalog.default to your catalog name

# --- Deploy ---
DATABRICKS_CONFIG_PROFILE=my-workspace make deploy
```

This will:
1. Create jobs, app, Lakebase database, and dashboard on your workspace
2. Run 9 setup tasks: load data, create views, fit distributions, configure Genie/MAS, and wire the app

### Redeploy app only (no setup)

```bash
DATABRICKS_CONFIG_PROFILE=my-workspace make deploy-app
```

### Rebuild from source

If you modify the frontend or Python package, rebuild before deploying:

```bash
npm install --prefix app/frontend   # first time only
make deploy FORCE_BUILD=1
```

---

## What Gets Created

| Resource | Name | Created By |
|----------|------|------------|
| Lakebase (Postgres) | `monte-carlo-app` | `bundle deploy` |
| Databricks App | `monte-carlo-ui` | `bundle deploy` |
| AI/BI Dashboard | Women's Health Analytics | `bundle deploy` |
| Setup Job | `monte-carlo-setup-pipeline` (9 tasks) | `bundle deploy` |
| Simulation Job | `monte-carlo-simulation-pipeline` (3 tasks) | `bundle deploy` |
| Genie Space | Women's Health Analytics | setup task 05 |
| MAS Endpoint | `mas-{tile_id}-endpoint` | setup task 06 |
| UC Functions | `check_simulation`, `trigger_simulation`, `list_distributions` | setup task 03 |
| Delta Tables | 12 data + 4 simulation tables | setup tasks 00-04, 07 |

---

## Verify

Open the app URL printed at the end of the setup pipeline, then try:

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
│   ├── setup/                    # 00-08: one-time setup tasks
│   └── jobs/                     # mc_01-03: simulation pipeline
├── src/mc_supervisor/
│   ├── monte_carlo/              # Engine, config, distribution sampler
│   ├── agentbricks/              # MAS supervisor + agent definitions
│   ├── genie/                    # Genie Space config
│   └── sql/functions/            # UC function definitions
├── infra/resources/              # Bundle resource definitions
├── data/                         # Synthetic CSV files
├── tests/                        # 228 tests
├── databricks.yml                # Bundle config
└── Makefile
```

---

## Testing

```bash
make test
```

228 tests covering distribution sampling, fitting, all 4 simulation types, config loading, supervisor routing, UC functions, and synthetic data generation.

---

## License

See [LICENSE.md](LICENSE.md) for details.

---

&copy; 2025 Databricks, Inc. All rights reserved.
