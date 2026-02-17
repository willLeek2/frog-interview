from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FeatureType(str, Enum):
    RANDOM = 'random'
    EXPLAIN = 'explain'
    QUIZ = 'quiz'


class RoleType(str, Enum):
    USER = 'user'
    ASSISTANT = 'assistant'
    SYSTEM = 'system'


class ChatSession(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    feature: FeatureType = Field(index=True)
    title: str = Field(default='新会话')
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)


class ChatMessage(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    session_id: str = Field(index=True)
    role: RoleType = Field(index=True)
    content: str
    citations_json: str | None = None
    metadata_json: str | None = None
    created_at: datetime = Field(default_factory=utc_now, index=True)


class TopicStat(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    topic: str = Field(index=True, unique=True)
    score: int = Field(default=0)
    updated_at: datetime = Field(default_factory=utc_now, index=True)
