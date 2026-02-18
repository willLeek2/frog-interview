from __future__ import annotations

from queue import Queue
from threading import Lock, Thread
from typing import Any

from sqlmodel import Session, desc, select

from app.db.session import get_session_ctx
from app.models.chat import (
    ChatMessage,
    ChatRunStage,
    ChatRunTask,
    ChatRunTaskStatus,
    ChatSession,
    RoleType,
    utc_now,
)
from app.schemas.chat import AssistantReply
from app.services.coach_service import CoachService
from app.utils.json_utils import from_json, to_json

_CHAT_TASK_QUEUE: Queue[str] = Queue()
_CHAT_WORKER_STARTED = False
_CHAT_WORKER_LOCK = Lock()


def _chat_task_worker() -> None:
    while True:
        task_id = _CHAT_TASK_QUEUE.get()
        try:
            with get_session_ctx() as db:
                service = ChatTaskService(start_worker=False)
                service._run_task(db=db, task_id=task_id)
        except Exception:
            pass
        finally:
            _CHAT_TASK_QUEUE.task_done()


class ChatTaskService:
    def __init__(self, start_worker: bool = True) -> None:
        self.coach = CoachService()
        if start_worker:
            self._ensure_worker_started()

    def enqueue_message_task(self, db: Session, session: ChatSession, content: str) -> dict[str, Any]:
        user_msg = ChatMessage(session_id=session.id, role=RoleType.USER, content=content)
        db.add(user_msg)
        session.updated_at = utc_now()
        db.add(session)
        db.commit()
        db.refresh(user_msg)

        task = ChatRunTask(
            session_id=session.id,
            user_message_id=user_msg.id,
            status=ChatRunTaskStatus.QUEUED,
            stage=ChatRunStage.QUEUED,
            stage_label='等待处理',
            events_json=to_json([self._event(ChatRunStage.QUEUED, '问题已入队，等待执行')]),
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        _CHAT_TASK_QUEUE.put(task.id)
        return self._to_task_read(task)

    def get_task(self, db: Session, task_id: str) -> dict[str, Any]:
        row = db.get(ChatRunTask, task_id)
        if not row:
            raise ValueError('任务不存在')
        return self._to_task_read(row)

    def list_session_tasks(self, db: Session, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = db.exec(
            select(ChatRunTask)
            .where(ChatRunTask.session_id == session_id)
            .order_by(desc(ChatRunTask.created_at))
            .limit(limit)
        ).all()
        return [self._to_task_read(x) for x in rows]

    def _run_task(self, db: Session, task_id: str) -> None:
        task = db.get(ChatRunTask, task_id)
        if not task:
            return
        if task.status not in {ChatRunTaskStatus.QUEUED, ChatRunTaskStatus.RUNNING}:
            return

        session = db.get(ChatSession, task.session_id)
        user_msg = db.get(ChatMessage, task.user_message_id) if task.user_message_id else None
        if not session or not user_msg:
            self._mark_failed(db=db, task_id=task_id, error_message='会话或用户消息不存在')
            return

        self._mark_progress(
            db=db,
            task_id=task_id,
            stage=ChatRunStage.LOCAL_RETRIEVAL,
            stage_label='正在检索本地资料',
            detail='开始本地向量检索',
            running=True,
        )

        def on_progress(stage: ChatRunStage | str, stage_label: str, detail: str = '') -> None:
            stage_enum = stage if isinstance(stage, ChatRunStage) else ChatRunStage(stage)
            self._mark_progress(
                db=db,
                task_id=task_id,
                stage=stage_enum,
                stage_label=stage_label,
                detail=detail,
                running=True,
            )

        try:
            reply = self.coach.generate_reply(
                db=db,
                session=session,
                user_message=user_msg.content,
                on_progress=on_progress,
            )
            self._save_assistant_reply(
                db=db,
                session=session,
                task_id=task_id,
                user_message_content=user_msg.content,
                reply=reply,
            )
        except Exception as exc:  # noqa: BLE001
            self._mark_failed(db=db, task_id=task_id, error_message=str(exc)[:500])

    def _save_assistant_reply(
        self,
        db: Session,
        session: ChatSession,
        task_id: str,
        user_message_content: str,
        reply: AssistantReply,
    ) -> None:
        self._mark_progress(
            db=db,
            task_id=task_id,
            stage=ChatRunStage.SAVING,
            stage_label='正在保存回答',
            detail='写入 assistant 消息',
            running=True,
        )

        assistant_row = ChatMessage(
            session_id=session.id,
            role=RoleType.ASSISTANT,
            content=reply.content,
            citations_json=to_json([x.model_dump() for x in reply.citations]),
            metadata_json=to_json(reply.metadata),
        )
        db.add(assistant_row)
        session.updated_at = utc_now()
        db.add(session)
        db.commit()
        db.refresh(assistant_row)

        if session.title.endswith('-会话') and session.title.count('-') == 1:
            session.title = user_message_content[:20]
            db.add(session)
            db.commit()

        self._mark_completed(
            db=db,
            task_id=task_id,
            result_message_id=assistant_row.id,
            metadata=reply.metadata,
        )

    def _mark_progress(
        self,
        db: Session,
        task_id: str,
        stage: ChatRunStage,
        stage_label: str,
        detail: str = '',
        running: bool = False,
    ) -> None:
        row = db.get(ChatRunTask, task_id)
        if not row:
            return
        if running:
            row.status = ChatRunTaskStatus.RUNNING
            row.started_at = row.started_at or utc_now()
        row.stage = stage
        row.stage_label = stage_label
        row.updated_at = utc_now()
        row.events_json = self._append_event(
            row.events_json,
            event=self._event(stage=stage, stage_label=stage_label, detail=detail),
        )
        db.add(row)
        db.commit()

    def _mark_completed(
        self,
        db: Session,
        task_id: str,
        result_message_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        row = db.get(ChatRunTask, task_id)
        if not row:
            return
        row.status = ChatRunTaskStatus.COMPLETED
        row.stage = ChatRunStage.COMPLETED
        row.stage_label = '回答已完成'
        row.result_message_id = result_message_id
        row.metadata_json = to_json(metadata or {})
        row.finished_at = utc_now()
        row.updated_at = utc_now()
        row.events_json = self._append_event(
            row.events_json,
            event=self._event(ChatRunStage.COMPLETED, '回答生成完成'),
        )
        db.add(row)
        db.commit()

    def _mark_failed(self, db: Session, task_id: str, error_message: str) -> None:
        row = db.get(ChatRunTask, task_id)
        if not row:
            return
        row.status = ChatRunTaskStatus.FAILED
        row.stage = ChatRunStage.FAILED
        row.stage_label = '处理失败'
        row.error_message = error_message
        row.finished_at = utc_now()
        row.updated_at = utc_now()
        row.events_json = self._append_event(
            row.events_json,
            event=self._event(ChatRunStage.FAILED, '处理失败', error_message),
        )
        db.add(row)
        db.commit()

    def _append_event(self, events_json: str | None, event: dict[str, Any]) -> str:
        events = from_json(events_json, [])
        events.append(event)
        return to_json(events[-50:])

    def _event(self, stage: ChatRunStage, stage_label: str, detail: str = '') -> dict[str, Any]:
        return {
            'stage': stage.value,
            'label': stage_label,
            'detail': detail,
            'at': utc_now().isoformat(),
        }

    def _to_task_read(self, row: ChatRunTask) -> dict[str, Any]:
        return {
            'id': row.id,
            'session_id': row.session_id,
            'user_message_id': row.user_message_id,
            'result_message_id': row.result_message_id,
            'status': row.status,
            'stage': row.stage,
            'stage_label': row.stage_label,
            'events': from_json(row.events_json, []),
            'metadata': from_json(row.metadata_json, {}),
            'error_message': row.error_message,
            'created_at': row.created_at,
            'updated_at': row.updated_at,
            'started_at': row.started_at,
            'finished_at': row.finished_at,
        }

    @staticmethod
    def _ensure_worker_started() -> None:
        global _CHAT_WORKER_STARTED
        with _CHAT_WORKER_LOCK:
            if _CHAT_WORKER_STARTED:
                return
            worker = Thread(target=_chat_task_worker, daemon=True, name='chat-task-worker')
            worker.start()
            _CHAT_WORKER_STARTED = True
