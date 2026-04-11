"""Example questions for MAS optimization via mas_add_examples_batch().

Static Genie/compound examples are kept as-is. Type-specific simulation
examples are generated dynamically from config.yaml so that adding a new
simulation type automatically produces a routing example.
"""

import json


# ---------------------------------------------------------------------------
# Static examples (not type-specific)
# ---------------------------------------------------------------------------

_GENIE_EXAMPLES = [
    {
        "question": "Show me total ER encounters by month for 2024",
        "guideline": "Route to encounter_analytics — this is a historical data query about encounter volumes.",
    },
    {
        "question": "What's our average length of stay for cardiac patients?",
        "guideline": "Route to encounter_analytics — historical LOS analysis by diagnosis.",
    },
    {
        "question": "Which departments have the highest readmission rates?",
        "guideline": "Route to encounter_analytics — historical readmission rate analysis.",
    },
    {
        "question": "Break down revenue by payer type for Q4 2024",
        "guideline": "Route to encounter_analytics — historical financial analysis.",
    },
    {
        "question": "What were the results of the last ed_wait_time simulation?",
        "guideline": "Route to encounter_analytics — query the simulation_results Gold table for past results.",
    },
]

_COMPOUND_EXAMPLE = {
    "question": "What was our readmission rate last year, and simulate what it would look like with 500 discharges per trial?",
    "guideline": (
        "Compound query: First route to encounter_analytics for historical readmission rate, "
        "then call simulation_checker with simulation_type='readmission_rate' "
        "and parameters='{\"discharges_per_trial\": 500}'. "
        "If 'not_found', call simulation_trigger, then poll simulation_checker. "
        "Synthesize both results."
    ),
}


# ---------------------------------------------------------------------------
# Dynamic simulation examples from config
# ---------------------------------------------------------------------------


def _generate_simulation_examples() -> list[dict]:
    """Generate one simulation example per type from config.yaml."""
    from src.databricks.monte_carlo import config_loader

    examples = []
    for sim_type in config_loader.get_valid_types():
        sim_cfg = config_loader.get_sim_type_config(sim_type)
        display_name = sim_cfg.get("display_name", sim_type)
        description = sim_cfg.get("description", "")
        defaults = config_loader.get_default_params(sim_type)

        # Build a compact sample params JSON (first 3 params with simple values)
        sample_params = {}
        for name, value in defaults.items():
            if len(sample_params) >= 3:
                break
            if isinstance(value, (int, float, str)):
                sample_params[name] = value
            elif isinstance(value, list) and len(value) <= 5:
                sample_params[name] = value
        params_json = json.dumps(sample_params)

        # Generate a natural question from the description
        question = f"Simulate {display_name.lower()} for the next period"
        if "monthly" in description.lower() or "month" in description.lower():
            question = f"Forecast {display_name.lower()} for the next 12 months"
        elif "department" in description.lower():
            question = f"Estimate {display_name.lower()} by department"
        elif "hour" in description.lower() or "wait" in description.lower():
            question = f"What are the expected {display_name.lower()} during peak hours?"

        guideline = (
            f"Call simulation_checker with simulation_type='{sim_type}' "
            f"and parameters='{params_json}'. "
            "If 'completed', present results. "
            "If 'not_found', call simulation_trigger, then poll simulation_checker."
        )

        examples.append({"question": question, "guideline": guideline})

    return examples


def get_supervisor_examples() -> list[dict]:
    """Return example questions with routing guidelines for the MAS.

    Each example helps the supervisor learn which agent handles which queries.
    Genie/compound examples are static; simulation examples are generated
    from config.yaml.
    """
    return _GENIE_EXAMPLES + _generate_simulation_examples() + [_COMPOUND_EXAMPLE]
