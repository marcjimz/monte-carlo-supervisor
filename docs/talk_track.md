# Demo Talk Track — Agentic Simulations UI

A 5-scene walkthrough of the Monte Carlo Simulation app, demonstrated end-to-end through the Databricks Apps UI. Each scene builds on the previous, progressing from data exploration through simulation execution, parameter sweep analysis, agent-powered conversation, and finally publishing for collaboration.

**App URL:** https://monte-carlo-ui-7405611426422298.18.azure.databricksapps.com

**Estimated time:** 12-15 minutes full walkthrough, 7-8 minutes abbreviated (Scenes 1, 3, 5).

---

## Before You Begin

### Pre-Demo Prep (do this 30 min before)

1. **Reseed demo data** to ensure a clean state. Open the browser console (F12) on the app and run:
   ```js
   fetch('/api/admin/reseed', { method: 'POST' }).then(r => r.json()).then(console.log)
   ```
   Or re-deploy the app (seed runs automatically on startup).
   This creates two analyses:
   - **Virtual Care Cost Impact Study** (Ali, published) — the completed showcase
   - **Postpartum Care Virtual Pilot** (you, draft) — the one you'll walk through live

2. **Pre-cache simulations** so they return instantly during the demo. Go to the **Simulations** page in the app and run these two:
   - **Cost Comparison**: member_count=50000, virtual_penetration=0.30, annual_encounter_rate=2.5, num_months=12 → Run Simulation
   - **Cost Comparison**: member_count=50000, virtual_penetration=0.40, annual_encounter_rate=2.5, num_months=12 → Run Simulation

   Wait ~5 min for each to complete. Verify they appear as "Completed" in the simulations list.

3. **Open the app** and confirm you see both analyses on the Analyses page.

4. **Open a second tab** to the Databricks workspace if you want to show job runs during Scene 2.

### Tips for Presenters

- **Pause after each action** to let the audience see the result before narrating
- **Click slowly and deliberately** — the audience needs to follow your cursor
- **Don't rush the heatmap** — the color gradient across cells is the visual payoff of Scene 3
- **Have the pre-cached sims ready** — if a simulation isn't cached, it takes 3-5 minutes and kills the demo pacing
- **Fallback**: If the MAS endpoint is slow in Scene 4, narrate the architecture while waiting. Show Ali's pre-seeded conversation as a backup.

---

## Scene 1: Explore Your Data

**Goal:** Show the embedded AI/BI dashboard with real-time KPIs, then use Genie to ask natural language questions and reveal the generated SQL.

**Time:** 3-4 minutes

### Setup Narration

> "Let's start where every analysis begins — understanding the data. We have three years of women's health encounter data across OB/GYN, Endocrinology, Psychiatry, and more. Rather than building dashboards from scratch, we embedded a Databricks AI/BI Lakeview dashboard directly into the app."

### Click Path

1. **Analyses page** → Click **"Postpartum Care Virtual Pilot"** (your draft analysis)
2. You land on the **"Explore & Chat with your Data"** tab — the AI/BI dashboard fills the page
3. Scroll through the dashboard widgets:
   - Point out the KPI tiles at the top (total encounters, unique patients, avg cost)
   - Show the volume trend chart (monthly encounters over 3 years)
   - Highlight the cost breakdown by department and payer mix charts
4. Click the **Genie chat icon** in the bottom-right corner of the embedded dashboard
5. Type this question into Genie:

```
What is the average cost per encounter for OB/GYN patients by payer type?
```

6. Wait for Genie to respond with a table of results
7. Click **"Show SQL"** (or the code icon) in Genie's response to reveal the generated query

### What to Highlight

> "Notice a few things here. First, this dashboard is a native Databricks Lakeview dashboard embedded directly in our app — no iframes to a separate BI tool. Second, when I asked Genie a question, it didn't just look up a pre-built answer. It wrote SQL against our metric views — `mv_wh_cost_by_condition` — and executed it in real time. The SQL is right here. This is the semantic layer at work: consistent definitions regardless of who's asking."

> "Now I know the historical baselines. OB/GYN inpatient encounters cost roughly $15K, outpatient around $1.2K. Commercial payers reimburse differently than Medicare. This context is critical before we start running simulations."

### Optional Follow-up Question

If time permits, ask Genie a second question to show breadth:

```
Show me the top 5 chronic conditions by total encounter volume in the last 12 months
```

> "Again — plain English to SQL, instant results. This is powered by the same Genie Space that our Multi-Agent Supervisor routes to programmatically in Scene 4."

---

## Scene 2: Run a Simulation

**Goal:** Show the Simulation Builder — select a type, configure parameters with fitted distributions, trigger execution, and inspect results.

**Time:** 3-4 minutes

### Setup Narration

> "Now that we understand the historical data, let's test a hypothesis. Postpartum patients currently have mostly in-person follow-ups. What if we shifted 30% of those encounters to virtual? How much would the blended cost change? Let's build a simulation to find out."

### Click Path

1. Click **"Simulations"** in the left sidebar (this is the global simulations page)
2. Click **"New Simulation"** button
3. Fill out the simulation builder form:
   - **Simulation Type:** select **"Cost Comparison"**
   - Point out the description that appears: *"Compare virtual vs in-person care costs..."*
   - **Parameters**: the form auto-populates from `config.yaml`:
     - `member_count`: **50000**
     - `virtual_penetration`: **0.30**
     - `annual_encounter_rate`: **2.5**
     - `num_months`: **12**
   - Point out the **Distributions** section below the parameters:
     - `In-Person Cost`: Log-Normal (Mean=7.63, Std Dev=1.33) — *fitted from historical data*
     - `Virtual Cost`: Normal (Mean=150, Std Dev=30)

> "Notice these distributions aren't arbitrary assumptions. The in-person cost distribution was fitted from 50,000 actual billing records using scipy. It's a Log-Normal — which makes sense, because healthcare costs are right-skewed with occasional high outliers. If you want to customize, you check the 'Customize' box and change the type or parameters."

4. Leave **Trials** at 10,000 and **Seed** at 42
5. Click **"Run Simulation"**
6. Show the green confirmation with the Job Run ID

> "Under the hood, this called a Unity Catalog function which triggered a Databricks Job. The job validates parameters, resolves fitted distributions from the Delta table, runs 10,000 Spark-distributed Monte Carlo trials, and writes results to Gold tables."

7. Scroll down to see the **simulations table** — point out your run appearing (it should show "Completed" if pre-cached)
8. Click the **Run ID** link to open the simulation detail page
9. Walk through the detail page:
   - **Parameters card**: shows the exact config used
   - **Distributions card**: shows which distributions were used (fitted vs custom)
   - **Results table**: mean, P05, P50, P95 for each metric by group (in-person vs virtual vs blended)
   - **Bar chart**: visual comparison

### What to Highlight

> "The simulation ran 10,000 trials. The blended cost at 30% virtual penetration is approximately $1,020 per encounter — that's a 7% reduction from the baseline. But look at the confidence intervals — P05 to P95 gives us the range of likely outcomes. This isn't a single-point spreadsheet estimate. It's a statistically robust projection with realistic variance from fitted distributions."

---

## Scene 3: Build a Parameter Sweep Matrix

**Goal:** Create a matrix that evaluates multiple scenarios simultaneously, then show the heatmap visualization with cross-cell comparison.

**Time:** 3-4 minutes

### Setup Narration

> "One simulation tells us about one scenario. But the real question is: how does cost change across different penetration rates AND different population sizes? Let's build a parameter sweep matrix to evaluate all combinations at once."

### Click Path

1. Click **"Analyses"** in the sidebar → click **"Postpartum Care Virtual Pilot"**
2. Click the **"Matrices"** tab
3. Click **"+ New Matrix"**
4. Fill out the matrix builder:
   - **Name**: `Penetration vs Population Sweep`
   - **Simulation Type**: Cost Comparison
   - **Row Parameter**: `virtual_penetration`
   - **Row Start**: `0.20` | **Row End**: `0.40` | **Row Step**: `0.10`
   - **Column Values**: `30000, 50000, 70000`
   - **Column Parameter**: `member_count`
   - **Output Metric**: `simulated_cost_per_encounter`
   - **Group Key**: `care_model` | **Group Value**: `blended`

> "I'm sweeping virtual penetration from 20% to 40% in 10-point increments, across three population sizes. That's 9 scenarios — each running 10,000 Monte Carlo trials. The output metric is blended cost per encounter."

5. Click **"Create Matrix"**
6. The matrix appears with all cells in "Pending" status
7. Click **"Run All (9)"**
8. Show cells transitioning from Pending → Running → Completed
   - If pre-cached, cells fill in instantly with results
   - Point out the **heatmap gradient** — darker cells = higher cost, lighter = lower

> "Watch the heatmap form. Each cell shows the mean cost with P05-P95 confidence bands. The gradient runs across ALL cells — not per-row — so you can instantly see where the sweet spots are."

9. Point out specific cells:
   - **20% penetration, 30K members**: ~$1,102 (darkest — highest cost)
   - **40% penetration, 70K members**: ~$955 (lightest — lowest cost)
   - The progression is clear across both axes

10. Show the **legend footer**: metric name, trial count, seed, gradient bar
11. Click **"Reverse"** to flip the heatmap coloring

### What to Highlight

> "This is the power of the matrix view. In one glance, you can see that increasing virtual penetration consistently reduces cost, and the effect is stable across population sizes. The 40% row is uniformly lighter than the 20% row. The confidence intervals — those P5 and P95 numbers in each cell — tell you this isn't noise. The trend is statistically robust across 90,000 total trials."

> "You can also edit the matrix name and add a description — click the pencil icon — so when you publish this analysis, collaborators know exactly what they're looking at."

---

## Scene 4: Agent Mode

**Goal:** Open the agent chat drawer and interact with the Multi-Agent Supervisor to ask historical and simulation questions conversationally — showing that everything in Scenes 1 and 2 can be done through natural language.

**Time:** 3-4 minutes

### Setup Narration

> "Everything we just did — querying historical data, running simulations — required clicking through forms and dashboards. But what if you could just ask? Our Multi-Agent Supervisor routes questions to the right agent automatically: Genie for historical analytics, simulation agents for Monte Carlo, and a distribution catalog for understanding the underlying models."

### Click Path

1. Click the **chat bubble icon** (MessageSquare) in the top-right corner of the analysis page
2. The **Agent Chat** drawer slides open from the right
3. Click **"Start a conversation"** (or the + icon to create a new thread)
4. Rename the thread: click the pencil icon → type **"Postpartum Analysis"** → Enter

**Question 1 — Historical data (routes to Genie):**

5. Type:

```
What is the average cost per encounter for OB/GYN patients?
```

6. Wait for the response. The MAS routes this to the `encounter_analytics` agent (Genie Space), which generates SQL and returns results.

> "Same question I asked the dashboard earlier, but now through the agent. The supervisor recognized this as a historical data question and routed it to Genie automatically. No one told it which agent to use."

**Question 2 — Simulation (routes to simulation agents):**

7. Type:

```
Compare virtual vs in-person care costs for 50,000 members with 40% virtual penetration
```

8. Wait for the response. The MAS first checks cached results via `simulation_checker`, finds the pre-cached run, and returns results immediately.

> "Now watch — this time it routed to the simulation agents. First it checked the cache and found that we already ran this exact scenario. The results came back instantly: blended cost drops to roughly $950 per encounter at 40% penetration, a 13% reduction. No form filling, no navigating to the simulations page. Just a question."

**Question 3 (optional) — Compound query:**

9. If time permits, type:

```
What was our OB/GYN cost per encounter last year, and how does it compare to the simulated cost at 30% virtual penetration?
```

> "This is the payoff of multi-agent orchestration. One question, two agents: Genie pulled the historical baseline, the simulation agent pulled the projected cost, and the supervisor synthesized both into a coherent comparison. That's what Agent Bricks does — declarative routing, no custom orchestration code."

### What to Highlight

> "Everything you see in this chat is backed by the same infrastructure: Genie Spaces for analytics, Unity Catalog functions for simulation triggers, and Delta Lake for results storage. The difference is that instead of navigating through UI tabs, the agent handles the routing. Both modalities — UI-driven and agent-driven — coexist in the same app."

---

## Scene 5: Publish & Share

**Goal:** Publish the analysis so collaborators can view it, then show the read-only viewer experience.

**Time:** 1-2 minutes

### Setup Narration

> "We've explored data, run simulations, built a matrix, and had an agent conversation — all within this draft analysis. Now let's share it with the team."

### Click Path

1. Close the chat drawer (click X)
2. Point out the **"draft"** badge next to the analysis name in the header
3. Click the **"Publish"** button (top-right, next to the chat icon)
4. The badge changes from "draft" to **"published"** (green)

> "Published. Now anyone in the organization can see this analysis — the dashboard, the matrix with its heatmap, the simulation results, and the full agent conversation thread."

5. Click **"Analyses"** in the sidebar to go back to the list
6. Point out both analyses are now published:
   - **Virtual Care Cost Impact Study** (Ali) — the completed showcase
   - **Postpartum Care Virtual Pilot** (you) — the one you just walked through
7. *(Optional)* Click into Ali's analysis to show the viewer experience:
   - No pencil icons (can't edit)
   - No "Run All" buttons on the matrix
   - No "New Matrix" builder
   - Can still view the heatmap, read the agent conversation, and explore the dashboard

### What to Highlight

> "Two things to notice. First, publishing is one click — there's no export, no screenshot, no 'attach to email' workflow. The analysis is live and interactive. Second, the viewer experience is read-only but full-fidelity: they see the same heatmap, the same confidence intervals, the same agent conversation. The data doesn't degrade when you share it."

---

## Wrap-Up Talking Points

After the 5 scenes, summarize the key takeaways:

1. **Full-stack Databricks App** — FastAPI + React SPA, deployed as a Databricks App with Lakebase (Postgres), OAuth authentication, and embedded AI/BI dashboards. No external infrastructure.

2. **Two modalities** — Everything can be done through the UI (dashboards, forms, matrices) OR through the agent chat. Users choose the interaction style that fits their workflow.

3. **Data-driven simulations** — Distribution parameters are fitted from historical encounter data using scipy, stored in versioned Delta tables. The Monte Carlo engine samples from these fitted distributions, not hand-tuned assumptions.

4. **Parameter sweep matrices** — Evaluate entire hypothesis spaces in one click. The heatmap visualization makes cross-scenario comparison instant and intuitive.

5. **Agent Bricks MAS** — Multi-Agent Supervisor routes questions to the right agent automatically: Genie for analytics, simulation agents for Monte Carlo, distribution catalog for model transparency. No custom routing code.

6. **Publish and collaborate** — Draft → Published with one click. Read-only viewers see full-fidelity results without the ability to modify.

---

## Common Questions

**Q: How long does a simulation take?**
First run: 3-5 minutes (Spark-distributed, 10,000 trials across 50 partitions). Subsequent identical requests return from cache in under 1 second. The matrix "Run All" triggers all cells concurrently (batched in groups of 3).

**Q: Can I customize the distributions?**
Yes. The Simulation Builder has a "Customize" toggle on each distribution. You can change the type (normal, lognormal, beta, gamma, uniform) and parameters. Uncustomized distributions use values fitted from historical data.

**Q: Is the data real?**
No. All data is synthetic, generated with deterministic seeding for reproducibility. Three years of women's health encounters with realistic clinical patterns. The distributions are calibrated from this synthetic data.

**Q: What happens if the MAS endpoint is slow?**
The agent chat calls the MAS serving endpoint. If the endpoint is cold-starting or processing a long simulation trigger, it can take 30-60 seconds. The UI shows a spinner. For the demo, pre-cache simulations so agent responses are fast.

**Q: Can I add collaborators?**
The data model supports it (viewer/editor roles), but the UI doesn't expose collaborator management yet. Currently, published analyses are visible to everyone.

**Q: What simulation types are available?**
Four types defined in `config.yaml`: Patient Volume (encounter forecasting), Revenue (financial projections with payer mix), Cost Comparison (virtual vs in-person), and System Cost ROI (multi-year investment analysis).
