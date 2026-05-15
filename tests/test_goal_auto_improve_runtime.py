from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from ops.scripts.auto_improve_goal_runtime import GoalAutoImproveRequest, run_goal_bound_auto_improve
from ops.scripts.goal_run_status import initialize_goal_runtime
from ops.scripts.runtime_context import RuntimeContext


pytestmark = pytest.mark.public
REPO_ROOT = Path(__file__).resolve().parents[1]
GOAL_BRANCH = "goal/5day-auto-improve-runtime"


def _run_git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _seed_repo_with_worktree(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git is required for goal auto-improve tests")
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


def _copy_goal_runtime_inputs(vault: Path) -> None:
    schema_dir = vault / "ops" / "schemas"
    policy_dir = vault / "ops" / "policies"
    schema_dir.mkdir(parents=True, exist_ok=True)
    policy_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "artifact-envelope.schema.json",
        "codex-goal-contract.schema.json",
        "goal-run-status.schema.json",
        "goal-resume-metadata.schema.json",
    ):
        shutil.copyfile(REPO_ROOT / "ops" / "schemas" / name, schema_dir / name)
    shutil.copyfile(
        REPO_ROOT / "ops" / "policies" / "wiki-maintainer-policy.yaml",
        policy_dir / "wiki-maintainer-policy.yaml",
    )


def _context(minute: int) -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 15, 0, minute, tzinfo=dt.timezone.utc),
    )


def _initialize_goal(vault: Path) -> None:
    initialize_goal_runtime(
        vault,
        repo_url="https://github.com/22nsuk/LLMwiki",
        visibility="PRIVATE",
        baseline_commit="6c3ca7c46c6369ad043d78da5114c84173a14973",
        branch=GOAL_BRANCH,
        worktree_path="../LLMwiki-worktrees/goal-5day-auto-improve-runtime",
        context=_context(0),
    )


def test_goal_bound_auto_improve_dry_run_maps_trial_budget_and_checkpoint(
    tmp_path: Path,
) -> None:
    vault = _seed_repo_with_worktree(tmp_path)
    _copy_goal_runtime_inputs(vault)
    _initialize_goal(vault)

    result = run_goal_bound_auto_improve(
        GoalAutoImproveRequest(
            vault=vault,
            policy_path="ops/policies/wiki-maintainer-policy.yaml",
            goal_profile="30-minute-trial",
            dry_run=True,
            context=_context(1),
        )
    )

    status = json.loads((vault / "ops" / "reports" / "goal-run-status.json").read_text())
    audit = (vault / "ops" / "reports" / "goal-audit-log.jsonl").read_text(encoding="utf-8")

    assert result["status"] == "dry_run"
    assert status["budget"] == {
        "max_minutes": 30,
        "max_proposals": 1,
        "max_consecutive_failures": 1,
    }
    assert status["resume"]["last_checkpoint"] == result["checkpoint"]
    assert (vault / result["checkpoint"]).is_file()
    assert "--goal-contract" in result["auto_improve_command"]
    assert '"event": "goal_run_dry_run"' in audit


def test_goal_bound_auto_improve_executes_ramp_with_profile_budget(
    tmp_path: Path,
) -> None:
    vault = _seed_repo_with_worktree(tmp_path)
    _copy_goal_runtime_inputs(vault)
    _initialize_goal(vault)
    calls: list[dict[str, Any]] = []

    def fake_runner(vault_path: Path, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        rel_path = "ops/reports/auto-improve-sessions/goal-ramp.json"
        session_path = vault_path / rel_path
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_text(
            json.dumps(
                {
                    "iterations": [{"iteration": 1}, {"iteration": 2}],
                    "attempted_proposal_ids": ["proposal-a", "proposal-b"],
                    "loop_state": {"consecutive_failures": 0},
                }
            ),
            encoding="utf-8",
        )
        return {
            "session_id": "goal-ramp",
            "session_report": rel_path,
            "iterations": 2,
            "stop_reason": "budget_exhausted",
            "run_ids": [],
        }

    result = run_goal_bound_auto_improve(
        GoalAutoImproveRequest(
            vault=vault,
            policy_path="ops/policies/wiki-maintainer-policy.yaml",
            goal_profile="6-hour-ramp",
            heartbeat_interval_seconds=0,
            context=_context(2),
        ),
        runner=fake_runner,
    )

    status = json.loads((vault / "ops" / "reports" / "goal-run-status.json").read_text())

    assert calls[0]["max_minutes"] == 360
    assert calls[0]["max_proposals"] == 6
    assert calls[0]["max_consecutive_failures"] == 1
    assert result["goal_profile"] == "6-hour-ramp"
    assert status["status"] == "running"
    assert status["progress"]["iterations_completed"] == 2
    assert status["progress"]["proposals_attempted"] == 2
    assert status["last_event"]["event"] == "goal_run_complete"
    assert "budget_exhausted" in status["last_event"]["reason"]


def test_goal_bound_auto_improve_resumes_from_checkpoint(
    tmp_path: Path,
) -> None:
    vault = _seed_repo_with_worktree(tmp_path)
    _copy_goal_runtime_inputs(vault)
    _initialize_goal(vault)
    dry_run = run_goal_bound_auto_improve(
        GoalAutoImproveRequest(
            vault=vault,
            policy_path="ops/policies/wiki-maintainer-policy.yaml",
            goal_profile="30-minute-trial",
            dry_run=True,
            context=_context(1),
        )
    )
    calls: list[dict[str, Any]] = []

    def fake_runner(vault_path: Path, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        rel_path = "ops/reports/auto-improve-sessions/goal-resume.json"
        session_path = vault_path / rel_path
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_text(
            json.dumps(
                {
                    "iterations": [{"iteration": 1}],
                    "attempted_proposal_ids": ["proposal-a"],
                    "loop_state": {"consecutive_failures": 0},
                }
            ),
            encoding="utf-8",
        )
        return {
            "session_id": "goal-resume",
            "session_report": rel_path,
            "iterations": 1,
            "stop_reason": "budget_exhausted",
            "run_ids": [],
        }

    result = run_goal_bound_auto_improve(
        GoalAutoImproveRequest(
            vault=vault,
            policy_path="ops/policies/wiki-maintainer-policy.yaml",
            goal_profile="30-minute-trial",
            resume_from_checkpoint=str(dry_run["checkpoint"]),
            heartbeat_interval_seconds=0,
            context=_context(2),
        ),
        runner=fake_runner,
    )

    status = json.loads((vault / "ops" / "reports" / "goal-run-status.json").read_text())

    assert calls[0]["max_minutes"] == 30
    assert result["checkpoint"] != dry_run["checkpoint"]
    assert status["progress"]["iterations_completed"] == 1
    assert status["resume"]["last_checkpoint"] == result["checkpoint"]
