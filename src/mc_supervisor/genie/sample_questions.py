"""Curated sample questions for the Genie Space — encounters + margin focus."""


def get_sample_questions() -> list[dict]:
    """Return sample questions for the Genie Space with expected query patterns."""
    return [
        {
            "question": "What is the average margin per encounter by region?",
            "description": "Direct margin analysis by geography",
        },
        {
            "question": "Show encounter volume trends by business unit for the last 12 months",
            "description": "Monthly volume trending by BU",
        },
        {
            "question": "What percentage of our encounters are the women's health population?",
            "description": "WH population segmentation",
        },
        {
            "question": "Break down total cost by financial class",
            "description": "Cost analysis by payer type",
        },
        {
            "question": "Which SG2 service lines have the highest surgical rate?",
            "description": "Surgical rate by SG2 taxonomy",
        },
        {
            "question": "Show me all Monte Carlo simulations that have been run",
            "description": "List simulation run history",
        },
        {
            "question": "Compare direct margin between inpatient and outpatient encounters",
            "description": "Margin comparison by base class",
        },
        {
            "question": "What is the age distribution of our women's health population?",
            "description": "Demographics for WH cohort",
        },
        {
            "question": "Show monthly encounter volume by source system for the last year",
            "description": "EMR source system trending",
        },
        {
            "question": "What are the top 10 SG2 disease bases by encounter volume?",
            "description": "SG2 disease base ranking",
        },
    ]
