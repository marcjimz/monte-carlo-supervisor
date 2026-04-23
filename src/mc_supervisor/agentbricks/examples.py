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
        "question": "What is the average margin per encounter by region?",
        "guideline": "Route to encounter_analytics — historical margin analysis by region.",
    },
    {
        "question": "Show encounter volume trends by business unit for the last 12 months",
        "guideline": "Route to encounter_analytics — historical volume trending.",
    },
    {
        "question": "What percentage of our encounters are the women's health population?",
        "guideline": "Route to encounter_analytics — WH population segmentation.",
    },
    {
        "question": "Break down total cost by financial class",
        "guideline": "Route to encounter_analytics — historical cost analysis by payer.",
    },
]

_DISTRIBUTION_EXAMPLE = {
    "question": "What distributions have been fitted for encounter margin simulations?",
    "guideline": "Route to distribution_catalog with simulation_type='encounter_margin'.",
}

_COMPOUND_EXAMPLE = {
    "question": "What was our average margin per encounter last quarter, and forecast the next 12 months at 3% growth?",
    "guideline": (
        "Compound query: First route to encounter_analytics for historical margin per encounter, "
        "then call simulation_checker with simulation_type='encounter_margin' "
        "and parameters='{\"growth_rate\": 0.03, \"num_months\": 12}'. "
        "If 'not_found', call simulation_trigger_mcp, then poll simulation_checker. "
        "Synthesize both results."
    ),
}


# ---------------------------------------------------------------------------
# Dynamic simulation examples from config
# ---------------------------------------------------------------------------


def _generate_simulation_examples() -> list[dict]:
    """Generate one simulation example per type from config.yaml."""
    from mc_supervisor.monte_carlo import config_loader

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
            if isinstance(value, (int, float, str, bool)):
                sample_params[name] = value
            elif isinstance(value, list) and len(value) <= 5:
                sample_params[name] = value
        params_json = json.dumps(sample_params)

        # Generate a natural question from the description
        question = f"Simulate {display_name.lower()} for the next period"
        if "roi" in description.lower() or "roi" in display_name.lower():
            question = f"Project the {display_name.lower()} for our virtual care partnership"
        elif "cost comparison" in description.lower() or "compare" in description.lower():
            question = f"Compare virtual vs in-person care costs for women's health"
        elif "monthly" in description.lower() or "month" in description.lower():
            question = f"Forecast {display_name.lower()} for the next 12 months"
        elif "department" in description.lower():
            question = f"Estimate {display_name.lower()} by department"

        guideline = (
            f"Call simulation_checker with simulation_type='{sim_type}' "
            f"and parameters='{params_json}'. "
            "If 'completed', present results. "
            "If 'not_found', call simulation_trigger_mcp, then poll simulation_checker."
        )

        examples.append({"question": question, "guideline": guideline})

    return examples


def get_supervisor_examples() -> list[dict]:
    """Return example questions with routing guidelines for the MAS.

    Each example helps the supervisor learn which agent handles which queries.
    Genie/compound examples are static; simulation examples are generated
    from config.yaml.
    """
    return _GENIE_EXAMPLES + _generate_simulation_examples() + [_DISTRIBUTION_EXAMPLE, _COMPOUND_EXAMPLE]
