"""Generate synthetic encounter records with realistic temporal patterns."""

import numpy as np
import pandas as pd

from ..config import (
    DATE_END,
    DATE_START,
    DEPARTMENTS,
    ENCOUNTER_TYPE_WEIGHTS,
    LOS_PARAMS,
    SPECIALTIES,
)

# ---------------------------------------------------------------------------
# Specialty-to-department mapping (SPECIALTIES and DEPARTMENTS are parallel
# lists in config, so we build a dict from their positional alignment).
# ---------------------------------------------------------------------------
_SPECIALTY_TO_DEPARTMENT = dict(zip(SPECIALTIES, DEPARTMENTS))

# ---------------------------------------------------------------------------
# Seasonal multipliers (month -> base multiplier).
# Flu season Nov-Feb gets a 1.3x bump; summer Jun-Aug gets a mild 1.15x bump
# that is applied only to Emergency encounters (trauma season).
# ---------------------------------------------------------------------------
_FLU_MONTHS = {11, 12, 1, 2}
_SUMMER_MONTHS = {6, 7, 8}
_FLU_MULTIPLIER = 1.3
_SUMMER_ER_MULTIPLIER = 1.15

# Weekend ER multiplier -- Emergency encounters are more likely on weekends.
_WEEKEND_ER_MULTIPLIER = 1.25


def _build_daily_weights(
    start: pd.Timestamp,
    end: pd.Timestamp,
    encounter_type: str,
) -> np.ndarray:
    """Return an array of relative daily weights for a given encounter type.

    The weights encode:
    - Flu-season spike (Nov-Feb) for *all* encounter types.
    - Summer trauma increase (Jun-Aug) for Emergency only.
    - Weekend/weekday pattern: ER is higher on weekends, others are lower.
    """
    dates = pd.date_range(start, end, freq="D")
    months = dates.month
    weekdays = dates.weekday  # 0=Mon, 6=Sun

    weights = np.ones(len(dates), dtype=np.float64)

    # --- Seasonal flu spike (all encounter types) ---
    flu_mask = np.isin(months, list(_FLU_MONTHS))
    weights[flu_mask] *= _FLU_MULTIPLIER

    # --- Summer trauma (Emergency only) ---
    if encounter_type == "Emergency":
        summer_mask = np.isin(months, list(_SUMMER_MONTHS))
        weights[summer_mask] *= _SUMMER_ER_MULTIPLIER

    # --- Weekday / weekend pattern ---
    is_weekend = weekdays >= 5
    if encounter_type == "Emergency":
        # ER is *higher* on weekends
        weights[is_weekend] *= _WEEKEND_ER_MULTIPLIER
        # Slightly lower on weekdays to compensate
        weights[~is_weekend] *= 0.95
    else:
        # Non-ER encounters are lower on weekends (clinics mostly closed)
        weights[is_weekend] *= 0.30

    return weights


def _sample_dates(
    rng: np.random.Generator,
    n: int,
    encounter_type: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> np.ndarray:
    """Sample *n* admission dates for a given encounter type respecting
    seasonal and weekday/weekend patterns.
    """
    dates = pd.date_range(start, end, freq="D")
    weights = _build_daily_weights(start, end, encounter_type)
    probs = weights / weights.sum()
    indices = rng.choice(len(dates), size=n, p=probs)
    return dates[indices].values


def _compute_los(
    rng: np.random.Generator,
    encounter_types: np.ndarray,
) -> np.ndarray:
    """Compute integer length-of-stay (days) from log-normal distributions.

    - Outpatient: always 0 (same-day).
    - Emergency: drawn from log-normal but floored to 1 day (represents hours).
    - Others: rounded from log-normal draws.
    """
    los = np.zeros(len(encounter_types), dtype=np.int32)

    for enc_type, (mu, sigma) in LOS_PARAMS.items():
        mask = encounter_types == enc_type
        count = mask.sum()
        if count == 0:
            continue

        if enc_type == "Outpatient":
            # Same-day: LOS stays 0
            continue

        raw = rng.lognormal(mean=mu, sigma=sigma, size=count)

        if enc_type == "Emergency":
            # Hours-scale -- store as 1 day
            los[mask] = 1
        else:
            # Round to nearest integer, minimum 1
            los[mask] = np.maximum(np.round(raw).astype(np.int32), 1)

    return los


def generate_encounters(
    num_encounters: int = 120_000,
    patients_df: pd.DataFrame | None = None,
    providers_df: pd.DataFrame | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic encounter records.

    Parameters
    ----------
    num_encounters : int
        Target number of encounter rows (default 120 000).
    patients_df : pd.DataFrame or None
        Patient table; must contain ``patient_id`` and ``num_chronic``
        (integer count of chronic conditions). If *None* a minimal stub is
        created for standalone testing.
    providers_df : pd.DataFrame or None
        Provider table; must contain ``provider_id``, ``facility_id``, and
        ``specialty``. If *None* a minimal stub is created.
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    pd.DataFrame
        Encounter records with columns: encounter_id, patient_id,
        provider_id, facility_id, encounter_type, department,
        admission_date, discharge_date, length_of_stay.
    """
    rng = np.random.default_rng(seed)

    start = pd.Timestamp(DATE_START)
    end = pd.Timestamp(DATE_END)

    # ------------------------------------------------------------------
    # Fallback stubs when upstream DataFrames are not supplied.
    # ------------------------------------------------------------------
    if patients_df is None:
        patients_df = pd.DataFrame(
            {
                "patient_id": [f"PAT{i+1:06d}" for i in range(100)],
                "num_chronic": rng.integers(0, 4, size=100),
            }
        )
    if providers_df is None:
        providers_df = pd.DataFrame(
            {
                "provider_id": [f"PRV{i+1:05d}" for i in range(20)],
                "facility_id": [f"FAC{(i % 3)+1:04d}" for i in range(20)],
                "specialty": rng.choice(SPECIALTIES, size=20),
            }
        )

    # ------------------------------------------------------------------
    # 1. Assign encounter types according to configured weights.
    # ------------------------------------------------------------------
    enc_types_list = list(ENCOUNTER_TYPE_WEIGHTS.keys())
    enc_type_probs = np.array(list(ENCOUNTER_TYPE_WEIGHTS.values()), dtype=np.float64)
    enc_type_probs /= enc_type_probs.sum()  # normalise in case of rounding

    encounter_types = rng.choice(enc_types_list, size=num_encounters, p=enc_type_probs)

    # ------------------------------------------------------------------
    # 2. Sample admission dates per encounter type (respects seasonality).
    # ------------------------------------------------------------------
    admission_dates = np.empty(num_encounters, dtype="datetime64[ns]")
    for enc_type in enc_types_list:
        mask = encounter_types == enc_type
        count = mask.sum()
        if count == 0:
            continue
        admission_dates[mask] = _sample_dates(rng, count, enc_type, start, end)

    # ------------------------------------------------------------------
    # 3. Compute length-of-stay and discharge dates.
    # ------------------------------------------------------------------
    los = _compute_los(rng, encounter_types)
    discharge_dates = admission_dates + pd.to_timedelta(los, unit="D")

    # ------------------------------------------------------------------
    # 4. Sample patients -- chronic patients get more encounters.
    #    Weight = 1 + num_chronic  (a patient with 3 chronic conditions is
    #    4x more likely to appear than one with 0).
    # ------------------------------------------------------------------
    patient_ids = patients_df["patient_id"].values
    num_chronic = patients_df["num_chronic"].values.astype(np.float64)
    patient_weights = 1.0 + num_chronic
    patient_probs = patient_weights / patient_weights.sum()

    sampled_patient_idx = rng.choice(
        len(patient_ids), size=num_encounters, p=patient_probs
    )
    sampled_patients = patient_ids[sampled_patient_idx]

    # ------------------------------------------------------------------
    # 5. Sample providers and derive facility / department.
    # ------------------------------------------------------------------
    provider_ids = providers_df["provider_id"].values
    provider_facilities = providers_df["facility_id"].values
    provider_specialties = providers_df["specialty"].values

    # Build a specialty-to-department lookup for the providers we have.
    provider_departments = np.array(
        [_SPECIALTY_TO_DEPARTMENT.get(s, "Internal Medicine") for s in provider_specialties]
    )

    # For Emergency encounters, prefer Emergency Medicine providers; for
    # others, sample uniformly across all providers.
    er_provider_mask = provider_specialties == "Emergency Medicine"
    has_er_providers = er_provider_mask.sum() > 0

    sampled_provider_idx = np.empty(num_encounters, dtype=np.intp)

    er_enc_mask = encounter_types == "Emergency"
    non_er_enc_mask = ~er_enc_mask

    if has_er_providers and er_enc_mask.sum() > 0:
        # ER encounters: 80% chance of an ER provider, 20% other
        er_indices = np.where(er_provider_mask)[0]
        non_er_indices = np.where(~er_provider_mask)[0]
        n_er = er_enc_mask.sum()

        use_er_provider = rng.random(n_er) < 0.80
        er_prov_choices = rng.choice(er_indices, size=n_er)
        non_er_prov_choices = rng.choice(
            non_er_indices if len(non_er_indices) > 0 else er_indices,
            size=n_er,
        )
        sampled_provider_idx[er_enc_mask] = np.where(
            use_er_provider, er_prov_choices, non_er_prov_choices
        )
    elif er_enc_mask.sum() > 0:
        sampled_provider_idx[er_enc_mask] = rng.choice(
            len(provider_ids), size=er_enc_mask.sum()
        )

    if non_er_enc_mask.sum() > 0:
        sampled_provider_idx[non_er_enc_mask] = rng.choice(
            len(provider_ids), size=non_er_enc_mask.sum()
        )

    sampled_providers = provider_ids[sampled_provider_idx]
    sampled_facilities = provider_facilities[sampled_provider_idx]
    sampled_departments = provider_departments[sampled_provider_idx]

    # Override department for Emergency encounters to "Emergency"
    sampled_departments = np.where(
        encounter_types == "Emergency", "Emergency", sampled_departments
    )

    # ------------------------------------------------------------------
    # 6. Build the DataFrame.
    # ------------------------------------------------------------------
    encounter_ids = np.array(
        [f"ENC{i+1:06d}" for i in range(num_encounters)], dtype=object
    )

    df = pd.DataFrame(
        {
            "encounter_id": encounter_ids,
            "patient_id": sampled_patients,
            "provider_id": sampled_providers,
            "facility_id": sampled_facilities,
            "encounter_type": encounter_types,
            "department": sampled_departments,
            "admission_date": pd.to_datetime(admission_dates),
            "discharge_date": pd.to_datetime(discharge_dates),
            "length_of_stay": los,
        }
    )

    # Sort by admission date for a natural chronological ordering.
    df = df.sort_values("admission_date").reset_index(drop=True)
    # Re-assign encounter IDs so they are chronological.
    df["encounter_id"] = [f"ENC{i+1:06d}" for i in range(num_encounters)]

    return df
