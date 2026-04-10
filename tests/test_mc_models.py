"""Tests for Monte Carlo simulation model functions — pure Python, no Spark required.

Each model function takes (pdf: pd.DataFrame, params: dict) -> pd.DataFrame
where pdf has columns [id, batch_seed].
"""

import pandas as pd
import pytest

from src.databricks.monte_carlo import config_loader
from src.databricks.monte_carlo.engine import (
    _simulate_ed_wait_time,
    _simulate_length_of_stay,
    _simulate_patient_volume,
    _simulate_readmission_rate,
    _simulate_revenue,
    get_available_simulation_types,
    get_simulation_model,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_batch_df(batch_id: int = 0, seed: int = 42) -> pd.DataFrame:
    """Create a single-row batch DataFrame matching the expected schema."""
    return pd.DataFrame({"id": [batch_id], "batch_seed": [seed]})


# Use small trial count to keep tests fast
SMALL_PARAMS = {"trials_per_batch": 3, "num_months": 4}


# ---------------------------------------------------------------------------
# Patient volume model
# ---------------------------------------------------------------------------


class TestPatientVolumeModel:
    def test_output_columns(self):
        pdf = _make_batch_df()
        result = _simulate_patient_volume(pdf, SMALL_PARAMS)
        expected_cols = {"batch_id", "trial_id", "month", "simulated_encounters"}
        assert expected_cols == set(result.columns)

    def test_non_negative_values(self):
        pdf = _make_batch_df()
        result = _simulate_patient_volume(pdf, SMALL_PARAMS)
        assert (result["simulated_encounters"] >= 0).all()

    def test_row_count(self):
        pdf = _make_batch_df()
        params = {"trials_per_batch": 5, "num_months": 6}
        result = _simulate_patient_volume(pdf, params)
        assert len(result) == 5 * 6  # trials x months


# ---------------------------------------------------------------------------
# Revenue model
# ---------------------------------------------------------------------------


class TestRevenueModel:
    def test_output_columns(self):
        pdf = _make_batch_df()
        result = _simulate_revenue(pdf, SMALL_PARAMS)
        expected_cols = {"batch_id", "trial_id", "month", "simulated_revenue", "simulated_charges"}
        assert expected_cols == set(result.columns)

    def test_non_negative_values(self):
        pdf = _make_batch_df()
        result = _simulate_revenue(pdf, SMALL_PARAMS)
        assert (result["simulated_revenue"] >= 0).all()
        assert (result["simulated_charges"] >= 0).all()


# ---------------------------------------------------------------------------
# Length-of-stay model
# ---------------------------------------------------------------------------


class TestLengthOfStayModel:
    def test_output_columns(self):
        pdf = _make_batch_df()
        params = {"trials_per_batch": 2, "patients_per_trial": 10, "departments": ["Emergency", "Cardiology"]}
        result = _simulate_length_of_stay(pdf, params)
        expected_cols = {"batch_id", "trial_id", "department", "simulated_avg_los"}
        assert expected_cols == set(result.columns)

    def test_positive_los(self):
        pdf = _make_batch_df()
        params = {"trials_per_batch": 2, "patients_per_trial": 10, "departments": ["Emergency"]}
        result = _simulate_length_of_stay(pdf, params)
        assert (result["simulated_avg_los"] > 0).all()


# ---------------------------------------------------------------------------
# Readmission rate model
# ---------------------------------------------------------------------------


class TestReadmissionModel:
    def test_output_columns(self):
        pdf = _make_batch_df()
        params = {"trials_per_batch": 2, "discharges_per_trial": 50, "departments": ["Emergency"]}
        result = _simulate_readmission_rate(pdf, params)
        expected_cols = {"batch_id", "trial_id", "department", "simulated_readmission_rate"}
        assert expected_cols == set(result.columns)

    def test_rate_between_zero_and_one(self):
        pdf = _make_batch_df()
        params = {"trials_per_batch": 5, "discharges_per_trial": 100, "departments": ["Cardiology", "Oncology"]}
        result = _simulate_readmission_rate(pdf, params)
        assert (result["simulated_readmission_rate"] >= 0).all()
        assert (result["simulated_readmission_rate"] <= 1).all()


# ---------------------------------------------------------------------------
# ED wait time model
# ---------------------------------------------------------------------------


class TestEdWaitModel:
    def test_output_columns(self):
        pdf = _make_batch_df()
        params = {"trials_per_batch": 2, "patients_per_hour": 10}
        result = _simulate_ed_wait_time(pdf, params)
        expected_cols = {"batch_id", "trial_id", "hour_of_day", "simulated_wait_minutes"}
        assert expected_cols == set(result.columns)

    def test_positive_wait_times(self):
        pdf = _make_batch_df()
        params = {"trials_per_batch": 2, "patients_per_hour": 10}
        result = _simulate_ed_wait_time(pdf, params)
        assert (result["simulated_wait_minutes"] > 0).all()

    def test_24_hours_per_trial(self):
        pdf = _make_batch_df()
        params = {"trials_per_batch": 3, "patients_per_hour": 5}
        result = _simulate_ed_wait_time(pdf, params)
        assert len(result) == 3 * 24  # trials x hours


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterministic:
    def test_same_seed_produces_same_patient_volume(self):
        pdf = _make_batch_df(batch_id=0, seed=42)
        params = {"trials_per_batch": 3, "num_months": 4}
        r1 = _simulate_patient_volume(pdf.copy(), params)
        r2 = _simulate_patient_volume(pdf.copy(), params)
        pd.testing.assert_frame_equal(r1, r2)

    def test_same_seed_produces_same_revenue(self):
        pdf = _make_batch_df(batch_id=0, seed=99)
        params = {"trials_per_batch": 3, "num_months": 4}
        r1 = _simulate_revenue(pdf.copy(), params)
        r2 = _simulate_revenue(pdf.copy(), params)
        pd.testing.assert_frame_equal(r1, r2)

    def test_different_seed_produces_different_results(self):
        params = {"trials_per_batch": 3, "num_months": 4}
        r1 = _simulate_patient_volume(_make_batch_df(seed=1), params)
        r2 = _simulate_patient_volume(_make_batch_df(seed=2), params)
        # Extremely unlikely for all values to be identical with different seeds
        assert not r1["simulated_encounters"].equals(r2["simulated_encounters"])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class TestPublicAPI:
    def test_get_simulation_model_returns_callable(self):
        for sim_type in get_available_simulation_types():
            fn, schema = get_simulation_model(sim_type)
            assert callable(fn)
            assert isinstance(schema, str)

    def test_get_simulation_model_raises_for_unknown(self):
        with pytest.raises(ValueError, match="Unknown simulation type"):
            get_simulation_model("nonexistent_type")

    def test_get_available_types(self):
        types = get_available_simulation_types()
        expected = set(config_loader.get_valid_types())
        assert set(types) == expected
        assert len(types) == len(expected)
