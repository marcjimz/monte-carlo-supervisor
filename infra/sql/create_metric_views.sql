-- UC Metric Views — parameterized via EXECUTE IMMEDIATE pattern.
-- Parameters: :catalog, :schema (passed via DAB sql_task base_parameters)
-- Uses EXECUTE IMMEDIATE because metric view DDL requires literal catalog.schema
-- references in the YAML source field (identifier() not supported inside YAML).

USE CATALOG IDENTIFIER(:catalog);
USE SCHEMA IDENTIFIER(:schema);

-- 1. mv_wh_cost_by_condition
DECLARE OR REPLACE qry_1 STRING;
SET VAR qry_1 =
  "CREATE OR REPLACE VIEW " || :catalog || "." || :schema || ".mv_wh_cost_by_condition
   WITH METRICS LANGUAGE YAML AS $$
  version: 1.1
  comment: \"Women's health cost KPIs by department, ICD-10 condition, encounter type, and payer.\"
  source: " || :catalog || "." || :schema || ".v_wh_billing_encounters
  dimensions:
    - name: Department
      expr: department
    - name: ICD-10 Code
      expr: primary_icd10_code
    - name: Encounter Type
      expr: encounter_type
    - name: Service Month
      expr: DATE_TRUNC('MONTH', admission_date)
    - name: Payer ID
      expr: payer_id
  measures:
    - name: Total Cost
      expr: SUM(paid_amount)
    - name: Avg Cost per Encounter
      expr: AVG(paid_amount)
    - name: Encounter Count
      expr: COUNT(1)
    - name: Denial Rate
      expr: COUNT(1) FILTER (WHERE claim_status = 'Denied') * 1.0 / NULLIF(COUNT(1), 0)
  $$";
EXECUTE IMMEDIATE qry_1;

-- 2. mv_wh_encounter_summary
DECLARE OR REPLACE qry_2 STRING;
SET VAR qry_2 =
  "CREATE OR REPLACE VIEW " || :catalog || "." || :schema || ".mv_wh_encounter_summary
   WITH METRICS LANGUAGE YAML AS $$
  version: 1.1
  comment: \"Women's health encounter KPIs by type, department, and time period.\"
  source: " || :catalog || "." || :schema || ".encounters
  filter: admission_date IS NOT NULL
  dimensions:
    - name: Encounter Type
      expr: encounter_type
    - name: Department
      expr: department
    - name: Admission Month
      expr: DATE_TRUNC('MONTH', admission_date)
  measures:
    - name: Total Encounters
      expr: COUNT(1)
    - name: Unique Patients
      expr: COUNT(DISTINCT patient_id)
    - name: Avg Length of Stay
      expr: AVG(length_of_stay)
  $$";
EXECUTE IMMEDIATE qry_2;

-- 3. mv_wh_diagnosis_prevalence
DECLARE OR REPLACE qry_3 STRING;
SET VAR qry_3 =
  "CREATE OR REPLACE VIEW " || :catalog || "." || :schema || ".mv_wh_diagnosis_prevalence
   WITH METRICS LANGUAGE YAML AS $$
  version: 1.1
  comment: \"Women's health diagnosis prevalence by condition, time, and age group.\"
  source: " || :catalog || "." || :schema || ".v_wh_encounter_diagnoses
  dimensions:
    - name: ICD-10 Code
      expr: icd10_code
    - name: Diagnosis Category
      expr: diagnosis_category
    - name: Service Month
      expr: DATE_TRUNC('MONTH', admission_date)
  measures:
    - name: Diagnosis Count
      expr: COUNT(1)
    - name: Unique Patients
      expr: COUNT(DISTINCT patient_id)
    - name: Encounters per Patient
      expr: COUNT(DISTINCT encounter_id) * 1.0 / NULLIF(COUNT(DISTINCT patient_id), 0)
  $$";
EXECUTE IMMEDIATE qry_3;

-- 4. mv_wh_patient_demographics
DECLARE OR REPLACE qry_4 STRING;
SET VAR qry_4 =
  "CREATE OR REPLACE VIEW " || :catalog || "." || :schema || ".mv_wh_patient_demographics
   WITH METRICS LANGUAGE YAML AS $$
  version: 1.1
  comment: \"Women's health population metrics by age group, insurance type, and chronic condition status.\"
  source: " || :catalog || "." || :schema || ".v_wh_encounter_patients
  dimensions:
    - name: Age Group
      expr: |
        CASE
          WHEN FLOOR(DATEDIFF(admission_date, date_of_birth) / 365.25) < 35 THEN 'Young Adult (18-34)'
          WHEN FLOOR(DATEDIFF(admission_date, date_of_birth) / 365.25) < 50 THEN 'Adult (35-49)'
          WHEN FLOOR(DATEDIFF(admission_date, date_of_birth) / 365.25) < 65 THEN 'Middle Age (50-64)'
          ELSE 'Senior (65+)'
        END
    - name: Insurance Type
      expr: insurance_type
    - name: Chronic Condition Flag
      expr: CASE WHEN num_chronic > 0 THEN 'Has Chronic Condition' ELSE 'No Chronic Condition' END
  measures:
    - name: Patient Count
      expr: COUNT(DISTINCT patient_id)
    - name: Total Encounters
      expr: COUNT(1)
    - name: Avg Encounters per Patient
      expr: COUNT(1) * 1.0 / NULLIF(COUNT(DISTINCT patient_id), 0)
  $$";
EXECUTE IMMEDIATE qry_4;

-- 5. mv_accelerate_encounters (Project Accelerate)
-- Customer customization: change source table name below if your encounters table differs.
-- The metric view is the abstraction layer — downstream fitting and simulations use MEASURE()
-- queries against this view, so column names in dimensions/measures must be preserved.
DECLARE OR REPLACE qry_5 STRING;
SET VAR qry_5 =
  "CREATE OR REPLACE VIEW " || :catalog || "." || :schema || ".mv_accelerate_encounters
   WITH METRICS LANGUAGE YAML AS $$
  version: 1.1
  comment: \"Encounter-level analytics with financial margins, SG2 taxonomy, and WH population segmentation.\"
  source: " || :catalog || "." || :schema || ".project_accelerate_encounters
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
      expr: CASE WHEN patient_age_years < 35 THEN '18-34' WHEN patient_age_years < 50 THEN '35-49' WHEN patient_age_years < 65 THEN '50-64' ELSE '65+' END
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
  $$";
EXECUTE IMMEDIATE qry_5;
