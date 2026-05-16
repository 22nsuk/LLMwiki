from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.output_runtime import display_path
from ops.scripts.runtime_context import RuntimeContext


class GoalWorktreeGuardError(Exception):
    pass


@dataclass(frozen=True)
class GitProbe:
    inside_work_tree: bool
    top_level: str
    branch: str
    commit: str
    common_dir: str
    git_dir_path: str
    remote_url: str


def _operation_policy(
    *,
    status: str,
    mode: str,
    reason: str,
) -> dict[str, str | bool]:
    if status == "pass" and mode == "git_worktree":
        return {
            "long_run_allowed": True,
            "allowed_operation": "long_run",
            "blocked_operation_reason": "",
        }
    if mode == "zip_or_report_only":
        return {
            "long_run_allowed": False,
            "allowed_operation": "trial_or_report_only",
            "blocked_operation_reason": (
                "Long-run goal execution requires a linked Git worktree on the "
                f"expected branch; this location is limited because {reason}."
            ),
        }
    return {
        "long_run_allowed": False,
        "allowed_operation": "report_only",
        "blocked_operation_reason": (
            "Long-run goal execution requires a linked Git worktree on the expected "
            f"branch; this location is report-only because {reason}."
        ),
    }


def _git(vault: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(vault), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise GoalWorktreeGuardError(completed.stderr.strip() or "git probe failed")
    return completed.stdout.strip()


def probe_git(vault: Path) -> GitProbe:
    inside = _git(vault, "rev-parse", "--is-inside-work-tree") == "true"
    return GitProbe(
        inside_work_tree=inside,
        top_level=_git(vault, "rev-parse", "--show-toplevel"),
        branch=_git(vault, "branch", "--show-current"),
        commit=_git(vault, "rev-parse", "HEAD"),
        common_dir=_git(vault, "rev-parse", "--git-common-dir"),
        git_dir_path=(vault / ".git").as_posix(),
        remote_url=_git(vault, "remote", "get-url", "origin"),
    )


def build_report(
    vault: Path,
    *,
    expected_branch: str = "goal/5day-auto-improve-runtime",
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.timezone.utc)
    try:
        probe = probe_git(vault)
    except GoalWorktreeGuardError as exc:
        reason = str(exc)
        return {
            "artifact_kind": "goal_worktree_guard",
            "generated_at": runtime_context.isoformat_z(),
            "status": "fail",
            "mode": "zip_or_report_only",
            "branch": "",
            "commit": "",
            "remote_url": "",
            "worktree_path": display_path(vault, vault),
            "reason": reason,
            **_operation_policy(
                status="fail",
                mode="zip_or_report_only",
                reason=reason,
            ),
        }
    git_file = (vault / ".git").is_file()
    branch_matches = probe.branch == expected_branch
    mode = "git_worktree" if git_file else "main_worktree"
    status = "pass" if probe.inside_work_tree and git_file and branch_matches else "fail"
    reason = "git linked worktree on expected branch"
    if not git_file:
        reason = "goal runtime must run from a linked git worktree, not the main worktree or a ZIP extract"
    elif not branch_matches:
        reason = f"branch {probe.branch or '<detached>'} does not match expected {expected_branch}"
    return {
        "artifact_kind": "goal_worktree_guard",
        "generated_at": runtime_context.isoformat_z(),
        "status": status,
        "mode": mode,
        "branch": probe.branch,
        "commit": probe.commit,
        "remote_url": probe.remote_url,
        "worktree_path": display_path(vault.parent, vault),
        "reason": reason,
        **_operation_policy(status=status, mode=mode, reason=reason),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate goal runtime git worktree mode.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--expected-branch", default="goal/5day-auto-improve-runtime")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, expected_branch=args.expected_branch)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
