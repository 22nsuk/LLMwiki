from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_object_from_path(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def load_json_object_from_vault(vault: Path, rel_path: str) -> dict[str, Any]:
    return load_json_object_from_path(vault / rel_path)
