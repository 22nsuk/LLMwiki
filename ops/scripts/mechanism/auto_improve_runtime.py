from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import (
    build_canonical_report_envelope,
    embed_artifact_envelope_metadata,
)
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object,
    read_json_object,
    write_json_object,
    write_schema_backed_report,
    write_schema_validated_json,
)
from ops.scripts.codex_goal_client import FileGoalBackend
from ops.scripts.experiment_telemetry_runtime import append_ledger_event
from ops.scripts.observability_artifacts_runtime import (
    write_outcome_metrics_report,
    write_promotion_decision_trends,
    write_routing_provenance_aggregate,
    write_run_artifact_fingerprint,
)
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.proposal_scope_runtime import build_scope_freeze, write_scope_freeze
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.runtime_event_logging_runtime import append_runtime_event
from ops.scripts.schema_constants_runtime import AUTO_IMPROVE_SESSION_SCHEMA_PATH
from ops.scripts.schema_runtime import load_schema_with_vault_override
from ops.scripts.subagent_routing_runtime import run_selector

from .auto_improve_execute_runtime import (
    ExecuteEvaluateDependencies,
    ExecuteEvaluatePhaseResult,
    ExecuteEvaluateRequest,
    execute_evaluate_phase,
)
from .auto_improve_execution_runtime import mutation_command
from .auto_improve_iteration_persistence_runtime import (
    PersistIterationDependencies,
    PersistIterationPhaseResult,
    persist_iteration_phase,
    write_iteration_telemetry,
)
from .auto_improve_iteration_runtime import (
    AutoImproveIterationDependencies,
    AutoImproveIterationRequest,
)
from .auto_improve_iteration_runtime import (
    run_auto_improve_iteration as run_auto_improve_iteration_helper,
)
from .auto_improve_outcome_runtime import (
    apply_execution_outcome,
    detect_executor_failure,
    evaluate_experiment_error,
    evaluate_experiment_result,
    evaluate_mutation_error,
    evaluate_scope_blocked,
    role_report_path,
)
from .auto_improve_queue_runtime import (
    build_proposal_queue,
    select_next_proposal,
)
from .auto_improve_readiness_runtime import (
    build_readiness_report,
    learning_review_required,
    write_readiness_report,
)
from .auto_improve_route_scaffold_runtime import (
    RouteScaffoldDependencies,
    RouteScaffoldPhaseResult,
    route_scaffold_phase,
)
from .auto_improve_session_completion_runtime import (
    SessionCompletionDependencies,
    complete_auto_improve_session,
)
from .auto_improve_session_runtime import (
    build_executor_rollup,
    build_iteration_rollup,
    build_routing_rollup,
    build_session_rollups,
    build_telemetry_rollup,
    increment_counter,
    normalize_session_report,
)
from .goal_runtime_certificate import (
    learning_uncertain_policy,
    post_promote_maintenance_policy,
)
from .mechanism_review_runtime import build_report as build_mechanism_review_report
from .mutation_proposal_runtime import build_report as build_mutation_proposal_report
from .run_mechanism_experiment_runtime import run_mechanism_experiment

AUTO_IMPROVE_SESSION_SCHEMA = AUTO_IMPROVE_SESSION_SCHEMA_PATH
DEFAULT_MECHANISM_REVIEW_REPORT = "ops/reports/mechanism-review-candidates.json"
DEFAULT_MUTATION_PROPOSAL_REPORT = "ops/reports/mutation-proposals.json"
DEFAULT_MAINTENANCE_ACTION_PLAN = "tmp/goal-runtime-maintenance-action.json"
MAINTENANCE_ACTION_PLAN_SCHEMA = "ops/schemas/goal-runtime-maintenance-action-plan.schema.json"
REPEATED_BLOCKER_THRESHOLD = 2
REMEDIATION_BACKLOG_REPORT = "ops/reports/remediation-backlog.json"
REPEAT_BACKLOG_ITEM_TYPES = frozenset(
    {
        "repeated_auto_improve_blocker",
        "repeated_negative_lesson",
    }
)


class AutoImproveError(Exception):
    exit_code = 8


class AutoImproveUsageError(AutoImproveError):
    exit_code = 2


class AutoImproveLearningReviewRequiredError(AutoImproveError):
    exit_code = 4


_increment_counter = increment_counter
_build_iteration_rollup = build_iteration_rollup
_build_routing_rollup = build_routing_rollup
_build_executor_rollup = build_executor_rollup
_build_telemetry_rollup = build_telemetry_rollup
_build_session_rollups = build_session_rollups
_build_proposal_queue = build_proposal_queue
_select_next_proposal = select_next_proposal
_role_report_path = role_report_path
_detect_executor_failure = detect_executor_failure
_mutation_command = mutation_command
_write_iteration_telemetry = write_iteration_telemetry


@dataclass(frozen=True)
class RefreshSelectPhaseResult:
    proposal: dict | None
    queue_snapshot: list[str]
    stop_reason: str | None = None


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


@dataclass
class AutoImproveLoopState:
    attempted: set[str]
    quarantined: set[str]
    consecutive_failures: int
    stop_reason: str
    start_monotonic: float
    pre_promotion_failure_outcomes: set[str]
    repeat_backlog_repair_active: bool = False


TERMINAL_SUCCESS_OUTCOMES = frozenset({"promoted"})
MAINTENANCE_WORK_ITEMS = (
    "mechanism_review_report",
    "mutation_proposal_report",
    "auto_improve_readiness_report",
    "auto_improve_session_report",
)
DEFAULT_POST_PROMOTE_MAINTENANCE_CYCLES = 1
STABLE_MAINTENANCE_QUEUE_THRESHOLD = 2
MAINTENANCE_ACTION_RESUME_TARGET = "auto-improve-goal-maintenance-action"
MAINTENANCE_ACTION_RUNNER_ACTION = "resume_session_with_additional_proposal_budget"


def _int_value(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _resolve_budget_value(name: str, value: int | None, default: int) -> int:
    resolved = default if value is None else value
    if not isinstance(resolved, int) or isinstance(resolved, bool) or resolved < 1:
        raise AutoImproveUsageError(f"{name} must be an integer greater than or equal to 1")
    return resolved


def _resolve_maintenance_interval(value: int | None) -> int:
    resolved = 300 if value is None else value
    if not isinstance(resolved, int) or isinstance(resolved, bool) or resolved < 1:
        raise AutoImproveUsageError(
            "maintenance_interval_seconds must be an integer greater than or equal to 1"
        )
    return resolved


def _resolve_post_promote_maintenance_cycles(value: int | None) -> int:
    resolved = DEFAULT_POST_PROMOTE_MAINTENANCE_CYCLES if value is None else value
    if not isinstance(resolved, int) or isinstance(resolved, bool) or resolved < 0:
        raise AutoImproveUsageError(
            "post_promote_maintenance_cycles must be an integer greater than or equal to 0"
        )
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


def _mapping_value(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else {}


def _list_text(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dict_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _is_open_repeat_backlog_item(item: Mapping[str, Any]) -> bool:
    status = str(item.get("status", "")).strip().lower()
    if status != "open":
        return False
    severity = str(item.get("severity", "")).strip()
    item_type = str(item.get("item_type", "")).strip()
    return severity == "blocks_repeat" or item_type in REPEAT_BACKLOG_ITEM_TYPES


def _open_repeat_backlog_items(vault: Path) -> list[dict[str, Any]]:
    report = load_optional_json_object(vault / REMEDIATION_BACKLOG_REPORT)
    items = [
        item
        for item in _dict_items(report.get("items"))
        if _is_open_repeat_backlog_item(item)
    ]
    return sorted(
        items,
        key=lambda item: (
            str(item.get("item_id", "")).strip(),
            str(item.get("blocker_id", "")).strip(),
        ),
    )


def _open_repeat_backlog_blocker_reason(vault: Path) -> str:
    for item in _open_repeat_backlog_items(vault):
        for key in ("blocker_id", "item_id", "item_type"):
            reason = str(item.get(key, "")).strip()
            if reason:
                return reason
    return ""


def _proposal_repairs_repeat_backlog(proposal: Mapping[str, Any] | None) -> bool:
    if not isinstance(proposal, Mapping):
        return False
    if _list_text(proposal.get("blocked_by")):
        return False
    proposal_id = str(proposal.get("proposal_id", "")).strip()
    family = str(proposal.get("family", "")).strip()
    failure_mode = str(proposal.get("failure_mode", "")).strip()
    return (
        family == "next_run_failure_repair"
        or failure_mode == "next_run_failure_repair"
        or proposal_id.startswith("next_run_failure_repair__")
    )


def _record_pre_run_selected_proposal_metadata(
    session: dict,
    proposals_report: Mapping[str, Any],
) -> bool:
    proposal, _queue_snapshot = _select_next_proposal(
        dict(proposals_report),
        attempted=set(_list_text(session.get("attempted_proposal_ids"))),
        quarantined=set(_list_text(session.get("quarantined_proposal_ids"))),
    )
    metadata = dict(_mapping_value(session, "metadata"))
    metadata["pre_run_selected_proposal"] = {
        "proposal_id": str(proposal.get("proposal_id", "")).strip() if proposal else "",
        "family": str(proposal.get("family", "")).strip() if proposal else "",
        "failure_mode": str(proposal.get("failure_mode", "")).strip() if proposal else "",
        "blocked_by": _list_text(proposal.get("blocked_by")) if proposal else [],
        "repeat_backlog_repair": _proposal_repairs_repeat_backlog(proposal),
    }
    session["metadata"] = metadata
    return bool(metadata["pre_run_selected_proposal"]["repeat_backlog_repair"])


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


def _empty_loop_state(context: RuntimeContext) -> dict:
    return {
        "consecutive_failures": 0,
        "last_outcome": "",
        "last_decision": "",
        "last_run_id": "",
        "last_blocking_reason": "",
        "blocking_reason_counts": {},
        "repeated_blocker_stop": False,
        "repeated_blocker_reason": "",
        "remediation_backlog_path": REMEDIATION_BACKLOG_REPORT,
        "updated_at": context.isoformat_z(),
    }


def _blocking_reason_counts_from_iterations(session: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for iteration in session.get("iterations", []):
        if not isinstance(iteration, Mapping):
            continue
        outcome = str(iteration.get("outcome", "")).strip()
        if not outcome or outcome in TERMINAL_SUCCESS_OUTCOMES:
            continue
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


def _normalize_blocking_reason_counts(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    normalized: dict[str, int] = {}
    for key, count in value.items():
        reason = str(key).strip()
        if not reason:
            continue
        normalized[reason] = max(0, _int_value(count, 0))
    return normalized


def _reconstructed_loop_state(session: dict, *, context: RuntimeContext) -> dict:
    state = _empty_loop_state(context)
    consecutive_failures = 0
    blocking_reason_counts: dict[str, int] = {}
    for iteration in session.get("iterations", []):
        if not isinstance(iteration, dict):
            continue
        outcome = str(iteration.get("outcome", "")).strip()
        if outcome in TERMINAL_SUCCESS_OUTCOMES:
            consecutive_failures = 0
        elif outcome:
            consecutive_failures += 1
            blocking_reason_counts[outcome] = blocking_reason_counts.get(outcome, 0) + 1
        state = {
            "consecutive_failures": consecutive_failures,
            "last_outcome": outcome,
            "last_decision": str(iteration.get("decision", "")).strip(),
            "last_run_id": str(iteration.get("run_id", "")).strip(),
            "last_blocking_reason": "" if outcome in TERMINAL_SUCCESS_OUTCOMES else outcome,
            "blocking_reason_counts": dict(blocking_reason_counts),
            "repeated_blocker_stop": False,
            "repeated_blocker_reason": "",
            "remediation_backlog_path": REMEDIATION_BACKLOG_REPORT,
            "updated_at": context.isoformat_z(),
        }
    return state


def _normalize_loop_state(session: dict, *, context: RuntimeContext) -> dict:
    existing = session.get("loop_state")
    if not isinstance(existing, dict):
        return _reconstructed_loop_state(session, context=context)
    reconstructed_counts = _blocking_reason_counts_from_iterations(session)
    existing_counts = _normalize_blocking_reason_counts(existing.get("blocking_reason_counts"))
    blocking_reason_counts = existing_counts or reconstructed_counts
    normalized = _empty_loop_state(context)
    normalized.update(
        {
            "consecutive_failures": max(
                0,
                _int_value(existing.get("consecutive_failures"), 0),
            ),
            "last_outcome": str(existing.get("last_outcome", "")).strip(),
            "last_decision": str(existing.get("last_decision", "")).strip(),
            "last_run_id": str(existing.get("last_run_id", "")).strip(),
            "last_blocking_reason": str(existing.get("last_blocking_reason", "")).strip(),
            "blocking_reason_counts": blocking_reason_counts,
            "repeated_blocker_stop": bool(existing.get("repeated_blocker_stop", False)),
            "repeated_blocker_reason": str(
                existing.get("repeated_blocker_reason", "")
            ).strip(),
            "remediation_backlog_path": str(
                existing.get("remediation_backlog_path", REMEDIATION_BACKLOG_REPORT)
            ).strip()
            or REMEDIATION_BACKLOG_REPORT,
            "updated_at": str(existing.get("updated_at", "")).strip() or context.isoformat_z(),
        }
    )
    return normalized


def _ensure_session_loop_state(session: dict, *, context: RuntimeContext) -> dict:
    session["loop_state"] = _normalize_loop_state(session, context=context)
    return session["loop_state"]


def _parse_utc_timestamp(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC).replace(microsecond=0)


def _format_utc_timestamp(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _session_generated_at(session: dict, *, context: RuntimeContext) -> str:
    generated = _parse_utc_timestamp(context.isoformat_z())
    observed_times: list[dt.datetime] = []
    for decision in session.get("next_run_decisions", []):
        if not isinstance(decision, dict):
            continue
        observed = _parse_utc_timestamp(decision.get("observed_at"))
        if observed is not None:
            observed_times.append(observed)

    latest_observed = max(observed_times, default=None)
    if latest_observed is not None and (generated is None or latest_observed > generated):
        return _format_utc_timestamp(latest_observed)
    if generated is not None:
        return _format_utc_timestamp(generated)
    return context.isoformat_z()


def _write_session_report(vault: Path, session: dict, *, context: RuntimeContext) -> Path:
    session = normalize_session_report(vault, dict(session))
    _ensure_session_loop_state(session, context=context)
    session["rollups"] = build_session_rollups(vault, session)
    policy, resolved_policy_path = load_policy(vault)
    generated_at = _session_generated_at(session, context=context)
    session["generated_at"] = generated_at
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind="auto_improve_session",
        producer="ops.scripts.auto_improve_runtime",
        source_command="python -m ops.scripts.auto_improve_runtime",
        resolved_policy_path=resolved_policy_path,
        schema_path=AUTO_IMPROVE_SESSION_SCHEMA,
        source_paths=[
            "ops/scripts/mechanism/auto_improve_runtime.py",
            "ops/scripts/mechanism/auto_improve_session_runtime.py",
            "ops/scripts/mechanism/auto_improve_next_run_decision_runtime.py",
            "ops/scripts/core/artifact_freshness_runtime.py",
        ],
        text_inputs={
            "session_id": str(session.get("session_id", "")),
            "status": str(session.get("status", "")),
            "policy_version": str(policy.get("version", "")),
        },
    )
    session = embed_artifact_envelope_metadata(session, envelope)
    schema = load_schema_with_vault_override(vault, AUTO_IMPROVE_SESSION_SCHEMA)
    destination = vault / session["path"]
    write_schema_validated_json(
        destination,
        session,
        schema,
        context="auto improve session schema validation failed",
    )
    write_routing_provenance_aggregate(vault, session, context=context)
    return destination


def _load_session_report(vault: Path, session_id: str) -> dict:
    path = vault / "ops" / "reports" / "auto-improve-sessions" / f"{session_id}.json"
    return read_json_object(path)


def refresh_auto_improve_session_report(
    vault: Path,
    *,
    session_id: str,
    policy_path: str | None = None,
    executor_name: str = "codex_exec",
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, _resolved_policy_path = load_policy(vault, policy_path)
    refresh_context = context or RuntimeContext.from_policy(policy, executor_id=executor_name)
    session = _load_session_report(vault, session_id)
    destination = _write_session_report(vault, session, context=refresh_context)
    refreshed = read_json_object(destination)
    return {
        "session_id": session_id,
        "session_report": report_path(vault, destination),
        "generated_at": str(refreshed.get("generated_at", "")).strip(),
        "status": str(refreshed.get("status", "")).strip(),
        "stop_reason": str(refreshed.get("stop_reason", "")).strip(),
    }


def _new_session_id(context: RuntimeContext) -> str:
    return "auto-improve-" + re.sub(r"[^0-9a-z]+", "-", context.isoformat_z().lower()).strip("-")


def _run_slug(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return normalized[:48] or "proposal"


def _build_run_id(session_id: str, iteration: int, proposal: dict) -> str:
    primary = proposal["primary_targets"][0]
    return f"{session_id}-run-{iteration:02d}-{_run_slug(Path(primary).stem)}"


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
        raise AutoImproveUsageError(
            f"resume executor mismatch: {executor_name} != {session_executor}"
        )


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


def _pre_run_readiness_snapshot(
    vault: Path,
    readiness_report: dict,
    readiness_destination: Path,
) -> dict[str, object]:
    execution = readiness_report.get("execution_readiness")
    if not isinstance(execution, dict):
        execution = {}
    learning = readiness_report.get("learning_readiness")
    if not isinstance(learning, dict):
        learning = {}
    queue = readiness_report.get("queue")
    if not isinstance(queue, dict):
        queue = {}
    metrics = learning.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
    return {
        "report": report_path(vault, readiness_destination),
        "generated_at": str(readiness_report.get("generated_at", "")).strip(),
        "execution_status": str(execution.get("status", "")).strip(),
        "learning_status": str(learning.get("status", "")).strip(),
        "learning_gate_effect": str(learning.get("gate_effect", "")).strip(),
        "runnable_proposal_count": _int_value(queue.get("runnable_proposal_count")),
        "session_reports_considered": _int_value(metrics.get("session_reports_considered")),
    }


def _readiness_queue_snapshot(readiness_report: Mapping[str, Any]) -> list[str]:
    queue = readiness_report.get("queue")
    if not isinstance(queue, Mapping):
        return []
    return _list_text(queue.get("runnable_proposal_ids"))


def _readiness_runnable_proposal_count(readiness_report: Mapping[str, Any]) -> int:
    queue = readiness_report.get("queue")
    if not isinstance(queue, Mapping):
        return 0
    return _int_value(queue.get("runnable_proposal_count"))


def _learning_uncertain_contract_authorization(session: Mapping[str, Any]) -> dict[str, object]:
    goal_contract = _mapping_value(session, "goal_contract")
    execution_policy = _mapping_value(goal_contract, "execution_policy")
    learning_policy = _mapping_value(execution_policy, "learning_uncertain")
    source = str(learning_policy.get("authorization_source", "")).strip()
    allowed = (
        bool(learning_policy.get("allow_bounded_trial", False))
        and bool(learning_policy.get("requires_explicit_authorization", False))
        and source == "codex_goal_contract"
    )
    return {
        "allowed": allowed,
        "authorization_source": source if allowed else "",
        "command_flag": str(learning_policy.get("command_flag", "")).strip(),
    }


def _preflight_learning_gate(
    vault: Path,
    start: AutoImproveSessionStart,
    *,
    allow_learning_uncertain: bool,
) -> bool:
    mechanism_review, proposals = _refresh_reports(
        vault,
        start.policy,
        start.resolved_policy_path,
        context=start.context,
    )
    readiness_report = build_readiness_report(
        vault,
        policy_path=str(start.resolved_policy_path),
        context=start.context,
        mechanism_review_report=mechanism_review,
        mutation_proposal_report=proposals,
    )
    readiness_destination = write_readiness_report(vault, readiness_report)
    runnable_proposal_ids = _readiness_queue_snapshot(readiness_report)
    repeat_backlog_repair_active = _record_pre_run_selected_proposal_metadata(
        start.session,
        proposals,
    )
    review_required = learning_review_required(readiness_report)
    contract_authorization = _learning_uncertain_contract_authorization(start.session)
    contract_authorized = bool(contract_authorization["allowed"])
    effective_allow_learning_uncertain = bool(
        allow_learning_uncertain or contract_authorized
    )
    authorization_source = (
        "command_flag"
        if allow_learning_uncertain
        else str(contract_authorization["authorization_source"])
    )
    start.session["status"] = "running"
    start.session["stop_reason"] = "running"
    start.session["queue_snapshot"] = runnable_proposal_ids
    start.session["learning_mode"] = {
        "allow_learning_uncertain": effective_allow_learning_uncertain,
        "bounded_trial": bool(review_required and effective_allow_learning_uncertain),
        "authorization_source": authorization_source,
        "contract_authorized": contract_authorized,
        "command_flag": str(contract_authorization["command_flag"])
        or ("--allow-learning-uncertain" if allow_learning_uncertain else ""),
    }
    start.session["pre_run_readiness"] = _pre_run_readiness_snapshot(
        vault,
        readiness_report,
        readiness_destination,
    )
    if review_required and not effective_allow_learning_uncertain:
        start.session["status"] = "blocked"
        start.session["stop_reason"] = "learning_review_required"
        _write_session_report(vault, start.session, context=start.context)
        append_runtime_event(
            vault,
            context=start.context,
            component="auto_improve_session",
            phase="preflight",
            decision="learning_review_required",
            artifact_path=report_path(vault, readiness_destination),
            session_id=start.session_id,
            policy_version=start.policy.get("version"),
        )
        learning = readiness_report.get("learning_readiness")
        recommended_next_step = ""
        if isinstance(learning, dict):
            recommended_next_step = str(learning.get("recommended_next_step", "")).strip()
        message = recommended_next_step or (
            "Auto-improve learning readiness requires explicit review before execution. "
            "Rerun with --allow-learning-uncertain only for a bounded trial."
        )
        raise AutoImproveLearningReviewRequiredError(message)
    _write_session_report(vault, start.session, context=start.context)
    return repeat_backlog_repair_active


def _refresh_reports(
    vault: Path,
    policy: dict,
    policy_path: Path,
    *,
    context: RuntimeContext,
) -> tuple[dict, dict]:
    mechanism_review = build_mechanism_review_report(
        vault,
        policy,
        policy_path,
        context=context,
    )
    write_json_object(vault / DEFAULT_MECHANISM_REVIEW_REPORT, mechanism_review)
    proposals = build_mutation_proposal_report(
        vault,
        policy,
        policy_path,
        context=context,
    )
    write_json_object(vault / DEFAULT_MUTATION_PROPOSAL_REPORT, proposals)
    return mechanism_review, proposals


def _refresh_select_phase(
    vault: Path,
    policy: dict,
    resolved_policy_path: Path,
    *,
    attempted: set[str],
    quarantined: set[str],
    context: RuntimeContext,
) -> RefreshSelectPhaseResult:
    _mechanism_review, proposals_report = _refresh_reports(
        vault,
        policy,
        resolved_policy_path,
        context=context,
    )
    proposal, queue_snapshot = _select_next_proposal(
        proposals_report,
        attempted=attempted,
        quarantined=quarantined,
    )
    return RefreshSelectPhaseResult(
        proposal=proposal,
        queue_snapshot=queue_snapshot,
        stop_reason="queue_exhausted" if proposal is None else None,
    )


def _route_scaffold_phase(
    vault: Path,
    policy: dict,
    resolved_policy_path: Path,
    *,
    run_id: str,
    proposal: dict,
    context: RuntimeContext,
) -> RouteScaffoldPhaseResult:
    return route_scaffold_phase(
        vault,
        policy,
        resolved_policy_path,
        run_id=run_id,
        proposal=proposal,
        proposal_report_path=DEFAULT_MUTATION_PROPOSAL_REPORT,
        context=context,
        dependencies=RouteScaffoldDependencies(
            build_scope_freeze=build_scope_freeze,
            write_scope_freeze=write_scope_freeze,
            run_selector=run_selector,
            run_mechanism_experiment=run_mechanism_experiment,
            append_ledger_event=append_ledger_event,
            role_report_path=_role_report_path,
        ),
    )


def _execute_evaluate_phase(request: ExecuteEvaluateRequest) -> ExecuteEvaluatePhaseResult:
    return execute_evaluate_phase(request)


def _persist_iteration_phase(
    vault: Path,
    session: dict,
    *,
    session_id: str,
    iteration: int,
    proposal: dict,
    route_scaffold: RouteScaffoldPhaseResult,
    execution: ExecuteEvaluatePhaseResult,
    quarantined: set[str],
    context: RuntimeContext,
) -> PersistIterationPhaseResult:
    return persist_iteration_phase(
        vault,
        session,
        session_id=session_id,
        iteration=iteration,
        proposal=proposal,
        route_scaffold=route_scaffold,
        execution=execution,
        quarantined=quarantined,
        context=context,
        dependencies=PersistIterationDependencies(
            apply_execution_outcome=apply_execution_outcome,
            write_iteration_telemetry=_write_iteration_telemetry,
            write_run_artifact_fingerprint=write_run_artifact_fingerprint,
            write_session_report=_write_session_report,
        ),
    )


def _initial_auto_improve_loop_state(auto_policy: dict, session: dict) -> AutoImproveLoopState:
    return AutoImproveLoopState(
        attempted=set(session["attempted_proposal_ids"]),
        quarantined=set(session["quarantined_proposal_ids"]),
        consecutive_failures=max(
            0,
            _int_value(session.get("loop_state", {}).get("consecutive_failures"), 0),
        ),
        stop_reason="queue_exhausted",
        start_monotonic=time.monotonic(),
        pre_promotion_failure_outcomes=set(
            auto_policy["quarantine"]["pre_promotion_failure_outcomes"]
        ),
    )


def _repeated_blocker_reason(session: Mapping[str, Any]) -> str:
    loop_state = _mapping_value(session, "loop_state")
    counts = _normalize_blocking_reason_counts(loop_state.get("blocking_reason_counts"))
    if not counts:
        counts = _blocking_reason_counts_from_iterations(session)
    for reason, count in sorted(counts.items()):
        if count >= REPEATED_BLOCKER_THRESHOLD:
            return reason
    return ""


def _mark_repeated_blocker_stop(session: dict, reason: str, *, context: RuntimeContext) -> None:
    loop_state = _ensure_session_loop_state(session, context=context)
    counts = _normalize_blocking_reason_counts(loop_state.get("blocking_reason_counts"))
    counts[reason] = max(counts.get(reason, 0), REPEATED_BLOCKER_THRESHOLD)
    loop_state["blocking_reason_counts"] = counts
    loop_state["repeated_blocker_stop"] = True
    loop_state["repeated_blocker_reason"] = reason
    loop_state["remediation_backlog_path"] = REMEDIATION_BACKLOG_REPORT


def _stop_reason_before_iteration(
    vault: Path,
    session: dict,
    state: AutoImproveLoopState,
    *,
    context: RuntimeContext,
    check_open_repeat_backlog: bool = True,
) -> str | None:
    repeated_blocker_reason = _repeated_blocker_reason(session)
    if repeated_blocker_reason:
        _mark_repeated_blocker_stop(session, repeated_blocker_reason, context=context)
        return "repeated_blocker_backlog_required"
    open_backlog_reason = (
        _open_repeat_backlog_blocker_reason(vault)
        if check_open_repeat_backlog and not state.repeat_backlog_repair_active
        else ""
    )
    if open_backlog_reason:
        _mark_repeated_blocker_stop(session, open_backlog_reason, context=context)
        return "repeated_blocker_backlog_required"
    if len(session.get("iterations", [])) >= session["budget"]["max_proposals"]:
        return "proposal_budget_exhausted"
    if time.monotonic() - state.start_monotonic > session["budget"]["max_minutes"] * 60:
        return "time_budget_exhausted"
    if state.consecutive_failures >= session["budget"]["max_consecutive_failures"]:
        return "failure_budget_exhausted"
    return None


def _stop_reason_after_loop(
    vault: Path,
    session: dict,
    state: AutoImproveLoopState,
    *,
    context: RuntimeContext,
) -> str:
    repeated_blocker_reason = _repeated_blocker_reason(session)
    if repeated_blocker_reason:
        _mark_repeated_blocker_stop(session, repeated_blocker_reason, context=context)
        return "repeated_blocker_backlog_required"
    open_backlog_reason = (
        ""
        if state.repeat_backlog_repair_active
        else _open_repeat_backlog_blocker_reason(vault)
    )
    if open_backlog_reason:
        _mark_repeated_blocker_stop(session, open_backlog_reason, context=context)
        return "repeated_blocker_backlog_required"
    if (
        state.stop_reason == "queue_exhausted"
        and len(session.get("iterations", [])) >= session["budget"]["max_proposals"]
    ):
        return "proposal_budget_exhausted"
    return state.stop_reason


def _run_auto_improve_iteration(
    vault: Path,
    start: AutoImproveSessionStart,
    state: AutoImproveLoopState,
    iteration: int,
) -> bool:
    iteration_context = start.context.with_iteration(iteration).with_executor(
        start.session["executor"]["name"]
    )
    iteration_result = run_auto_improve_iteration_helper(
        AutoImproveIterationRequest(
            vault=vault,
            policy=start.policy,
            resolved_policy_path=start.resolved_policy_path,
            session=start.session,
            session_id=start.session_id,
            proposal_report_path=DEFAULT_MUTATION_PROPOSAL_REPORT,
            iteration=iteration,
            attempted=state.attempted,
            quarantined=state.quarantined,
            consecutive_failures=state.consecutive_failures,
            pre_promotion_failure_outcomes=state.pre_promotion_failure_outcomes,
            context=iteration_context,
        ),
        dependencies=AutoImproveIterationDependencies(
            refresh_select_phase=_refresh_select_phase,
            route_scaffold_phase=_route_scaffold_phase,
            execute_evaluate_dependencies=ExecuteEvaluateDependencies(
                mutation_command=_mutation_command,
                run_mechanism_experiment=run_mechanism_experiment,
                role_report_path=_role_report_path,
                evaluate_scope_blocked=evaluate_scope_blocked,
                evaluate_experiment_result=evaluate_experiment_result,
                evaluate_mutation_error=evaluate_mutation_error,
                evaluate_experiment_error=evaluate_experiment_error,
            ),
            execute_evaluate_phase_fn=execute_evaluate_phase,
            persist_iteration_dependencies=PersistIterationDependencies(
                apply_execution_outcome=apply_execution_outcome,
                write_iteration_telemetry=_write_iteration_telemetry,
                write_run_artifact_fingerprint=write_run_artifact_fingerprint,
                write_session_report=_write_session_report,
            ),
            persist_iteration_phase_fn=persist_iteration_phase,
            append_runtime_event=append_runtime_event,
        ),
        build_run_id=_build_run_id,
    )
    state.consecutive_failures = iteration_result.consecutive_failures
    if iteration_result.stop_reason is not None:
        state.stop_reason = iteration_result.stop_reason
    return iteration_result.keep_running


def _complete_auto_improve_session(
    vault: Path,
    start: AutoImproveSessionStart,
    state: AutoImproveLoopState,
) -> dict:
    return complete_auto_improve_session(
        vault,
        session=start.session,
        session_id=start.session_id,
        stop_reason=state.stop_reason,
        policy=start.policy,
        resolved_policy_path=start.resolved_policy_path,
        context=start.context,
        dependencies=SessionCompletionDependencies(
            write_session_report=_write_session_report,
            write_promotion_decision_trends=write_promotion_decision_trends,
            write_outcome_metrics_report=write_outcome_metrics_report,
        ),
    )


def _successful_improvement_count(session: Mapping[str, Any]) -> int:
    count = 0
    for iteration in session.get("iterations", []):
        if not isinstance(iteration, Mapping):
            continue
        if (
            str(iteration.get("decision", "")).strip() == "PROMOTE"
            or str(iteration.get("outcome", "")).strip() == "promoted"
            or str(iteration.get("status", "")).strip() == "promoted"
        ):
            count += 1
    return count


def _last_iteration_outcome(session: Mapping[str, Any]) -> str:
    iterations = session.get("iterations", [])
    if not isinstance(iterations, list):
        return ""
    for iteration in reversed(iterations):
        if not isinstance(iteration, Mapping):
            continue
        return str(iteration.get("outcome", "")).strip()
    return ""


def _expected_maintenance_cycle_count(
    *,
    start_elapsed_seconds: int,
    target_elapsed_seconds: int,
    interval_seconds: int,
) -> int:
    if start_elapsed_seconds >= target_elapsed_seconds:
        return 0
    remaining = target_elapsed_seconds - start_elapsed_seconds
    return (remaining + interval_seconds - 1) // interval_seconds + 1


def _maintenance_cycle_count(session: Mapping[str, Any]) -> int:
    maintenance = _mapping_value(session, "maintenance")
    return _int_value(maintenance.get("cycle_count"))


def maintenance_action_resume_plan(
    vault: Path,
    *,
    session_id: str,
    mutation_proposals_report_path: str = DEFAULT_MUTATION_PROPOSAL_REPORT,
) -> dict[str, Any]:
    session = _load_session_report(vault, session_id)
    maintenance = _mapping_value(session, "maintenance")
    queue_action = _mapping_value(maintenance, "queue_action")
    queue_action_payload: dict[str, Any] = {
        "status": "none",
        "reason": "",
        "proposal_ids": [],
        "runner_action": "none",
        "proposal_budget_increment": 0,
        "resume_target": "",
        "recommended_next_step": "",
    }
    queue_action_payload.update(dict(queue_action))
    if not isinstance(queue_action_payload.get("proposal_ids"), list):
        queue_action_payload["proposal_ids"] = []
    current_budget = _int_value(_mapping_value(session, "budget").get("max_proposals"))
    current_iterations = len(session.get("iterations", [])) if isinstance(session.get("iterations"), list) else 0
    base_plan: dict[str, Any] = {
        "artifact_kind": "goal_runtime_maintenance_action_plan",
        "producer": "ops.scripts.auto_improve_runtime",
        "session_id": session_id,
        "status": "attention",
        "current_max_proposals": current_budget,
        "current_iteration_count": current_iterations,
        "next_max_proposals": current_budget,
        "queue_action": queue_action_payload,
        "selected_proposal": {
            "proposal_id": "",
            "family": "",
            "failure_mode": "",
        },
        "blockers": [],
        "recommended_next_action": "",
        "decisions": {
            "can_resume": False,
            "requires_budget_increment": False,
        },
    }
    if str(queue_action_payload.get("status", "")).strip() != "action_required":
        base_plan["status"] = "pass"
        base_plan["recommended_next_action"] = "No maintenance queue action requires a resume."
        return base_plan
    if str(queue_action_payload.get("runner_action", "")).strip() != MAINTENANCE_ACTION_RUNNER_ACTION:
        base_plan["blockers"] = ["maintenance queue action has no executable runner action"]
        base_plan["recommended_next_action"] = (
            "Refresh maintenance evidence, then rerun maintenance action planning."
        )
        return base_plan
    increment = _int_value(queue_action_payload.get("proposal_budget_increment"))
    if increment < 1:
        base_plan["blockers"] = ["maintenance queue action has invalid proposal budget increment"]
        base_plan["recommended_next_action"] = (
            "Refresh maintenance evidence so queue_action.proposal_budget_increment "
            "declares the explicit resume budget increase."
        )
        return base_plan
    proposals_report = load_optional_json_object(vault / mutation_proposals_report_path)
    proposals = proposals_report.get("proposals")
    if not isinstance(proposals, list):
        base_plan["blockers"] = ["mutation proposal report is missing or invalid"]
        base_plan["recommended_next_action"] = (
            "Run make mutation-proposal or make goal-runtime-between-run-settle, "
            "then rerun the maintenance action."
        )
        return base_plan
    selected, actionable_queue = _select_next_proposal(
        {"proposals": proposals},
        attempted=set(_list_text(session.get("attempted_proposal_ids"))),
        quarantined=set(_list_text(session.get("quarantined_proposal_ids"))),
    )
    action_proposal_ids = set(_list_text(queue_action_payload.get("proposal_ids")))
    if not selected:
        base_plan["blockers"] = ["no unattempted runnable proposal is available"]
        base_plan["recommended_next_action"] = (
            "Refresh mutation proposals and readiness. If the queue remains blocked, "
            "the maintenance action cannot complete by adding proposal budget alone."
        )
        return base_plan
    selected_proposal_id = str(selected.get("proposal_id", "")).strip()
    if action_proposal_ids and selected_proposal_id not in action_proposal_ids:
        base_plan["blockers"] = ["selected proposal is not in the maintenance action queue"]
        base_plan["recommended_next_action"] = (
            "Run make goal-runtime-between-run-settle so readiness and mutation proposal "
            "queue evidence converge, then rerun the maintenance action."
        )
        return base_plan
    next_budget = max(current_budget + increment, current_iterations + 1)
    base_plan.update(
        {
            "status": "pass",
            "next_max_proposals": next_budget,
            "selected_proposal": {
                "proposal_id": selected_proposal_id,
                "family": str(selected.get("family", "")).strip(),
                "failure_mode": str(selected.get("failure_mode", "")).strip(),
            },
            "recommended_next_action": (
                f"Run make {MAINTENANCE_ACTION_RESUME_TARGET} with "
                f"GOAL_MAX_PROPOSALS={next_budget}."
            ),
            "decisions": {
                "can_resume": True,
                "requires_budget_increment": next_budget > current_budget,
            },
            "actionable_queue_snapshot": actionable_queue,
        }
    )
    return base_plan


def write_maintenance_action_resume_plan(
    vault: Path,
    plan: Mapping[str, Any],
    *,
    out_path: str = DEFAULT_MAINTENANCE_ACTION_PLAN,
) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=dict(plan),
            schema_path=MAINTENANCE_ACTION_PLAN_SCHEMA,
            out_path=out_path,
            default_relative_path=DEFAULT_MAINTENANCE_ACTION_PLAN,
            context="goal runtime maintenance action plan schema validation failed",
            trailing_newline=True,
        )
    )


def _maintenance_queue_action(queue_snapshot: list[str]) -> dict[str, Any]:
    if not queue_snapshot:
        return {
            "status": "none",
            "reason": "queue_empty",
            "proposal_ids": [],
            "runner_action": "none",
            "proposal_budget_increment": 0,
            "resume_target": "",
            "recommended_next_step": "Refresh auto-improve readiness and inspect queue remediations.",
        }
    if all(item.startswith("recent_log_overlap_queue_blocked__") for item in queue_snapshot):
        return {
            "status": "action_required",
            "reason": "recent_log_overlap_queue_blocked",
            "proposal_ids": queue_snapshot,
            "runner_action": MAINTENANCE_ACTION_RUNNER_ACTION,
            "proposal_budget_increment": 1,
            "resume_target": MAINTENANCE_ACTION_RESUME_TARGET,
            "recommended_next_step": (
                f"Run make {MAINTENANCE_ACTION_RESUME_TARGET} so the generated "
                "recent-log-overlap queue-unblock proposal can run instead of "
                "repeating maintenance refreshes."
            ),
        }
    return {
        "status": "action_required",
        "reason": "stable_runnable_queue",
        "proposal_ids": queue_snapshot,
        "runner_action": MAINTENANCE_ACTION_RUNNER_ACTION,
        "proposal_budget_increment": 1,
        "resume_target": MAINTENANCE_ACTION_RESUME_TARGET,
        "recommended_next_step": (
            f"Run make {MAINTENANCE_ACTION_RESUME_TARGET} so the stable queued "
            "proposal can run with one additional proposal budget slot."
        ),
    }


def _maintenance_cycle_queue_metadata(
    cycles: list[Any],
    queue_snapshot: list[str],
    runnable_proposal_count: int,
) -> dict[str, Any]:
    previous = cycles[-1] if cycles and isinstance(cycles[-1], Mapping) else {}
    previous_snapshot = _list_text(previous.get("queue_snapshot")) if previous else []
    previous_runnable_count = _int_value(previous.get("runnable_proposal_count"), -1)
    queue_changed = not previous or queue_snapshot != previous_snapshot
    runnable_count_changed = previous_runnable_count != runnable_proposal_count
    stable_count = 1
    if previous and not queue_changed:
        stable_count = _int_value(previous.get("stable_queue_snapshot_count"), 1) + 1
    meaningful_reasons: list[str] = []
    if not previous:
        meaningful_reasons.append("post_promote_observation")
    if queue_changed and previous:
        meaningful_reasons.append("queue_snapshot_changed")
    if runnable_count_changed and previous:
        meaningful_reasons.append("runnable_proposal_count_changed")
    meaningful = bool(meaningful_reasons)
    return {
        "queue_snapshot_changed": queue_changed,
        "stable_queue_snapshot_count": stable_count,
        "meaningful": meaningful,
        "meaningful_reasons": meaningful_reasons,
        "queue_action": _maintenance_queue_action(queue_snapshot),
    }


def _record_maintenance_cycle(
    vault: Path,
    start: AutoImproveSessionStart,
    state: AutoImproveLoopState,
    *,
    index: int,
    cycle_started_elapsed_seconds: int,
) -> None:
    cycle_started_monotonic = time.monotonic()
    mechanism_review, proposals = _refresh_reports(
        vault,
        start.policy,
        start.resolved_policy_path,
        context=start.context,
    )
    readiness_report = build_readiness_report(
        vault,
        policy_path=str(start.resolved_policy_path),
        context=start.context,
        mechanism_review_report=mechanism_review,
        mutation_proposal_report=proposals,
    )
    readiness_destination = write_readiness_report(vault, readiness_report)
    queue_snapshot = _readiness_queue_snapshot(readiness_report)
    start.session["queue_snapshot"] = queue_snapshot
    loop_state = _ensure_session_loop_state(start.session, context=start.context)
    loop_state["updated_at"] = start.context.isoformat_z()
    maintenance = _mapping_value(start.session, "maintenance")
    cycles = maintenance.get("cycles")
    if not isinstance(cycles, list):
        cycles = []
    session_report = start.session.get("path", "")
    cycle_completed_elapsed_seconds = int(time.monotonic() - state.start_monotonic)
    runnable_proposal_count = _readiness_runnable_proposal_count(readiness_report)
    queue_metadata = _maintenance_cycle_queue_metadata(
        cycles,
        queue_snapshot,
        runnable_proposal_count,
    )
    cycles.append(
        {
            "index": index,
            "observed_at": start.context.isoformat_z(),
            "cycle_started_elapsed_seconds": cycle_started_elapsed_seconds,
            "elapsed_seconds": cycle_completed_elapsed_seconds,
            "duration_ms": int(round((time.monotonic() - cycle_started_monotonic) * 1000)),
            "status": "pass",
            "work_items": list(MAINTENANCE_WORK_ITEMS),
            "mechanism_review_report": DEFAULT_MECHANISM_REVIEW_REPORT,
            "mutation_proposal_report": DEFAULT_MUTATION_PROPOSAL_REPORT,
            "readiness_report": report_path(vault, readiness_destination),
            "session_report": str(session_report),
            "runnable_proposal_count": runnable_proposal_count,
            "queue_snapshot": queue_snapshot,
            **queue_metadata,
        }
    )
    latest_cycle = cycles[-1]
    start.session["maintenance"] = {
        **dict(maintenance),
        "status": "running",
        "cycles": cycles,
        "cycle_count": len(cycles),
        "meaningful_cycle_count": len(
            [
                cycle
                for cycle in cycles
                if isinstance(cycle, Mapping)
                and bool(cycle.get("meaningful", False))
            ]
        ),
        "stable_queue_snapshot_count": _int_value(
            latest_cycle.get("stable_queue_snapshot_count")
        ),
        "stable_queue_snapshot": _list_text(latest_cycle.get("queue_snapshot")),
        "queue_action": dict(_mapping_value(latest_cycle, "queue_action")),
        "completed_at": start.context.isoformat_z(),
        "last_cycle_elapsed_seconds": cycle_completed_elapsed_seconds,
    }
    _write_session_report(vault, start.session, context=start.context)
    append_runtime_event(
        vault,
        context=start.context,
        component="auto_improve_session",
        phase="proposal_budget_maintenance",
        decision="cycle_pass",
        artifact_path=str(session_report),
        duration_ms=int(round((time.monotonic() - cycle_started_monotonic) * 1000)),
        session_id=start.session_id,
        policy_version=start.policy.get("version"),
    )


def _run_proposal_budget_maintenance(
    vault: Path,
    start: AutoImproveSessionStart,
    state: AutoImproveLoopState,
    *,
    interval_seconds: int,
    max_cycles: int | None,
) -> None:
    target_elapsed_seconds = start.session["budget"]["max_minutes"] * 60
    start_elapsed_seconds = int(time.monotonic() - state.start_monotonic)
    if max_cycles is None:
        expected_min_cycle_count = _expected_maintenance_cycle_count(
            start_elapsed_seconds=start_elapsed_seconds,
            target_elapsed_seconds=target_elapsed_seconds,
            interval_seconds=interval_seconds,
        )
        completion_condition = "time_budget"
    else:
        expected_min_cycle_count = max_cycles
        completion_condition = "post_promote_cycle_limit"
    start.session["maintenance"] = {
        "mode": "proposal_budget_runtime_maintenance",
        "status": "running",
        "started_at": start.context.isoformat_z(),
        "completed_at": "",
        "target_elapsed_seconds": target_elapsed_seconds,
        "target_cycle_count": expected_min_cycle_count,
        "completion_condition": completion_condition,
        "started_elapsed_seconds": start_elapsed_seconds,
        "interval_seconds": interval_seconds,
        "expected_min_cycle_count": expected_min_cycle_count,
        "cycle_count": 0,
        "meaningful_cycle_count": 0,
        "stable_queue_snapshot_count": 0,
        "stable_queue_snapshot": [],
        "queue_action": {
            "status": "none",
            "reason": "",
            "proposal_ids": [],
            "recommended_next_step": "",
        },
        "last_cycle_elapsed_seconds": 0,
        "stop_reason": "running",
        "cycles": [],
    }
    _write_session_report(vault, start.session, context=start.context)
    if expected_min_cycle_count == 0:
        start.session["maintenance"]["status"] = "complete"
        start.session["maintenance"]["completed_at"] = start.context.isoformat_z()
        start.session["maintenance"]["stop_reason"] = "time_budget_already_reached"
        _write_session_report(vault, start.session, context=start.context)
        return

    while True:
        cycle_started_elapsed_seconds = int(time.monotonic() - state.start_monotonic)
        _record_maintenance_cycle(
            vault,
            start,
            state,
            index=_maintenance_cycle_count(start.session) + 1,
            cycle_started_elapsed_seconds=cycle_started_elapsed_seconds,
        )
        elapsed_seconds = int(time.monotonic() - state.start_monotonic)
        maintenance = _mapping_value(start.session, "maintenance")
        stable_count = _int_value(maintenance.get("stable_queue_snapshot_count"))
        stable_snapshot = _list_text(maintenance.get("stable_queue_snapshot"))
        if (
            stable_snapshot
            and stable_count >= STABLE_MAINTENANCE_QUEUE_THRESHOLD
        ):
            completion_condition = "stable_queue_snapshot"
            break
        if max_cycles is not None and _maintenance_cycle_count(start.session) >= max_cycles:
            break
        if elapsed_seconds >= target_elapsed_seconds:
            break
        time.sleep(min(interval_seconds, target_elapsed_seconds - elapsed_seconds))

    maintenance = dict(_mapping_value(start.session, "maintenance"))
    maintenance["status"] = "complete"
    maintenance["completed_at"] = start.context.isoformat_z()
    maintenance["completion_condition"] = completion_condition
    if completion_condition == "stable_queue_snapshot":
        maintenance["stop_reason"] = "stable_queue_snapshot"
    elif max_cycles is not None:
        maintenance["stop_reason"] = "post_promote_cycle_limit_reached"
    else:
        maintenance["stop_reason"] = "time_budget_reached"
    maintenance["last_cycle_elapsed_seconds"] = int(time.monotonic() - state.start_monotonic)
    start.session["maintenance"] = maintenance
    if maintenance["stop_reason"] == "time_budget_reached":
        state.stop_reason = "time_budget_exhausted"
    _write_session_report(vault, start.session, context=start.context)


def _maybe_run_proposal_budget_maintenance(
    vault: Path,
    request: AutoImproveSessionRequest,
    start: AutoImproveSessionStart,
    state: AutoImproveLoopState,
    *,
    new_iteration_count: int,
) -> None:
    post_promote_cycles = _resolve_post_promote_maintenance_cycles(
        request.post_promote_maintenance_cycles
    )
    if not request.maintain_until_budget and post_promote_cycles == 0:
        return
    if (
        not request.maintain_until_budget
        and request.post_promote_maintenance_cycles is None
        and new_iteration_count <= 0
    ):
        return
    if state.stop_reason != "proposal_budget_exhausted":
        return
    if _last_iteration_outcome(start.session) != "promoted":
        return
    if int(time.monotonic() - state.start_monotonic) >= start.session["budget"]["max_minutes"] * 60:
        state.stop_reason = "time_budget_exhausted"
        return
    _run_proposal_budget_maintenance(
        vault,
        start,
        state,
        interval_seconds=_resolve_maintenance_interval(request.maintenance_interval_seconds),
        max_cycles=None if request.maintain_until_budget else post_promote_cycles,
    )


def run_auto_improve_session(
    vault: AutoImproveSessionRequest | Path | None = None,
    **legacy_kwargs: Any,
) -> dict:
    request = _coerce_auto_improve_session_request(vault, legacy_kwargs)
    start = _start_auto_improve_session(request)
    loop_state = _initial_auto_improve_loop_state(start.auto_policy, start.session)
    initial_stop_reason = _stop_reason_before_iteration(
        request.vault,
        start.session,
        loop_state,
        context=start.context,
        check_open_repeat_backlog=False,
    )
    if initial_stop_reason is None:
        loop_state.repeat_backlog_repair_active = (
            _preflight_learning_gate(
                request.vault,
                start,
                allow_learning_uncertain=request.allow_learning_uncertain,
            )
            is True
        )
    else:
        loop_state.stop_reason = initial_stop_reason

    initial_iteration_count = len(start.session["iterations"])
    first_iteration = initial_iteration_count + 1
    for iteration in range(first_iteration, start.session["budget"]["max_proposals"] + 1):
        stop_reason = _stop_reason_before_iteration(
            request.vault,
            start.session,
            loop_state,
            context=start.context,
        )
        if stop_reason is not None:
            loop_state.stop_reason = stop_reason
            break
        if not _run_auto_improve_iteration(request.vault, start, loop_state, iteration):
            break

    loop_state.stop_reason = _stop_reason_after_loop(
        request.vault,
        start.session,
        loop_state,
        context=start.context,
    )
    _maybe_run_proposal_budget_maintenance(
        request.vault,
        request,
        start,
        loop_state,
        new_iteration_count=len(start.session["iterations"]) - initial_iteration_count,
    )
    result = _complete_auto_improve_session(request.vault, start, loop_state)
    append_runtime_event(
        request.vault,
        context=start.context,
        component="auto_improve_session",
        phase="complete",
        decision=str(result.get("stop_reason", "")).strip(),
        artifact_path=str(result.get("session_report", "")).strip(),
        duration_ms=int(round((time.monotonic() - loop_state.start_monotonic) * 1000)),
        session_id=start.session_id,
        policy_version=start.policy.get("version"),
    )
    return result
