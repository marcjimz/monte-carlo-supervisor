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
        monthly_mean       - average encounters per month (default 4200)
        monthly_std        - std-dev of encounters per month (default 600)
        growth_rate        - year-over-year growth rate (default 0.03)
        seasonality_amp    - amplitude of seasonal sine wave (default 0.08)
        num_months         - forecast horizon in months (default 12)
        trials_per_batch   - number of trials in this batch (default 200)
    """
    batch_id = int(pdf["id"].iloc[0])
    seed = int(pdf["batch_seed"].iloc[0])
    rng = np.random.default_rng(seed)

    monthly_mean = params.get("monthly_mean", 4200)
    monthly_std = params.get("monthly_std", 600)
    growth_rate = params.get("growth_rate", 0.03)
    seasonality_amp = params.get("seasonality_amp", 0.08)
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
        avg_monthly_revenue   - baseline monthly revenue (default 5_000_000)
        revenue_std           - std-dev (default 800_000)
        avg_charge_to_rev     - charge-to-revenue ratio (default 1.35)
        denial_rate           - claim denial rate (default 0.08)
        num_months            - forecast horizon (default 12)
        trials_per_batch      - trials in this batch (default 200)
    """
    batch_id = int(pdf["id"].iloc[0])
    seed = int(pdf["batch_seed"].iloc[0])
    rng = np.random.default_rng(seed)

    avg_rev = params.get("avg_monthly_revenue", 5_000_000)
    rev_std = params.get("revenue_std", 800_000)
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


@register_template("cohort_cost_comparison")
def _simulate_cost_comparison(pdf: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Compare costs between virtual and in-person care for women's health.

    Per trial: draw in-person cost from LogNormal, virtual cost from LogNormal
    (lower mean). Output 2 rows per trial (one per care_model) with
    cost_per_encounter, total_cost, encounter_count.

    Parameters (in *params*):
        baseline_cost_inperson  - avg cost per in-person encounter (default 1200)
        projected_cost_virtual  - avg cost per virtual encounter (default 450)
        cost_std_fraction       - cost uncertainty as fraction of mean (default 0.25)
        member_count            - covered population size (default 50000)
        virtual_penetration     - fraction using virtual care (default 0.30)
        num_months              - projection horizon in months (default 12)
        trials_per_batch        - trials per batch (default 200)
    """
    batch_id = int(pdf["id"].iloc[0])
    seed = int(pdf["batch_seed"].iloc[0])
    rng = np.random.default_rng(seed)

    inperson_mean = params.get("baseline_cost_inperson", 1200)
    virtual_mean = params.get("projected_cost_virtual", 450)
    cost_std_frac = params.get("cost_std_fraction", 0.25)
    member_count = params.get("member_count", 50000)
    virtual_pen = params.get("virtual_penetration", 0.30)
    num_months = params.get("num_months", 12)
    trials_per_batch = params.get("trials_per_batch", 200)

    # LogNormal parameters: mu = ln(mean) - sigma^2/2 so that E[X] = mean
    def _lognormal_params(mean: float, std_frac: float):
        sigma = np.sqrt(np.log(1 + std_frac**2))
        mu = np.log(mean) - sigma**2 / 2
        return mu, sigma

    ip_mu, ip_sigma = _lognormal_params(inperson_mean, cost_std_frac)
    vt_mu, vt_sigma = _lognormal_params(virtual_mean, cost_std_frac)

    # Encounter rate: ~2.5 encounters per member per year (WH baseline)
    annual_encounter_rate = 2.5

    rows: list[dict] = []
    for trial in range(trials_per_batch):
        trial_id = batch_id * trials_per_batch + trial

        # In-person arm: all members stay in-person
        ip_cost_per_enc = float(rng.lognormal(ip_mu, ip_sigma))
        ip_encounter_count = member_count * annual_encounter_rate * (num_months / 12.0)
        ip_total_cost = ip_cost_per_enc * ip_encounter_count

        rows.append({
            "batch_id": batch_id,
            "trial_id": trial_id,
            "care_model": "in_person",
            "simulated_cost_per_encounter": ip_cost_per_enc,
            "simulated_total_cost": ip_total_cost,
            "simulated_encounter_count": ip_encounter_count,
        })

        # Virtual arm: fraction shifts to virtual care
        n_virtual = member_count * virtual_pen
        n_inperson = member_count - n_virtual
        vt_cost_per_enc = float(rng.lognormal(vt_mu, vt_sigma))
        ip_cost_remaining = float(rng.lognormal(ip_mu, ip_sigma))

        virtual_encounters = n_virtual * annual_encounter_rate * (num_months / 12.0)
        inperson_encounters = n_inperson * annual_encounter_rate * (num_months / 12.0)
        blended_total = (vt_cost_per_enc * virtual_encounters +
                         ip_cost_remaining * inperson_encounters)
        total_encounters = virtual_encounters + inperson_encounters
        blended_cost_per_enc = blended_total / total_encounters if total_encounters > 0 else 0.0

        rows.append({
            "batch_id": batch_id,
            "trial_id": trial_id,
            "care_model": "virtual_blend",
            "simulated_cost_per_encounter": blended_cost_per_enc,
            "simulated_total_cost": blended_total,
            "simulated_encounter_count": total_encounters,
        })

    return pd.DataFrame(rows)


@register_template("multi_year_roi_projection")
def _simulate_system_cost_roi(pdf: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Project total system cost reduction and ROI from virtual care partnership.

    Per trial: draw baseline from LogNormal, then for each year: inflate costs,
    apply encounter reduction (excluding surgical if include_surgery=false),
    compute gross_savings, subtract annual solution cost for net_savings,
    compute ROI. Output 1 row per year.

    Parameters (in *params*):
        baseline_annual_cost    - total annual WH system cost (default 500M)
        encounter_reduction_pct - pct reduction in encounters (default 0.08)
        labor_inflation_rate    - annual labor inflation (default 0.04)
        expense_inflation       - annual non-labor inflation (default 0.03)
        include_surgery         - include surgical costs in reduction (default false)
        solution_cost           - total investment cost over period (default 2B)
        num_years               - projection horizon in years (default 5)
        labor_fraction          - fraction of cost from labor (default 0.55)
        surgical_fraction       - fraction from surgical encounters (default 0.15)
        trials_per_batch        - trials per batch (default 200)
    """
    batch_id = int(pdf["id"].iloc[0])
    seed = int(pdf["batch_seed"].iloc[0])
    rng = np.random.default_rng(seed)

    baseline = params.get("baseline_annual_cost", 500_000_000)
    reduction_pct = params.get("encounter_reduction_pct", 0.08)
    labor_inflation = params.get("labor_inflation_rate", 0.04)
    expense_inflation = params.get("expense_inflation", 0.03)
    include_surgery = params.get("include_surgery", False)
    total_solution_cost = params.get("solution_cost", 2_000_000_000)
    num_years = params.get("num_years", 5)
    labor_frac = params.get("labor_fraction", 0.55)
    surgical_frac = params.get("surgical_fraction", 0.15)
    trials_per_batch = params.get("trials_per_batch", 200)

    # Annual solution cost = total / num_years
    annual_solution_cost = total_solution_cost / max(num_years, 1)

    # LogNormal params for baseline cost uncertainty (~5% std)
    sigma = np.sqrt(np.log(1 + 0.05**2))
    mu = np.log(baseline) - sigma**2 / 2

    rows: list[dict] = []
    for trial in range(trials_per_batch):
        trial_id = batch_id * trials_per_batch + trial
        # Draw stochastic baseline
        base_cost = float(rng.lognormal(mu, sigma))

        for year in range(1, num_years + 1):
            # Inflate baseline
            labor_cost = base_cost * labor_frac * (1 + labor_inflation) ** year
            non_labor_cost = base_cost * (1 - labor_frac) * (1 + expense_inflation) ** year
            inflated_baseline = labor_cost + non_labor_cost

            # Reducible portion: exclude surgical unless include_surgery
            if include_surgery:
                reducible_fraction = 1.0
            else:
                reducible_fraction = 1.0 - surgical_frac

            # Apply encounter reduction with some noise
            effective_reduction = reduction_pct * (1 + rng.normal(0, 0.1))
            effective_reduction = max(0, min(effective_reduction, 0.5))  # cap at 50%

            gross_savings = inflated_baseline * reducible_fraction * effective_reduction
            reduced_cost = inflated_baseline - gross_savings
            net_savings = gross_savings - annual_solution_cost
            roi = net_savings / annual_solution_cost if annual_solution_cost > 0 else 0.0

            rows.append({
                "batch_id": batch_id,
                "trial_id": trial_id,
                "year": year,
                "simulated_baseline_cost": inflated_baseline,
                "simulated_reduced_cost": reduced_cost,
                "simulated_gross_savings": gross_savings,
                "simulated_net_savings": net_savings,
                "simulated_roi": roi,
            })

    return pd.DataFrame(rows)
