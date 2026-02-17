from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.db.session import get_session
from app.models.chat import IndexRebuildMode
from app.schemas.chat import (
    IndexRebuildResponse,
    IndexRebuildTaskCreateRequest,
    IndexRebuildTaskCreateResponse,
    IndexRebuildTaskRead,
)
from app.services.indexing_service import IndexingService
from app.services.retrieval_service import RetrievalService

router = APIRouter()


@router.post('/rebuild', response_model=IndexRebuildTaskCreateResponse)
def rebuild_index(
    req: IndexRebuildTaskCreateRequest | None = None,
    db: Session = Depends(get_session),
) -> IndexRebuildTaskCreateResponse:
    """触发索引重建任务，返回任务 ID 供前端轮询进度。
    
    - mode='incremental' (默认): 只索引新增或变更的文件，速度快
    - mode='full': 清空后全部重新索引，最彻底
    """
    mode_str = (req.mode if req else 'incremental').lower()
    mode = IndexRebuildMode.FULL if mode_str == 'full' else IndexRebuildMode.INCREMENTAL
    
    service = IndexingService(start_worker=True)
    result = service.enqueue_rebuild_task(db=db, mode=mode)
    return IndexRebuildTaskCreateResponse(
        task_id=result['task_id'],
        status=result['status'],
        mode=result['mode'],
    )


@router.get('/rebuild/tasks/{task_id}', response_model=IndexRebuildTaskRead)
def get_rebuild_task(task_id: str, db: Session = Depends(get_session)) -> IndexRebuildTaskRead:
    """获取索引重建任务的进度和状态。"""
    service = IndexingService(start_worker=False)
    try:
        data = service.get_task(db=db, task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return IndexRebuildTaskRead(**data)


@router.get('/rebuild/tasks', response_model=list[IndexRebuildTaskRead])
def list_rebuild_tasks(
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_session),
) -> list[IndexRebuildTaskRead]:
    """获取最近的索引重建任务列表。"""
    service = IndexingService(start_worker=False)
    rows = service.list_recent_tasks(db=db, limit=limit)
    return [IndexRebuildTaskRead(**row) for row in rows]


@router.get('/rebuild/latest', response_model=IndexRebuildTaskRead | None)
def get_latest_rebuild_task(db: Session = Depends(get_session)) -> IndexRebuildTaskRead | None:
    """获取最新的索引重建任务（方便前端直接查询）。"""
    service = IndexingService(start_worker=False)
    rows = service.list_recent_tasks(db=db, limit=1)
    if not rows:
        return None
    return IndexRebuildTaskRead(**rows[0])


@router.post('/rebuild/sync', response_model=IndexRebuildResponse)
def rebuild_index_sync(
    mode: str = Query(default='incremental'),
    db: Session = Depends(get_session),
) -> IndexRebuildResponse:
    """[已废弃，仅用于调试] 同步执行索引重建，会阻塞直到完成。
    
    - mode='incremental' (默认): 只索引新增/变更的文件
    - mode='full': 清空后全部重新索引
    """
    mode_enum = IndexRebuildMode.FULL if mode.lower() == 'full' else IndexRebuildMode.INCREMENTAL
    retrieval = RetrievalService()
    service = IndexingService(retrieval_service=retrieval, start_worker=False)
    result = service.rebuild(db=db, mode=mode_enum)
    return IndexRebuildResponse(
        files_scanned=result['files_scanned'],
        chunks_indexed=result['chunks_indexed'],
        topics_count=result['topics_count'],
        collection=result['collection'],
    )
