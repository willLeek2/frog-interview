from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from app.core.config import settings
from app.services.openrouter_client import OpenRouterClient


@dataclass
class ChunkDoc:
    chunk_id: str
    content: str
    source_path: str
    source_title: str
    heading: str | None = None


class RetrievalService:
    def __init__(self) -> None:
        self.client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        self.collection = settings.qdrant_collection
        self.openrouter = OpenRouterClient()

    def _collection_exists(self) -> bool:
        try:
            collections = self.client.get_collections().collections
            return any(c.name == self.collection for c in collections)
        except Exception:  # noqa: BLE001
            return False

    def recreate_collection(self, vector_size: int) -> None:
        self.client.recreate_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    def ensure_collection(self, vector_size: int) -> None:
        if not self._collection_exists():
            self.recreate_collection(vector_size)

    def upsert_chunks(self, chunks: list[ChunkDoc], batch_size: int = 24) -> int:
        if not chunks:
            return 0

        first_vec = self.openrouter.embeddings([chunks[0].content])[0]
        self.ensure_collection(len(first_vec))

        total = 0
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.content for c in batch]
            vectors = self.openrouter.embeddings(texts)
            points: list[PointStruct] = []
            for chunk, vector in zip(batch, vectors, strict=False):
                points.append(
                    PointStruct(
                        id=chunk.chunk_id,
                        vector=vector,
                        payload={
                            'content': chunk.content,
                            'source_path': chunk.source_path,
                            'source_title': chunk.source_title,
                            'heading': chunk.heading or '',
                        },
                    )
                )
            self.client.upsert(collection_name=self.collection, points=points, wait=True)
            total += len(points)
        return total

    def search(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        if not self._collection_exists():
            return []

        query_vec = self.openrouter.embeddings([query])[0]
        limit = top_k or settings.retrieval_top_k
        result = self.client.search(
            collection_name=self.collection,
            query_vector=query_vec,
            limit=limit,
            with_payload=True,
        )
        rows: list[dict[str, Any]] = []
        for item in result:
            payload = item.payload or {}
            rows.append(
                {
                    'score': float(item.score),
                    'content': payload.get('content', ''),
                    'source_path': payload.get('source_path', ''),
                    'source_title': payload.get('source_title', ''),
                    'heading': payload.get('heading', ''),
                }
            )
        return rows

    def count(self) -> int:
        if not self._collection_exists():
            return 0
        info = self.client.get_collection(self.collection)
        return int(info.points_count or 0)
