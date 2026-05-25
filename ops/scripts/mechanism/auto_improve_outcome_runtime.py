from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.experiment_telemetry_runtime import run_rel
from ops.scripts.promotion_decision_registry_runtime import (
    PromotionDecisionRegistryError,
    decision_from_payload,
    decision_is_terminal,
    decision_outcome,
)

TERMINAL_SUCCESS_OUTCOMES = frozenset({"promoted"})
RETRYABLE_EXECUTOR_FAILURE_OUTCOMES = frozenset({"executor_usage_limited"})
_USAGE_LIMIT_NOTE_MARKERS = (
    "executor_usage_limited",
    "codex exec blocked by usage limit",
)
_USAGE_LIMIT_STDERR_RE = re.compile(
    r"^\s*(?:ERROR:\s*)?(?:you(?:'ve| have) hit your usage limit|"
    r"usage limit\b|upgrade to pro\b|try again at\b).*$",
    flags=re.IGNORECASE | re.MULTILINE,
)


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


def _read_report_artifact_text(report: dict, artifact_root: Path, key: str) -> str:
    artifacts = report.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return ""
    rel_path = str(artifacts.get(key, "")).strip()
    if not rel_path:
        return ""
    artifact_path = Path(rel_path)
    if artifact_path.is_absolute():
        return ""
    path = artifact_root / artifact_path
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _executor_report_has_usage_limit(report: dict, artifact_root: Path) -> bool:
    diagnostics = report.get("diagnostics", {})
    if isinstance(diagnostics, dict):
        notes = diagnostics.get("notes", [])
        if isinstance(notes, list):
            combined_notes = "\n".join(str(item) for item in notes).lower()
            if any(marker in combined_notes for marker in _USAGE_LIMIT_NOTE_MARKERS):
                return True
    result = report.get("result")
    if not isinstance(result, dict) or result.get("returncode") in (0, "0"):
        return False
    stderr = _read_report_artifact_text(report, artifact_root, "stderr")
    return bool(_USAGE_LIMIT_STDERR_RE.search(stderr))


def detect_executor_failure(run_id: str, roles: list[str], artifact_root: Path) -> str:
    for role in roles:
        report_path = artifact_root / role_report_path(run_id, role)
        if not report_path.exists():
            continue
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("status") == "pass":
            continue
        if _executor_report_has_usage_limit(report, artifact_root):
            return "executor_usage_limited"
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
            next_consecutive_failures=(
                0 if outcome in TERMINAL_SUCCESS_OUTCOMES else consecutive_failures + 1
            ),
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
    next_consecutive_failures = consecutive_failures
    if outcome not in RETRYABLE_EXECUTOR_FAILURE_OUTCOMES:
        next_consecutive_failures += 1
    return ExecutionOutcome(
        outcome=outcome,
        next_consecutive_failures=next_consecutive_failures,
        quarantine_proposal=(
            outcome not in RETRYABLE_EXECUTOR_FAILURE_OUTCOMES
            and outcome in pre_promotion_failure_outcomes
        ),
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
