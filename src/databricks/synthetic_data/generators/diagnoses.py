"""Generate synthetic diagnosis and readmission records."""

import numpy as np
import pandas as pd


# Map departments to ICD-10 categories that are most relevant.
# Departments not listed here will fall back to uniform sampling.
_DEPT_CATEGORY_RELEVANCE: dict[str, list[str]] = {
    "Emergency": ["Injury", "Signs/Symptoms", "Cardiovascular", "Respiratory", "Infectious"],
    "Cardiology": ["Cardiovascular"],
    "Orthopedics": ["Musculoskeletal", "Injury"],
    "General Surgery": ["Gastrointestinal", "Musculoskeletal", "Injury"],
    "Internal Medicine": [
        "Cardiovascular",
        "Endocrine",
        "Respiratory",
        "Gastrointestinal",
        "Signs/Symptoms",
    ],
    "Pediatrics": ["Respiratory", "Infectious", "Signs/Symptoms", "Injury"],
    "Obstetrics": ["Genitourinary", "Signs/Symptoms", "Endocrine"],
    "Neurology": ["Neurological"],
    "Oncology": ["Neoplasm"],
    "Pulmonology": ["Respiratory"],
    "Gastroenterology": ["Gastrointestinal"],
    "Nephrology": ["Genitourinary"],
    "Endocrinology": ["Endocrine"],
    "Dermatology": ["Infectious", "Signs/Symptoms"],
    "Urology": ["Genitourinary"],
    "Psychiatry": ["Mental Health"],
    "Radiology": ["Signs/Symptoms", "Neoplasm", "Musculoskeletal"],
    "Anesthesiology": ["Signs/Symptoms", "Cardiovascular"],
    "Rehabilitation": ["Musculoskeletal", "Neurological", "Injury"],
    "Intensive Care": [
        "Cardiovascular",
        "Respiratory",
        "Infectious",
        "Injury",
        "Signs/Symptoms",
    ],
}


def _build_department_weights(
    department: str, icd10_df: pd.DataFrame, rng: np.random.Generator
) -> np.ndarray:
    """Return sampling weights over ``icd10_df`` rows for *department*.

    Codes whose category is listed as relevant get a weight of 5.0; all
    other codes get a baseline weight of 1.0.  Weights are normalised to
    probabilities before being returned.
    """
    relevant_cats = _DEPT_CATEGORY_RELEVANCE.get(department, [])

    if relevant_cats:
        weights = np.where(icd10_df["category"].isin(relevant_cats), 5.0, 1.0)
    else:
        weights = np.ones(len(icd10_df), dtype=np.float64)

    return weights / weights.sum()


def generate_diagnoses(
    encounters_df: pd.DataFrame,
    icd10_df: pd.DataFrame,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate 1-3 diagnosis records per encounter.

    Args:
        encounters_df: DataFrame with at least ``encounter_id`` and
            ``department`` columns.
        icd10_df: Reference ICD-10 codes DataFrame with ``icd10_code``,
            ``description``, and ``category`` columns.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: diagnosis_id, encounter_id, icd10_code,
        description, is_primary, sequence_num.
    """
    rng = np.random.default_rng(seed)

    # Pre-compute per-department weight vectors
    departments = encounters_df["department"].unique()
    dept_weights: dict[str, np.ndarray] = {
        dept: _build_department_weights(dept, icd10_df, rng) for dept in departments
    }

    icd10_codes = icd10_df["icd10_code"].values
    icd10_descriptions = icd10_df["description"].values

    records: list[dict] = []
    dx_counter = 0

    for enc_id, dept in zip(encounters_df["encounter_id"], encounters_df["department"]):
        num_dx = rng.choice([1, 2, 3], p=[0.35, 0.40, 0.25])
        weights = dept_weights[dept]

        # Sample without replacement if possible
        n_sample = min(num_dx, len(icd10_df))
        chosen_indices = rng.choice(len(icd10_df), size=n_sample, replace=False, p=weights)

        for seq, idx in enumerate(chosen_indices, start=1):
            dx_counter += 1
            records.append(
                {
                    "diagnosis_id": f"DX{dx_counter:06d}",
                    "encounter_id": enc_id,
                    "icd10_code": icd10_codes[idx],
                    "description": icd10_descriptions[idx],
                    "is_primary": seq == 1,
                    "sequence_num": seq,
                }
            )

    return pd.DataFrame(records)


def generate_readmissions(
    encounters_df: pd.DataFrame,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate 30-day readmission records for inpatient encounters.

    Approximately 6-7 % of inpatient encounters are flagged as having a
    30-day readmission.  For each flagged encounter a matching *readmit*
    encounter is drawn from a later inpatient encounter for the same
    patient.  When no suitable readmit encounter exists the record is
    still created with a synthetic ``days_between`` value.

    Args:
        encounters_df: DataFrame with at least ``encounter_id``,
            ``patient_id``, ``encounter_type``, ``admission_date``, and
            ``discharge_date`` columns.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: readmission_id, original_encounter_id,
        readmit_encounter_id, days_between, is_30_day.
    """
    rng = np.random.default_rng(seed)

    # Restrict to inpatient encounters only
    inpatient = encounters_df[encounters_df["encounter_type"] == "Inpatient"].copy()
    inpatient = inpatient.sort_values("admission_date").reset_index(drop=True)

    # Target ~6.5 % 30-day readmission rate
    readmit_prob = 0.065
    mask = rng.random(len(inpatient)) < readmit_prob
    flagged = inpatient[mask]

    # Build a lookup: patient_id -> sorted list of (admission_date, encounter_id)
    patient_encounters: dict[str, list[tuple]] = {}
    for _, row in inpatient.iterrows():
        patient_encounters.setdefault(row["patient_id"], []).append(
            (row["admission_date"], row["encounter_id"])
        )

    records: list[dict] = []
    readmit_counter = 0

    for _, row in flagged.iterrows():
        pid = row["patient_id"]
        discharge = row["discharge_date"]
        enc_list = patient_encounters.get(pid, [])

        # Look for the next inpatient encounter within 30 days of discharge
        candidates = [
            (adm, eid)
            for adm, eid in enc_list
            if adm > discharge and (adm - discharge).days <= 30 and eid != row["encounter_id"]
        ]

        if candidates:
            # Pick the earliest qualifying readmit encounter
            candidates.sort()
            readmit_adm, readmit_eid = candidates[0]
            days_between = (readmit_adm - discharge).days
        else:
            # No actual encounter found -- synthesize a plausible readmission
            days_between = int(rng.integers(1, 31))
            readmit_eid = None

        readmit_counter += 1
        records.append(
            {
                "readmission_id": f"READM{readmit_counter:06d}",
                "original_encounter_id": row["encounter_id"],
                "readmit_encounter_id": readmit_eid,
                "days_between": days_between,
                "is_30_day": True,
            }
        )

    return pd.DataFrame(records)
