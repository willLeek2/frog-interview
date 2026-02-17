from __future__ import annotations

import json
from typing import Any


def to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def from_json(data: str | None, fallback: Any) -> Any:
    if not data:
        return fallback
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return fallback
