"""Tests for women's health hypothesis testing models — pure Python, no Spark required.

Tests for the two new simulation types:
- cost_comparison (H2): Virtual vs in-person cost comparison
- system_cost_roi (H5): Multi-year system cost ROI projection

All tests pass distribution specs via params["distributions"].
"""

import pandas as pd
import pytest

from src.mc_supervisor.monte_carlo import config_loader, model_templates


def _make_batch_df(batch_id: int = 0, seed: int = 42) -> pd.DataFrame:
    return pd.DataFrame({"id": [batch_id], "batch_seed": [seed]})


# Default distribution specs for tests
_COST_COMPARISON_DISTS = {
    "inperson_cost": {"type": "lognormal", "params": {"mean": 7.09, "sigma": 0.22}},
    "virtual_cost": {"type": "lognormal", "params": {"mean": 6.11, "sigma": 0.22}},
}

_SYSTEM_COST_ROI_DISTS = {
    "baseline_cost": {"type": "lognormal", "params": {"mean": 20.03, "sigma": 0.05}},
    "reduction_noise": {"type": "normal", "params": {"loc": 0, "scale": 0.1}},
}


# ---------------------------------------------------------------------------
# Cost Comparison (H2)
# ---------------------------------------------------------------------------


class TestCostComparison:
    """Validate the cohort_cost_comparison model template."""

    @pytest.fixture
    def result(self) -> pd.DataFrame:
        template_fn = model_templates.get_template("cohort_cost_comparison")
        params = {
            "trials_per_batch": 10,
            "member_count": 5000,
            "virtual_penetration": 0.30,
            "num_months": 12,
            "distributions": _COST_COMPARISON_DISTS,
        }
        return template_fn(_make_batch_df(), params)

    def test_schema_columns(self, result: pd.DataFrame):
        expected = {"batch_id", "trial_id", "care_model",
                    "simulated_cost_per_encounter", "simulated_total_cost",
                    "simulated_encounter_count"}
        assert set(result.columns) == expected

    def test_both_care_models_present(self, result: pd.DataFrame):
        models = set(result["care_model"].unique())
        assert models == {"in_person", "virtual_blend"}

    def test_two_rows_per_trial(self, result: pd.DataFrame):
        """Each trial should have exactly 2 rows (one per care model)."""
        assert len(result) == 10 * 2

    def test_costs_non_negative(self, result: pd.DataFrame):
        assert (result["simulated_cost_per_encounter"] >= 0).all()
        assert (result["simulated_total_cost"] >= 0).all()
        assert (result["simulated_encounter_count"] >= 0).all()

    def test_virtual_blend_cheaper_on_average(self):
        """Across many trials, virtual blend should have lower avg cost per encounter."""
        template_fn = model_templates.get_template("cohort_cost_comparison")
        params = {
            "trials_per_batch": 200,
            "member_count": 10000,
            "virtual_penetration": 0.30,
            "num_months": 12,
            "distributions": _COST_COMPARISON_DISTS,
        }
        result = template_fn(_make_batch_df(), params)

        ip = result[result["care_model"] == "in_person"]
        vb = result[result["care_model"] == "virtual_blend"]
        assert vb["simulated_cost_per_encounter"].mean() < ip["simulated_cost_per_encounter"].mean()

    def test_deterministic(self):
        template_fn = model_templates.get_template("cohort_cost_comparison")
        params = {
            "trials_per_batch": 5,
            "member_count": 100,
            "num_months": 6,
            "distributions": _COST_COMPARISON_DISTS,
        }
        r1 = template_fn(_make_batch_df(seed=42), params)
        r2 = template_fn(_make_batch_df(seed=42), params)
        pd.testing.assert_frame_equal(r1, r2)


# ---------------------------------------------------------------------------
# System Cost ROI (H5)
# ---------------------------------------------------------------------------


class TestSystemCostRoi:
    """Validate the multi_year_roi_projection model template."""

    @pytest.fixture
    def result(self) -> pd.DataFrame:
        template_fn = model_templates.get_template("multi_year_roi_projection")
        params = {
            "trials_per_batch": 10,
            "encounter_reduction_pct": 0.08,
            "labor_inflation_rate": 0.04,
            "expense_inflation": 0.03,
            "include_surgery": False,
            "solution_cost": 2_000_000_000,
            "num_years": 5,
            "labor_fraction": 0.55,
            "surgical_fraction": 0.15,
            "distributions": _SYSTEM_COST_ROI_DISTS,
        }
        return template_fn(_make_batch_df(), params)

    def test_schema_columns(self, result: pd.DataFrame):
        expected = {"batch_id", "trial_id", "year",
                    "simulated_baseline_cost", "simulated_reduced_cost",
                    "simulated_gross_savings", "simulated_net_savings",
                    "simulated_roi"}
        assert set(result.columns) == expected

    def test_multi_year_output(self, result: pd.DataFrame):
        """Output should have rows for years 1-5."""
        years = set(result["year"].unique())
        assert years == {1, 2, 3, 4, 5}

    def test_row_count(self, result: pd.DataFrame):
        """Should have trials * years rows."""
        assert len(result) == 10 * 5

    def test_gross_savings_non_negative(self, result: pd.DataFrame):
        """Gross savings should always be non-negative."""
        assert (result["simulated_gross_savings"] >= 0).all()

    def test_reduced_cost_less_than_baseline(self, result: pd.DataFrame):
        """Reduced cost should be less than baseline (savings applied)."""
        assert (result["simulated_reduced_cost"] <= result["simulated_baseline_cost"]).all()

    def test_roi_formula(self, result: pd.DataFrame):
        """ROI should approximately equal (net_savings / annual_solution_cost)."""
        annual_cost = 2_000_000_000 / 5  # total / years
        computed_roi = result["simulated_net_savings"] / annual_cost
        pd.testing.assert_series_equal(
            result["simulated_roi"],
            computed_roi,
            check_names=False,
            atol=1e-6,
        )

    def test_inflation_increases_baseline_over_years(self):
        """Baseline cost should increase year over year due to inflation."""
        template_fn = model_templates.get_template("multi_year_roi_projection")
        params = {
            "trials_per_batch": 1,
            "encounter_reduction_pct": 0.0,  # no reduction to isolate inflation
            "labor_inflation_rate": 0.04,
            "expense_inflation": 0.03,
            "include_surgery": False,
            "solution_cost": 0,  # no solution cost
            "num_years": 5,
            "labor_fraction": 0.55,
            "surgical_fraction": 0.15,
            "distributions": _SYSTEM_COST_ROI_DISTS,
        }
        result = template_fn(_make_batch_df(seed=99), params)
        baselines = result.sort_values("year")["simulated_baseline_cost"].values
        # Each year's baseline should be greater than the previous
        for i in range(1, len(baselines)):
            assert baselines[i] > baselines[i - 1], (
                f"Year {i+1} baseline ({baselines[i]}) not greater than year {i} ({baselines[i-1]})"
            )

    def test_include_surgery_increases_savings(self):
        """Including surgery in reduction should increase gross savings."""
        template_fn = model_templates.get_template("multi_year_roi_projection")
        base_params = {
            "trials_per_batch": 50,
            "encounter_reduction_pct": 0.08,
            "labor_inflation_rate": 0.04,
            "expense_inflation": 0.03,
            "solution_cost": 0,
            "num_years": 3,
            "labor_fraction": 0.55,
            "surgical_fraction": 0.15,
            "distributions": _SYSTEM_COST_ROI_DISTS,
        }

        params_no_surg = {**base_params, "include_surgery": False}
        params_with_surg = {**base_params, "include_surgery": True}

        r_no = template_fn(_make_batch_df(seed=42), params_no_surg)
        r_with = template_fn(_make_batch_df(seed=42), params_with_surg)

        assert r_with["simulated_gross_savings"].mean() > r_no["simulated_gross_savings"].mean()

    def test_deterministic(self):
        template_fn = model_templates.get_template("multi_year_roi_projection")
        params = {
            "trials_per_batch": 5,
            "num_years": 3,
            "distributions": _SYSTEM_COST_ROI_DISTS,
        }
        r1 = template_fn(_make_batch_df(seed=42), params)
        r2 = template_fn(_make_batch_df(seed=42), params)
        pd.testing.assert_frame_equal(r1, r2)
