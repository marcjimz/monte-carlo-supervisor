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


@register_template("encounter_margin_forecast")
def _simulate_encounter_margin(pdf: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Project monthly encounter direct margin with growth and cost inflation.

    Per trial per month:
    1. Sample monthly encounter volume, apply growth factor.
    2. Sample monthly direct margin base, apply growth and inflation.
    3. Compute margin per encounter.
    Output: month, direct_margin, volume, margin_per_encounter.

    Parameters (in *params*):
        distributions.monthly_margin   - monthly total direct margin distribution
        distributions.encounter_volume - monthly encounter count distribution
        distributions.cost_per_encounter - avg cost per encounter (lognormal)
        growth_rate      - annual encounter volume growth rate (default 0.02)
        cost_inflation   - annual cost inflation rate (default 0.035)
        num_months       - forecast horizon in months (default 12)
        trials_per_batch - trials in this batch (default 200)
    """
    batch_id = int(pdf["id"].iloc[0])
    seed = int(pdf["batch_seed"].iloc[0])
    rng = np.random.default_rng(seed)

    dist_specs = params.get("distributions", {})
    growth_rate = params.get("growth_rate", 0.02)
    cost_inflation = params.get("cost_inflation", 0.035)
    num_months = params.get("num_months", 12)
    trials_per_batch = params.get("trials_per_batch", 200)

    margin_spec = dist_specs.get(
        "monthly_margin",
        {"type": "normal", "params": {"loc": 4500000, "scale": 900000}},
    )
    volume_spec = dist_specs.get(
        "encounter_volume",
        {"type": "normal", "params": {"loc": 6250, "scale": 800}},
    )

    rows: list[dict] = []
    for trial in range(trials_per_batch):
        trial_id = batch_id * trials_per_batch + trial
        for m in range(num_months):
            # Growth compounds monthly, inflation erodes margin
            growth_factor = 1.0 + growth_rate * (m / 12.0)
            inflation_factor = 1.0 + cost_inflation * (m / 12.0)

            base_margin = float(sample_from_spec(rng, margin_spec)[0])
            base_volume = float(sample_from_spec(rng, volume_spec)[0])

            enc_volume = max(0.0, base_volume * growth_factor)
            # Margin grows with volume but is eroded by cost inflation
            direct_margin = base_margin * growth_factor / inflation_factor
            margin_per_enc = direct_margin / enc_volume if enc_volume > 0 else 0.0

            rows.append({
                "batch_id": batch_id,
                "trial_id": trial_id,
                "month": f"M{m + 1:02d}",
                "simulated_direct_margin": max(0.0, direct_margin),
                "simulated_encounter_volume": enc_volume,
                "simulated_margin_per_encounter": margin_per_enc,
            })

    return pd.DataFrame(rows)


@register_template("wh_margin_cohort")
def _simulate_wh_margin_comparison(pdf: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Compare direct margins between WH and non-WH populations.

    Per trial: sample WH and non-WH per-encounter margin. Compute two
    scenarios — baseline (current WH penetration) and wh_expanded (target
    penetration). Output: scenario, margin_per_encounter, direct_margin,
    encounter_count.

    Parameters (in *params*):
        distributions.wh_margin     - per-encounter direct margin for WH population
        distributions.non_wh_margin - per-encounter direct margin for non-WH population
        total_encounters       - total annual encounter volume (default 75000)
        wh_penetration         - current WH population fraction (default 0.35)
        wh_penetration_target  - target WH penetration (default 0.50)
        num_months             - projection horizon in months (default 12)
        trials_per_batch       - trials per batch (default 200)
    """
    batch_id = int(pdf["id"].iloc[0])
    seed = int(pdf["batch_seed"].iloc[0])
    rng = np.random.default_rng(seed)

    dist_specs = params.get("distributions", {})
    total_encounters = params.get("total_encounters", 75000)
    wh_pen = params.get("wh_penetration", 0.35)
    wh_target = params.get("wh_penetration_target", 0.50)
    num_months = params.get("num_months", 12)
    trials_per_batch = params.get("trials_per_batch", 200)

    wh_spec = dist_specs.get(
        "wh_margin",
        {"type": "normal", "params": {"loc": 850, "scale": 200}},
    )
    non_wh_spec = dist_specs.get(
        "non_wh_margin",
        {"type": "normal", "params": {"loc": 620, "scale": 180}},
    )

    monthly_encounters = total_encounters * (num_months / 12.0)

    rows: list[dict] = []
    for trial in range(trials_per_batch):
        trial_id = batch_id * trials_per_batch + trial

        wh_margin_per_enc = float(sample_from_spec(rng, wh_spec)[0])
        non_wh_margin_per_enc = float(sample_from_spec(rng, non_wh_spec)[0])

        # Baseline scenario: current penetration mix
        base_wh_enc = monthly_encounters * wh_pen
        base_non_wh_enc = monthly_encounters * (1 - wh_pen)
        base_total_margin = (
            wh_margin_per_enc * base_wh_enc
            + non_wh_margin_per_enc * base_non_wh_enc
        )
        base_blended = (
            base_total_margin / monthly_encounters if monthly_encounters > 0 else 0.0
        )

        rows.append({
            "batch_id": batch_id,
            "trial_id": trial_id,
            "scenario": "baseline",
            "simulated_margin_per_encounter": base_blended,
            "simulated_direct_margin": base_total_margin,
            "simulated_encounter_count": monthly_encounters,
        })

        # Expanded WH scenario: target penetration
        exp_wh_enc = monthly_encounters * wh_target
        exp_non_wh_enc = monthly_encounters * (1 - wh_target)
        exp_total_margin = (
            wh_margin_per_enc * exp_wh_enc
            + non_wh_margin_per_enc * exp_non_wh_enc
        )
        exp_blended = (
            exp_total_margin / monthly_encounters if monthly_encounters > 0 else 0.0
        )

        rows.append({
            "batch_id": batch_id,
            "trial_id": trial_id,
            "scenario": "wh_expanded",
            "simulated_margin_per_encounter": exp_blended,
            "simulated_direct_margin": exp_total_margin,
            "simulated_encounter_count": monthly_encounters,
        })

    return pd.DataFrame(rows)
