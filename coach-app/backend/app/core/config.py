from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_LOCAL_DATA_DIR = Path(__file__).resolve().parents[2] / 'data'
DEFAULT_LOCAL_DB_PATH = DEFAULT_LOCAL_DATA_DIR / 'coach_app.db'


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'Coach App API'
    app_env: str = 'dev'
    app_host: str = '0.0.0.0'
    app_port: int = 8000
    app_cors_origins: str = 'http://localhost:5173,http://localhost:3000'

    # Data
    data_dir: str = str(DEFAULT_LOCAL_DATA_DIR)
    database_url: str = f'sqlite:///{DEFAULT_LOCAL_DB_PATH}'

    # Resources
    resources_dir: str = str(Path(__file__).resolve().parents[4] / 'resources')

    # Qdrant
    qdrant_url: str = 'http://qdrant:6333'
    qdrant_api_key: str | None = None
    qdrant_collection: str = 'coach_chunks'

    # OpenRouter
    openrouter_api_key: str = Field(default='', validation_alias='OPENROUTER_API_KEY')
    openrouter_base_url: str = 'https://openrouter.ai/api/v1'
    openrouter_chat_model: str = 'openai/gpt-4.1-mini'
    openrouter_embedding_model: str = 'openai/text-embedding-3-small'
    openrouter_audio_model: str = 'openai/gpt-4o-mini-transcribe'
    openrouter_vision_model: str = 'openai/gpt-4.1-mini'
    openrouter_timeout_seconds: int = 45
    openrouter_provider_order: str | None = None
    openrouter_allow_fallbacks: bool = True
    openrouter_provider_sort: str = 'price'

    # Perplexity
    perplexity_api_key: str | None = Field(default=None, validation_alias='PERPLEXITY_API_KEY')
    perplexity_base_url: str = 'https://api.perplexity.ai'
    perplexity_model: str = 'sonar'
    perplexity_timeout_seconds: int = 35

    # Jina Reader
    jina_api_key: str | None = Field(default=None, validation_alias='JINA_API_KEY')
    jina_reader_base_url: str = 'https://r.jina.ai'
    jina_timeout_seconds: int = 20

    # Retrieval
    retrieval_top_k: int = 6
    chunk_size: int = 1200
    chunk_overlap: int = 180

    # Experience Mining
    qdrant_experience_collection: str = 'coach_experience_questions'
    experience_cluster_threshold: float = 0.84
    experience_batch_max_files: int = 20
    experience_max_image_mb: int = 8
    experience_hot_default_days: int = 180

    def cors_origins(self) -> list[str]:
        return [x.strip() for x in self.app_cors_origins.split(',') if x.strip()]


settings = Settings()
