from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.experience import (
    ExperienceBatchDetail,
    ExperienceBatchRead,
    ExperienceClusterDetailRead,
    ExperienceHotQuestionRead,
    ExperienceProcessResponse,
    ExperienceProcessTaskRead,
)
from app.services.experience_mining_service import ExperienceMiningService

router = APIRouter()


@router.post('/batches', response_model=ExperienceBatchRead)
def create_batch(
    files: list[UploadFile] = File(...),
    company: str | None = Form(default=None),
    business_line: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    interview_at: str | None = Form(default=None),
    db: Session = Depends(get_session),
) -> ExperienceBatchRead:
    service = ExperienceMiningService()
    dt: datetime | None = None
    if interview_at:
        try:
            dt = datetime.fromisoformat(interview_at)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail='interview_at 需要 ISO 日期格式') from exc

    try:
        row = service.create_batch(
            db=db,
            files=files,
            company=company,
            business_line=business_line,
            notes=notes,
            interview_at=dt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ExperienceBatchRead(
        id=row.id,
        company=row.company,
        business_line=row.business_line,
        interview_at=row.interview_at,
        status=row.status,
        error_message=row.error_message,
        image_count=service._count_images(db, row.id),  # noqa: SLF001
        question_count=service._count_questions(db, row.id),  # noqa: SLF001
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get('/batches', response_model=list[ExperienceBatchRead])
def list_batches(db: Session = Depends(get_session)) -> list[ExperienceBatchRead]:
    service = ExperienceMiningService()
    rows = service.list_batches(db=db)
    return [ExperienceBatchRead(**item) for item in rows]


@router.get('/batches/{batch_id}', response_model=ExperienceBatchDetail)
def get_batch_detail(batch_id: str, db: Session = Depends(get_session)) -> ExperienceBatchDetail:
    service = ExperienceMiningService()
    try:
        detail = service.get_batch_detail(db=db, batch_id=batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ExperienceBatchDetail(**detail)


@router.post('/batches/{batch_id}/process', response_model=ExperienceProcessResponse)
def process_batch(batch_id: str, db: Session = Depends(get_session)) -> ExperienceProcessResponse:
    service = ExperienceMiningService()
    try:
        data = service.enqueue_process_task(db=db, batch_id=batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f'处理失败: {exc}') from exc
    return ExperienceProcessResponse(**data)


@router.get('/tasks/{task_id}', response_model=ExperienceProcessTaskRead)
def get_task(task_id: str, db: Session = Depends(get_session)) -> ExperienceProcessTaskRead:
    service = ExperienceMiningService()
    try:
        data = service.get_task(db=db, task_id=task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ExperienceProcessTaskRead(**data)


@router.get('/batches/{batch_id}/tasks', response_model=list[ExperienceProcessTaskRead])
def list_batch_tasks(batch_id: str, limit: int = 30, db: Session = Depends(get_session)) -> list[ExperienceProcessTaskRead]:
    service = ExperienceMiningService()
    rows = service.list_batch_tasks(db=db, batch_id=batch_id, limit=limit)
    return [ExperienceProcessTaskRead(**x) for x in rows]


@router.get('/hot-questions', response_model=list[ExperienceHotQuestionRead])
def list_hot_questions(
    days: int | None = None,
    company: str | None = None,
    limit: int = 20,
    db: Session = Depends(get_session),
) -> list[ExperienceHotQuestionRead]:
    service = ExperienceMiningService()
    rows = service.hot_questions(db=db, days=days, company=company, limit=limit)
    return [ExperienceHotQuestionRead(**item) for item in rows]


@router.get('/clusters/{cluster_id}', response_model=ExperienceClusterDetailRead)
def get_cluster_detail(cluster_id: str, limit: int = 200, db: Session = Depends(get_session)) -> ExperienceClusterDetailRead:
    service = ExperienceMiningService()
    try:
        data = service.get_cluster_detail(db=db, cluster_id=cluster_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ExperienceClusterDetailRead(**data)
