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
