"""Monte Carlo simulation model for revenue projection.

Simulates monthly revenue paths by drawing per-encounter revenue from
log-normal distributions parameterised per payer type. Designed to run
inside ``applyInPandas`` on Spark executors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def simulate_revenue_batch(batch_df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Simulate monthly revenue paths for a batch of trials.

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
        - **months_ahead** (int): Number of months to forecast.
        - **volume_change_pct** (float): Expected volume change per
          month as a fraction (e.g. 0.02 for 2 % growth). Applied
          cumulatively.
        - **payer_params** (dict[str, dict]): Per-payer log-normal
          parameters. Each value is ``{"mu": float, "sigma": float}``
          representing the log-normal mean and std-dev of per-encounter
          revenue for that payer.
        - **payer_mix** (dict[str, float]): Probability that any given
          encounter belongs to each payer. Values should sum to 1.
        - **base_monthly_volume** (int): Baseline number of encounters
          per month before volume change is applied.

    Returns
    -------
    pd.DataFrame
        One row per (trial, month) with columns:
        ``trial_id``, ``batch_id``, ``month``, ``simulated_revenue``.
    """
    months_ahead: int = int(params["months_ahead"])
    volume_change_pct: float = float(params.get("volume_change_pct", 0.0))
    base_monthly_volume: int = int(params.get("base_monthly_volume", 1000))

    payer_params: dict[str, dict] = params["payer_params"]
    payer_mix: dict[str, float] = params["payer_mix"]

    # Ordered lists so iteration is deterministic.
    payer_names = sorted(payer_params.keys())
    payer_probs = np.array([payer_mix[p] for p in payer_names], dtype=np.float64)
    payer_probs /= payer_probs.sum()  # normalise

    payer_mus = np.array([payer_params[p]["mu"] for p in payer_names], dtype=np.float64)
    payer_sigmas = np.array([payer_params[p]["sigma"] for p in payer_names], dtype=np.float64)

    results: list[pd.DataFrame] = []

    for _, row in batch_df.iterrows():
        rng = np.random.default_rng(int(row["batch_seed"]))
        trial_id = row["trial_id"]
        batch_id = row["batch_id"]

        monthly_revenues = np.empty(months_ahead, dtype=np.float64)

        for month_idx in range(months_ahead):
            # Apply cumulative volume change.
            adjusted_volume = int(
                round(base_monthly_volume * (1.0 + volume_change_pct) ** (month_idx + 1))
            )
            adjusted_volume = max(adjusted_volume, 0)

            if adjusted_volume == 0:
                monthly_revenues[month_idx] = 0.0
                continue

            # Assign each encounter to a payer.
            encounter_payers = rng.choice(len(payer_names), size=adjusted_volume, p=payer_probs)

            # Vectorised log-normal draw: sample all encounters, then
            # look up mu/sigma per encounter based on payer assignment.
            mus = payer_mus[encounter_payers]
            sigmas = payer_sigmas[encounter_payers]

            per_encounter_revenue = rng.lognormal(mean=mus, sigma=sigmas)

            monthly_revenues[month_idx] = per_encounter_revenue.sum()

        trial_df = pd.DataFrame(
            {
                "trial_id": np.full(months_ahead, trial_id),
                "batch_id": np.full(months_ahead, batch_id),
                "month": np.arange(1, months_ahead + 1),
                "simulated_revenue": monthly_revenues,
            }
        )
        results.append(trial_df)

    if not results:
        return pd.DataFrame(columns=["trial_id", "batch_id", "month", "simulated_revenue"])

    return pd.concat(results, ignore_index=True)
