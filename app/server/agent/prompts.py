"""System prompt generation for the LangGraph supervisor agent.

Routing instructions and parameter reference generation extracted from
src/mc_supervisor/agentbricks/supervisor.py — now used directly by the
LangGraph graph instead of the MAS.
"""

from __future__ import annotations

import json

from server.agent.config import AgentConfig

ROUTING_INSTRUCTIONS = """Route queries as follows:
1. Historical data questions (costs, trends, volumes, demographics, 'show me', 'what was') → query_analytics tool (Genie)
2. Previously-run simulation results ('show me past simulations', 'what were the results of') → query_analytics tool (Genie queries simulation_results table)
3. NEW single simulations or forecasts ('forecast', 'simulate', 'what if', 'predict', 'project', 'probability', 'ROI', 'cost comparison') → simulation workflow below
4. Questions about fitted distributions ('what distributions', 'fitted parameters', 'distribution quality', 'what specs') → list_distributions tool
5. Parameter sweep / sensitivity analysis / matrix ('matrix', 'sensitivity', 'sweep', 'compare across', 'grid of', 'vary X and Y', 'range of values') → create_matrix tool

Common women's health topics routed to Genie: OB/GYN encounters, cost by condition, menopause/endometriosis/fibroids prevalence, payer mix, diagnosis trends.
Common simulation topics: virtual care cost comparison (H2), system cost ROI (H5), patient volume forecasting, revenue projection.

For compound queries (e.g., "What was our OB/GYN cost per encounter last year, and simulate the 5-year ROI at 8% encounter reduction?"):
- First use query_analytics for historical context
- Then follow the simulation workflow below
- Synthesize both results in the response

SIMULATION WORKFLOW (check → trigger → poll):
Step 1: Call check_simulation with the user's parameters.
Step 2: If status is "completed" → present the results to the user. DONE.
Step 3: If status is "running" → call check_simulation again with the EXACT SAME parameters. Repeat until "completed".
Step 4: If status is "not_found" AND you have NOT yet triggered → call trigger_simulation with the EXACT SAME parameters to start a new simulation.
Step 5: After trigger_simulation returns "submitted" → call check_simulation with the SAME parameters to poll. The pipeline starts within ~2 minutes. Expect "submitted" → "running" → "completed" progression. Keep polling.
IMPORTANT: After triggering, check_simulation may return "submitted" (queued) or "not_found" briefly while the pipeline starts. This is NORMAL — do NOT call trigger_simulation again. Keep calling check_simulation until you see "running" or "completed".
IMPORTANT: Never change parameters between calls. Always use identical values for simulation_type, parameters, num_simulations, and seed across all calls in a single workflow.

MATRIX WORKFLOW (for parameter sweeps):
When the user wants to compare results across multiple parameter values (sensitivity analysis, parameter sweep, grid search):
Step 1: Call create_matrix with the simulation type, two parameters to sweep, and their value arrays.
Step 2: The system will create the matrix with all cells in "pending" state.
Step 3: Tell the user: "Your matrix has been created and all cell simulations are now running automatically. Results will appear in this chat when complete (typically 5-10 minutes)."
IMPORTANT: Simulations are automatically triggered after matrix creation. Do NOT tell the user to click Run All.
IMPORTANT: Use JSON arrays for row_values and col_values (e.g. [0.05, 0.08, 0.10, 0.15]).
IMPORTANT: Only override base_parameters for non-swept parameters the user explicitly mentions."""

TOOL_GUIDE = """
Available tools:
- check_simulation: Check if a simulation has cached results or is running. ALWAYS call this first before triggering.
- trigger_simulation: Submit a new simulation to the pipeline. Only call when check_simulation returns "not_found".
- create_matrix: Create a parameter sweep matrix for sensitivity analysis.
- list_distributions: List fitted distribution specs for simulation types.
- query_analytics: Ask natural language questions about hospital data and past simulation results via Genie.

When you need to use a tool, respond with the appropriate tool call. Do not describe what you would do — actually call the tool."""


def _get_parameter_reference() -> str:
    """Generate parameter reference from config.yaml."""
    try:
        from mc_supervisor.monte_carlo import config_loader
    except ImportError:
        return ""

    lines = [
        "\n\nWhen calling simulations, construct the parameters JSON using these parameter names:"
    ]
    for sim_type in config_loader.get_valid_types():
        defaults = config_loader.get_default_params(sim_type)
        sample = {}
        for name, value in defaults.items():
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

    lines.append("\nFor create_matrix, use these parameter names as row_parameter / col_parameter:")
    for sim_type in config_loader.get_valid_types():
        param_names = list(config_loader.get_default_params(sim_type).keys())
        lines.append(f"- {sim_type}: {', '.join(param_names)}")

    return "\n".join(lines)


def get_system_prompt(config: AgentConfig) -> str:
    """Compose the full system prompt: persona + routing + tool guide + param reference."""
    parts = [
        config.prompt.persona,
        "",
        ROUTING_INSTRUCTIONS,
        TOOL_GUIDE,
        _get_parameter_reference(),
    ]
    return "\n".join(parts)
