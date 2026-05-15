from __future__ import annotations

from pathlib import Path

from ops.scripts.path_runtime import normalize_repo_path_text
from ops.scripts.policy_runtime import report_path


def current_repo_target_path(vault: Path, path: str) -> str | None:
    normalized = normalize_repo_path_text(path)
    if normalized is None:
        return None

    if (vault / normalized).exists():
        return normalized

    parts = normalized.split("/")
    if len(parts) == 3 and parts[:2] == ["ops", "scripts"] and parts[2].endswith(".py"):
        matches = sorted((vault / "ops" / "scripts").glob(f"*/{parts[2]}"))
        if len(matches) == 1:
            return report_path(vault, matches[0])

    return normalized


def current_repo_target_paths(vault: Path, paths: list[str]) -> list[str]:
    resolved: dict[str, None] = {}
    for path in paths:
        current = current_repo_target_path(vault, path)
        if current:
            resolved[current] = None
    return list(resolved)
