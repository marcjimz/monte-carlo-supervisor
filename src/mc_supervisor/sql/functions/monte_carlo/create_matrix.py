"""UC Function definition for create_matrix — validates matrix parameters.

This is a **validation-only** function. It checks that the simulation type,
row/column parameters, and value arrays are valid, then returns a structured
JSON result. The actual matrix creation (Lakebase CRUD) is performed by
``thread_service.py`` when it intercepts the ``matrix_builder`` tool_call
SSE event — the same interception pattern used for ``simulation_trigger``.
"""


class CreateMatrixFunction:
    """UC SQL Function that validates parameter sweep matrix definitions."""

    name = "create_matrix"

    @classmethod
    def _description(cls, types_str: str) -> str:
        return (
            "Creates a parameter sweep matrix that runs multiple simulations "
            "varying two parameters across a grid of values. Returns the validated "
            "matrix specification. The system will automatically create the matrix "
            "and trigger all cell simulations. "
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
    p_row_parameter STRING COMMENT 'Parameter name for matrix rows (e.g. encounter_reduction_pct)',
    p_row_values STRING COMMENT 'JSON array of row values, e.g. [0.05, 0.08, 0.10, 0.15]',
    p_col_parameter STRING COMMENT 'Parameter name for matrix columns (e.g. solution_cost)',
    p_col_values STRING COMMENT 'JSON array of column values, e.g. [500000000, 1000000000]',
    p_output_metric STRING COMMENT 'Output metric to display (nullable — defaults to primary metric for the simulation type)',
    p_base_parameters STRING COMMENT 'JSON object of non-swept parameter overrides (nullable — defaults to empty)',
    p_name STRING COMMENT 'Display name for the matrix (nullable — auto-generated)',
    p_num_simulations INT COMMENT 'Number of Monte Carlo trials per cell (default: 10000)',
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
            WHEN p_row_parameter = p_col_parameter
            THEN '{{"error":"row_parameter and col_parameter must be different"}}'
            WHEN p_row_values IS NULL OR LENGTH(TRIM(p_row_values)) < 2
            THEN '{{"error":"p_row_values must be a non-empty JSON array"}}'
            WHEN p_col_values IS NULL OR LENGTH(TRIM(p_col_values)) < 2
            THEN '{{"error":"p_col_values must be a non-empty JSON array"}}'
            ELSE concat(
                '{{"status":"validated","simulation_type":"', p_simulation_type,
                '","row_parameter":"', p_row_parameter,
                '","row_values":', p_row_values,
                ',"col_parameter":"', p_col_parameter,
                '","col_values":', p_col_values,
                ',"output_metric":"', COALESCE(p_output_metric, ''),
                '","base_parameters":', COALESCE(p_base_parameters, '{{}}'),
                ',"name":"', COALESCE(p_name, ''),
                '","num_simulations":', CAST(COALESCE(p_num_simulations, 10000) AS STRING),
                ',"seed":', CAST(COALESCE(p_seed, 42) AS STRING),
                ',"message":"Matrix validated. The system will create the matrix and trigger all cell simulations automatically."}}'
            )
        END
);"""

    @classmethod
    def get_grant_sql(cls, catalog: str, schema: str, principal: str = "account users") -> str:
        return f"GRANT EXECUTE ON FUNCTION {catalog}.{schema}.{cls.name} TO `{principal}`;"
