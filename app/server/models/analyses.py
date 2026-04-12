"""Pydantic models for analyses."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AnalysisCreate(BaseModel):
    name: str = "Untitled Analysis"
    description: str | None = None


class AnalysisUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class Collaborator(BaseModel):
    id: UUID
    analysis_id: UUID
    user_email: str
    role: str = "viewer"
    created_at: datetime


class CollaboratorAdd(BaseModel):
    user_email: str
    role: str = "viewer"


class AnalysisSimulation(BaseModel):
    id: UUID
    analysis_id: UUID
    run_id: str
    added_by: str
    created_at: datetime


class Analysis(BaseModel):
    id: UUID
    name: str
    description: str | None
    owner_email: str
    status: str
    created_at: datetime
    updated_at: datetime


class AnalysisList(BaseModel):
    analyses: list[Analysis]


class AnalysisDetail(Analysis):
    collaborators: list[Collaborator] = Field(default_factory=list)
    simulations: list[AnalysisSimulation] = Field(default_factory=list)
