from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _sanitize_root_strings(*roots: Path) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for root in roots:
        variants: list[str] = []
        for candidate in (root, root.absolute()):
            candidate_text = candidate.as_posix().rstrip("/")
            if candidate_text:
                variants.append(candidate_text)
        try:
            resolved_text = root.resolve().as_posix().rstrip("/")
        except OSError:
            resolved_text = ""
        if resolved_text:
            variants.append(resolved_text)
        for root_text in variants:
            key = root_text.lower()
            if not root_text or key in seen:
                continue
            seen.add(key)
            normalized.append(root_text)
    normalized.sort(key=len, reverse=True)
    return normalized


def _sanitize_path_text(text: str, *, roots: list[Path]) -> str:
    sanitized = text.replace("\\", "/")
    for root_text in _sanitize_root_strings(*roots):
        sanitized = re.sub(re.escape(f"{root_text}/"), "", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(re.escape(root_text), ".", sanitized, flags=re.IGNORECASE)
    return sanitized


def _sanitize_argv(argv: list[str], *, roots: list[Path]) -> list[str]:
    return [_sanitize_path_text(item, roots=roots) for item in argv]


def _sanitize_json_strings(value: Any, *, roots: list[Path]) -> Any:
    if isinstance(value, str):
        return _sanitize_path_text(value, roots=roots)
    if isinstance(value, list):
        return [_sanitize_json_strings(item, roots=roots) for item in value]
    if isinstance(value, dict):
        return {
            _sanitize_path_text(key, roots=roots) if isinstance(key, str) else key: _sanitize_json_strings(
                item,
                roots=roots,
            )
            for key, item in value.items()
        }
    return value


def _display_command_argv(argv: list[str]) -> list[str]:
    if not argv:
        return []
    executable_name = Path(argv[0]).name.lower()
    if executable_name in {"codex", "codex.exe", "codex.cmd", "codex.ps1", "codex.js"}:
        return ["codex", *argv[1:]]
    return list(argv)
