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
            # Fact tables (for cross-domain queries metric views can't cover)
            # NOTE: billing is intentionally excluded — cost queries must use
            # mv_wh_cost_by_condition to avoid total_charges vs paid_amount ambiguity
            f"{catalog}.{schema}.diagnoses",
            f"{catalog}.{schema}.encounters",
            f"{catalog}.{schema}.patients",
            # Reference/dimension tables
            f"{catalog}.{schema}.cpt_codes",
            f"{catalog}.{schema}.departments",
            f"{catalog}.{schema}.facilities",
            f"{catalog}.{schema}.icd10_codes",
            f"{catalog}.{schema}.payers",
            f"{catalog}.{schema}.procedures",
            f"{catalog}.{schema}.providers",
            f"{catalog}.{schema}.readmissions",
            # Simulation result tables (Gold)
            f"{catalog}.{schema}.simulation_results",
            f"{catalog}.{schema}.simulation_runs",
        ],
        "metric_views": [
            # Canonical KPI sources — Genie should prefer these over raw tables
            f"{catalog}.{schema}.mv_wh_cost_by_condition",
            f"{catalog}.{schema}.mv_wh_diagnosis_prevalence",
            f"{catalog}.{schema}.mv_wh_encounter_summary",
            f"{catalog}.{schema}.mv_wh_patient_demographics",
        ],
        "instructions": (
            "You are a women's health data analyst. Answer questions about patient encounters, "
            "costs by condition, diagnosis prevalence, demographics, and operational metrics "
            "for a women's health virtual care evaluation.\n\n"
            "The data represents 100% in-person baseline encounters for women's health conditions "
            "including menopause, endometriosis, fibroids, abnormal uterine bleeding, pelvic pain, "
            "and related comorbidities (cardiovascular, endocrine, mental health).\n\n"
            "IMPORTANT — ALWAYS prefer metric views (mv_wh_*) over raw tables for standard KPIs. "
            "Metric views define canonical measures via MEASURE() syntax that ensure consistent "
            "answers across all consumers. Use raw tables ONLY when the question cannot be "
            "answered by any metric view.\n\n"
            "Metric view mapping:\n"
            "- Cost questions (avg cost, total cost, denial rate) → mv_wh_cost_by_condition "
            "(dimensions: Department, ICD-10 Code, Encounter Type, Service Month, Payer ID)\n"
            "- Volume questions (encounter counts, unique patients, LOS) → mv_wh_encounter_summary "
            "(dimensions: Encounter Type, Department, Admission Month)\n"
            "- Diagnosis questions (prevalence, top diagnoses) → mv_wh_diagnosis_prevalence "
            "(dimensions: ICD-10 Code, Diagnosis Category, Service Month)\n"
            "- Demographics questions (age, insurance, chronic conditions) → mv_wh_patient_demographics "
            "(dimensions: Age Group, Insurance Type, Chronic Condition Flag)\n\n"
            "When using metric views, reference measures with MEASURE() syntax, e.g.: "
            "SELECT Department, MEASURE(`Avg Cost per Encounter`) FROM mv_wh_cost_by_condition "
            "GROUP BY Department.\n\n"
            "For simulation results, query simulation_results joined with simulation_runs "
            "to show parameters and outcomes of previously-run Monte Carlo simulations "
            "(cost comparison, system ROI, patient volume, revenue projections).\n\n"
            "Always include relevant context: time periods, departments, encounter types, conditions."
        ),
    }
