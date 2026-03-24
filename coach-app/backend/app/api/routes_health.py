from fastapi import APIRouter

from app.services.retrieval_service import RetrievalService

router = APIRouter()


@router.get('/health')
def health() -> dict[str, str | int | None]:
    try:
        retrieval = RetrievalService()
        points = retrieval.count()
        return {
            'status': 'ok',
            'qdrant_status': 'ok',
            'qdrant_points': points,
            'qdrant_error': None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            'status': 'degraded',
            'qdrant_status': 'unreachable',
            'qdrant_points': 0,
            'qdrant_error': str(exc)[:300],
        }
