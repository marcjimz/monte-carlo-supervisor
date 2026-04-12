"""Health, user, and config routes."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, Request

from server.auth import User, get_current_user
from server.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok"}



@router.get("/user")
async def current_user(user: User = Depends(get_current_user)):
    return {"email": user.email, "username": user.username}


@router.get("/config/simulation-types")
async def simulation_types():
    """Return all simulation type configs for the UI."""
    settings = get_settings()
    config_path = Path(settings.config_yaml_path)

    if not config_path.exists():
        return {"simulation_types": {}}

    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Build a UI-friendly config for each type
    types = {}
    for type_name, type_config in config.get("simulation_types", {}).items():
        types[type_name] = {
            "display_name": type_config.get("display_name", type_name),
            "description": type_config.get("description", ""),
            "parameters": type_config.get("parameters", {}),
            "distributions": {
                name: {
                    "description": dist.get("description", ""),
                    "default_spec": dist.get("default_spec", {}),
                }
                for name, dist in type_config.get("distributions", {}).items()
            },
            "aggregation": type_config.get("aggregation", {}),
            "schema": type_config.get("schema", ""),
        }

    return {"simulation_types": types}
