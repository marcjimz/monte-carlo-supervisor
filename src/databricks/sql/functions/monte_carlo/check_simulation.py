"""UC Function definition for check_simulation — read-only cache lookup.

Checks ``simulation_runs`` for a matching completed or running simulation
and returns Gold results if available.  This function performs **no side
effects** — it never triggers jobs or writes data.

Separated from the old ``run_simulation`` to avoid Spark SQL evaluating
``http_request()`` in non-matching CASE branches.
"""


class CheckSimulationFunction:
    """UC SQL Function that checks simulation cache by exact parameter match."""

    name = "check_simulation"

    @classmethod
    def _description(cls, types_str: str) -> str:
        return (
            "Checks whether a Monte Carlo simulation has completed results for the "
            "given parameters. Returns cached results instantly if a matching "
            "completed run exists, running if a job is in progress, or "
            "not_found if no matching run exists. Read-only -- never starts jobs. "
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
        # mc_job_id and connection_name accepted for registry API compat but unused.
        if valid_types is None:
            raise ValueError("valid_types is required — load from config_loader.get_valid_types()")
        types_str = ", ".join(sorted(valid_types))
        not_in_str = ", ".join(f"'{t}'" for t in sorted(valid_types))
        description = cls._description(types_str)
        #
        # IMPORTANT: Spark SQL UDF params (p_*) CANNOT be referenced inside
        # subqueries.  All param matching is done in the JOIN ON clause.
        # The subquery uses PARTITION BY on table columns to rank by recency
        # per unique parameter combination.
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
                'Call check_simulation again with the same parameters to poll for completion."}}'
            )

            -- Simulation failed
            WHEN latest.run_status = 'FAILED' AND latest.run_id IS NOT NULL
            THEN concat(
                '{{"status":"failed","simulation_type":"', p_simulation_type,
                '","run_id":"', latest.run_id,
                '","message":"The simulation failed. This may be a transient error. ',
                'You can call trigger_simulation with the same parameters to retry."}}'
            )

            -- No matching run found
            ELSE concat(
                '{{"status":"not_found","simulation_type":"', p_simulation_type,
                '","message":"No matching simulation found for these parameters. ',
                'Call trigger_simulation with the same parameters to start a new distributed Spark job."}}'
            )
        END
    FROM (SELECT 1 AS x) dummy
    LEFT JOIN (
        SELECT run_id, simulation_type AS sim_type,
               parameters AS sim_params, seed AS sim_seed,
               num_simulations AS sim_num_sims,
               status AS run_status,
               seed AS run_seed, num_simulations AS run_num_sims,
               ROW_NUMBER() OVER (
                   PARTITION BY simulation_type, parameters, seed, num_simulations
                   ORDER BY created_at DESC
               ) AS rn
        FROM {catalog}.{schema}.simulation_runs
        WHERE status IN ('COMPLETED', 'RUNNING', 'FAILED')
    ) latest ON latest.sim_type = p_simulation_type
           AND latest.sim_params = COALESCE(p_parameters, '{{}}')
           AND latest.sim_seed = COALESCE(p_seed, 42)
           AND latest.sim_num_sims = COALESCE(p_num_simulations, 10000)
           AND latest.rn = 1
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
