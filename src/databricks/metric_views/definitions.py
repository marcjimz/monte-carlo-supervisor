"""UC Metric View definitions using CREATE VIEW ... WITH METRICS LANGUAGE YAML."""


def get_metric_view_definitions(catalog: str, schema: str) -> list[dict]:
    """Return all metric view definitions as (name, sql) pairs."""
    return [
        {
            "name": "mv_encounter_summary",
            "sql": f"""
CREATE OR REPLACE VIEW {catalog}.{schema}.mv_encounter_summary
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Hospital encounter KPIs by department, type, and time period. Use for volume trends, LOS analysis, and operational reporting."
  source: {catalog}.{schema}.encounters
  filter: admission_date IS NOT NULL
  dimensions:
    - name: Department
      expr: department
      comment: "Hospital department (Emergency, Cardiology, Orthopedics, etc.)"
    - name: Encounter Type
      expr: encounter_type
      comment: "Type of visit: Inpatient, Outpatient, Emergency, or Observation"
    - name: Admission Month
      expr: DATE_TRUNC('MONTH', admission_date)
      comment: "Month of admission for time-series trending"
    - name: Admission Year
      expr: YEAR(admission_date)
      comment: "Year of admission"
    - name: Facility ID
      expr: facility_id
      comment: "Facility where encounter occurred"
  measures:
    - name: Total Encounters
      expr: COUNT(1)
      comment: "Total number of patient encounters"
    - name: Avg Length of Stay
      expr: AVG(length_of_stay)
      comment: "Average days from admission to discharge"
    - name: Median Length of Stay
      expr: PERCENTILE_APPROX(length_of_stay, 0.5)
      comment: "Median length of stay in days"
    - name: Max Length of Stay
      expr: MAX(length_of_stay)
      comment: "Maximum length of stay in days"
    - name: Unique Patients
      expr: COUNT(DISTINCT patient_id)
      comment: "Number of distinct patients seen"
$$;""",
        },
        {
            "name": "mv_revenue_by_payer",
            "sql": f"""
CREATE OR REPLACE VIEW {catalog}.{schema}.mv_revenue_by_payer
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Revenue and reimbursement KPIs by payer, encounter type, and time period. Use for financial analysis, denial tracking, and payer mix analysis."
  source: {catalog}.{schema}.billing AS b JOIN {catalog}.{schema}.encounters AS e ON b.encounter_id = e.encounter_id
  dimensions:
    - name: Payer ID
      expr: b.payer_id
      comment: "Insurance payer identifier"
    - name: Encounter Type
      expr: e.encounter_type
      comment: "Type of visit: Inpatient, Outpatient, Emergency, or Observation"
    - name: Payment Month
      expr: DATE_TRUNC('MONTH', e.admission_date)
      comment: "Month of service for revenue trending"
    - name: Claim Status
      expr: b.claim_status
      comment: "Claim status: Paid, Denied, or Pending"
    - name: Facility ID
      expr: e.facility_id
      comment: "Facility where service was rendered"
  measures:
    - name: Total Revenue
      expr: SUM(b.paid_amount)
      comment: "Total amount collected from all payers"
    - name: Total Charges
      expr: SUM(b.total_charges)
      comment: "Total gross charges before adjustments"
    - name: Avg Reimbursement Rate
      expr: SUM(b.paid_amount) / NULLIF(SUM(b.total_charges), 0)
      comment: "Ratio of paid amount to total charges"
    - name: Denial Count
      expr: COUNT(1) FILTER (WHERE b.claim_status = 'Denied')
      comment: "Number of denied claims"
    - name: Denial Rate
      expr: COUNT(1) FILTER (WHERE b.claim_status = 'Denied') * 1.0 / NULLIF(COUNT(1), 0)
      comment: "Fraction of claims that were denied"
    - name: Avg Patient Responsibility
      expr: AVG(b.patient_responsibility)
      comment: "Average out-of-pocket cost per encounter"
$$;""",
        },
        {
            "name": "mv_readmission_rates",
            "sql": f"""
CREATE OR REPLACE VIEW {catalog}.{schema}.mv_readmission_rates
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "30-day readmission rate KPIs by diagnosis, department, and time. Use for quality reporting and readmission risk analysis."
  source: {catalog}.{schema}.encounters AS e LEFT JOIN {catalog}.{schema}.readmissions AS r ON e.encounter_id = r.original_encounter_id LEFT JOIN {catalog}.{schema}.diagnoses AS d ON e.encounter_id = d.encounter_id AND d.is_primary = TRUE
  filter: e.encounter_type = 'Inpatient'
  dimensions:
    - name: Department
      expr: e.department
      comment: "Discharging department"
    - name: Diagnosis Category
      expr: SUBSTRING(d.icd10_code, 1, 3)
      comment: "First 3 characters of primary ICD-10 code"
    - name: Discharge Quarter
      expr: DATE_TRUNC('QUARTER', e.discharge_date)
      comment: "Quarter of discharge for trending"
    - name: Facility ID
      expr: e.facility_id
      comment: "Facility of original admission"
  measures:
    - name: Total Discharges
      expr: COUNT(DISTINCT e.encounter_id)
      comment: "Total inpatient discharges"
    - name: Readmission Count
      expr: COUNT(DISTINCT r.readmission_id)
      comment: "Number of 30-day readmissions"
    - name: Readmission Rate
      expr: COUNT(DISTINCT r.readmission_id) * 1.0 / NULLIF(COUNT(DISTINCT e.encounter_id), 0)
      comment: "30-day readmission rate as fraction"
    - name: Avg Days to Readmission
      expr: AVG(r.days_between)
      comment: "Average days between discharge and readmission"
$$;""",
        },
        {
            "name": "mv_daily_census",
            "sql": f"""
CREATE OR REPLACE VIEW {catalog}.{schema}.mv_daily_census
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Daily inpatient census and bed utilization. Use for capacity planning and occupancy analysis."
  source: {catalog}.{schema}.encounters
  filter: encounter_type = 'Inpatient' AND admission_date IS NOT NULL
  dimensions:
    - name: Department
      expr: department
      comment: "Hospital department"
    - name: Facility ID
      expr: facility_id
      comment: "Facility identifier"
    - name: Admission Date
      expr: admission_date
      comment: "Date of admission for daily census"
    - name: Admission Month
      expr: DATE_TRUNC('MONTH', admission_date)
      comment: "Month for monthly census trending"
  measures:
    - name: Daily Admissions
      expr: COUNT(1)
      comment: "Number of admissions on a given day"
    - name: Avg Length of Stay
      expr: AVG(length_of_stay)
      comment: "Average LOS for admitted patients"
    - name: Total Bed Days
      expr: SUM(length_of_stay)
      comment: "Total patient-days (sum of all LOS)"
$$;""",
        },
        {
            "name": "mv_department_throughput",
            "sql": f"""
CREATE OR REPLACE VIEW {catalog}.{schema}.mv_department_throughput
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Department-level operational throughput including patient volume and procedure counts."
  source: {catalog}.{schema}.encounters AS e LEFT JOIN {catalog}.{schema}.procedures AS p ON e.encounter_id = p.encounter_id
  dimensions:
    - name: Department
      expr: e.department
      comment: "Hospital department"
    - name: Encounter Type
      expr: e.encounter_type
      comment: "Type of visit"
    - name: Service Month
      expr: DATE_TRUNC('MONTH', e.admission_date)
      comment: "Month of service"
    - name: Facility ID
      expr: e.facility_id
      comment: "Facility identifier"
  measures:
    - name: Patient Volume
      expr: COUNT(DISTINCT e.encounter_id)
      comment: "Number of unique encounters"
    - name: Procedure Count
      expr: COUNT(p.procedure_id)
      comment: "Total procedures performed"
    - name: Procedures per Encounter
      expr: COUNT(p.procedure_id) * 1.0 / NULLIF(COUNT(DISTINCT e.encounter_id), 0)
      comment: "Average procedures per patient encounter"
    - name: Avg Length of Stay
      expr: AVG(e.length_of_stay)
      comment: "Average length of stay"
$$;""",
        },
        {
            "name": "mv_patient_demographics",
            "sql": f"""
CREATE OR REPLACE VIEW {catalog}.{schema}.mv_patient_demographics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Population health metrics by age group, gender, and insurance type. Use for demographic analysis and chronic condition prevalence."
  source: {catalog}.{schema}.encounters AS e JOIN {catalog}.{schema}.patients AS pt ON e.patient_id = pt.patient_id
  dimensions:
    - name: Age Group
      expr: CASE
        WHEN FLOOR(DATEDIFF(e.admission_date, pt.date_of_birth) / 365.25) < 18 THEN 'Pediatric (0-17)'
        WHEN FLOOR(DATEDIFF(e.admission_date, pt.date_of_birth) / 365.25) < 35 THEN 'Young Adult (18-34)'
        WHEN FLOOR(DATEDIFF(e.admission_date, pt.date_of_birth) / 365.25) < 50 THEN 'Adult (35-49)'
        WHEN FLOOR(DATEDIFF(e.admission_date, pt.date_of_birth) / 365.25) < 65 THEN 'Middle Age (50-64)'
        ELSE 'Senior (65+)'
        END
      comment: "Patient age group at time of encounter"
    - name: Gender
      expr: pt.gender
      comment: "Patient gender"
    - name: Insurance Type
      expr: pt.insurance_type
      comment: "Patient insurance type"
    - name: Encounter Year
      expr: YEAR(e.admission_date)
      comment: "Year of encounter"
  measures:
    - name: Patient Count
      expr: COUNT(DISTINCT pt.patient_id)
      comment: "Number of distinct patients"
    - name: Total Encounters
      expr: COUNT(1)
      comment: "Total encounters for demographic group"
    - name: Encounters per Patient
      expr: COUNT(1) * 1.0 / NULLIF(COUNT(DISTINCT pt.patient_id), 0)
      comment: "Average encounters per patient"
    - name: Avg Age
      expr: AVG(FLOOR(DATEDIFF(e.admission_date, pt.date_of_birth) / 365.25))
      comment: "Average patient age at encounter"
$$;""",
        },
    ]


def get_all_metric_view_ddl(catalog: str, schema: str) -> list[str]:
    """Return just the SQL DDL strings for all metric views."""
    return [mv["sql"] for mv in get_metric_view_definitions(catalog, schema)]
