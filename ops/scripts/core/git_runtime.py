from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from pathlib import Path


def _path_is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        try:
            path.absolute().relative_to(root.absolute())
            return True
        except ValueError:
            return False


def trusted_git_path_env(
    vault: Path,
    env: Mapping[str, str] | None = None,
) -> tuple[str, int]:
    source_env = env or os.environ
    entries: list[str] = []
    ignored = 0
    for raw_entry in source_env.get("PATH", "").split(os.pathsep):
        if raw_entry in {"", "."}:
            ignored += 1
            continue
        entry = Path(raw_entry)
        if not entry.is_absolute() or _path_is_inside(entry, vault):
            ignored += 1
            continue
        entries.append(raw_entry)
    return os.pathsep.join(entries), ignored


def resolve_trusted_git_executable(
    vault: Path,
    env: Mapping[str, str] | None = None,
) -> tuple[str | None, str, int]:
    path_text, ignored_path_entry_count = trusted_git_path_env(vault, env)
    resolved = shutil.which("git", path=path_text)
    if resolved is None:
        return None, path_text, ignored_path_entry_count
    resolved_path = Path(resolved).resolve()
    if _path_is_inside(resolved_path, vault):
        return None, path_text, ignored_path_entry_count + 1
    return str(resolved_path), path_text, ignored_path_entry_count


def trusted_git_subprocess_env(
    path_text: str,
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    subprocess_env = dict(env or os.environ)
    subprocess_env["PATH"] = path_text
    subprocess_env["GIT_OPTIONAL_LOCKS"] = "0"
    subprocess_env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess_env
