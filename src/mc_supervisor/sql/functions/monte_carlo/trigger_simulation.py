"""UC Function definition for trigger_simulation — submits via App endpoint.

Calls ``http_request()`` via a UC HTTP Connection to POST to the
Databricks App's ``/api/simulations/internal/submit-simulation`` endpoint.
The App writes a SUBMITTED row to Delta, which triggers the pipeline
via a table-update trigger.

This avoids the workspace IP ACL issue where the SQL warehouse's egress
IP is not in the workspace allow-list (the App URL is on
``*.databricksapps.com`` — outside workspace IP ACL).
"""


class TriggerSimulationFunction:
    """UC SQL Function that triggers a Monte Carlo simulation via the App endpoint."""

    name = "trigger_simulation"

    @classmethod
    def _description(cls, types_str: str) -> str:
        return (
            "Triggers a Monte Carlo simulation by submitting to the App endpoint. "
            "The simulation pipeline starts within ~2 minutes via table trigger. "
            "Only call this when check_simulation returns not_found. "
            "After triggering, call check_simulation to poll for completion. "
            f"Supports: {types_str}."
        )

    @classmethod
    def get_registration_sql(
        cls,
        catalog: str,
        schema: str,
        mc_job_id: str = "0",
        connection_name: str = "monte_carlo_app",
        valid_types: list[str] | None = None,
    ) -> str:
        if valid_types is None:
            raise ValueError("valid_types is required — load from config_loader.get_valid_types()")
        types_str = ", ".join(sorted(valid_types))
        not_in_str = ", ".join(f"'{t}'" for t in sorted(valid_types))
        description = cls._description(types_str)
        return f"""
CREATE OR REPLACE FUNCTION {catalog}.{schema}.{cls.name}(
    p_simulation_type STRING COMMENT 'One of: {types_str}',
    p_parameters STRING COMMENT 'JSON parameters for the simulation, e.g. {{"monthly_mean": 10000, "num_months": 6}}',
    p_num_simulations INT COMMENT 'Number of Monte Carlo trials (default: 10000)',
    p_seed INT COMMENT 'Random seed for reproducibility (default: 42)'
)
RETURNS STRING
LANGUAGE SQL
COMMENT '{description}'
RETURN (
    SELECT
        CASE
            WHEN p_simulation_type NOT IN ({not_in_str})
            THEN '{{"error":"Invalid simulation_type. Must be one of: {types_str}"}}'
            ELSE concat(
                '{{"status":"submitted","simulation_type":"', p_simulation_type,
                '","parameters":', COALESCE(p_parameters, '{{}}'),
                ',"num_simulations":', CAST(COALESCE(p_num_simulations, 10000) AS STRING),
                ',"seed":', CAST(COALESCE(p_seed, 42) AS STRING),
                ',"app_response":',
                (http_request(
                    conn => '{connection_name}',
                    method => 'POST',
                    path => '/api/simulations/internal/submit-simulation',
                    json => to_json(named_struct(
                        'simulation_type', p_simulation_type,
                        'parameters', COALESCE(p_parameters, '{{}}'),
                        'num_simulations', CAST(COALESCE(p_num_simulations, 10000) AS STRING),
                        'seed', CAST(COALESCE(p_seed, 42) AS STRING)
                    ))
                )).text,
                ',"message":"Simulation queued. The pipeline starts within ~2 minutes via table trigger. ',
                'Call check_simulation with the same parameters to poll for completion."}}'
            )
        END
);"""

    @classmethod
    def get_grant_sql(cls, catalog: str, schema: str, principal: str = "account users") -> str:
        return f"GRANT EXECUTE ON FUNCTION {catalog}.{schema}.{cls.name} TO `{principal}`;"
