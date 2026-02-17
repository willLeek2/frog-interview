from __future__ import annotations

import hashlib
import re
import uuid
from collections import Counter
from pathlib import Path
from queue import Queue
from threading import Lock, Thread
from typing import Any

from sqlmodel import Session, delete, select

from app.core.config import settings
from app.db.session import get_session_ctx
from app.models.chat import (
    IndexRebuildMode,
    IndexRebuildTask,
    IndexRebuildTaskStatus,
    IndexedFile,
    TopicStat,
    utc_now,
)
from app.services.retrieval_service import ChunkDoc, RetrievalService
from app.utils.json_utils import to_json

SUPPORTED_EXTENSIONS = {'.md', '.markdown', '.txt'}
SKIP_DIR_NAMES = {'.git', 'node_modules', '.idea', '.vscode', '__pycache__'}

_INDEX_QUEUE: Queue[tuple[str, IndexRebuildMode]] = Queue()
_WORKER_STARTED = False
_WORKER_LOCK = Lock()


def _index_task_worker() -> None:
    while True:
        task_id, mode = _INDEX_QUEUE.get()
        try:
            with get_session_ctx() as db:
                service = IndexingService(start_worker=False)
                service._run_task(db=db, task_id=task_id, mode=mode)
        except Exception:
            pass
        finally:
            _INDEX_QUEUE.task_done()


class IndexingService:
    def __init__(self, retrieval_service: RetrievalService | None = None, start_worker: bool = True) -> None:
        self.retrieval = retrieval_service or RetrievalService()
        if start_worker:
            self._ensure_worker_started()

    def enqueue_rebuild_task(
        self,
        db: Session,
        mode: IndexRebuildMode = IndexRebuildMode.INCREMENTAL,
    ) -> dict[str, Any]:
        """创建并返回索引重建任务，入队等待执行。"""
        # 检查是否已有正在执行的任务
        existing = db.exec(
            select(IndexRebuildTask).where(
                IndexRebuildTask.status.in_([
                    IndexRebuildTaskStatus.QUEUED,
                    IndexRebuildTaskStatus.RUNNING,
                ])
            )
        ).first()
        if existing:
            return {
                'task_id': existing.id,
                'status': existing.status,
                'mode': existing.mode,
                'already_exists': True,
            }

        task = IndexRebuildTask(status=IndexRebuildTaskStatus.QUEUED, mode=mode)
        db.add(task)
        db.commit()
        db.refresh(task)

        _INDEX_QUEUE.put((task.id, mode))
        return {
            'task_id': task.id,
            'status': task.status,
            'mode': task.mode,
            'already_exists': False,
        }

    def get_task(self, db: Session, task_id: str) -> dict[str, Any]:
        """获取任务详情和进度。"""
        row = db.get(IndexRebuildTask, task_id)
        if not row:
            raise ValueError('任务不存在')
        return self._to_task_read(row)

    def list_recent_tasks(self, db: Session, limit: int = 10) -> list[dict[str, Any]]:
        """获取最近的任务列表。"""
        rows = db.exec(
            select(IndexRebuildTask)
            .order_by(IndexRebuildTask.created_at.desc())
            .limit(limit)
        ).all()
        return [self._to_task_read(row) for row in rows]

    def rebuild(
        self,
        db: Session,
        task_id: str | None = None,
        mode: IndexRebuildMode = IndexRebuildMode.INCREMENTAL,
    ) -> dict[str, Any]:
        """执行索引重建。
        
        Args:
            mode: 'full' 全量重建(清空后重新索引) 或 'incremental' 增量更新
        """
        resource_root = Path(settings.resources_dir)
        all_files = self._scan_files(resource_root)
        total_files = len(all_files)

        # 更新任务：开始执行，记录总文件数
        if task_id:
            task = db.get(IndexRebuildTask, task_id)
            if task:
                task.status = IndexRebuildTaskStatus.RUNNING
                task.files_total = total_files
                task.files_scanned = 0
                task.files_added = 0
                task.files_updated = 0
                task.files_unchanged = 0
                task.chunks_indexed = 0
                task.topics_count = 0
                task.started_at = utc_now()
                task.updated_at = utc_now()
                db.add(task)
                db.commit()

        # 全量模式：清空 Qdrant 和 IndexedFile 记录
        if mode == IndexRebuildMode.FULL:
            self._clear_collection()
            db.exec(delete(IndexedFile))
            db.commit()

        topic_counter: Counter[str] = Counter()
        files_scanned = 0
        files_added = 0
        files_updated = 0
        files_unchanged = 0
        chunks_indexed = 0

        try:
            # 获取当前已索引文件记录
            indexed_files_map: dict[str, IndexedFile] = {}
            if mode == IndexRebuildMode.INCREMENTAL:
                all_indexed = db.exec(select(IndexedFile)).all()
                indexed_files_map = {f.rel_path: f for f in all_indexed}

            for path in all_files:
                rel = str(path.relative_to(resource_root.parent))
                text = self._safe_read(path)
                files_scanned += 1

                if not text.strip():
                    # 空文件：如果是增量模式且之前有记录，需要删除
                    if mode == IndexRebuildMode.INCREMENTAL and rel in indexed_files_map:
                        self._remove_file_from_index(db, rel)
                        files_updated += 1
                    continue

                # 计算内容哈希
                content_hash = hashlib.sha1(text.encode('utf-8')).hexdigest()
                mtime = path.stat().st_mtime

                # 增量模式：检查是否需要更新
                if mode == IndexRebuildMode.INCREMENTAL:
                    existing = indexed_files_map.get(rel)
                    if existing and existing.content_hash == content_hash:
                        # 文件未变更
                        files_unchanged += 1
                        # 仍需要统计主题
                        heading_topic = self._extract_primary_topic(text)
                        if heading_topic:
                            topic_counter[heading_topic] += 1
                        continue

                # 需要索引此文件
                title = self._guess_title(path, text)
                heading_topic = self._extract_primary_topic(text)
                if heading_topic:
                    topic_counter[heading_topic] += 1

                file_chunks: list[ChunkDoc] = []
                for idx, chunk_text in enumerate(self._chunk_text(text), start=1):
                    chunk_id = self._chunk_id(rel, idx, chunk_text)
                    file_chunks.append(
                        ChunkDoc(
                            chunk_id=chunk_id,
                            content=chunk_text,
                            source_path=rel,
                            source_title=title,
                            heading=heading_topic,
                        )
                    )

                # 增量模式：先删除旧的 chunks（通过不同的 chunk_id 机制自动覆盖）
                # 由于 chunk_id 是基于内容的 UUID5，内容变更后 chunk_id 会变
                # 但内容相同的 chunk 会被复用

                # 索引 chunks
                if file_chunks:
                    indexed = self.retrieval.upsert_chunks(file_chunks)
                    chunks_indexed += indexed

                # 更新或创建 IndexedFile 记录
                self._update_indexed_file(
                    db,
                    rel,
                    content_hash=content_hash,
                    mtime=mtime,
                    chunks_count=len(file_chunks),
                )

                if mode == IndexRebuildMode.INCREMENTAL:
                    if rel in indexed_files_map:
                        files_updated += 1
                    else:
                        files_added += 1

                # 更新进度
                if task_id and files_scanned % 5 == 0:  # 每 5 个文件更新一次
                    task = db.get(IndexRebuildTask, task_id)
                    if task:
                        task.files_scanned = files_scanned
                        task.files_added = files_added
                        task.files_updated = files_updated
                        task.files_unchanged = files_unchanged
                        task.chunks_indexed = chunks_indexed
                        task.updated_at = utc_now()
                        db.add(task)
                        db.commit()

            # 增量模式：删除已不存在文件的索引
            if mode == IndexRebuildMode.INCREMENTAL:
                current_paths = {str(p.relative_to(resource_root.parent)) for p in all_files}
                for rel_path in list(indexed_files_map.keys()):
                    if rel_path not in current_paths:
                        self._remove_file_from_index(db, rel_path)
                        files_updated += 1

            # 保存主题统计（全量模式直接替换，增量模式合并）
            self._save_topics(db, topic_counter, mode == IndexRebuildMode.FULL)

            result = {
                'files_scanned': files_scanned,
                'files_added': files_added,
                'files_updated': files_updated,
                'files_unchanged': files_unchanged,
                'chunks_indexed': chunks_indexed,
                'topics_count': len(topic_counter),
                'collection': settings.qdrant_collection,
                'mode': mode,
            }

            # 更新任务完成状态
            if task_id:
                task = db.get(IndexRebuildTask, task_id)
                if task:
                    task.status = IndexRebuildTaskStatus.COMPLETED
                    task.files_scanned = files_scanned
                    task.files_added = files_added
                    task.files_updated = files_updated
                    task.files_unchanged = files_unchanged
                    task.chunks_indexed = chunks_indexed
                    task.topics_count = len(topic_counter)
                    task.result_json = to_json(result)
                    task.finished_at = utc_now()
                    task.updated_at = utc_now()
                    db.add(task)
                    db.commit()

            return result

        except Exception as exc:
            if task_id:
                task = db.get(IndexRebuildTask, task_id)
                if task:
                    task.status = IndexRebuildTaskStatus.FAILED
                    task.error_message = str(exc)[:500]
                    task.finished_at = utc_now()
                    task.updated_at = utc_now()
                    db.add(task)
                    db.commit()
            raise

    def _run_task(
        self,
        db: Session,
        task_id: str,
        mode: IndexRebuildMode = IndexRebuildMode.INCREMENTAL,
    ) -> None:
        """后台 worker 调用入口。"""
        task = db.get(IndexRebuildTask, task_id)
        if not task:
            return
        if task.status not in {IndexRebuildTaskStatus.QUEUED, IndexRebuildTaskStatus.RUNNING}:
            return

        task.status = IndexRebuildTaskStatus.RUNNING
        task.error_message = None
        task.started_at = task.started_at or utc_now()
        task.updated_at = utc_now()
        db.add(task)
        db.commit()

        try:
            self.rebuild(db=db, task_id=task_id, mode=mode)
        except Exception:
            pass

    def _update_indexed_file(
        self,
        db: Session,
        rel_path: str,
        content_hash: str,
        mtime: float,
        chunks_count: int,
    ) -> None:
        """更新或创建 IndexedFile 记录。"""
        existing = db.exec(
            select(IndexedFile).where(IndexedFile.rel_path == rel_path)
        ).first()
        if existing:
            existing.content_hash = content_hash
            existing.mtime = mtime
            existing.chunks_count = chunks_count
            existing.indexed_at = utc_now()
            db.add(existing)
        else:
            db.add(IndexedFile(
                rel_path=rel_path,
                content_hash=content_hash,
                mtime=mtime,
                chunks_count=chunks_count,
            ))
        db.commit()

    def _remove_file_from_index(self, db: Session, rel_path: str) -> None:
        """从索引中移除文件（增量模式下文件被删除时调用）。"""
        # 删除 IndexedFile 记录
        db.exec(delete(IndexedFile).where(IndexedFile.rel_path == rel_path))
        db.commit()
        # Note: Qdrant 中的 chunks 暂时保留，因为无法精确定位
        # 可以定期通过 full 模式重建来清理

    def _clear_collection(self) -> None:
        """清空 Qdrant collection。"""
        try:
            if self.retrieval._collection_exists():
                self.retrieval.client.delete_collection(self.retrieval.collection)
        except Exception:
            pass

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

    def _save_topics(self, db: Session, topics: Counter[str], replace: bool = True) -> None:
        if replace:
            db.exec(delete(TopicStat))
        now = utc_now()
        for topic, score in topics.most_common(300):
            if replace:
                db.add(TopicStat(topic=topic, score=score, updated_at=now))
            else:
                # 增量模式：合并统计
                existing = db.exec(
                    select(TopicStat).where(TopicStat.topic == topic)
                ).first()
                if existing:
                    existing.score += score
                    existing.updated_at = now
                    db.add(existing)
                else:
                    db.add(TopicStat(topic=topic, score=score, updated_at=now))
        db.commit()

    def _to_task_read(self, row: IndexRebuildTask) -> dict[str, Any]:
        return {
            'id': row.id,
            'status': row.status,
            'mode': row.mode,
            'files_total': row.files_total,
            'files_scanned': row.files_scanned,
            'files_added': row.files_added,
            'files_updated': row.files_updated,
            'files_unchanged': row.files_unchanged,
            'chunks_indexed': row.chunks_indexed,
            'topics_count': row.topics_count,
            'error_message': row.error_message,
            'created_at': row.created_at,
            'updated_at': row.updated_at,
            'started_at': row.started_at,
            'finished_at': row.finished_at,
        }

    @staticmethod
    def _ensure_worker_started() -> None:
        global _WORKER_STARTED
        with _WORKER_LOCK:
            if _WORKER_STARTED:
                return
            worker = Thread(target=_index_task_worker, daemon=True, name='index-rebuild-worker')
            worker.start()
            _WORKER_STARTED = True
