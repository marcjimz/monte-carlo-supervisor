"""UC HTTP Connection for workspace REST API access.

Creates a Unity Catalog connection that allows SQL functions to call the
Databricks REST API (e.g., Jobs API) using ``http_request()``.  Credentials
are stored in Databricks Secrets — no PAT tokens in code.
"""


class WorkspaceConnection:
    """Generates DDL for a UC HTTP Connection to the Databricks workspace."""

    DEFAULT_NAME = "monte_carlo_ws"
    DEFAULT_SCOPE = "monte_carlo"
    DEFAULT_SECRET_KEY = "workspace_token"

    @classmethod
    def get_create_sql(
        cls,
        workspace_url: str,
        connection_name: str = DEFAULT_NAME,
        secret_scope: str = DEFAULT_SCOPE,
        secret_key: str = DEFAULT_SECRET_KEY,
    ) -> str:
        """Return ``CREATE CONNECTION`` SQL for the workspace HTTP endpoint."""
        # Strip trailing slash from workspace URL
        host = workspace_url.rstrip("/")
        return f"""
CREATE CONNECTION IF NOT EXISTS {connection_name} TYPE HTTP
OPTIONS (
    host '{host}',
    bearer_token secret('{secret_scope}', '{secret_key}')
)""".strip()

    @classmethod
    def get_grant_sql(
        cls,
        connection_name: str = DEFAULT_NAME,
        principal: str = "account users",
    ) -> str:
        """Return ``GRANT USE_CONNECTION`` SQL."""
        return f"GRANT USE_CONNECTION ON CONNECTION {connection_name} TO `{principal}`"
