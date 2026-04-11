"""Tests for Monte Carlo simulation model functions — pure Python, no Spark required.

Each model function takes (pdf: pd.DataFrame, params: dict) -> pd.DataFrame
where pdf has columns [id, batch_seed].

Tests are parametrized over config.yaml so adding a new simulation type
automatically gets test coverage.
"""

import json

import pandas as pd
import pytest

from src.databricks.monte_carlo import config_loader, model_templates
from src.databricks.monte_carlo.engine import (
    get_available_simulation_types,
    get_simulation_model,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_batch_df(batch_id: int = 0, seed: int = 42) -> pd.DataFrame:
    """Create a single-row batch DataFrame matching the expected schema."""
    return pd.DataFrame({"id": [batch_id], "batch_seed": [seed]})


def _parse_schema_columns(schema_str: str) -> set[str]:
    """Parse a Spark DDL schema string into a set of column names.

    E.g. "batch_id long, trial_id long, month string" -> {"batch_id", "trial_id", "month"}
    """
    cols = set()
    for field in schema_str.split(","):
        parts = field.strip().split()
        if parts:
            cols.add(parts[0])
    return cols


def _get_small_params(simulation_type: str) -> dict:
    """Return small-scale params for fast testing of the given simulation type."""
    defaults = config_loader.get_default_params(simulation_type)
    # Override to small scale
    defaults["trials_per_batch"] = 3
    # Limit departments/months for speed
    if "num_months" in defaults:
        defaults["num_months"] = 4
    if "departments" in defaults:
        defaults["departments"] = defaults["departments"][:2]
    if "patients_per_trial" in defaults:
        defaults["patients_per_trial"] = 10
    if "discharges_per_trial" in defaults:
        defaults["discharges_per_trial"] = 50
    if "patients_per_hour" in defaults:
        defaults["patients_per_hour"] = 10
    return defaults


# ---------------------------------------------------------------------------
# Config-driven parametrized tests
# ---------------------------------------------------------------------------

_ALL_TYPES = config_loader.get_valid_types()


@pytest.mark.parametrize("sim_type", _ALL_TYPES)
class TestModelOutput:
    """Verify each simulation type produces correct output columns and valid data."""

    def test_output_columns_match_schema(self, sim_type):
        """Output DataFrame columns must match the schema defined in config.yaml."""
        schema_str = config_loader.get_schema(sim_type)
        expected_cols = _parse_schema_columns(schema_str)

        template_name = config_loader.get_model_template(sim_type)
        template_fn = model_templates.get_template(template_name)

        pdf = _make_batch_df()
        params = _get_small_params(sim_type)
        result = template_fn(pdf, params)

        assert set(result.columns) == expected_cols, (
            f"{sim_type}: expected columns {expected_cols}, got {set(result.columns)}"
        )

    def test_non_empty_output(self, sim_type):
        """Model must produce at least one row of output."""
        template_name = config_loader.get_model_template(sim_type)
        template_fn = model_templates.get_template(template_name)

        pdf = _make_batch_df()
        params = _get_small_params(sim_type)
        result = template_fn(pdf, params)

        assert len(result) > 0

    def test_value_column_non_negative(self, sim_type):
        """The aggregation value column must have non-negative values."""
        value_col, _ = config_loader.get_agg_config(sim_type)
        template_name = config_loader.get_model_template(sim_type)
        template_fn = model_templates.get_template(template_name)

        pdf = _make_batch_df()
        params = _get_small_params(sim_type)
        result = template_fn(pdf, params)

        assert (result[value_col] >= 0).all(), (
            f"{sim_type}: {value_col} has negative values"
        )

    def test_batch_id_populated(self, sim_type):
        """batch_id column must be present and populated."""
        template_name = config_loader.get_model_template(sim_type)
        template_fn = model_templates.get_template(template_name)

        pdf = _make_batch_df(batch_id=7)
        params = _get_small_params(sim_type)
        result = template_fn(pdf, params)

        assert (result["batch_id"] == 7).all()


# ---------------------------------------------------------------------------
# Rate-bounded models (readmission_rate is between 0 and 1)
# ---------------------------------------------------------------------------


class TestRateBounds:
    def test_readmission_rate_between_zero_and_one(self):
        if "readmission_rate" not in _ALL_TYPES:
            pytest.skip("readmission_rate not in config")
        template_fn = model_templates.get_template("grouped_binomial_rate")
        pdf = _make_batch_df()
        params = _get_small_params("readmission_rate")
        result = template_fn(pdf, params)
        assert (result["simulated_readmission_rate"] >= 0).all()
        assert (result["simulated_readmission_rate"] <= 1).all()


# ---------------------------------------------------------------------------
# Row count tests (model-specific structure)
# ---------------------------------------------------------------------------


class TestRowCounts:
    def test_timeseries_row_count(self):
        """Timeseries models produce trials * months rows."""
        if "patient_volume" not in _ALL_TYPES:
            pytest.skip("patient_volume not in config")
        template_fn = model_templates.get_template("normal_timeseries")
        pdf = _make_batch_df()
        params = {"trials_per_batch": 5, "num_months": 6}
        result = template_fn(pdf, params)
        assert len(result) == 5 * 6

    def test_hourly_row_count(self):
        """Hourly models produce trials * 24 rows."""
        if "ed_wait_time" not in _ALL_TYPES:
            pytest.skip("ed_wait_time not in config")
        template_fn = model_templates.get_template("hourly_gamma")
        pdf = _make_batch_df()
        params = {"trials_per_batch": 3, "patients_per_hour": 5}
        result = template_fn(pdf, params)
        assert len(result) == 3 * 24


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterministic:
    @pytest.mark.parametrize("sim_type", _ALL_TYPES)
    def test_same_seed_same_output(self, sim_type):
        """Same seed must produce identical output for any simulation type."""
        template_name = config_loader.get_model_template(sim_type)
        template_fn = model_templates.get_template(template_name)

        params = _get_small_params(sim_type)
        r1 = template_fn(_make_batch_df(seed=42), params)
        r2 = template_fn(_make_batch_df(seed=42), params)
        pd.testing.assert_frame_equal(r1, r2)

    def test_different_seed_different_output(self):
        """Different seeds should produce different output."""
        # Use first available type
        sim_type = _ALL_TYPES[0]
        template_name = config_loader.get_model_template(sim_type)
        template_fn = model_templates.get_template(template_name)
        value_col, _ = config_loader.get_agg_config(sim_type)

        params = _get_small_params(sim_type)
        r1 = template_fn(_make_batch_df(seed=1), params)
        r2 = template_fn(_make_batch_df(seed=2), params)
        assert not r1[value_col].equals(r2[value_col])


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
