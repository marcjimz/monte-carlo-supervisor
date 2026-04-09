"""Agent Bricks Multi-Agent Supervisor configuration.

Uses AgentBricksManager from databricks-tools-core for programmatic creation.
"""

SUPERVISOR_NAME = "Hospital-Monte-Carlo-Supervisor"

SUPERVISOR_DESCRIPTION = (
    "Hospital analytics and Monte Carlo simulation supervisor. "
    "Routes historical data questions to Genie Space and "
    "forward-looking simulation/forecasting questions through a "
    "check-then-trigger workflow using distributed Spark jobs."
)

SUPERVISOR_INSTRUCTIONS = """Route queries as follows:
1. Historical data questions (counts, trends, averages, breakdowns, 'show me', 'what was') → encounter_analytics (Genie)
2. Previously-run simulation results ('show me past simulations', 'what were the results of') → encounter_analytics (Genie queries simulation_results table)
3. NEW simulations or forecasts ('forecast', 'simulate', 'what if', 'predict', 'project', 'probability') → simulation workflow below

For compound queries (e.g., "What was readmission rate last year AND simulate 15% LOS reduction"):
- First route to encounter_analytics for historical context
- Then follow the simulation workflow below
- Synthesize both results in the response

SIMULATION WORKFLOW (check → trigger → poll):
Step 1: Call simulation_checker with the user's parameters.
Step 2: If status is "completed" → present the results to the user. DONE.
Step 3: If status is "running" → inform the user, then call simulation_checker again with the EXACT SAME parameters. Repeat until "completed".
Step 4: If status is "not_found" → call simulation_trigger with the EXACT SAME parameters to start a new Spark job.
Step 5: After simulation_trigger returns "triggered" → call simulation_checker again with the SAME parameters to poll. Repeat until "completed".
IMPORTANT: Never change parameters between calls. Always use identical values for simulation_type, parameters, num_simulations, and seed across all calls in a single workflow.

When calling simulations, construct the parameters JSON using these parameter names:
- patient_volume: {"monthly_mean": 10000, "monthly_std": 1500, "growth_rate": 0.03, "num_months": 12}
- revenue: {"avg_monthly_revenue": 12000000, "revenue_std": 2000000, "denial_rate": 0.08, "num_months": 12}
- readmission_rate: {"departments": ["Cardiology", "Emergency"], "base_readmission_rate": {"Cardiology": 0.18}, "discharges_per_trial": 300}
- ed_wait_time: {"base_wait_minutes": 45, "peak_multiplier": 2.0, "peak_hours": [10,11,12,13,14,18,19,20,21], "patients_per_hour": 50}
- length_of_stay: {"departments": ["Cardiology", "Emergency"], "los_baseline": {"Cardiology": [1.4, 0.6]}, "patients_per_trial": 500}

Only override parameters the user explicitly mentions. Use defaults for everything else by passing '{}'."""


def get_supervisor_agents(genie_space_id: str, catalog: str, schema: str) -> list[dict]:
    """Return the agent list in AgentBricksManager.mas_create() format."""
    return [
        {
            "name": "encounter_analytics",
            "description": (
                "Answers questions about hospital encounter data AND previously-run "
                "simulation results. Use for: historical volumes, trends, LOS, "
                "readmission rates, revenue, department throughput, patient demographics, "
                "AND querying existing simulation results from the simulation_results "
                "Gold table."
            ),
            "agent_type": "genie",
            "genie_space": {"id": genie_space_id},
        },
        {
            "name": "simulation_checker",
            "description": (
                "Checks whether a Monte Carlo simulation has completed results or is "
                "currently running. Returns cached results instantly if a matching run "
                "exists (status 'completed' with full statistical distributions), "
                "'running' if a job is in progress, or 'not_found' if no matching run "
                "exists. This is a read-only check — it never starts new jobs. "
                "ALWAYS call this FIRST before triggering a new simulation. "
                "Supports: patient_volume, revenue, readmission_rate, ed_wait_time, length_of_stay."
            ),
            "agent_type": "unity_catalog_function",
            "unity_catalog_function": {
                "uc_path": {
                    "catalog": catalog,
                    "schema": schema,
                    "name": "check_simulation",
                }
            },
        },
        {
            "name": "simulation_trigger",
            "description": (
                "Triggers a new distributed Spark Monte Carlo simulation job with 10,000+ "
                "trials across multiple nodes. The job runs 5-10 minutes. "
                "ONLY call this when simulation_checker returns 'not_found'. "
                "After triggering, call simulation_checker again with the same parameters "
                "to poll for completion. "
                "Supports: patient_volume, revenue, readmission_rate, ed_wait_time, length_of_stay."
            ),
            "agent_type": "unity_catalog_function",
            "unity_catalog_function": {
                "uc_path": {
                    "catalog": catalog,
                    "schema": schema,
                    "name": "trigger_simulation",
                }
            },
        },
    ]


def get_supervisor_config(genie_space_id: str, catalog: str, schema: str) -> dict:
    """Return the full MAS configuration dict."""
    return {
        "name": SUPERVISOR_NAME,
        "description": SUPERVISOR_DESCRIPTION,
        "agents": get_supervisor_agents(genie_space_id, catalog, schema),
        "instructions": SUPERVISOR_INSTRUCTIONS,
    }
