"""Pydantic models for simulations (synced from Delta)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CheckRequest(BaseModel):
    simulation_type: str
    parameters: dict = Field(default_factory=dict)
    num_simulations: int = 10000
    seed: int = 42


class TriggerRequest(BaseModel):
    simulation_type: str
    parameters: dict = Field(default_factory=dict)
    num_simulations: int = 10000
    seed: int = 42


class SimulationRun(BaseModel):
    run_id: str
    simulation_type: str
    parameters: str
    params_hash: str
    seed: int
    num_simulations: int
    status: str
    job_run_id: str | None = None
    created_at: str
    updated_at: str


class SimulationResult(BaseModel):
    run_id: str
    simulation_type: str
    metric_name: str
    group_key: str
    group_value: str
    num_trials: int
    mean_value: float
    std_value: float | None = None
    min_value: float | None = None
    max_value: float | None = None
    p05: float | None = None
    p10: float | None = None
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    p90: float | None = None
    p95: float | None = None
    created_at: str


class DistributionSpec(BaseModel):
    simulation_type: str
    distribution_name: str
    version: int
    spec: str
    fit_metadata: str | None = None
    created_at: str
