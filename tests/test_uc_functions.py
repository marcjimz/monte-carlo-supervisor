"""Tests for UC SQL function definitions — pure Python, no Spark required."""

from src.databricks.monte_carlo import config_loader
from src.databricks.sql.functions.monte_carlo.check_simulation import CheckSimulationFunction
from src.databricks.sql.functions.monte_carlo.trigger_simulation import TriggerSimulationFunction
from src.databricks.sql.functions.monte_carlo.registry import MonteCarloRegistry

CATALOG = "test_catalog"
SCHEMA = "test_schema"
JOB_ID = "12345"
CONN_NAME = "test_conn"
VALID_TYPES = config_loader.get_valid_types()


# ---------------------------------------------------------------------------
# CheckSimulationFunction
# ---------------------------------------------------------------------------


class TestCheckSimulationFunction:
    def test_name(self):
        assert CheckSimulationFunction.name == "check_simulation"

    def test_sql_contains_create_function(self):
        sql = CheckSimulationFunction.get_registration_sql(CATALOG, SCHEMA, valid_types=VALID_TYPES)
        assert f"CREATE OR REPLACE FUNCTION {CATALOG}.{SCHEMA}.check_simulation" in sql

    def test_sql_has_four_parameters(self):
        sql = CheckSimulationFunction.get_registration_sql(CATALOG, SCHEMA, valid_types=VALID_TYPES)
        assert "p_simulation_type" in sql
        assert "p_parameters" in sql
        assert "p_num_simulations" in sql
        assert "p_seed" in sql

    def test_sql_does_not_contain_http_request(self):
        """check_simulation must be read-only — no http_request calls."""
        sql = CheckSimulationFunction.get_registration_sql(CATALOG, SCHEMA, valid_types=VALID_TYPES)
        assert "http_request" not in sql

    def test_sql_returns_not_found_status(self):
        sql = CheckSimulationFunction.get_registration_sql(CATALOG, SCHEMA, valid_types=VALID_TYPES)
        assert "not_found" in sql

    def test_sql_returns_failed_status(self):
        """check_simulation should report failed runs instead of not_found."""
        sql = CheckSimulationFunction.get_registration_sql(CATALOG, SCHEMA, valid_types=VALID_TYPES)
        assert '"failed"' in sql or "'FAILED'" in sql

    def test_sql_includes_failed_in_status_filter(self):
        """WHERE clause should include FAILED to prevent infinite re-trigger loops."""
        sql = CheckSimulationFunction.get_registration_sql(CATALOG, SCHEMA, valid_types=VALID_TYPES)
        assert "'FAILED'" in sql

    def test_sql_matches_on_parameters(self):
        """Verify the query filters on parameters, not just simulation_type."""
        sql = CheckSimulationFunction.get_registration_sql(CATALOG, SCHEMA, valid_types=VALID_TYPES)
        # Match is done via aliased column in JOIN ON clause (sim_params)
        # or directly via PARTITION BY (parameters)
        assert "sim_params" in sql or "parameters =" in sql or "parameters=" in sql

    def test_sql_matches_on_seed(self):
        sql = CheckSimulationFunction.get_registration_sql(CATALOG, SCHEMA, valid_types=VALID_TYPES)
        assert "seed =" in sql or "seed=" in sql

    def test_sql_matches_on_num_simulations(self):
        sql = CheckSimulationFunction.get_registration_sql(CATALOG, SCHEMA, valid_types=VALID_TYPES)
        # Match is done via aliased column in JOIN ON clause (sim_num_sims)
        # or directly via PARTITION BY (num_simulations)
        assert "sim_num_sims" in sql or "num_simulations =" in sql or "num_simulations=" in sql

    def test_sql_references_simulation_runs(self):
        sql = CheckSimulationFunction.get_registration_sql(CATALOG, SCHEMA, valid_types=VALID_TYPES)
        assert f"{CATALOG}.{SCHEMA}.simulation_runs" in sql

    def test_sql_references_simulation_results(self):
        sql = CheckSimulationFunction.get_registration_sql(CATALOG, SCHEMA, valid_types=VALID_TYPES)
        assert f"{CATALOG}.{SCHEMA}.simulation_results" in sql

    def test_grant_sql(self):
        sql = CheckSimulationFunction.get_grant_sql(CATALOG, SCHEMA)
        assert f"GRANT EXECUTE ON FUNCTION {CATALOG}.{SCHEMA}.check_simulation" in sql


# ---------------------------------------------------------------------------
# TriggerSimulationFunction
# ---------------------------------------------------------------------------


class TestTriggerSimulationFunction:
    def test_name(self):
        assert TriggerSimulationFunction.name == "trigger_simulation"

    def test_sql_contains_create_function(self):
        sql = TriggerSimulationFunction.get_registration_sql(CATALOG, SCHEMA, JOB_ID, CONN_NAME, valid_types=VALID_TYPES)
        assert f"CREATE OR REPLACE FUNCTION {CATALOG}.{SCHEMA}.trigger_simulation" in sql

    def test_sql_contains_http_request(self):
        sql = TriggerSimulationFunction.get_registration_sql(CATALOG, SCHEMA, JOB_ID, CONN_NAME, valid_types=VALID_TYPES)
        assert "http_request" in sql

    def test_sql_contains_job_id(self):
        sql = TriggerSimulationFunction.get_registration_sql(CATALOG, SCHEMA, JOB_ID, CONN_NAME, valid_types=VALID_TYPES)
        assert JOB_ID in sql

    def test_sql_contains_connection_name(self):
        sql = TriggerSimulationFunction.get_registration_sql(CATALOG, SCHEMA, JOB_ID, CONN_NAME, valid_types=VALID_TYPES)
        assert CONN_NAME in sql

    def test_sql_does_not_query_simulation_tables(self):
        """trigger_simulation should not read simulation_runs or simulation_results."""
        sql = TriggerSimulationFunction.get_registration_sql(CATALOG, SCHEMA, JOB_ID, CONN_NAME, valid_types=VALID_TYPES)
        assert "simulation_runs" not in sql
        assert "simulation_results" not in sql

    def test_sql_returns_triggered_status(self):
        sql = TriggerSimulationFunction.get_registration_sql(CATALOG, SCHEMA, JOB_ID, CONN_NAME, valid_types=VALID_TYPES)
        assert "triggered" in sql

    def test_grant_sql(self):
        sql = TriggerSimulationFunction.get_grant_sql(CATALOG, SCHEMA)
        assert f"GRANT EXECUTE ON FUNCTION {CATALOG}.{SCHEMA}.trigger_simulation" in sql


# ---------------------------------------------------------------------------
# Registry with new functions
# ---------------------------------------------------------------------------


class TestRegistryWithNewFunctions:
    def test_registry_has_three_functions(self):
        registry = MonteCarloRegistry(CATALOG, SCHEMA, JOB_ID, CONN_NAME)
        assert len(registry.FUNCTIONS) == 3

    def test_registry_function_names(self):
        registry = MonteCarloRegistry(CATALOG, SCHEMA, JOB_ID, CONN_NAME)
        names = {f.name for f in registry.FUNCTIONS}
        assert names == {"check_simulation", "trigger_simulation", "list_distributions"}

    def test_registration_sql_returns_three_statements(self):
        registry = MonteCarloRegistry(CATALOG, SCHEMA, JOB_ID, CONN_NAME)
        stmts = registry.get_all_registration_sql()
        assert len(stmts) == 3

    def test_grant_sql_returns_three_statements(self):
        registry = MonteCarloRegistry(CATALOG, SCHEMA, JOB_ID, CONN_NAME)
        stmts = registry.get_all_grant_sql()
        assert len(stmts) == 3

    def test_deprecated_functions_includes_run_simulation(self):
        registry = MonteCarloRegistry(CATALOG, SCHEMA, JOB_ID, CONN_NAME)
        deprecated = registry.get_deprecated_function_names()
        assert "run_simulation" in deprecated

    def test_deprecated_functions_not_in_active(self):
        registry = MonteCarloRegistry(CATALOG, SCHEMA, JOB_ID, CONN_NAME)
        active_names = {f.name for f in registry.FUNCTIONS}
        for deprecated_name in registry.get_deprecated_function_names():
            assert deprecated_name not in active_names
