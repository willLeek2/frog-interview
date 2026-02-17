from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExperienceBatchStatus(str, Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'


class ExperienceProcessTaskStatus(str, Enum):
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'


class ExperienceBatch(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    company: str | None = Field(default=None, index=True)
    business_line: str | None = Field(default=None, index=True)
    notes: str | None = None
    interview_at: date | None = Field(default=None, index=True)
    status: ExperienceBatchStatus = Field(default=ExperienceBatchStatus.PENDING, index=True)
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)


class ExperienceImage(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    batch_id: str = Field(index=True)
    original_name: str
    content_type: str | None = None
    file_path: str
    file_size: int = 0
    order_index: int = Field(default=0, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class ExperienceQuestionCluster(SQLModel, table=True):
    id: str = Field(primary_key=True)
    canonical_question: str
    topic_tags_json: str | None = None
    companies_json: str | None = None
    first_seen_at: datetime = Field(default_factory=utc_now, index=True)
    last_seen_at: datetime = Field(default_factory=utc_now, index=True)
    total_count: int = Field(default=0)


class ExperienceQuestion(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    batch_id: str = Field(index=True)
    cluster_id: str = Field(index=True)
    image_id: str | None = Field(default=None, index=True)
    question_text: str
    normalized_question: str = Field(index=True)
    topic_tags_json: str | None = None
    company: str | None = Field(default=None, index=True)
    business_line: str | None = Field(default=None, index=True)
    interview_round: str | None = Field(default=None, index=True)
    confidence: float = Field(default=0.0)
    extra_json: str | None = None
    created_at: datetime = Field(default_factory=utc_now, index=True)


class ExperienceProcessTask(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    batch_id: str = Field(index=True)
    status: ExperienceProcessTaskStatus = Field(default=ExperienceProcessTaskStatus.QUEUED, index=True)
    result_json: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)
    started_at: datetime | None = Field(default=None, index=True)
    finished_at: datetime | None = Field(default=None, index=True)
