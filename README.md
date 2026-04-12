<div align="center">
  <a href="https://www.databricks.com/">
    <img src="https://www.databricks.com/wp-content/uploads/2022/06/db-nav-logo.svg" alt="Databricks" width="300">
  </a>
  <h1>Women's Health Monte Carlo Supervisor</h1>
  <p><strong>Evaluate virtual care partnerships for women's health using distribution-driven Monte Carlo simulation and conversational AI.</strong></p>
</div>

---

## Overview

This solution accelerator combines Databricks Genie Space analytics with Monte Carlo simulation to evaluate the impact of introducing virtual care for women's health conditions. A single AI supervisor routes historical data questions to Genie, forward-looking hypothesis simulations to distributed Spark jobs, and distribution discovery queries to a fitted distribution catalog — enabling questions like "What's our OB/GYN cost per encounter?", "Project the 5-year ROI at 8% encounter reduction", and "What distributions have been fitted for cost comparison?" in the same conversation.

Synthetic data represents a 100% in-person baseline across women's health conditions (menopause, endometriosis, fibroids, pelvic pain, abnormal uterine bleeding). Simulations model the hypothetical impact of introducing virtual care using distribution specs fitted from historical data.

---

## Architecture

```
+----------------------------------------------------------------------+
|  Agent Bricks Multi-Agent Supervisor                                 |
|  +------------------------+  +---------------------+  +-----------+  |
|  | encounter_analytics    |  | simulation_checker/ |  | dist.     |  |
|  | (Genie Space)          |  | simulation_trigger  |  | catalog   |  |
|  | - WH encounter data    |  | (UC Functions)      |  | (UC Fn)   |  |
|  | - 4 Metric Views       |  | - Cache check       |  | - Fitted  |  |
|  | - Simulation Gold      |  | - Trigger Job       |  |   specs   |  |
|  +------------------------+  +---------------------+  +-----------+  |
+----------+-------------------------+-----------------+---------------+
           |                         |                 |
           v                         v                 v
+----------+----------+  +-----------+---------+  +----+---------------+
| Unity Catalog       |  | Databricks Job:     |  | distribution_specs |
| - 12 WH Tables      |  |   mc_pipeline       |  | Delta table        |
| - 4 Metric Views    |  | 1. Validate+resolve |  | - Versioned specs  |
| - Simulation Results|  |    distributions    |  | - KS fit metrics   |
+---------------------+  | 2. Spark MC         |  +--------------------+
                          |    (applyInPandas)  |
                          | 3. Aggregate → Gold |
                          +---------------------+
```

---

## Key Components

### Synthetic Women's Health Data

Twelve tables of deterministic, seeded synthetic data representing a three-year women's health dataset (2023-2026):

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

### Distribution-Driven Monte Carlo Engine

All stochastic draws go through a central `distribution_sampler` using distribution spec dicts. Specs can be fitted from historical data and stored in a versioned Delta table, or fall back to config defaults.

**Supported distribution types:** normal, lognormal, beta, gamma, uniform

Four simulation types powered by Spark-distributed `applyInPandas` execution:

| Simulation Type | Distributions | Structural Parameters | Output Metrics |
|---|---|---|---|
| `patient_volume` | `encounter_volume` (normal) | growth_rate, seasonality_amp, num_months | simulated_encounters by month |
| `revenue` | `gross_charges` (normal), `denial_rate` (beta) | avg_charge_to_rev, num_months | simulated_revenue by month |
| `cost_comparison` | `inperson_cost` (lognormal), `virtual_cost` (lognormal) | member_count, virtual_penetration, num_months | simulated_cost_per_encounter, simulated_total_cost by care_model |
| `system_cost_roi` | `baseline_cost` (lognormal), `reduction_noise` (normal) | encounter_reduction_pct, labor_inflation_rate, solution_cost, num_years | simulated_roi, simulated_net_savings, simulated_gross_savings by year |

Default configuration: 10,000 trials distributed across 50 Spark partitions with deterministic seeding per batch.

**Distribution resolution flow:**
1. Validate notebook checks `distribution_specs` Delta table for fitted specs
2. If fitted specs exist, uses the latest version; otherwise falls back to `config.yaml` defaults
3. Distribution version is included in cache key — re-fitting distributions invalidates cached results

### Genie Space

"Women's Health Analytics" — a natural-language interface configured with all WH tables, 4 metric views, and simulation Gold results. Users ask about OB/GYN costs, diagnosis prevalence, payer mix, and simulation outcomes in plain English.

### Agent Bricks Multi-Agent Supervisor

A declarative MAS with four sub-agents:

- **encounter_analytics** (Genie Space): Historical WH data questions and past simulation results
- **simulation_checker** (UC Function): Check cached simulation results
- **simulation_trigger** (UC Function): Trigger new Monte Carlo simulation jobs
- **distribution_catalog** (UC Function): Discover fitted distribution specs and goodness-of-fit metrics

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

The setup pipeline runs 8 tasks:

| Task | Purpose |
|---|---|
| `setup_catalog` | Create Unity Catalog catalog and schema |
| `load_data` | Load CSV files into UC tables |
| `create_metric_views` | Register 4 WH Metric Views |
| `create_sim_tables` | Create simulation_runs, simulation_trials, simulation_results, distribution_specs tables |
| `fit_distributions` | Fit distributions from historical data and write versioned specs |
| `register_functions` | Register `check_simulation`, `trigger_simulation`, and `list_distributions` UC Functions |
| `configure_genie` | Create Women's Health Analytics Genie Space |
| `create_supervisor` | Create Agent Bricks MAS with 4 agents |

### Verify

Test the MAS with sample queries:

```
"What is the average cost per encounter for OB/GYN patients?"
"Compare virtual vs in-person care costs for women's health"
"What distributions have been fitted for cost comparison simulations?"
"What was our OB/GYN cost per encounter last year, and simulate the 5-year ROI at 8% encounter reduction?"
```

---

## Hypothesis Testing

### H2: Cost Comparison (Virtual vs In-Person)

The `cost_comparison` simulation draws per-encounter costs from LogNormal distributions (`inperson_cost` and `virtual_cost`) for both care models and computes blended totals based on virtual penetration rate. Structural parameters: `member_count`, `virtual_penetration`, `annual_encounter_rate`, `num_months`.

### H5: System Cost ROI

The `system_cost_roi` simulation projects multi-year system costs with labor/expense inflation, applies an encounter reduction percentage (excluding surgical unless specified), and computes gross savings, net savings (minus partnership investment), and ROI. It draws the baseline annual cost from a LogNormal distribution (`baseline_cost`) and applies reduction noise from a Normal distribution (`reduction_noise`). Structural parameters: `encounter_reduction_pct`, `solution_cost`, `num_years`, `labor_inflation_rate`, `expense_inflation`, `include_surgery`.

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

### Simulation Tables

| Table | Purpose |
|---|---|
| `simulation_runs` | Run metadata + cache index |
| `simulation_trials` | Bronze: raw trial outcomes (schema evolves via mergeSchema) |
| `simulation_results` | Gold: aggregated percentiles by metric |
| `distribution_specs` | Versioned fitted distribution specs with KS goodness-of-fit metadata |

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
│   │   ├── 06_create_supervisor.py
│   │   └── 07_fit_distributions.py        # Fit distributions from historical data
│   └── jobs/                              # MC simulation pipeline tasks
│       ├── mc_01_validate.py              # Validate + resolve distribution specs
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
│       │   ├── config.yaml                # Single source of truth (v2.0)
│       │   ├── config_loader.py
│       │   ├── distribution_sampler.py    # Central distribution sampling utility
│       │   ├── fitting.py                 # scipy-based offline distribution fitting
│       │   ├── model_templates.py         # 4 model templates
│       │   ├── engine.py
│       │   └── results.py
│       ├── sql/functions/monte_carlo/     # UC Function definitions
│       │   ├── check_simulation.py
│       │   ├── trigger_simulation.py
│       │   ├── list_distributions.py      # Distribution catalog UC function
│       │   └── registry.py
│       ├── genie/                         # Genie Space configuration
│       └── agentbricks/                   # Agent Bricks MAS (4 agents)
└── tests/
    ├── test_synthetic_generators.py
    ├── test_distribution_sampler.py       # Distribution sampler unit tests
    ├── test_fitting.py                    # Distribution fitting tests
    ├── test_mc_models.py                  # Config-driven model contract tests
    ├── test_hypothesis_models.py          # H2/H5 domain-specific invariants
    ├── test_simulation_config.py          # Config structure + loader API
    ├── test_supervisor_config.py          # MAS agents + routing + examples
    └── test_uc_functions.py               # UC function SQL generation
```

---

## Testing

228 tests covering:

| Test File | Tests | What It Validates |
|---|---|---|
| `test_distribution_sampler.py` | 20 | All 5 distribution types, validation, determinism |
| `test_fitting.py` | 10 | scipy fitting accuracy, auto-fit selection, KS statistics |
| `test_mc_models.py` | 25 | Schema, row counts, determinism, public API (all sim types) |
| `test_hypothesis_models.py` | 17 | H2 virtual-vs-in-person economics, H5 inflation/ROI/surgery invariants |
| `test_simulation_config.py` | 40 | Config structure, loader API, distribution specs, UC function integration |
| `test_supervisor_config.py` | 26 | 4 agents, routing instructions, examples, DDL, cache keys |
| `test_uc_functions.py` | 22 | SQL generation, parameters, grants, registry |
| `test_synthetic_generators.py` | 68 | Data generation correctness, WH-specific constraints |

```bash
# Run all tests
make test

# Or directly
python -m pytest tests/ -v
```

---

## License

See [LICENSE.md](LICENSE.md) for details.

---

&copy; 2025 Databricks, Inc. All rights reserved.
