"""Environment configuration loader."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / ".env")


def get_config() -> dict:
    """Load configuration from environment variables."""
    return {
        "databricks_host": os.getenv("DATABRICKS_HOST", ""),
        "databricks_token": os.getenv("DATABRICKS_TOKEN", ""),
        "catalog": os.getenv("UC_CATALOG", "monte_carlo_sim"),
        "schema": os.getenv("UC_SCHEMA", "hospital_data"),
        "mc_job_id": os.getenv("MC_JOB_ID", ""),
        "genie_space_id": os.getenv("GENIE_SPACE_ID", ""),
        "data_seed": int(os.getenv("DATA_SEED", "42")),
    }
