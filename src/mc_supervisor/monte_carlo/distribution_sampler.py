"""Pure numpy distribution sampling utility for Monte Carlo simulations.

Dispatches to numpy Generator methods at simulation time — no scipy dependency.
Distribution specs are dicts with ``type`` and ``params`` keys, e.g.::

    {"type": "lognormal", "params": {"mean": 7.09, "sigma": 0.22}}
"""

from __future__ import annotations

import numpy as np

SUPPORTED_TYPES = {"normal", "lognormal", "beta", "gamma", "uniform"}

# Required parameter keys per distribution type
_REQUIRED_PARAMS: dict[str, set[str]] = {
    "normal": {"loc", "scale"},
    "lognormal": {"mean", "sigma"},
    "beta": {"a", "b"},
    "gamma": {"shape", "scale"},
    "uniform": {"low", "high"},
}


def validate_spec(spec: dict) -> None:
    """Raise ``ValueError`` if *spec* is malformed.

    A valid spec must have:
    - ``type`` key with a value in :data:`SUPPORTED_TYPES`
    - ``params`` key with a dict containing the required parameter keys
      for that distribution type
    """
    if "type" not in spec:
        raise ValueError("Distribution spec missing required key 'type'")
    dist_type = spec["type"]
    if dist_type not in SUPPORTED_TYPES:
        raise ValueError(
            f"Unsupported distribution type '{dist_type}'. "
            f"Must be one of: {', '.join(sorted(SUPPORTED_TYPES))}"
        )
    if "params" not in spec:
        raise ValueError("Distribution spec missing required key 'params'")
    params = spec["params"]
    if not isinstance(params, dict):
        raise ValueError(f"Distribution spec 'params' must be a dict, got {type(params).__name__}")
    required = _REQUIRED_PARAMS[dist_type]
    missing = required - set(params.keys())
    if missing:
        raise ValueError(
            f"Distribution type '{dist_type}' missing required params: {', '.join(sorted(missing))}. "
            f"Required: {', '.join(sorted(required))}"
        )


def sample_from_spec(rng: np.random.Generator, spec: dict, size: int = 1) -> np.ndarray:
    """Draw *size* samples from the distribution described by *spec*.

    Parameters
    ----------
    rng : numpy.random.Generator
        Seeded random number generator.
    spec : dict
        Distribution specification with ``type`` and ``params`` keys.
    size : int
        Number of samples to draw (default 1).

    Returns
    -------
    numpy.ndarray
        Array of shape ``(size,)`` with drawn samples.
    """
    validate_spec(spec)
    dist_type = spec["type"]
    p = spec["params"]

    if dist_type == "normal":
        return rng.normal(loc=p["loc"], scale=p["scale"], size=size)
    elif dist_type == "lognormal":
        return rng.lognormal(mean=p["mean"], sigma=p["sigma"], size=size)
    elif dist_type == "beta":
        return rng.beta(a=p["a"], b=p["b"], size=size)
    elif dist_type == "gamma":
        return rng.gamma(shape=p["shape"], scale=p["scale"], size=size)
    elif dist_type == "uniform":
        return rng.uniform(low=p["low"], high=p["high"], size=size)
    else:
        raise ValueError(f"Unsupported distribution type '{dist_type}'")
