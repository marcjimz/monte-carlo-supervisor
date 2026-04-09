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
            "question": "What were the results of the last ed_wait_time simulation?",
            "guideline": "Route to encounter_analytics — query the simulation_results Gold table for past results.",
        },
        # Monte Carlo-routed (simulation_checker + simulation_trigger)
        {
            "question": "Forecast ER patient volumes for the next 90 days",
            "guideline": (
                "Call simulation_checker with simulation_type='patient_volume' "
                "and parameters='{\"num_months\": 3}'. "
                "If 'completed', present results. "
                "If 'not_found', call simulation_trigger with the same parameters, "
                "then poll simulation_checker. "
                "If 'running', poll simulation_checker again."
            ),
        },
        {
            "question": "What are the expected ER wait times during peak hours?",
            "guideline": (
                "Call simulation_checker with simulation_type='ed_wait_time' "
                "and parameters='{\"base_wait_minutes\": 45, \"peak_multiplier\": 2.0, \"patients_per_hour\": 50}'. "
                "If 'completed', present results. "
                "If 'not_found', call simulation_trigger, then poll simulation_checker."
            ),
        },
        {
            "question": "Simulate what happens to revenue if we increase the denial rate to 12%",
            "guideline": (
                "Call simulation_checker with simulation_type='revenue' "
                "and parameters='{\"denial_rate\": 0.12, \"num_months\": 12}'. "
                "If 'completed', present results. "
                "If 'not_found', call simulation_trigger, then poll simulation_checker."
            ),
        },
        {
            "question": "Estimate 30-day readmission rates for Cardiology and Emergency departments",
            "guideline": (
                "Call simulation_checker with simulation_type='readmission_rate' "
                "and parameters='{\"departments\": [\"Cardiology\", \"Emergency\"], \"discharges_per_trial\": 300}'. "
                "If 'completed', present results. "
                "If 'not_found', call simulation_trigger, then poll simulation_checker."
            ),
        },
        {
            "question": "Model length of stay for Cardiology with 500 patients per trial",
            "guideline": (
                "Call simulation_checker with simulation_type='length_of_stay' "
                "and parameters='{\"departments\": [\"Cardiology\"], \"patients_per_trial\": 500}'. "
                "If 'completed', present results. "
                "If 'not_found', call simulation_trigger, then poll simulation_checker."
            ),
        },
        # Compound queries
        {
            "question": "What was our readmission rate last year, and simulate what it would look like with 500 discharges per trial?",
            "guideline": (
                "Compound query: First route to encounter_analytics for historical readmission rate, "
                "then call simulation_checker with simulation_type='readmission_rate' "
                "and parameters='{\"discharges_per_trial\": 500}'. "
                "If 'not_found', call simulation_trigger, then poll simulation_checker. "
                "Synthesize both results."
            ),
        },
    ]
