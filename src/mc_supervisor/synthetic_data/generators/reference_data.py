"""Generate static reference/lookup tables — Women's Health focus."""

import pandas as pd


def generate_icd10_codes() -> pd.DataFrame:
    """Generate ICD-10 codes focused on women's health conditions."""
    codes = [
        # Women's Health
        ("N95.1", "Menopausal and female climacteric states", "Women's Health"),
        ("N95.0", "Postmenopausal bleeding", "Women's Health"),
        ("R10.2", "Pelvic and perineal pain", "Women's Health"),
        ("G89.29", "Other chronic pain", "Women's Health"),
        ("G89.4", "Chronic pain syndrome", "Women's Health"),
        ("N94.1", "Dyspareunia", "Women's Health"),
        ("N80.0", "Endometriosis of uterus", "Women's Health"),
        ("D25.9", "Leiomyoma of uterus, unspecified", "Women's Health"),
        ("N92.0", "Excessive and frequent menstruation with regular cycle", "Women's Health"),
        ("N92.1", "Excessive and frequent menstruation with irregular cycle", "Women's Health"),
        ("N93.9", "Abnormal uterine and vaginal bleeding, unspecified", "Women's Health"),
        ("N81.2", "Incomplete uterovaginal prolapse", "Women's Health"),
        ("N76.0", "Acute vaginitis", "Women's Health"),
        ("N73.0", "Acute parametritis and pelvic cellulitis", "Women's Health"),
        ("E28.2", "Polycystic ovarian syndrome", "Women's Health"),
        # Genitourinary
        ("N39.0", "Urinary tract infection, site not specified", "Genitourinary"),
        ("N18.3", "Chronic kidney disease, stage 3", "Genitourinary"),
        ("N30.00", "Acute cystitis without hematuria", "Genitourinary"),
        ("N75.1", "Abscess of Bartholin gland", "Genitourinary"),
        # Cardiovascular (comorbidity)
        ("I10", "Essential hypertension", "Cardiovascular"),
        ("I25.10", "Atherosclerotic heart disease", "Cardiovascular"),
        ("I48.91", "Atrial fibrillation, unspecified", "Cardiovascular"),
        ("I50.9", "Heart failure, unspecified", "Cardiovascular"),
        # Endocrine (comorbidity)
        ("E11.9", "Type 2 diabetes without complications", "Endocrine"),
        ("E11.65", "Type 2 diabetes with hyperglycemia", "Endocrine"),
        ("E78.5", "Hyperlipidemia, unspecified", "Endocrine"),
        ("E66.01", "Morbid obesity due to excess calories", "Endocrine"),
        ("E03.9", "Hypothyroidism, unspecified", "Endocrine"),
        # Mental Health (comorbidity)
        ("F32.1", "Major depressive disorder, single episode, moderate", "Mental Health"),
        ("F41.1", "Generalized anxiety disorder", "Mental Health"),
        ("F32.9", "Major depressive disorder, single episode, unspecified", "Mental Health"),
        ("F43.10", "Post-traumatic stress disorder, unspecified", "Mental Health"),
        # Signs/Symptoms
        ("R06.00", "Dyspnea, unspecified", "Signs/Symptoms"),
        ("R07.9", "Chest pain, unspecified", "Signs/Symptoms"),
        ("R50.9", "Fever, unspecified", "Signs/Symptoms"),
        ("R11.2", "Nausea with vomiting, unspecified", "Signs/Symptoms"),
        ("R10.9", "Unspecified abdominal pain", "Signs/Symptoms"),
        # Gastrointestinal
        ("K21.0", "GERD with esophagitis", "Gastrointestinal"),
        ("K80.20", "Calculus of gallbladder without cholecystitis", "Gastrointestinal"),
        ("K57.30", "Diverticulosis of large intestine", "Gastrointestinal"),
        # Infectious
        ("A41.9", "Sepsis, unspecified organism", "Infectious"),
        ("B34.9", "Viral infection, unspecified", "Infectious"),
    ]
    return pd.DataFrame(codes, columns=["icd10_code", "description", "category"])


def generate_cpt_codes() -> pd.DataFrame:
    """Generate CPT codes focused on women's health procedures."""
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
        # Gynecology Surgery
        ("58558", "Hysteroscopy with biopsy", "Surgery", 800, 2500),
        ("58571", "Laparoscopic hysterectomy", "Surgery", 2500, 6000),
        ("57421", "Colposcopy with biopsy", "Surgery", 300, 800),
        ("58661", "Laparoscopic removal of adnexal structures", "Surgery", 1500, 4000),
        ("58120", "Dilation and curettage", "Surgery", 400, 1200),
        ("57460", "Colposcopy with LEEP", "Surgery", 500, 1500),
        ("47562", "Laparoscopic cholecystectomy", "Surgery", 800, 2000),
        # Radiology
        ("76830", "Transvaginal ultrasound", "Radiology", 150, 400),
        ("76856", "Pelvic ultrasound", "Radiology", 100, 300),
        ("77065", "Diagnostic mammography", "Radiology", 100, 250),
        ("74177", "CT abdomen and pelvis with contrast", "Radiology", 200, 600),
        ("72197", "MRI pelvis with and without contrast", "Radiology", 300, 800),
        # Laboratory
        ("80053", "Comprehensive metabolic panel", "Laboratory", 15, 50),
        ("85025", "Complete blood count (CBC)", "Laboratory", 10, 35),
        ("84443", "Thyroid stimulating hormone (TSH)", "Laboratory", 20, 60),
        ("83036", "Hemoglobin A1c", "Laboratory", 15, 50),
        ("80061", "Lipid panel", "Laboratory", 15, 50),
        ("87624", "HPV high-risk detection", "Laboratory", 30, 80),
        ("88175", "Pap smear, ThinPrep", "Laboratory", 25, 70),
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
