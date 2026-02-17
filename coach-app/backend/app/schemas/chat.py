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


class IndexRebuildTaskCreateRequest(BaseModel):
    mode: str = 'incremental'  # 'full' 或 'incremental'


class IndexRebuildTaskCreateResponse(BaseModel):
    task_id: str
    status: str
    mode: str


class IndexRebuildTaskRead(BaseModel):
    id: str
    status: str
    mode: str
    files_total: int
    files_scanned: int
    files_added: int
    files_updated: int
    files_unchanged: int
    chunks_indexed: int
    topics_count: int
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AudioTranscribeResponse(BaseModel):
    text: str
