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
3. NEW single simulations or forecasts ('forecast', 'simulate', 'what if', 'predict', 'project', 'probability', 'ROI', 'cost comparison') → simulation workflow below
4. Questions about fitted distributions ('what distributions', 'fitted parameters', 'distribution quality', 'what specs') → distribution_catalog
5. Parameter sweep / sensitivity analysis / matrix ('matrix', 'sensitivity', 'sweep', 'compare across', 'grid of', 'vary X and Y', 'range of values') → matrix_builder

Common women's health topics routed to Genie: OB/GYN encounters, cost by condition, menopause/endometriosis/fibroids prevalence, payer mix, diagnosis trends.
Common simulation topics: virtual care cost comparison (H2), system cost ROI (H5), patient volume forecasting, revenue projection.

For compound queries (e.g., "What was our OB/GYN cost per encounter last year, and simulate the 5-year ROI at 8% encounter reduction?"):
- First route to encounter_analytics for historical context
- Then follow the simulation workflow below
- Synthesize both results in the response

SIMULATION WORKFLOW (check → trigger → poll):
Step 1: Call simulation_checker with the user's parameters.
Step 2: If status is "completed" → present the results to the user. DONE.
Step 3: If status is "running" → call simulation_checker again with the EXACT SAME parameters. Repeat until "completed".
Step 4: If status is "not_found" AND you have NOT yet triggered → call simulation_trigger with the EXACT SAME parameters to start a new Spark job.
Step 5: After simulation_trigger returns "triggered" → call simulation_checker with the SAME parameters to poll. Repeat until "completed".
IMPORTANT: After triggering, check_simulation may return "not_found" for 1-2 minutes while the distributed Spark cluster starts. This is NORMAL — do NOT call trigger_simulation again. Keep calling check_simulation until you see "running" or "completed".
IMPORTANT: Never change parameters between calls. Always use identical values for simulation_type, parameters, num_simulations, and seed across all calls in a single workflow.

MATRIX WORKFLOW (for parameter sweeps):
When the user wants to compare results across multiple parameter values (sensitivity analysis, parameter sweep, grid search):
Step 1: Call matrix_builder with the simulation type, two parameters to sweep, and their value arrays.
Step 2: The system will automatically create the matrix and trigger all cell simulations.
Step 3: Tell the user the matrix has been created and they can view it on the Matrices tab.
IMPORTANT: Use JSON arrays for p_row_values and p_col_values (e.g. '[0.05, 0.08, 0.10, 0.15]').
IMPORTANT: Only override p_base_parameters for non-swept parameters the user explicitly mentions."""


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

    # Matrix-specific guidance: valid sweep parameter names per type
    lines.append("\nFor matrix_builder, use these parameter names as p_row_parameter / p_col_parameter:")
    for sim_type in config_loader.get_valid_types():
        param_names = list(config_loader.get_default_params(sim_type).keys())
        lines.append(f"- {sim_type}: {', '.join(param_names)}")

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
        {
            "name": "matrix_builder",
            "description": (
                "Creates a parameter sweep matrix that runs multiple simulations varying "
                "two parameters across a grid of values. Use this for sensitivity analysis, "
                "parameter sweeps, or comparing outcomes across ranges. The system creates "
                "the matrix and automatically triggers all cell simulations. "
                f"Supports: {types_str}."
            ),
            "agent_type": "unity_catalog_function",
            "unity_catalog_function": {
                "uc_path": {
                    "catalog": catalog,
                    "schema": schema,
                    "name": "create_matrix",
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
