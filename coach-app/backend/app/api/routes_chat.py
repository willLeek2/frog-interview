from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, delete, desc, select

from app.core.config import settings
from app.db.session import get_session
from app.models.chat import ChatMessage, ChatRunTask, ChatSession, FeatureType
from app.schemas.chat import (
    ChatRunTaskCreateResponse,
    ChatRunTaskRead,
    CitationContentRead,
    MessageCreate,
    MessageRead,
    SessionCreate,
    SessionDetail,
    SessionRead,
)
from app.services.chat_task_service import ChatTaskService
from app.utils.json_utils import from_json

router = APIRouter()


def _to_session_read(row: ChatSession) -> SessionRead:
    return SessionRead(
        id=row.id,
        feature=row.feature,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_message_read(row: ChatMessage) -> MessageRead:
    return MessageRead(
        id=row.id,
        session_id=row.session_id,
        role=row.role,
        content=row.content,
        citations=from_json(row.citations_json, []),
        metadata=from_json(row.metadata_json, {}),
        created_at=row.created_at,
    )


@router.get('/sessions', response_model=list[SessionRead])
def list_sessions(feature: FeatureType, db: Session = Depends(get_session)) -> list[SessionRead]:
    stmt = select(ChatSession).where(ChatSession.feature == feature).order_by(desc(ChatSession.updated_at))
    rows = db.exec(stmt).all()
    return [_to_session_read(x) for x in rows]


@router.post('/sessions', response_model=SessionRead)
def create_session(payload: SessionCreate, db: Session = Depends(get_session)) -> SessionRead:
    row = ChatSession(feature=payload.feature, title=payload.title or f'{payload.feature.value}-会话')
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_session_read(row)


@router.get('/sessions/{session_id}', response_model=SessionDetail)
def get_session_detail(session_id: str, db: Session = Depends(get_session)) -> SessionDetail:
    session_row = db.get(ChatSession, session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail='会话不存在')

    stmt = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at)
    msgs = db.exec(stmt).all()
    return SessionDetail(session=_to_session_read(session_row), messages=[_to_message_read(x) for x in msgs])


@router.delete('/sessions/{session_id}')
def delete_session(session_id: str, db: Session = Depends(get_session)) -> dict[str, str]:
    session_row = db.get(ChatSession, session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail='会话不存在')
    db.exec(delete(ChatRunTask).where(ChatRunTask.session_id == session_id))
    db.exec(delete(ChatMessage).where(ChatMessage.session_id == session_id))
    db.delete(session_row)
    db.commit()
    return {'status': 'deleted'}


@router.post('/sessions/{session_id}/messages', response_model=ChatRunTaskCreateResponse)
def send_message(
    session_id: str,
    payload: MessageCreate,
    db: Session = Depends(get_session),
) -> ChatRunTaskCreateResponse:
    session_row = db.get(ChatSession, session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail='会话不存在')

    service = ChatTaskService(start_worker=True)
    task = service.enqueue_message_task(db=db, session=session_row, content=payload.content)
    return ChatRunTaskCreateResponse(
        task_id=task['id'],
        session_id=task['session_id'],
        status=task['status'],
        stage=task['stage'],
        stage_label=task['stage_label'],
    )


@router.get('/tasks/{task_id}', response_model=ChatRunTaskRead)
def get_task(task_id: str, db: Session = Depends(get_session)) -> ChatRunTaskRead:
    service = ChatTaskService(start_worker=False)
    try:
        data = service.get_task(db=db, task_id=task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ChatRunTaskRead(**data)


@router.get('/sessions/{session_id}/tasks', response_model=list[ChatRunTaskRead])
def list_session_tasks(
    session_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_session),
) -> list[ChatRunTaskRead]:
    session_row = db.get(ChatSession, session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail='会话不存在')
    service = ChatTaskService(start_worker=False)
    rows = service.list_session_tasks(db=db, session_id=session_id, limit=limit)
    return [ChatRunTaskRead(**x) for x in rows]


def _resolve_local_resource_path(raw_url: str) -> Path | None:
    clean_url = raw_url.split('#', 1)[0].split('?', 1)[0].strip()
    if not clean_url:
        return None
    if clean_url.startswith('http://') or clean_url.startswith('https://'):
        return None

    resources_root = Path(settings.resources_dir).resolve()
    if clean_url.startswith('resources/'):
        rel = clean_url[len('resources/') :]
        candidate = (resources_root / rel).resolve()
    else:
        path = Path(clean_url)
        candidate = path.resolve() if path.is_absolute() else (resources_root / clean_url).resolve()

    try:
        candidate.relative_to(resources_root)
    except ValueError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


@router.get('/citations/content', response_model=CitationContentRead)
def get_citation_content(
    url: str | None = None,
    title: str | None = None,
    source: str | None = None,
) -> CitationContentRead:
    if not url:
        return CitationContentRead(
            title=title or '来源信息缺失',
            url=None,
            source=source,
            render_mode='raw_text',
            content='该引用没有可解析的链接地址。',
            truncated=False,
        )

    local_path = _resolve_local_resource_path(url)
    if local_path:
        raw = local_path.read_text(encoding='utf-8', errors='ignore')
        limit = 120_000
        truncated = len(raw) > limit
        content = raw[:limit]
        suffix = local_path.suffix.lower()
        render_mode = 'markdown' if suffix in {'.md', '.markdown'} else 'raw_text'
        return CitationContentRead(
            title=title or local_path.name,
            url=url,
            source=source or 'local',
            render_mode=render_mode,
            content=content,
            truncated=truncated,
        )

    return CitationContentRead(
        title=title or '外部来源',
        url=url,
        source=source or 'web',
        render_mode='external',
        content='当前来源为外部链接，点击右上角可打开原文。',
        external_url=url if url.startswith('http://') or url.startswith('https://') else None,
        truncated=False,
    )
