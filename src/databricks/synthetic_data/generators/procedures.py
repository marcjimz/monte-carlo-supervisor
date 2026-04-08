"""Generate synthetic procedure records."""

import numpy as np
import pandas as pd

# Maps encounter types to the CPT categories most likely to be ordered and
# the distribution of how many procedures an encounter generates.
_ENCOUNTER_PROCEDURE_PROFILE: dict[str, dict] = {
    "Inpatient": {
        "categories": ["E&M", "Laboratory", "Radiology", "Surgery", "Cardiology", "Anesthesia"],
        # (num_procedures, probabilities) -- inpatient encounters get more procedures
        "count_choices": [0, 1, 2, 3, 4, 5],
        "count_probs": [0.02, 0.15, 0.30, 0.28, 0.15, 0.10],
    },
    "Emergency": {
        "categories": ["E&M", "Laboratory", "Radiology"],
        "count_choices": [0, 1, 2, 3],
        "count_probs": [0.05, 0.35, 0.40, 0.20],
    },
    "Outpatient": {
        "categories": ["E&M", "Laboratory", "Radiology"],
        "count_choices": [0, 1, 2],
        "count_probs": [0.30, 0.50, 0.20],
    },
    "Observation": {
        "categories": ["E&M", "Laboratory", "Radiology"],
        "count_choices": [0, 1, 2, 3],
        "count_probs": [0.08, 0.35, 0.37, 0.20],
    },
}

# Departments that strongly favour surgical CPT codes
_SURGICAL_DEPARTMENTS = {
    "General Surgery",
    "Orthopedics",
    "Obstetrics",
    "Urology",
    "Anesthesiology",
}


def _build_cpt_weights(
    encounter_type: str,
    department: str,
    cpt_df: pd.DataFrame,
) -> np.ndarray:
    """Return normalised sampling weights over ``cpt_df`` rows.

    Codes whose category matches the encounter-type profile get a high
    weight.  Surgery-oriented departments additionally boost surgical
    codes.
    """
    profile = _ENCOUNTER_PROCEDURE_PROFILE.get(encounter_type, _ENCOUNTER_PROCEDURE_PROFILE["Outpatient"])
    relevant_cats = set(profile["categories"])

    weights = np.where(cpt_df["category"].isin(relevant_cats), 5.0, 1.0)

    # Extra boost for surgical departments
    if department in _SURGICAL_DEPARTMENTS:
        surgical_mask = cpt_df["category"].isin({"Surgery", "Anesthesia"})
        weights = np.where(surgical_mask, weights * 3.0, weights)

    return weights / weights.sum()


def generate_procedures(
    encounters_df: pd.DataFrame,
    cpt_df: pd.DataFrame,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate procedure records for encounters (~90K total).

    Args:
        encounters_df: DataFrame with at least ``encounter_id``,
            ``encounter_type``, ``department``, ``admission_date``,
            ``discharge_date``, and ``provider_id`` columns.
        cpt_df: Reference CPT codes DataFrame with ``cpt_code``,
            ``description``, and ``category`` columns.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: procedure_id, encounter_id, cpt_code,
        description, procedure_date, provider_id.
    """
    rng = np.random.default_rng(seed)

    cpt_codes = cpt_df["cpt_code"].values
    cpt_descriptions = cpt_df["description"].values

    # Pre-compute weights keyed by (encounter_type, department)
    weight_cache: dict[tuple[str, str], np.ndarray] = {}

    records: list[dict] = []
    proc_counter = 0

    for _, row in encounters_df.iterrows():
        enc_type = row["encounter_type"]
        dept = row["department"]
        enc_id = row["encounter_id"]
        admission = row["admission_date"]
        discharge = row["discharge_date"]
        provider = row["provider_id"]

        # Determine how many procedures this encounter generates
        profile = _ENCOUNTER_PROCEDURE_PROFILE.get(enc_type, _ENCOUNTER_PROCEDURE_PROFILE["Outpatient"])
        num_procs = int(
            rng.choice(profile["count_choices"], p=profile["count_probs"])
        )

        if num_procs == 0:
            continue

        # Fetch or compute CPT weights
        cache_key = (enc_type, dept)
        if cache_key not in weight_cache:
            weight_cache[cache_key] = _build_cpt_weights(enc_type, dept, cpt_df)
        weights = weight_cache[cache_key]

        n_sample = min(num_procs, len(cpt_df))
        chosen_indices = rng.choice(len(cpt_df), size=n_sample, replace=False, p=weights)

        for idx in chosen_indices:
            proc_counter += 1

            # Procedure date: on or after admission, up to discharge
            if admission == discharge or pd.isna(discharge):
                proc_date = admission
            else:
                span_days = (discharge - admission).days
                offset = int(rng.integers(0, span_days + 1))
                proc_date = admission + pd.Timedelta(days=offset)

            records.append(
                {
                    "procedure_id": f"PROC{proc_counter:06d}",
                    "encounter_id": enc_id,
                    "cpt_code": cpt_codes[idx],
                    "description": cpt_descriptions[idx],
                    "procedure_date": proc_date,
                    "provider_id": provider,
                }
            )

    return pd.DataFrame(records)
