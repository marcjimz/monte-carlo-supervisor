"""UC HTTP Connections for workspace and App REST API access.

Creates Unity Catalog connections that allow SQL functions to call REST APIs
using ``http_request()``.

- ``WorkspaceConnection``: Points to the workspace URL (Jobs API, etc.)
- ``AppConnection``: Points to the Databricks App URL (``*.databricksapps.com``)

Both use **OAuth M2M** with a Service Principal. Tokens auto-rotate; no manual
management required.
"""


class WorkspaceConnection:
    """Generates DDL for a UC HTTP Connection to the Databricks workspace."""

    DEFAULT_NAME = "monte_carlo_ws"

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


class AppConnection:
    """Generates DDL for a UC HTTP Connection to the Databricks App URL.

    Same OAuth M2M pattern as WorkspaceConnection but with the App URL
    (``*.databricksapps.com``) as the host. The token endpoint still points
    to the workspace OIDC endpoint for SP authentication.
    """

    DEFAULT_NAME = "monte_carlo_app"

    @classmethod
    def get_create_oauth_m2m_sql(
        cls,
        app_url: str,
        workspace_url: str,
        client_id: str,
        client_secret: str,
        connection_name: str = DEFAULT_NAME,
        is_mcp_connection: bool = False,
    ) -> str:
        """Return ``CREATE CONNECTION`` SQL using OAuth M2M.

        The host is the App URL; the token_endpoint is derived from the
        workspace URL (same OIDC endpoint used by the workspace connection).

        When *is_mcp_connection* is True the ``is_mcp_connection 'true'``
        option is added so MAS can use this connection for external MCP
        server agents.
        """
        app_host = app_url.rstrip("/")
        ws_host = workspace_url.rstrip("/")
        token_endpoint = f"{ws_host}/oidc/v1/token"
        mcp_line = "\n    is_mcp_connection 'true'," if is_mcp_connection else ""
        return f"""
CREATE CONNECTION {connection_name} TYPE HTTP
OPTIONS (
    host '{app_host}',{mcp_line}
    client_id '{client_id}',
    client_secret '{client_secret}',
    oauth_scope 'all-apis',
    token_endpoint '{token_endpoint}'
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
