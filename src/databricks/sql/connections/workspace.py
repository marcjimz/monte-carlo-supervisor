"""UC HTTP Connection for workspace REST API access.

Creates a Unity Catalog connection that allows SQL functions to call the
Databricks REST API (e.g., Jobs API) using ``http_request()``.

Supports two credential types:
- **OAuth M2M** (preferred): Service Principal with OAuth client credentials.
  Tokens auto-rotate; no manual management.
- **Bearer Token** (fallback): PAT stored in Databricks Secrets.
"""


class WorkspaceConnection:
    """Generates DDL for a UC HTTP Connection to the Databricks workspace."""

    DEFAULT_NAME = "monte_carlo_ws"
    DEFAULT_SCOPE = "monte_carlo"

    @classmethod
    def get_create_oauth_m2m_sql(
        cls,
        workspace_url: str,
        client_id: str,
        client_secret: str,
        connection_name: str = DEFAULT_NAME,
    ) -> str:
        """Return ``CREATE CONNECTION`` SQL using OAuth M2M (Service Principal).

        The token_endpoint is derived from the workspace URL automatically.
        """
        host = workspace_url.rstrip("/")
        token_endpoint = f"{host}/oidc/v1/token"
        return f"""
CREATE CONNECTION {connection_name} TYPE HTTP
OPTIONS (
    host '{host}',
    client_id '{client_id}',
    client_secret '{client_secret}',
    oauth_scope 'all-apis',
    token_endpoint '{token_endpoint}'
)""".strip()

    @classmethod
    def get_create_bearer_sql(
        cls,
        workspace_url: str,
        connection_name: str = DEFAULT_NAME,
        secret_scope: str = DEFAULT_SCOPE,
        secret_key: str = "workspace_token",
    ) -> str:
        """Return ``CREATE CONNECTION`` SQL using a Bearer Token from secrets."""
        host = workspace_url.rstrip("/")
        return f"""
CREATE CONNECTION {connection_name} TYPE HTTP
OPTIONS (
    host '{host}',
    bearer_token secret('{secret_scope}', '{secret_key}')
)""".strip()

    @classmethod
    def get_drop_sql(cls, connection_name: str = DEFAULT_NAME) -> str:
        """Return ``DROP CONNECTION`` SQL."""
        return f"DROP CONNECTION IF EXISTS {connection_name}"

    @classmethod
    def get_grant_sql(
        cls,
        connection_name: str = DEFAULT_NAME,
        principal: str = "account users",
    ) -> str:
        """Return ``GRANT USE_CONNECTION`` SQL."""
        return f"GRANT USE_CONNECTION ON CONNECTION {connection_name} TO `{principal}`"
