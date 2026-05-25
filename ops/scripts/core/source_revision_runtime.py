from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceRevision:
    revision: str
    status: str


def _git_head(vault: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=vault,
            check=False,
            text=True,
            capture_output=True,
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
