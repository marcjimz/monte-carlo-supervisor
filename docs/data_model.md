# Data Model

All tables reside in Unity Catalog under `{catalog}.{schema}` (default: `monte_carlo_sim.hospital_data`). The synthetic dataset represents a three-year hospital system with 15 facilities, 25,000 patients, and 120,000 encounters spanning January 2022 through December 2024.

---

## Entity Relationship Overview

```
patients ──────────┐
                    │ patient_id
providers ─────┐   ├──── encounters ──────┬──── diagnoses ──── icd10_codes
               │   │     │ encounter_id   │     (icd10_code)
facilities ────┘   │     │                ├──── procedures ──── cpt_codes
  (facility_id,    │     │                │     (cpt_code)
   provider_id)    │     │                ├──── billing ──── payers
                   │     │                │     (payer_id)
                   │     │                └──── readmissions
                   │     │                      (original_encounter_id,
                   │     │                       readmit_encounter_id)
                   │     │
                   │     └──── departments
                   │
                   └───── (patient_id links to encounters)
```

**Central fact table:** `encounters` is the primary fact table. All clinical and financial tables join to it via `encounter_id`. Patient demographics join via `patient_id`.

---

## Dimension Tables

### patients

Patient demographics including insurance and chronic conditions. Each patient has a unique ID and may have multiple encounters over the three-year period.

| Column | Type | Description |
|---|---|---|
| `patient_id` | STRING | Unique patient identifier (UUID) |
| `first_name` | STRING | Patient first name |
| `last_name` | STRING | Patient last name |
| `date_of_birth` | DATE | Date of birth (bimodal age distribution) |
| `gender` | STRING | Gender (Male, Female, Other) |
| `race` | STRING | Race/ethnicity category |
| `zip_code` | STRING | 5-digit zip code |
| `insurance_type` | STRING | Primary insurance type (Medicare, Medicaid, Commercial, Self-Pay, Other) |
| `chronic_conditions` | STRING | Comma-separated list of chronic conditions (Diabetes, Hypertension, COPD, etc.) |
| `created_at` | TIMESTAMP | Record creation timestamp |

**~25,000 rows.** Age distribution is bimodal (pediatric peak and senior peak). Chronic condition prevalence increases with age. Insurance type distribution: Medicare 30%, Medicaid 15%, Commercial 47%, Self-Pay 5%, Other 3%.

### providers

Physician and clinical provider records associated with facilities.

| Column | Type | Description |
|---|---|---|
| `provider_id` | STRING | Unique provider identifier (UUID) |
| `first_name` | STRING | Provider first name |
| `last_name` | STRING | Provider last name |
| `specialty` | STRING | Medical specialty (20 specialties aligned with departments) |
| `facility_id` | STRING | FK to facilities.facility_id |
| `npi` | STRING | National Provider Identifier (10-digit) |
| `created_at` | TIMESTAMP | Record creation timestamp |

**~500 rows.** Providers are distributed across 15 facilities with specialties aligned to departments.

### facilities

Hospital and clinic locations.

| Column | Type | Description |
|---|---|---|
| `facility_id` | STRING | Unique facility identifier (UUID) |
| `facility_name` | STRING | Facility name |
| `facility_type` | STRING | Type (Hospital, Clinic, Urgent Care, etc.) |
| `bed_count` | INT | Total licensed bed count |
| `city` | STRING | City |
| `state` | STRING | State abbreviation |
| `zip_code` | STRING | 5-digit zip code |
| `created_at` | TIMESTAMP | Record creation timestamp |

**~15 rows.** Mix of large hospitals (300+ beds) and smaller clinics.

---

## Fact Tables

### encounters

The central fact table recording every patient-facility interaction. All clinical and financial tables join to encounters via `encounter_id`.

| Column | Type | Description |
|---|---|---|
| `encounter_id` | STRING | Unique encounter identifier (UUID) |
| `patient_id` | STRING | FK to patients.patient_id |
| `provider_id` | STRING | FK to providers.provider_id |
| `facility_id` | STRING | FK to facilities.facility_id |
| `encounter_type` | STRING | Type: Inpatient (20%), Outpatient (45%), Emergency (25%), Observation (10%) |
| `admission_date` | DATE | Date of admission or visit |
| `discharge_date` | DATE | Date of discharge (same day for Outpatient) |
| `length_of_stay` | DOUBLE | Days from admission to discharge |
| `department` | STRING | Department name (20 departments) |
| `created_at` | TIMESTAMP | Record creation timestamp |

**~120,000 rows.** Seasonal patterns: elevated volumes November-February (flu season), weekday/weekend ER variation. LOS follows log-normal distributions per encounter type: Inpatient median ~3.3 days, Observation ~1.3 days, Emergency ~1 day, Outpatient same-day.

### diagnoses

ICD-10 diagnosis codes assigned to encounters. Each encounter may have one primary and multiple secondary diagnoses.

| Column | Type | Description |
|---|---|---|
| `diagnosis_id` | STRING | Unique diagnosis record identifier (UUID) |
| `encounter_id` | STRING | FK to encounters.encounter_id |
| `icd10_code` | STRING | ICD-10-CM code (e.g., I50.9 for heart failure) |
| `is_primary` | BOOLEAN | Whether this is the primary diagnosis for the encounter |
| `created_at` | TIMESTAMP | Record creation timestamp |

**~180,000 rows.** Average of 1.5 diagnoses per encounter. Primary diagnosis is always present; secondary diagnoses correlate with chronic conditions and encounter type.

### procedures

CPT procedure codes associated with encounters.

| Column | Type | Description |
|---|---|---|
| `procedure_id` | STRING | Unique procedure record identifier (UUID) |
| `encounter_id` | STRING | FK to encounters.encounter_id |
| `cpt_code` | STRING | CPT procedure code |
| `procedure_date` | DATE | Date procedure was performed |
| `created_at` | TIMESTAMP | Record creation timestamp |

**~90,000 rows.** Not all encounters have procedures (Outpatient visits may have none). Inpatient and surgical encounters have higher procedure counts.

### billing

Claims and billing records linked to encounters. One billing record per encounter.

| Column | Type | Description |
|---|---|---|
| `billing_id` | STRING | Unique billing record identifier (UUID) |
| `encounter_id` | STRING | FK to encounters.encounter_id |
| `payer_id` | STRING | FK to payers.payer_id |
| `total_charges` | DOUBLE | Gross charges before adjustments |
| `allowed_amount` | DOUBLE | Payer-allowed amount |
| `paid_amount` | DOUBLE | Actual amount paid by payer |
| `patient_responsibility` | DOUBLE | Patient out-of-pocket amount |
| `claim_status` | STRING | Claim status: Paid, Denied, or Pending |
| `created_at` | TIMESTAMP | Record creation timestamp |

**~120,000 rows.** One-to-one with encounters. Charges follow normal distributions by encounter type (Inpatient mean $15K, Emergency $3.5K, Observation $5K, Outpatient $1.2K). Reimbursement rates are payer-specific (Medicare 78%, Commercial 85-88%, Self-Pay 40%). Claim denial rate is approximately 8%.

### readmissions

30-day readmission events linking an original discharge to a subsequent admission.

| Column | Type | Description |
|---|---|---|
| `readmission_id` | STRING | Unique readmission record identifier (UUID) |
| `original_encounter_id` | STRING | FK to encounters.encounter_id (original admission) |
| `readmit_encounter_id` | STRING | FK to encounters.encounter_id (readmission) |
| `days_between` | INT | Days between discharge and readmission (1-30) |
| `created_at` | TIMESTAMP | Record creation timestamp |

**~8,000 rows.** Readmissions are generated based on encounter type and patient chronic conditions. Patients with chronic conditions (heart failure, COPD, diabetes) have higher readmission rates.

---

## Reference Tables

### icd10_codes

ICD-10-CM diagnosis code lookup.

| Column | Type | Description |
|---|---|---|
| `icd10_code` | STRING | ICD-10-CM code |
| `description` | STRING | Human-readable diagnosis description |
| `category` | STRING | Broad category (first 3 characters of code) |

**~500 rows.** Covers common inpatient and emergency diagnoses across all departments.

### cpt_codes

CPT procedure code lookup.

| Column | Type | Description |
|---|---|---|
| `cpt_code` | STRING | CPT code |
| `description` | STRING | Human-readable procedure description |
| `category` | STRING | Procedure category (Surgery, Radiology, Lab, etc.) |

**~300 rows.** Common hospital procedures spanning evaluation, surgical, diagnostic, and therapeutic categories.

### payers

Insurance payer reference data.

| Column | Type | Description |
|---|---|---|
| `payer_id` | STRING | Unique payer identifier |
| `payer_name` | STRING | Payer name |
| `payer_type` | STRING | Type: Government, Commercial, Self-Pay |

**~10 rows.** Medicare, Medicaid, four commercial payers (Blue Cross, Aetna, UnitedHealth, Cigna), Self-Pay, and Other.

### departments

Hospital department reference data.

| Column | Type | Description |
|---|---|---|
| `department_id` | STRING | Unique department identifier |
| `department_name` | STRING | Department name |

**~20 rows.** Emergency, Cardiology, Orthopedics, General Surgery, Internal Medicine, Pediatrics, Obstetrics, Neurology, Oncology, Pulmonology, Gastroenterology, Nephrology, Endocrinology, Dermatology, Urology, Psychiatry, Radiology, Anesthesiology, Rehabilitation, Intensive Care.

---

## Simulation Result Tables

These tables are created by notebook `04_create_simulation_tables.py` and populated by the Monte Carlo pipeline.

### simulation_runs

Metadata for each Monte Carlo simulation run, serving as both an audit log and a cache index.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `run_id` | STRING | NOT NULL | Unique simulation run identifier (UUID) |
| `simulation_type` | STRING | NOT NULL | Simulation type (patient_volume, revenue, length_of_stay, readmission_rate, ed_wait_time) |
| `parameters` | STRING | NOT NULL | JSON-encoded simulation parameters |
| `params_hash` | STRING | NOT NULL | SHA-256 hash for cache lookup |
| `seed` | INT | NOT NULL | Base random seed |
| `num_simulations` | INT | NOT NULL | Total number of Monte Carlo trials |
| `status` | STRING | NOT NULL | Run status: RUNNING, COMPLETED, or FAILED |
| `job_run_id` | STRING | Nullable | Databricks Job run ID |
| `created_at` | STRING | NOT NULL | ISO-8601 UTC timestamp of run creation |
| `updated_at` | STRING | NOT NULL | ISO-8601 UTC timestamp of last status update |

**Delta table properties:** autoOptimize.optimizeWrite = true, autoOptimize.autoCompact = true.

### simulation_trials

Bronze table containing raw trial-level results from every simulation run.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `run_id` | STRING | NOT NULL | FK to simulation_runs.run_id |
| `batch_id` | BIGINT | NOT NULL | Batch index (Spark partition) |
| `trial_id` | BIGINT | NOT NULL | Global trial index |
| `month` | STRING | Nullable | Simulated month label (patient_volume, revenue) |
| `department` | STRING | Nullable | Department name (length_of_stay, readmission_rate) |
| `hour_of_day` | INT | Nullable | Hour 0-23 (ed_wait_time) |
| `simulated_encounters` | DOUBLE | Nullable | Simulated encounter count (patient_volume) |
| `simulated_revenue` | DOUBLE | Nullable | Simulated revenue (revenue) |
| `simulated_charges` | DOUBLE | Nullable | Simulated charges (revenue) |
| `simulated_avg_los` | DOUBLE | Nullable | Simulated avg length of stay (length_of_stay) |
| `simulated_readmission_rate` | DOUBLE | Nullable | Simulated readmission rate (readmission_rate) |
| `simulated_wait_minutes` | DOUBLE | Nullable | Simulated ED wait time (ed_wait_time) |
| `created_at` | STRING | NOT NULL | ISO-8601 UTC timestamp |

**Partitioned by** `run_id`. This is a wide table where only the columns relevant to the simulation type are populated; others are NULL.

### simulation_results

Gold table containing aggregated percentile distributions for each simulation run.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `run_id` | STRING | NOT NULL | FK to simulation_runs.run_id |
| `simulation_type` | STRING | NOT NULL | Type of simulation |
| `metric_name` | STRING | NOT NULL | Name of the simulated metric column |
| `group_key` | STRING | NOT NULL | Dimension name used for grouping (month, department, hour_of_day) |
| `group_value` | STRING | NOT NULL | Dimension value |
| `num_trials` | BIGINT | NOT NULL | Number of trials aggregated |
| `mean_value` | DOUBLE | NOT NULL | Mean of simulated metric |
| `std_value` | DOUBLE | Nullable | Standard deviation |
| `min_value` | DOUBLE | Nullable | Minimum value |
| `max_value` | DOUBLE | Nullable | Maximum value |
| `p05` | DOUBLE | Nullable | 5th percentile |
| `p10` | DOUBLE | Nullable | 10th percentile |
| `p25` | DOUBLE | Nullable | 25th percentile |
| `p50` | DOUBLE | Nullable | 50th percentile (median) |
| `p75` | DOUBLE | Nullable | 75th percentile |
| `p90` | DOUBLE | Nullable | 90th percentile |
| `p95` | DOUBLE | Nullable | 95th percentile |
| `created_at` | STRING | NOT NULL | ISO-8601 UTC timestamp |

**Partitioned by** `run_id`. This is the table queried by Genie for past simulation results and returned by the UC Function for cached results.

---

## Relationships

```
patients.patient_id          --> encounters.patient_id       (1:many)
providers.provider_id        --> encounters.provider_id      (1:many)
facilities.facility_id       --> encounters.facility_id      (1:many)
facilities.facility_id       --> providers.facility_id       (1:many)
encounters.encounter_id      --> diagnoses.encounter_id      (1:many)
encounters.encounter_id      --> procedures.encounter_id     (1:many)
encounters.encounter_id      --> billing.encounter_id        (1:1)
encounters.encounter_id      --> readmissions.original_encounter_id  (1:0..1)
encounters.encounter_id      --> readmissions.readmit_encounter_id   (1:0..1)
icd10_codes.icd10_code       --> diagnoses.icd10_code        (1:many)
cpt_codes.cpt_code           --> procedures.cpt_code         (1:many)
payers.payer_id              --> billing.payer_id            (1:many)
simulation_runs.run_id       --> simulation_trials.run_id    (1:many)
simulation_runs.run_id       --> simulation_results.run_id   (1:many)
```

---

## Generation Strategy

### Seeded Deterministic Generation

All synthetic data is generated using `numpy.random.default_rng(seed=42)`. The global seed is defined in `src/databricks/synthetic_data/config.py` and passed to all generators. Running `make generate-data` produces identical CSV files every time.

### Pre-Generated CSV Files

Twelve CSV files are committed to the `/data/` directory:

```
data/
├── patients.csv          (~25,000 rows)
├── providers.csv         (~500 rows)
├── facilities.csv        (~15 rows)
├── encounters.csv        (~120,000 rows)
├── diagnoses.csv         (~180,000 rows)
├── procedures.csv        (~90,000 rows)
├── billing.csv           (~120,000 rows)
├── readmissions.csv      (~8,000 rows)
├── icd10_codes.csv       (~500 rows)
├── cpt_codes.csv         (~300 rows)
├── payers.csv            (~10 rows)
└── departments.csv       (~20 rows)
```

### Realistic Distribution Characteristics

- **Age**: Bimodal distribution with pediatric and senior peaks
- **Seasonality**: Encounter volumes spike November-February (flu season)
- **Weekday/Weekend**: ER encounters show different patterns on weekdays vs. weekends
- **Chronic conditions**: Higher prevalence in older patients, correlated with longer LOS and higher readmission rates
- **Financial realism**: Payer-specific reimbursement rates (Medicare 78%, Commercial 85-88%, Self-Pay 40%), 8% claim denial rate
- **LOS distributions**: Log-normal per encounter type (Inpatient mu=1.2/sigma=0.7, Emergency mu=0.0/sigma=0.3)
- **Charges**: Normal distributions by encounter type (Inpatient mean $15K, Emergency mean $3.5K)
