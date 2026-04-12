"""Model template functions for Monte Carlo simulations.

Each template implements a reusable statistical model pattern. The config.yaml
specifies which template to use for each simulation type.

All stochastic draws go through ``distribution_sampler.sample_from_spec()``
using distribution specs from ``params["distributions"]``.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from .distribution_sampler import sample_from_spec

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
        distributions.encounter_volume - distribution spec for base encounter volume
        growth_rate        - year-over-year growth rate (default 0.03)
        seasonality_amp    - amplitude of seasonal sine wave (default 0.08)
        num_months         - forecast horizon in months (default 12)
        trials_per_batch   - number of trials in this batch (default 200)
    """
    batch_id = int(pdf["id"].iloc[0])
    seed = int(pdf["batch_seed"].iloc[0])
    rng = np.random.default_rng(seed)

    dist_specs = params.get("distributions", {})
    growth_rate = params.get("growth_rate", 0.03)
    seasonality_amp = params.get("seasonality_amp", 0.08)
    num_months = params.get("num_months", 12)
    trials_per_batch = params.get("trials_per_batch", 200)

    encounter_spec = dist_specs.get("encounter_volume", {"type": "normal", "params": {"loc": 4200, "scale": 600}})

    rows: list[dict] = []
    for trial in range(trials_per_batch):
        for m in range(num_months):
            growth_factor = 1.0 + growth_rate * (m / 12.0)
            seasonal_factor = 1.0 + seasonality_amp * np.sin(2 * np.pi * (m - 1) / 12.0)
            base_value = sample_from_spec(rng, encounter_spec)
            value = float(base_value[0]) * growth_factor * seasonal_factor
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
        distributions.gross_charges - distribution spec for monthly gross charges
        distributions.denial_rate   - distribution spec for claim denial rate (beta)
        avg_charge_to_rev     - charge-to-revenue ratio (default 1.35)
        num_months            - forecast horizon (default 12)
        trials_per_batch      - trials in this batch (default 200)
    """
    batch_id = int(pdf["id"].iloc[0])
    seed = int(pdf["batch_seed"].iloc[0])
    rng = np.random.default_rng(seed)

    dist_specs = params.get("distributions", {})
    charge_ratio = params.get("avg_charge_to_rev", 1.35)
    num_months = params.get("num_months", 12)
    trials_per_batch = params.get("trials_per_batch", 200)

    charges_spec = dist_specs.get("gross_charges", {"type": "normal", "params": {"loc": 6750000, "scale": 1080000}})
    denial_spec = dist_specs.get("denial_rate", {"type": "beta", "params": {"a": 2, "b": 23}})

    rows: list[dict] = []
    for trial in range(trials_per_batch):
        for m in range(num_months):
            gross_charges = float(sample_from_spec(rng, charges_spec)[0])
            gross_charges = max(0.0, gross_charges)
            denied_fraction = float(sample_from_spec(rng, denial_spec)[0])
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

    Per trial: draw in-person cost from distribution spec, virtual cost from
    distribution spec (lower mean). Output 2 rows per trial (one per care_model)
    with cost_per_encounter, total_cost, encounter_count.

    Parameters (in *params*):
        distributions.inperson_cost  - cost per in-person encounter (lognormal)
        distributions.virtual_cost   - cost per virtual encounter (lognormal)
        member_count            - covered population size (default 50000)
        virtual_penetration     - fraction using virtual care (default 0.30)
        annual_encounter_rate   - avg encounters per member per year (default 2.5)
        num_months              - projection horizon in months (default 12)
        trials_per_batch        - trials per batch (default 200)
    """
    batch_id = int(pdf["id"].iloc[0])
    seed = int(pdf["batch_seed"].iloc[0])
    rng = np.random.default_rng(seed)

    dist_specs = params.get("distributions", {})
    member_count = params.get("member_count", 50000)
    virtual_pen = params.get("virtual_penetration", 0.30)
    num_months = params.get("num_months", 12)
    trials_per_batch = params.get("trials_per_batch", 200)
    annual_encounter_rate = params.get("annual_encounter_rate", 2.5)

    inperson_spec = dist_specs.get("inperson_cost", {"type": "lognormal", "params": {"mean": 7.09, "sigma": 0.22}})
    virtual_spec = dist_specs.get("virtual_cost", {"type": "lognormal", "params": {"mean": 6.11, "sigma": 0.22}})

    rows: list[dict] = []
    for trial in range(trials_per_batch):
        trial_id = batch_id * trials_per_batch + trial

        # In-person arm: all members stay in-person
        ip_cost_per_enc = float(sample_from_spec(rng, inperson_spec)[0])
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
        vt_cost_per_enc = float(sample_from_spec(rng, virtual_spec)[0])
        ip_cost_remaining = float(sample_from_spec(rng, inperson_spec)[0])

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

    Per trial: draw baseline from distribution spec, then for each year: inflate
    costs, apply encounter reduction (excluding surgical if include_surgery=false),
    compute gross_savings, subtract annual solution cost for net_savings,
    compute ROI. Output 1 row per year.

    Parameters (in *params*):
        distributions.baseline_cost    - baseline annual system cost (lognormal)
        distributions.reduction_noise  - noise on encounter reduction (normal)
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

    dist_specs = params.get("distributions", {})
    reduction_pct = params.get("encounter_reduction_pct", 0.08)
    labor_inflation = params.get("labor_inflation_rate", 0.04)
    expense_inflation = params.get("expense_inflation", 0.03)
    include_surgery = params.get("include_surgery", False)
    total_solution_cost = params.get("solution_cost", 2_000_000_000)
    num_years = params.get("num_years", 5)
    labor_frac = params.get("labor_fraction", 0.55)
    surgical_frac = params.get("surgical_fraction", 0.15)
    trials_per_batch = params.get("trials_per_batch", 200)

    baseline_spec = dist_specs.get("baseline_cost", {"type": "lognormal", "params": {"mean": 20.03, "sigma": 0.05}})
    noise_spec = dist_specs.get("reduction_noise", {"type": "normal", "params": {"loc": 0, "scale": 0.1}})

    # Annual solution cost = total / num_years
    annual_solution_cost = total_solution_cost / max(num_years, 1)

    rows: list[dict] = []
    for trial in range(trials_per_batch):
        trial_id = batch_id * trials_per_batch + trial
        # Draw stochastic baseline
        base_cost = float(sample_from_spec(rng, baseline_spec)[0])

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

            # Apply encounter reduction with noise from distribution spec
            noise = float(sample_from_spec(rng, noise_spec)[0])
            effective_reduction = reduction_pct * (1 + noise)
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
