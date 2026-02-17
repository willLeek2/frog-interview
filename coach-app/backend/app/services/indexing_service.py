from __future__ import annotations

import re
import uuid
from collections import Counter
from pathlib import Path

from sqlmodel import Session, delete

from app.core.config import settings
from app.models.chat import TopicStat, utc_now
from app.schemas.chat import IndexRebuildResponse
from app.services.retrieval_service import ChunkDoc, RetrievalService

SUPPORTED_EXTENSIONS = {'.md', '.markdown', '.txt'}
SKIP_DIR_NAMES = {'.git', 'node_modules', '.idea', '.vscode', '__pycache__'}


class IndexingService:
    def __init__(self, retrieval_service: RetrievalService) -> None:
        self.retrieval = retrieval_service

    def rebuild(self, db: Session) -> IndexRebuildResponse:
        resource_root = Path(settings.resources_dir)
        files = self._scan_files(resource_root)
        chunks: list[ChunkDoc] = []
        topic_counter: Counter[str] = Counter()

        for path in files:
            text = self._safe_read(path)
            if not text.strip():
                continue
            rel = str(path.relative_to(resource_root.parent))
            title = self._guess_title(path, text)
            heading_topic = self._extract_primary_topic(text)
            if heading_topic:
                topic_counter[heading_topic] += 1
            for idx, chunk in enumerate(self._chunk_text(text), start=1):
                chunk_id = self._chunk_id(rel, idx, chunk)
                chunks.append(
                    ChunkDoc(
                        chunk_id=chunk_id,
                        content=chunk,
                        source_path=rel,
                        source_title=title,
                        heading=heading_topic,
                    )
                )

        indexed = self.retrieval.upsert_chunks(chunks)
        self._save_topics(db, topic_counter)

        return IndexRebuildResponse(
            files_scanned=len(files),
            chunks_indexed=indexed,
            topics_count=len(topic_counter),
            collection=settings.qdrant_collection,
        )

    def _scan_files(self, root: Path) -> list[Path]:
        if not root.exists():
            return []
        matched: list[Path] = []
        for path in root.rglob('*'):
            if not path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                matched.append(path)
        return matched

    def _safe_read(self, path: Path) -> str:
        try:
            return path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            return path.read_text(encoding='utf-8', errors='ignore')

    def _guess_title(self, path: Path, text: str) -> str:
        for line in text.splitlines()[:20]:
            if line.strip().startswith('#'):
                return line.strip().lstrip('#').strip()
        return path.stem

    def _extract_primary_topic(self, text: str) -> str | None:
        for line in text.splitlines()[:80]:
            m = re.match(r'^#{1,3}\s+(.+)$', line.strip())
            if m:
                return m.group(1).strip()[:120]
        return None

    def _chunk_text(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        max_size = settings.chunk_size
        overlap = settings.chunk_overlap

        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        chunks: list[str] = []
        current = ''

        for para in paragraphs:
            candidate = f'{current}\n\n{para}'.strip() if current else para
            if len(candidate) <= max_size:
                current = candidate
                continue

            if current:
                chunks.append(current)
            if len(para) <= max_size:
                current = para
            else:
                for i in range(0, len(para), max_size - overlap):
                    piece = para[i : i + max_size]
                    if piece.strip():
                        chunks.append(piece.strip())
                current = ''

        if current:
            chunks.append(current)

        return chunks

    def _chunk_id(self, rel_path: str, idx: int, chunk: str) -> str:
        name = f'{rel_path}:{idx}:{chunk[:160]}'
        return str(uuid.uuid5(uuid.NAMESPACE_URL, name))

    def _save_topics(self, db: Session, topics: Counter[str]) -> None:
        db.exec(delete(TopicStat))
        now = utc_now()
        for topic, score in topics.most_common(300):
            db.add(TopicStat(topic=topic, score=score, updated_at=now))
        db.commit()
