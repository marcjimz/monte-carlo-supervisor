"""Configuration loader for Monte Carlo simulation engine.

Loads simulation type definitions from config.yaml. Designed with a future
database backend in mind -- the YAML file can be replaced by a DB table
without changing the public API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_CONFIG: dict | None = None
_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config(config_path: Path | None = None) -> dict:
    """Load and cache simulation config from YAML.

    Parameters
    ----------
    config_path : Path, optional
        Override config file path (useful for testing).
    """
    import yaml  # lazy import — not available on all Databricks runtimes

    global _CONFIG
    path = config_path or _CONFIG_PATH
    if _CONFIG is None or config_path is not None:
        with open(path) as f:
            _CONFIG = yaml.safe_load(f)
    return _CONFIG


def reset_config():
    """Clear cached config (for testing)."""
    global _CONFIG
    _CONFIG = None


def get_valid_types(config: dict | None = None) -> list[str]:
    """Return sorted list of simulation type names from config."""
    cfg = config or load_config()
    return sorted(cfg["simulation_types"].keys())


def get_agg_config(simulation_type: str, config: dict | None = None) -> tuple[str, str]:
    """Return (value_column, group_column) for the given simulation type."""
    cfg = config or load_config()
    sim_config = cfg["simulation_types"].get(simulation_type)
    if sim_config is None:
        available = ", ".join(get_valid_types(cfg))
        raise ValueError(
            f"No config for simulation type '{simulation_type}'. Available: {available}"
        )
    agg = sim_config["aggregation"]
    return agg["value_column"], agg["group_column"]


def get_default_params(simulation_type: str, config: dict | None = None) -> dict[str, Any]:
    """Return default parameter values for the given simulation type."""
    cfg = config or load_config()
    sim_config = cfg["simulation_types"].get(simulation_type)
    if sim_config is None:
        available = ", ".join(get_valid_types(cfg))
        raise ValueError(
            f"No config for simulation type '{simulation_type}'. Available: {available}"
        )
    return {
        name: param["default"]
        for name, param in sim_config.get("parameters", {}).items()
        if "default" in param
    }


def get_schema(simulation_type: str, config: dict | None = None) -> str:
    """Return the Spark DDL schema string for the given simulation type."""
    cfg = config or load_config()
    sim_config = cfg["simulation_types"].get(simulation_type)
    if sim_config is None:
        raise ValueError(f"No config for simulation type '{simulation_type}'")
    return sim_config["schema"]


def get_model_template(simulation_type: str, config: dict | None = None) -> str:
    """Return the model template name for the given simulation type."""
    cfg = config or load_config()
    sim_config = cfg["simulation_types"].get(simulation_type)
    if sim_config is None:
        raise ValueError(f"No config for simulation type '{simulation_type}'")
    return sim_config["model_template"]


def get_all_agg_metrics(simulation_type: str, config: dict | None = None) -> list[tuple[str, str]]:
    """Return all (value_column, group_column) pairs for the given simulation type.

    Includes the primary aggregation metric plus any additional_metrics defined
    in config.yaml.  This is used by results.py to write multiple Gold rows.
    """
    cfg = config or load_config()
    sim_config = cfg["simulation_types"].get(simulation_type)
    if sim_config is None:
        available = ", ".join(get_valid_types(cfg))
        raise ValueError(
            f"No config for simulation type '{simulation_type}'. Available: {available}"
        )
    agg = sim_config["aggregation"]
    metrics = [(agg["value_column"], agg["group_column"])]
    for extra in agg.get("additional_metrics", []):
        metrics.append((extra["value_column"], extra["group_column"]))
    return metrics


def get_required_distributions(simulation_type: str, config: dict | None = None) -> dict[str, dict]:
    """Return ``{dist_name: {description, default_spec}}`` for the given type.

    Returns an empty dict if the simulation type has no ``distributions`` block.
    """
    cfg = config or load_config()
    sim_config = cfg["simulation_types"].get(simulation_type)
    if sim_config is None:
        available = ", ".join(get_valid_types(cfg))
        raise ValueError(
            f"No config for simulation type '{simulation_type}'. Available: {available}"
        )
    return sim_config.get("distributions", {})


def get_default_distribution_specs(simulation_type: str, config: dict | None = None) -> dict[str, dict]:
    """Return ``{dist_name: default_spec}`` for the given type.

    Extracts the ``default_spec`` from each entry in the ``distributions``
    block.  Used when no fitted distribution specs are available.
    """
    dists = get_required_distributions(simulation_type, config)
    return {name: info["default_spec"] for name, info in dists.items()}


def get_sim_type_config(simulation_type: str, config: dict | None = None) -> dict:
    """Return the full config dict for a single simulation type.

    Includes display_name, description, model_template, schema, parameters,
    and aggregation. Used by supervisor.py and examples.py to generate
    dynamic instructions and examples from config.
    """
    cfg = config or load_config()
    sim_config = cfg["simulation_types"].get(simulation_type)
    if sim_config is None:
        available = ", ".join(get_valid_types(cfg))
        raise ValueError(
            f"No config for simulation type '{simulation_type}'. Available: {available}"
        )
    return sim_config
