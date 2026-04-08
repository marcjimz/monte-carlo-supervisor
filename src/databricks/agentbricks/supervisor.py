"""Agent Bricks Multi-Agent Supervisor configuration."""


def get_supervisor_config(genie_space_id: str, catalog: str, schema: str) -> dict:
    """Return the MAS configuration for the Hospital Monte Carlo Supervisor.

    This configuration is passed to manage_mas(action="create_or_update", ...).
    """
    return {
        "name": "Hospital-Monte-Carlo-Supervisor",
        "description": (
            "Hospital analytics and Monte Carlo simulation supervisor. "
            "Routes historical data questions to Genie Space and "
            "forward-looking simulation/forecasting questions to the "
            "run_simulation UC function."
        ),
        "agents": [
            {
                "name": "encounter_analytics",
                "genie_space_id": genie_space_id,
                "description": (
                    "Answers questions about hospital encounter data AND previously-run "
                    "simulation results. Use for: historical volumes, trends, LOS, "
                    "readmission rates, revenue, department throughput, patient demographics, "
                    "AND querying existing simulation results from the simulation_results "
                    "Gold table."
                ),
            },
            {
                "name": "monte_carlo_simulator",
                "uc_function_name": f"{catalog}.{schema}.run_simulation",
                "description": (
                    "Triggers Monte Carlo simulations or retrieves cached results. "
                    "Supports 5 simulation types: patient_volume (forecast volumes), "
                    "revenue (project revenue under scenarios), readmission_risk "
                    "(estimate readmission probability), capacity (bed overflow analysis), "
                    "length_of_stay (LOS modeling with interventions). "
                    "Pass simulation_type and JSON parameters. Checks cache first — "
                    "returns instantly if same simulation was run before, otherwise "
                    "triggers a Databricks Job."
                ),
            },
        ],
        "instructions": """Route queries as follows:
1. Historical data questions (counts, trends, averages, breakdowns, 'show me', 'what was') → encounter_analytics (Genie)
2. Previously-run simulation results ('show me past simulations', 'what were the results of') → encounter_analytics (Genie queries simulation_results table)
3. NEW simulations or forecasts ('forecast', 'simulate', 'what if', 'predict', 'project', 'probability') → monte_carlo_simulator

For compound queries (e.g., "What was readmission rate last year AND simulate 15% LOS reduction"):
- First route to encounter_analytics for historical context
- Then route to monte_carlo_simulator for the simulation
- Synthesize both results in the response

When calling monte_carlo_simulator, construct the parameters JSON:
- patient_volume: {"department": "...", "encounter_type": "...", "forecast_days": N}
- revenue: {"facility_id": "...", "months_ahead": N, "volume_change_pct": 0.05, "payer_mix_shift": {"Medicare": -0.10}}
- readmission_risk: {"diagnosis_category": "I50", "age_min": 65, "age_max": 120}
- capacity: {"facility_id": "...", "additional_beds": 50, "volume_increase_pct": 0.10}
- length_of_stay: {"department": "...", "diagnosis_category": "...", "los_reduction_pct": 0.15}""",
    }
