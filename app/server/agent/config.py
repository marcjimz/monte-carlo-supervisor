"""Agent configuration — Pydantic models for LangGraph agent settings."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """LLM endpoint configuration for dual-model architecture."""

    supervisor_endpoint: str = "databricks-claude-opus-4-7"
    executor_endpoint: str = "databricks-claude-sonnet-4"
    supervisor_max_tokens: int = 4096
    executor_max_tokens: int = 2048
    supervisor_temperature: float = 0.3
    executor_temperature: float = 0.1


class GenieConfig(BaseModel):
    """Genie Space REST API configuration."""

    space_id: str = ""
    poll_interval_seconds: float = 2.0
    poll_max_seconds: float = 120.0
    max_retries: int = 3


class PromptConfig(BaseModel):
    """Prompt tuning configuration."""

    persona: str = (
        "You are a Women's Health analytics and Monte Carlo simulation supervisor. "
        "You help users explore hospital encounter data, run cost simulations, "
        "and perform sensitivity analyses for virtual care programs."
    )
    max_poll_attempts: int = 10
    auto_trigger_on_not_found: bool = True


class AgentConfig(BaseModel):
    """Top-level agent configuration."""

    model: ModelConfig = Field(default_factory=ModelConfig)
    genie: GenieConfig = Field(default_factory=GenieConfig)
    prompt: PromptConfig = Field(default_factory=PromptConfig)
    catalog: str = ""
    schema_name: str = ""
