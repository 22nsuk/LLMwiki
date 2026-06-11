from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.codex_goal_client import FileGoalBackend
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import AUTO_IMPROVE_SESSION_SCHEMA_PATH

from .auto_improve_error_runtime import AutoImproveUsageError
from .auto_improve_loop_decision_runtime import (
    _empty_loop_state,
    _ensure_session_loop_state,
)
from .auto_improve_maintenance_decision_runtime import MAINTENANCE_ACTION_RUNNER_ACTION
from .auto_improve_session_report_runtime import _load_session_report
from .auto_improve_value_runtime import _int_value, _list_text, _mapping_value
from .goal_runtime_certificate import (
    learning_uncertain_policy,
    post_promote_maintenance_policy,
)

AUTO_IMPROVE_SESSION_SCHEMA = AUTO_IMPROVE_SESSION_SCHEMA_PATH


@dataclass(frozen=True)
class AutoImproveSessionStart:
    policy: dict
    resolved_policy_path: Path
    auto_policy: dict
    session: dict
    session_id: str
    context: RuntimeContext


@dataclass(frozen=True)
class AutoImproveSessionRequest:
    vault: Path
    policy_path: str | None
    session_id: str | None = None
    resume_session: str | None = None
    goal_contract_path: str | None = None
    max_proposals: int | None = None
    max_minutes: int | None = None
    max_consecutive_failures: int | None = None
    executor_name: str | None = None
    artifact_class: str = "system_mechanism"
    allow_learning_uncertain: bool = False
    maintain_until_budget: bool = False
    maintenance_interval_seconds: int | None = None
    post_promote_maintenance_cycles: int | None = None
    context: RuntimeContext | None = None

    def resolved(self) -> AutoImproveSessionRequest:
        return AutoImproveSessionRequest(
            vault=self.vault.resolve(),
            policy_path=self.policy_path,
            session_id=self.session_id,
            resume_session=self.resume_session,
            goal_contract_path=self.goal_contract_path,
            max_proposals=self.max_proposals,
            max_minutes=self.max_minutes,
            max_consecutive_failures=self.max_consecutive_failures,
            executor_name=self.executor_name,
            artifact_class=self.artifact_class,
            allow_learning_uncertain=self.allow_learning_uncertain,
            maintain_until_budget=self.maintain_until_budget,
            maintenance_interval_seconds=self.maintenance_interval_seconds,
            post_promote_maintenance_cycles=self.post_promote_maintenance_cycles,
            context=self.context,
        )


def _coerce_auto_improve_session_request(
    vault: AutoImproveSessionRequest | Path | None,
    legacy_kwargs: dict[str, Any],
) -> AutoImproveSessionRequest:
    if isinstance(vault, AutoImproveSessionRequest):
        if legacy_kwargs:
            unexpected = ", ".join(sorted(legacy_kwargs))
            raise TypeError(f"unexpected legacy session arguments with request object: {unexpected}")
        return vault.resolved()
    if vault is None:
        raise TypeError("run_auto_improve_session() missing required argument: 'vault'")
    if "policy_path" not in legacy_kwargs:
        raise TypeError("run_auto_improve_session() missing required keyword-only argument: 'policy_path'")
    allowed_keys = {
        "policy_path",
        "session_id",
        "resume_session",
        "goal_contract_path",
        "max_proposals",
        "max_minutes",
        "max_consecutive_failures",
        "executor_name",
        "artifact_class",
        "allow_learning_uncertain",
        "maintain_until_budget",
        "maintenance_interval_seconds",
        "post_promote_maintenance_cycles",
        "context",
    }
    unexpected_keys = sorted(set(legacy_kwargs) - allowed_keys)
    if unexpected_keys:
        unexpected = ", ".join(unexpected_keys)
        raise TypeError(f"run_auto_improve_session() got unexpected keyword argument(s): {unexpected}")
    return AutoImproveSessionRequest(
        vault=Path(vault).resolve(),
        policy_path=legacy_kwargs["policy_path"],
        session_id=legacy_kwargs.get("session_id"),
        resume_session=legacy_kwargs.get("resume_session"),
        goal_contract_path=legacy_kwargs.get("goal_contract_path"),
        max_proposals=legacy_kwargs.get("max_proposals"),
        max_minutes=legacy_kwargs.get("max_minutes"),
        max_consecutive_failures=legacy_kwargs.get("max_consecutive_failures"),
        executor_name=legacy_kwargs.get("executor_name"),
        artifact_class=legacy_kwargs.get("artifact_class", "system_mechanism"),
        allow_learning_uncertain=bool(legacy_kwargs.get("allow_learning_uncertain", False)),
        maintain_until_budget=bool(legacy_kwargs.get("maintain_until_budget", False)),
        maintenance_interval_seconds=legacy_kwargs.get("maintenance_interval_seconds"),
        post_promote_maintenance_cycles=legacy_kwargs.get("post_promote_maintenance_cycles"),
        context=legacy_kwargs.get("context"),
    )


def _resolve_budget_value(name: str, value: int | None, default: int) -> int:
    resolved = default if value is None else value
    if not isinstance(resolved, int) or isinstance(resolved, bool) or resolved < 1:
        raise AutoImproveUsageError(f"{name} must be an integer greater than or equal to 1")
    return resolved


def _apply_resume_budget_overrides(
    session: dict[str, Any],
    auto_policy: Mapping[str, Any],
    *,
    max_proposals: int | None,
    max_minutes: int | None,
    max_consecutive_failures: int | None,
) -> None:
    budget = _mapping_value(session, "budget")
    defaults = _mapping_value(auto_policy, "defaults")
    session["budget"] = {
        "max_proposals": _resolve_budget_value(
            "max_proposals",
            max_proposals,
            _int_value(budget.get("max_proposals"))
            or _int_value(defaults.get("max_proposals")),
        ),
        "max_minutes": _resolve_budget_value(
            "max_minutes",
            max_minutes,
            _int_value(budget.get("max_minutes")) or _int_value(defaults.get("max_minutes")),
        ),
        "max_consecutive_failures": _resolve_budget_value(
            "max_consecutive_failures",
            max_consecutive_failures,
            _int_value(budget.get("max_consecutive_failures"))
            or _int_value(defaults.get("max_consecutive_failures")),
        ),
    }


def _canonical_json_digest(payload: Mapping[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _positive_contract_int(payload: Mapping[str, Any], key: str, *, context: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise AutoImproveUsageError(f"goal contract {context}.{key} must be an integer >= 1")
    return value


def _goal_contract_snapshot(
    vault: Path,
    *,
    contract_path: str,
    contract: Mapping[str, Any],
    resolved_contract_path: Path,
) -> dict[str, Any]:
    budgets = _mapping_value(contract, "budgets")
    runtime = _mapping_value(contract, "runtime")
    promotion_guard = _mapping_value(contract, "promotion_guard")
    learning_policy = learning_uncertain_policy(contract)
    maintenance_policy = post_promote_maintenance_policy(contract)
    max_wall_clock_seconds = _positive_contract_int(
        budgets,
        "max_wall_clock_seconds",
        context="budgets",
    )
    max_unattended_seconds = _positive_contract_int(
        runtime,
        "max_unattended_seconds",
        context="runtime",
    )
    return {
        "path": report_path(vault, resolved_contract_path),
        "requested_path": contract_path,
        "contract_sha256": _canonical_json_digest(contract),
        "contract_id": str(contract.get("contract_id", "")).strip(),
        "status": str(contract.get("status", "")).strip(),
        "runtime_mode": str(runtime.get("mode", "")).strip(),
        "max_wall_clock_seconds": max_wall_clock_seconds,
        "max_unattended_seconds": max_unattended_seconds,
        "max_proposals": _positive_contract_int(
            budgets,
            "max_proposals",
            context="budgets",
        ),
        "max_consecutive_failures": _positive_contract_int(
            budgets,
            "max_consecutive_failures",
            context="budgets",
        ),
        "can_promote_result": bool(promotion_guard.get("can_promote_result", False)),
        "promotion_blockers": _list_text(promotion_guard.get("promotion_blockers")),
        "execution_policy": {
            "learning_uncertain": learning_policy,
            "post_promote_maintenance": maintenance_policy,
        },
    }


def _load_goal_contract_snapshot(vault: Path, goal_contract_path: str) -> dict[str, Any]:
    backend = FileGoalBackend(vault=vault, contract_path=goal_contract_path)
    contract = backend.get_goal()
    return _goal_contract_snapshot(
        vault,
        contract_path=goal_contract_path,
        contract=contract,
        resolved_contract_path=backend.destination,
    )


def _validate_goal_contract_budget(session: Mapping[str, Any], snapshot: Mapping[str, Any]) -> None:
    budget = _mapping_value(session, "budget")
    max_proposals = _positive_contract_int(budget, "max_proposals", context="session.budget")
    max_minutes = _positive_contract_int(budget, "max_minutes", context="session.budget")
    max_consecutive_failures = _positive_contract_int(
        budget,
        "max_consecutive_failures",
        context="session.budget",
    )
    contract_max_proposals = _positive_contract_int(snapshot, "max_proposals", context="snapshot")
    contract_max_failures = _positive_contract_int(
        snapshot,
        "max_consecutive_failures",
        context="snapshot",
    )
    contract_wall_seconds = min(
        _positive_contract_int(snapshot, "max_wall_clock_seconds", context="snapshot"),
        _positive_contract_int(snapshot, "max_unattended_seconds", context="snapshot"),
    )
    if max_proposals > contract_max_proposals:
        raise AutoImproveUsageError(
            "max_proposals exceeds goal contract budget: "
            f"requested {max_proposals}, contract allows {contract_max_proposals}"
        )
    if max_consecutive_failures > contract_max_failures:
        raise AutoImproveUsageError(
            "max_consecutive_failures exceeds goal contract budget: "
            f"requested {max_consecutive_failures}, contract allows {contract_max_failures}"
        )
    if max_minutes * 60 > contract_wall_seconds:
        allowed_minutes = contract_wall_seconds // 60
        raise AutoImproveUsageError(
            "max_minutes exceeds goal contract budget: "
            f"requested {max_minutes}m, contract allows {allowed_minutes}m "
            f"({contract_wall_seconds}s)"
        )


def _session_goal_contract_path(session: Mapping[str, Any]) -> str:
    goal_contract = _mapping_value(session, "goal_contract")
    return str(goal_contract.get("requested_path") or goal_contract.get("path") or "").strip()


def _session_allows_maintenance_action_budget_increment(
    session: Mapping[str, Any],
    existing: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> bool:
    maintenance = _mapping_value(session, "maintenance")
    queue_action = _mapping_value(maintenance, "queue_action")
    if str(queue_action.get("status", "")).strip() != "action_required":
        return False
    if str(queue_action.get("runner_action", "")).strip() != MAINTENANCE_ACTION_RUNNER_ACTION:
        return False
    if str(session.get("stop_reason", "")).strip() != "proposal_budget_exhausted":
        return False
    increment = _int_value(queue_action.get("proposal_budget_increment"))
    if increment < 1:
        return False
    existing_max = _int_value(existing.get("max_proposals"))
    snapshot_max = _int_value(snapshot.get("max_proposals"))
    session_max = _int_value(_mapping_value(session, "budget").get("max_proposals"))
    return (
        existing_max > 0
        and session_max > existing_max
        and snapshot_max == session_max
        and session_max <= existing_max + increment
    )


def _compatible_goal_contract_refresh(
    existing: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    allow_max_proposals_increase: bool = False,
) -> bool:
    checks = (
        ("contract_id", "contract_id"),
        ("runtime_mode", "runtime_mode"),
        ("path", "path"),
    )
    for existing_key, snapshot_key in checks:
        existing_value = str(existing.get(existing_key, "")).strip()
        snapshot_value = str(snapshot.get(snapshot_key, "")).strip()
        if existing_value and snapshot_value and existing_value != snapshot_value:
            return False
    budget_fields = (
        "max_wall_clock_seconds",
        "max_unattended_seconds",
        "max_proposals",
        "max_consecutive_failures",
    )
    for field in budget_fields:
        existing_budget = _int_value(existing.get(field))
        snapshot_budget = _int_value(snapshot.get(field))
        if field == "max_proposals" and allow_max_proposals_increase:
            continue
        if existing_budget > 0 and snapshot_budget > existing_budget:
            return False
    return True


def _attach_goal_contract_snapshot(
    vault: Path,
    session: dict,
    *,
    goal_contract_path: str,
) -> None:
    snapshot = _load_goal_contract_snapshot(vault, goal_contract_path)
    _validate_goal_contract_budget(session, snapshot)
    existing = _mapping_value(session, "goal_contract")
    existing_digest = str(existing.get("contract_sha256", "")).strip()
    allow_max_proposals_increase = _session_allows_maintenance_action_budget_increment(
        session,
        existing,
        snapshot,
    )
    if (
        existing_digest
        and existing_digest != snapshot["contract_sha256"]
        and not _compatible_goal_contract_refresh(
            existing,
            snapshot,
            allow_max_proposals_increase=allow_max_proposals_increase,
        )
    ):
        raise AutoImproveUsageError(
            "resume goal contract digest mismatch: "
            f"{existing_digest} != {snapshot['contract_sha256']}"
        )
    session["goal_contract"] = snapshot


def _new_session_id(context: RuntimeContext) -> str:
    return "auto-improve-" + re.sub(r"[^0-9a-z]+", "-", context.isoformat_z().lower()).strip("-")


def _validate_auto_improve_request(
    auto_policy: dict,
    *,
    artifact_class: str,
    executor_name: str | None,
) -> str:
    if artifact_class != auto_policy["artifact_class"]:
        raise AutoImproveUsageError(f"unsupported artifact class: {artifact_class}")
    requested_executor = executor_name or auto_policy["defaults"]["executor"]
    allowed_executors = set(auto_policy["allowed_executors"])
    if requested_executor not in allowed_executors:
        allowed = ", ".join(sorted(allowed_executors))
        raise AutoImproveUsageError(
            f"unsupported executor: {requested_executor}; allowed executors: {allowed}"
        )
    return requested_executor


def _validate_resume_executor(
    session: dict,
    *,
    executor_name: str | None,
    allowed_executors: set[str],
) -> None:
    session_executor = str(session.get("executor", {}).get("name", "")).strip()
    if session_executor not in allowed_executors:
        allowed = ", ".join(sorted(allowed_executors))
        raise AutoImproveUsageError(
            f"unsupported executor in resumed session: {session_executor}; allowed executors: {allowed}"
        )
    if executor_name is not None and executor_name != session_executor:
        raise AutoImproveUsageError(f"resume executor mismatch: {executor_name} != {session_executor}")


def _new_auto_improve_session(
    vault: Path,
    auto_policy: dict,
    policy: dict,
    resolved_policy_path: Path,
    *,
    session_id: str,
    max_proposals: int | None,
    max_minutes: int | None,
    max_consecutive_failures: int | None,
    requested_executor: str,
    context: RuntimeContext,
) -> dict:
    return {
        "$schema": AUTO_IMPROVE_SESSION_SCHEMA,
        "session_id": session_id,
        "generated_at": context.isoformat_z(),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy["version"],
        },
        "status": "running",
        "budget": {
            "max_proposals": _resolve_budget_value(
                "max_proposals",
                max_proposals,
                auto_policy["defaults"]["max_proposals"],
            ),
            "max_minutes": _resolve_budget_value(
                "max_minutes",
                max_minutes,
                auto_policy["defaults"]["max_minutes"],
            ),
            "max_consecutive_failures": _resolve_budget_value(
                "max_consecutive_failures",
                max_consecutive_failures,
                auto_policy["defaults"]["max_consecutive_failures"],
            ),
        },
        "executor": {
            "name": requested_executor,
        },
        "attempted_proposal_ids": [],
        "quarantined_proposal_ids": [],
        "run_ids": [],
        "iterations": [],
        "next_run_decisions": [],
        "learning_summary": {
            "attempt_count": 0,
            "rework_count": 0,
            "rollback_signal_count": 0,
            "defect_escape_pair_count": 0,
            "session_context_status": "no_iterations",
            "evidence_gaps": ["session.iterations is empty", "session.run_ids is empty"],
        },
        "loop_state": _empty_loop_state(context),
        "queue_snapshot": [],
        "stop_reason": "running",
        "path": f"{auto_policy['session_reports_dir'].rstrip('/')}/{session_id}.json",
    }


def _start_auto_improve_session(request: AutoImproveSessionRequest) -> AutoImproveSessionStart:
    policy, resolved_policy_path = load_policy(request.vault, request.policy_path)
    auto_policy = policy["auto_improve_policy"]
    requested_executor = _validate_auto_improve_request(
        auto_policy,
        artifact_class=request.artifact_class,
        executor_name=request.executor_name,
    )
    base_context = request.context or RuntimeContext.from_policy(policy, executor_id=requested_executor)

    goal_contract_path: str | None
    if request.resume_session:
        session = _load_session_report(request.vault, request.resume_session)
        _apply_resume_budget_overrides(
            session,
            auto_policy,
            max_proposals=request.max_proposals,
            max_minutes=request.max_minutes,
            max_consecutive_failures=request.max_consecutive_failures,
        )
        _ensure_session_loop_state(session, context=base_context)
        current_session_id = request.resume_session
        _validate_resume_executor(
            session,
            executor_name=request.executor_name,
            allowed_executors=set(auto_policy["allowed_executors"]),
        )
        goal_contract_path = request.goal_contract_path or _session_goal_contract_path(session)
    else:
        current_session_id = request.session_id or _new_session_id(base_context)
        session = _new_auto_improve_session(
            request.vault,
            auto_policy,
            policy,
            resolved_policy_path,
            session_id=current_session_id,
            max_proposals=request.max_proposals,
            max_minutes=request.max_minutes,
            max_consecutive_failures=request.max_consecutive_failures,
            requested_executor=requested_executor,
            context=base_context,
        )
        goal_contract_path = request.goal_contract_path

    if goal_contract_path:
        _attach_goal_contract_snapshot(
            request.vault,
            session,
            goal_contract_path=goal_contract_path,
        )

    return AutoImproveSessionStart(
        policy=policy,
        resolved_policy_path=resolved_policy_path,
        auto_policy=auto_policy,
        session=session,
        session_id=current_session_id,
        context=base_context,
    )
