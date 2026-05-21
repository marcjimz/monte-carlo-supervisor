"""DEPRECATED: Superseded by check_simulation + trigger_simulation.

The single-function approach had two bugs:
  1. Spark SQL doesn't short-circuit CASE for ``http_request()`` —
     spurious Spark jobs were triggered even when cached results existed.
  2. Matched on ``simulation_type`` only, not actual parameters.

Kept for backward compatibility reference. The ``MonteCarloRegistry``
no longer includes this function in its active FUNCTIONS list.
"""


class RunSimulationFunction:
    """UC SQL Function that checks cache, triggers Spark jobs, and returns results."""

    name = "run_simulation"

    @classmethod
    def _description(cls, types_str: str) -> str:
        return (
            "Runs Monte Carlo simulations using a distributed Spark pipeline. "
            "Returns cached results instantly if a matching completed run exists, "
            "otherwise triggers a new Spark job (10,000 trials across multiple nodes). "
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
            -- Invalid simulation type
            WHEN p_simulation_type NOT IN ({not_in_str})
            THEN '{{"error":"Invalid simulation_type. Must be one of: {types_str}"}}'

            -- Completed results available — return Gold data
            WHEN latest.run_status = 'COMPLETED' AND latest.run_id IS NOT NULL
            THEN concat(
                '{{"status":"completed","run_id":"', latest.run_id,
                '","simulation_type":"', p_simulation_type,
                '","num_simulations":', CAST(COALESCE(latest.run_num_sims, COALESCE(p_num_simulations, 10000)) AS STRING),
                ',"seed":', CAST(COALESCE(latest.run_seed, COALESCE(p_seed, 42)) AS STRING),
                ',"results":',
                COALESCE(res.results_json, '[]'),
                '}}'
            )

            -- Simulation is currently running
            WHEN latest.run_status = 'RUNNING' AND latest.run_id IS NOT NULL
            THEN concat(
                '{{"status":"running","simulation_type":"', p_simulation_type,
                '","run_id":"', latest.run_id,
                '","message":"A distributed Spark Monte Carlo simulation is currently running. ',
                'Please call this function again with the same parameters to check for completion."}}'
            )

            -- No completed or running run — trigger a new Spark job
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
                'Please call this function again with the same parameters to check for completion."}}'
            )
        END
    FROM (SELECT 1 AS x) dummy
    LEFT JOIN (
        SELECT run_id, simulation_type AS sim_type, status AS run_status,
               seed AS run_seed, num_simulations AS run_num_sims,
               ROW_NUMBER() OVER (PARTITION BY simulation_type ORDER BY created_at DESC) AS rn
        FROM {catalog}.{schema}.simulation_runs
        WHERE status IN ('COMPLETED', 'RUNNING')
    ) latest ON latest.sim_type = p_simulation_type AND latest.rn = 1
    LEFT JOIN (
        SELECT r.run_id,
            to_json(collect_list(
                named_struct(
                    'simulation_type', r.simulation_type,
                    'metric_name', r.metric_name,
                    'group_key', r.group_key,
                    'group_value', r.group_value,
                    'mean_value', r.mean_value,
                    'std_value', r.std_value,
                    'p05', r.p05,
                    'p10', r.p10,
                    'p25', r.p25,
                    'p50', r.p50,
                    'p75', r.p75,
                    'p90', r.p90,
                    'p95', r.p95
                )
            )) AS results_json
        FROM {catalog}.{schema}.simulation_results r
        GROUP BY r.run_id
    ) res ON res.run_id = latest.run_id
    LIMIT 1
);"""

    @classmethod
    def get_grant_sql(cls, catalog: str, schema: str, principal: str = "account users") -> str:
        return f"GRANT EXECUTE ON FUNCTION {catalog}.{schema}.{cls.name} TO `{principal}`;"
