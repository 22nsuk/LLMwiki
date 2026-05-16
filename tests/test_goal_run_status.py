from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ops.scripts.goal_run_status import initialize_goal_runtime, main as goal_run_status_main
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema


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
        pytest.skip("git is required for goal run status tests")
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


def _copy_goal_schemas(vault: Path) -> None:
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


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 15, 0, 0, tzinfo=dt.timezone.utc),
    )


def test_initialize_goal_runtime_records_private_github_worktree_and_resume_artifacts(
    tmp_path: Path,
) -> None:
    vault = _seed_repo_with_worktree(tmp_path)
    _copy_goal_schemas(vault)

    status = initialize_goal_runtime(
        vault,
        repo_url="https://github.com/22nsuk/LLMwiki",
        visibility="PRIVATE",
        baseline_commit="6c3ca7c46c6369ad043d78da5114c84173a14973",
        branch=GOAL_BRANCH,
        worktree_path="../LLMwiki-worktrees/goal-5day-auto-improve-runtime",
        context=fixed_context(),
    )

    status_path = vault / "ops" / "reports" / "goal-run-status.json"
    contract_path = vault / "ops" / "reports" / "codex-goal-contract.json"
    status_schema = load_schema(vault / "ops" / "schemas" / "goal-run-status.schema.json")
    contract_schema = load_schema(vault / "ops" / "schemas" / "codex-goal-contract.schema.json")
    persisted_status = json.loads(status_path.read_text(encoding="utf-8"))
    persisted_contract = json.loads(contract_path.read_text(encoding="utf-8"))

    assert validate_with_schema(persisted_status, status_schema) == []
    assert validate_with_schema(persisted_contract, contract_schema) == []
    assert persisted_status == status
    assert status["repo"]["visibility"] == "PRIVATE"
    assert status["repo"]["worktree_guard"]["status"] == "pass"
    assert status["repo"]["worktree_guard"]["long_run_allowed"] is True
    assert status["repo"]["worktree_guard"]["allowed_operation"] == "long_run"
    assert status["promotion_policy"]["promotion_ban_active"] is True
    assert status["budget"]["max_minutes"] == 7200
    assert status["resume"]["resume_supported"] is True
    assert status["resume"]["last_checkpoint"].startswith("ops/reports/goal-checkpoints/")
    assert (vault / status["resume"]["last_checkpoint"]).is_file()
    assert (vault / "ops" / "reports" / "goal-status.md").is_file()
    assert (vault / "ops" / "reports" / "goal-resume-metadata.json").is_file()
    audit_events = (vault / "ops" / "reports" / "goal-audit-log.jsonl").read_text(
        encoding="utf-8"
    )
    assert '"event": "initialized"' in audit_events


def test_initialize_goal_runtime_blocks_zip_mode_but_writes_report_artifacts(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_goal_schemas(vault)

    status = initialize_goal_runtime(
        vault,
        repo_url="https://github.com/22nsuk/LLMwiki",
        visibility="PRIVATE",
        baseline_commit="6c3ca7c46c6369ad043d78da5114c84173a14973",
        branch=GOAL_BRANCH,
        worktree_path="../LLMwiki-worktrees/goal-5day-auto-improve-runtime",
        context=fixed_context(),
    )

    status_path = vault / "ops" / "reports" / "goal-run-status.json"
    status_schema = load_schema(vault / "ops" / "schemas" / "goal-run-status.schema.json")
    persisted_status = json.loads(status_path.read_text(encoding="utf-8"))

    assert validate_with_schema(persisted_status, status_schema) == []
    assert persisted_status == status
    guard = status["repo"]["worktree_guard"]
    assert status["status"] == "blocked"
    assert guard["status"] == "fail"
    assert guard["mode"] == "zip_or_report_only"
    assert guard["long_run_allowed"] is False
    assert guard["allowed_operation"] == "trial_or_report_only"
    assert status["last_event"]["event"] == "goal_runtime_init_blocked_by_worktree_guard"
    assert "Long-run goal execution requires a linked Git worktree" in guard[
        "blocked_operation_reason"
    ]
    audit_events = (vault / "ops" / "reports" / "goal-audit-log.jsonl").read_text(
        encoding="utf-8"
    )
    assert '"event": "goal_runtime_init_blocked_by_worktree_guard"' in audit_events


def test_goal_run_status_heartbeat_syncs_promotion_policy_from_readiness(
    tmp_path: Path,
) -> None:
    vault = _seed_repo_with_worktree(tmp_path)
    _copy_goal_schemas(vault)
    initialize_goal_runtime(
        vault,
        repo_url="https://github.com/22nsuk/LLMwiki",
        visibility="PRIVATE",
        baseline_commit="6c3ca7c46c6369ad043d78da5114c84173a14973",
        branch=GOAL_BRANCH,
        worktree_path="../LLMwiki-worktrees/goal-5day-auto-improve-runtime",
        context=fixed_context(),
    )
    readiness_path = vault / "ops" / "reports" / "auto-improve-readiness.json"
    readiness_path.write_text(
        json.dumps(
            {
                "can_promote_result": True,
                "diagnostics": {
                    "release_authority_preflight_summary": {
                        "status": "pass",
                        "preflight_status": "sealed_clean_pass",
                        "clean_required_preflight": True,
                        "expected_blocked_preflight": False,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    assert goal_run_status_main(["heartbeat", "--vault", str(vault), "--reason", "sync"]) == 0

    status = json.loads((vault / "ops" / "reports" / "goal-run-status.json").read_text())
    assert status["promotion_policy"]["can_promote_result"] is True
    assert status["promotion_policy"]["promotion_ban_active"] is False
    assert "Promotion gate is open" in status["promotion_policy"]["promotion_ban_reason"]
