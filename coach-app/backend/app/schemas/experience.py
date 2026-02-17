from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.experience import ExperienceBatchStatus, ExperienceProcessTaskStatus


class ExperienceImageRead(BaseModel):
    id: str
    original_name: str
    content_type: str | None = None
    file_size: int
    order_index: int
    created_at: datetime


class ExperienceQuestionRead(BaseModel):
    id: str
    cluster_id: str
    question_text: str
    normalized_question: str
    topic_tags: list[str] = Field(default_factory=list)
    company: str | None = None
    business_line: str | None = None
    interview_round: str | None = None
    confidence: float = 0
    extra: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ExperienceBatchRead(BaseModel):
    id: str
    company: str | None = None
    business_line: str | None = None
    interview_at: date | None = None
    status: ExperienceBatchStatus
    error_message: str | None = None
    image_count: int = 0
    question_count: int = 0
    created_at: datetime
    updated_at: datetime


class ExperienceBatchDetail(BaseModel):
    batch: ExperienceBatchRead
    images: list[ExperienceImageRead]
    questions: list[ExperienceQuestionRead]


class ExperienceProcessResponse(BaseModel):
    task_id: str
    batch_id: str
    status: ExperienceProcessTaskStatus
    already_exists: bool = False


class ExperienceProcessTaskRead(BaseModel):
    id: str
    batch_id: str
    status: ExperienceProcessTaskStatus
    result: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ExperienceHotQuestionRead(BaseModel):
    cluster_id: str
    canonical_question: str
    topic_tags: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    total_count: int
    last_seen_at: datetime


class ExperienceClusterVariantRead(BaseModel):
    normalized_question: str
    sample_question: str
    count: int
    last_seen_at: datetime
    companies: list[str] = Field(default_factory=list)


class ExperienceClusterSourceBatchRead(BaseModel):
    batch_id: str
    company: str | None = None
    business_line: str | None = None
    interview_at: date | None = None
    question_count: int
    last_seen_at: datetime


class ExperienceClusterDetailRead(BaseModel):
    cluster_id: str
    canonical_question: str
    topic_tags: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    total_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    variants: list[ExperienceClusterVariantRead] = Field(default_factory=list)
    source_batches: list[ExperienceClusterSourceBatchRead] = Field(default_factory=list)
