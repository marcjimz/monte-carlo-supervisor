"""Genie Space configuration — Women's Health Analytics."""


def get_genie_space_config(catalog: str, schema: str) -> dict:
    """Return Genie Space configuration for women's health analytics.

    Note: warehouse_id is not included here — it is auto-detected at runtime
    via AgentBricksManager.get_best_warehouse_id().
    """
    return {
        "display_name": "Women's Health Analytics",
        "description": (
            "Natural language analytics over women's health encounter data. "
            "Ask questions about patient volumes, costs by condition, diagnosis "
            "prevalence, demographics, and virtual care hypothesis testing. "
            "Also query previously-run Monte Carlo simulation results."
        ),
        "tables": [
            # Core fact/dimension tables
            f"{catalog}.{schema}.encounters",
            f"{catalog}.{schema}.patients",
            f"{catalog}.{schema}.providers",
            f"{catalog}.{schema}.facilities",
            f"{catalog}.{schema}.diagnoses",
            f"{catalog}.{schema}.procedures",
            f"{catalog}.{schema}.billing",
            f"{catalog}.{schema}.readmissions",
            # Reference tables
            f"{catalog}.{schema}.icd10_codes",
            f"{catalog}.{schema}.cpt_codes",
            f"{catalog}.{schema}.payers",
            f"{catalog}.{schema}.departments",
            # Metric views
            f"{catalog}.{schema}.mv_wh_cost_by_condition",
            f"{catalog}.{schema}.mv_wh_encounter_summary",
            f"{catalog}.{schema}.mv_wh_diagnosis_prevalence",
            f"{catalog}.{schema}.mv_wh_patient_demographics",
            # Simulation result tables (Gold)
            f"{catalog}.{schema}.simulation_runs",
            f"{catalog}.{schema}.simulation_results",
        ],
        "instructions": (
            "You are a women's health data analyst. Answer questions about patient encounters, "
            "costs by condition, diagnosis prevalence, demographics, and operational metrics "
            "for a women's health virtual care evaluation.\n\n"
            "The data represents 100% in-person baseline encounters for women's health conditions "
            "including menopause, endometriosis, fibroids, abnormal uterine bleeding, pelvic pain, "
            "and related comorbidities (cardiovascular, endocrine, mental health).\n\n"
            "Use metric views (mv_wh_*) when the question maps to a standard KPI — they have "
            "pre-defined measures and dimensions via MEASURE() syntax.\n\n"
            "For simulation results, query simulation_results joined with simulation_runs "
            "to show parameters and outcomes of previously-run Monte Carlo simulations "
            "(cost comparison, system ROI, patient volume, revenue projections).\n\n"
            "Always include relevant context: time periods, departments, encounter types, conditions."
        ),
    }
