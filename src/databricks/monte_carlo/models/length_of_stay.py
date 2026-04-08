"""Monte Carlo simulation model for length-of-stay analysis.

Simulates average length-of-stay and total bed-day consumption for
a patient cohort, with support for an intervention that reduces LOS
by a given percentage. Designed to run inside ``applyInPandas`` on
Spark executors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def simulate_los_batch(batch_df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Simulate LOS distributions with an optional intervention.

    For each trial the model:

    1. Draws *annual_patients* LOS values from
       ``LogNormal(los_mu, los_sigma)``.
    2. Applies a percentage reduction (``reduction_pct``) to each
       sampled LOS to model an intervention effect.
    3. Computes the average LOS and total bed-days for the cohort.

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
        - **los_mu** (float): Log-normal mu for length-of-stay.
        - **los_sigma** (float): Log-normal sigma for length-of-stay.
        - **reduction_pct** (float): Fractional reduction in LOS from
          intervention (e.g. 0.10 for a 10 % reduction). Set to 0 for
          the baseline (no intervention) scenario.
        - **annual_patients** (int): Number of patients in the annual
          cohort to simulate.

    Returns
    -------
    pd.DataFrame
        One row per trial with columns:
        ``trial_id``, ``batch_id``, ``simulated_avg_los``, ``bed_days``.
    """
    los_mu: float = float(params["los_mu"])
    los_sigma: float = float(params["los_sigma"])
    reduction_pct: float = float(params.get("reduction_pct", 0.0))
    annual_patients: int = int(params["annual_patients"])

    n_trials = len(batch_df)

    trial_ids = batch_df["trial_id"].values
    batch_ids = batch_df["batch_id"].values
    seeds = batch_df["batch_seed"].values.astype(np.int64)

    simulated_avg_los = np.empty(n_trials, dtype=np.float64)
    bed_days = np.empty(n_trials, dtype=np.float64)

    for i in range(n_trials):
        rng = np.random.default_rng(seeds[i])

        # Draw raw LOS for each patient.
        raw_los = rng.lognormal(mean=los_mu, sigma=los_sigma, size=annual_patients)

        # Apply intervention reduction.
        adjusted_los = raw_los * (1.0 - reduction_pct)

        # Floor to minimum 1 day.
        adjusted_los = np.maximum(adjusted_los, 1.0)

        simulated_avg_los[i] = adjusted_los.mean()
        bed_days[i] = adjusted_los.sum()

    return pd.DataFrame(
        {
            "trial_id": trial_ids,
            "batch_id": batch_ids,
            "simulated_avg_los": simulated_avg_los,
            "bed_days": bed_days,
        }
    )
