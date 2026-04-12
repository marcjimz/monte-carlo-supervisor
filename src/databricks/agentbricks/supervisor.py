"""Agent Bricks Multi-Agent Supervisor configuration — Women's Health focus.

Uses AgentBricksManager from databricks-tools-core for programmatic creation.
Instructions and agent descriptions are generated dynamically from config.yaml
so that adding/removing simulation types requires zero code changes here.
"""

import json

SUPERVISOR_NAME = "Womens-Health-MC-Supervisor"

SUPERVISOR_DESCRIPTION = (
    "Women's health analytics and Monte Carlo simulation supervisor. "
    "Routes historical data questions about women's health encounters, costs, "
    "and diagnoses to Genie Space, and forward-looking virtual care hypothesis "
    "simulations through a check-then-trigger workflow using distributed Spark jobs."
)

# Static routing logic — this is architectural, not type-specific
_ROUTING_INSTRUCTIONS = """Route queries as follows:
1. Historical data questions (costs, trends, volumes, demographics, 'show me', 'what was') → encounter_analytics (Genie)
2. Previously-run simulation results ('show me past simulations', 'what were the results of') → encounter_analytics (Genie queries simulation_results table)
3. NEW simulations or forecasts ('forecast', 'simulate', 'what if', 'predict', 'project', 'probability', 'ROI', 'cost comparison') → simulation workflow below
4. Questions about fitted distributions ('what distributions', 'fitted parameters', 'distribution quality', 'what specs') → distribution_catalog

Common women's health topics routed to Genie: OB/GYN encounters, cost by condition, menopause/endometriosis/fibroids prevalence, payer mix, diagnosis trends.
Common simulation topics: virtual care cost comparison (H2), system cost ROI (H5), patient volume forecasting, revenue projection.

For compound queries (e.g., "What was our OB/GYN cost per encounter last year, and simulate the 5-year ROI at 8% encounter reduction?"):
- First route to encounter_analytics for historical context
- Then follow the simulation workflow below
- Synthesize both results in the response

SIMULATION WORKFLOW (check → trigger → check once):
Step 1: Call simulation_checker with the user's parameters.
Step 2: If status is "completed" → present the results to the user. DONE.
Step 3: If status is "running" → tell the user: "Your simulation is currently running. Please ask me again in 2-3 minutes to check the results." DONE. Do NOT call simulation_checker again — the job needs time to finish.
Step 4: If status is "not_found" → call simulation_trigger with the EXACT SAME parameters to start a new Spark job.
Step 5: After simulation_trigger returns "triggered" → call simulation_checker ONCE with the SAME parameters. If still "running", tell the user: "Your simulation has been started. It typically takes 3-5 minutes. Please ask me again shortly to see the results." DONE. Do NOT keep polling.
IMPORTANT: Never change parameters between calls. Always use identical values for simulation_type, parameters, num_simulations, and seed across all calls in a single workflow.
IMPORTANT: Do NOT poll simulation_checker in a loop. The simulation runs as a distributed Spark job and takes several minutes. Polling repeatedly will not make it faster and will cause errors. Check at most twice (once after trigger), then ask the user to check back."""


def _get_parameter_reference() -> str:
    """Generate the parameter reference block from config.yaml."""
    from src.databricks.monte_carlo import config_loader

    lines = [
        "\n\nWhen calling simulations, construct the parameters JSON using these parameter names:"
    ]
    for sim_type in config_loader.get_valid_types():
        defaults = config_loader.get_default_params(sim_type)
        # Build a clean JSON sample with a few key params
        sample = {}
        for name, value in defaults.items():
            # Skip large nested dicts/lists to keep the reference concise
            if isinstance(value, dict) and len(value) > 3:
                sample[name] = {k: v for i, (k, v) in enumerate(value.items()) if i < 2}
            elif isinstance(value, list) and len(value) > 5:
                sample[name] = value[:3]
            else:
                sample[name] = value
        lines.append(f"- {sim_type}: {json.dumps(sample)}")

    lines.append(
        "\nOnly override parameters the user explicitly mentions. "
        "Use defaults for everything else by passing '{}'."
    )
    return "\n".join(lines)


def get_supervisor_instructions() -> str:
    """Generate supervisor instructions dynamically from config.yaml."""
    return _ROUTING_INSTRUCTIONS + _get_parameter_reference()


def _get_supported_types_str() -> str:
    """Return comma-separated sorted list of simulation types from config."""
    from src.databricks.monte_carlo import config_loader
    return ", ".join(config_loader.get_valid_types())


def get_supervisor_agents(genie_space_id: str, catalog: str, schema: str) -> list[dict]:
    """Return the agent list in AgentBricksManager.mas_create() format."""
    types_str = _get_supported_types_str()
    return [
        {
            "name": "encounter_analytics",
            "description": (
                "Answers questions about women's health encounter data AND previously-run "
                "simulation results. Use for: costs by condition, OB/GYN volumes, diagnosis "
                "prevalence, patient demographics, payer mix, department throughput, "
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
                f"Supports: {types_str}."
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
                f"Supports: {types_str}."
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
        {
            "name": "distribution_catalog",
            "description": (
                "Lists available fitted distribution specs for simulation types. "
                "Call this to discover what distributions have been fitted from historical data, "
                "their parameters, and goodness-of-fit metrics. "
                "Optionally filter by simulation_type."
            ),
            "agent_type": "unity_catalog_function",
            "unity_catalog_function": {
                "uc_path": {
                    "catalog": catalog,
                    "schema": schema,
                    "name": "list_distributions",
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
        "instructions": get_supervisor_instructions(),
    }
