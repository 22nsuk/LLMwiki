from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ops.scripts.codex_goal_client import GoalBackend
from ops.scripts.runtime_context import RuntimeContext

from .goal_run_status import DEFAULT_AUDIT_LOG_PATH, DEFAULT_CONTRACT_PATH, DEFAULT_STATUS_PATH


AutoImproveRunner = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class GoalAutoImproveRequest:
    vault: Path
    policy_path: str | None
    goal_contract: str = DEFAULT_CONTRACT_PATH
    goal_profile: str = "30-minute-trial"
    status_out: str = DEFAULT_STATUS_PATH
    audit_jsonl: str = DEFAULT_AUDIT_LOG_PATH
    resume_from_checkpoint: str | None = None
    session_id: str | None = None
    resume_session: str | None = None
    executor_name: str = "codex_exec"
    artifact_class: str = "system_mechanism"
    allow_learning_uncertain: bool = False
    heartbeat_interval_minutes: int | None = None
    heartbeat_interval_seconds: float | None = None
    checkpoint_interval_minutes: int | None = None
    checkpoint_interval_seconds: float | None = None
    readiness_interval_seconds: float | None = None
    session_synopsis_interval_seconds: float | None = None
    sustain_until_budget: bool = False
    sustain_budget_seconds: float | None = None
    dry_run: bool = False
    goal_backend: GoalBackend | None = None
    context: RuntimeContext | None = None


def context_from_request(request: GoalAutoImproveRequest) -> RuntimeContext:
    return request.context or RuntimeContext(display_timezone=dt.timezone.utc)


def auto_improve_command(
    request: GoalAutoImproveRequest,
    profile: dict[str, int | str],
) -> list[str]:
    command = [
        ".venv/bin/python",
        "-m",
        "ops.scripts.mechanism.auto_improve_loop",
        "--vault",
        ".",
        "--policy",
        request.policy_path or "ops/policies/wiki-maintainer-policy.yaml",
        "--goal-contract",
        request.goal_contract,
        "--goal-profile",
        str(profile["profile"]),
        "--status-out",
        request.status_out,
        "--audit-jsonl",
        request.audit_jsonl,
        "--max-proposals",
        str(profile["max_proposals"]),
        "--max-minutes",
        str(profile["max_minutes"]),
        "--max-consecutive-failures",
        str(profile["max_consecutive_failures"]),
        "--executor",
        request.executor_name,
    ]
    if request.resume_from_checkpoint:
        command.extend(["--resume-from-checkpoint", request.resume_from_checkpoint])
    if request.session_id:
        command.extend(["--session-id", request.session_id])
    if request.resume_session:
        command.extend(["--resume-session", request.resume_session])
    if request.allow_learning_uncertain:
        command.append("--allow-learning-uncertain")
    if request.sustain_until_budget:
        command.append("--sustain-until-budget")
    if request.sustain_budget_seconds is not None:
        command.extend(["--sustain-budget-seconds", str(request.sustain_budget_seconds)])
    return command
