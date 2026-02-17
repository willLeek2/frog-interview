from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.chat import IndexRebuildResponse
from app.services.indexing_service import IndexingService
from app.services.retrieval_service import RetrievalService

router = APIRouter()


@router.post('/rebuild', response_model=IndexRebuildResponse)
def rebuild_index(db: Session = Depends(get_session)) -> IndexRebuildResponse:
    retrieval = RetrievalService()
    service = IndexingService(retrieval_service=retrieval)
    return service.rebuild(db=db)
