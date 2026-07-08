from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .git_runtime import resolve_trusted_git_executable, trusted_git_subprocess_env


@dataclass(frozen=True)
class SourceRevision:
    revision: str
    status: str


def _git_head(vault: Path) -> str:
    git_executable, path_text, _ignored_path_entry_count = resolve_trusted_git_executable(
        vault
    )
    if git_executable is None:
        return ""
    try:
        completed = subprocess.run(
            [git_executable, "rev-parse", "HEAD"],
            cwd=vault,
            check=False,
            text=True,
            capture_output=True,
            env=trusted_git_subprocess_env(path_text),
        )
    except OSError:
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def resolve_source_revision(vault: Path) -> SourceRevision:
    commit = _git_head(vault)
    if commit:
        return SourceRevision(revision=commit, status="git_head")
    if (vault / ".git").exists():
        return SourceRevision(revision="git_unavailable", status="git_unavailable")
    return SourceRevision(
        revision="source_package_without_git",
        status="source_package_without_git",
    )
