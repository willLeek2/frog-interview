from __future__ import annotations

import random
from typing import Any, Callable

from sqlmodel import Session, desc, select

from app.models.chat import ChatMessage, ChatRunStage, ChatSession, FeatureType, TopicStat
from app.schemas.chat import AssistantReply, Citation
from app.services.openrouter_client import OpenRouterClient
from app.services.retrieval_service import RetrievalService
from app.services.web_research_service import WebResearchService


class CoachService:
    def __init__(self) -> None:
        self.openrouter = OpenRouterClient()
        self.retrieval = RetrievalService()
        self.web_research = WebResearchService()

    def generate_reply(
        self,
        db: Session,
        session: ChatSession,
        user_message: str,
        on_progress: Callable[[ChatRunStage, str, str], None] | None = None,
    ) -> AssistantReply:
        def report(stage: ChatRunStage, label: str, detail: str = '') -> None:
            if on_progress:
                on_progress(stage, label, detail)

        history = self._load_recent_history(db, session.id)

        report(ChatRunStage.TOOL_CALL, '本地向量检索中', '正在执行 embedding 检索候选资料')
        local_hits = self.retrieval.search(user_message)
        report(ChatRunStage.LOCAL_RETRIEVAL, '本地资料检索完成', f'命中 {len(local_hits)} 条资料片段')
        local_context = self._format_local_context(local_hits)
        citations = self._local_citations(local_hits)

        system_prompt = self._system_prompt_by_feature(session.feature)
        extra_user_context = ''
        metadata: dict[str, Any] = {'feature': session.feature.value}

        if session.feature == FeatureType.EXPLAIN:
            report(ChatRunStage.WEB_RESEARCH, '外网检索中', '正在调用搜索与网页抓取工具')
            try:
                web_data = self.web_research.run_hybrid(user_message)
                metadata['web_provider'] = web_data.get('provider')
                metadata['web_search_results_count'] = len(web_data.get('search_results', []))
                web_context = self._format_web_context(web_data)
                extra_user_context = (
                    f'\n\n[外网检索摘要]\n{web_data.get("answer", "")}\n\n'
                    f'[外网抓取正文]\n{web_context}\n'
                )
                citations.extend(self._web_citations(web_data))
            except Exception:
                report(ChatRunStage.WEB_RESEARCH, '外网检索降级', '主检索失败，切换 OpenRouter Web 回退')
                fallback = self.web_research.fallback_with_openrouter_web(user_message)
                metadata['web_provider'] = fallback.get('provider')
                extra_user_context = f'\n\n[外网检索摘要]\n{fallback.get("answer", "")}\n'
                citations.extend(self._fallback_citations(fallback))

        elif session.feature == FeatureType.RANDOM:
            random_topic = self._pick_random_topic(db)
            metadata['random_topic'] = random_topic
            extra_user_context = f'\n\n[随机题目主题建议]\n{random_topic}'

        messages = [{'role': 'system', 'content': system_prompt}]
        messages.extend(history)
        messages.append(
            {
                'role': 'user',
                'content': (
                    f'{user_message}\n\n[本地资料上下文]\n{local_context[:6000]}'
                    f'{extra_user_context}'
                ),
            }
        )

        report(ChatRunStage.LLM_GENERATION, '生成回答中', '正在综合资料组织最终回答')
        data = self.openrouter.chat_completion(
            messages=messages,
            provider=self.openrouter.default_provider_preferences(),
        )
        content = (
            data.get('choices', [{}])[0]
            .get('message', {})
            .get('content', '暂时没有生成有效回答，请重试。')
        )
        if not content.strip():
            content = '暂时没有生成有效回答，请重试。'

        return AssistantReply(content=content, citations=citations[:20], metadata=metadata)

    def _load_recent_history(self, db: Session, session_id: str, max_items: int = 12) -> list[dict[str, str]]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(desc(ChatMessage.created_at))
            .limit(max_items)
        )
        rows = list(reversed(db.exec(stmt).all()))
        return [{'role': row.role.value, 'content': row.content} for row in rows]

    def _system_prompt_by_feature(self, feature: FeatureType) -> str:
        common = (
            '你是 Java 后端面试辅导助手。优先使用本地资料结论。回答结构：\n'
            '1) 直接回答（必须详细，按定义/结论 -> 核心机制 -> 边界条件展开）\n'
            '2) 面试关联考点\n'
            '3) 面试官追问与回答要点\n'
            '4) 回答必讲点（面试官希望听到的关键点清单）\n'
            '5) 资料定位（本地路径+关键词）\n'
            '默认中文。内容务实，不空泛。'
        )

        if feature == FeatureType.EXPLAIN:
            return common + '\nExplain 模式要求：本地资料优先；若有外网上下文，结合近半年英文信息。'
        if feature == FeatureType.RANDOM:
            return (
                common
                + '\n随机抽题模式：先出1题；用户作答后给参考答案要点、评分建议和资料定位。不输出固定话术模板。'
            )
        return common + '\n出题模式：围绕用户给定主题出题，给答案要点和追问。不输出固定话术模板。'

    def _format_local_context(self, hits: list[dict[str, Any]]) -> str:
        if not hits:
            return '无本地检索结果。'
        parts: list[str] = []
        for idx, item in enumerate(hits, start=1):
            parts.append(
                f'[{idx}] path={item.get("source_path")} title={item.get("source_title")}\n{item.get("content")[:900]}'
            )
        return '\n\n'.join(parts)

    def _format_web_context(self, data: dict[str, Any]) -> str:
        pages = data.get('crawled_pages', [])
        if not pages:
            return '无抓取正文。'
        lines: list[str] = []
        for i, page in enumerate(pages, start=1):
            lines.append(f'[{i}] {page.get("title")} ({page.get("url")})\n{page.get("content", "")[:1500]}')
        return '\n\n'.join(lines)

    def _local_citations(self, hits: list[dict[str, Any]]) -> list[Citation]:
        return [
            Citation(
                title=item.get('source_title') or 'local-doc',
                url=item.get('source_path'),
                snippet=(item.get('content') or '')[:200],
                source='local',
            )
            for item in hits
        ]

    def _web_citations(self, data: dict[str, Any]) -> list[Citation]:
        citations: list[Citation] = []
        for item in data.get('search_results', [])[:8]:
            citations.append(
                Citation(
                    title=item.get('title'),
                    url=item.get('url'),
                    snippet=item.get('snippet', ''),
                    source='web',
                )
            )
        return citations

    def _fallback_citations(self, data: dict[str, Any]) -> list[Citation]:
        result: list[Citation] = []
        for ann in data.get('annotations', []):
            url_obj = ann.get('url_citation') or {}
            if not url_obj:
                continue
            result.append(
                Citation(
                    title=url_obj.get('title'),
                    url=url_obj.get('url'),
                    snippet=url_obj.get('content', ''),
                    source='web',
                )
            )
        return result

    def _pick_random_topic(self, db: Session) -> str:
        stmt = select(TopicStat).order_by(desc(TopicStat.score)).limit(80)
        topics = db.exec(stmt).all()
        if not topics:
            return 'MySQL 事务隔离与 MVCC'
        weighted: list[str] = []
        for row in topics:
            weight = max(1, min(8, row.score))
            weighted.extend([row.topic] * weight)
        return random.choice(weighted)
