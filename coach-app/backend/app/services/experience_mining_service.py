from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from queue import Queue
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams
from sqlmodel import Session, desc, delete, select

from app.core.config import settings
from app.db.session import get_session_ctx
from app.models.experience import (
    ExperienceBatch,
    ExperienceBatchStatus,
    ExperienceImage,
    ExperienceProcessTask,
    ExperienceProcessTaskStatus,
    ExperienceQuestion,
    ExperienceQuestionCluster,
    utc_now,
)
from app.services.openrouter_client import OpenRouterClient
from app.utils.json_utils import from_json, to_json

_PROCESS_QUEUE: Queue[str] = Queue()
_WORKER_STARTED = False
_WORKER_LOCK = Lock()


def _process_task_worker() -> None:
    while True:
        task_id = _PROCESS_QUEUE.get()
        try:
            with get_session_ctx() as db:
                service = ExperienceMiningService(start_worker=False)
                service._run_task(db=db, task_id=task_id)
        except Exception:  # noqa: BLE001
            # worker 不应因为单任务失败退出
            pass
        finally:
            _PROCESS_QUEUE.task_done()


class ExperienceMiningService:
    def __init__(self, start_worker: bool = True) -> None:
        self.openrouter = OpenRouterClient()
        self.vector_client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        self.collection = settings.qdrant_experience_collection
        self.cluster_threshold = settings.experience_cluster_threshold
        if start_worker:
            self._ensure_worker_started()

    def create_batch(
        self,
        db: Session,
        files: list[Any],
        company: str | None = None,
        business_line: str | None = None,
        notes: str | None = None,
        interview_at: datetime | None = None,
    ) -> ExperienceBatch:
        if not files:
            raise ValueError('至少需要上传一张图片')
        if len(files) > settings.experience_batch_max_files:
            raise ValueError(f'单次最多上传 {settings.experience_batch_max_files} 张图片')

        batch = ExperienceBatch(
            company=(company or '').strip() or None,
            business_line=(business_line or '').strip() or None,
            notes=(notes or '').strip() or None,
            interview_at=interview_at.date() if interview_at else None,
            status=ExperienceBatchStatus.PENDING,
        )
        db.add(batch)

        upload_dir = self._batch_upload_dir(batch.id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        max_bytes = settings.experience_max_image_mb * 1024 * 1024

        try:
            for idx, file in enumerate(files, start=1):
                raw = file.file.read()
                if not raw:
                    continue
                if len(raw) > max_bytes:
                    raise ValueError(f'图片 {file.filename} 超过大小限制 {settings.experience_max_image_mb}MB')
                suffix = self._suffix_from_name(file.filename or '', file.content_type)
                saved_name = f'{idx:03d}{suffix}'
                saved_path = upload_dir / saved_name
                saved_path.write_bytes(raw)

                db.add(
                    ExperienceImage(
                        batch_id=batch.id,
                        original_name=file.filename or saved_name,
                        content_type=file.content_type,
                        file_path=str(saved_path),
                        file_size=len(raw),
                        order_index=idx,
                    )
                )
        except Exception:
            db.rollback()
            shutil.rmtree(upload_dir, ignore_errors=True)
            raise

        batch.updated_at = utc_now()
        db.add(batch)
        db.commit()
        db.refresh(batch)
        return batch

    def list_batches(self, db: Session, limit: int = 50) -> list[dict[str, Any]]:
        rows = db.exec(select(ExperienceBatch).order_by(desc(ExperienceBatch.created_at)).limit(limit)).all()
        result: list[dict[str, Any]] = []
        for row in rows:
            image_count = self._count_images(db, row.id)
            question_count = self._count_questions(db, row.id)
            result.append(
                {
                    'id': row.id,
                    'company': row.company,
                    'business_line': row.business_line,
                    'interview_at': row.interview_at,
                    'status': row.status,
                    'error_message': row.error_message,
                    'image_count': image_count,
                    'question_count': question_count,
                    'created_at': row.created_at,
                    'updated_at': row.updated_at,
                }
            )
        return result

    def get_batch_detail(self, db: Session, batch_id: str) -> dict[str, Any]:
        batch = db.get(ExperienceBatch, batch_id)
        if not batch:
            raise ValueError('批次不存在')

        images = db.exec(
            select(ExperienceImage)
            .where(ExperienceImage.batch_id == batch_id)
            .order_by(ExperienceImage.order_index)
        ).all()
        questions = db.exec(
            select(ExperienceQuestion)
            .where(ExperienceQuestion.batch_id == batch_id)
            .order_by(ExperienceQuestion.created_at)
        ).all()

        return {
            'batch': {
                'id': batch.id,
                'company': batch.company,
                'business_line': batch.business_line,
                'interview_at': batch.interview_at,
                'status': batch.status,
                'error_message': batch.error_message,
                'image_count': len(images),
                'question_count': len(questions),
                'created_at': batch.created_at,
                'updated_at': batch.updated_at,
            },
            'images': [
                {
                    'id': row.id,
                    'original_name': row.original_name,
                    'content_type': row.content_type,
                    'file_size': row.file_size,
                    'order_index': row.order_index,
                    'created_at': row.created_at,
                }
                for row in images
            ],
            'questions': [
                {
                    'id': row.id,
                    'cluster_id': row.cluster_id,
                    'question_text': row.question_text,
                    'normalized_question': row.normalized_question,
                    'topic_tags': from_json(row.topic_tags_json, []),
                    'company': row.company,
                    'business_line': row.business_line,
                    'interview_round': row.interview_round,
                    'confidence': row.confidence,
                    'extra': from_json(row.extra_json, {}),
                    'created_at': row.created_at,
                }
                for row in questions
            ],
        }

    def enqueue_process_task(self, db: Session, batch_id: str) -> dict[str, Any]:
        batch = db.get(ExperienceBatch, batch_id)
        if not batch:
            raise ValueError('批次不存在')

        existing = db.exec(
            select(ExperienceProcessTask)
            .where(ExperienceProcessTask.batch_id == batch_id)
            .where(
                ExperienceProcessTask.status.in_(
                    [ExperienceProcessTaskStatus.QUEUED, ExperienceProcessTaskStatus.RUNNING]
                )
            )
            .order_by(desc(ExperienceProcessTask.created_at))
            .limit(1)
        ).first()
        if existing:
            return {
                'task_id': existing.id,
                'batch_id': existing.batch_id,
                'status': existing.status,
                'already_exists': True,
            }

        task = ExperienceProcessTask(batch_id=batch_id, status=ExperienceProcessTaskStatus.QUEUED)
        db.add(task)
        batch.status = ExperienceBatchStatus.PENDING
        batch.updated_at = utc_now()
        db.add(batch)
        db.commit()
        db.refresh(task)

        _PROCESS_QUEUE.put(task.id)
        return {
            'task_id': task.id,
            'batch_id': task.batch_id,
            'status': task.status,
            'already_exists': False,
        }

    def get_task(self, db: Session, task_id: str) -> dict[str, Any]:
        row = db.get(ExperienceProcessTask, task_id)
        if not row:
            raise ValueError('任务不存在')
        return self._to_task_read(row)

    def list_batch_tasks(self, db: Session, batch_id: str, limit: int = 30) -> list[dict[str, Any]]:
        rows = db.exec(
            select(ExperienceProcessTask)
            .where(ExperienceProcessTask.batch_id == batch_id)
            .order_by(desc(ExperienceProcessTask.created_at))
            .limit(limit)
        ).all()
        return [self._to_task_read(x) for x in rows]

    def get_cluster_detail(self, db: Session, cluster_id: str, limit: int = 200) -> dict[str, Any]:
        cluster = db.get(ExperienceQuestionCluster, cluster_id)
        if not cluster:
            raise ValueError('题簇不存在')

        rows = db.exec(
            select(ExperienceQuestion)
            .where(ExperienceQuestion.cluster_id == cluster_id)
            .order_by(desc(ExperienceQuestion.created_at))
            .limit(limit)
        ).all()

        variants_map: dict[str, dict[str, Any]] = {}
        batch_map: dict[str, dict[str, Any]] = {}
        for row in rows:
            variant = variants_map.setdefault(
                row.normalized_question,
                {
                    'normalized_question': row.normalized_question,
                    'sample_question': row.question_text,
                    'count': 0,
                    'last_seen_at': row.created_at,
                    'companies': set(),
                },
            )
            variant['count'] += 1
            variant['last_seen_at'] = max(variant['last_seen_at'], row.created_at)
            if row.company:
                variant['companies'].add(row.company)

            if row.batch_id not in batch_map:
                batch_obj = db.get(ExperienceBatch, row.batch_id)
                batch_map[row.batch_id] = {
                    'batch_id': row.batch_id,
                    'company': batch_obj.company if batch_obj else None,
                    'business_line': batch_obj.business_line if batch_obj else None,
                    'interview_at': batch_obj.interview_at if batch_obj else None,
                    'question_count': 0,
                    'last_seen_at': row.created_at,
                }
            batch_map[row.batch_id]['question_count'] += 1
            batch_map[row.batch_id]['last_seen_at'] = max(batch_map[row.batch_id]['last_seen_at'], row.created_at)

        variants = [
            {
                'normalized_question': item['normalized_question'],
                'sample_question': item['sample_question'],
                'count': item['count'],
                'last_seen_at': item['last_seen_at'],
                'companies': sorted(item['companies']),
            }
            for item in variants_map.values()
        ]
        variants.sort(key=lambda x: x['count'], reverse=True)

        source_batches = list(batch_map.values())
        source_batches.sort(key=lambda x: x['last_seen_at'], reverse=True)

        return {
            'cluster_id': cluster.id,
            'canonical_question': cluster.canonical_question,
            'topic_tags': from_json(cluster.topic_tags_json, []),
            'companies': from_json(cluster.companies_json, []),
            'total_count': cluster.total_count,
            'first_seen_at': cluster.first_seen_at,
            'last_seen_at': cluster.last_seen_at,
            'variants': variants[:30],
            'source_batches': source_batches[:30],
        }

    def process_batch(self, db: Session, batch_id: str) -> dict[str, Any]:
        batch = db.get(ExperienceBatch, batch_id)
        if not batch:
            raise ValueError('批次不存在')

        images = db.exec(
            select(ExperienceImage)
            .where(ExperienceImage.batch_id == batch_id)
            .order_by(ExperienceImage.order_index)
        ).all()
        if not images:
            raise ValueError('该批次没有可处理图片')

        batch.status = ExperienceBatchStatus.RUNNING
        batch.error_message = None
        batch.updated_at = utc_now()
        db.add(batch)
        db.commit()

        extracted_count = 0
        created_clusters = 0
        try:
            db.exec(delete(ExperienceQuestion).where(ExperienceQuestion.batch_id == batch_id))
            db.commit()

            for image in images:
                extracted = self._extract_questions_from_image(image=image, batch=batch)
                for item in extracted:
                    raw_question = (item.get('question') or '').strip()
                    if not raw_question:
                        continue

                    # Skip personal questions that are not generally applicable
                    if item.get('is_personal') is True:
                        continue

                    normalized = self._normalize_question(raw_question)
                    if not normalized:
                        continue

                    topic_tags = self._sanitize_tags(item.get('topic_tags'))
                    is_algorithm = item.get('is_algorithm') is True

                    # Add algorithm tag if detected
                    if is_algorithm and '算法' not in topic_tags:
                        topic_tags.append('算法')

                    cluster_id, created = self._resolve_cluster(
                        db=db,
                        normalized_question=normalized,
                        topic_tags=topic_tags,
                        company=batch.company,
                    )
                    if created:
                        created_clusters += 1

                    row = ExperienceQuestion(
                        batch_id=batch.id,
                        cluster_id=cluster_id,
                        image_id=image.id,
                        question_text=raw_question,
                        normalized_question=normalized,
                        topic_tags_json=to_json(topic_tags),
                        company=batch.company,
                        business_line=batch.business_line,
                        interview_round=(item.get('interview_round') or '').strip() or None,
                        confidence=self._safe_confidence(item.get('confidence')),
                        extra_json=to_json(
                            {
                                'source_image': image.original_name,
                                'ocr_raw': item.get('ocr_raw', ''),
                                'is_algorithm': is_algorithm,
                            }
                        ),
                    )
                    db.add(row)
                    extracted_count += 1

            batch.status = ExperienceBatchStatus.COMPLETED
            batch.updated_at = utc_now()
            db.add(batch)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            batch.status = ExperienceBatchStatus.FAILED
            batch.error_message = str(exc)[:500]
            batch.updated_at = utc_now()
            db.add(batch)
            db.commit()
            raise

        return {
            'batch_id': batch.id,
            'status': batch.status,
            'questions_extracted': extracted_count,
            'clusters_created': created_clusters,
        }

    def delete_question(self, db: Session, batch_id: str, question_id: str) -> None:
        question = db.get(ExperienceQuestion, question_id)
        if not question:
            raise ValueError('题目不存在')
        if question.batch_id != batch_id:
            raise ValueError('题目不属于该批次')
        db.delete(question)
        db.commit()

        # 更新题簇计数
        cluster = db.get(ExperienceQuestionCluster, question.cluster_id)
        if cluster:
            cluster.total_count = max(0, cluster.total_count - 1)
            cluster.last_seen_at = utc_now()
            db.add(cluster)
            db.commit()

    def list_algorithm_questions(
        self,
        db: Session,
        batch_id: str | None = None,
        company: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        from sqlmodel import select
        from app.utils.json_utils import from_json

        stmt = select(ExperienceQuestion).order_by(desc(ExperienceQuestion.created_at))
        if batch_id:
            stmt = stmt.where(ExperienceQuestion.batch_id == batch_id)
        if company:
            stmt = stmt.where(ExperienceQuestion.company == company)
        stmt = stmt.limit(limit)

        rows = db.exec(stmt).all()
        result: list[dict[str, Any]] = []

        for row in rows:
            extra = from_json(row.extra_json, {})
            # Check if this is an algorithm question
            is_algorithm = extra.get('is_algorithm') is True
            tags = from_json(row.topic_tags_json, [])
            if not is_algorithm and '算法' not in tags:
                continue

            result.append({
                'id': row.id,
                'question_text': row.question_text,
                'normalized_question': row.normalized_question,
                'topic_tags': tags,
                'company': row.company,
                'business_line': row.business_line,
                'interview_round': row.interview_round,
                'confidence': row.confidence,
                'batch_id': row.batch_id,
                'cluster_id': row.cluster_id,
                'created_at': row.created_at,
            })

        return result

    def hot_questions(
        self,
        db: Session,
        days: int | None = None,
        company: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        lookback_days = days or settings.experience_hot_default_days
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)

        stmt = select(ExperienceQuestion).where(ExperienceQuestion.created_at >= cutoff)
        if company:
            stmt = stmt.where(ExperienceQuestion.company == company)
        rows = db.exec(stmt).all()

        grouped: dict[str, list[ExperienceQuestion]] = {}
        for row in rows:
            grouped.setdefault(row.cluster_id, []).append(row)

        result: list[dict[str, Any]] = []
        for cluster_id, items in grouped.items():
            cluster = db.get(ExperienceQuestionCluster, cluster_id)
            canonical = cluster.canonical_question if cluster else items[0].normalized_question
            tags = from_json(cluster.topic_tags_json if cluster else items[0].topic_tags_json, [])
            companies = from_json(cluster.companies_json if cluster else None, [])
            if not companies:
                companies = sorted({x.company for x in items if x.company})
            last_seen = max(x.created_at for x in items)
            result.append(
                {
                    'cluster_id': cluster_id,
                    'canonical_question': canonical,
                    'topic_tags': tags,
                    'companies': companies,
                    'total_count': len(items),
                    'last_seen_at': last_seen,
                }
            )

        result.sort(key=lambda x: x['total_count'], reverse=True)
        return result[:limit]

    def _extract_questions_from_image(
        self,
        image: ExperienceImage,
        batch: ExperienceBatch,
    ) -> list[dict[str, Any]]:
        image_bytes = Path(image.file_path).read_bytes()
        mime = image.content_type or self._mime_from_suffix(Path(image.file_path).suffix)
        data_uri = f'data:{mime};base64,{base64.b64encode(image_bytes).decode("utf-8")}'

        metadata_hint = {
            'company': batch.company or '',
            'business_line': batch.business_line or '',
            'notes': batch.notes or '',
        }
        instruction = (
            'You are extracting interview questions from screenshot images.\n'
            'Return only JSON and focus on user-visible interview questions.\n'
            'Keep question wording close to the original text.\n\n'
            'IMPORTANT FILTERING RULES:\n'
            '1. Skip questions that are highly personal to the interviewee (e.g., about their own past internships, '
            'personal projects, or unique experiences that are not generally applicable to other candidates).\n'
            '2. Keep only questions that have general applicability to other interview candidates.\n'
            '3. Mark algorithm/coding questions containing "手撕", "算法题", "coding", "算法", "编程题" as is_algorithm=true.\n\n'
            f'Metadata hint: {json.dumps(metadata_hint, ensure_ascii=False)}'
        )
        response_schema = {
            'type': 'json_schema',
            'json_schema': {
                'name': 'experience_extract',
                'strict': True,
                'schema': {
                    'type': 'object',
                    'additionalProperties': False,
                    'properties': {
                        'questions': {
                            'type': 'array',
                            'items': {
                                'type': 'object',
                                'additionalProperties': False,
                                'properties': {
                                    'question': {'type': 'string'},
                                    'topic_tags': {'type': 'array', 'items': {'type': 'string'}},
                                    'interview_round': {'type': 'string'},
                                    'confidence': {'type': 'number'},
                                    'ocr_raw': {'type': 'string'},
                                    'is_personal': {'type': 'boolean'},
                                    'is_algorithm': {'type': 'boolean'},
                                },
                                'required': ['question', 'topic_tags', 'interview_round', 'confidence', 'ocr_raw', 'is_personal', 'is_algorithm'],
                            },
                        }
                    },
                    'required': ['questions'],
                },
            },
        }

        try:
            data = self.openrouter.chat_completion(
                model=self.openrouter.model_for('vision'),
                messages=[
                    {
                        'role': 'user',
                        'content': [
                            {'type': 'text', 'text': instruction},
                            {'type': 'image_url', 'image_url': {'url': data_uri}},
                        ],
                    }
                ],
                provider=self.openrouter.provider_preferences('vision'),
                extra_body={'response_format': response_schema},
            )
            content = self._extract_content_text(data)
            parsed = self._parse_json_content(content)
            questions = parsed.get('questions', [])
            if isinstance(questions, list):
                return [x for x in questions if isinstance(x, dict)]
        except Exception:  # noqa: BLE001
            pass

        # 兼容：结构化输出不可用时，退化为文本 JSON 指令
        fallback = self.openrouter.chat_completion(
            model=self.openrouter.model_for('vision'),
            messages=[
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'text',
                            'text': (
                                instruction
                                + '\nReturn strict JSON object with key "questions".'
                                ' No markdown wrapper.'
                            ),
                        },
                        {'type': 'image_url', 'image_url': {'url': data_uri}},
                    ],
                }
            ],
            provider=self.openrouter.provider_preferences('vision'),
        )
        text = self._extract_content_text(fallback)
        parsed = self._parse_json_content(text)
        items = parsed.get('questions', [])
        if not isinstance(items, list):
            return []
        return [x for x in items if isinstance(x, dict)]

    def _resolve_cluster(
        self,
        db: Session,
        normalized_question: str,
        topic_tags: list[str],
        company: str | None,
    ) -> tuple[str, bool]:
        # 先尝试精确命中，避免重复调用向量接口
        existed = db.exec(
            select(ExperienceQuestion)
            .where(ExperienceQuestion.normalized_question == normalized_question)
            .order_by(desc(ExperienceQuestion.created_at))
            .limit(1)
        ).first()
        if existed:
            self._touch_cluster(db, existed.cluster_id, normalized_question, topic_tags, company)
            return existed.cluster_id, False

        try:
            vector = self.openrouter.embeddings([normalized_question])[0]
            self._ensure_collection(len(vector))
            result = self.vector_client.query_points(
                collection_name=self.collection,
                query=vector,
                limit=1,
                with_payload=True,
            )
            if result.points:
                top = result.points[0]
                payload = top.payload or {}
                cluster_id = payload.get('cluster_id')
                if cluster_id and float(top.score) >= self.cluster_threshold:
                    self._touch_cluster(db, str(cluster_id), normalized_question, topic_tags, company)
                    return str(cluster_id), False
        except Exception:  # noqa: BLE001
            pass

        cluster_id = str(uuid4())
        self._touch_cluster(db, cluster_id, normalized_question, topic_tags, company)

        try:
            vector = self.openrouter.embeddings([normalized_question])[0]
            point_id = hashlib.sha1(cluster_id.encode('utf-8')).hexdigest()
            self._ensure_collection(len(vector))
            self.vector_client.upsert(
                collection_name=self.collection,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            'cluster_id': cluster_id,
                            'canonical_question': normalized_question,
                            'company': company or '',
                        },
                    )
                ],
                wait=True,
            )
        except Exception:  # noqa: BLE001
            pass

        return cluster_id, True

    def _touch_cluster(
        self,
        db: Session,
        cluster_id: str,
        canonical_question: str,
        topic_tags: list[str],
        company: str | None,
    ) -> None:
        row = db.get(ExperienceQuestionCluster, cluster_id)
        now = utc_now()
        if not row:
            row = ExperienceQuestionCluster(
                id=cluster_id,
                canonical_question=canonical_question,
                topic_tags_json=to_json(topic_tags),
                companies_json=to_json([company] if company else []),
                first_seen_at=now,
                last_seen_at=now,
                total_count=0,
            )

        tags = from_json(row.topic_tags_json, [])
        for t in topic_tags:
            if t not in tags:
                tags.append(t)
        companies = from_json(row.companies_json, [])
        if company and company not in companies:
            companies.append(company)

        row.canonical_question = row.canonical_question or canonical_question
        row.topic_tags_json = to_json(tags[:20])
        row.companies_json = to_json(companies[:20])
        row.last_seen_at = now
        row.total_count += 1
        db.add(row)

    def _to_task_read(self, row: ExperienceProcessTask) -> dict[str, Any]:
        return {
            'id': row.id,
            'batch_id': row.batch_id,
            'status': row.status,
            'result': from_json(row.result_json, {}),
            'error_message': row.error_message,
            'created_at': row.created_at,
            'updated_at': row.updated_at,
            'started_at': row.started_at,
            'finished_at': row.finished_at,
        }

    def _run_task(self, db: Session, task_id: str) -> None:
        task = db.get(ExperienceProcessTask, task_id)
        if not task:
            return
        if task.status not in {ExperienceProcessTaskStatus.QUEUED, ExperienceProcessTaskStatus.RUNNING}:
            return

        task.status = ExperienceProcessTaskStatus.RUNNING
        task.error_message = None
        task.started_at = task.started_at or utc_now()
        task.updated_at = utc_now()
        db.add(task)
        db.commit()

        try:
            result = self.process_batch(db=db, batch_id=task.batch_id)
            task.status = ExperienceProcessTaskStatus.COMPLETED
            task.result_json = to_json(result)
            task.error_message = None
        except Exception as exc:  # noqa: BLE001
            task.status = ExperienceProcessTaskStatus.FAILED
            task.result_json = None
            task.error_message = str(exc)[:500]
        finally:
            task.finished_at = utc_now()
            task.updated_at = utc_now()
            db.add(task)
            db.commit()

    @staticmethod
    def _ensure_worker_started() -> None:
        global _WORKER_STARTED
        with _WORKER_LOCK:
            if _WORKER_STARTED:
                return
            worker = Thread(target=_process_task_worker, daemon=True, name='experience-process-worker')
            worker.start()
            _WORKER_STARTED = True

    def _count_images(self, db: Session, batch_id: str) -> int:
        rows = db.exec(select(ExperienceImage.id).where(ExperienceImage.batch_id == batch_id)).all()
        return len(rows)

    def _count_questions(self, db: Session, batch_id: str) -> int:
        rows = db.exec(select(ExperienceQuestion.id).where(ExperienceQuestion.batch_id == batch_id)).all()
        return len(rows)

    def _batch_upload_dir(self, batch_id: str) -> Path:
        return Path(settings.data_dir) / 'experience_uploads' / batch_id

    def _ensure_collection(self, vector_size: int) -> None:
        try:
            names = [x.name for x in self.vector_client.get_collections().collections]
            if self.collection in names:
                return
            self.vector_client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
        except Exception:  # noqa: BLE001
            pass

    def _extract_content_text(self, data: dict[str, Any]) -> str:
        content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    value = item.get('text')
                    if isinstance(value, str):
                        parts.append(value)
            return '\n'.join(parts)
        return ''

    def _parse_json_content(self, text: str) -> dict[str, Any]:
        clean = text.strip()
        if clean.startswith('```'):
            clean = re.sub(r'^```(?:json)?\s*', '', clean, flags=re.IGNORECASE).strip()
            clean = re.sub(r'\s*```$', '', clean).strip()
        start = clean.find('{')
        end = clean.rfind('}')
        if start >= 0 and end > start:
            clean = clean[start : end + 1]
        try:
            data = json.loads(clean)
            if isinstance(data, dict):
                return data
        except Exception:  # noqa: BLE001
            pass
        return {'questions': []}

    def _normalize_question(self, text: str) -> str:
        x = text.strip()
        x = re.sub(r'\s+', ' ', x)
        x = x.replace('？', '?')
        return x[:500]

    def _sanitize_tags(self, tags: Any) -> list[str]:
        if not isinstance(tags, list):
            return []
        result: list[str] = []
        for item in tags:
            if not isinstance(item, str):
                continue
            val = item.strip()
            if not val:
                continue
            if val not in result:
                result.append(val[:32])
        return result[:12]

    def _safe_confidence(self, value: Any) -> float:
        try:
            x = float(value)
        except Exception:  # noqa: BLE001
            return 0.0
        return max(0.0, min(1.0, x))

    def _suffix_from_name(self, name: str, content_type: str | None) -> str:
        suffix = Path(name).suffix.lower()
        if suffix in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}:
            return suffix
        return self._suffix_from_content_type(content_type)

    def _suffix_from_content_type(self, content_type: str | None) -> str:
        mapping = {
            'image/png': '.png',
            'image/jpeg': '.jpg',
            'image/webp': '.webp',
            'image/gif': '.gif',
        }
        return mapping.get((content_type or '').lower(), '.jpg')

    def _mime_from_suffix(self, suffix: str) -> str:
        mapping = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.webp': 'image/webp',
            '.gif': 'image/gif',
        }
        return mapping.get(suffix.lower(), 'image/jpeg')
