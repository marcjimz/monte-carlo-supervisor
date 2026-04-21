"""Registry for Monte Carlo UC functions."""

from .check_simulation import CheckSimulationFunction
from .create_matrix import CreateMatrixFunction
from .list_distributions import ListDistributionsFunction
from .run_simulation import RunSimulationFunction
from .trigger_simulation import TriggerSimulationFunction

_valid_types_cache: list[str] | None = None


def _load_valid_types() -> list[str]:
    """Load simulation type names from config.yaml (single source of truth)."""
    global _valid_types_cache
    if _valid_types_cache is None:
        from src.databricks.monte_carlo import config_loader
        _valid_types_cache = config_loader.get_valid_types()
    return _valid_types_cache


class MonteCarloRegistry:
    """Central registry for all Monte Carlo UC functions."""

    FUNCTIONS = [
        CheckSimulationFunction,
        TriggerSimulationFunction,
        CreateMatrixFunction,
        ListDistributionsFunction,
    ]

    DEPRECATED_FUNCTIONS = [
        RunSimulationFunction,
    ]

    def __init__(
        self,
        catalog: str,
        schema: str,
        mc_job_id: str = "",
        connection_name: str = "monte_carlo_ws",
        valid_types: list[str] | None = None,
    ):
        self.catalog = catalog
        self.schema = schema
        self.mc_job_id = mc_job_id
        self.connection_name = connection_name
        self.valid_types = valid_types or _load_valid_types()

    def get_all_registration_sql(self) -> list[str]:
        """Generate CREATE FUNCTION SQL for all registered functions."""
        statements = []
        for func_cls in self.FUNCTIONS:
            if hasattr(func_cls, "get_registration_sql"):
                sql = func_cls.get_registration_sql(
                    self.catalog, self.schema, self.mc_job_id, self.connection_name,
                    valid_types=self.valid_types,
                )
                statements.append(sql)
        return statements

    def get_all_grant_sql(self, principal: str = "account users") -> list[str]:
        """Generate GRANT EXECUTE SQL for all registered functions."""
        return [
            func_cls.get_grant_sql(self.catalog, self.schema, principal)
            for func_cls in self.FUNCTIONS
            if hasattr(func_cls, "get_grant_sql")
        ]

    def get_deprecated_function_names(self) -> list[str]:
        """Return names of deprecated functions that should be dropped during migration."""
        return [f.name for f in self.DEPRECATED_FUNCTIONS]
