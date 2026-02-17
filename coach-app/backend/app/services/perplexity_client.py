from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class PerplexityClient:
    def __init__(self) -> None:
        self.base_url = settings.perplexity_base_url.rstrip('/')
        self.timeout = settings.perplexity_timeout_seconds

    def _headers(self) -> dict[str, str]:
        if not settings.perplexity_api_key:
            raise RuntimeError('PERPLEXITY_API_KEY 未配置')
        return {
            'Authorization': f'Bearer {settings.perplexity_api_key}',
            'Content-Type': 'application/json',
        }

    def search_answer(self, query: str) -> dict[str, Any]:
        payload = {
            'model': settings.perplexity_model,
            'messages': [
                {
                    'role': 'system',
                    'content': (
                        'You are a research assistant. Use recent English sources from the last 6 months '
                        'when possible, and provide concise factual output.'
                    ),
                },
                {'role': 'user', 'content': query},
            ],
            'stream': False,
            'search_mode': 'web',
            'search_language_filter': ['en'],
            'search_recency_filter': 'month',
            'return_related_questions': False,
            'web_search_options': {'search_context_size': 'high'},
        }

        last_err: Exception | None = None
        for attempt in range(3):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        f'{self.base_url}/chat/completions',
                        headers=self._headers(),
                        json=payload,
                    )
                    resp.raise_for_status()
                    return resp.json()
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                if attempt == 2:
                    break
        raise RuntimeError(f'Perplexity 请求失败: {last_err}')
