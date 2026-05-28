from __future__ import annotations

import hashlib
import re
from typing import Any

from ops.scripts.experiment_telemetry_runtime import run_rel
from ops.scripts.mechanism.failure_taxonomy_runtime import (
    blocking_role_for_failure_taxonomy,
    failure_taxonomy_from_outcome,
    is_actionable_repair_failure_taxonomy,
    is_retryable_failure_taxonomy,
)
from ops.scripts.runtime_context import RuntimeContext

NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE = "next_run_failure_repair"
NEXT_RUN_FAILURE_REPAIR_SOURCE_CANDIDATE_TYPE = "auto_improve_next_run_decision_candidate"
NEXT_RUN_FAILURE_REPAIR_FAMILY = "next_run_failure_repair"

CARRY_FORWARD_DECISION = "carry_forward"
CHOOSE_ALTERNATIVE_DECISION = "choose_alternative"
IGNORE_RETRYABLE_DECISION = "ignore_retryable"

REPAIR_FAILURE_ACTION = "repair_failure"
SELECT_ALTERNATIVE_ACTION = "select_alternative_proposal"
WAIT_FOR_CAPACITY_ACTION = "wait_for_executor_capacity"

OPEN_DECISION_STATUS = "open"
CLOSED_DECISION_STATUS = "closed"

def _list_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _positive_int(value: object, default: int = 1) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        resolved = value
    elif isinstance(value, str):
        try:
            resolved = int(value)
        except ValueError:
            return default
    else:
        return default
    return max(1, resolved)


def _proposal_tier(value: object) -> str:
    tier = str(value or "").strip()
    return tier if tier in {"core", "supporting"} else "supporting"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unknown"


def _target_slug(primary_targets: list[str]) -> str:
    stems = [target.rsplit("/", 1)[-1].rsplit(".", 1)[0] for target in primary_targets]
    return _slug("-".join(stems))


def next_run_failure_repair_proposal_id(
    primary_targets: list[str],
    failure_taxonomy: str,
) -> str:
    return (
        f"{NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE}__"
        f"{_target_slug(primary_targets)}__{_slug(failure_taxonomy)}"
    )


def _decision_id(
    *,
    session_id: str,
    run_id: str,
    proposal_id: str,
    failure_taxonomy: str,
) -> str:
    raw = "|".join([session_id, run_id, proposal_id, failure_taxonomy])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"next-run-decision:{_slug(run_id)}:{digest}"


def _decision_shape(
    *,
    failure_taxonomy: str,
    primary_targets: list[str],
) -> tuple[str, str, str, str]:
    if is_retryable_failure_taxonomy(failure_taxonomy):
        return (
            IGNORE_RETRYABLE_DECISION,
            WAIT_FOR_CAPACITY_ACTION,
            CLOSED_DECISION_STATUS,
            "Failure is executor capacity related, so it should not become a repair proposal.",
        )
    if not primary_targets:
        return (
            CHOOSE_ALTERNATIVE_DECISION,
            SELECT_ALTERNATIVE_ACTION,
            CLOSED_DECISION_STATUS,
            "Failure has no bounded primary target, so the next run should select other queued work.",
        )
    if is_actionable_repair_failure_taxonomy(failure_taxonomy):
        return (
            CARRY_FORWARD_DECISION,
            REPAIR_FAILURE_ACTION,
            OPEN_DECISION_STATUS,
            "Failure is actionable and target-bounded, so it should become the next repair candidate.",
        )
    return (
        CHOOSE_ALTERNATIVE_DECISION,
        SELECT_ALTERNATIVE_ACTION,
        CLOSED_DECISION_STATUS,
        "Failure taxonomy is not recognized as actionable next-run repair evidence.",
    )


def build_next_run_decision(
    *,
    session_id: str,
    iteration: int,
    run_id: str,
    proposal: dict[str, Any],
    outcome: object,
    roles: list[str],
    scope_freeze_rel: str,
    routing_report_rels: list[str],
    telemetry_rel: str,
    context: RuntimeContext,
    executor_report_rels: list[str] | None = None,
    blocking_role: str | None = None,
    failure_taxonomy_override: str | None = None,
) -> dict[str, Any] | None:
    failure_taxonomy = failure_taxonomy_from_outcome(outcome, failure_taxonomy_override)
    if not failure_taxonomy or bool(getattr(outcome, "is_terminal_success", False)):
        return None

    primary_targets = _list_strings(proposal.get("primary_targets"))
    supporting_targets = _list_strings(proposal.get("supporting_targets"))
    must_change_tests = _list_strings(proposal.get("must_change_tests"))
    decision, next_run_action, status, reason = _decision_shape(
        failure_taxonomy=failure_taxonomy,
        primary_targets=primary_targets,
    )
    proposal_id = str(proposal.get("proposal_id", "")).strip()
    target_proposal_id = (
        next_run_failure_repair_proposal_id(primary_targets, failure_taxonomy)
        if decision == CARRY_FORWARD_DECISION
        else ""
    )
    executor_reports = (
        _list_strings(executor_report_rels)
        if executor_report_rels is not None
        else [run_rel(run_id, f"{role}-executor-report.json") for role in roles if role]
    )
    evidence_paths = [
        telemetry_rel,
        scope_freeze_rel,
        *routing_report_rels,
        *executor_reports,
    ]
    if getattr(outcome, "result", None):
        evidence_paths.append(run_rel(run_id, "promotion-report.json"))

    return {
        "decision_id": _decision_id(
            session_id=session_id,
            run_id=run_id,
            proposal_id=proposal_id,
            failure_taxonomy=failure_taxonomy,
        ),
        "observed_at": context.isoformat_z(),
        "session_id": session_id,
        "iteration": max(1, int(iteration)),
        "source_run_id": run_id,
        "proposal_id": proposal_id,
        "source_candidate_id": str(proposal.get("source_candidate_id", "")).strip(),
        "target_proposal_id": target_proposal_id,
        "proposal_family": str(proposal.get("family", "")).strip(),
        "proposal_tier": _proposal_tier(proposal.get("tier")),
        "failure_taxonomy": failure_taxonomy,
        "blocking_role": str(blocking_role or "").strip()
        or blocking_role_for_failure_taxonomy(failure_taxonomy, roles),
        "decision": decision,
        "next_run_action": next_run_action,
        "status": status,
        "reason": reason,
        "quarantined_source_proposal": bool(getattr(outcome, "quarantine_proposal", False)),
        "primary_targets": primary_targets,
        "supporting_targets": supporting_targets,
        "must_change_tests": must_change_tests,
        "evidence_paths": list(dict.fromkeys(path for path in evidence_paths if path)),
    }


def normalize_next_run_decisions(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "decision_id": str(item.get("decision_id", "")).strip(),
                "observed_at": str(item.get("observed_at", "")).strip(),
                "session_id": str(item.get("session_id", "")).strip(),
                "iteration": _positive_int(item.get("iteration", 1)),
                "source_run_id": str(item.get("source_run_id", "")).strip(),
                "proposal_id": str(item.get("proposal_id", "")).strip(),
                "source_candidate_id": str(item.get("source_candidate_id", "")).strip(),
                "target_proposal_id": str(item.get("target_proposal_id", "")).strip(),
                "proposal_family": str(item.get("proposal_family", "")).strip(),
                "proposal_tier": _proposal_tier(item.get("proposal_tier")),
                "failure_taxonomy": str(item.get("failure_taxonomy", "")).strip(),
                "blocking_role": str(item.get("blocking_role", "")).strip(),
                "decision": str(item.get("decision", "")).strip(),
                "next_run_action": str(item.get("next_run_action", "")).strip(),
                "status": str(item.get("status", "")).strip(),
                "reason": str(item.get("reason", "")).strip(),
                "quarantined_source_proposal": bool(item.get("quarantined_source_proposal", False)),
                "primary_targets": _list_strings(item.get("primary_targets")),
                "supporting_targets": _list_strings(item.get("supporting_targets")),
                "must_change_tests": _list_strings(item.get("must_change_tests")),
                "evidence_paths": _list_strings(item.get("evidence_paths")),
            }
        )
    return normalized
