"""Monte Carlo simulation model for hospital capacity planning.

Simulates daily census and bed overflow using Poisson admissions and
log-normal length-of-stay distributions. Designed to run inside
``applyInPandas`` on Spark executors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def simulate_capacity_batch(batch_df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Simulate daily census and overflow for a batch of trials.

    For each trial the model:

    1. Draws daily new admissions from ``Poisson(daily_admit_rate)``.
    2. Assigns each admission a length-of-stay sampled from
       ``LogNormal(los_mu, los_sigma)`` (rounded to whole days, min 1).
    3. Tracks concurrent census for each forecast day and computes
       overflow as ``max(0, census - total_beds)``.

    Each row in *batch_df* represents one trial and must contain a
    ``batch_seed`` column used to initialise a per-trial PRNG for
    reproducibility.

    Parameters
    ----------
    batch_df : pd.DataFrame
        Batch frame with at least ``trial_id``, ``batch_id``, and
        ``batch_seed`` columns.
    params : dict
        Simulation parameters:
        - **total_beds** (int): Total available bed capacity.
        - **daily_admit_rate** (float): Mean daily admissions (Poisson
          lambda).
        - **los_mu** (float): Log-normal mu for length-of-stay.
        - **los_sigma** (float): Log-normal sigma for length-of-stay.
        - **forecast_days** (int): Number of days to simulate.

    Returns
    -------
    pd.DataFrame
        One row per (trial, day) with columns:
        ``trial_id``, ``batch_id``, ``day``, ``census``, ``overflow``.
    """
    total_beds: int = int(params["total_beds"])
    daily_admit_rate: float = float(params["daily_admit_rate"])
    los_mu: float = float(params["los_mu"])
    los_sigma: float = float(params["los_sigma"])
    forecast_days: int = int(params["forecast_days"])

    results: list[pd.DataFrame] = []

    for _, row in batch_df.iterrows():
        rng = np.random.default_rng(int(row["batch_seed"]))
        trial_id = row["trial_id"]
        batch_id = row["batch_id"]

        # --- Generate admissions for each day ---
        daily_admissions = rng.poisson(lam=daily_admit_rate, size=forecast_days)

        total_patients = daily_admissions.sum()

        if total_patients == 0:
            # Edge case: no admissions at all.
            trial_df = pd.DataFrame(
                {
                    "trial_id": np.full(forecast_days, trial_id),
                    "batch_id": np.full(forecast_days, batch_id),
                    "day": np.arange(1, forecast_days + 1),
                    "census": np.zeros(forecast_days, dtype=np.int64),
                    "overflow": np.zeros(forecast_days, dtype=np.int64),
                }
            )
            results.append(trial_df)
            continue

        # --- Assign LOS to each admitted patient ---
        raw_los = rng.lognormal(mean=los_mu, sigma=los_sigma, size=total_patients)
        patient_los = np.maximum(np.round(raw_los).astype(np.int64), 1)

        # Build admission-day and discharge-day arrays for each patient.
        admit_days = np.repeat(np.arange(forecast_days), daily_admissions)
        discharge_days = admit_days + patient_los  # exclusive upper bound

        # --- Compute daily census using vectorised comparison ---
        # For each day d, census = number of patients where
        # admit_day <= d < discharge_day.
        days = np.arange(forecast_days)  # shape (forecast_days,)
        # Broadcasting: (forecast_days, 1) vs (1, total_patients)
        occupied = (admit_days[np.newaxis, :] <= days[:, np.newaxis]) & (
            days[:, np.newaxis] < discharge_days[np.newaxis, :]
        )
        census = occupied.sum(axis=1)  # (forecast_days,)

        overflow = np.maximum(census - total_beds, 0)

        trial_df = pd.DataFrame(
            {
                "trial_id": np.full(forecast_days, trial_id),
                "batch_id": np.full(forecast_days, batch_id),
                "day": days + 1,  # 1-indexed
                "census": census,
                "overflow": overflow,
            }
        )
        results.append(trial_df)

    if not results:
        return pd.DataFrame(columns=["trial_id", "batch_id", "day", "census", "overflow"])

    return pd.concat(results, ignore_index=True)
