from __future__ import annotations

import datetime as dt
import shutil
import subprocess
from pathlib import Path

import pytest

from ops.scripts.goal_worktree_guard import build_report
from ops.scripts.runtime_context import RuntimeContext


pytestmark = pytest.mark.public
GOAL_BRANCH = "goal/5day-auto-improve-runtime"


def _run_git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _seed_repo_with_worktree(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git is required for worktree guard tests")
    repo = tmp_path / "repo"
    worktree = tmp_path / "goal-worktree"
    repo.mkdir()
    _run_git(repo, "init", "-q", "-b", "main")
    _run_git(repo, "config", "user.name", "Test User")
    _run_git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-q", "-m", "initial")
    _run_git(repo, "remote", "add", "origin", "https://github.com/22nsuk/LLMwiki.git")
    _run_git(repo, "worktree", "add", "-q", "-b", GOAL_BRANCH, worktree, "main")
    return worktree


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 15, 0, 0, tzinfo=dt.timezone.utc),
    )


def test_goal_worktree_guard_passes_only_for_linked_expected_branch(tmp_path: Path) -> None:
    worktree = _seed_repo_with_worktree(tmp_path)

    report = build_report(worktree, expected_branch=GOAL_BRANCH, context=fixed_context())

    assert report["status"] == "pass"
    assert report["mode"] == "git_worktree"
    assert report["branch"] == GOAL_BRANCH
    assert report["remote_url"] == "https://github.com/22nsuk/LLMwiki.git"
    assert report["reason"] == "git linked worktree on expected branch"


def test_goal_worktree_guard_rejects_zip_or_report_only_directory(tmp_path: Path) -> None:
    report = build_report(tmp_path, expected_branch=GOAL_BRANCH, context=fixed_context())

    assert report["status"] == "fail"
    assert report["mode"] == "zip_or_report_only"
    assert report["branch"] == ""
