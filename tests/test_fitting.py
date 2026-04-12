"""Tests for distribution fitting — requires scipy."""

import numpy as np
import pytest

from src.databricks.monte_carlo.fitting import (
    auto_fit,
    fit_beta,
    fit_distribution,
    fit_lognormal,
    fit_normal,
)


class TestFitNormal:
    def test_fitted_params_close_to_true(self):
        rng = np.random.default_rng(42)
        data = rng.normal(loc=100, scale=15, size=5000)
        result = fit_normal(data)
        spec = result["spec"]
        assert spec["type"] == "normal"
        assert abs(spec["params"]["loc"] - 100) < 2.0
        assert abs(spec["params"]["scale"] - 15) < 2.0

    def test_metadata_fields(self):
        rng = np.random.default_rng(42)
        data = rng.normal(loc=0, scale=1, size=1000)
        result = fit_normal(data)
        meta = result["metadata"]
        assert "n_samples" in meta
        assert "ks_statistic" in meta
        assert "p_value" in meta
        assert meta["n_samples"] == 1000


class TestFitLognormal:
    def test_fitted_params_close_to_true(self):
        rng = np.random.default_rng(42)
        # Generate lognormal with mu=5.0, sigma=0.5
        data = rng.lognormal(mean=5.0, sigma=0.5, size=5000)
        result = fit_lognormal(data)
        spec = result["spec"]
        assert spec["type"] == "lognormal"
        assert abs(spec["params"]["mean"] - 5.0) < 0.2
        assert abs(spec["params"]["sigma"] - 0.5) < 0.1

    def test_rejects_non_positive_data(self):
        with pytest.raises(ValueError, match="no positive values"):
            fit_lognormal(np.array([-1.0, -2.0, -3.0]))


class TestFitBeta:
    def test_fitted_params_close_to_true(self):
        rng = np.random.default_rng(42)
        data = rng.beta(a=2, b=5, size=5000)
        result = fit_beta(data)
        spec = result["spec"]
        assert spec["type"] == "beta"
        assert abs(spec["params"]["a"] - 2.0) < 0.5
        assert abs(spec["params"]["b"] - 5.0) < 1.0


class TestAutoFit:
    def test_selects_normal_for_normal_data(self):
        rng = np.random.default_rng(42)
        data = rng.normal(loc=50, scale=5, size=5000)
        result = auto_fit(data)
        # Should be either normal or lognormal (both can fit symmetric data)
        assert result["spec"]["type"] in ("normal", "lognormal", "gamma")

    def test_selects_beta_for_0_1_data(self):
        rng = np.random.default_rng(42)
        data = rng.beta(a=2, b=5, size=5000)
        result = auto_fit(data)
        # Beta should be tried and likely win for data confined to [0, 1]
        assert result["spec"]["type"] == "beta"

    def test_ks_statistic_reasonable(self):
        """For correctly-distributed data, p-value should be > 0.05."""
        rng = np.random.default_rng(42)
        data = rng.normal(loc=100, scale=10, size=2000)
        result = fit_normal(data)
        assert result["metadata"]["p_value"] > 0.05


class TestFitDistribution:
    def test_dispatches_to_correct_fitter(self):
        rng = np.random.default_rng(42)
        data = rng.normal(loc=0, scale=1, size=1000)
        result = fit_distribution(data, "normal")
        assert result["spec"]["type"] == "normal"

    def test_raises_for_unknown_type(self):
        with pytest.raises(ValueError, match="No fitter"):
            fit_distribution(np.array([1, 2, 3]), "uniform")
