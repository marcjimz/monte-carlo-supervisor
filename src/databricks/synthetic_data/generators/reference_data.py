"""Generate static reference/lookup tables."""

import pandas as pd


def generate_icd10_codes() -> pd.DataFrame:
    """Generate common ICD-10 diagnosis codes."""
    codes = [
        # Cardiovascular
        ("I10", "Essential hypertension", "Cardiovascular"),
        ("I25.10", "Atherosclerotic heart disease", "Cardiovascular"),
        ("I48.91", "Atrial fibrillation, unspecified", "Cardiovascular"),
        ("I50.9", "Heart failure, unspecified", "Cardiovascular"),
        ("I50.22", "Chronic systolic heart failure", "Cardiovascular"),
        ("I50.32", "Chronic diastolic heart failure", "Cardiovascular"),
        ("I21.9", "Acute myocardial infarction, unspecified", "Cardiovascular"),
        ("I63.9", "Cerebral infarction, unspecified", "Cardiovascular"),
        ("I70.0", "Atherosclerosis of aorta", "Cardiovascular"),
        # Respiratory
        ("J44.1", "COPD with acute exacerbation", "Respiratory"),
        ("J44.0", "COPD with acute lower respiratory infection", "Respiratory"),
        ("J45.20", "Mild intermittent asthma, uncomplicated", "Respiratory"),
        ("J45.40", "Moderate persistent asthma, uncomplicated", "Respiratory"),
        ("J18.9", "Pneumonia, unspecified organism", "Respiratory"),
        ("J96.00", "Acute respiratory failure", "Respiratory"),
        ("J06.9", "Acute upper respiratory infection", "Respiratory"),
        # Endocrine/Metabolic
        ("E11.9", "Type 2 diabetes without complications", "Endocrine"),
        ("E11.65", "Type 2 diabetes with hyperglycemia", "Endocrine"),
        ("E11.22", "Type 2 diabetes with diabetic CKD", "Endocrine"),
        ("E78.5", "Hyperlipidemia, unspecified", "Endocrine"),
        ("E66.01", "Morbid obesity due to excess calories", "Endocrine"),
        ("E03.9", "Hypothyroidism, unspecified", "Endocrine"),
        # Musculoskeletal
        ("M54.5", "Low back pain", "Musculoskeletal"),
        ("M17.11", "Primary osteoarthritis, right knee", "Musculoskeletal"),
        ("M79.3", "Panniculitis, unspecified", "Musculoskeletal"),
        ("S72.001A", "Fracture of unspecified part of neck of right femur", "Musculoskeletal"),
        ("M16.11", "Primary osteoarthritis, right hip", "Musculoskeletal"),
        # Gastrointestinal
        ("K21.0", "GERD with esophagitis", "Gastrointestinal"),
        ("K80.20", "Calculus of gallbladder without cholecystitis", "Gastrointestinal"),
        ("K57.30", "Diverticulosis of large intestine", "Gastrointestinal"),
        ("K92.1", "Melena", "Gastrointestinal"),
        ("K35.80", "Unspecified acute appendicitis", "Gastrointestinal"),
        # Genitourinary
        ("N18.3", "Chronic kidney disease, stage 3", "Genitourinary"),
        ("N18.4", "Chronic kidney disease, stage 4", "Genitourinary"),
        ("N39.0", "Urinary tract infection, site not specified", "Genitourinary"),
        ("N40.0", "Benign prostatic hyperplasia without obstruction", "Genitourinary"),
        # Mental/Behavioral
        ("F32.1", "Major depressive disorder, single episode, moderate", "Mental Health"),
        ("F41.1", "Generalized anxiety disorder", "Mental Health"),
        ("F10.20", "Alcohol dependence, uncomplicated", "Mental Health"),
        ("F17.210", "Nicotine dependence, cigarettes, uncomplicated", "Mental Health"),
        # Neoplasms
        ("C34.90", "Malignant neoplasm of unspecified part of lung", "Neoplasm"),
        ("C50.919", "Malignant neoplasm of unspecified site of breast", "Neoplasm"),
        ("C18.9", "Malignant neoplasm of colon, unspecified", "Neoplasm"),
        ("C61", "Malignant neoplasm of prostate", "Neoplasm"),
        # Neurological
        ("G20", "Parkinson's disease", "Neurological"),
        ("G30.9", "Alzheimer's disease, unspecified", "Neurological"),
        ("G40.909", "Epilepsy, unspecified, not intractable", "Neurological"),
        ("G43.909", "Migraine, unspecified, not intractable", "Neurological"),
        # Infectious
        ("A41.9", "Sepsis, unspecified organism", "Infectious"),
        ("B34.9", "Viral infection, unspecified", "Infectious"),
        ("U07.1", "COVID-19", "Infectious"),
        # Injuries
        ("S06.0X0A", "Concussion without loss of consciousness", "Injury"),
        ("S52.501A", "Unspecified fracture of lower end of radius", "Injury"),
        ("T81.4XXA", "Infection following a procedure", "Injury"),
        # Signs/Symptoms
        ("R06.00", "Dyspnea, unspecified", "Signs/Symptoms"),
        ("R07.9", "Chest pain, unspecified", "Signs/Symptoms"),
        ("R50.9", "Fever, unspecified", "Signs/Symptoms"),
        ("R11.2", "Nausea with vomiting, unspecified", "Signs/Symptoms"),
        ("R10.9", "Unspecified abdominal pain", "Signs/Symptoms"),
    ]
    return pd.DataFrame(codes, columns=["icd10_code", "description", "category"])


def generate_cpt_codes() -> pd.DataFrame:
    """Generate common CPT procedure codes."""
    codes = [
        # Evaluation & Management
        ("99213", "Office visit, established patient, low complexity", "E&M", 75, 150),
        ("99214", "Office visit, established patient, moderate complexity", "E&M", 110, 200),
        ("99215", "Office visit, established patient, high complexity", "E&M", 150, 275),
        ("99281", "Emergency department visit, minor", "E&M", 50, 150),
        ("99283", "Emergency department visit, moderate", "E&M", 150, 400),
        ("99285", "Emergency department visit, high severity", "E&M", 300, 800),
        ("99221", "Initial hospital care, low complexity", "E&M", 150, 300),
        ("99223", "Initial hospital care, high complexity", "E&M", 250, 500),
        # Surgery
        ("27447", "Total knee replacement", "Surgery", 1500, 3500),
        ("27130", "Total hip replacement", "Surgery", 1500, 3500),
        ("47562", "Laparoscopic cholecystectomy", "Surgery", 800, 2000),
        ("44970", "Laparoscopic appendectomy", "Surgery", 700, 1800),
        ("33533", "CABG, single arterial graft", "Surgery", 3000, 7000),
        ("49505", "Inguinal hernia repair", "Surgery", 500, 1500),
        # Radiology
        ("71046", "Chest X-ray, 2 views", "Radiology", 30, 100),
        ("74177", "CT abdomen and pelvis with contrast", "Radiology", 200, 600),
        ("70553", "MRI brain with and without contrast", "Radiology", 300, 800),
        ("76856", "Pelvic ultrasound", "Radiology", 100, 300),
        ("77065", "Diagnostic mammography", "Radiology", 100, 250),
        # Cardiology
        ("93000", "Electrocardiogram (ECG), complete", "Cardiology", 25, 75),
        ("93306", "Transthoracic echocardiography", "Cardiology", 200, 500),
        ("93458", "Left heart catheterization", "Cardiology", 500, 1500),
        ("92928", "Percutaneous coronary stent placement", "Cardiology", 2000, 5000),
        # Laboratory
        ("80053", "Comprehensive metabolic panel", "Laboratory", 15, 50),
        ("85025", "Complete blood count (CBC)", "Laboratory", 10, 35),
        ("84443", "Thyroid stimulating hormone (TSH)", "Laboratory", 20, 60),
        ("83036", "Hemoglobin A1c", "Laboratory", 15, 50),
        ("80061", "Lipid panel", "Laboratory", 15, 50),
        # Anesthesia
        ("00140", "Anesthesia for procedures on eye", "Anesthesia", 200, 600),
        ("00400", "Anesthesia for procedures on integumentary system", "Anesthesia", 200, 500),
        ("01402", "Anesthesia for total knee replacement", "Anesthesia", 400, 1000),
    ]
    return pd.DataFrame(codes, columns=["cpt_code", "description", "category", "fee_low", "fee_high"])


def generate_payers() -> pd.DataFrame:
    """Generate insurance payer reference table."""
    payers = [
        ("PAY001", "Medicare", "Government", 0.78),
        ("PAY002", "Medicaid", "Government", 0.65),
        ("PAY003", "Commercial - Blue Cross", "Commercial", 0.88),
        ("PAY004", "Commercial - Aetna", "Commercial", 0.85),
        ("PAY005", "Commercial - UnitedHealth", "Commercial", 0.87),
        ("PAY006", "Commercial - Cigna", "Commercial", 0.86),
        ("PAY007", "Self-Pay", "Self-Pay", 0.40),
        ("PAY008", "Other", "Other", 0.75),
    ]
    return pd.DataFrame(payers, columns=["payer_id", "payer_name", "payer_type", "avg_reimbursement_rate"])


def generate_departments() -> pd.DataFrame:
    """Generate hospital department reference table."""
    from ..config import DEPARTMENTS
    rows = [(f"DEPT{i+1:03d}", name) for i, name in enumerate(DEPARTMENTS)]
    return pd.DataFrame(rows, columns=["department_id", "department_name"])
