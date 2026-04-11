<div align="center">
  <a href="https://www.databricks.com/">
    <img src="https://www.databricks.com/wp-content/uploads/2022/06/db-nav-logo.svg" alt="Databricks" width="300">
  </a>
  <h1>Women's Health Monte Carlo Supervisor</h1>
  <p><strong>Evaluate virtual care partnerships for women's health using Monte Carlo simulation and conversational AI.</strong></p>
</div>

---

## Overview

This solution accelerator combines Databricks Genie Space analytics with Monte Carlo simulation to evaluate the impact of introducing virtual care for women's health conditions. A single AI supervisor routes historical data questions to Genie and forward-looking hypothesis simulations (cost comparison, system ROI) to distributed Spark jobs — enabling questions like "What's our OB/GYN cost per encounter?" and "Project the 5-year ROI at 8% encounter reduction" in the same conversation.

Synthetic data represents a 100% in-person baseline across women's health conditions (menopause, endometriosis, fibroids, pelvic pain, abnormal uterine bleeding). Simulations model the hypothetical impact of introducing virtual care.

---

## Architecture

```
+-------------------------------------------------------------+
|  Agent Bricks Multi-Agent Supervisor                        |
|  +---------------------------+  +------------------------+  |
|  | encounter_analytics       |  | simulation_checker/    |  |
|  | (Genie Space)             |  | simulation_trigger     |  |
|  | - WH encounter data       |  | (UC Functions)         |  |
|  | - 4 Metric Views          |  | - Cache check          |  |
|  | - Simulation Gold results |  | - Trigger Job          |  |
|  +---------------------------+  +------------------------+  |
+-------------------+---------------------+-------------------+
                    |                     |
                    v                     v
+-------------------+---+   +-------------+-------------------+
| Unity Catalog         |   | Databricks Job:                 |
| - 12 WH Tables        |   |   monte_carlo_pipeline          |
| - 4 Metric Views      |   | Task 1: Validate + check cache  |
| - Simulation Results  |   | Task 2: Spark-distributed MC    |
+-----------------------+   |         (applyInPandas)          |
                            | Task 3: Aggregate Bronze -> Gold |
                            +---------------------------------+
```

---

## Key Components

### Synthetic Women's Health Data

Twelve tables of deterministic, seeded synthetic data representing a three-year women's health dataset (2022-2024):

- **10,000 female patients** (18+) with demographics, insurance types, and WH chronic conditions (PCOS, endometriosis, menopause, etc.)
- **50,000 encounters** across OB/GYN, Internal Medicine, Endocrinology, Psychiatry, General Surgery, Radiology, and Emergency
- WH-focused ICD-10 codes (menopause, pelvic pain, fibroids, abnormal uterine bleeding) and gynecology CPT codes (hysteroscopy, lap hysterectomy, colposcopy, transvaginal US)
- Realistic distributions: bimodal age (reproductive/postmenopausal), seasonal patterns, payer-specific reimbursement rates, 8% denial rate

### UC Metric Views

Four semantic metric views for women's health analytics:

| Metric View | Source | Key Measures |
|---|---|---|
| `mv_wh_cost_by_condition` | billing + encounters + diagnoses | Total Cost, Avg Cost per Encounter, Denial Rate |
| `mv_wh_encounter_summary` | encounters | Total Encounters, Unique Patients, Avg LOS |
| `mv_wh_diagnosis_prevalence` | encounters + diagnoses + icd10_codes | Diagnosis Count, Unique Patients, Encounters per Patient |
| `mv_wh_patient_demographics` | patients + encounters | Patient Count, Total Encounters, Avg Encounters per Patient |

### Monte Carlo Simulation Engine

Four simulation types powered by Spark-distributed `applyInPandas` execution:

| Simulation Type | Model | Purpose |
|---|---|---|
| `patient_volume` | Normal timeseries with growth/seasonality | WH encounter volume forecasting |
| `revenue` | Normal charges with Beta denial rates | WH revenue/cost projection |
| `cost_comparison` | LogNormal cohort comparison (H2) | Virtual vs in-person cost comparison |
| `system_cost_roi` | Multi-year inflation + reduction (H5) | System cost ROI from virtual care partnership |

Default configuration: 10,000 trials distributed across 50 Spark partitions with deterministic seeding per batch.

### Genie Space

"Women's Health Analytics" — a natural-language interface configured with all WH tables, 4 metric views, and simulation Gold results. Users ask about OB/GYN costs, diagnosis prevalence, payer mix, and simulation outcomes in plain English.

### Agent Bricks Multi-Agent Supervisor

A declarative MAS with three sub-agents:

- **encounter_analytics** (Genie Space): Historical WH data questions and past simulation results
- **simulation_checker** (UC Function): Check cached simulation results
- **simulation_trigger** (UC Function): Trigger new Monte Carlo simulation jobs

---

## Quick Start

### Prerequisites

- Databricks workspace with Unity Catalog enabled
- Databricks CLI v0.280+ (`databricks version`)
- SQL Warehouse (serverless recommended)
- Python 3.10+

### Setup

```bash
# 1. Clone and install
git clone <repo-url>
cd monte-carlo-supervisor
make install

# 2. Authenticate
databricks auth login --host <your-workspace-url> --profile my-workspace

# 3. Deploy and run setup pipeline
DATABRICKS_CONFIG_PROFILE=my-workspace databricks bundle deploy
```

The setup pipeline runs 7 tasks:

| Task | Purpose |
|---|---|
| `setup_catalog` | Create Unity Catalog catalog and schema |
| `load_data` | Load CSV files into UC tables |
| `create_metric_views` | Register 4 WH Metric Views |
| `create_sim_tables` | Create simulation_runs, simulation_trials, simulation_results tables |
| `register_functions` | Register `check_simulation` and `trigger_simulation` UC Functions |
| `configure_genie` | Create Women's Health Analytics Genie Space |
| `create_supervisor` | Create Agent Bricks MAS |

### Verify

Test the MAS with sample queries:

```
"What is the average cost per encounter for OB/GYN patients?"
"Compare virtual vs in-person care costs for women's health"
"What was our OB/GYN cost per encounter last year, and simulate the 5-year ROI at 8% encounter reduction?"
```

---

## Hypothesis Testing

### H2: Cost Comparison (Virtual vs In-Person)

The `cost_comparison` simulation draws per-encounter costs from LogNormal distributions for both care models and computes blended totals based on virtual penetration rate. Key parameters: `baseline_cost_inperson`, `projected_cost_virtual`, `virtual_penetration`, `member_count`.

### H5: System Cost ROI

The `system_cost_roi` simulation projects multi-year system costs with labor/expense inflation, applies an encounter reduction percentage (excluding surgical unless specified), and computes gross savings, net savings (minus partnership investment), and ROI. Key parameters: `baseline_annual_cost`, `encounter_reduction_pct`, `solution_cost`, `num_years`.

Both types support multi-metric Gold aggregation — each simulation writes percentile distributions for all configured metrics (e.g., ROI, net savings, and gross savings by year).

---

## Data Model

All tables reside in `{catalog}.{schema}` (default: `monte_carlo_sim.hospital_data`).

### Dimension Tables

| Table | ~Rows | Key Columns |
|---|---|---|
| `patients` | 10,000 | patient_id, date_of_birth, gender (all F), insurance_type, chronic_conditions |
| `providers` | 200 | provider_id, name, specialty, facility_id, npi |
| `facilities` | 8 | facility_id, name, type, bed_count, city, state |

### Fact Tables

| Table | ~Rows | Key Columns |
|---|---|---|
| `encounters` | 50,000 | encounter_id, patient_id, provider_id, encounter_type, department, admission_date, length_of_stay |
| `diagnoses` | ~95,000 | diagnosis_id, encounter_id, icd10_code, is_primary |
| `procedures` | ~37,000 | procedure_id, encounter_id, cpt_code, procedure_date |
| `billing` | 50,000 | billing_id, encounter_id, total_charges, paid_amount, payer_id, claim_status |
| `readmissions` | ~650 | readmission_id, original_encounter_id, days_between |

### Reference Tables

| Table | ~Rows | Purpose |
|---|---|---|
| `icd10_codes` | ~42 | WH-focused ICD-10 diagnosis codes |
| `cpt_codes` | ~27 | WH-focused CPT procedure codes |
| `payers` | 8 | Insurance payer reference |
| `departments` | 7 | Department names |

### Simulation Result Tables

| Table | Purpose |
|---|---|
| `simulation_runs` | Run metadata + cache index |
| `simulation_trials` | Bronze: raw trial outcomes (schema evolves via mergeSchema) |
| `simulation_results` | Gold: aggregated percentiles by metric |

---

## Project Structure

```
monte-carlo-supervisor/
├── README.md
├── Makefile
├── pyproject.toml
├── data/                                  # Pre-generated synthetic CSV files
├── infra/                                 # Databricks Asset Bundle
├── notebooks/
│   ├── setup/                             # Run once to initialize
│   │   ├── 00_setup_catalog.py
│   │   ├── 01_generate_synthetic_data.py
│   │   ├── 02_create_metric_views.py
│   │   ├── 03_register_mc_functions.py
│   │   ├── 04_create_simulation_tables.py
│   │   ├── 05_configure_genie_space.py
│   │   └── 06_create_supervisor.py
│   └── jobs/                              # MC simulation pipeline tasks
│       ├── mc_01_validate.py
│       ├── mc_02_simulate.py
│       └── mc_03_aggregate.py
├── src/
│   └── databricks/
│       ├── synthetic_data/                # WH data generation
│       │   ├── config.py
│       │   └── generators/
│       ├── metric_views/                  # 4 WH Metric View definitions
│       │   └── definitions.py
│       ├── monte_carlo/                   # MC simulation engine
│       │   ├── config.yaml                # Single source of truth
│       │   ├── config_loader.py
│       │   ├── model_templates.py         # 4 model templates
│       │   ├── engine.py
│       │   └── results.py
│       ├── sql/functions/monte_carlo/     # UC Function definitions
│       ├── genie/                         # Genie Space configuration
│       └── agentbricks/                   # Agent Bricks MAS
└── tests/
    ├── test_synthetic_generators.py
    ├── test_mc_models.py
    ├── test_hypothesis_models.py
    ├── test_simulation_config.py
    ├── test_supervisor_config.py
    └── test_uc_functions.py
```

---

## License

See [LICENSE.md](LICENSE.md) for details.

---

&copy; 2025 Databricks, Inc. All rights reserved.
