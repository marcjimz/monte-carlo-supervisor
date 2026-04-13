"""Pydantic models for parameter sweep matrices."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MatrixCreate(BaseModel):
    name: str = "Untitled Matrix"
    simulation_type: str
    row_parameter: str
    row_values: list[float]
    col_parameter: str
    col_values: list[float]
    base_parameters: dict = Field(default_factory=dict)
    output_metric: str
    output_group_key: str | None = None
    output_group_value: str | None = None
    num_simulations: int = 10000
    seed: int = 42


class MatrixUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class MatrixCell(BaseModel):
    id: UUID
    matrix_id: UUID
    row_value: float
    col_value: float
    run_id: str | None
    status: str
    result_mean: float | None
    result_p05: float | None
    result_p50: float | None
    result_p95: float | None
    created_at: datetime
    updated_at: datetime


class Matrix(BaseModel):
    id: UUID
    analysis_id: UUID
    name: str
    description: str | None = None
    simulation_type: str
    row_parameter: str
    row_values: list[float]
    col_parameter: str
    col_values: list[float]
    base_parameters: dict
    output_metric: str
    output_group_key: str | None
    output_group_value: str | None
    num_simulations: int
    seed: int
    created_at: datetime
    updated_at: datetime
    cells: list[MatrixCell] = Field(default_factory=list)
