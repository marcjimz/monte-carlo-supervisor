-- Base views — pre-joined sources for metric views and Genie Space.
-- Parameters: :catalog, :schema (passed via DAB sql_task base_parameters)

USE CATALOG IDENTIFIER(:catalog);
USE SCHEMA IDENTIFIER(:schema);

-- 1. v_wh_billing_encounters — billing joined with encounters and primary diagnosis
CREATE OR REPLACE VIEW v_wh_billing_encounters AS
SELECT
    b.billing_id, b.encounter_id, b.total_charges, b.payer_id,
    b.allowed_amount, b.paid_amount, b.patient_responsibility, b.claim_status,
    b.payment_date, e.encounter_type, e.department, e.admission_date,
    e.discharge_date, e.facility_id, e.patient_id, e.provider_id,
    d.icd10_code AS primary_icd10_code
FROM billing AS b
JOIN encounters AS e ON b.encounter_id = e.encounter_id
LEFT JOIN diagnoses AS d
    ON e.encounter_id = d.encounter_id AND d.is_primary = 1;

-- 2. v_wh_encounter_patients — encounters joined with patient demographics
CREATE OR REPLACE VIEW v_wh_encounter_patients AS
SELECT
    e.encounter_id, e.patient_id, e.facility_id, e.encounter_type,
    e.department, e.admission_date, e.discharge_date, e.length_of_stay,
    pt.date_of_birth, pt.gender, pt.insurance_type, pt.num_chronic,
    pt.chronic_conditions
FROM encounters AS e
JOIN patients AS pt ON e.patient_id = pt.patient_id;

-- 3. v_wh_encounter_diagnoses — encounters joined with diagnoses and ICD-10 categories
CREATE OR REPLACE VIEW v_wh_encounter_diagnoses AS
SELECT
    e.encounter_id, e.patient_id, e.encounter_type, e.department,
    e.admission_date, e.length_of_stay,
    d.icd10_code, d.description AS diagnosis_description, d.is_primary,
    ic.category AS diagnosis_category
FROM encounters AS e
JOIN diagnoses AS d ON e.encounter_id = d.encounter_id
LEFT JOIN icd10_codes AS ic ON d.icd10_code = ic.icd10_code;
