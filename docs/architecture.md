# Architecture

This document describes the three-layer architecture of the Hospital Monte Carlo Supervisor, covering the Agent Bricks MAS, the Monte Carlo pipeline, the Genie Space, and the Delta Lake storage layer.

---

## Three-Layer Architecture

The system is organized into three distinct layers, each mapping to a Databricks platform capability:

```
Layer 1: Orchestration    Agent Bricks Multi-Agent Supervisor
Layer 2: Execution        Genie Space (SQL analytics) + Databricks Job (MC simulation)
Layer 3: Storage          Delta Lake tables in Unity Catalog
```

### Layer 1 -- Orchestration (Agent Bricks MAS)

The top layer is a declarative Multi-Agent Supervisor created via the `manage_mas` pattern from the Databricks AI Dev Kit. It exposes a single conversational endpoint (served via Model Serving) that accepts natural-language queries and routes them to the appropriate sub-agent.

**Sub-agents:**

| Agent Name | Type | Backing Resource | Responsibility |
|---|---|---|---|
| `encounter_analytics` | Genie Space | Genie Space ID | Historical analytics, KPI lookups, simulation result queries |
| `monte_carlo_simulator` | UC Function | `{catalog}.{schema}.run_simulation` | New simulation requests, cache retrieval |

**Routing logic** (defined in supervisor instructions):

1. **Historical data** (counts, trends, averages, "show me", "what was") routes to `encounter_analytics`
2. **Past simulation results** ("show me past simulations", "what were the results of") routes to `encounter_analytics` (Genie queries the `simulation_results` Gold table)
3. **New simulations** ("forecast", "simulate", "what if", "predict", "project") routes to `monte_carlo_simulator`
4. **Compound queries** are decomposed: historical context from Genie first, then simulation from the UC Function, with results synthesized in the response

### Layer 2 -- Execution

#### Genie Space

The Genie Space provides natural-language-to-SQL translation over:

- 12 hospital data tables (patients, encounters, diagnoses, procedures, billing, readmissions, and 4 reference tables)
- 6 UC Metric Views with pre-defined dimensions and measures
- 2 simulation result tables (simulation_runs, simulation_results)

Custom instructions tell Genie to prefer metric views (via `MEASURE()` syntax) when the question maps to a standard KPI, and to join `simulation_results` with `simulation_runs` for past simulation queries.

#### Monte Carlo Pipeline (Databricks Job)

The `monte_carlo_pipeline` Databricks Job executes simulations in three sequential tasks:

```
Task 1: mc_01_validate.py
  - Validate simulation_type against allowed values
  - Parse and validate JSON parameters
  - Compute cache key (SHA-256 hash of type + params + seed + num_simulations)
  - Check simulation_runs table for matching completed run
  - If cache hit: write task value with cached run_id, skip remaining tasks
  - If cache miss: write run metadata with status=RUNNING

Task 2: mc_02_simulate.py
  - Create seed DataFrame (one row per batch, each with deterministic seed)
  - Broadcast params to all executors
  - Execute groupBy("id").applyInPandas() with the simulation model
  - Each executor runs trials_per_batch trials independently
  - Write raw trial results to simulation_trials (Bronze)

Task 3: mc_03_aggregate.py
  - Read Bronze trials for the current run_id
  - Group by natural dimension (month, department, hour_of_day)
  - Compute: mean, std, min, max, p05, p10, p25, p50, p75, p90, p95
  - Write aggregated results to simulation_results (Gold)
  - Update simulation_runs status to COMPLETED
```

### Layer 3 -- Storage (Delta Lake)

All data resides in Unity Catalog under a single catalog and schema:

```
{catalog}.{schema}/
├── patients              (Dimension)
├── providers             (Dimension)
├── facilities            (Dimension)
├── encounters            (Fact)
├── diagnoses             (Fact)
├── procedures            (Fact)
├── billing               (Fact)
├── readmissions          (Fact)
├── icd10_codes           (Reference)
├── cpt_codes             (Reference)
├── payers                (Reference)
├── departments           (Reference)
├── mv_encounter_summary  (Metric View)
├── mv_revenue_by_payer   (Metric View)
├── mv_readmission_rates  (Metric View)
├── mv_daily_census       (Metric View)
├── mv_department_throughput (Metric View)
├── mv_patient_demographics  (Metric View)
├── simulation_runs       (MC metadata)
├── simulation_trials     (MC Bronze)
└── simulation_results    (MC Gold)
```

---

## Agent Bricks MAS Configuration

The supervisor is defined in `src/databricks/agentbricks/supervisor.py` using the `get_supervisor_config()` function, which returns a configuration dict passed to `manage_mas(action="create_or_update", ...)`.

### Agent Definitions

```python
{
    "name": "Hospital-Monte-Carlo-Supervisor",
    "agents": [
        {
            "name": "encounter_analytics",
            "genie_space_id": "<genie_space_id>",
            "description": "Answers questions about hospital encounter data AND "
                           "previously-run simulation results..."
        },
        {
            "name": "monte_carlo_simulator",
            "uc_function_name": "{catalog}.{schema}.run_simulation",
            "description": "Triggers Monte Carlo simulations or retrieves cached "
                           "results. Supports 5 simulation types..."
        }
    ]
}
```

### Routing Instructions

The supervisor instructions specify parameter construction patterns for each simulation type:

| Simulation Type | Parameter Template |
|---|---|
| `patient_volume` | `{"department": "...", "encounter_type": "...", "forecast_days": N}` |
| `revenue` | `{"facility_id": "...", "months_ahead": N, "volume_change_pct": 0.05, "payer_mix_shift": {"Medicare": -0.10}}` |
| `readmission_risk` | `{"diagnosis_category": "I50", "age_min": 65, "age_max": 120}` |
| `capacity` | `{"facility_id": "...", "additional_beds": 50, "volume_increase_pct": 0.10}` |
| `length_of_stay` | `{"department": "...", "diagnosis_category": "...", "los_reduction_pct": 0.15}` |

### Example-Based Optimization

The file `src/databricks/agentbricks/examples.py` defines 11 example questions with routing guidelines, added via `mas_add_examples_batch()`. These examples help the supervisor learn routing patterns through few-shot examples covering Genie-routed queries, MC-routed queries, and compound queries.

---

## Genie Space Setup

The Genie Space configuration is defined in `src/databricks/genie/space_config.py`.

### Included Tables

The space includes all 12 hospital data tables, all 6 metric views, and 2 simulation result tables (simulation_runs and simulation_results), for a total of 20 queryable objects.

### Custom Instructions

The Genie Space instructions specify:

1. Use metric views (prefixed `mv_`) when the question maps to a standard KPI, leveraging their pre-defined `MEASURE()` dimensions and measures
2. For simulation results, join `simulation_results` with `simulation_runs` to show parameters alongside outcomes
3. Always include relevant context (time periods, departments, encounter types) in query results

### Sample Questions

Ten curated sample questions are defined in `src/databricks/genie/sample_questions.py`, covering volume trends, LOS analysis, readmission rates, revenue breakdowns, demographics, and simulation result queries.

---

## Monte Carlo Pipeline Flow

### Request Flow (End to End)

```
User: "Forecast ER volumes for the next 90 days"
  |
  v
MAS Supervisor: Detects forecast intent -> routes to monte_carlo_simulator
  |
  v
UC Function: run_simulation('patient_volume', '{"department":"Emergency",...}', 10000, 42)
  |
  +---> Compute cache key: SHA-256("patient_volume|{...}|42|10000")
  |
  +---> Check simulation_runs for matching params_hash with status=COMPLETED
  |
  +---> [Cache Hit]  -> Return Gold results as JSON immediately
  |
  +---> [Cache Miss] -> Trigger Databricks Job: monte_carlo_pipeline
         |
         +---> Task 1: Validate params, write run metadata (status=RUNNING)
         |
         +---> Task 2: Create 50-batch seed DataFrame
         |             GroupBy("id").applyInPandas(simulate_fn)
         |             Each executor: 200 trials x forecast period
         |             Write to simulation_trials (Bronze)
         |
         +---> Task 3: Read Bronze, compute percentiles by dimension
                       Write to simulation_results (Gold)
                       Update simulation_runs status=COMPLETED
```

### Distributed Execution Pattern (applyInPandas)

The core simulation engine in `src/databricks/monte_carlo/engine.py` uses Spark's `applyInPandas` to distribute trials across executors:

1. **Seed DataFrame**: `spark.range(num_batches)` creates one row per batch, each with a deterministic seed derived from `base_seed + batch_id`
2. **Broadcast params**: Simulation parameters are broadcast to all executors via `sparkContext.broadcast()`
3. **GroupBy + applyInPandas**: Each batch is processed independently by an executor running the simulation model function
4. **Model function**: Receives a single-row pandas DataFrame (batch metadata) and the broadcast params dict, runs `trials_per_batch` trials using `numpy.random.default_rng(batch_seed)`, returns a pandas DataFrame of trial results

This pattern ensures:
- **Parallelism**: Trials run concurrently across Spark executors
- **Reproducibility**: Each batch has a deterministic seed derived from the base seed
- **Efficiency**: Vectorized numpy operations within each batch

---

## Cache Strategy

### Cache Key Computation

The cache key is a SHA-256 hash of four components:

```
SHA-256( simulation_type | canonicalized_parameters_json | seed | num_simulations )
```

Parameters JSON is canonicalized (sorted keys, no whitespace) before hashing so that `{"a":1,"b":2}` and `{"b":2,"a":1}` produce the same hash.

### Cache Lookup

The `run_simulation` UC Function checks the `simulation_runs` table:

```sql
SELECT run_id, created_at
FROM simulation_runs
WHERE params_hash = '<computed_hash>'
  AND status = 'COMPLETED'
ORDER BY created_at DESC
LIMIT 1
```

If a match is found, the function reads aggregated results from `simulation_results` for that `run_id` and returns them as JSON immediately, without triggering a new job.

### Cache Invalidation

There is no automatic cache invalidation. If the underlying hospital data changes or new simulation models are deployed, previous results remain in the cache. To force a re-run, either:

- Use a different seed value
- Use a different num_simulations value
- Manually delete the matching row from `simulation_runs`

---

## Data Flow Diagrams

### Setup Flow (One-Time)

```
CSV files (data/*.csv)
  |
  v  [Notebook 01]
UC Tables (12 hospital tables)
  |
  v  [Notebook 02]
UC Metric Views (6 semantic views)
  |
  v  [Notebook 03]
UC Function: run_simulation
  |
  v  [Notebook 04]
Simulation Tables (runs, trials, results)
  |
  v  [Notebook 05]
Genie Space (configured with all tables + views)
  |
  v  [Notebook 06]
Agent Bricks MAS (supervisor endpoint)
```

### Query Flow (Runtime)

```
User Question
  |
  v
Agent Bricks MAS (Model Serving endpoint)
  |
  +--[Historical]---> Genie Space ---> SQL over UC Tables/Metric Views ---> Response
  |
  +--[Simulation]---> UC Function: run_simulation
                        |
                        +--[Cached]----> simulation_results (Gold) ---> JSON Response
                        |
                        +--[New]-------> Databricks Job
                                           |
                                           v
                                         simulation_trials (Bronze)
                                           |
                                           v
                                         simulation_results (Gold)
                                           |
                                           v
                                         JSON Response
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Agent Bricks MAS | Over custom LangGraph | Declarative config, native Genie + UC Function sub-agents, built-in routing, UC governance, one-click deploy |
| Job-based MC simulations | Over inline UC functions | Spark-distributed via applyInPandas, batch trials per executor, results persisted in Delta Lake per Databricks MC best practices |
| Single `run_simulation` UC function | Over 5 separate functions | Simplifies MAS config (one agent), centralized cache logic, type dispatching via parameter |
| Delta Lake result tables | Over ephemeral JSON returns | Results queryable by Genie, cacheable, traceable via job_run_id and params_hash |
| Native UC Metric Views | Over regular SQL views | First-class UC object with YAML dimensions + measures, natively consumed by Genie Spaces |
| Seeded generators + committed CSVs | Over runtime-only generation | Deterministic output (seed=42), files committed for inspection and reproducibility |
