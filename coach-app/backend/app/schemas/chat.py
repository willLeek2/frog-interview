from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.chat import FeatureType, RoleType


class Citation(BaseModel):
    title: str | None = None
    url: str | None = None
    snippet: str | None = None
    source: str | None = None


class SessionCreate(BaseModel):
    feature: FeatureType
    title: str | None = None


class SessionRead(BaseModel):
    id: str
    feature: FeatureType
    title: str
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)


class MessageRead(BaseModel):
    id: str
    session_id: str
    role: RoleType
    content: str
    citations: list[Citation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class SessionDetail(BaseModel):
    session: SessionRead
    messages: list[MessageRead]


class AssistantReply(BaseModel):
    content: str
    citations: list[Citation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexRebuildResponse(BaseModel):
    files_scanned: int
    chunks_indexed: int
    topics_count: int
    collection: str


class AudioTranscribeResponse(BaseModel):
    text: str
