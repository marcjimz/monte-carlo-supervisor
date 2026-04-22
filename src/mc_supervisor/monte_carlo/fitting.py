"""Distribution fitting utilities for Monte Carlo simulations.

Uses scipy for offline fitting — only imported in setup notebooks, never at
simulation runtime. Fits distributions to historical data and returns spec
dicts compatible with ``distribution_sampler.sample_from_spec()``.
"""

from __future__ import annotations

import numpy as np

from .distribution_sampler import SUPPORTED_TYPES


def fit_normal(data: np.ndarray) -> dict:
    """Fit a normal distribution and return spec + metadata."""
    from scipy import stats

    loc, scale = stats.norm.fit(data)
    ks_stat, p_value = stats.kstest(data, "norm", args=(loc, scale))
    return {
        "spec": {"type": "normal", "params": {"loc": float(loc), "scale": float(scale)}},
        "metadata": {
            "n_samples": len(data),
            "ks_statistic": float(ks_stat),
            "p_value": float(p_value),
        },
    }


def fit_lognormal(data: np.ndarray) -> dict:
    """Fit a lognormal distribution and return spec + metadata.

    numpy's lognormal uses ``mean`` and ``sigma`` (of the underlying normal),
    which is what scipy's ``lognorm`` shape/loc/scale parameterization maps to.
    """
    from scipy import stats

    # Filter to positive values only
    pos_data = data[data > 0]
    if len(pos_data) == 0:
        raise ValueError("Cannot fit lognormal: no positive values in data")

    shape, loc, scale = stats.lognorm.fit(pos_data, floc=0)
    # scipy's lognorm: shape=sigma, scale=exp(mu) => mu=log(scale), sigma=shape
    mu = float(np.log(scale))
    sigma = float(shape)

    ks_stat, p_value = stats.kstest(pos_data, "lognorm", args=(shape, loc, scale))
    return {
        "spec": {"type": "lognormal", "params": {"mean": mu, "sigma": sigma}},
        "metadata": {
            "n_samples": len(pos_data),
            "ks_statistic": float(ks_stat),
            "p_value": float(p_value),
        },
    }


def fit_beta(data: np.ndarray) -> dict:
    """Fit a beta distribution and return spec + metadata."""
    from scipy import stats

    # Clip to (0, 1) for beta fitting
    clipped = np.clip(data, 1e-10, 1 - 1e-10)
    a, b, loc, scale = stats.beta.fit(clipped, floc=0, fscale=1)

    ks_stat, p_value = stats.kstest(clipped, "beta", args=(a, b, loc, scale))
    return {
        "spec": {"type": "beta", "params": {"a": float(a), "b": float(b)}},
        "metadata": {
            "n_samples": len(clipped),
            "ks_statistic": float(ks_stat),
            "p_value": float(p_value),
        },
    }


def fit_gamma(data: np.ndarray) -> dict:
    """Fit a gamma distribution and return spec + metadata."""
    from scipy import stats

    pos_data = data[data > 0]
    if len(pos_data) == 0:
        raise ValueError("Cannot fit gamma: no positive values in data")

    shape, loc, scale = stats.gamma.fit(pos_data, floc=0)

    ks_stat, p_value = stats.kstest(pos_data, "gamma", args=(shape, loc, scale))
    return {
        "spec": {"type": "gamma", "params": {"shape": float(shape), "scale": float(scale)}},
        "metadata": {
            "n_samples": len(pos_data),
            "ks_statistic": float(ks_stat),
            "p_value": float(p_value),
        },
    }


_FITTERS = {
    "normal": fit_normal,
    "lognormal": fit_lognormal,
    "beta": fit_beta,
    "gamma": fit_gamma,
}


def fit_distribution(data: np.ndarray, dist_type: str) -> dict:
    """Fit a specific distribution type to data.

    Parameters
    ----------
    data : np.ndarray
        1-D array of observed values.
    dist_type : str
        One of ``"normal"``, ``"lognormal"``, ``"beta"``, ``"gamma"``.

    Returns
    -------
    dict
        ``{"spec": {...}, "metadata": {...}}``
    """
    if dist_type not in _FITTERS:
        raise ValueError(
            f"No fitter for distribution type '{dist_type}'. "
            f"Available: {', '.join(sorted(_FITTERS.keys()))}"
        )
    return _FITTERS[dist_type](data)


def auto_fit(data: np.ndarray) -> dict:
    """Try multiple distributions and return the best fit by KS test.

    Tries normal, lognormal, gamma (and beta if data is in [0, 1]).
    Returns the fit with the lowest KS statistic.
    """
    candidates = ["normal", "lognormal", "gamma"]
    if np.all((data >= 0) & (data <= 1)):
        candidates.append("beta")

    best = None
    for dist_type in candidates:
        try:
            result = fit_distribution(data, dist_type)
            if best is None or result["metadata"]["ks_statistic"] < best["metadata"]["ks_statistic"]:
                best = result
        except (ValueError, RuntimeError):
            continue

    if best is None:
        raise ValueError("Could not fit any distribution to the provided data")
    return best
