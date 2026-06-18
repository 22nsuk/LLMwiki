from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .codex_exec_executor import _ExecutionSummary

NON_WORKER_INTEGRITY_IGNORE_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    ".coverage",
    ".DS_Store",
    ".git",
    ".obsidian",
    ".venv",
    ".idea",
    ".vscode",
}
NON_WORKER_INTEGRITY_IGNORE_SUFFIXES = {".pyc", ".pyo"}


def _is_non_worker_integrity_ignored(rel_path: str, *, run_id: str) -> bool:
    normalized = rel_path.replace("\\", "/")
    if normalized == f"runs/{run_id}" or normalized.startswith(f"runs/{run_id}/"):
        return True
    if normalized == "tmp" or normalized.startswith("tmp/"):
        return True
    parts = [part for part in Path(normalized).parts if part not in {".", ""}]
    return any(part in NON_WORKER_INTEGRITY_IGNORE_NAMES for part in parts)


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _workspace_integrity_digests(workspace_root: Path, *, run_id: str) -> dict[str, str]:
    digests: dict[str, str] = {}
    for path in workspace_root.rglob("*"):
        if not path.is_file():
            continue
        rel_path = path.relative_to(workspace_root).as_posix()
        if _is_non_worker_integrity_ignored(rel_path, run_id=run_id):
            continue
        if path.suffix in NON_WORKER_INTEGRITY_IGNORE_SUFFIXES:
            continue
        digests[rel_path] = _file_digest(path)
    return digests


def _non_worker_integrity_issues(before: dict[str, str], after: dict[str, str]) -> list[str]:
    before_paths = set(before)
    after_paths = set(after)
    issues: list[str] = []
    for label, paths in (
        ("added", sorted(after_paths - before_paths)),
        ("removed", sorted(before_paths - after_paths)),
        (
            "modified",
            sorted(path for path in before_paths & after_paths if before[path] != after[path]),
        ),
    ):
        if not paths:
            continue
        preview = ", ".join(paths[:10])
        suffix = "" if len(paths) <= 10 else f", ... (+{len(paths) - 10} more)"
        issues.append(f"{label}: {preview}{suffix}")
    return issues


def _apply_non_worker_integrity_guard(
    summary: _ExecutionSummary,
    *,
    role: str,
    before: dict[str, str] | None,
    after: dict[str, str] | None,
) -> _ExecutionSummary:
    from .codex_exec_executor import _ExecutionSummary

    if role == "worker" or before is None or after is None:
        return summary
    issues = _non_worker_integrity_issues(before, after)
    if not issues:
        return summary
    return _ExecutionSummary(
        status="fail",
        decision="blocked",
        notes=[
            *summary.notes,
            (
                f"non-worker workspace mutation guard blocked {role}: "
                + "; ".join(issues)
            ),
        ],
        timed_out=summary.timed_out,
        timeout_seconds=summary.timeout_seconds,
        termination_reason=summary.termination_reason,
    )
