from fastapi import APIRouter

from app.api.routes_audio import router as audio_router
from app.api.routes_chat import router as chat_router
from app.api.routes_experience import router as experience_router
from app.api.routes_health import router as health_router
from app.api.routes_index import router as index_router

api_router = APIRouter()
api_router.include_router(health_router, tags=['health'])
api_router.include_router(chat_router, prefix='/api/v1/chat', tags=['chat'])
api_router.include_router(index_router, prefix='/api/v1/index', tags=['index'])
api_router.include_router(audio_router, prefix='/api/v1/audio', tags=['audio'])
api_router.include_router(experience_router, prefix='/api/v1/experience', tags=['experience'])
