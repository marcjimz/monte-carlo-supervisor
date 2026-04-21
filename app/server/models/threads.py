"""Pydantic models for agent threads and messages."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ThreadCreate(BaseModel):
    title: str = "New Thread"
    icon: str = "chat"


class ThreadUpdate(BaseModel):
    title: str | None = None
    icon: str | None = None


class MessageCreate(BaseModel):
    content: str


class Message(BaseModel):
    id: UUID
    thread_id: UUID
    role: str
    content: str
    metadata: dict | None = None
    created_at: datetime


class Thread(BaseModel):
    id: UUID
    analysis_id: UUID
    owner_email: str
    title: str
    icon: str | None
    created_at: datetime
    updated_at: datetime
    messages: list[Message] = Field(default_factory=list)
