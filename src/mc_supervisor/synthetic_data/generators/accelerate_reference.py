"""Reference data for Project Accelerate encounters.

SG2 taxonomy, business units, regions, ICD-10 mappings, and financial parameters.
Used by the encounter generator to produce realistic synthetic data.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Business units and regions
# ---------------------------------------------------------------------------

BUSINESS_UNITS = [
    {"id": "BU001", "name": "North General Hospital", "region": "North"},
    {"id": "BU002", "name": "North Specialty Center", "region": "North"},
    {"id": "BU003", "name": "Central Medical Center", "region": "Central"},
    {"id": "BU004", "name": "Central Outpatient Pavilion", "region": "Central"},
    {"id": "BU005", "name": "South Community Hospital", "region": "South"},
    {"id": "BU006", "name": "South Women's Center", "region": "South"},
]

REGIONS = ["North", "Central", "South"]

# ---------------------------------------------------------------------------
# Encounter classification
# ---------------------------------------------------------------------------

BASE_CLASS_WEIGHTS = {
    "Inpatient": 0.20,
    "Outpatient": 0.50,
    "Emergency": 0.15,
    "Observation": 0.15,
}

PATIENT_CLASS_MAP = {
    "Inpatient": ["Inpatient", "Inpatient Rehab", "Inpatient Psych"],
    "Outpatient": ["Outpatient", "Outpatient Surgery", "Day Surgery"],
    "Emergency": ["Emergency", "Emergency Psych"],
    "Observation": ["Observation", "Extended Observation"],
}

PATIENT_CLASS_INNER_WEIGHTS = {
    "Inpatient": [0.80, 0.12, 0.08],
    "Outpatient": [0.70, 0.20, 0.10],
    "Emergency": [0.90, 0.10],
    "Observation": [0.80, 0.20],
}

SOURCE_SYSTEMS = ["Epic", "Cerner", "Meditech"]
SOURCE_SYSTEM_WEIGHTS = [0.60, 0.30, 0.10]

# ---------------------------------------------------------------------------
# Financial parameters
# ---------------------------------------------------------------------------

FIN_CLASS_WEIGHTS = {
    "Commercial": 0.45,
    "Medicare": 0.25,
    "Medicaid": 0.15,
    "Self-Pay": 0.10,
    "Other": 0.05,
}

REIMBURSEMENT_RATES = {
    "Commercial": 0.88,
    "Medicare": 0.78,
    "Medicaid": 0.65,
    "Self-Pay": 0.40,
    "Other": 0.75,
}

# Charge parameters by base class: (log_mean, log_sigma) for lognormal
CHARGE_LOG_PARAMS = {
    "Inpatient": (9.80, 0.60),    # median ~$18,000
    "Outpatient": (7.31, 0.55),   # median ~$1,500
    "Emergency": (8.29, 0.50),    # median ~$4,000
    "Observation": (8.70, 0.45),  # median ~$6,000
}

COST_TO_CHARGE = {
    "Inpatient": (0.65, 0.80),
    "Outpatient": (0.60, 0.75),
    "Emergency": (0.70, 0.85),
    "Observation": (0.65, 0.78),
}

# LOS parameters by base class: (log_mean, log_sigma) for lognormal
LOS_LOG_PARAMS = {
    "Inpatient": (1.2, 0.7),
    "Outpatient": (0.0, 0.1),
    "Emergency": (0.0, 0.3),
    "Observation": (0.3, 0.4),
}

# ---------------------------------------------------------------------------
# SG2 taxonomy (service line -> care family -> disease base)
# ---------------------------------------------------------------------------

SG2_TAXONOMY = {
    "Women's Health": {
        "Obstetrics": ["Normal Delivery", "C-Section Delivery", "High-Risk Pregnancy", "Prenatal Care"],
        "Gynecology": ["Menstrual Disorders", "Endometriosis", "Uterine Fibroids", "Pelvic Floor Disorders"],
        "Breast Health": ["Breast Cancer Screening", "Breast Biopsy", "Breast Cancer Treatment"],
        "Reproductive Medicine": ["Fertility Treatment", "Contraceptive Management"],
    },
    "Cardiovascular": {
        "Heart Failure": ["CHF Management", "Cardiomyopathy"],
        "Coronary Artery Disease": ["Stable Angina", "Acute MI"],
        "Arrhythmia": ["Atrial Fibrillation", "SVT Management"],
    },
    "Orthopedics": {
        "Joint Replacement": ["Hip Replacement", "Knee Replacement"],
        "Spine": ["Lumbar Disc Disease", "Cervical Disc Disease"],
        "Sports Medicine": ["ACL Repair", "Rotator Cuff"],
    },
    "Neurosciences": {
        "Stroke": ["Ischemic Stroke", "TIA Management"],
        "Headache": ["Migraine Management", "Cluster Headache"],
    },
    "General Medicine": {
        "Diabetes": ["Type 2 Diabetes", "Diabetic Complications"],
        "Endocrine": ["Hypothyroidism", "Adrenal Disorders"],
        "Pulmonary": ["COPD Management", "Asthma"],
    },
    "Digestive Health": {
        "Gastroenterology": ["GERD", "IBS Management"],
        "Hepatology": ["Fatty Liver Disease", "Hepatitis Management"],
    },
    "Behavioral Health": {
        "Depression": ["Major Depression", "Postpartum Depression"],
        "Anxiety": ["Generalized Anxiety", "Panic Disorder"],
    },
    "Oncology": {
        "Gynecologic Oncology": ["Ovarian Cancer", "Cervical Cancer"],
        "Breast Oncology": ["Early Stage Breast Cancer", "Metastatic Breast Cancer"],
    },
    "Urology": {
        "Urinary": ["UTI Management", "Incontinence"],
    },
}

# ICD-10 codes mapped to SG2: (icd_code, diagnosis_name, service_line, care_family, disease_base)
ICD_SG2_MAPPING = [
    # Women's Health
    ("O80", "Full-term uncomplicated delivery", "Women's Health", "Obstetrics", "Normal Delivery"),
    ("O82", "Cesarean delivery", "Women's Health", "Obstetrics", "C-Section Delivery"),
    ("O09.90", "Supervision of high risk pregnancy", "Women's Health", "Obstetrics", "High-Risk Pregnancy"),
    ("Z34.90", "Supervision of normal pregnancy", "Women's Health", "Obstetrics", "Prenatal Care"),
    ("N92.0", "Excessive and frequent menstruation", "Women's Health", "Gynecology", "Menstrual Disorders"),
    ("N80.0", "Endometriosis of uterus", "Women's Health", "Gynecology", "Endometriosis"),
    ("D25.9", "Leiomyoma of uterus, unspecified", "Women's Health", "Gynecology", "Uterine Fibroids"),
    ("N81.2", "Incomplete uterovaginal prolapse", "Women's Health", "Gynecology", "Pelvic Floor Disorders"),
    ("Z12.31", "Screening mammogram", "Women's Health", "Breast Health", "Breast Cancer Screening"),
    ("N63.0", "Unspecified lump in breast", "Women's Health", "Breast Health", "Breast Biopsy"),
    ("C50.919", "Malignant neoplasm of breast", "Women's Health", "Breast Health", "Breast Cancer Treatment"),
    ("N97.9", "Female infertility, unspecified", "Women's Health", "Reproductive Medicine", "Fertility Treatment"),
    ("Z30.09", "Contraceptive management", "Women's Health", "Reproductive Medicine", "Contraceptive Management"),
    # Cardiovascular
    ("I50.9", "Heart failure, unspecified", "Cardiovascular", "Heart Failure", "CHF Management"),
    ("I42.9", "Cardiomyopathy, unspecified", "Cardiovascular", "Heart Failure", "Cardiomyopathy"),
    ("I25.10", "Atherosclerotic heart disease", "Cardiovascular", "Coronary Artery Disease", "Stable Angina"),
    ("I21.9", "Acute myocardial infarction", "Cardiovascular", "Coronary Artery Disease", "Acute MI"),
    ("I48.91", "Atrial fibrillation", "Cardiovascular", "Arrhythmia", "Atrial Fibrillation"),
    # Orthopedics
    ("M16.11", "Primary osteoarthritis, right hip", "Orthopedics", "Joint Replacement", "Hip Replacement"),
    ("M17.11", "Primary osteoarthritis, right knee", "Orthopedics", "Joint Replacement", "Knee Replacement"),
    ("M51.16", "Lumbar disc disorder with radiculopathy", "Orthopedics", "Spine", "Lumbar Disc Disease"),
    # Neurosciences
    ("I63.9", "Cerebral infarction, unspecified", "Neurosciences", "Stroke", "Ischemic Stroke"),
    ("G43.909", "Migraine, unspecified", "Neurosciences", "Headache", "Migraine Management"),
    # General Medicine
    ("E11.9", "Type 2 diabetes without complications", "General Medicine", "Diabetes", "Type 2 Diabetes"),
    ("E03.9", "Hypothyroidism, unspecified", "General Medicine", "Endocrine", "Hypothyroidism"),
    ("J44.1", "COPD with acute exacerbation", "General Medicine", "Pulmonary", "COPD Management"),
    ("J45.20", "Mild intermittent asthma", "General Medicine", "Pulmonary", "Asthma"),
    # Digestive Health
    ("K21.0", "GERD with esophagitis", "Digestive Health", "Gastroenterology", "GERD"),
    ("K58.9", "IBS without diarrhea", "Digestive Health", "Gastroenterology", "IBS Management"),
    # Behavioral Health
    ("F32.9", "Major depressive disorder", "Behavioral Health", "Depression", "Major Depression"),
    ("F53.0", "Postpartum depression", "Behavioral Health", "Depression", "Postpartum Depression"),
    ("F41.1", "Generalized anxiety disorder", "Behavioral Health", "Anxiety", "Generalized Anxiety"),
    # Oncology
    ("C56.9", "Malignant neoplasm of ovary", "Oncology", "Gynecologic Oncology", "Ovarian Cancer"),
    ("C53.9", "Malignant neoplasm of cervix uteri", "Oncology", "Gynecologic Oncology", "Cervical Cancer"),
    # Urology
    ("N39.0", "Urinary tract infection", "Urology", "Urinary", "UTI Management"),
    ("N39.3", "Stress incontinence", "Urology", "Urinary", "Incontinence"),
]

WH_SERVICE_LINE = "Women's Health"

# ---------------------------------------------------------------------------
# Patient name generation (no Faker dependency)
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "Emma", "Olivia", "Ava", "Isabella", "Sophia", "Mia", "Charlotte", "Amelia",
    "Harper", "Evelyn", "Abigail", "Emily", "Elizabeth", "Sofia", "Ella",
    "Madison", "Scarlett", "Victoria", "Aria", "Grace", "Chloe", "Camila",
    "Penelope", "Riley", "Layla", "Lillian", "Nora", "Zoey", "Hannah", "Lily",
    "Eleanor", "Hazel", "Violet", "Aurora", "Savannah", "Audrey", "Brooklyn",
    "Bella", "Claire", "Skylar", "Lucy", "Paisley", "Everly", "Anna", "Caroline",
    "Nova", "Genesis", "Emilia", "Kennedy", "Samantha", "Maya", "Willow",
    "Kinsley", "Naomi", "Aaliyah", "Elena", "Sarah", "Ariana", "Allison",
    "Gabriella", "Alice", "Madelyn", "Cora", "Ruby", "Eva", "Serenity",
    "Autumn", "Adeline", "Hailey", "Gianna", "Valentina", "Isla", "Eliana",
    "Quinn", "Nevaeh", "Ivy", "Sadie", "Piper", "Lydia", "Alexa", "Josephine",
    "Emery", "Julia", "Delilah", "Arianna", "Vivian", "Kaylee", "Sophie",
    "Brielle", "Madeline", "Peyton", "Rylee", "Clara", "Hadley", "Melanie",
    "Mackenzie", "Reagan", "Adalynn", "Liliana", "Aubrey", "Jade",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
    "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green",
    "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz",
    "Parker", "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris",
    "Morales", "Murphy", "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan",
    "Cooper", "Peterson", "Bailey", "Reed", "Kelly", "Howard", "Ramos",
    "Kim", "Cox", "Ward", "Richardson", "Watson", "Brooks", "Chavez",
    "Wood", "James", "Bennett", "Gray", "Mendoza", "Ruiz", "Hughes",
    "Price", "Alvarez", "Castillo", "Sanders", "Patel", "Myers", "Long",
    "Ross", "Foster", "Jimenez", "Powell",
]
