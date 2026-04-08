"""Monte Carlo simulation model for readmission risk.

Uses a Beta-Bernoulli conjugate model to simulate readmission rates
and counts for patient cohorts. Designed to run inside
``applyInPandas`` on Spark executors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def simulate_readmission_batch(batch_df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Simulate readmission rates and counts using Beta-Bernoulli.

    For each trial the model:

    1. Draws a readmission probability *p* from ``Beta(alpha, beta_param)``.
    2. Simulates *cohort_size* Bernoulli trials at rate *p* and counts
       the total readmissions.

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
        - **alpha** (float): Alpha parameter of the Beta prior
          (conceptually: prior successes / observed readmissions).
        - **beta_param** (float): Beta parameter of the Beta prior
          (conceptually: prior non-readmissions).
        - **cohort_size** (int): Number of patients in the simulated
          cohort per trial.

    Returns
    -------
    pd.DataFrame
        One row per trial with columns:
        ``trial_id``, ``batch_id``, ``simulated_rate``,
        ``simulated_readmissions``.
    """
    alpha: float = float(params["alpha"])
    beta_param: float = float(params["beta_param"])
    cohort_size: int = int(params["cohort_size"])

    n_trials = len(batch_df)

    trial_ids = batch_df["trial_id"].values
    batch_ids = batch_df["batch_id"].values
    seeds = batch_df["batch_seed"].values.astype(np.int64)

    simulated_rates = np.empty(n_trials, dtype=np.float64)
    simulated_readmissions = np.empty(n_trials, dtype=np.int64)

    for i in range(n_trials):
        rng = np.random.default_rng(seeds[i])

        # Step 1: draw readmission probability from the Beta prior.
        p = rng.beta(alpha, beta_param)

        # Step 2: simulate Bernoulli outcomes for the cohort.
        readmitted = rng.binomial(n=1, p=p, size=cohort_size)
        total_readmissions = readmitted.sum()

        simulated_rates[i] = p
        simulated_readmissions[i] = total_readmissions

    return pd.DataFrame(
        {
            "trial_id": trial_ids,
            "batch_id": batch_ids,
            "simulated_rate": simulated_rates,
            "simulated_readmissions": simulated_readmissions,
        }
    )
