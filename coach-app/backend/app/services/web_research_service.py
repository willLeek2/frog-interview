from __future__ import annotations

from typing import Any

from app.services.jina_client import JinaReaderClient
from app.services.openrouter_client import OpenRouterClient
from app.services.perplexity_client import PerplexityClient


class WebResearchService:
    def __init__(self) -> None:
        self.pplx = PerplexityClient()
        self.jina = JinaReaderClient()
        self.openrouter = OpenRouterClient()

    def run_hybrid(self, query: str) -> dict[str, Any]:
        pplx_data = self.pplx.search_answer(query)

        answer_text = (
            pplx_data.get('choices', [{}])[0]
            .get('message', {})
            .get('content', '')
            .strip()
        )
        search_results = pplx_data.get('search_results') or []
        citations = pplx_data.get('citations') or []

        crawled_pages: list[dict[str, str]] = []
        for item in search_results[:3]:
            url = item.get('url')
            if not url:
                continue
            try:
                content = self.jina.read_url(url)
                crawled_pages.append(
                    {
                        'url': url,
                        'title': item.get('title', ''),
                        'content': content[:5000],
                    }
                )
            except Exception:  # noqa: BLE001
                # 单个页面抓取失败不影响主流程
                continue

        return {
            'provider': 'pplx+jina',
            'answer': answer_text,
            'search_results': search_results,
            'citations': citations,
            'crawled_pages': crawled_pages,
        }

    def fallback_with_openrouter_web(self, query: str) -> dict[str, Any]:
        data = self.openrouter.chat_completion(
            messages=[
                {
                    'role': 'user',
                    'content': (
                        'Search the web and answer using recent English sources in the last 6 months. '
                        f'Question: {query}'
                    ),
                }
            ],
            plugins=[{'id': 'web'}],
        )
        choice = data.get('choices', [{}])[0]
        message = choice.get('message', {})
        annotations = message.get('annotations', [])
        return {
            'provider': 'openrouter-web-plugin',
            'answer': message.get('content', ''),
            'annotations': annotations,
        }
