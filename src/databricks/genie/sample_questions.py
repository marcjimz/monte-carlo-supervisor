"""Curated sample questions for the Genie Space."""


def get_sample_questions() -> list[dict]:
    """Return sample questions for the Genie Space with expected query patterns."""
    return [
        {
            "question": "Show me total ER encounters by month for 2024",
            "description": "Monthly ER volume trend",
        },
        {
            "question": "What is the average length of stay for cardiac patients?",
            "description": "LOS by diagnosis category",
        },
        {
            "question": "Which departments have the highest readmission rates?",
            "description": "Readmission rate ranking by department",
        },
        {
            "question": "Break down revenue by payer type for the last quarter",
            "description": "Payer mix financial analysis",
        },
        {
            "question": "How many unique patients did we see each month in 2024?",
            "description": "Monthly unique patient volume",
        },
        {
            "question": "What is the denial rate by payer?",
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
            "question": "What are the results of the most recent patient volume simulation?",
            "description": "Query simulation results Gold table",
        },
        {
            "question": "Show me all Monte Carlo simulations that have been run",
            "description": "List simulation run history",
        },
    ]
