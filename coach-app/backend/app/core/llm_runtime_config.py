from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)
BACKEND_DIR = Path(__file__).resolve().parents[2]


class LlmRuntimeConfigLoader:
    def __init__(self) -> None:
        self._lock = Lock()
        self._cached_path: Path | None = None
        self._cached_mtime_ns: int | None = None
        self._cached_config: dict[str, Any] = {}

    def _resolve_path(self) -> Path:
        path = Path(settings.llms_config_path).expanduser()
        if not path.is_absolute():
            path = BACKEND_DIR / path
        return path

    def _reset_cache_if_same_path(self, path: Path) -> None:
        with self._lock:
            if self._cached_path == path:
                self._cached_mtime_ns = None
                self._cached_config = {}

    def _load_json(self, path: Path) -> dict[str, Any]:
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
        except Exception as exc:  # noqa: BLE001
            logger.warning('解析 llms.local.json 失败，将回退到环境变量配置: path=%s err=%s', path, exc)
            with self._lock:
                if self._cached_path == path and self._cached_config:
                    return self._cached_config
            return {}

        if not isinstance(raw, dict):
            logger.warning('llms.local.json 顶层必须是 object，将回退到环境变量配置: path=%s', path)
            return {}
        return raw

    def load(self) -> dict[str, Any]:
        path = self._resolve_path()
        try:
            mtime_ns = path.stat().st_mtime_ns
        except FileNotFoundError:
            self._reset_cache_if_same_path(path)
            return {}
        except OSError as exc:
            logger.warning('读取 llms.local.json 失败，将回退到环境变量配置: path=%s err=%s', path, exc)
            return {}

        with self._lock:
            if self._cached_path == path and self._cached_mtime_ns == mtime_ns:
                return self._cached_config

        data = self._load_json(path)
        with self._lock:
            self._cached_path = path
            self._cached_mtime_ns = mtime_ns
            self._cached_config = data
            return self._cached_config

    def openrouter(self) -> dict[str, Any]:
        data = self.load()
        node = data.get('openrouter')
        if isinstance(node, dict):
            return node
        return {}


runtime_llm_config = LlmRuntimeConfigLoader()
