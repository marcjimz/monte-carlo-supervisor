"""Example questions for MAS optimization via mas_add_examples_batch()."""


def get_supervisor_examples() -> list[dict]:
    """Return example questions with routing guidelines for the MAS.

    Each example helps the supervisor learn which agent handles which queries.
    """
    return [
        # Genie-routed (encounter_analytics)
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
            "question": "What were the results of the last capacity simulation?",
            "guideline": "Route to encounter_analytics — query the simulation_results Gold table for past results.",
        },
        # Monte Carlo-routed (monte_carlo_simulator)
        {
            "question": "Forecast ER patient volumes for the next 90 days",
            "guideline": (
                "Route to monte_carlo_simulator with simulation_type='patient_volume' "
                'and parameters=\'{"department": "Emergency", "encounter_type": "Emergency", "forecast_days": 90}\'.'
            ),
        },
        {
            "question": "What if we add 50 beds — what's our overflow probability?",
            "guideline": (
                "Route to monte_carlo_simulator with simulation_type='capacity' "
                'and parameters=\'{"facility_id": null, "additional_beds": 50, "forecast_days": 90}\'.'
            ),
        },
        {
            "question": "Simulate what happens to revenue if we shift 10% of Medicare patients to managed care",
            "guideline": (
                "Route to monte_carlo_simulator with simulation_type='revenue' "
                'and parameters=\'{"months_ahead": 12, "payer_mix_shift": {"Medicare": -0.10, "Commercial - UnitedHealth": 0.10}}\'.'
            ),
        },
        {
            "question": "Estimate readmission risk for heart failure patients over 65",
            "guideline": (
                "Route to monte_carlo_simulator with simulation_type='readmission_risk' "
                'and parameters=\'{"diagnosis_category": "I50", "age_min": 65}\'.'
            ),
        },
        {
            "question": "Simulate the impact of reducing LOS by 15% in the Cardiology department",
            "guideline": (
                "Route to monte_carlo_simulator with simulation_type='length_of_stay' "
                'and parameters=\'{"department": "Cardiology", "los_reduction_pct": 0.15}\'.'
            ),
        },
        # Compound queries
        {
            "question": "What was our readmission rate last year, and simulate what happens if we reduce LOS by 15%?",
            "guideline": (
                "Compound query: First route to encounter_analytics for historical readmission rate, "
                "then route to monte_carlo_simulator with simulation_type='length_of_stay' "
                "and los_reduction_pct=0.15. Synthesize both results."
            ),
        },
    ]
