"""Databricks SQL Statement Execution API wrapper.

Calls UC functions and queries Delta tables via the Statement Execution API,
using the Databricks SDK's WorkspaceClient.
"""

from __future__ import annotations

import json
import logging
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

from server.config import Settings, get_settings

logger = logging.getLogger(__name__)

_client: WorkspaceClient | None = None


def _get_client(settings: Settings | None = None) -> WorkspaceClient:
    global _client
    if _client is not None:
        return _client

    s = settings or get_settings()
    if s.is_databricks_app:
        _client = WorkspaceClient()
    else:
        _client = WorkspaceClient(profile=s.databricks_profile)
    return _client


def execute_uc_function(
    func_name: str,
    args: dict,
    settings: Settings | None = None,
) -> str:
    """Call a UC function and return its JSON string result.

    Builds a SELECT statement like:
        SELECT catalog.schema.func_name('arg1', 'arg2', ...)
    """
    s = settings or get_settings()
    client = _get_client(s)
    fqn = f"{s.uc_catalog}.{s.uc_schema}.{func_name}"

    # Build argument list
    arg_parts = []
    for key, val in args.items():
        if isinstance(val, str):
            # Escape single quotes in strings
            escaped = val.replace("'", "''")
            arg_parts.append(f"'{escaped}'")
        elif isinstance(val, bool):
            arg_parts.append("TRUE" if val else "FALSE")
        elif val is None:
            arg_parts.append("NULL")
        else:
            arg_parts.append(str(val))

    sql = f"SELECT {fqn}({', '.join(arg_parts)})"
    logger.info(f"Executing UC function: {sql[:200]}")

    response = client.statement_execution.execute_statement(
        warehouse_id=s.sql_warehouse_id,
        statement=sql,
        wait_timeout="60s",
    )

    # Poll if needed
    while response.status and response.status.state in (
        StatementState.PENDING,
        StatementState.RUNNING,
    ):
        time.sleep(2)
        response = client.statement_execution.get_statement(response.statement_id)

    if response.status and response.status.state == StatementState.FAILED:
        error_msg = response.status.error.message if response.status.error else "Unknown error"
        raise RuntimeError(f"UC function {func_name} failed: {error_msg}")

    # Extract result
    if response.result and response.result.data_array:
        return response.result.data_array[0][0] or "{}"

    return "{}"


def execute_query(
    sql: str,
    settings: Settings | None = None,
) -> list[dict]:
    """Execute an arbitrary SQL query and return rows as dicts."""
    s = settings or get_settings()
    client = _get_client(s)

    response = client.statement_execution.execute_statement(
        warehouse_id=s.sql_warehouse_id,
        statement=sql,
        wait_timeout="60s",
    )

    # Poll if needed
    while response.status and response.status.state in (
        StatementState.PENDING,
        StatementState.RUNNING,
    ):
        time.sleep(2)
        response = client.statement_execution.get_statement(response.statement_id)

    if response.status and response.status.state == StatementState.FAILED:
        error_msg = response.status.error.message if response.status.error else "Unknown error"
        raise RuntimeError(f"SQL query failed: {error_msg}")

    if not response.result or not response.result.data_array:
        return []

    # Build column names from manifest
    columns = []
    if response.manifest and response.manifest.schema and response.manifest.schema.columns:
        columns = [col.name for col in response.manifest.schema.columns]

    rows = []
    for row_data in response.result.data_array:
        if columns:
            rows.append(dict(zip(columns, row_data)))
        else:
            rows.append({"_col": row_data})

    return rows
