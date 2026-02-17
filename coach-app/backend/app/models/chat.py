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


class IndexRebuildTaskStatus(str, Enum):
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'


class IndexRebuildMode(str, Enum):
    FULL = 'full'              # 全量重建：清空后重新索引
    INCREMENTAL = 'incremental'  # 增量更新：只处理新增/变更的文件


class IndexRebuildTask(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    status: IndexRebuildTaskStatus = Field(default=IndexRebuildTaskStatus.QUEUED, index=True)
    mode: IndexRebuildMode = Field(default=IndexRebuildMode.INCREMENTAL, index=True)
    # 进度信息
    files_total: int = Field(default=0)
    files_scanned: int = Field(default=0)
    files_added: int = Field(default=0)      # 增量：新增文件数
    files_updated: int = Field(default=0)    # 增量：更新文件数
    files_unchanged: int = Field(default=0)  # 增量：未变更文件数
    chunks_indexed: int = Field(default=0)
    topics_count: int = Field(default=0)
    # 结果/错误
    result_json: str | None = None
    error_message: str | None = None
    # 时间戳
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)
    started_at: datetime | None = Field(default=None, index=True)
    finished_at: datetime | None = Field(default=None, index=True)


class IndexedFile(SQLModel, table=True):
    """记录已索引文件的状态，用于增量更新。"""
    id: int | None = Field(default=None, primary_key=True)
    rel_path: str = Field(index=True, unique=True)
    content_hash: str = Field(index=True)  # 文件内容哈希
    mtime: float = Field(default=0.0)      # 文件修改时间戳
    chunks_count: int = Field(default=0)
    indexed_at: datetime = Field(default_factory=utc_now, index=True)
