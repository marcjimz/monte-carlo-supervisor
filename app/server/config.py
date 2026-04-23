"""Pydantic Settings for the Monte Carlo UI app.

Supports two modes:
- Databricks App: env vars auto-populated by resource bindings
- Local dev: uses databricks-sdk profile for auth
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Databricks
    databricks_host: str = ""
    uc_catalog: str = "monte_carlo_supervisor_catalog"
    uc_schema: str = "hospital_data"
    supervisor_endpoint: str = "databricks-claude-opus-4-7"
    executor_endpoint: str = "databricks-claude-sonnet-4"
    sql_warehouse_id: str = "39aeb4605bfae41b"

    # Lakebase (auto-populated by resource binding in Databricks Apps)
    pghost: str = ""
    pgport: int = 5432
    pgdatabase: str = "mcapp"
    pguser: str = ""

    @model_validator(mode="after")
    def _resolve_pguser(self) -> "Settings":
        """Fall back to DATABRICKS_CLIENT_ID if PGUSER is not set.

        In Databricks Apps, the platform injects the app's service principal
        UUID as DATABRICKS_CLIENT_ID. This is the same value needed for PGUSER
        when connecting to Lakebase.
        """
        if not self.pguser:
            self.pguser = os.environ.get("DATABRICKS_CLIENT_ID", "")
        return self

    # Lakebase Autoscaling (for credential generation)
    lakebase_project: str = "monte-carlo-app"
    lakebase_branch: str = "production"
    lakebase_endpoint: str = "primary"

    # AI/BI Dashboard
    dashboard_id: str = ""

    # Genie Space
    genie_space_id: str = ""

    # Feature flags
    seed_demo_data: bool = True

    # Auth
    databricks_profile: str = "mc-supervisor"

    # Config path — bundled copy in server/ dir, fallback to parent repo
    config_yaml_path: str = str(
        Path(__file__).resolve().parent / "config.yaml"
        if (Path(__file__).resolve().parent / "config.yaml").exists()
        else Path(__file__).resolve().parent.parent.parent
        / "src" / "mc_supervisor" / "monte_carlo" / "config.yaml"
    )

    @property
    def is_databricks_app(self) -> bool:
        return bool(os.environ.get("DATABRICKS_APP_PORT"))

    model_config = {"env_prefix": "", "case_sensitive": False}


@lru_cache
def get_settings() -> Settings:
    return Settings()
