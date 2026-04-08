"""Generate synthetic patient demographic records."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
from faker import Faker

from ..config import CHRONIC_CONDITIONS, INSURANCE_WEIGHTS


def generate_patients(num_patients: int = 25_000, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic patient records with realistic demographics.

    Produces patient records with a bimodal age distribution (pediatric 0-18
    and elderly 55-90 peaks) and age-correlated chronic conditions.

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

    # --- Age distribution (bimodal) ---
    ages = _sample_bimodal_ages(rng, num_patients)

    # Reference date for computing date_of_birth
    ref_date = date(2024, 6, 1)

    # --- Build arrays for each column ---
    patient_ids = [f"PAT{i + 1:06d}" for i in range(num_patients)]

    first_names = [fake.first_name() for _ in range(num_patients)]
    last_names = [fake.last_name() for _ in range(num_patients)]

    dobs = [ref_date - timedelta(days=int(age * 365.25)) for age in ages]

    genders = rng.choice(["M", "F", "Other"], size=num_patients, p=[0.48, 0.48, 0.04]).tolist()

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


def _sample_bimodal_ages(rng: np.random.Generator, n: int) -> np.ndarray:
    """Sample ages from a bimodal distribution with pediatric and elderly peaks.

    ~30 % of the population falls into the pediatric peak (0-18) and ~70 %
    into the elderly peak (55-90), reflecting a hospital-centric population.
    """
    pediatric_frac = 0.30
    n_pediatric = int(n * pediatric_frac)
    n_elderly = n - n_pediatric

    # Pediatric: truncated normal centred at 8, sd 5, clipped to [0, 18]
    pediatric_ages = rng.normal(loc=8, scale=5, size=n_pediatric)
    pediatric_ages = np.clip(pediatric_ages, 0, 18)

    # Elderly: truncated normal centred at 72, sd 12, clipped to [55, 90]
    elderly_ages = rng.normal(loc=72, scale=12, size=n_elderly)
    elderly_ages = np.clip(elderly_ages, 55, 90)

    ages = np.concatenate([pediatric_ages, elderly_ages])
    rng.shuffle(ages)
    return ages


def _assign_insurance(rng: np.random.Generator, ages: np.ndarray, n: int) -> list[str]:
    """Assign insurance type weighted by config, with age-based adjustments.

    Patients >= 65 are strongly skewed toward Medicare; pediatric patients
    are more likely to be on Medicaid.
    """
    insurance_names = list(INSURANCE_WEIGHTS.keys())
    base_probs = np.array(list(INSURANCE_WEIGHTS.values()), dtype=np.float64)

    results: list[str] = []
    for age in ages:
        probs = base_probs.copy()
        if age >= 65:
            # Boost Medicare significantly for senior patients
            probs[insurance_names.index("Medicare")] *= 3.0
        elif age < 18:
            # Boost Medicaid for pediatric patients
            probs[insurance_names.index("Medicaid")] *= 3.0
        # Re-normalise
        probs /= probs.sum()
        results.append(rng.choice(insurance_names, p=probs))
    return results


def _assign_chronic_conditions(rng: np.random.Generator, ages: np.ndarray) -> list[str]:
    """Assign chronic conditions with age-dependent prevalence.

    Elderly patients (>= 55) have a higher probability per condition and are
    more likely to accumulate multiple comorbidities.  Pediatric patients
    mostly have none or one condition (e.g., asthma).
    """
    results: list[str] = []
    for age in ages:
        if age < 18:
            # Pediatric: ~15 % chance of one condition, almost always asthma
            if rng.random() < 0.15:
                conditions = [rng.choice(["Asthma", "Obesity", "Depression"])]
            else:
                conditions = []
        elif age < 55:
            # Working-age gap (shouldn't happen often given bimodal sampling,
            # but handle gracefully): low burden
            per_condition_prob = 0.08
            conditions = [c for c in CHRONIC_CONDITIONS if rng.random() < per_condition_prob]
        else:
            # Elderly: probability increases with age
            base_prob = 0.10 + (age - 55) * 0.005  # 10 % at 55 -> 27.5 % at 90
            conditions = [c for c in CHRONIC_CONDITIONS if rng.random() < base_prob]

        results.append("|".join(conditions) if conditions else "")
    return results
