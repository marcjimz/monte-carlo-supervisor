"""UC Function definition for list_distributions — distribution catalog discovery.

Returns fitted distribution specs from the ``distribution_specs`` table so that
the MAS agent can discover what distributions are available, their parameters,
and goodness-of-fit metrics.
"""


class ListDistributionsFunction:
    """UC SQL Function that lists available fitted distribution specs."""

    name = "list_distributions"

    @classmethod
    def _description(cls) -> str:
        return (
            "Lists available fitted distribution specs for simulation types. "
            "Returns distribution parameters, version, and goodness-of-fit metrics. "
            "Optionally filter by simulation_type. Returns the latest version only."
        )

    @classmethod
    def get_registration_sql(
        cls,
        catalog: str,
        schema: str,
        mc_job_id: str = "0",
        connection_name: str = "monte_carlo_ws",
        valid_types: list[str] | None = None,
    ) -> str:
        # mc_job_id, connection_name, valid_types accepted for registry API compat.
        description = cls._description()
        return f"""
CREATE OR REPLACE FUNCTION {catalog}.{schema}.{cls.name}(
    p_simulation_type STRING COMMENT 'Optional: filter by simulation type. Pass NULL or empty string to list all.'
)
RETURNS STRING
LANGUAGE SQL
COMMENT '{description}'
RETURN (
    SELECT to_json(collect_list(
        named_struct(
            'simulation_type', d.simulation_type,
            'distribution_name', d.distribution_name,
            'version', d.version,
            'spec', d.spec,
            'fit_metadata', d.fit_metadata,
            'created_at', d.created_at
        )
    ))
    FROM {catalog}.{schema}.distribution_specs d
    INNER JOIN (
        SELECT simulation_type, MAX(version) AS max_version
        FROM {catalog}.{schema}.distribution_specs
        GROUP BY simulation_type
    ) latest ON d.simulation_type = latest.simulation_type
           AND d.version = latest.max_version
    WHERE (p_simulation_type IS NULL
           OR p_simulation_type = ''
           OR d.simulation_type = p_simulation_type)
);"""

    @classmethod
    def get_grant_sql(cls, catalog: str, schema: str, principal: str = "account users") -> str:
        return f"GRANT EXECUTE ON FUNCTION {catalog}.{schema}.{cls.name} TO `{principal}`;"
