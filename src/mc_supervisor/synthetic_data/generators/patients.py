"""Generate synthetic patient demographic records — Women's Health (adult female)."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
from faker import Faker

from ..config import CHRONIC_CONDITIONS, INSURANCE_WEIGHTS


def generate_patients(num_patients: int = 10_000, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic patient records — all female, age 18+.

    Args:
        num_patients: Number of patient records to generate.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: patient_id, first_name, last_name,
        date_of_birth, gender, zip_code, insurance_type, chronic_conditions.
    """
    rng = np.random.default_rng(seed)
    fake = Faker()
    Faker.seed(seed)

    # --- Age distribution (adult women 18-90) ---
    ages = _sample_adult_female_ages(rng, num_patients)

    # Reference date for computing date_of_birth
    ref_date = date(2026, 3, 1)

    # --- Build arrays for each column ---
    patient_ids = [f"PAT{i + 1:06d}" for i in range(num_patients)]

    first_names = [fake.first_name_female() for _ in range(num_patients)]
    last_names = [fake.last_name() for _ in range(num_patients)]

    dobs = [ref_date - timedelta(days=int(age * 365.25)) for age in ages]

    # All female — women's health cohort
    genders = ["F"] * num_patients

    zip_codes = [fake.zipcode() for _ in range(num_patients)]

    insurance_types = _assign_insurance(rng, ages, num_patients)

    chronic_conditions = _assign_chronic_conditions(rng, ages)

    df = pd.DataFrame(
        {
            "patient_id": patient_ids,
            "first_name": first_names,
            "last_name": last_names,
            "date_of_birth": dobs,
            "gender": genders,
            "zip_code": zip_codes,
            "insurance_type": insurance_types,
            "chronic_conditions": chronic_conditions,
        }
    )
    df["date_of_birth"] = pd.to_datetime(df["date_of_birth"])
    # Derived column used by encounter generator for weighting
    df["num_chronic"] = df["chronic_conditions"].apply(
        lambda x: len(x.split("|")) if x else 0
    )
    return df


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sample_adult_female_ages(rng: np.random.Generator, n: int) -> np.ndarray:
    """Sample ages for adult women (18-90) with bimodal distribution.

    ~40% reproductive age (18-45) and ~60% perimenopause/postmenopause (45-90),
    reflecting a women's health-centric population.
    """
    reproductive_frac = 0.40
    n_reproductive = int(n * reproductive_frac)
    n_older = n - n_reproductive

    # Reproductive age: normal centred at 32, sd 7, clipped to [18, 45]
    reproductive_ages = rng.normal(loc=32, scale=7, size=n_reproductive)
    reproductive_ages = np.clip(reproductive_ages, 18, 45)

    # Perimenopause/postmenopause: normal centred at 62, sd 10, clipped to [45, 90]
    older_ages = rng.normal(loc=62, scale=10, size=n_older)
    older_ages = np.clip(older_ages, 45, 90)

    ages = np.concatenate([reproductive_ages, older_ages])
    rng.shuffle(ages)
    return ages


def _assign_insurance(rng: np.random.Generator, ages: np.ndarray, n: int) -> list[str]:
    """Assign insurance type weighted by config, with age-based adjustments.

    Patients >= 65 are strongly skewed toward Medicare.
    """
    insurance_names = list(INSURANCE_WEIGHTS.keys())
    base_probs = np.array(list(INSURANCE_WEIGHTS.values()), dtype=np.float64)

    results: list[str] = []
    for age in ages:
        probs = base_probs.copy()
        if age >= 65:
            # Boost Medicare significantly for senior patients
            probs[insurance_names.index("Medicare")] *= 3.0
        # Re-normalise
        probs /= probs.sum()
        results.append(rng.choice(insurance_names, p=probs))
    return results


def _assign_chronic_conditions(rng: np.random.Generator, ages: np.ndarray) -> list[str]:
    """Assign chronic conditions with age-dependent prevalence.

    Conditions are women's health focused (PCOS, endometriosis, menopause, etc.)
    """
    results: list[str] = []
    for age in ages:
        if age < 35:
            # Younger women: PCOS, endometriosis more prevalent
            per_condition_prob = 0.10
            conditions = [c for c in CHRONIC_CONDITIONS if rng.random() < per_condition_prob]
        elif age < 50:
            # Perimenopause age: rising chronic conditions
            per_condition_prob = 0.12 + (age - 35) * 0.003
            conditions = [c for c in CHRONIC_CONDITIONS if rng.random() < per_condition_prob]
        else:
            # Postmenopause: higher burden
            base_prob = 0.12 + (age - 50) * 0.004  # 12% at 50 -> 28% at 90
            conditions = [c for c in CHRONIC_CONDITIONS if rng.random() < base_prob]

        results.append("|".join(conditions) if conditions else "")
    return results
