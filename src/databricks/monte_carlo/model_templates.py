"""Model template functions for Monte Carlo simulations.

Each template implements a reusable statistical model pattern. The config.yaml
specifies which template to use for each simulation type.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

_TEMPLATE_REGISTRY: dict[str, Callable] = {}


def register_template(name: str):
    """Decorator that registers a model template function."""

    def _wrap(fn: Callable):
        _TEMPLATE_REGISTRY[name] = fn
        return fn

    return _wrap


def get_template(name: str) -> Callable:
    """Return the template function for the given name."""
    if name not in _TEMPLATE_REGISTRY:
        available = ", ".join(sorted(_TEMPLATE_REGISTRY.keys()))
        raise ValueError(f"Unknown model template '{name}'. Available: {available}")
    return _TEMPLATE_REGISTRY[name]


def get_available_templates() -> list[str]:
    """Return sorted list of registered template names."""
    return sorted(_TEMPLATE_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Template implementations
# ---------------------------------------------------------------------------


@register_template("normal_timeseries")
def _simulate_patient_volume(pdf: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Simulate monthly patient encounter volume.

    Parameters (in *params*):
        monthly_mean       - average encounters per month (default 10000)
        monthly_std        - std-dev of encounters per month (default 1500)
        growth_rate        - year-over-year growth rate (default 0.03)
        seasonality_amp    - amplitude of seasonal sine wave (default 0.12)
        num_months         - forecast horizon in months (default 12)
        trials_per_batch   - number of trials in this batch (default 200)
    """
    batch_id = int(pdf["id"].iloc[0])
    seed = int(pdf["batch_seed"].iloc[0])
    rng = np.random.default_rng(seed)

    monthly_mean = params.get("monthly_mean", 10000)
    monthly_std = params.get("monthly_std", 1500)
    growth_rate = params.get("growth_rate", 0.03)
    seasonality_amp = params.get("seasonality_amp", 0.12)
    num_months = params.get("num_months", 12)
    trials_per_batch = params.get("trials_per_batch", 200)

    rows: list[dict] = []
    for trial in range(trials_per_batch):
        for m in range(num_months):
            growth_factor = 1.0 + growth_rate * (m / 12.0)
            seasonal_factor = 1.0 + seasonality_amp * np.sin(2 * np.pi * (m - 1) / 12.0)
            mean_adj = monthly_mean * growth_factor * seasonal_factor
            value = rng.normal(mean_adj, monthly_std)
            rows.append(
                {
                    "batch_id": batch_id,
                    "trial_id": batch_id * trials_per_batch + trial,
                    "month": f"M{m + 1:02d}",
                    "simulated_encounters": max(0.0, value),
                }
            )
    return pd.DataFrame(rows)


@register_template("revenue_projection")
def _simulate_revenue(pdf: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Simulate monthly revenue and charges.

    Parameters (in *params*):
        avg_monthly_revenue   - baseline monthly revenue (default 12_000_000)
        revenue_std           - std-dev (default 2_000_000)
        avg_charge_to_rev     - charge-to-revenue ratio (default 1.35)
        denial_rate           - claim denial rate (default 0.08)
        num_months            - forecast horizon (default 12)
        trials_per_batch      - trials in this batch (default 200)
    """
    batch_id = int(pdf["id"].iloc[0])
    seed = int(pdf["batch_seed"].iloc[0])
    rng = np.random.default_rng(seed)

    avg_rev = params.get("avg_monthly_revenue", 12_000_000)
    rev_std = params.get("revenue_std", 2_000_000)
    charge_ratio = params.get("avg_charge_to_rev", 1.35)
    denial_rate = params.get("denial_rate", 0.08)
    num_months = params.get("num_months", 12)
    trials_per_batch = params.get("trials_per_batch", 200)

    rows: list[dict] = []
    for trial in range(trials_per_batch):
        for m in range(num_months):
            gross_charges = rng.normal(avg_rev * charge_ratio, rev_std * charge_ratio)
            gross_charges = max(0.0, gross_charges)
            denied_fraction = rng.beta(2, (2 / denial_rate) - 2) if denial_rate > 0 else 0.0
            net_revenue = gross_charges * (1.0 - denied_fraction) / charge_ratio
            rows.append(
                {
                    "batch_id": batch_id,
                    "trial_id": batch_id * trials_per_batch + trial,
                    "month": f"M{m + 1:02d}",
                    "simulated_revenue": max(0.0, net_revenue),
                    "simulated_charges": gross_charges,
                }
            )
    return pd.DataFrame(rows)


@register_template("grouped_lognormal_mean")
def _simulate_length_of_stay(pdf: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Simulate average length-of-stay by department.

    Parameters (in *params*):
        departments        - list of department names (default: common set)
        los_baseline       - dict of dept -> (mu, sigma) log-normal params
        trials_per_batch   - trials per batch (default 200)
        patients_per_trial - patients sampled per department per trial (default 500)
    """
    batch_id = int(pdf["id"].iloc[0])
    seed = int(pdf["batch_seed"].iloc[0])
    rng = np.random.default_rng(seed)

    default_departments = [
        "Emergency", "Cardiology", "Orthopedics", "General Surgery",
        "Internal Medicine", "Pediatrics", "Oncology", "Neurology",
        "Intensive Care", "Pulmonology",
    ]
    departments = params.get("departments", default_departments)
    los_baseline = params.get(
        "los_baseline",
        {
            "Emergency": (0.0, 0.3),
            "Cardiology": (1.4, 0.6),
            "Orthopedics": (1.5, 0.7),
            "General Surgery": (1.2, 0.7),
            "Internal Medicine": (1.1, 0.6),
            "Pediatrics": (0.8, 0.5),
            "Oncology": (1.6, 0.8),
            "Neurology": (1.3, 0.7),
            "Intensive Care": (1.8, 0.9),
            "Pulmonology": (1.3, 0.6),
        },
    )
    trials_per_batch = params.get("trials_per_batch", 200)
    patients_per_trial = params.get("patients_per_trial", 500)

    rows: list[dict] = []
    for trial in range(trials_per_batch):
        for dept in departments:
            mu, sigma = los_baseline.get(dept, (1.0, 0.5))
            samples = rng.lognormal(mu, sigma, size=patients_per_trial)
            avg_los = float(np.mean(samples))
            rows.append(
                {
                    "batch_id": batch_id,
                    "trial_id": batch_id * trials_per_batch + trial,
                    "department": dept,
                    "simulated_avg_los": avg_los,
                }
            )
    return pd.DataFrame(rows)


@register_template("grouped_binomial_rate")
def _simulate_readmission_rate(pdf: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Simulate 30-day readmission rates by department.

    Parameters (in *params*):
        departments          - list of department names
        base_readmission_rate - dict of dept -> base rate (default ~0.12)
        trials_per_batch     - trials per batch (default 200)
        discharges_per_trial - discharges sampled per department per trial (default 300)
    """
    batch_id = int(pdf["id"].iloc[0])
    seed = int(pdf["batch_seed"].iloc[0])
    rng = np.random.default_rng(seed)

    default_departments = [
        "Emergency", "Cardiology", "Orthopedics", "General Surgery",
        "Internal Medicine", "Pediatrics", "Oncology", "Neurology",
        "Intensive Care", "Pulmonology",
    ]
    departments = params.get("departments", default_departments)
    base_rates = params.get(
        "base_readmission_rate",
        {
            "Emergency": 0.15,
            "Cardiology": 0.18,
            "Orthopedics": 0.08,
            "General Surgery": 0.12,
            "Internal Medicine": 0.14,
            "Pediatrics": 0.06,
            "Oncology": 0.20,
            "Neurology": 0.16,
            "Intensive Care": 0.22,
            "Pulmonology": 0.17,
        },
    )
    trials_per_batch = params.get("trials_per_batch", 200)
    discharges_per_trial = params.get("discharges_per_trial", 300)

    rows: list[dict] = []
    for trial in range(trials_per_batch):
        for dept in departments:
            rate = base_rates.get(dept, 0.12)
            readmissions = rng.binomial(discharges_per_trial, rate)
            simulated_rate = readmissions / discharges_per_trial
            rows.append(
                {
                    "batch_id": batch_id,
                    "trial_id": batch_id * trials_per_batch + trial,
                    "department": dept,
                    "simulated_readmission_rate": float(simulated_rate),
                }
            )
    return pd.DataFrame(rows)


@register_template("hourly_gamma")
def _simulate_ed_wait_time(pdf: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Simulate emergency department wait times by hour of day.

    Parameters (in *params*):
        base_wait_minutes   - baseline mean wait in minutes (default 45)
        peak_multiplier     - multiplier during peak hours (default 2.0)
        peak_hours          - list of peak hours 0-23 (default [10-14, 18-21])
        trials_per_batch    - trials per batch (default 200)
        patients_per_hour   - patients sampled per hour per trial (default 50)
    """
    batch_id = int(pdf["id"].iloc[0])
    seed = int(pdf["batch_seed"].iloc[0])
    rng = np.random.default_rng(seed)

    base_wait = params.get("base_wait_minutes", 45)
    peak_mult = params.get("peak_multiplier", 2.0)
    peak_hours = set(params.get("peak_hours", [10, 11, 12, 13, 14, 18, 19, 20, 21]))
    trials_per_batch = params.get("trials_per_batch", 200)
    patients_per_hour = params.get("patients_per_hour", 50)

    rows: list[dict] = []
    for trial in range(trials_per_batch):
        for hour in range(24):
            mean_wait = base_wait * (peak_mult if hour in peak_hours else 1.0)
            # Gamma distribution to keep wait times positive with right skew
            shape = (mean_wait / 15.0) ** 2  # variance ~ 15^2 base
            scale = mean_wait / shape if shape > 0 else 1.0
            samples = rng.gamma(shape, scale, size=patients_per_hour)
            avg_wait = float(np.mean(samples))
            rows.append(
                {
                    "batch_id": batch_id,
                    "trial_id": batch_id * trials_per_batch + trial,
                    "hour_of_day": hour,
                    "simulated_wait_minutes": avg_wait,
                }
            )
    return pd.DataFrame(rows)
