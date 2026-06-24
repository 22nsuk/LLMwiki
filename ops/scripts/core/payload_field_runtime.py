from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def dict_field(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def bool_at(payload: Mapping[str, Any], path: tuple[str, ...]) -> bool:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return False
        value = value.get(key)
    return bool(value)


def str_at(payload: Mapping[str, Any], path: tuple[str, ...], default: str = "") -> str:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    text = str(value or "").strip()
    return text or default


def int_at(payload: Mapping[str, Any], path: tuple[str, ...], default: int = 0) -> int:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
