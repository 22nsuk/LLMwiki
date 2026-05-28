from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.experiment_telemetry_runtime import run_rel, write_run_telemetry
from ops.scripts.promotion_decision_registry_runtime import (
    PromotionDecisionRegistryError,
    decision_record_from_payload,
    decision_record_from_report,
)
from ops.scripts.runtime_context import RuntimeContext

from .auto_improve_execute_runtime import ExecuteEvaluatePhaseResult
from .auto_improve_iteration_telemetry_runtime import (
    iteration_behavior_delta_digest,
    iteration_same_eval_contract,
    iteration_same_eval_reason,
)
from .failure_taxonomy_runtime import failure_taxonomy_from_iteration
from .auto_improve_next_run_decision_runtime import build_next_run_decision
from .auto_improve_outcome_runtime import role_report_path
from .auto_improve_route_scaffold_runtime import RouteScaffoldPhaseResult
from .auto_improve_session_runtime import load_optional_json

ITERATION_TELEMETRY_WRITTEN_FIELDS = frozenset(
    {
        "session_id",
        "run_id",
        "generated_at",
        "observed_at",
        "proposal_id",
        "source_candidate_id",
        "proposal_snapshot",
        "scope_freeze",
        "routing_reports",
        "executor_reports",
        "phase_durations",
        "failure_taxonomy",
        "decision",
        "finalized",
        "finalize_result",
    }
)

ITERATION_TELEMETRY_MERGED_FIELDS = frozenset(
    {
        "decision_record",
        "discard_non_regression_evidence",
        "command_timeouts",
        "timeout_failure_artifacts",
        "pre_promotion_failure_artifacts",
        "behavior_delta",
        "behavior_delta_digest",
        "same_eval_reason",
        "same_eval_reason_code",
        "strict_secondary_improvement_present",
        "secondary_improvement_axes",
    }
)

# Run-telemetry fields produced earlier in the run that later iteration writes
# should preserve unless an explicit overwrite or merge rule applies.
PRESERVED_RUN_TELEMETRY_FIELDS = frozenset(
    {
        "metadata",
        "primary_targets", "supporting_targets", "test_files",
        "workspace_preparation", "structural_complexity_budget", "apply_mode", "apply_status",
        "live_applied", "shadow_apply_report", "rollback_rehearsal_report",
        "post_mutation_generated_artifact_convergence",
    }
)
PRE_PROMOTION_FAILURE_ARTIFACT_OUTCOMES = frozenset(
    {"mutation_failed", "repo_health_blocked"}
)
PRE_PROMOTION_FAILURE_LOG_NAMES = (
    "mutation-command.stdout.txt",
    "mutation-command.stderr.txt",
    "repo-health.stdout.txt",
    "repo-health.stderr.txt",
    "repo-health-artifact-freshness-report-check.json",
    "structural-complexity-budget.json",
)
DISCARD_NON_REGRESSION_CHECK_IDS = (
    "candidate_eval_pass",
    "eval_score_improves",
    "lint_non_regression",
    "structural_complexity_non_regression",
    "tests_non_regression",
)
PROMOTION_CHECK_STATUS_VALUES = frozenset({"PASS", "WARN", "FAIL"})
@dataclass(frozen=True)
class PersistIterationPhaseResult:
    consecutive_failures: int
    telemetry_rel: str


@dataclass(frozen=True)
class PersistIterationDependencies:
    apply_execution_outcome: Callable[..., int]
    write_iteration_telemetry: Callable[..., str]
    write_run_artifact_fingerprint: Callable[..., str]
    write_session_report: Callable[..., Path]


@dataclass(frozen=True)
class IterationTelemetryRequest:
    vault: Path
    run_id: str
    session_id: str
    proposal: dict
    scope_freeze_rel: str
    routing_report_rels: list[str]
    roles: list[str]
    phase_durations: dict[str, float]
    outcome: str
    result: dict | None
    context: RuntimeContext


@dataclass(frozen=True)
class LoadedPromotionReport:
    payload: dict[str, Any]
    source_kind: str
    source_path: str


def _normalize_timeout_result(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    if not any(key in value for key in ("timed_out", "timeout_seconds", "termination_reason")):
        return None
    timeout_seconds = value.get("timeout_seconds", 0)
    if not isinstance(timeout_seconds, int):
        timeout_seconds = 0
    return {
        "timed_out": bool(value.get("timed_out", False)),
        "timeout_seconds": timeout_seconds,
        "termination_reason": str(value.get("termination_reason", "")),
        "launch_succeeded": bool(value.get("launch_succeeded", True)),
        "signal_sent": str(value.get("signal_sent", "none")),
        "final_state_observed": str(value.get("final_state_observed", "")),
        "stdout_received": bool(value.get("stdout_received", False)),
        "stderr_received": bool(value.get("stderr_received", False)),
    }


def _iteration_command_timeouts(vault: Path, run_id: str, result: dict | None) -> dict | None:
    existing_report = load_optional_json(vault / run_rel(run_id, "run-telemetry.json"))
    merged: dict[str, dict] = {}
    timeout_sources = []
    if isinstance(existing_report, dict):
        timeout_sources.append(existing_report.get("command_timeouts", {}))
    if isinstance(result, dict):
        timeout_sources.extend((result.get("command_timeouts", {}), result))
    for source in timeout_sources:
        if not isinstance(source, dict):
            continue
        for key in ("mutation_command", "repo_health"):
            normalized = _normalize_timeout_result(source.get(key))
            if normalized is not None:
                merged[key] = normalized
    return merged or None


def _iteration_timeout_failure_artifacts(vault: Path, run_id: str, result: dict | None) -> list[str]:
    artifacts: set[str] = set()
    existing_report = load_optional_json(vault / run_rel(run_id, "run-telemetry.json"))
    artifact_sources = (
        existing_report.get("timeout_failure_artifacts", []) if isinstance(existing_report, dict) else [],
        result.get("timeout_failure_artifacts", []) if isinstance(result, dict) else [],
    )
    artifacts.update(
        str(item)
        for source in artifact_sources
        if isinstance(source, list)
        for item in source
        if str(item).strip()
    )
    run_dir = vault / run_rel(run_id, "")
    if run_dir.exists():
        artifacts.update(
            run_rel(run_id, path.name)
            for path in run_dir.glob("*-timeout-failure.json")
            if path.is_file()
        )
    return sorted(artifacts)


def _iteration_pre_promotion_failure_artifacts(
    vault: Path,
    run_id: str,
    outcome: str,
) -> list[str]:
    if outcome not in PRE_PROMOTION_FAILURE_ARTIFACT_OUTCOMES:
        return []
    run_dir = vault / run_rel(run_id, "")
    if not run_dir.is_dir():
        return []
    return [
        run_rel(run_id, log_name)
        for log_name in PRE_PROMOTION_FAILURE_LOG_NAMES
        if (run_dir / log_name).is_file()
    ]


def _iteration_behavior_delta(vault: Path, run_id: str, result: dict | None) -> str:
    if isinstance(result, dict):
        behavior_delta = result.get("behavior_delta")
        if isinstance(behavior_delta, str) and behavior_delta.strip():
            return behavior_delta
    existing_report = load_optional_json(vault / run_rel(run_id, "run-telemetry.json"))
    if isinstance(existing_report, dict):
        behavior_delta = existing_report.get("behavior_delta")
        if isinstance(behavior_delta, str) and behavior_delta.strip():
            return behavior_delta
    rel_path = run_rel(run_id, "behavior-delta.json")
    if (vault / rel_path).is_file():
        return rel_path
    return ""


def _load_repo_relative_json(vault: Path, rel_path: object) -> dict | None:
    if not isinstance(rel_path, str) or not rel_path.strip():
        return None
    path = Path(rel_path)
    if path.is_absolute():
        return None
    vault_root = vault.resolve()
    resolved_path = (vault_root / path).resolve()
    if not resolved_path.is_relative_to(vault_root):
        return None
    payload = load_optional_json(resolved_path)
    return payload if isinstance(payload, dict) else None


def _normalized_repo_relative_path(rel_path: object) -> str:
    if not isinstance(rel_path, str) or not rel_path.strip():
        return ""
    normalized = rel_path.strip().replace("\\", "/")
    if normalized.startswith("/") or Path(normalized).is_absolute():
        return ""
    parts = normalized.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return ""
    return "/".join(parts)


def _promotion_report_path_matches_run(rel_path: object, run_id: str) -> bool:
    if not isinstance(rel_path, str) or not rel_path.strip():
        return True
    normalized = _normalized_repo_relative_path(rel_path)
    if not normalized:
        return False
    return normalized == run_rel(run_id, "promotion-report.json") or normalized.startswith(
        run_rel(run_id, "")
    )


def _decision_record_matches_run(decision_record: object, run_id: str) -> bool:
    if not isinstance(decision_record, dict):
        return True
    subject_id = str(decision_record.get("subject_id", "")).strip()
    return not subject_id or subject_id == run_id


def _promotion_report_matches_run(promotion_report: dict[str, Any], run_id: str) -> bool:
    report_run_id = str(promotion_report.get("run_id", "")).strip()
    if report_run_id and report_run_id != run_id:
        return False
    return _decision_record_matches_run(promotion_report.get("decision_record"), run_id)


def _iteration_executor_report_rels(vault: Path, run_id: str, roles: list[str]) -> list[str]:
    report_rels: list[str] = []
    for role in roles:
        rel_path = role_report_path(run_id, role)
        if _load_repo_relative_json(vault, rel_path) is not None:
            report_rels.append(rel_path)
    return report_rels


def _role_from_executor_report_rel(rel_path: str) -> str:
    filename = rel_path.rsplit("/", 1)[-1]
    suffix = "-executor-report.json"
    if filename.endswith(suffix):
        return filename[: -len(suffix)]
    return ""


def _blocking_role_from_executor_reports(vault: Path, report_rels: list[str]) -> str:
    for rel_path in report_rels:
        payload = _load_repo_relative_json(vault, rel_path)
        if payload is None:
            continue
        status = str(payload.get("status", "")).strip().lower()
        if status and status != "pass":
            return str(payload.get("role", "")).strip() or _role_from_executor_report_rel(rel_path)
    return ""


def _load_promotion_report_from_rel(
    vault: Path,
    rel_path: object,
    *,
    run_id: str,
    source_kind: str,
) -> LoadedPromotionReport | None:
    if not _promotion_report_path_matches_run(rel_path, run_id):
        return None
    payload = _load_repo_relative_json(vault, rel_path)
    if payload is None:
        return None
    if not _promotion_report_matches_run(payload, run_id):
        return None
    return LoadedPromotionReport(
        payload=payload,
        source_kind=source_kind,
        source_path=str(rel_path).strip(),
    )


def _promotion_report_from_source(
    vault: Path,
    run_id: str,
    source: object,
) -> LoadedPromotionReport | None:
    if not isinstance(source, dict):
        return None
    promotion_report = source.get("promotion_report")
    if isinstance(promotion_report, dict):
        if not _promotion_report_matches_run(promotion_report, run_id):
            return None
        return LoadedPromotionReport(
            payload=promotion_report,
            source_kind="inline",
            source_path="",
        )
    return _load_promotion_report_from_rel(
        vault,
        promotion_report,
        run_id=run_id,
        source_kind="path",
    )


def _iteration_promotion_report(
    vault: Path,
    run_id: str,
    result: dict | None,
    existing_report: dict,
) -> LoadedPromotionReport | None:
    for source in (result, existing_report):
        promotion_report = _promotion_report_from_source(vault, run_id, source)
        if promotion_report is not None:
            return promotion_report
    return _load_promotion_report_from_rel(
        vault,
        run_rel(run_id, "promotion-report.json"),
        run_id=run_id,
        source_kind="default_path",
    )


def _decision_record_from_source(vault: Path, run_id: str, source: object) -> dict | None:
    if not isinstance(source, dict):
        return None
    promotion_report = _promotion_report_from_source(vault, run_id, source)
    if promotion_report is not None:
        try:
            decision_record = decision_record_from_report(
                promotion_report.payload,
                require_record=False,
            )
            return (
                decision_record
                if _decision_record_matches_run(decision_record, run_id)
                else None
            )
        except PromotionDecisionRegistryError:
            pass
    decision_record = source.get("decision_record")
    if isinstance(decision_record, dict):
        if not _decision_record_matches_run(decision_record, run_id):
            return None
        try:
            return decision_record_from_payload(
                {"decision_record": decision_record},
                require_record=True,
            )
        except PromotionDecisionRegistryError:
            pass
    return None


def _decision_from_record(decision_record: dict[str, Any] | None) -> str:
    if not isinstance(decision_record, dict):
        return ""
    return str(decision_record.get("decision", "")).strip().upper()


def _promotion_check_statuses(promotion_report: dict[str, Any]) -> dict[str, str]:
    checks = promotion_report.get("checks")
    if not isinstance(checks, list):
        return {}
    statuses: dict[str, str] = {}
    for check in checks:
        if not isinstance(check, dict):
            continue
        check_id = str(check.get("id", "")).strip()
        if not check_id:
            continue
        statuses[check_id] = str(check.get("status", "")).strip().upper()
    return statuses


def _blocking_promotion_check_ids(
    statuses: dict[str, str],
    decision_record: dict[str, Any] | None,
) -> list[str]:
    failed_ids = sorted(check_id for check_id, status in statuses.items() if status == "FAIL")
    if failed_ids:
        return failed_ids
    if isinstance(decision_record, dict):
        evidence_refs = decision_record.get("evidence_refs")
        if isinstance(evidence_refs, list):
            evidence_ids = sorted(str(item).strip() for item in evidence_refs if str(item).strip())
            if evidence_ids:
                return evidence_ids
    return sorted(
        check_id
        for check_id, status in _non_regression_check_statuses(statuses).items()
        if status in {"FAIL", "MISSING", "UNKNOWN"}
    )


def _non_regression_check_statuses(statuses: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for check_id in DISCARD_NON_REGRESSION_CHECK_IDS:
        raw_status = str(statuses.get(check_id, "")).strip().upper()
        if not raw_status:
            normalized[check_id] = "MISSING"
        elif raw_status in PROMOTION_CHECK_STATUS_VALUES:
            normalized[check_id] = raw_status
        else:
            normalized[check_id] = "UNKNOWN"
    return normalized


def _discard_non_regression_evidence(
    vault: Path,
    run_id: str,
    outcome: str,
    result: dict | None,
    existing_report: dict,
) -> dict[str, Any] | None:
    if str(outcome).strip().lower() != "discarded":
        return None
    promotion_report = _iteration_promotion_report(vault, run_id, result, existing_report)
    if promotion_report is None:
        return None
    decision_record: dict[str, Any] | None = None
    try:
        decision_record = decision_record_from_report(promotion_report.payload, require_record=False)
    except PromotionDecisionRegistryError:
        if isinstance(promotion_report.payload.get("decision_record"), dict):
            return None
        decision_record = None
    report_decision = _decision_from_record(decision_record)
    if not report_decision:
        report_decision = str(promotion_report.payload.get("decision", "")).strip().upper()
    if report_decision != "DISCARD":
        return None
    statuses = _promotion_check_statuses(promotion_report.payload)
    evidence: dict[str, Any] = {
        "promotion_report_source": promotion_report.source_kind,
        "candidate_eval_pass": statuses.get("candidate_eval_pass") == "PASS",
        "eval_score_improves": statuses.get("eval_score_improves") == "PASS",
        "lint_non_regression": statuses.get("lint_non_regression") == "PASS",
        "structural_complexity_non_regression": (
            statuses.get("structural_complexity_non_regression") == "PASS"
        ),
        "tests_non_regression": statuses.get("tests_non_regression") == "PASS",
        "non_regression_check_statuses": _non_regression_check_statuses(statuses),
        "blocking_check_ids": _blocking_promotion_check_ids(statuses, decision_record),
        "decision_record_reason_code": str(
            (decision_record or {}).get("reason_code", "")
        ).strip(),
    }
    if promotion_report.source_path:
        evidence["promotion_report"] = promotion_report.source_path
    return evidence


def _iteration_decision_record(
    vault: Path,
    run_id: str,
    result: dict | None,
    existing_report: dict,
) -> dict | None:
    for source in (result, existing_report):
        decision_record = _decision_record_from_source(vault, run_id, source)
        if decision_record is not None:
            return decision_record
    promotion_report = _load_promotion_report_from_rel(
        vault,
        run_rel(run_id, "promotion-report.json"),
        run_id=run_id,
        source_kind="default_path",
    )
    if promotion_report is None:
        return None
    try:
        decision_record = decision_record_from_report(
            promotion_report.payload,
            require_record=False,
        )
        return (
            decision_record
            if _decision_record_matches_run(decision_record, run_id)
            else None
        )
    except PromotionDecisionRegistryError:
        return None


def _preserve_existing_telemetry_fields(payload: dict[str, Any], existing_report: dict) -> None:
    for field in PRESERVED_RUN_TELEMETRY_FIELDS:
        if field in existing_report:
            payload[field] = existing_report[field]


def _update_session_loop_state(
    session: dict[str, Any],
    *,
    run_id: str,
    outcome: object,
    consecutive_failures: int,
    failure_taxonomy: object = "",
    context: RuntimeContext,
) -> None:
    outcome_text = str(getattr(outcome, "outcome", "")).strip()
    decision_text = str(getattr(outcome, "decision", "")).strip()
    terminal_success = bool(getattr(outcome, "is_terminal_success", False))
    blocking_reason = str(failure_taxonomy).strip() or outcome_text
    existing_state = session.get("loop_state")
    existing_state = existing_state if isinstance(existing_state, dict) else {}
    raw_counts = existing_state.get("blocking_reason_counts")
    blocking_reason_counts: dict[str, int] = {}
    if isinstance(raw_counts, dict):
        for key, value in raw_counts.items():
            reason = str(key).strip()
            if not reason:
                continue
            if isinstance(value, int) and not isinstance(value, bool):
                blocking_reason_counts[reason] = max(0, value)
    if blocking_reason and not terminal_success:
        blocking_reason_counts[blocking_reason] = blocking_reason_counts.get(blocking_reason, 0) + 1
    session["loop_state"] = {
        "consecutive_failures": max(0, consecutive_failures),
        "last_outcome": outcome_text,
        "last_decision": decision_text,
        "last_run_id": run_id,
        "last_blocking_reason": "" if terminal_success else blocking_reason,
        "blocking_reason_counts": blocking_reason_counts,
        "repeated_blocker_stop": bool(existing_state.get("repeated_blocker_stop", False)),
        "repeated_blocker_reason": str(existing_state.get("repeated_blocker_reason", "")).strip(),
        "remediation_backlog_path": str(
            existing_state.get("remediation_backlog_path", "ops/reports/remediation-backlog.json")
        ).strip()
        or "ops/reports/remediation-backlog.json",
        "updated_at": context.isoformat_z(),
    }


def write_iteration_telemetry(
    *args: Any,
    request: IterationTelemetryRequest | None = None,
    **kwargs: Any,
) -> str:
    request = _coerce_iteration_telemetry_request(request=request, args=args, kwargs=kwargs)
    loaded_existing_report = load_optional_json(
        request.vault / run_rel(request.run_id, "run-telemetry.json")
    )
    existing_report = loaded_existing_report if isinstance(loaded_existing_report, dict) else {}
    observed_at = request.context.isoformat_z()
    executor_report_rels = _iteration_executor_report_rels(
        request.vault,
        request.run_id,
        request.roles,
    )
    payload = {
        "session_id": request.session_id,
        "run_id": request.run_id,
        "generated_at": observed_at,
        "observed_at": observed_at,
        "proposal_id": request.proposal["proposal_id"],
        "source_candidate_id": str(request.proposal.get("source_candidate_id", "")).strip(),
        "proposal_snapshot": run_rel(request.run_id, "proposal-snapshot.json"),
        "scope_freeze": request.scope_freeze_rel,
        "routing_reports": request.routing_report_rels,
        "executor_reports": executor_report_rels,
        "phase_durations": request.phase_durations,
        "failure_taxonomy": request.outcome if request.outcome != "promoted" else "",
        "decision": (request.result or {}).get("decision", ""),
        "finalized": bool((request.result or {}).get("finalized")),
        "finalize_result": (request.result or {}).get("finalize_result", {}),
    }
    _preserve_existing_telemetry_fields(payload, existing_report)
    decision_record = _iteration_decision_record(
        request.vault,
        request.run_id,
        request.result,
        existing_report,
    )
    if isinstance(decision_record, dict):
        payload["decision_record"] = decision_record
        payload["decision"] = _decision_from_record(decision_record)
    discard_evidence = _discard_non_regression_evidence(
        request.vault,
        request.run_id,
        request.outcome,
        request.result,
        existing_report,
    )
    if discard_evidence is not None:
        payload["discard_non_regression_evidence"] = discard_evidence
    payload["failure_taxonomy"] = failure_taxonomy_from_iteration(
        request.outcome,
        decision_record=decision_record,
        discard_evidence=discard_evidence,
        result_failure_taxonomy=str((request.result or {}).get("failure_taxonomy", "")).strip(),
    )
    command_timeouts = _iteration_command_timeouts(request.vault, request.run_id, request.result)
    if command_timeouts is not None:
        payload["command_timeouts"] = command_timeouts
    timeout_failure_artifacts = _iteration_timeout_failure_artifacts(
        request.vault, request.run_id, request.result
    )
    if timeout_failure_artifacts:
        payload["timeout_failure_artifacts"] = timeout_failure_artifacts
    pre_promotion_failure_artifacts = _iteration_pre_promotion_failure_artifacts(
        request.vault,
        request.run_id,
        request.outcome,
    )
    if pre_promotion_failure_artifacts:
        payload["pre_promotion_failure_artifacts"] = pre_promotion_failure_artifacts
    behavior_delta = _iteration_behavior_delta(request.vault, request.run_id, request.result)
    behavior_delta_digest = ""
    if behavior_delta:
        payload["behavior_delta"] = behavior_delta
        behavior_delta_digest = iteration_behavior_delta_digest(
            request.vault,
            behavior_delta,
            existing_report,
        )
        if behavior_delta_digest:
            payload["behavior_delta_digest"] = behavior_delta_digest
    same_eval_reason = iteration_same_eval_reason(request.result, existing_report)
    if same_eval_reason:
        payload["same_eval_reason"] = same_eval_reason
    same_eval_contract = iteration_same_eval_contract(
        request.result,
        existing_report,
        same_eval_reason=same_eval_reason,
        behavior_delta_digest=behavior_delta_digest,
    )
    if same_eval_reason or same_eval_contract["same_eval_reason_code"] != "unknown":
        payload["same_eval_reason_code"] = same_eval_contract["same_eval_reason_code"]
        payload["strict_secondary_improvement_present"] = same_eval_contract[
            "strict_secondary_improvement_present"
        ]
        payload["secondary_improvement_axes"] = same_eval_contract["secondary_improvement_axes"]
    return write_run_telemetry(request.vault, request.run_id, payload)


def _coerce_iteration_telemetry_request(
    *,
    request: IterationTelemetryRequest | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> IterationTelemetryRequest:
    if request is not None:
        if args or kwargs:
            raise TypeError("request cannot be combined with positional or keyword telemetry fields")
        return request

    field_names = [
        "vault",
        "run_id",
        "session_id",
        "proposal",
        "scope_freeze_rel",
        "routing_report_rels",
        "roles",
        "phase_durations",
        "outcome",
        "result",
        "context",
    ]
    if len(args) > len(field_names):
        raise TypeError(f"expected at most {len(field_names)} positional arguments")
    values = dict(zip(field_names, args, strict=False))
    values.update(kwargs)
    missing = [name for name in field_names if name not in values]
    if missing:
        raise TypeError(f"missing iteration telemetry fields: {', '.join(missing)}")
    return IterationTelemetryRequest(**values)


def persist_iteration_phase(
    vault: Path,
    session: dict[str, Any],
    *,
    session_id: str,
    iteration: int,
    proposal: dict[str, Any],
    route_scaffold: RouteScaffoldPhaseResult,
    execution: ExecuteEvaluatePhaseResult,
    quarantined: set[str],
    context: RuntimeContext,
    dependencies: PersistIterationDependencies,
) -> PersistIterationPhaseResult:
    run_id = route_scaffold.run_id
    consecutive_failures = dependencies.apply_execution_outcome(
        session,
        proposal_id=proposal["proposal_id"],
        quarantined=quarantined,
        outcome=execution.outcome,
    )
    phase_durations = dict(route_scaffold.phase_durations)
    phase_durations.update(execution.phase_durations)
    telemetry_rel = dependencies.write_iteration_telemetry(
        request=IterationTelemetryRequest(
            vault=vault,
            run_id=run_id,
            session_id=session_id,
            proposal=proposal,
            scope_freeze_rel=route_scaffold.scope_freeze_rel,
            routing_report_rels=route_scaffold.routing_report_rels,
            roles=route_scaffold.roles,
            phase_durations=phase_durations,
            outcome=execution.outcome.outcome,
            result=execution.outcome.result,
            context=context,
        ),
    )
    dependencies.write_run_artifact_fingerprint(vault, run_id, context=context)
    executor_report_rels = _iteration_executor_report_rels(vault, run_id, route_scaffold.roles)
    telemetry_payload = load_optional_json(vault / telemetry_rel)
    telemetry_failure_taxonomy = str(telemetry_payload.get("failure_taxonomy", "")).strip() if isinstance(telemetry_payload, dict) else ""
    iteration_record = execution.outcome.iteration_record(
        index=iteration,
        proposal_id=proposal["proposal_id"],
        run_id=run_id,
    )
    if telemetry_failure_taxonomy:
        iteration_record["failure_taxonomy"] = telemetry_failure_taxonomy
    session["iterations"].append(iteration_record)
    next_run_decision = build_next_run_decision(
        session_id=session_id,
        iteration=iteration,
        run_id=run_id,
        proposal=proposal,
        outcome=execution.outcome,
        roles=route_scaffold.roles,
        scope_freeze_rel=route_scaffold.scope_freeze_rel,
        routing_report_rels=route_scaffold.routing_report_rels,
        telemetry_rel=telemetry_rel,
        context=context,
        executor_report_rels=executor_report_rels,
        blocking_role=_blocking_role_from_executor_reports(vault, executor_report_rels),
        failure_taxonomy_override=telemetry_failure_taxonomy,
    )
    if next_run_decision is not None:
        session.setdefault("next_run_decisions", []).append(next_run_decision)
    _update_session_loop_state(
        session,
        run_id=run_id,
        outcome=execution.outcome,
        consecutive_failures=consecutive_failures,
        failure_taxonomy=telemetry_failure_taxonomy,
        context=context,
    )
    dependencies.write_session_report(vault, session, context=context)
    return PersistIterationPhaseResult(
        consecutive_failures=consecutive_failures,
        telemetry_rel=telemetry_rel,
    )
