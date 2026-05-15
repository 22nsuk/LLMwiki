from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.experiment_telemetry_runtime import run_rel
from ops.scripts.promotion_decision_registry_runtime import (
    PromotionDecisionRegistryError,
    decision_is_terminal,
    decision_from_payload,
    decision_outcome,
)


TERMINAL_SUCCESS_OUTCOMES = frozenset({"promoted", "discarded"})


@dataclass(frozen=True)
class ExecutionOutcome:
    outcome: str
    next_consecutive_failures: int
    result: dict | None = None
    quarantine_proposal: bool = False

    @property
    def is_terminal_success(self) -> bool:
        return self.outcome in TERMINAL_SUCCESS_OUTCOMES

    @property
    def iteration_status(self) -> str:
        return "complete" if self.is_terminal_success else "blocked"

    @property
    def decision(self) -> str:
        if not isinstance(self.result, dict):
            return ""
        try:
            return decision_from_payload(self.result, require_record=False)
        except PromotionDecisionRegistryError:
            return str(self.result.get("decision", ""))

    def iteration_record(self, *, index: int, proposal_id: str, run_id: str) -> dict:
        return {
            "index": index,
            "proposal_id": proposal_id,
            "run_id": run_id,
            "status": self.iteration_status,
            "outcome": self.outcome,
            "decision": self.decision,
        }


def role_report_path(run_id: str, role: str) -> str:
    return run_rel(run_id, f"{role}-executor-report.json")


def detect_executor_failure(run_id: str, roles: list[str], artifact_root: Path) -> str:
    for role in roles:
        report_path = artifact_root / role_report_path(run_id, role)
        if not report_path.exists():
            continue
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("status") == "pass":
            continue
        if role == "reviewer":
            return "review_blocked"
        if role == "validator" or role.endswith("auditor"):
            return "validation_blocked"
        return "mutation_failed"
    return "mutation_failed"


def evaluate_scope_blocked(consecutive_failures: int) -> ExecutionOutcome:
    return ExecutionOutcome(
        outcome="scope_blocked",
        next_consecutive_failures=consecutive_failures + 1,
        quarantine_proposal=True,
    )


def evaluate_experiment_result(result: dict, consecutive_failures: int) -> ExecutionOutcome:
    try:
        decision = decision_from_payload(result, require_record=False)
    except PromotionDecisionRegistryError:
        decision = str(result.get("decision", ""))
    try:
        outcome = decision_outcome(decision)
        is_terminal = decision_is_terminal(decision)
    except PromotionDecisionRegistryError:
        outcome = ""
        is_terminal = False
    if is_terminal:
        return ExecutionOutcome(
            outcome=outcome,
            next_consecutive_failures=0,
            result=result,
        )
    if outcome:
        return ExecutionOutcome(
            outcome=outcome,
            next_consecutive_failures=consecutive_failures + 1,
            result=result,
        )
    repo_health = result.get("repo_health", {})
    if isinstance(repo_health, dict) and not bool(repo_health.get("passed", True)):
        return ExecutionOutcome(
            outcome="repo_health_blocked",
            next_consecutive_failures=consecutive_failures + 1,
            result=result,
            quarantine_proposal=True,
        )
    return ExecutionOutcome(
        outcome="hold",
        next_consecutive_failures=consecutive_failures + 1,
        result=result,
    )


def evaluate_mutation_error(
    *,
    run_id: str,
    roles: list[str],
    artifact_root: Path,
    pre_promotion_failure_outcomes: set[str] | frozenset[str],
    consecutive_failures: int,
) -> ExecutionOutcome:
    outcome = detect_executor_failure(run_id, roles, artifact_root)
    return ExecutionOutcome(
        outcome=outcome,
        next_consecutive_failures=consecutive_failures + 1,
        quarantine_proposal=outcome in pre_promotion_failure_outcomes,
    )


def evaluate_experiment_error(consecutive_failures: int) -> ExecutionOutcome:
    return ExecutionOutcome(
        outcome="repo_health_blocked",
        next_consecutive_failures=consecutive_failures + 1,
        quarantine_proposal=True,
    )


def apply_execution_outcome(
    session: dict,
    *,
    proposal_id: str,
    quarantined: set[str],
    outcome: ExecutionOutcome,
) -> int:
    if outcome.quarantine_proposal:
        quarantined.add(proposal_id)
        session["quarantined_proposal_ids"] = sorted(quarantined)
    return outcome.next_consecutive_failures
