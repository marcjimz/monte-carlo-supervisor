"""Configuration for synthetic data generation — Women's Health focus."""

SEED = 42

# Volume targets (WH-scoped: adult women only)
NUM_PATIENTS = 10_000
NUM_PROVIDERS = 200
NUM_FACILITIES = 8
NUM_ENCOUNTERS = 50_000

# Date range (3 years of data)
DATE_START = "2022-01-01"
DATE_END = "2024-12-31"

# Output directory
DATA_DIR = "data"

# Encounter type distribution (WH: primarily outpatient)
ENCOUNTER_TYPE_WEIGHTS = {
    "Outpatient": 0.60,
    "Emergency": 0.10,
    "Inpatient": 0.20,
    "Observation": 0.10,
}

# Insurance type distribution
INSURANCE_WEIGHTS = {
    "Medicare": 0.30,
    "Medicaid": 0.15,
    "Commercial - Blue Cross": 0.15,
    "Commercial - Aetna": 0.12,
    "Commercial - UnitedHealth": 0.12,
    "Commercial - Cigna": 0.08,
    "Self-Pay": 0.05,
    "Other": 0.03,
}

# Department list (WH-relevant subset)
DEPARTMENTS = [
    "OB/GYN",
    "Internal Medicine",
    "Endocrinology",
    "Psychiatry",
    "General Surgery",
    "Radiology",
    "Emergency",
]

# Chronic conditions relevant to women's health
CHRONIC_CONDITIONS = [
    "PCOS",
    "Endometriosis",
    "Hypertension",
    "Diabetes",
    "Obesity",
    "Depression",
    "Anxiety",
    "Hypothyroidism",
    "Menopause-related conditions",
    "Chronic Pelvic Pain",
]

# Specialties aligned with departments
SPECIALTIES = [
    "Obstetrics & Gynecology",
    "Internal Medicine",
    "Endocrinology",
    "Psychiatry",
    "General Surgery",
    "Radiology",
    "Emergency Medicine",
]

# LOS parameters by encounter type (log-normal mu, sigma)
LOS_PARAMS = {
    "Inpatient": (1.2, 0.7),       # median ~3.3 days
    "Observation": (0.3, 0.4),      # median ~1.3 days
    "Emergency": (0.0, 0.3),        # median ~1 day (hours)
    "Outpatient": (0.0, 0.1),       # same-day
}

# Billing parameters by encounter type (mean charges)
CHARGE_PARAMS = {
    "Inpatient": (15000, 8000),
    "Emergency": (3500, 2000),
    "Observation": (5000, 2500),
    "Outpatient": (1200, 800),
}

# Payer reimbursement rates (fraction of charges)
PAYER_REIMBURSEMENT = {
    "Medicare": 0.78,
    "Medicaid": 0.65,
    "Commercial - Blue Cross": 0.88,
    "Commercial - Aetna": 0.85,
    "Commercial - UnitedHealth": 0.87,
    "Commercial - Cigna": 0.86,
    "Self-Pay": 0.40,
    "Other": 0.75,
}

# Claim denial rate
DENIAL_RATE = 0.08
