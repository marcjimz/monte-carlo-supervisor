"""Monte Carlo simulation model for patient volume forecasting.

Simulates daily patient volumes using Poisson arrivals modulated by
seasonal factors. Designed to run inside ``applyInPandas`` on Spark
executors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def simulate_patient_volume_batch(batch_df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Simulate patient volume for a batch of trials.

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
        - **department** (str): Department name (metadata only).
        - **encounter_type** (str): Encounter type (metadata only).
        - **forecast_days** (int): Number of days to forecast.
        - **mean_daily** (float): Baseline mean daily patient volume
          (lambda for the Poisson distribution).
        - **seasonal_factors** (list[float]): Length-12 array of
          monthly multipliers applied to *mean_daily*. Index 0 is
          January.

    Returns
    -------
    pd.DataFrame
        One row per (trial, day) with columns:
        ``trial_id``, ``batch_id``, ``day``, ``simulated_volume``.
    """
    forecast_days: int = int(params["forecast_days"])
    mean_daily: float = float(params["mean_daily"])

    # Seasonal factors — default to flat (1.0) when not supplied.
    seasonal_factors = np.asarray(
        params.get("seasonal_factors", np.ones(12)),
        dtype=np.float64,
    )
    if seasonal_factors.shape[0] != 12:
        raise ValueError(f"seasonal_factors must have length 12, got {seasonal_factors.shape[0]}")

    # Pre-compute the monthly factor for each forecast day.
    # Assume forecast starts from month 1 (January); callers can rotate
    # the seasonal_factors array to align with the actual start month.
    day_indices = np.arange(forecast_days)
    month_for_day = (day_indices // 30) % 12  # approximate month index
    lambdas = mean_daily * seasonal_factors[month_for_day]  # (forecast_days,)

    results: list[pd.DataFrame] = []

    for _, row in batch_df.iterrows():
        rng = np.random.default_rng(int(row["batch_seed"]))
        trial_id = row["trial_id"]
        batch_id = row["batch_id"]

        # Vectorised Poisson draw for all forecast days at once.
        volumes = rng.poisson(lam=lambdas)

        trial_df = pd.DataFrame(
            {
                "trial_id": np.full(forecast_days, trial_id),
                "batch_id": np.full(forecast_days, batch_id),
                "day": day_indices + 1,  # 1-indexed days
                "simulated_volume": volumes,
            }
        )
        results.append(trial_df)

    if not results:
        return pd.DataFrame(columns=["trial_id", "batch_id", "day", "simulated_volume"])

    return pd.concat(results, ignore_index=True)
