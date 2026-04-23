"""Tests for encounter-based model templates — pure Python, no Spark required.

Tests for the two simulation types:
- encounter_margin (encounter_margin_forecast template)
- wh_margin_comparison (wh_margin_cohort template)

All tests pass distribution specs via params["distributions"].
"""

import pandas as pd
import pytest

from src.mc_supervisor.monte_carlo import model_templates


def _make_batch_df(batch_id: int = 0, seed: int = 42) -> pd.DataFrame:
    return pd.DataFrame({"id": [batch_id], "batch_seed": [seed]})


# Default distribution specs for tests
_ENCOUNTER_MARGIN_DISTS = {
    "monthly_margin": {"type": "normal", "params": {"loc": 4500000, "scale": 900000}},
    "encounter_volume": {"type": "normal", "params": {"loc": 6250, "scale": 800}},
    "cost_per_encounter": {"type": "lognormal", "params": {"mean": 7.5, "sigma": 0.3}},
}

_WH_MARGIN_DISTS = {
    "wh_margin": {"type": "normal", "params": {"loc": 850, "scale": 200}},
    "non_wh_margin": {"type": "normal", "params": {"loc": 620, "scale": 180}},
}


# ---------------------------------------------------------------------------
# Encounter Margin Forecast
# ---------------------------------------------------------------------------


class TestEncounterMarginForecast:
    """Validate the encounter_margin_forecast model template."""

    @pytest.fixture
    def result(self) -> pd.DataFrame:
        template_fn = model_templates.get_template("encounter_margin_forecast")
        params = {
            "trials_per_batch": 10,
            "growth_rate": 0.02,
            "cost_inflation": 0.035,
            "num_months": 12,
            "distributions": _ENCOUNTER_MARGIN_DISTS,
        }
        return template_fn(_make_batch_df(), params)

    def test_schema_columns(self, result: pd.DataFrame):
        expected = {"batch_id", "trial_id", "month",
                    "simulated_direct_margin", "simulated_encounter_volume",
                    "simulated_margin_per_encounter"}
        assert set(result.columns) == expected

    def test_all_months_present(self, result: pd.DataFrame):
        months = set(result["month"].unique())
        expected_months = {f"M{m:02d}" for m in range(1, 13)}
        assert months == expected_months

    def test_row_count(self, result: pd.DataFrame):
        """Should have trials * months rows."""
        assert len(result) == 10 * 12

    def test_margins_non_negative(self, result: pd.DataFrame):
        assert (result["simulated_direct_margin"] >= 0).all()

    def test_volume_non_negative(self, result: pd.DataFrame):
        assert (result["simulated_encounter_volume"] >= 0).all()

    def test_margin_per_encounter_consistent(self, result: pd.DataFrame):
        """margin_per_encounter should equal direct_margin / volume."""
        non_zero = result[result["simulated_encounter_volume"] > 0]
        computed = non_zero["simulated_direct_margin"] / non_zero["simulated_encounter_volume"]
        pd.testing.assert_series_equal(
            non_zero["simulated_margin_per_encounter"],
            computed,
            check_names=False,
            atol=1e-6,
        )

    def test_deterministic(self):
        template_fn = model_templates.get_template("encounter_margin_forecast")
        params = {
            "trials_per_batch": 5,
            "num_months": 6,
            "distributions": _ENCOUNTER_MARGIN_DISTS,
        }
        r1 = template_fn(_make_batch_df(seed=42), params)
        r2 = template_fn(_make_batch_df(seed=42), params)
        pd.testing.assert_frame_equal(r1, r2)


# ---------------------------------------------------------------------------
# WH Margin Comparison
# ---------------------------------------------------------------------------


class TestWhMarginComparison:
    """Validate the wh_margin_cohort model template."""

    @pytest.fixture
    def result(self) -> pd.DataFrame:
        template_fn = model_templates.get_template("wh_margin_cohort")
        params = {
            "trials_per_batch": 10,
            "total_encounters": 75000,
            "wh_penetration": 0.35,
            "wh_penetration_target": 0.50,
            "num_months": 12,
            "distributions": _WH_MARGIN_DISTS,
        }
        return template_fn(_make_batch_df(), params)

    def test_schema_columns(self, result: pd.DataFrame):
        expected = {"batch_id", "trial_id", "scenario",
                    "simulated_margin_per_encounter", "simulated_direct_margin",
                    "simulated_encounter_count"}
        assert set(result.columns) == expected

    def test_both_scenarios_present(self, result: pd.DataFrame):
        scenarios = set(result["scenario"].unique())
        assert scenarios == {"baseline", "wh_expanded"}

    def test_two_rows_per_trial(self, result: pd.DataFrame):
        """Each trial should have exactly 2 rows (one per scenario)."""
        assert len(result) == 10 * 2

    def test_encounter_counts_positive(self, result: pd.DataFrame):
        assert (result["simulated_encounter_count"] > 0).all()

    def test_expanded_wh_higher_margin_on_average(self):
        """With higher WH margin, expanded WH should have higher blended margin."""
        template_fn = model_templates.get_template("wh_margin_cohort")
        params = {
            "trials_per_batch": 200,
            "total_encounters": 75000,
            "wh_penetration": 0.35,
            "wh_penetration_target": 0.50,
            "num_months": 12,
            "distributions": _WH_MARGIN_DISTS,
        }
        result = template_fn(_make_batch_df(), params)

        baseline = result[result["scenario"] == "baseline"]
        expanded = result[result["scenario"] == "wh_expanded"]
        assert (
            expanded["simulated_margin_per_encounter"].mean()
            > baseline["simulated_margin_per_encounter"].mean()
        )

    def test_deterministic(self):
        template_fn = model_templates.get_template("wh_margin_cohort")
        params = {
            "trials_per_batch": 5,
            "total_encounters": 10000,
            "distributions": _WH_MARGIN_DISTS,
        }
        r1 = template_fn(_make_batch_df(seed=42), params)
        r2 = template_fn(_make_batch_df(seed=42), params)
        pd.testing.assert_frame_equal(r1, r2)
