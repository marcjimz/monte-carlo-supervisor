"""Registry for Monte Carlo UC functions."""

from .run_simulation import RunSimulationFunction


class MonteCarloRegistry:
    """Central registry for all Monte Carlo UC functions."""

    FUNCTIONS = [
        RunSimulationFunction,
    ]

    def __init__(self, catalog: str, schema: str, mc_job_id: str = ""):
        self.catalog = catalog
        self.schema = schema
        self.mc_job_id = mc_job_id

    def get_all_registration_sql(self) -> list[str]:
        """Generate CREATE FUNCTION SQL for all registered functions."""
        statements = []
        for func_cls in self.FUNCTIONS:
            if hasattr(func_cls, "get_registration_sql"):
                sql = func_cls.get_registration_sql(self.catalog, self.schema, self.mc_job_id)
                statements.append(sql)
        return statements

    def get_all_grant_sql(self, principal: str = "account users") -> list[str]:
        """Generate GRANT EXECUTE SQL for all registered functions."""
        return [
            func_cls.get_grant_sql(self.catalog, self.schema, principal)
            for func_cls in self.FUNCTIONS
            if hasattr(func_cls, "get_grant_sql")
        ]
