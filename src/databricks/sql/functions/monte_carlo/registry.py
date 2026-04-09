"""Registry for Monte Carlo UC functions."""

from .check_simulation import CheckSimulationFunction
from .run_simulation import RunSimulationFunction
from .trigger_simulation import TriggerSimulationFunction


class MonteCarloRegistry:
    """Central registry for all Monte Carlo UC functions."""

    FUNCTIONS = [
        CheckSimulationFunction,
        TriggerSimulationFunction,
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
    ):
        self.catalog = catalog
        self.schema = schema
        self.mc_job_id = mc_job_id
        self.connection_name = connection_name

    def get_all_registration_sql(self) -> list[str]:
        """Generate CREATE FUNCTION SQL for all registered functions."""
        statements = []
        for func_cls in self.FUNCTIONS:
            if hasattr(func_cls, "get_registration_sql"):
                sql = func_cls.get_registration_sql(
                    self.catalog, self.schema, self.mc_job_id, self.connection_name
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
