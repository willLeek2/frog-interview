from __future__ import annotations

import base64
from typing import Any, Literal

import httpx

from app.core.config import settings
from app.core.llm_runtime_config import runtime_llm_config


class OpenRouterClient:
    def __init__(self) -> None:
        self.base_url = settings.openrouter_base_url.rstrip('/')

    def _headers(self) -> dict[str, str]:
        if not settings.openrouter_api_key:
            raise RuntimeError('OPENROUTER_API_KEY 未配置')
        return {
            'Authorization': f'Bearer {settings.openrouter_api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://coach-app.local',
            'X-Title': 'coach-app',
        }

    def _parse_provider_order(self, raw: str | None) -> list[str]:
        if not raw:
            return []
        return [x.strip() for x in raw.split(',') if x.strip()]

    def _parse_provider_order_value(self, value: Any) -> list[str]:
        if isinstance(value, str):
            return self._parse_provider_order(value)
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        return []

    def _parse_bool(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {'true', '1', 'yes', 'on'}:
                return True
            if lowered in {'false', '0', 'no', 'off'}:
                return False
        return None

    def _parse_positive_int(self, value: Any) -> int | None:
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.strip().isdigit():
            parsed = int(value.strip())
            if parsed > 0:
                return parsed
        return None

    def _openrouter_runtime(self) -> dict[str, Any]:
        return runtime_llm_config.openrouter()

    def model_for(self, purpose: Literal['chat', 'embedding', 'audio', 'vision']) -> str:
        runtime = self._openrouter_runtime()
        runtime_key_map = {
            'chat': 'chat_model',
            'embedding': 'embedding_model',
            'audio': 'audio_model',
            'vision': 'vision_model',
        }
        runtime_model = runtime.get(runtime_key_map[purpose])
        if isinstance(runtime_model, str) and runtime_model.strip():
            return runtime_model.strip()

        defaults = {
            'chat': settings.openrouter_chat_model,
            'embedding': settings.openrouter_embedding_model,
            'audio': settings.openrouter_audio_model,
            'vision': settings.openrouter_vision_model,
        }
        return defaults[purpose]

    def _timeout_seconds(self) -> int:
        runtime_timeout = self._parse_positive_int(self._openrouter_runtime().get('timeout_seconds'))
        if runtime_timeout is not None:
            return runtime_timeout
        return settings.openrouter_timeout_seconds

    def _post(self, path: str, payload: dict[str, Any], retries: int = 2) -> dict[str, Any]:
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                with httpx.Client(timeout=self._timeout_seconds()) as client:
                    response = client.post(f'{self.base_url}{path}', headers=self._headers(), json=payload)
                    response.raise_for_status()
                    return response.json()
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                if attempt == retries:
                    break
        raise RuntimeError(f'OpenRouter 请求失败: {last_err}')

    def provider_preferences(self, purpose: Literal['chat', 'embedding', 'audio', 'vision'] = 'chat') -> dict[str, Any]:
        provider: dict[str, Any] = {
            'allow_fallbacks': settings.openrouter_allow_fallbacks,
            'sort': settings.openrouter_provider_sort,
            'data_collection': 'deny',
        }

        runtime_provider = self._openrouter_runtime().get('provider')
        if isinstance(runtime_provider, dict):
            allow_fallbacks = self._parse_bool(runtime_provider.get('allow_fallbacks'))
            if allow_fallbacks is not None:
                provider['allow_fallbacks'] = allow_fallbacks
            runtime_sort = runtime_provider.get('sort')
            if isinstance(runtime_sort, str) and runtime_sort.strip():
                provider['sort'] = runtime_sort.strip()
            runtime_data_collection = runtime_provider.get('data_collection')
            if isinstance(runtime_data_collection, str) and runtime_data_collection.strip():
                provider['data_collection'] = runtime_data_collection.strip()

        purpose_order_map = {
            'chat': settings.openrouter_chat_provider_order,
            'embedding': settings.openrouter_embedding_provider_order,
            'audio': settings.openrouter_audio_provider_order,
            'vision': settings.openrouter_vision_provider_order,
        }
        runtime_order = []
        if isinstance(runtime_provider, dict):
            runtime_order = self._parse_provider_order_value(runtime_provider.get(f'{purpose}_order'))
            if not runtime_order:
                runtime_order = self._parse_provider_order_value(runtime_provider.get('order'))

        order = (
            runtime_order
            or self._parse_provider_order(purpose_order_map.get(purpose))
            or self._parse_provider_order(settings.openrouter_provider_order)
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
        purpose: Literal['chat', 'vision'] = 'chat',
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'model': model or self.model_for(purpose),
            'messages': messages,
            'stream': False,
        }
        payload['provider'] = provider or self.provider_preferences(purpose)
        if plugins:
            payload['plugins'] = plugins
        if extra_body:
            payload.update(extra_body)
        return self._post('/chat/completions', payload)

    def embeddings(self, inputs: list[str], model: str | None = None) -> list[list[float]]:
        payload = {
            'model': model or self.model_for('embedding'),
            'input': inputs,
            'provider': self.provider_preferences('embedding'),
        }
        data = self._post('/embeddings', payload)
        return [item['embedding'] for item in data.get('data', [])]

    def transcribe_audio(self, audio_bytes: bytes, fmt: str = 'wav') -> str:
        b64 = base64.b64encode(audio_bytes).decode('utf-8')
        payload = {
            'model': self.model_for('audio'),
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
