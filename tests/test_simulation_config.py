"""Tests for config.yaml, config_loader, and model_templates — pure Python, no Spark required.

Validates that config.yaml is well-formed, all model templates are registered,
aggregation columns match schemas, and config_loader functions return correct data.
"""

import pytest

from src.databricks.monte_carlo import config_loader, model_templates


# ---------------------------------------------------------------------------
# Config structure validation
# ---------------------------------------------------------------------------


class TestConfigStructure:
    """Validate config.yaml has all required keys for every simulation type."""

    @pytest.fixture(autouse=True)
    def _load_config(self):
        config_loader.reset_config()
        self.config = config_loader.load_config()

    def test_has_simulation_types(self):
        assert "simulation_types" in self.config
        assert len(self.config["simulation_types"]) > 0

    def test_has_version(self):
        assert "version" in self.config

    @pytest.mark.parametrize(
        "required_key",
        ["model_template", "schema", "parameters", "aggregation"],
    )
    def test_every_type_has_required_keys(self, required_key):
        for sim_type, sim_config in self.config["simulation_types"].items():
            assert required_key in sim_config, (
                f"Simulation type '{sim_type}' missing required key '{required_key}'"
            )

    def test_aggregation_has_value_and_group_columns(self):
        for sim_type, sim_config in self.config["simulation_types"].items():
            agg = sim_config["aggregation"]
            assert "value_column" in agg, f"'{sim_type}' aggregation missing value_column"
            assert "group_column" in agg, f"'{sim_type}' aggregation missing group_column"


# ---------------------------------------------------------------------------
# Model templates registration
# ---------------------------------------------------------------------------


class TestModelTemplateRegistration:
    """Verify every config model_template maps to a registered Python function."""

    @pytest.fixture(autouse=True)
    def _load_config(self):
        config_loader.reset_config()
        self.config = config_loader.load_config()

    def test_every_template_is_registered(self):
        for sim_type, sim_config in self.config["simulation_types"].items():
            template_name = sim_config["model_template"]
            fn = model_templates.get_template(template_name)
            assert callable(fn), (
                f"Template '{template_name}' for '{sim_type}' is not callable"
            )

    def test_no_duplicate_template_names(self):
        """Each template should be unique (no accidental overwrites)."""
        templates = model_templates.get_available_templates()
        assert len(templates) == len(set(templates))


# ---------------------------------------------------------------------------
# Schema / aggregation consistency
# ---------------------------------------------------------------------------


class TestSchemaAggregationConsistency:
    """Ensure aggregation columns appear in their simulation type's schema string."""

    @pytest.fixture(autouse=True)
    def _load_config(self):
        config_loader.reset_config()
        self.config = config_loader.load_config()

    def test_value_column_in_schema(self):
        for sim_type, sim_config in self.config["simulation_types"].items():
            schema = sim_config["schema"]
            value_col = sim_config["aggregation"]["value_column"]
            assert value_col in schema, (
                f"'{sim_type}' value_column '{value_col}' not found in schema: {schema}"
            )

    def test_group_column_in_schema(self):
        for sim_type, sim_config in self.config["simulation_types"].items():
            schema = sim_config["schema"]
            group_col = sim_config["aggregation"]["group_column"]
            assert group_col in schema, (
                f"'{sim_type}' group_column '{group_col}' not found in schema: {schema}"
            )


# ---------------------------------------------------------------------------
# Config loader functions
# ---------------------------------------------------------------------------


class TestConfigLoader:
    """Test config_loader public API."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        config_loader.reset_config()

    def test_get_valid_types_returns_sorted_list(self):
        types = config_loader.get_valid_types()
        assert types == sorted(types)
        assert len(types) > 0

    def test_get_valid_types_matches_config_keys(self):
        config = config_loader.load_config()
        expected = sorted(config["simulation_types"].keys())
        assert config_loader.get_valid_types() == expected

    def test_get_agg_config_returns_tuple(self):
        for sim_type in config_loader.get_valid_types():
            result = config_loader.get_agg_config(sim_type)
            assert isinstance(result, tuple)
            assert len(result) == 2
            assert all(isinstance(s, str) for s in result)

    def test_get_agg_config_raises_for_unknown(self):
        with pytest.raises(ValueError, match="No config"):
            config_loader.get_agg_config("nonexistent_type")

    def test_get_default_params_returns_dict(self):
        for sim_type in config_loader.get_valid_types():
            params = config_loader.get_default_params(sim_type)
            assert isinstance(params, dict)
            assert len(params) > 0

    def test_get_default_params_raises_for_unknown(self):
        with pytest.raises(ValueError, match="No config"):
            config_loader.get_default_params("nonexistent_type")

    def test_get_schema_returns_string(self):
        for sim_type in config_loader.get_valid_types():
            schema = config_loader.get_schema(sim_type)
            assert isinstance(schema, str)
            assert len(schema) > 0

    def test_get_model_template_returns_string(self):
        for sim_type in config_loader.get_valid_types():
            template = config_loader.get_model_template(sim_type)
            assert isinstance(template, str)
            assert len(template) > 0

    def test_reset_config_clears_cache(self):
        config_loader.load_config()
        config_loader.reset_config()
        # After reset, next load should re-read from file
        config = config_loader.load_config()
        assert "simulation_types" in config


# ---------------------------------------------------------------------------
# UC Function valid_types integration
# ---------------------------------------------------------------------------


class TestUCFunctionValidTypes:
    """Verify UC SQL functions accept and use valid_types from config."""

    def test_check_simulation_uses_custom_types(self):
        from src.databricks.sql.functions.monte_carlo.check_simulation import CheckSimulationFunction

        custom_types = ["alpha", "beta"]
        sql = CheckSimulationFunction.get_registration_sql(
            "cat", "sch", valid_types=custom_types,
        )
        assert "'alpha'" in sql
        assert "'beta'" in sql

    def test_trigger_simulation_uses_custom_types(self):
        from src.databricks.sql.functions.monte_carlo.trigger_simulation import TriggerSimulationFunction

        custom_types = ["gamma", "delta"]
        sql = TriggerSimulationFunction.get_registration_sql(
            "cat", "sch", valid_types=custom_types,
        )
        assert "'delta'" in sql
        assert "'gamma'" in sql

    def test_registry_passes_valid_types(self):
        from src.databricks.sql.functions.monte_carlo.registry import MonteCarloRegistry

        custom_types = ["foo", "bar"]
        registry = MonteCarloRegistry("cat", "sch", "123", "conn", valid_types=custom_types)
        stmts = registry.get_all_registration_sql()
        for sql in stmts:
            assert "'bar'" in sql
            assert "'foo'" in sql
