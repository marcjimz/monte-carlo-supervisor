# Monte Carlo Simulations

This document covers the Monte Carlo simulation methodology, the five simulation types and their statistical distributions, the Spark-distributed execution pattern, the Bronze-to-Gold results pipeline, the caching strategy, and how to add new simulation types.

---

## Methodology Overview

Monte Carlo simulation estimates the probability distribution of an outcome by running a large number of randomized trials, each sampling from statistical distributions calibrated to historical data. Rather than producing a single point forecast ("ER volume will be 3,200 next month"), it produces a probability distribution ("ER volume will be between 2,800 and 3,600 with 80% confidence").

This project runs simulations on Spark using the `groupBy().applyInPandas()` pattern, which distributes trial batches across executors for parallel computation. Each batch uses a deterministic seed derived from a base seed, ensuring full reproducibility.

### Key Properties

- **Stochastic**: Each trial samples from probability distributions, producing different outcomes
- **Distributed**: Trials are partitioned into batches executed in parallel across Spark executors
- **Reproducible**: Deterministic seeding ensures identical results given the same parameters and seed
- **Cached**: Results are stored in Delta Lake with SHA-256-based cache keys for instant retrieval on repeat requests

### Default Configuration

| Parameter | Default Value | Description |
|---|---|---|
| `num_simulations` | 10,000 | Total number of Monte Carlo trials |
| `num_batches` | 50 | Number of Spark partitions (one batch per executor) |
| `trials_per_batch` | 200 | Trials per batch (num_simulations / num_batches) |
| `seed` | 42 | Base random seed |

---

## Simulation Types

### 1. patient_volume

**Purpose:** Forecast monthly patient encounter volumes with growth trends and seasonal patterns.

**Statistical Model:**

For each trial and each forecast month `m`:

```
growth_factor = 1.0 + growth_rate * (m / 12.0)
seasonal_factor = 1.0 + seasonality_amp * sin(2 * pi * (m - 1) / 12.0)
adjusted_mean = monthly_mean * growth_factor * seasonal_factor
simulated_volume = Normal(adjusted_mean, monthly_std)
```

The model combines three components:
- **Baseline**: Historical mean monthly encounters (default: 10,000)
- **Growth trend**: Linear year-over-year growth (default: 3%)
- **Seasonality**: Sinusoidal seasonal pattern (default amplitude: 12%) peaking in winter months

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `monthly_mean` | float | 10,000 | Average encounters per month |
| `monthly_std` | float | 1,500 | Std-dev of monthly encounters |
| `growth_rate` | float | 0.03 | Year-over-year growth rate |
| `seasonality_amp` | float | 0.12 | Amplitude of seasonal sine wave |
| `num_months` | int | 12 | Forecast horizon in months |

**Output schema:** `batch_id long, trial_id long, month string, simulated_encounters double`

**Aggregation dimension:** `month` -- Gold results show percentiles for each forecast month.

---

### 2. revenue

**Purpose:** Project monthly revenue and charges under different payer mix and denial rate assumptions.

**Statistical Model:**

For each trial and each forecast month:

```
gross_charges = Normal(avg_revenue * charge_ratio, revenue_std * charge_ratio)
denied_fraction = Beta(2, (2 / denial_rate) - 2)
net_revenue = gross_charges * (1.0 - denied_fraction) / charge_ratio
```

The model captures:
- **Charge generation**: Normal distribution around baseline revenue scaled by charge-to-revenue ratio (default: 1.35x)
- **Denial uncertainty**: Beta distribution centered on historical denial rate (default: 8%), capturing the stochastic nature of claims processing
- **Net revenue**: Gross charges minus denied portion, divided by charge ratio

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `avg_monthly_revenue` | float | 12,000,000 | Baseline monthly revenue |
| `revenue_std` | float | 2,000,000 | Std-dev of monthly revenue |
| `avg_charge_to_rev` | float | 1.35 | Charge-to-revenue ratio |
| `denial_rate` | float | 0.08 | Claim denial rate |
| `num_months` | int | 12 | Forecast horizon in months |

**Output schema:** `batch_id long, trial_id long, month string, simulated_revenue double, simulated_charges double`

**Aggregation dimension:** `month` -- Gold results show revenue and charge percentiles per month.

---

### 3. length_of_stay

**Purpose:** Simulate average length-of-stay distributions by department under current or modified conditions.

**Statistical Model:**

For each trial and each department:

```
los_samples = LogNormal(mu, sigma, size=patients_per_trial)
simulated_avg_los = mean(los_samples)
```

Where `(mu, sigma)` are department-specific log-normal parameters. The log-normal distribution is a natural fit for LOS data, which is right-skewed (most stays are short, a few are very long).

**Department-specific parameters (mu, sigma):**

| Department | mu | sigma | Approx. Median (days) |
|---|---|---|---|
| Emergency | 0.0 | 0.3 | 1.0 |
| Cardiology | 1.4 | 0.6 | 4.1 |
| Orthopedics | 1.5 | 0.7 | 4.5 |
| General Surgery | 1.2 | 0.7 | 3.3 |
| Internal Medicine | 1.1 | 0.6 | 3.0 |
| Pediatrics | 0.8 | 0.5 | 2.2 |
| Oncology | 1.6 | 0.8 | 5.0 |
| Neurology | 1.3 | 0.7 | 3.7 |
| Intensive Care | 1.8 | 0.9 | 6.0 |
| Pulmonology | 1.3 | 0.6 | 3.7 |

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `departments` | list[str] | 10 common departments | Departments to simulate |
| `los_baseline` | dict | Department-specific (mu, sigma) | Log-normal parameters per department |
| `patients_per_trial` | int | 500 | Patients sampled per department per trial |

**Output schema:** `batch_id long, trial_id long, department string, simulated_avg_los double`

**Aggregation dimension:** `department` -- Gold results show LOS percentiles per department.

---

### 4. readmission_rate

**Purpose:** Simulate 30-day readmission rates by department using binomial models.

**Statistical Model:**

For each trial and each department:

```
readmissions = Binomial(discharges_per_trial, base_rate)
simulated_rate = readmissions / discharges_per_trial
```

The binomial distribution models each discharge as an independent Bernoulli trial with department-specific readmission probability. The per-trial rate naturally varies around the base rate, producing realistic uncertainty distributions.

**Department-specific base rates:**

| Department | Base Readmission Rate |
|---|---|
| Emergency | 15% |
| Cardiology | 18% |
| Orthopedics | 8% |
| General Surgery | 12% |
| Internal Medicine | 14% |
| Pediatrics | 6% |
| Oncology | 20% |
| Neurology | 16% |
| Intensive Care | 22% |
| Pulmonology | 17% |

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `departments` | list[str] | 10 common departments | Departments to simulate |
| `base_readmission_rate` | dict | Department-specific rates | Base rate per department |
| `discharges_per_trial` | int | 300 | Discharges sampled per department per trial |

**Output schema:** `batch_id long, trial_id long, department string, simulated_readmission_rate double`

**Aggregation dimension:** `department` -- Gold results show readmission rate percentiles per department.

---

### 5. ed_wait_time

**Purpose:** Simulate emergency department wait times by hour of day, accounting for peak-hour congestion.

**Statistical Model:**

For each trial and each hour (0-23):

```
mean_wait = base_wait * (peak_multiplier if hour in peak_hours else 1.0)
shape = (mean_wait / 15.0) ^ 2
scale = mean_wait / shape
wait_samples = Gamma(shape, scale, size=patients_per_hour)
simulated_avg_wait = mean(wait_samples)
```

The Gamma distribution is used because:
- It produces strictly positive values (wait times cannot be negative)
- It is right-skewed (a few patients wait much longer than average)
- Shape and scale can be parameterized from the desired mean

Peak hours (default: 10:00-14:00 and 18:00-21:00) have wait times multiplied by a peak factor (default: 2x).

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `base_wait_minutes` | float | 45 | Baseline mean wait in minutes |
| `peak_multiplier` | float | 2.0 | Multiplier during peak hours |
| `peak_hours` | list[int] | [10-14, 18-21] | Hours (0-23) considered peak |
| `patients_per_hour` | int | 50 | Patients sampled per hour per trial |

**Output schema:** `batch_id long, trial_id long, hour_of_day int, simulated_wait_minutes double`

**Aggregation dimension:** `hour_of_day` -- Gold results show wait time percentiles per hour.

---

## Distributed Execution Pattern (applyInPandas)

The simulation engine in `src/databricks/monte_carlo/engine.py` distributes trial computation across Spark executors using the `applyInPandas` pattern.

### Step-by-Step Execution

**Step 1: Create seed DataFrame**

```python
seed_df = spark.range(num_batches).withColumn("batch_seed", col("id") + lit(base_seed))
```

This produces a DataFrame with `num_batches` rows (default: 50), each containing a batch index `id` and a deterministic `batch_seed` derived from the base seed.

**Step 2: Broadcast parameters**

```python
bc_params = spark.sparkContext.broadcast(params)
```

Simulation parameters are broadcast to all executors, avoiding serialization overhead per partition.

**Step 3: Apply simulation function**

```python
def _apply_fn(pdf: pd.DataFrame) -> pd.DataFrame:
    return model_fn(pdf, bc_params.value)

trials_df = seed_df.groupBy("id").applyInPandas(_apply_fn, schema=output_schema)
```

Each executor receives a single-row pandas DataFrame (one batch), initializes a `numpy.random.default_rng` with that batch's seed, and runs `trials_per_batch` trials. The output is a pandas DataFrame matching the declared schema.

**Step 4: Collect results**

The resulting Spark DataFrame contains all trial results across all batches. It is written to the `simulation_trials` Bronze table.

### Why applyInPandas?

- **Natural parallelism**: Each batch runs independently on its own executor
- **NumPy vectorization**: Simulation logic uses vectorized numpy operations within each batch
- **Deterministic seeding**: Each batch has a unique seed derived from the base seed, ensuring reproducibility regardless of executor assignment
- **Schema enforcement**: The output schema is declared upfront, catching schema mismatches early

### Performance Characteristics

With default settings (10,000 trials, 50 batches, 200 trials per batch):

- Each executor processes 200 trials independently
- For `patient_volume` with 12 months: each batch produces 2,400 rows (200 trials x 12 months)
- Total Bronze rows: 120,000 (50 batches x 2,400 rows)
- Typical execution time: 30 seconds to 2 minutes on a 10-worker cluster

---

## Result Tables (Bronze / Gold)

The results pipeline follows a medallion architecture, implemented in `src/databricks/monte_carlo/results.py`.

### Bronze: simulation_trials

Raw trial-level results from every simulation. Each row represents one simulated outcome for one trial at one dimension value (e.g., one month, one department, one hour).

The table is a wide union schema -- columns for all simulation types are present, but only the columns relevant to the simulation type are populated. For example, a `patient_volume` run populates `month` and `simulated_encounters` while leaving `department`, `simulated_avg_los`, etc. as NULL.

**Written by:** `write_bronze_trials()` in the mc_02_simulate job task.

### Gold: simulation_results

Aggregated percentile distributions grouped by the natural dimension for each simulation type:

| Simulation Type | Group Key | Value Column |
|---|---|---|
| `patient_volume` | month | simulated_encounters |
| `revenue` | month | simulated_revenue |
| `length_of_stay` | department | simulated_avg_los |
| `readmission_rate` | department | simulated_readmission_rate |
| `ed_wait_time` | hour_of_day | simulated_wait_minutes |

**Percentiles computed:** p05, p10, p25, p50 (median), p75, p90, p95

**Additional statistics:** mean, std, min, max, num_trials

**Written by:** `aggregate_to_gold()` in the mc_03_aggregate job task.

**Queried by:**
- The `run_simulation` UC Function for cached result retrieval
- The Genie Space for natural-language queries about past simulation results

---

## Caching Strategy

### Cache Key

The cache key is a SHA-256 hash computed from four components:

```python
payload = f"{simulation_type}|{canonical_params}|{seed}|{num_simulations}"
cache_key = hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

The parameters JSON is canonicalized before hashing: parsed, re-serialized with sorted keys and no whitespace. This ensures that `{"a": 1, "b": 2}` and `{"b": 2, "a": 1}` produce the same cache key.

### Cache Lookup

The `run_simulation` UC Function and the mc_01_validate job task both check the cache:

```sql
SELECT run_id, created_at
FROM simulation_runs
WHERE params_hash = '<cache_key>'
  AND status = 'COMPLETED'
ORDER BY created_at DESC
LIMIT 1
```

### Cache Behavior

| Scenario | Behavior |
|---|---|
| Same type + params + seed + count | Cache hit -- return Gold results immediately |
| Same type + params, different seed | Cache miss -- new run with different random stream |
| Same type + params, different count | Cache miss -- different number of trials |
| Any parameter change | Cache miss -- different hash |

### Cache Invalidation

There is no automatic TTL or invalidation. Cached results persist until:
- A row is manually deleted from `simulation_runs`
- A different seed or trial count is used (creates a new cache entry)
- The table is truncated

For production use, consider adding a TTL check (e.g., ignore results older than 24 hours) by adding a timestamp filter to the cache lookup query.

---

## How to Add a New Simulation Type

Follow these steps to add a new simulation model to the engine.

### Step 1: Define the simulation function

In `src/databricks/monte_carlo/engine.py`, add a new function decorated with `@_register`:

```python
# Define the output schema (Spark DDL string)
_TRIAL_SCHEMA_NEW_TYPE = (
    "batch_id long, trial_id long, dimension_col string, simulated_metric double"
)

@_register("new_type", _TRIAL_SCHEMA_NEW_TYPE)
def _simulate_new_type(pdf: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Simulate [description].

    Parameters (in *params*):
        param_a            - description (default X)
        param_b            - description (default Y)
        trials_per_batch   - injected automatically by engine
    """
    batch_id = int(pdf["id"].iloc[0])
    seed = int(pdf["batch_seed"].iloc[0])
    rng = np.random.default_rng(seed)

    param_a = params.get("param_a", default_value)
    trials_per_batch = params.get("trials_per_batch", 200)

    rows: list[dict] = []
    for trial in range(trials_per_batch):
        # Your simulation logic here
        value = rng.normal(param_a, 1.0)
        rows.append({
            "batch_id": batch_id,
            "trial_id": batch_id * trials_per_batch + trial,
            "dimension_col": "some_value",
            "simulated_metric": value,
        })
    return pd.DataFrame(rows)
```

The `@_register("new_type", schema)` decorator automatically adds the function to the engine's registry.

### Step 2: Add aggregation configuration

In `src/databricks/monte_carlo/results.py`, add an entry to `_AGG_CONFIG`:

```python
_AGG_CONFIG: dict[str, tuple[str, str]] = {
    # ... existing entries ...
    "new_type": ("simulated_metric", "dimension_col"),
}
```

This tells the Gold aggregation which column to compute percentiles on and which column to group by.

### Step 3: Add columns to simulation_trials (if needed)

If your simulation outputs new columns not already in the wide Bronze table, add them to the `get_simulation_tables_ddl()` function in `results.py`:

```sql
simulated_metric   DOUBLE   COMMENT 'Simulated metric for new_type'
dimension_col      STRING   COMMENT 'Dimension for new_type'
```

### Step 4: Update the UC Function

In `src/databricks/sql/functions/monte_carlo/run_simulation.py`, add the new type to `VALID_TYPES`:

```python
VALID_TYPES = [
    "patient_volume", "revenue", "readmission_risk",
    "capacity", "length_of_stay", "new_type"
]
```

### Step 5: Update the supervisor instructions

In `src/databricks/agentbricks/supervisor.py`, add the new type's parameter template to the routing instructions so the supervisor knows how to construct parameters for the new simulation.

### Step 6: Add examples

In `src/databricks/agentbricks/examples.py`, add example questions that demonstrate when to route to the new simulation type.

### Step 7: Test

Add test cases to `tests/test_mc_functions.py` to verify the new simulation function produces the correct output schema and deterministic results with a fixed seed.
