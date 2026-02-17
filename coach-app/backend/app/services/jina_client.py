from __future__ import annotations

from urllib.parse import quote

import httpx

from app.core.config import settings


class JinaReaderClient:
    def __init__(self) -> None:
        self.base_url = settings.jina_reader_base_url.rstrip('/')
        self.timeout = settings.jina_timeout_seconds

    def _headers(self) -> dict[str, str]:
        headers = {
            'Accept': 'text/plain',
            'x-cache-tolerance': '60',
        }
        if settings.jina_api_key:
            headers['Authorization'] = f'Bearer {settings.jina_api_key}'
        return headers

    def read_url(self, url: str, bypass_cache: bool = False) -> str:
        safe_url = quote(url, safe=':/?&=#%')
        endpoint = f'{self.base_url}/{safe_url}'
        headers = self._headers()
        if bypass_cache:
            headers['x-no-cache'] = 'true'

        last_err: Exception | None = None
        for attempt in range(3):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.get(endpoint, headers=headers)
                    resp.raise_for_status()
                    return resp.text
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                if attempt == 2:
                    break
        raise RuntimeError(f'Jina Reader 请求失败: {last_err}')
