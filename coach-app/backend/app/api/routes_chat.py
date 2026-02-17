from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, desc, select

from app.db.session import get_session
from app.models.chat import ChatMessage, ChatSession, FeatureType, RoleType, utc_now
from app.schemas.chat import MessageCreate, MessageRead, SessionCreate, SessionDetail, SessionRead
from app.services.coach_service import CoachService
from app.utils.json_utils import from_json, to_json

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


@router.post('/sessions/{session_id}/messages', response_model=MessageRead)
def send_message(session_id: str, payload: MessageCreate, db: Session = Depends(get_session)) -> MessageRead:
    session_row = db.get(ChatSession, session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail='会话不存在')

    user_msg = ChatMessage(session_id=session_id, role=RoleType.USER, content=payload.content)
    db.add(user_msg)
    session_row.updated_at = utc_now()
    db.add(session_row)
    db.commit()

    coach = CoachService()
    assistant_reply = coach.generate_reply(db=db, session=session_row, user_message=payload.content)

    assistant_row = ChatMessage(
        session_id=session_id,
        role=RoleType.ASSISTANT,
        content=assistant_reply.content,
        citations_json=to_json([x.model_dump() for x in assistant_reply.citations]),
        metadata_json=to_json(assistant_reply.metadata),
    )
    db.add(assistant_row)
    session_row.updated_at = utc_now()
    db.add(session_row)
    db.commit()
    db.refresh(assistant_row)

    if session_row.title.endswith('-会话') and session_row.title.count('-') == 1:
        session_row.title = payload.content[:20]
        db.add(session_row)
        db.commit()

    return _to_message_read(assistant_row)
