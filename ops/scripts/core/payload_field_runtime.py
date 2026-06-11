from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def dict_field(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}
