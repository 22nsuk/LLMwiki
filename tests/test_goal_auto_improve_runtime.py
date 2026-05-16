from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from ops.scripts.auto_improve_goal_runtime import (
    GoalAutoImproveRequest,
    _run_periodic_refresh_command,
    run_goal_bound_auto_improve,
)
from ops.scripts.codex_goal_client import FakeGoalBackend
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


def _write_usage_limited_executor_report(
    vault: Path,
    run_id: str,
    *,
    retry_after: str,
) -> None:
    run_dir = vault / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    stderr_rel = f"runs/{run_id}/worker.stderr.txt"
    (vault / stderr_rel).write_text(
        f"OpenAI usage limit reached. try again at {retry_after}\n",
        encoding="utf-8",
    )
    (run_dir / "worker-executor-report.json").write_text(
        json.dumps(
            {
                "status": "fail",
                "artifacts": {"stderr": stderr_rel},
                "diagnostics": {
                    "notes": [
                        "codex exec exited with 1",
                        f"codex exec blocked by usage limit; retry_after={retry_after}",
                    ]
                },
            }
        ),
        encoding="utf-8",
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


def test_goal_bound_auto_improve_rejects_nonpersistent_goal_backend(
    tmp_path: Path,
) -> None:
    vault = _seed_repo_with_worktree(tmp_path)
    _copy_goal_runtime_inputs(vault)
    _initialize_goal(vault)

    with pytest.raises(ValueError, match="process-persistent goal backend"):
        run_goal_bound_auto_improve(
            GoalAutoImproveRequest(
                vault=vault,
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
                goal_profile="30-minute-trial",
                goal_backend=FakeGoalBackend(),
                dry_run=True,
                context=_context(1),
            )
        )


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
    assert status["heartbeat"]["last_heartbeat_at"] == "2026-05-15T00:02:00Z"


def test_goal_bound_auto_improve_keeps_periodic_checkpoints_from_running_profile(
    tmp_path: Path,
) -> None:
    vault = _seed_repo_with_worktree(tmp_path)
    _copy_goal_runtime_inputs(vault)
    _initialize_goal(vault)

    def slow_fake_runner(vault_path: Path, **_: Any) -> dict[str, Any]:
        rel_path = "ops/reports/auto-improve-sessions/goal-sustained.json"
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
        time.sleep(0.15)
        return {
            "session_id": "goal-sustained",
            "session_report": rel_path,
            "iterations": 1,
            "stop_reason": "budget_exhausted",
            "run_ids": [],
        }

    result = run_goal_bound_auto_improve(
        GoalAutoImproveRequest(
            vault=vault,
            policy_path="ops/policies/wiki-maintainer-policy.yaml",
            goal_profile="5-day-sustained",
            heartbeat_interval_seconds=0.03,
            checkpoint_interval_seconds=0.03,
            readiness_interval_seconds=0,
            session_synopsis_interval_seconds=0,
            context=_context(3),
        ),
        runner=slow_fake_runner,
    )

    status = json.loads((vault / "ops" / "reports" / "goal-run-status.json").read_text())

    assert status["active_profile"] == "5-day-sustained"
    assert status["resume"]["last_checkpoint"] == result["checkpoint"]
    assert any(
        item["reason"] == "periodic checkpoint for goal profile: 5-day-sustained"
        for item in status["checkpoints"]
    )
    assert (vault / status["resume"]["last_checkpoint"]).is_file()


def test_goal_bound_auto_improve_sustains_heartbeat_until_budget_elapsed(
    tmp_path: Path,
) -> None:
    vault = _seed_repo_with_worktree(tmp_path)
    _copy_goal_runtime_inputs(vault)
    _initialize_goal(vault)

    def fast_fake_runner(vault_path: Path, **_: Any) -> dict[str, Any]:
        rel_path = "ops/reports/auto-improve-sessions/goal-sustain.json"
        session_path = vault_path / rel_path
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_text(
            json.dumps(
                {
                    "iterations": [],
                    "attempted_proposal_ids": [],
                    "loop_state": {"consecutive_failures": 0},
                }
            ),
            encoding="utf-8",
        )
        return {
            "session_id": "goal-sustain",
            "session_report": rel_path,
            "iterations": 0,
            "stop_reason": "queue_exhausted",
            "run_ids": [],
        }

    result = run_goal_bound_auto_improve(
        GoalAutoImproveRequest(
            vault=vault,
            policy_path="ops/policies/wiki-maintainer-policy.yaml",
            goal_profile="5-day-sustained",
            heartbeat_interval_seconds=0.02,
            checkpoint_interval_seconds=0.02,
            readiness_interval_seconds=0,
            session_synopsis_interval_seconds=0,
            sustain_until_budget=True,
            sustain_budget_seconds=0.08,
            context=_context(4),
        ),
        runner=fast_fake_runner,
    )

    status = json.loads((vault / "ops" / "reports" / "goal-run-status.json").read_text())

    assert result["status"] == "running"
    assert "sustained_budget_elapsed" in status["last_event"]["reason"]
    assert any(
        item["reason"] == "periodic checkpoint for goal profile: 5-day-sustained"
        for item in status["checkpoints"]
    )


def test_goal_bound_auto_improve_sustains_retryable_executor_usage_limit(
    tmp_path: Path,
) -> None:
    vault = _seed_repo_with_worktree(tmp_path)
    _copy_goal_runtime_inputs(vault)
    _initialize_goal(vault)

    def usage_limited_runner(vault_path: Path, **_: Any) -> dict[str, Any]:
        run_id = "goal-usage-limited-run"
        _write_usage_limited_executor_report(
            vault_path,
            run_id,
            retry_after="May 15th, 2026 12:10 AM",
        )
        rel_path = "ops/reports/auto-improve-sessions/goal-usage-limited.json"
        session_path = vault_path / rel_path
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_text(
            json.dumps(
                {
                    "iterations": [{"iteration": 1, "outcome": "executor_usage_limited"}],
                    "attempted_proposal_ids": ["proposal-a"],
                    "loop_state": {"consecutive_failures": 0},
                }
            ),
            encoding="utf-8",
        )
        return {
            "session_id": "goal-usage-limited",
            "session_report": rel_path,
            "iterations": 1,
            "stop_reason": "executor_usage_limited",
            "run_ids": [run_id],
        }

    result = run_goal_bound_auto_improve(
        GoalAutoImproveRequest(
            vault=vault,
            policy_path="ops/policies/wiki-maintainer-policy.yaml",
            goal_profile="30-minute-trial",
            heartbeat_interval_seconds=0.02,
            checkpoint_interval_seconds=0.02,
            sustain_until_budget=True,
            sustain_budget_seconds=0.08,
            context=_context(5),
        ),
        runner=usage_limited_runner,
    )

    status = json.loads((vault / "ops" / "reports" / "goal-run-status.json").read_text())

    assert result["status"] == "running"
    assert "sustained_budget_elapsed" in status["last_event"]["reason"]
    assert status["progress"]["iterations_completed"] == 1
    assert status["progress"]["consecutive_failures"] == 0
    assert status["executor_backoff"] == {
        "active": True,
        "reason": "executor_usage_limited",
        "retry_after": "May 15th, 2026 12:10 AM",
        "retry_after_utc": "2026-05-15T00:10:00Z",
        "source": "runs/goal-usage-limited-run/worker-executor-report.json",
        "last_observed_at": "2026-05-15T00:05:00Z",
    }


def test_goal_bound_auto_improve_defers_profile_when_usage_limit_backoff_is_active(
    tmp_path: Path,
) -> None:
    vault = _seed_repo_with_worktree(tmp_path)
    _copy_goal_runtime_inputs(vault)
    _initialize_goal(vault)
    status_path = vault / "ops" / "reports" / "goal-run-status.json"
    seeded_status = json.loads(status_path.read_text(encoding="utf-8"))
    seeded_status["executor_backoff"] = {
        "active": True,
        "reason": "executor_usage_limited",
        "retry_after": "May 15th, 2026 12:10 AM",
        "retry_after_utc": "2026-05-15T00:10:00Z",
        "source": "runs/previous/worker-executor-report.json",
        "last_observed_at": "2026-05-15T00:05:00Z",
    }
    status_path.write_text(json.dumps(seeded_status), encoding="utf-8")

    def runner_should_not_fire(vault_path: Path, **_: Any) -> dict[str, Any]:
        raise AssertionError(f"executor should wait for backoff before running in {vault_path}")

    result = run_goal_bound_auto_improve(
        GoalAutoImproveRequest(
            vault=vault,
            policy_path="ops/policies/wiki-maintainer-policy.yaml",
            goal_profile="6-hour-ramp",
            heartbeat_interval_seconds=0,
            checkpoint_interval_seconds=0,
            sustain_until_budget=True,
            sustain_budget_seconds=0.04,
            context=_context(6),
        ),
        runner=runner_should_not_fire,
    )

    status = json.loads(status_path.read_text(encoding="utf-8"))

    assert result["status"] == "running"
    assert result["auto_improve"]["stop_reason"] == "executor_usage_limited"
    assert "sustained_budget_elapsed" in status["last_event"]["reason"]
    assert status["executor_backoff"]["retry_after_utc"] == "2026-05-15T00:10:00Z"
    assert status["progress"]["proposals_attempted"] == 0


def test_goal_bound_auto_improve_blocks_when_periodic_readiness_regresses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = _seed_repo_with_worktree(tmp_path)
    _copy_goal_runtime_inputs(vault)
    _initialize_goal(vault)

    def fake_refresh(vault_path: Path, target: str) -> None:
        assert target == "auto-improve-readiness-report-body"
        readiness_path = vault_path / "ops" / "reports" / "auto-improve-readiness.json"
        readiness_path.parent.mkdir(parents=True, exist_ok=True)
        readiness_path.write_text(
            json.dumps(
                {
                    "can_execute_trial": True,
                    "can_promote_result": False,
                    "blockers": None,
                    "diagnostics": {
                        "release_authority_preflight_summary": {
                            "status": "blocked",
                            "preflight_status": "expected_blocked_preflight",
                            "clean_required_preflight": False,
                            "expected_blocked_preflight": True,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    def fast_fake_runner(vault_path: Path, **_: Any) -> dict[str, Any]:
        rel_path = "ops/reports/auto-improve-sessions/goal-regression.json"
        session_path = vault_path / rel_path
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_text(
            json.dumps(
                {
                    "iterations": [],
                    "attempted_proposal_ids": [],
                    "loop_state": {"consecutive_failures": 0},
                }
            ),
            encoding="utf-8",
        )
        return {
            "session_id": "goal-regression",
            "session_report": rel_path,
            "iterations": 0,
            "stop_reason": "queue_exhausted",
            "run_ids": [],
        }

    monkeypatch.setattr(
        "ops.scripts.mechanism.auto_improve_goal_runtime._run_periodic_refresh_command",
        fake_refresh,
    )

    result = run_goal_bound_auto_improve(
        GoalAutoImproveRequest(
            vault=vault,
            policy_path="ops/policies/wiki-maintainer-policy.yaml",
            goal_profile="5-day-sustained",
            heartbeat_interval_seconds=0,
            checkpoint_interval_seconds=0,
            readiness_interval_seconds=0.02,
            session_synopsis_interval_seconds=0,
            sustain_until_budget=True,
            sustain_budget_seconds=0.2,
            context=_context(5),
        ),
        runner=fast_fake_runner,
    )

    status = json.loads((vault / "ops" / "reports" / "goal-run-status.json").read_text())

    assert result["status"] == "blocked"
    assert status["last_event"]["event"] == "goal_run_complete"
    assert "periodic maintenance failure" in status["last_event"]["reason"]
    assert "can_promote_result=false" in status["last_event"]["reason"]


def test_periodic_refresh_command_uses_current_python_for_worktree_make(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("ops.scripts.mechanism.auto_improve_goal_runtime.subprocess.run", fake_run)

    _run_periodic_refresh_command(tmp_path, "auto-improve-readiness-report-body")

    assert calls
    args, kwargs = calls[0]
    assert args == ["make", "auto-improve-readiness-report-body", f"PYTHON={sys.executable}"]
    assert kwargs["cwd"] == tmp_path
