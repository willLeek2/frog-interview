from __future__ import annotations

import base64
from typing import Any, Literal

import httpx

from app.core.config import settings


class OpenRouterClient:
    def __init__(self) -> None:
        self.base_url = settings.openrouter_base_url.rstrip('/')
        self.timeout = settings.openrouter_timeout_seconds

    def _headers(self) -> dict[str, str]:
        if not settings.openrouter_api_key:
            raise RuntimeError('OPENROUTER_API_KEY 未配置')
        return {
            'Authorization': f'Bearer {settings.openrouter_api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://coach-app.local',
            'X-Title': 'coach-app',
        }

    def _post(self, path: str, payload: dict[str, Any], retries: int = 2) -> dict[str, Any]:
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(f'{self.base_url}{path}', headers=self._headers(), json=payload)
                    response.raise_for_status()
                    return response.json()
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                if attempt == retries:
                    break
        raise RuntimeError(f'OpenRouter 请求失败: {last_err}')

    def _parse_provider_order(self, raw: str | None) -> list[str]:
        if not raw:
            return []
        return [x.strip() for x in raw.split(',') if x.strip()]

    def provider_preferences(self, purpose: Literal['chat', 'embedding', 'audio', 'vision'] = 'chat') -> dict[str, Any]:
        provider: dict[str, Any] = {
            'allow_fallbacks': settings.openrouter_allow_fallbacks,
            'sort': settings.openrouter_provider_sort,
            'data_collection': 'deny',
        }
        purpose_order_map = {
            'chat': settings.openrouter_chat_provider_order,
            'embedding': settings.openrouter_embedding_provider_order,
            'audio': settings.openrouter_audio_provider_order,
            'vision': settings.openrouter_vision_provider_order,
        }
        order = self._parse_provider_order(purpose_order_map.get(purpose)) or self._parse_provider_order(
            settings.openrouter_provider_order
        )
        if order:
            provider['order'] = order
        return provider

    def default_provider_preferences(self) -> dict[str, Any]:
        return self.provider_preferences('chat')

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        provider: dict[str, Any] | None = None,
        plugins: list[dict[str, Any]] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'model': model or settings.openrouter_chat_model,
            'messages': messages,
            'stream': False,
        }
        payload['provider'] = provider or self.provider_preferences('chat')
        if plugins:
            payload['plugins'] = plugins
        if extra_body:
            payload.update(extra_body)
        return self._post('/chat/completions', payload)

    def embeddings(self, inputs: list[str], model: str | None = None) -> list[list[float]]:
        payload = {
            'model': model or settings.openrouter_embedding_model,
            'input': inputs,
            'provider': self.provider_preferences('embedding'),
        }
        data = self._post('/embeddings', payload)
        return [item['embedding'] for item in data.get('data', [])]

    def transcribe_audio(self, audio_bytes: bytes, fmt: str = 'wav') -> str:
        b64 = base64.b64encode(audio_bytes).decode('utf-8')
        payload = {
            'model': settings.openrouter_audio_model,
            'messages': [
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': 'Please transcribe this audio to plain text.'},
                        {'type': 'input_audio', 'input_audio': {'data': b64, 'format': fmt}},
                    ],
                }
            ],
            'stream': False,
            'provider': self.provider_preferences('audio'),
        }
        data = self._post('/chat/completions', payload)
        choices = data.get('choices', [])
        if not choices:
            return ''
        return choices[0].get('message', {}).get('content', '')
