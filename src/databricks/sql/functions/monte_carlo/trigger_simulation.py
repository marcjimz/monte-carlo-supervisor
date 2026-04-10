"""UC Function definition for trigger_simulation — triggers a Spark simulation job.

Calls ``http_request()`` via a UC HTTP Connection to POST to the
Databricks Jobs API ``/api/2.1/jobs/run-now``.  This function performs
**no table reads** — it only fires the job and returns the API response.

Separated from the old ``run_simulation`` to avoid Spark SQL evaluating
``http_request()`` in non-matching CASE branches.
"""


class TriggerSimulationFunction:
    """UC SQL Function that triggers a distributed Spark Monte Carlo simulation job."""

    name = "trigger_simulation"

    @classmethod
    def _description(cls, types_str: str) -> str:
        return (
            "Triggers a new distributed Spark Monte Carlo simulation job with "
            "10,000+ trials across multiple nodes. The job runs 5-10 minutes. "
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
        connection_name: str = "monte_carlo_ws",
        valid_types: list[str] | None = None,
    ) -> str:
        if valid_types is None:
            valid_types = ["ed_wait_time", "length_of_stay", "patient_volume", "readmission_rate", "revenue"]
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
                '{{"status":"triggered","simulation_type":"', p_simulation_type,
                '","parameters":', COALESCE(p_parameters, '{{}}'),
                ',"num_simulations":', CAST(COALESCE(p_num_simulations, 10000) AS STRING),
                ',"seed":', CAST(COALESCE(p_seed, 42) AS STRING),
                ',"job_response":',
                (http_request(
                    conn => '{connection_name}',
                    method => 'POST',
                    path => '/api/2.1/jobs/run-now',
                    json => to_json(named_struct(
                        'job_id', CAST({mc_job_id} AS BIGINT),
                        'job_parameters', named_struct(
                            'simulation_type', p_simulation_type,
                            'parameters', COALESCE(p_parameters, '{{}}'),
                            'num_simulations', CAST(COALESCE(p_num_simulations, 10000) AS STRING),
                            'seed', CAST(COALESCE(p_seed, 42) AS STRING)
                        )
                    ))
                )).text,
                ',"message":"Distributed Spark Monte Carlo simulation triggered. ',
                'The job runs ~5-10 minutes with ', CAST(COALESCE(p_num_simulations, 10000) AS STRING), ' trials across multiple Spark executors. ',
                'Call check_simulation with the same parameters to poll for completion."}}'
            )
        END
);"""

    @classmethod
    def get_grant_sql(cls, catalog: str, schema: str, principal: str = "account users") -> str:
        return f"GRANT EXECUTE ON FUNCTION {catalog}.{schema}.{cls.name} TO `{principal}`;"
