"""Tests for distribution_sampler — pure Python, no Spark required."""

import numpy as np
import pytest

from src.mc_supervisor.monte_carlo.distribution_sampler import (
    SUPPORTED_TYPES,
    sample_from_spec,
    validate_spec,
)


# ---------------------------------------------------------------------------
# validate_spec
# ---------------------------------------------------------------------------


class TestValidateSpec:
    def test_valid_normal(self):
        validate_spec({"type": "normal", "params": {"loc": 0, "scale": 1}})

    def test_valid_lognormal(self):
        validate_spec({"type": "lognormal", "params": {"mean": 5.0, "sigma": 0.5}})

    def test_valid_beta(self):
        validate_spec({"type": "beta", "params": {"a": 2, "b": 5}})

    def test_valid_gamma(self):
        validate_spec({"type": "gamma", "params": {"shape": 2.0, "scale": 1.0}})

    def test_valid_uniform(self):
        validate_spec({"type": "uniform", "params": {"low": 0, "high": 10}})

    def test_missing_type(self):
        with pytest.raises(ValueError, match="missing required key 'type'"):
            validate_spec({"params": {"loc": 0, "scale": 1}})

    def test_unknown_type(self):
        with pytest.raises(ValueError, match="Unsupported distribution type 'poisson'"):
            validate_spec({"type": "poisson", "params": {"lam": 5}})

    def test_missing_params(self):
        with pytest.raises(ValueError, match="missing required key 'params'"):
            validate_spec({"type": "normal"})

    def test_missing_required_param_keys(self):
        with pytest.raises(ValueError, match="missing required params"):
            validate_spec({"type": "normal", "params": {"loc": 0}})

    def test_params_not_dict(self):
        with pytest.raises(ValueError, match="must be a dict"):
            validate_spec({"type": "normal", "params": [0, 1]})


# ---------------------------------------------------------------------------
# sample_from_spec
# ---------------------------------------------------------------------------


class TestSampleFromSpec:
    def test_normal_shape(self):
        rng = np.random.default_rng(42)
        spec = {"type": "normal", "params": {"loc": 100, "scale": 10}}
        result = sample_from_spec(rng, spec, size=1000)
        assert result.shape == (1000,)

    def test_normal_approximate_mean(self):
        rng = np.random.default_rng(42)
        spec = {"type": "normal", "params": {"loc": 100, "scale": 10}}
        result = sample_from_spec(rng, spec, size=10000)
        assert abs(result.mean() - 100) < 1.0

    def test_lognormal_positive_values(self):
        rng = np.random.default_rng(42)
        spec = {"type": "lognormal", "params": {"mean": 5.0, "sigma": 0.5}}
        result = sample_from_spec(rng, spec, size=1000)
        assert (result > 0).all()

    def test_lognormal_approximate_median(self):
        rng = np.random.default_rng(42)
        spec = {"type": "lognormal", "params": {"mean": 5.0, "sigma": 0.5}}
        result = sample_from_spec(rng, spec, size=10000)
        # Median of lognormal(mu, sigma) = exp(mu)
        expected_median = np.exp(5.0)
        assert abs(np.median(result) - expected_median) / expected_median < 0.05

    def test_beta_values_in_0_1(self):
        rng = np.random.default_rng(42)
        spec = {"type": "beta", "params": {"a": 2, "b": 5}}
        result = sample_from_spec(rng, spec, size=1000)
        assert (result >= 0).all()
        assert (result <= 1).all()

    def test_gamma_positive_values(self):
        rng = np.random.default_rng(42)
        spec = {"type": "gamma", "params": {"shape": 2.0, "scale": 3.0}}
        result = sample_from_spec(rng, spec, size=1000)
        assert (result > 0).all()

    def test_uniform_values_in_range(self):
        rng = np.random.default_rng(42)
        spec = {"type": "uniform", "params": {"low": 5, "high": 15}}
        result = sample_from_spec(rng, spec, size=1000)
        assert (result >= 5).all()
        assert (result <= 15).all()

    def test_default_size_is_one(self):
        rng = np.random.default_rng(42)
        spec = {"type": "normal", "params": {"loc": 0, "scale": 1}}
        result = sample_from_spec(rng, spec)
        assert result.shape == (1,)

    def test_deterministic_same_seed(self):
        spec = {"type": "normal", "params": {"loc": 0, "scale": 1}}
        r1 = sample_from_spec(np.random.default_rng(42), spec, size=100)
        r2 = sample_from_spec(np.random.default_rng(42), spec, size=100)
        np.testing.assert_array_equal(r1, r2)

    def test_different_seeds_different_output(self):
        spec = {"type": "normal", "params": {"loc": 0, "scale": 1}}
        r1 = sample_from_spec(np.random.default_rng(1), spec, size=100)
        r2 = sample_from_spec(np.random.default_rng(2), spec, size=100)
        assert not np.array_equal(r1, r2)
