"""Genie Space configuration — tables, instructions, and setup."""


def get_genie_space_config(catalog: str, schema: str) -> dict:
    """Return Genie Space configuration for the hospital encounter analytics space.

    Note: warehouse_id is not included here — it is auto-detected at runtime
    via AgentBricksManager.get_best_warehouse_id().
    """
    return {
        "display_name": "Hospital Encounter Analytics",
        "description": (
            "Natural language analytics over hospital encounter data. "
            "Ask questions about patient volumes, revenue, readmissions, "
            "length of stay, department throughput, and demographics. "
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
            f"{catalog}.{schema}.mv_encounter_summary",
            f"{catalog}.{schema}.mv_revenue_by_payer",
            f"{catalog}.{schema}.mv_readmission_rates",
            f"{catalog}.{schema}.mv_daily_census",
            f"{catalog}.{schema}.mv_department_throughput",
            f"{catalog}.{schema}.mv_patient_demographics",
            # Simulation result tables (Gold)
            f"{catalog}.{schema}.simulation_runs",
            f"{catalog}.{schema}.simulation_results",
        ],
        "instructions": (
            "You are a hospital data analyst. Answer questions about patient encounters, "
            "revenue, readmissions, length of stay, and operational metrics.\n\n"
            "Use metric views (mv_*) when the question maps to a standard KPI — they have "
            "pre-defined measures and dimensions via MEASURE() syntax.\n\n"
            "For simulation results, query simulation_results joined with simulation_runs "
            "to show parameters and outcomes of previously-run Monte Carlo simulations.\n\n"
            "Always include relevant context: time periods, departments, encounter types."
        ),
    }
