"""Curated sample questions for the Genie Space — Women's Health focus."""


def get_sample_questions() -> list[dict]:
    """Return sample questions for the Genie Space with expected query patterns."""
    return [
        {
            "question": "What is the average cost per encounter for OB/GYN patients?",
            "description": "Cost analysis by department",
        },
        {
            "question": "Show me diagnosis prevalence by month for chronic pelvic pain",
            "description": "Diagnosis trending for WH conditions",
        },
        {
            "question": "Break down revenue by payer type for women's health encounters",
            "description": "Payer mix financial analysis",
        },
        {
            "question": "What were the results of the last cost comparison simulation?",
            "description": "Query simulation results Gold table",
        },
        {
            "question": "How many unique patients did we see each month in 2024?",
            "description": "Monthly unique patient volume",
        },
        {
            "question": "What is the denial rate by payer for OB/GYN encounters?",
            "description": "Claims denial analysis",
        },
        {
            "question": "Show me the top 10 diagnoses by encounter volume",
            "description": "Diagnosis frequency ranking",
        },
        {
            "question": "Compare inpatient vs outpatient encounters by department",
            "description": "Encounter type distribution",
        },
        {
            "question": "What is the age distribution of patients with endometriosis?",
            "description": "Demographics for specific condition",
        },
        {
            "question": "Show me all Monte Carlo simulations that have been run",
            "description": "List simulation run history",
        },
    ]
