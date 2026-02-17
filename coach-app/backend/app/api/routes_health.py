from fastapi import APIRouter

from app.services.retrieval_service import RetrievalService

router = APIRouter()


@router.get('/health')
def health() -> dict[str, str | int]:
    retrieval = RetrievalService()
    points = retrieval.count()
    return {'status': 'ok', 'qdrant_points': points}
