"""UC Metric View definitions — Women's Health focus.

Metric view YAML ``source`` must be a single table or view — JOINs are not
supported.  For views that need data from multiple tables we first create a
regular SQL view that performs the JOIN, then point the metric view at it.
"""


def get_base_view_definitions(catalog: str, schema: str) -> list[dict]:
    """Return regular SQL views that pre-join tables for metric views."""
    return [
        {
            "name": "v_wh_billing_encounters",
            "sql": f"""
CREATE OR REPLACE VIEW {catalog}.{schema}.v_wh_billing_encounters AS
SELECT
    b.billing_id, b.encounter_id, b.total_charges, b.payer_id,
    b.allowed_amount, b.paid_amount, b.patient_responsibility, b.claim_status,
    b.payment_date, e.encounter_type, e.department, e.admission_date,
    e.discharge_date, e.facility_id, e.patient_id, e.provider_id,
    d.icd10_code AS primary_icd10_code
FROM {catalog}.{schema}.billing AS b
JOIN {catalog}.{schema}.encounters AS e ON b.encounter_id = e.encounter_id
LEFT JOIN {catalog}.{schema}.diagnoses AS d
    ON e.encounter_id = d.encounter_id AND d.is_primary = 1
""",
        },
        {
            "name": "v_wh_encounter_patients",
            "sql": f"""
CREATE OR REPLACE VIEW {catalog}.{schema}.v_wh_encounter_patients AS
SELECT
    e.encounter_id, e.patient_id, e.facility_id, e.encounter_type,
    e.department, e.admission_date, e.discharge_date, e.length_of_stay,
    pt.date_of_birth, pt.gender, pt.insurance_type, pt.num_chronic,
    pt.chronic_conditions
FROM {catalog}.{schema}.encounters AS e
JOIN {catalog}.{schema}.patients AS pt ON e.patient_id = pt.patient_id
""",
        },
        {
            "name": "v_wh_encounter_diagnoses",
            "sql": f"""
CREATE OR REPLACE VIEW {catalog}.{schema}.v_wh_encounter_diagnoses AS
SELECT
    e.encounter_id, e.patient_id, e.encounter_type, e.department,
    e.admission_date, e.length_of_stay,
    d.icd10_code, d.description AS diagnosis_description, d.is_primary,
    ic.category AS diagnosis_category
FROM {catalog}.{schema}.encounters AS e
JOIN {catalog}.{schema}.diagnoses AS d ON e.encounter_id = d.encounter_id
LEFT JOIN {catalog}.{schema}.icd10_codes AS ic ON d.icd10_code = ic.icd10_code
""",
        },
    ]


def get_metric_view_definitions(catalog: str, schema: str) -> list[dict]:
    """Return all metric view definitions as (name, sql) pairs."""
    return [
        {
            "name": "mv_wh_cost_by_condition",
            "sql": f"""
CREATE OR REPLACE VIEW {catalog}.{schema}.mv_wh_cost_by_condition
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Women's health cost KPIs by department, ICD-10 condition, encounter type, and payer. Use for cost analysis, denial tracking, and condition-level financial reporting."
  source: {catalog}.{schema}.v_wh_billing_encounters
  dimensions:
    - name: Department
      expr: department
      comment: "Clinical department (OB/GYN, Internal Medicine, etc.)"
    - name: ICD-10 Code
      expr: primary_icd10_code
      comment: "Primary ICD-10 diagnosis code for the encounter"
    - name: Encounter Type
      expr: encounter_type
      comment: "Type of visit: Inpatient, Outpatient, Emergency, or Observation"
    - name: Service Month
      expr: DATE_TRUNC('MONTH', admission_date)
      comment: "Month of service for cost trending"
    - name: Payer ID
      expr: payer_id
      comment: "Insurance payer identifier"
  measures:
    - name: Total Cost
      expr: SUM(paid_amount)
      comment: "Total cost (paid amount) across encounters"
    - name: Avg Cost per Encounter
      expr: AVG(paid_amount)
      comment: "Average cost per encounter"
    - name: Encounter Count
      expr: COUNT(1)
      comment: "Total number of encounters"
    - name: Denial Rate
      expr: COUNT(1) FILTER (WHERE claim_status = 'Denied') * 1.0 / NULLIF(COUNT(1), 0)
      comment: "Fraction of claims that were denied"
$$;""",
        },
        {
            "name": "mv_wh_encounter_summary",
            "sql": f"""
CREATE OR REPLACE VIEW {catalog}.{schema}.mv_wh_encounter_summary
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Women's health encounter KPIs by type, department, and time period. Use for volume trends and operational reporting."
  source: {catalog}.{schema}.encounters
  filter: admission_date IS NOT NULL
  dimensions:
    - name: Encounter Type
      expr: encounter_type
      comment: "Type of visit: Inpatient, Outpatient, Emergency, or Observation"
    - name: Department
      expr: department
      comment: "Department (OB/GYN, Internal Medicine, etc.)"
    - name: Admission Month
      expr: DATE_TRUNC('MONTH', admission_date)
      comment: "Month of admission for time-series trending"
  measures:
    - name: Total Encounters
      expr: COUNT(1)
      comment: "Total number of patient encounters"
    - name: Unique Patients
      expr: COUNT(DISTINCT patient_id)
      comment: "Number of distinct patients seen"
    - name: Avg Length of Stay
      expr: AVG(length_of_stay)
      comment: "Average days from admission to discharge"
$$;""",
        },
        {
            "name": "mv_wh_diagnosis_prevalence",
            "sql": f"""
CREATE OR REPLACE VIEW {catalog}.{schema}.mv_wh_diagnosis_prevalence
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Women's health diagnosis prevalence by condition, time, and age group. Use for condition trending and population health analysis."
  source: {catalog}.{schema}.v_wh_encounter_diagnoses
  dimensions:
    - name: ICD-10 Code
      expr: icd10_code
      comment: "ICD-10 diagnosis code"
    - name: Diagnosis Category
      expr: diagnosis_category
      comment: "ICD-10 category (Women's Health, Cardiovascular, etc.)"
    - name: Service Month
      expr: DATE_TRUNC('MONTH', admission_date)
      comment: "Month of service for trending"
  measures:
    - name: Diagnosis Count
      expr: COUNT(1)
      comment: "Total diagnosis occurrences"
    - name: Unique Patients
      expr: COUNT(DISTINCT patient_id)
      comment: "Number of distinct patients with this diagnosis"
    - name: Encounters per Patient
      expr: COUNT(DISTINCT encounter_id) * 1.0 / NULLIF(COUNT(DISTINCT patient_id), 0)
      comment: "Average encounters per patient for this diagnosis"
$$;""",
        },
        {
            "name": "mv_wh_patient_demographics",
            "sql": f"""
CREATE OR REPLACE VIEW {catalog}.{schema}.mv_wh_patient_demographics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Women's health population metrics by age group, insurance type, and chronic condition status. Use for demographic analysis and chronic condition prevalence."
  source: {catalog}.{schema}.v_wh_encounter_patients
  dimensions:
    - name: Age Group
      expr: CASE
        WHEN FLOOR(DATEDIFF(admission_date, date_of_birth) / 365.25) < 35 THEN 'Young Adult (18-34)'
        WHEN FLOOR(DATEDIFF(admission_date, date_of_birth) / 365.25) < 50 THEN 'Adult (35-49)'
        WHEN FLOOR(DATEDIFF(admission_date, date_of_birth) / 365.25) < 65 THEN 'Middle Age (50-64)'
        ELSE 'Senior (65+)'
        END
      comment: "Patient age group at time of encounter"
    - name: Insurance Type
      expr: insurance_type
      comment: "Patient insurance type"
    - name: Chronic Condition Flag
      expr: CASE WHEN num_chronic > 0 THEN 'Has Chronic Condition' ELSE 'No Chronic Condition' END
      comment: "Whether the patient has any chronic conditions"
  measures:
    - name: Patient Count
      expr: COUNT(DISTINCT patient_id)
      comment: "Number of distinct patients"
    - name: Total Encounters
      expr: COUNT(1)
      comment: "Total encounters for demographic group"
    - name: Avg Encounters per Patient
      expr: COUNT(1) * 1.0 / NULLIF(COUNT(DISTINCT patient_id), 0)
      comment: "Average encounters per patient"
$$;""",
        },
        # ------------------------------------------------------------------
        # Project Accelerate — encounter-level analytics
        # Customer customization: change the source table in the YAML if
        # your encounters table has a different name.  Dimension/measure
        # names MUST be preserved for downstream fitting & simulations.
        # ------------------------------------------------------------------
        {
            "name": "mv_accelerate_encounters",
            "sql": f"""
CREATE OR REPLACE VIEW {catalog}.{schema}.mv_accelerate_encounters
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Encounter-level analytics with financial margins, SG2 taxonomy, and WH population segmentation."
  source: {catalog}.{schema}.project_accelerate_encounters
  dimensions:
    - name: Admit Month
      expr: DATE_TRUNC('MONTH', admit_date)
    - name: Admit Year
      expr: YEAR(admit_date)
    - name: Base Class
      expr: base_class_config_name
    - name: Patient Class
      expr: patient_class_config_name
    - name: Source System
      expr: source_system_name
    - name: HB PB
      expr: hb_pb
    - name: Region
      expr: region_name
    - name: Business Unit
      expr: business_unit_name
    - name: Financial Class
      expr: fin_class
    - name: WH Population
      expr: CASE WHEN is_custom_womens_health_population = 1 THEN 'WH' ELSE 'Non-WH' END
    - name: Patient Gender
      expr: patient_gender
    - name: Age Group
      expr: >-
        CASE
        WHEN patient_age_years < 35 THEN '18-34'
        WHEN patient_age_years < 50 THEN '35-49'
        WHEN patient_age_years < 65 THEN '50-64'
        ELSE '65+'
        END
    - name: Surgery Flag
      expr: CASE WHEN surgery_flag = 1 THEN 'Yes' ELSE 'No' END
    - name: Primary DX Service Line
      expr: try_element_at(diagnoses, 1).sg2_service_line_group
    - name: Primary DX Care Family
      expr: try_element_at(diagnoses, 1).sg2_care_family_group
    - name: Primary DX Disease Base
      expr: try_element_at(diagnoses, 1).sg2_disease_base_group
    - name: Primary DX Name
      expr: try_element_at(diagnoses, 1).diagnosis_name
    - name: Primary DX ICD Code
      expr: try_element_at(diagnoses, 1).icd_code_value
    - name: Hospital Final DX Service Line
      expr: try_element_at(filter(diagnoses, x -> x.diagnosis_type = 'hosp_acct_final_dx'), 1).sg2_service_line_group
    - name: Physician DX Service Line
      expr: try_element_at(filter(diagnoses, x -> x.diagnosis_type = 'phys_billing_encounter_dx'), 1).sg2_service_line_group
  measures:
    - name: Encounter Count
      expr: COUNT(*)
    - name: Patient Count
      expr: COUNT(DISTINCT cdm_patient_key)
    - name: Total Charge
      expr: SUM(total_charge)
    - name: Expected Payment
      expr: SUM(custom_expected_payment)
    - name: Total Cost
      expr: SUM(total_cost)
    - name: Total Direct Cost
      expr: SUM(total_direct_cost)
    - name: Total Variable Cost
      expr: SUM(total_variable_cost)
    - name: Total Margin
      expr: SUM(total_margin)
    - name: Direct Margin
      expr: SUM(direct_margin)
    - name: Variable Margin
      expr: SUM(variable_margin)
    - name: Surgery Count
      expr: SUM(surgery_flag)
    - name: Billing Encounter Count
      expr: COUNT(DISTINCT billing_encounter_id)
$$;""",
        },
    ]


def get_all_metric_view_ddl(catalog: str, schema: str) -> list[str]:
    """Return just the SQL DDL strings for all metric views."""
    return [mv["sql"] for mv in get_metric_view_definitions(catalog, schema)]
