# Demo Talk Track

A structured 6-scene demo narrative for presenting the Hospital Monte Carlo Supervisor. Each scene builds on the previous one, progressing from simple historical queries through Monte Carlo forecasting to compound analytics-plus-simulation requests.

**Estimated time:** 15-20 minutes for the full walkthrough, 8-10 minutes for the abbreviated version (Scenes 1, 3, 6).

---

## Before You Begin

### Environment Setup

1. Ensure all setup notebooks (00-06) have been run successfully
2. Open the AI Playground connected to the `Hospital-Monte-Carlo-Supervisor` endpoint
3. Run at least one Monte Carlo simulation beforehand so Scene 6 has cached results to reference
4. Have the Databricks workspace open in a second tab for showing job runs if needed

### Tips for Presenters

- **Pause after each query** to let the audience read the response before explaining
- **Highlight the routing** -- point out which sub-agent handled each request
- **Show MLflow traces** (optional) to demonstrate observability of the routing decisions
- **Use the exact prompts** provided below, as they are optimized for the supervisor's routing instructions
- **Have a fallback**: If the endpoint is slow, explain the architecture while waiting and show pre-captured screenshots

---

## Scene 1: Historical Volume Trends

**Goal:** Demonstrate that the supervisor routes historical data questions to the Genie Space for SQL-based analytics.

### Setup

> "Let's start with a straightforward analytics question -- the kind of thing you'd normally go to a BI dashboard for."

### What to Ask

```
Show me total ER encounters by month for 2024
```

### Expected Behavior

- The supervisor routes to `encounter_analytics` (Genie Space)
- Genie queries `mv_encounter_summary` filtered to `Encounter Type = 'Emergency'` and `Admission Year = 2024`
- Returns a 12-row monthly breakdown of ER encounter counts
- Seasonal pattern visible: higher volumes in January-February (flu season) and a dip in summer months

### What to Highlight

> "Notice that the supervisor automatically recognized this as a historical data question and routed it to our Genie Space. Genie used the `mv_encounter_summary` metric view, which has pre-defined dimensions and measures. No one had to write SQL -- the user asked in plain English."

---

## Scene 2: Clinical KPI Lookup

**Goal:** Show the depth of the data model and metric views for clinical analytics.

### Setup

> "Now let's ask something more clinical -- a question a chief medical officer might ask."

### What to Ask

```
What's our average length of stay for cardiac patients?
```

### Expected Behavior

- Routes to `encounter_analytics` (Genie Space)
- Genie joins encounters with diagnoses, filters to cardiology-related ICD-10 codes (I-series), and computes average LOS
- Returns average LOS broken down by encounter type or department
- Typical result: Inpatient cardiac LOS of 4-6 days, aligning with log-normal generation parameters

### What to Highlight

> "Again, this went straight to Genie. The system understood 'cardiac patients' means filtering by cardiology diagnoses, and 'length of stay' maps to a standard KPI in our metric views. This is the semantic layer at work -- consistent definitions regardless of who's asking."

---

## Scene 3: Forward-Looking Forecast

**Goal:** Demonstrate the Monte Carlo simulation capability through a forecasting request.

### Setup

> "Now here's where it gets interesting. So far we've only looked backward. What if the operations team needs to plan ahead?"

### What to Ask

```
Forecast ER patient volumes for the next 90 days
```

### Expected Behavior

- The supervisor detects forecast intent ("forecast", "next 90 days") and routes to `monte_carlo_simulator`
- The UC Function `run_simulation` is called with:
  - `simulation_type = 'patient_volume'`
  - `parameters = '{"department": "Emergency", "forecast_days": 90}'`
  - `num_simulations = 10000`
  - `seed = 42`
- If this is the first run: a Databricks Job is triggered, and the response indicates results will be available shortly
- If cached: returns percentile distributions (p10, p25, p50, p75, p90) immediately

### What to Highlight

> "Watch the routing change -- the supervisor recognized 'forecast' as a simulation request and sent it to the Monte Carlo engine instead of Genie. Under the hood, this triggered a Databricks Job that distributed 10,000 simulation trials across 50 Spark executors. Each trial models daily ER arrivals with seasonal patterns and growth trends. The results give us a probability distribution, not just a single number."

> "If we ask the same question again, it returns instantly from cache -- the system hashes the parameters and checks for a matching completed run."

---

## Scene 4: What-If Capacity Analysis

**Goal:** Show scenario modeling for operational planning.

### Setup

> "Operations is considering expanding capacity. They want to know what happens if they add beds."

### What to Ask

```
What if we add 50 beds -- what's our overflow probability?
```

### Expected Behavior

- Routes to `monte_carlo_simulator`
- UC Function called with `simulation_type = 'capacity'` and `parameters = '{"additional_beds": 50}'`
- Simulation models Poisson admissions against total bed capacity
- Returns probability of overflow (census exceeding capacity) across the forecast horizon

### What to Highlight

> "This is a question no BI dashboard can answer -- it requires running thousands of simulated scenarios. The Monte Carlo engine models daily admissions as a Poisson process and tracks census against bed capacity. The result tells us: with 50 additional beds, what's the probability that we still hit overflow on any given day? That's actionable intelligence for a capital expenditure decision."

---

## Scene 5: Revenue Scenario Modeling

**Goal:** Demonstrate financial what-if analysis with payer mix changes.

### Setup

> "The CFO wants to understand revenue impact of a payer mix shift. Medicare reimbursement rates are lower than commercial -- what happens if the mix changes?"

### What to Ask

```
Compare projected revenue if we shift 10% of Medicare to managed care
```

### Expected Behavior

- Routes to `monte_carlo_simulator`
- UC Function called with `simulation_type = 'revenue'` and a `payer_mix_shift` parameter
- Simulation models per-encounter revenue with payer-specific reimbursement rates and denial probabilities
- Returns revenue distribution showing the projected impact of the payer mix change

### What to Highlight

> "The model uses log-normal revenue distributions with payer-specific parameters. Medicare reimburses at about 78 cents on the dollar, while commercial plans run 85-88%. Shifting 10% of volume from Medicare to commercial should increase net revenue, but by how much? The Monte Carlo simulation gives us the full probability distribution -- the expected value and the uncertainty range."

---

## Scene 6: Compound Query

**Goal:** Show the supervisor's ability to decompose a multi-part question, route to different agents, and synthesize results.

### Setup

> "This is the showstopper. In practice, executives don't ask simple questions -- they ask compound questions that mix historical context with forward-looking analysis. Let's see how the supervisor handles that."

### What to Ask

```
What was readmission rate last year, and simulate what happens with 15% LOS reduction?
```

### Expected Behavior

The supervisor decomposes this into two sequential operations:

1. **Historical lookup** (Genie): Queries `mv_readmission_rates` for the 30-day readmission rate in the prior year. Returns baseline metrics by department.

2. **Simulation** (Monte Carlo): Calls `run_simulation` with `simulation_type = 'length_of_stay'` and `parameters = '{"los_reduction_pct": 0.15}'`. Models the effect of reducing LOS by 15% across departments.

3. **Synthesis**: The supervisor combines both results, presenting the historical baseline alongside the projected impact.

### What to Highlight

> "This is where the multi-agent architecture really shines. A single question triggered two different agents. First, Genie pulled the historical readmission rate -- that's our baseline. Then the Monte Carlo engine simulated what happens if we implement a program that reduces length of stay by 15%. The supervisor synthesized both into a coherent response."

> "Without Agent Bricks, you'd need to build custom orchestration logic to decompose this query, route the parts, manage the data flow, and synthesize the response. Here, it's declarative -- we defined two agents and their descriptions, and the supervisor handles the rest."

---

## Wrap-Up Talking Points

After the 6 scenes, summarize the key architectural advantages:

1. **Single conversational interface** -- No switching between BI tools and spreadsheets. Historical analytics and probabilistic forecasting live in one endpoint.

2. **Declarative orchestration** -- Agent Bricks MAS routes automatically based on agent descriptions. No custom routing code to maintain.

3. **Databricks-native throughout** -- Unity Catalog tables, Metric Views, Genie Spaces, UC Functions, Databricks Jobs, Delta Lake, MLflow tracing. No external services.

4. **Production-grade simulation** -- Spark-distributed Monte Carlo using `applyInPandas`, deterministic seeding, Bronze-to-Gold medallion architecture, SHA-256-based caching.

5. **Semantic consistency** -- UC Metric Views provide a single source of truth for KPI definitions. Whether Genie or a human analyst queries the data, the calculations are the same.

---

## Common Questions and Answers

**Q: How long does a simulation take?**
A: First run: typically 2-5 minutes depending on cluster size and num_simulations (default 10,000 trials across 50 batches). Subsequent identical requests return from cache in under 1 second.

**Q: Can Genie run simulations directly?**
A: No. Genie is a SQL analytics tool -- it queries pre-computed results. For new simulations, the supervisor routes to the UC Function which triggers a Databricks Job. Once complete, Genie can query the Gold results table.

**Q: Is the data real?**
A: No. All data is synthetic, generated with deterministic seeding (seed=42) for reproducibility. The distributions are calibrated to be realistic: bimodal age, seasonal encounter patterns, payer-specific reimbursement rates, and realistic readmission rates.

**Q: How do I add a new simulation type?**
A: Define a new simulation function in `src/databricks/monte_carlo/engine.py` using the `@_register` decorator, define the output schema, add an aggregation config entry in `results.py`, and update the `VALID_TYPES` list in the UC Function. See [docs/simulations.md](simulations.md) for the full guide.

**Q: What happens if the simulation job fails?**
A: The `simulation_runs` table tracks status. If a job fails, the status remains `RUNNING` (or can be updated to `FAILED`). The next request with the same parameters will not find a `COMPLETED` cache entry and will trigger a new job run.

**Q: Can this work with real hospital data?**
A: Yes. Replace the synthetic data generation step with your actual data pipeline. The metric views, simulation engine, and MAS configuration are data-agnostic -- they work with any data that matches the expected schema.
