# Demo Talk Track

A structured 6-scene demo narrative for presenting the Women's Health Monte Carlo Supervisor. Each scene builds on the previous one, progressing from historical analytics through distribution discovery and Monte Carlo hypothesis testing to compound multi-agent queries.

**Estimated time:** 15-20 minutes for the full walkthrough, 8-10 minutes for the abbreviated version (Scenes 1, 4, 6).

---

## Before You Begin

### Environment Setup

1. Ensure all setup notebooks (00-07) have been run successfully
2. Open the AI Playground connected to the `Womens-Health-MC-Supervisor` endpoint
3. Run at least one Monte Carlo simulation beforehand so Scene 4 has cached results to reference
4. Have the Databricks workspace open in a second tab for showing job runs if needed

### Tips for Presenters

- **Pause after each query** to let the audience read the response before explaining
- **Highlight the routing** -- point out which sub-agent handled each request
- **Show MLflow traces** (optional) to demonstrate observability of the routing decisions
- **Use the exact prompts** provided below, as they are optimized for the supervisor's routing instructions
- **Have a fallback**: If the endpoint is slow, explain the architecture while waiting and show pre-captured screenshots

---

## Scene 1: Historical Cost Analysis

**Goal:** Demonstrate that the supervisor routes historical data questions to the Genie Space for SQL-based analytics over women's health encounter data.

### Setup

> "Let's start with a straightforward analytics question -- the kind of thing you'd normally go to a BI dashboard for. Our data spans three years of women's health encounters across OB/GYN, Endocrinology, Psychiatry, and other departments."

### What to Ask

```
What is the average cost per encounter for OB/GYN patients?
```

### Expected Behavior

- The supervisor routes to `encounter_analytics` (Genie Space)
- Genie queries `mv_wh_cost_by_condition` filtered to OB/GYN encounters
- Returns average cost broken down by encounter type, showing inpatient costs around $15K, outpatient around $1.2K, with an overall blended average
- Payer reimbursement variation visible across Medicare, Medicaid, and commercial plans

### What to Highlight

> "Notice that the supervisor automatically recognized this as a historical data question and routed it to our Genie Space. Genie used the `mv_wh_cost_by_condition` metric view, which has pre-defined dimensions and measures for women's health cost analytics. No one had to write SQL -- the user asked in plain English."

---

## Scene 2: Diagnosis Trending

**Goal:** Show the depth of the clinical data model for trending women's health conditions over time.

### Setup

> "Now let's ask something more clinical -- a question a chief medical officer or women's health program director might ask."

### What to Ask

```
Show me diagnosis prevalence by month for endometriosis in 2025
```

### Expected Behavior

- Routes to `encounter_analytics` (Genie Space)
- Genie queries `mv_wh_diagnosis_prevalence` filtered to endometriosis ICD-10 codes and admission year 2025
- Returns a 12-row monthly breakdown showing diagnosis counts and unique patient volumes
- Seasonal variation visible across the year

### What to Highlight

> "Again, this went straight to Genie. The system understood 'endometriosis' maps to ICD-10 codes in our women's health code set, and 'prevalence by month' maps to the diagnosis prevalence metric view. This is the semantic layer at work -- consistent definitions regardless of who's asking."

---

## Scene 3: Distribution Discovery

**Goal:** Demonstrate the distribution catalog agent -- showing that simulation parameters are fitted from real data, not arbitrary assumptions.

### Setup

> "Before we run a simulation, let's look at what's under the hood. Our Monte Carlo engine uses distribution specs that are fitted from the historical data we just queried. Let's see what's been fitted."

### What to Ask

```
What distributions have been fitted for cost comparison simulations?
```

### Expected Behavior

- The supervisor routes to `distribution_catalog` (UC Function `list_distributions`)
- Returns fitted distribution specs for `cost_comparison` simulation type, including:
  - `inperson_cost`: lognormal distribution (mean=7.63, sigma=1.33) fitted from 50K encounter records
  - Goodness-of-fit metadata: KS statistic, p-value, number of samples
  - Distribution version for cache invalidation

### What to Highlight

> "This is a key differentiator -- our simulation parameters aren't made up. They're fitted from the actual encounter data using scipy. The `inperson_cost` distribution was fitted from 50,000 real encounter billing records. The KS statistic tells us how well the fitted distribution matches the empirical data. And when the data changes, we re-fit and the version bumps, automatically invalidating any cached simulation results."

---

## Scene 4: Virtual Care Cost Comparison (H2)

**Goal:** Demonstrate the Monte Carlo simulation capability through a cost comparison hypothesis -- what happens if we introduce virtual care for women's health?

### Setup

> "Now here's where it gets interesting. So far we've only looked backward. The whole point of this system is to test hypotheses about the future. Hypothesis 2: What's the cost impact of introducing virtual care for women's health patients?"

### What to Ask

```
Compare virtual vs in-person care costs for 50,000 members with 30% virtual penetration
```

### Expected Behavior

- The supervisor detects simulation intent and routes to `simulation_checker` first
- If cached: returns results immediately showing cost comparison metrics
- If not cached: routes to `simulation_trigger`, which calls the UC Function to trigger a Databricks Job, then tells the user to check back in a few minutes
- Re-ask the same question after 3-5 minutes; the supervisor will find cached results
- The MC pipeline runs: validate params, resolve fitted distributions, run 10,000 Spark-distributed trials, aggregate to Gold
- Results show:
  - In-person mean cost: ~$4,924/encounter
  - Virtual blend mean cost: ~$3,670/encounter (25% reduction at 30% virtual penetration)
  - Total costs: in-person ~$616M vs virtual blend ~$459M for 50K members over 12 months

### What to Highlight

> "Watch the routing -- the supervisor first checked if we already have cached results for these exact parameters. Under the hood, the Monte Carlo engine drew per-encounter costs from LogNormal distributions fitted from our actual billing data. The fitted distribution has higher variance than a simple assumption, which gives us realistic confidence intervals."

> "The key result: shifting 30% of encounters to virtual care reduces the blended cost by about 25%. That's $157 million in annual savings for a 50,000-member women's health population. But notice the confidence intervals -- that's the value of running 10,000 trials instead of a single point estimate."

---

## Scene 5: System Cost ROI (H5)

**Goal:** Show multi-year financial projection with ROI analysis -- the executive-level question.

### Setup

> "The cost comparison showed savings per encounter. But the CFO wants to know: if we invest in a virtual care platform, what's the actual return on investment over five years?"

### What to Ask

```
Project the 5-year system cost ROI assuming 8% encounter reduction and a $2B partnership investment
```

### Expected Behavior

- Routes through `simulation_checker` → `simulation_trigger` → informs user to check back in 3-5 minutes
- Simulation models 5 years with labor/expense inflation, encounter reduction (excluding surgical), and applies the $2B investment cost
- Results show:
  - Gross savings: $38-44M/year, growing with inflation
  - Net savings: deeply negative (~-$356M to -$361M/year) because $400M/year amortized cost dwarfs the savings
  - ROI: approximately -0.90
  - Year-over-year variation from fitted `reduction_noise` distribution

### What to Highlight

> "This is exactly the kind of analysis that prevents bad investment decisions. The gross savings are real -- $40M+ per year from reducing encounters. But when you factor in a $2B platform investment amortized over 5 years, the ROI is -90%. The Monte Carlo simulation shows this isn't just a pessimistic estimate -- it's the expected outcome across 10,000 trials with realistic cost variance."

> "The insight here isn't 'don't do virtual care' -- it's 'the investment needs to be right-sized.' A $200M investment with the same encounter reduction would likely show positive ROI. That's the kind of scenario analysis this system enables."

---

## Scene 6: Compound Query

**Goal:** Show the supervisor's ability to decompose a multi-part question, route to different agents, and synthesize results.

### Setup

> "This is the showstopper. In practice, executives don't ask simple questions -- they ask compound questions that mix historical context with forward-looking analysis. Let's see how the supervisor handles that."

### What to Ask

```
What was our OB/GYN cost per encounter last year, and simulate the 5-year ROI at 8% encounter reduction?
```

### Expected Behavior

The supervisor decomposes this into two sequential operations:

1. **Historical lookup** (Genie): Queries `mv_wh_cost_by_condition` for OB/GYN average cost per encounter in 2025. Returns baseline cost metrics by encounter type and payer.

2. **Simulation** (Monte Carlo): Routes through `simulation_checker` → `simulation_trigger` for `system_cost_roi` with 8% encounter reduction. Returns ROI, net savings, and gross savings projections by year.

3. **Synthesis**: The supervisor combines both results, presenting the historical baseline alongside the projected ROI impact.

### What to Highlight

> "This is where the multi-agent architecture really shines. A single question triggered two different agents. First, Genie pulled the historical OB/GYN cost -- that's our baseline. Then the Monte Carlo engine projected the 5-year ROI. The supervisor synthesized both into a coherent response."

> "Without Agent Bricks, you'd need to build custom orchestration logic to decompose this query, route the parts, manage the data flow, and synthesize the response. Here, it's declarative -- we defined four agents and their descriptions, and the supervisor handles the rest."

---

## Wrap-Up Talking Points

After the 6 scenes, summarize the key architectural advantages:

1. **Single conversational interface** -- No switching between BI tools and spreadsheets. Historical analytics, distribution discovery, and probabilistic hypothesis testing live in one endpoint.

2. **Declarative orchestration** -- Agent Bricks MAS routes automatically based on agent descriptions. No custom routing code to maintain.

3. **Data-driven simulations** -- Distribution specs are fitted from historical data using scipy, not hand-tuned assumptions. Re-fitting automatically invalidates cached results.

4. **Databricks-native throughout** -- Unity Catalog tables, Metric Views, Genie Spaces, UC Functions, Databricks Jobs, Delta Lake, MLflow tracing. No external services.

5. **Production-grade Monte Carlo** -- Spark-distributed using `applyInPandas`, deterministic seeding, Bronze-to-Gold medallion architecture, SHA-256-based caching with distribution version awareness.

6. **Women's health focus** -- Purpose-built data model, ICD-10 codes, CPT codes, and metric views for women's health conditions. Demonstrates domain-specific value, not generic analytics.

---

## Common Questions and Answers

**Q: How long does a simulation take?**
A: First run: typically 3-5 minutes depending on cluster size and num_simulations (default 10,000 trials across 50 Spark partitions). The supervisor will trigger the job and ask you to check back after a few minutes. Subsequent identical requests return from cache in under 1 second.

**Q: What simulation types are available?**
A: Four types: `patient_volume` (encounter forecasting), `revenue` (financial projections with payer mix), `cost_comparison` (virtual vs in-person H2 hypothesis), and `system_cost_roi` (multi-year ROI with investment analysis, H5 hypothesis).

**Q: Can Genie run simulations directly?**
A: No. Genie is a SQL analytics tool -- it queries pre-computed results. For new simulations, the supervisor routes to the UC Function which triggers a Databricks Job. Once complete, Genie can query the Gold results table.

**Q: Is the data real?**
A: No. All data is synthetic, generated with deterministic seeding (seed=42) for reproducibility. The data spans April 2023 through March 2026 -- three years of women's health encounters. The distributions are calibrated to be realistic: bimodal age (reproductive/postmenopausal), seasonal encounter patterns, payer-specific reimbursement rates, and WH-focused ICD-10/CPT codes.

**Q: How are distributions fitted?**
A: Notebook `07_fit_distributions.py` runs scipy-based fitting against the historical encounter data. It tries multiple distribution families (normal, lognormal, beta, gamma) and selects the best fit using the Kolmogorov-Smirnov test. Fitted specs are stored in the `distribution_specs` Delta table with versioning and KS metadata.

**Q: How do I add a new simulation type?**
A: Define a new model template in `model_templates.py` using the `sample_from_spec()` pattern, add its configuration to `config.yaml`, register the aggregation config in `results.py`, and update the `VALID_TYPES` list in the UC Function registry. See [docs/simulations.md](simulations.md) for the full guide.

**Q: What happens if the simulation job fails?**
A: The `simulation_runs` table tracks status. If a job fails, the status remains `RUNNING` (or can be updated to `FAILED`). The next request with the same parameters will not find a `COMPLETED` cache entry and will trigger a new job run.

**Q: Can this work with real patient data?**
A: Yes. Replace the synthetic data generation step with your actual data pipeline. The metric views, simulation engine, and MAS configuration are data-agnostic -- they work with any data that matches the expected schema. The distribution fitting pipeline would then produce specs based on real encounter data.
