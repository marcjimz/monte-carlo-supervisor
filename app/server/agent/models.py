"""Model factory — creates ChatOpenAI instances for Databricks Foundation Model API."""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from server.agent.config import ModelConfig


def _get_databricks_base_url() -> str:
    """Return the Databricks serving endpoint base URL."""
    import os

    from server.config import get_settings

    settings = get_settings()
    host = settings.databricks_host or os.environ.get("DATABRICKS_HOST", "")
    # DATABRICKS_HOST in Databricks Apps is just hostname without scheme
    if host and not host.startswith("http"):
        host = f"https://{host}"
    return f"{host.rstrip('/')}/serving-endpoints"


def _get_databricks_api_key() -> str:
    """Return a Databricks API token."""
    import os

    if token := os.environ.get("DATABRICKS_TOKEN"):
        return token

    from server.config import get_settings

    settings = get_settings()
    if settings.is_databricks_app:
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        return w.config.authenticate().get("Authorization", "").removeprefix("Bearer ")

    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient(profile=settings.databricks_profile)
    return w.config.authenticate().get("Authorization", "").removeprefix("Bearer ")


def get_supervisor_model(config: ModelConfig | None = None) -> ChatOpenAI:
    """Create the supervisor model (high-reasoning, e.g. Opus)."""
    cfg = config or ModelConfig()
    return ChatOpenAI(
        model=cfg.supervisor_endpoint,
        base_url=_get_databricks_base_url(),
        api_key=_get_databricks_api_key(),
        max_tokens=cfg.supervisor_max_tokens,
    )


def get_executor_model(config: ModelConfig | None = None) -> ChatOpenAI:
    """Create the executor model (fast, e.g. Sonnet)."""
    cfg = config or ModelConfig()
    return ChatOpenAI(
        model=cfg.executor_endpoint,
        base_url=_get_databricks_base_url(),
        api_key=_get_databricks_api_key(),
        max_tokens=cfg.executor_max_tokens,
    )
