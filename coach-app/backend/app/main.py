from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select

from app.api.router import api_router
from app.core.config import settings
from app.db.session import create_db_and_tables, get_session_ctx
from app.models.experience import (
    ExperienceBatch,
    ExperienceBatchStatus,
    ExperienceProcessTask,
    ExperienceProcessTaskStatus,
    utc_now,
)


def recover_incomplete_experience_tasks() -> None:
    interrupted_statuses = [
        ExperienceProcessTaskStatus.QUEUED,
        ExperienceProcessTaskStatus.RUNNING,
    ]
    recovery_message = '服务重启后未恢复该任务，请重新发起处理'

    with get_session_ctx() as db:
        tasks = db.exec(
            select(ExperienceProcessTask).where(ExperienceProcessTask.status.in_(interrupted_statuses))
        ).all()
        if not tasks:
            return

        now = utc_now()
        affected_batch_ids = {task.batch_id for task in tasks}

        for task in tasks:
            task.status = ExperienceProcessTaskStatus.FAILED
            task.error_message = task.error_message or recovery_message
            task.finished_at = task.finished_at or now
            task.updated_at = now
            db.add(task)

        for batch_id in affected_batch_ids:
            batch = db.get(ExperienceBatch, batch_id)
            if not batch:
                continue
            if batch.status in {ExperienceBatchStatus.PENDING, ExperienceBatchStatus.RUNNING}:
                batch.status = ExperienceBatchStatus.FAILED
                batch.error_message = recovery_message
                batch.updated_at = now
                db.add(batch)

        db.commit()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins(),
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    @app.on_event('startup')
    def on_startup() -> None:
        Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
        create_db_and_tables()
        recover_incomplete_experience_tasks()

    app.include_router(api_router)
    return app


app = create_app()
