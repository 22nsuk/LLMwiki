from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext


DEFAULT_OUT = "tmp/goal-runtime-run-admission.json"
DEFAULT_CLEANUP_REPORT = "tmp/goal-runtime-clean-transient.json"
DEFAULT_QUARANTINE_PREFLIGHT_REPORT = "tmp/goal-runtime-quarantine-preflight.json"
DEFAULT_FIXED_POINT_REPORT = "tmp/goal-runtime-fixed-point-check.json"
DEFAULT_GOAL_WORKTREE_GUARD_REPORT = "ops/reports/goal-worktree-guard.json"
DEFAULT_MUTATION_PROPOSALS_REPORT = "ops/reports/mutation-proposals.json"
DEFAULT_READINESS_REPORT = "ops/reports/auto-improve-readiness.json"
DEFAULT_REMEDIATION_BACKLOG_REPORT = "ops/reports/remediation-backlog.json"
DEFAULT_GOAL_CONTRACT_REPORT = "ops/reports/codex-goal-contract.json"
DEFAULT_GOAL_RUN_STATUS_REPORT = "ops/reports/goal-run-status.json"
DEFAULT_RUNTIME_CERTIFICATE_REPORT = "ops/reports/goal-runtime-certificate.json"
PRODUCER = "ops.scripts.goal_runtime_run_admission"
SCHEMA_PATH = "ops/schemas/goal-runtime-run-admission.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.goal_runtime_run_admission --vault ."
START_BLOCKER_SEVERITY = "block_start"
PROMOTION_BLOCKER_SEVERITY = "block_promotion"


@dataclass(frozen=True)
class GoalRuntimeRunAdmissionRequest:
    vault: Path
    out_path: str | None = None
    policy_path: str | None = None
    cleanup_report_path: str = DEFAULT_CLEANUP_REPORT
    quarantine_preflight_report_path: str = DEFAULT_QUARANTINE_PREFLIGHT_REPORT
    fixed_point_report_path: str = DEFAULT_FIXED_POINT_REPORT
    goal_worktree_guard_report_path: str = DEFAULT_GOAL_WORKTREE_GUARD_REPORT
    mutation_proposals_report_path: str = DEFAULT_MUTATION_PROPOSALS_REPORT
    readiness_report_path: str = DEFAULT_READINESS_REPORT
    remediation_backlog_report_path: str = DEFAULT_REMEDIATION_BACKLOG_REPORT
    goal_contract_path: str = DEFAULT_GOAL_CONTRACT_REPORT
    goal_run_status_path: str = DEFAULT_GOAL_RUN_STATUS_REPORT
    runtime_certificate_report_path: str = DEFAULT_RUNTIME_CERTIFICATE_REPORT
    context: RuntimeContext | None = None


def _load_json_object(vault: Path, rel_path: str) -> dict[str, Any]:
    try:
        payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_bool(value: object) -> bool:
    return value is True


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _list_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dict_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _list_field(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _canonical_json_digest(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _blocker_ids(value: object, key: str = "id") -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for item in value:
        if isinstance(item, dict):
            blocker_id = str(item.get(key, "")).strip()
            if blocker_id:
                ids.append(blocker_id)
        elif str(item).strip():
            ids.append(str(item).strip())
    return list(dict.fromkeys(ids))


def _check(
    *,
    check_id: str,
    status: str,
    severity: str,
    expected: object,
    observed: object,
    reason: str,
    next_action: str,
    evidence_paths: list[str],
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status,
        "severity": severity,
        "expected": expected,
        "observed": observed,
        "reason": reason,
        "next_action": next_action,
        "evidence_paths": list(dict.fromkeys(path for path in evidence_paths if path)),
    }


def _artifact_kind_check(payload: dict[str, Any], expected_kind: str) -> str:
    artifact_kind = str(payload.get("artifact_kind", "")).strip()
    if not payload:
        return "missing"
    if artifact_kind and artifact_kind != expected_kind:
        return "invalid"
    return "present"


def _cleanup_check(cleanup: dict[str, Any], path: str) -> dict[str, Any]:
    kind_status = _artifact_kind_check(cleanup, "goal_runtime_clean_transient")
    summary = _dict_field(cleanup, "summary")
    failed_count = _as_int(summary.get("failed_count"))
    would_remove_count = _as_int(summary.get("would_remove_count"))
    apply_enabled = _as_bool(summary.get("apply"))
    cleanup_status = str(cleanup.get("status", "missing")).strip() or "missing"
    passed = (
        kind_status == "present"
        and cleanup_status == "pass"
        and failed_count == 0
        and would_remove_count == 0
        and apply_enabled
    )
    return _check(
        check_id="start_transient_cleanup_applied",
        status="pass" if passed else "fail",
        severity=START_BLOCKER_SEVERITY,
        expected={
            "artifact_kind": "goal_runtime_clean_transient",
            "status": "pass",
            "failed_count": 0,
            "would_remove_count": 0,
            "apply": True,
        },
        observed={
            "artifact_status": kind_status,
            "status": cleanup_status,
            "failed_count": failed_count,
            "would_remove_count": would_remove_count,
            "apply": apply_enabled,
        },
        reason=(
            "transient cleanup is applied and no removable residue remains"
            if passed
            else "run admission requires transient cleanup to be applied, not only planned, before a new goal run starts"
        ),
        next_action=(
            "Proceed with run admission."
            if passed
            else "Run `make goal-runtime-clean-transient` with cleanup apply enabled, then rerun admission."
        ),
        evidence_paths=[path],
    )


def _quarantine_preflight_check(quarantine_preflight: dict[str, Any], path: str) -> dict[str, Any]:
    kind_status = _artifact_kind_check(quarantine_preflight, "goal_runtime_quarantine_preflight")
    status = str(quarantine_preflight.get("status", "missing")).strip() or "missing"
    summary = _dict_field(quarantine_preflight, "summary")
    operator_decision_required_count = _as_int(summary.get("operator_decision_required_count"))
    invalid_exclusion_count = _as_int(summary.get("invalid_exclusion_count"))
    passed = (
        kind_status == "present"
        and status == "pass"
        and operator_decision_required_count == 0
        and invalid_exclusion_count == 0
    )
    return _check(
        check_id="start_history_quarantine_preflight_clear",
        status="pass" if passed else "fail",
        severity=START_BLOCKER_SEVERITY,
        expected={
            "artifact_kind": "goal_runtime_quarantine_preflight",
            "status": "pass",
            "operator_decision_required_count": 0,
            "invalid_exclusion_count": 0,
        },
        observed={
            "artifact_status": kind_status,
            "status": status,
            "operator_decision_required_count": operator_decision_required_count,
            "invalid_exclusion_count": invalid_exclusion_count,
            "excluded_run_count": _as_int(summary.get("excluded_run_count")),
            "quarantined_run_count": _as_int(summary.get("quarantined_run_count")),
        },
        reason=(
            "quarantine preflight found no unresolved active-history cleanup"
            if passed
            else "new runs must not start while active mechanism history still needs archive/quarantine cleanup"
        ),
        next_action=(
            "Proceed with run admission."
            if passed
            else "Run `make goal-runtime-quarantine-preflight` and resolve its `recommended_next_action`."
        ),
        evidence_paths=[path],
    )


def _fixed_point_check(fixed_point: dict[str, Any], path: str) -> dict[str, Any]:
    kind_status = _artifact_kind_check(fixed_point, "goal_runtime_fixed_point_check")
    status = str(fixed_point.get("status", "missing")).strip() or "missing"
    failed_count = _as_int(_dict_field(fixed_point, "summary").get("failed_check_count"))
    passed = kind_status == "present" and status == "pass" and failed_count == 0
    return _check(
        check_id="start_fixed_point_current",
        status="pass" if passed else "fail",
        severity=START_BLOCKER_SEVERITY,
        expected={"artifact_kind": "goal_runtime_fixed_point_check", "status": "pass", "failed_check_count": 0},
        observed={"artifact_status": kind_status, "status": status, "failed_check_count": failed_count},
        reason=(
            "goal runtime evidence is at a fixed point"
            if passed
            else "new runs must not start while goal runtime evidence surfaces are stale or mutually inconsistent"
        ),
        next_action=(
            "Proceed with run admission."
            if passed
            else "Run `make goal-runtime-local-evidence-converge goal-runtime-fixed-point-check` before starting the run."
        ),
        evidence_paths=[path],
    )


def _worktree_check(guard: dict[str, Any], path: str) -> dict[str, Any]:
    kind_status = _artifact_kind_check(guard, "goal_worktree_guard")
    git = _dict_field(guard, "git")
    decisions = _dict_field(guard, "decisions")
    status = str(guard.get("status", "missing")).strip() or "missing"
    dirty_entry_count = _as_int(git.get("dirty_entry_count"))
    can_execute = _as_bool(decisions.get("can_execute_goal_runtime"))
    can_promote = _as_bool(decisions.get("can_promote_result"))
    fatal_blockers = _list_strings(decisions.get("fatal_blockers"))
    promotion_blockers = _list_strings(decisions.get("promotion_blockers"))
    passed = (
        kind_status == "present"
        and status == "pass"
        and can_execute
        and can_promote
        and dirty_entry_count == 0
        and not fatal_blockers
        and not promotion_blockers
    )
    return _check(
        check_id="start_worktree_promotable",
        status="pass" if passed else "fail",
        severity=START_BLOCKER_SEVERITY,
        expected={
            "artifact_kind": "goal_worktree_guard",
            "status": "pass",
            "can_execute_goal_runtime": True,
            "can_promote_result": True,
            "dirty_entry_count": 0,
            "fatal_blockers": [],
            "promotion_blockers": [],
        },
        observed={
            "artifact_status": kind_status,
            "status": status,
            "can_execute_goal_runtime": can_execute,
            "can_promote_result": can_promote,
            "dirty_entry_count": dirty_entry_count,
            "fatal_blockers": fatal_blockers,
            "promotion_blockers": promotion_blockers,
        },
        reason=(
            "worktree guard is clean and promotable"
            if passed
            else "new mutation runs start only from a clean Git worktree that can later promote results"
        ),
        next_action=(
            "Proceed with run admission."
            if passed
            else "Commit, discard intentionally, or clean local changes, then rerun `make auto-improve-goal-preflight`."
        ),
        evidence_paths=[path],
    )


def _mutation_queue_check(mutation_proposals: dict[str, Any], path: str) -> dict[str, Any]:
    kind_status = _artifact_kind_check(mutation_proposals, "mutation_proposals_report")
    diagnostics = _dict_field(mutation_proposals, "diagnostics")
    queue_selection = _dict_field(diagnostics, "queue_selection")
    proposals = _list_field(mutation_proposals, "proposals")
    runnable_available_count = _as_int(queue_selection.get("runnable_available_count"))
    selected_runnable_count = _as_int(queue_selection.get("selected_runnable_count"))
    blocked_available_count = _as_int(queue_selection.get("blocked_available_count"))
    blocked_reason_counts = _list_field(queue_selection, "blocked_reason_counts")
    passed = (
        kind_status == "present"
        and runnable_available_count > 0
        and selected_runnable_count > 0
    )
    return _check(
        check_id="start_runnable_proposal_queue",
        status="pass" if passed else "fail",
        severity=START_BLOCKER_SEVERITY,
        expected={"runnable_available_count": ">0", "selected_runnable_count": ">0"},
        observed={
            "artifact_status": kind_status,
            "proposal_count": len(proposals),
            "runnable_available_count": runnable_available_count,
            "selected_runnable_count": selected_runnable_count,
            "blocked_available_count": blocked_available_count,
            "blocked_reason_counts": blocked_reason_counts,
        },
        reason=(
            "mutation proposal queue contains a selected runnable proposal"
            if passed
            else "new runs must not start when every proposal is blocked or the queue has not selected a runnable item"
        ),
        next_action=(
            "Proceed with run admission."
            if passed
            else "Refresh `make refresh-generated-core`; if only recent_log_overlap remains, wait, rotate target, or emit a non-overlapping repair proposal before running."
        ),
        evidence_paths=[path],
    )


def _readiness_execution_check(readiness: dict[str, Any], path: str) -> dict[str, Any]:
    kind_status = _artifact_kind_check(readiness, "auto_improve_readiness_report")
    execution = _dict_field(readiness, "execution_readiness")
    can_run = _as_bool(execution.get("can_run"))
    runnable_count = _as_int(execution.get("runnable_proposal_count"))
    reasons = _list_strings(execution.get("reasons"))
    passed = kind_status == "present" and can_run and runnable_count > 0
    return _check(
        check_id="start_execution_readiness",
        status="pass" if passed else "fail",
        severity=START_BLOCKER_SEVERITY,
        expected={"execution_readiness.can_run": True, "runnable_proposal_count": ">0"},
        observed={
            "artifact_status": kind_status,
            "execution_readiness.can_run": can_run,
            "runnable_proposal_count": runnable_count,
            "reasons": reasons,
        },
        reason=(
            "auto-improve readiness permits execution"
            if passed
            else "readiness still says execution is not runnable after pre-run convergence"
        ),
        next_action=(
            "Proceed with run admission."
            if passed
            else "Resolve readiness execution blockers before starting `make auto-improve-goal-run`."
        ),
        evidence_paths=[path],
    )


def _readiness_promotion_check(readiness: dict[str, Any], path: str) -> dict[str, Any]:
    kind_status = _artifact_kind_check(readiness, "auto_improve_readiness_report")
    can_promote = _as_bool(readiness.get("can_promote_result"))
    promotion_blockers = _blocker_ids(readiness.get("promotion_blockers"))
    passed = kind_status == "present" and can_promote and not promotion_blockers
    return _check(
        check_id="promotion_readiness_clear",
        status="pass" if passed else "attention",
        severity=PROMOTION_BLOCKER_SEVERITY,
        expected={"can_promote_result": True, "promotion_blockers": []},
        observed={
            "artifact_status": kind_status,
            "can_promote_result": can_promote,
            "promotion_blockers": promotion_blockers,
        },
        reason=(
            "readiness already permits promotion"
            if passed
            else "promotion is still blocked; admission may start only if start checks pass, but final promotion remains gated"
        ),
        next_action=(
            "Proceed with run admission."
            if passed
            else "Keep promotion blocked until readiness, source package, public, and certificate evidence converge."
        ),
        evidence_paths=[path],
    )


def _remediation_backlog_check(remediation_backlog: dict[str, Any], path: str) -> dict[str, Any]:
    kind_status = _artifact_kind_check(remediation_backlog, "remediation_backlog")
    status = str(remediation_backlog.get("status", "missing")).strip() or "missing"
    summary = _dict_field(remediation_backlog, "summary")
    open_total_count = _as_int(summary.get("open_total_count"))
    open_promotion_count = _as_int(summary.get("open_promotion_count"))
    open_repeat_count = _as_int(summary.get("open_repeat_count"))
    active_blocker_count = _as_int(
        summary.get("active_blocker_count")
    )
    items = _list_field(remediation_backlog, "items")
    open_blockers = [
        str(item.get("blocker_id", "") or item.get("id", "")).strip()
        for item in items
        if isinstance(item, dict) and str(item.get("status", "")).strip() == "open"
    ]
    open_blockers = [item for item in open_blockers if item]
    passed = kind_status == "present" and open_promotion_count == 0
    return _check(
        check_id="promotion_remediation_backlog_clear",
        status="pass" if passed else "attention",
        severity=PROMOTION_BLOCKER_SEVERITY,
        expected={"open_promotion_count": 0},
        observed={
            "artifact_status": kind_status,
            "status": status,
            "open_total_count": open_total_count,
            "open_promotion_count": open_promotion_count,
            "open_repeat_count": open_repeat_count,
            "active_blocker_count": active_blocker_count,
            "open_blockers": list(dict.fromkeys(open_blockers)),
        },
        reason=(
            "remediation backlog is clear"
            if passed
            else "remediation backlog remains open, so this run cannot be treated as promotable until it is closed or explicitly deferred"
        ),
        next_action=(
            "Proceed with run admission."
            if passed
            else "Close, repair, or explicitly defer promotion-blocking backlog items before promotion."
        ),
        evidence_paths=[path],
    )


def _durable_goal_authority_check(
    *,
    contract: dict[str, Any],
    contract_path: str,
    goal_run_status: dict[str, Any],
    goal_run_status_path: str,
    runtime_certificate: dict[str, Any],
    runtime_certificate_path: str,
) -> dict[str, Any]:
    contract_digest = _canonical_json_digest(contract) if contract else ""
    contract_backend = _dict_field(contract, "goal_backend")
    contract_runtime = _dict_field(contract, "runtime")
    contract_guard = _dict_field(contract, "promotion_guard")
    status_goal = _dict_field(goal_run_status, "goal")
    status_backend = _dict_field(status_goal, "backend")
    status_currentness = _dict_field(goal_run_status, "currentness")
    certificate_goal = _dict_field(runtime_certificate, "goal")
    certificate_run = _dict_field(runtime_certificate, "run")
    certificate_currentness = _dict_field(runtime_certificate, "currentness")
    certificate = _dict_field(runtime_certificate, "certificate")
    contract_update = _dict_field(runtime_certificate, "contract_update")
    blockers = _blocker_ids(runtime_certificate.get("blockers"), key="blocker_id")
    if not blockers:
        blockers = _blocker_ids(runtime_certificate.get("blockers"))

    status_contract_sha = str(status_goal.get("contract_sha256", "")).strip()
    certificate_contract_sha = str(certificate_goal.get("contract_sha256_after", "")).strip()
    checks = {
        "contract_present": bool(contract),
        "contract_backend_process_persistent": _as_bool(contract_backend.get("process_persistent")),
        "contract_runtime_certificate_verified": str(
            contract_runtime.get("certificate_status", "")
        ).strip()
        == "verified",
        "contract_promotion_guard_verified": _as_bool(
            contract_guard.get("runtime_certificate_verified")
        ),
        "goal_status_present": _artifact_kind_check(goal_run_status, "goal_run_status") == "present",
        "goal_status_current": str(status_currentness.get("status", "")).strip() == "current",
        "goal_status_contract_path_matches": str(status_goal.get("contract_path", "")).strip()
        == contract_path,
        "goal_status_contract_digest_matches": bool(contract_digest)
        and status_contract_sha == contract_digest,
        "goal_status_backend_process_persistent": _as_bool(
            status_backend.get("process_persistent")
        ),
        "certificate_present": _artifact_kind_check(
            runtime_certificate,
            "goal_runtime_certificate",
        )
        == "present",
        "certificate_status_pass": str(runtime_certificate.get("status", "")).strip() == "pass",
        "certificate_current": str(certificate_currentness.get("status", "")).strip()
        == "current",
        "certificate_contract_path_matches": str(certificate_goal.get("contract_path", "")).strip()
        == contract_path,
        "certificate_contract_digest_matches": bool(contract_digest)
        and certificate_contract_sha == contract_digest,
        "certificate_status_report_matches": str(
            certificate_run.get("status_report_path", "")
        ).strip()
        == goal_run_status_path,
        "certificate_eligible": str(certificate.get("verification_status", "")).strip()
        in {"eligible", "already_verified"}
        and _as_bool(certificate.get("eligible")),
        "certificate_contract_update_verified": _as_bool(
            contract_update.get("runtime_certificate_verified_after")
        ),
        "certificate_blockers_clear": not blockers,
    }
    passed = all(checks.values())
    return _check(
        check_id="promotion_durable_goal_authority_current",
        status="pass" if passed else "attention",
        severity=PROMOTION_BLOCKER_SEVERITY,
        expected={
            "contract_backend.process_persistent": True,
            "contract.runtime.certificate_status": "verified",
            "contract.promotion_guard.runtime_certificate_verified": True,
            "goal_run_status.goal.contract_path": contract_path,
            "goal_run_status.goal.contract_sha256": contract_digest or "<current contract digest>",
            "goal_run_status.currentness.status": "current",
            "runtime_certificate.goal.contract_path": contract_path,
            "runtime_certificate.goal.contract_sha256_after": contract_digest
            or "<current contract digest>",
            "runtime_certificate.run.status_report_path": goal_run_status_path,
            "runtime_certificate.status": "pass",
            "runtime_certificate.currentness.status": "current",
            "runtime_certificate.blockers": [],
        },
        observed={
            **checks,
            "contract_digest": contract_digest,
            "goal_status_contract_sha256": status_contract_sha,
            "certificate_contract_sha256_after": certificate_contract_sha,
            "certificate_blockers": blockers,
        },
        reason=(
            "file-backed goal contract, run status, and runtime certificate agree on the verified contract digest"
            if passed
            else "native Codex goal state is advisory until file-backed contract, goal-run-status, and runtime certificate evidence agree on a verified digest"
        ),
        next_action=(
            "Proceed with promotion authority checks."
            if passed
            else "Run `make auto-improve-goal-contract auto-improve-goal-status goal-runtime-certificate` with the same GOAL_RUN_ID, then rerun admission before claiming completion or promotion."
        ),
        evidence_paths=[contract_path, goal_run_status_path, runtime_certificate_path],
    )


def _summary(checks: list[dict[str, Any]]) -> dict[str, Any]:
    start_blockers = [
        check
        for check in checks
        if check["severity"] == START_BLOCKER_SEVERITY and check["status"] != "pass"
    ]
    promotion_blockers = [
        check
        for check in checks
        if check["severity"] == PROMOTION_BLOCKER_SEVERITY and check["status"] != "pass"
    ]
    return {
        "check_count": len(checks),
        "start_blocker_count": len(start_blockers),
        "promotion_blocker_count": len(promotion_blockers),
        "attention_check_count": sum(1 for check in checks if check["status"] == "attention"),
        "failed_check_count": sum(1 for check in checks if check["status"] == "fail"),
    }


def _status(decisions: dict[str, bool]) -> str:
    if not decisions["can_start_goal_runtime"]:
        return "fail"
    if not decisions["can_promote_result_later"]:
        return "attention"
    return "pass"


def _recommended_next_action(checks: list[dict[str, Any]], decisions: dict[str, bool]) -> str:
    for check in checks:
        if check["severity"] == START_BLOCKER_SEVERITY and check["status"] != "pass":
            return check["next_action"]
    if not decisions["can_promote_result_later"]:
        return "Start only bounded repair work; keep promotion blocked until promotion checks pass."
    return "Start `make auto-improve-goal-run`."


def build_report(
    request: GoalRuntimeRunAdmissionRequest | Path,
    **legacy_fields: Any,
) -> dict[str, Any]:
    if isinstance(request, GoalRuntimeRunAdmissionRequest):
        if legacy_fields:
            raise TypeError("build_report accepts either a request object or legacy keyword fields")
        active_request = request
    else:
        active_request = GoalRuntimeRunAdmissionRequest(vault=Path(request), **legacy_fields)
    vault = active_request.vault.resolve()
    policy, resolved_policy_path = load_policy(vault, active_request.policy_path)
    context = active_request.context or RuntimeContext.from_policy(policy)
    cleanup = _load_json_object(vault, active_request.cleanup_report_path)
    quarantine_preflight = _load_json_object(vault, active_request.quarantine_preflight_report_path)
    fixed_point = _load_json_object(vault, active_request.fixed_point_report_path)
    guard = _load_json_object(vault, active_request.goal_worktree_guard_report_path)
    mutation_proposals = _load_json_object(vault, active_request.mutation_proposals_report_path)
    readiness = _load_json_object(vault, active_request.readiness_report_path)
    remediation_backlog = _load_json_object(vault, active_request.remediation_backlog_report_path)
    goal_contract = _load_json_object(vault, active_request.goal_contract_path)
    goal_run_status = _load_json_object(vault, active_request.goal_run_status_path)
    runtime_certificate = _load_json_object(
        vault,
        active_request.runtime_certificate_report_path,
    )
    checks = [
        _cleanup_check(cleanup, active_request.cleanup_report_path),
        _quarantine_preflight_check(
            quarantine_preflight,
            active_request.quarantine_preflight_report_path,
        ),
        _fixed_point_check(fixed_point, active_request.fixed_point_report_path),
        _worktree_check(guard, active_request.goal_worktree_guard_report_path),
        _mutation_queue_check(mutation_proposals, active_request.mutation_proposals_report_path),
        _readiness_execution_check(readiness, active_request.readiness_report_path),
        _readiness_promotion_check(readiness, active_request.readiness_report_path),
        _remediation_backlog_check(remediation_backlog, active_request.remediation_backlog_report_path),
        _durable_goal_authority_check(
            contract=goal_contract,
            contract_path=active_request.goal_contract_path,
            goal_run_status=goal_run_status,
            goal_run_status_path=active_request.goal_run_status_path,
            runtime_certificate=runtime_certificate,
            runtime_certificate_path=active_request.runtime_certificate_report_path,
        ),
    ]
    summary = _summary(checks)
    decisions = {
        "can_start_goal_runtime": summary["start_blocker_count"] == 0,
        "can_mutate_candidate": summary["start_blocker_count"] == 0,
        "can_promote_result_later": summary["start_blocker_count"] == 0
        and summary["promotion_blocker_count"] == 0,
        "should_pause_before_run": summary["start_blocker_count"] > 0,
    }
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=context.isoformat_z(),
            artifact_kind="goal_runtime_run_admission",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/mechanism/goal_runtime_run_admission.py",
                "ops/scripts/mechanism/goal_runtime_quarantine_preflight.py",
                "ops/schemas/goal-runtime-run-admission.schema.json",
                "mk/mechanism.mk",
            ],
            file_inputs={
                "cleanup_report": active_request.cleanup_report_path,
                "quarantine_preflight_report": active_request.quarantine_preflight_report_path,
                "fixed_point_report": active_request.fixed_point_report_path,
                "goal_worktree_guard_report": active_request.goal_worktree_guard_report_path,
                "mutation_proposals_report": active_request.mutation_proposals_report_path,
                "readiness_report": active_request.readiness_report_path,
                "remediation_backlog_report": active_request.remediation_backlog_report_path,
                "goal_contract": active_request.goal_contract_path,
                "goal_run_status": active_request.goal_run_status_path,
                "runtime_certificate_report": active_request.runtime_certificate_report_path,
            },
            source_tree_excluded_files=(active_request.out_path or DEFAULT_OUT,),
        ),
        "vault": report_path(vault, vault),
        "status": _status(decisions),
        "decisions": decisions,
        "summary": summary,
        "recommended_next_action": _recommended_next_action(checks, decisions),
        "inputs": {
            "cleanup_report": active_request.cleanup_report_path,
            "quarantine_preflight_report": active_request.quarantine_preflight_report_path,
            "fixed_point_report": active_request.fixed_point_report_path,
            "goal_worktree_guard_report": active_request.goal_worktree_guard_report_path,
            "mutation_proposals_report": active_request.mutation_proposals_report_path,
            "readiness_report": active_request.readiness_report_path,
            "remediation_backlog_report": active_request.remediation_backlog_report_path,
            "goal_contract": active_request.goal_contract_path,
            "goal_run_status": active_request.goal_run_status_path,
            "runtime_certificate_report": active_request.runtime_certificate_report_path,
        },
        "checks": checks,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="goal runtime run admission schema validation failed",
            trailing_newline=True,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gate a new goal-runtime run on pre-run convergence.")
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output report path.")
    parser.add_argument("--cleanup-report", default=DEFAULT_CLEANUP_REPORT)
    parser.add_argument("--quarantine-preflight-report", default=DEFAULT_QUARANTINE_PREFLIGHT_REPORT)
    parser.add_argument("--fixed-point-report", default=DEFAULT_FIXED_POINT_REPORT)
    parser.add_argument("--goal-worktree-guard-report", default=DEFAULT_GOAL_WORKTREE_GUARD_REPORT)
    parser.add_argument("--mutation-proposals-report", default=DEFAULT_MUTATION_PROPOSALS_REPORT)
    parser.add_argument("--readiness-report", default=DEFAULT_READINESS_REPORT)
    parser.add_argument("--remediation-backlog-report", default=DEFAULT_REMEDIATION_BACKLOG_REPORT)
    parser.add_argument("--goal-contract", default=DEFAULT_GOAL_CONTRACT_REPORT)
    parser.add_argument("--goal-run-status", default=DEFAULT_GOAL_RUN_STATUS_REPORT)
    parser.add_argument("--runtime-certificate-report", default=DEFAULT_RUNTIME_CERTIFICATE_REPORT)
    parser.add_argument("--policy-path", default=None)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero when start admission is blocked.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        GoalRuntimeRunAdmissionRequest(
            vault=vault,
            out_path=args.out,
            policy_path=args.policy_path,
            cleanup_report_path=args.cleanup_report,
            quarantine_preflight_report_path=args.quarantine_preflight_report,
            fixed_point_report_path=args.fixed_point_report,
            goal_worktree_guard_report_path=args.goal_worktree_guard_report,
            mutation_proposals_report_path=args.mutation_proposals_report,
            readiness_report_path=args.readiness_report,
            remediation_backlog_report_path=args.remediation_backlog_report,
            goal_contract_path=args.goal_contract,
            goal_run_status_path=args.goal_run_status,
            runtime_certificate_report_path=args.runtime_certificate_report,
        )
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    if args.strict and not report["decisions"]["can_start_goal_runtime"]:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
