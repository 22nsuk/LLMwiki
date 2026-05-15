#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope  # noqa: PLC0415
    from ops.scripts.artifact_io_runtime import (  # noqa: PLC0415
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.learning.learning_claim_model import (  # noqa: PLC0415
        ImprovementClaimInputs,
        improvement_claim_model,
        learning_claim_blocker_status,
    )
    from ops.scripts.advisory_lifecycle_runtime import (  # noqa: PLC0415
        ADVISORY_LIFECYCLE_NOT_APPLICABLE,
        advisory_lifecycle_assessment,
        advisory_lifecycle_summary,
    )
    from ops.scripts.output_runtime import display_path  # noqa: PLC0415
    from ops.scripts.policy_runtime import load_policy, report_path  # noqa: PLC0415
    from ops.scripts.release.release_authority_vocabulary import REASON_MACHINE_RELEASE_NOT_ALLOWED  # noqa: PLC0415
    from ops.scripts.release.release_status_v2 import release_status_v2_view_with_readiness_fallback  # noqa: PLC0415
    from ops.scripts.runtime_context import RuntimeContext  # noqa: PLC0415
    from ops.scripts.schema_constants_runtime import (
        RELEASE_EVIDENCE_DASHBOARD_SCHEMA_PATH,
    )  # noqa: PLC0415
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )  # noqa: PLC0415
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.learning.learning_claim_model import (
        ImprovementClaimInputs,
        improvement_claim_model,
        learning_claim_blocker_status,
    )
    from .advisory_lifecycle_runtime import (
        ADVISORY_LIFECYCLE_NOT_APPLICABLE,
        advisory_lifecycle_assessment,
        advisory_lifecycle_summary,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.release.release_authority_vocabulary import (
        REASON_MACHINE_RELEASE_NOT_ALLOWED,
    )
    from .release_status_v2 import release_status_v2_view_with_readiness_fallback
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import RELEASE_EVIDENCE_DASHBOARD_SCHEMA_PATH
    from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint


DEFAULT_OUT = "ops/reports/release-evidence-dashboard.json"
PRODUCER = "ops.scripts.release_evidence_dashboard"
CLOSEOUT_PATH = "ops/reports/release-closeout-summary.json"
FIXED_POINT_PATH = "ops/reports/release-closeout-fixed-point.json"
FIXED_POINT_COST_TREND_PATH = "ops/reports/release-closeout-fixed-point-cost-trend.json"
SIGNOFF_REVALIDATION_PATH = "ops/reports/learning-readiness-signoff-revalidation.json"
ARTIFACT_FRESHNESS_PATH = "ops/reports/artifact-freshness-report.json"
LEARNING_DELTA_SCOREBOARD_PATH = "ops/reports/learning-delta-scoreboard.json"
RELEASE_STATE_CLEAN_PASS = "clean_pass"
RELEASE_STATE_CONDITIONAL_PASS = "conditional_pass"
RELEASE_STATE_BLOCKED = "blocked"
RELEASE_STATE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class LearningDeltaSections:
    summary: dict[str, Any]
    guard: dict[str, Any]
    unlock: dict[str, Any]
    placeholder_audit: dict[str, Any]


@dataclass(frozen=True)
class LearningDeltaCoverage:
    telemetry_ratio: float
    reason_ratio: float
    strict_secondary_ratio: float
    digest_ratio: float


@dataclass(frozen=True)
class LearningDeltaDecision:
    sections: LearningDeltaSections
    confirmed_predicate_results: list[dict[str, Any]]
    confirmed_blocking_predicate_ids: list[str]
    confirmed_summary: dict[str, Any]
    coverage: LearningDeltaCoverage
    confirmed_status: str
    evidence_cohort_status: str
    learning_claim_blocker_status: str
    claim_level: str
    bundle_status: str
    confirmed_wording_allowed: bool
    claim_model: dict[str, Any]
    claim_wording_policy_status: str


@dataclass(frozen=True)
class FinalizerEvidenceDigests:
    fixed_point_digest: str
    cost_trend_digest: str


@dataclass(frozen=True)
class FinalizerDurationSections:
    duration_summary: dict[str, Any]
    expensive_prerequisites: dict[str, Any]
    writer_costs: list[dict[str, Any]]
    threshold_summary: dict[str, Any]
    trend_latest_sample: dict[str, Any]


@dataclass(frozen=True)
class DashboardReports:
    closeout: dict[str, Any]
    closeout_load_status: str
    fixed_point: dict[str, Any]
    fixed_point_load_status: str
    cost_trend: dict[str, Any]
    cost_trend_load_status: str
    revalidation: dict[str, Any]
    revalidation_load_status: str
    freshness: dict[str, Any]
    freshness_load_status: str
    learning_scoreboard: dict[str, Any]
    learning_scoreboard_load_status: str


@dataclass(frozen=True)
class DashboardSignals:
    closeout_input: dict[str, Any]
    finalizer_duration: dict[str, Any]
    learning_guard: dict[str, Any]


@dataclass(frozen=True)
class DashboardStatusCounts:
    required_input_fail_count: int
    fail_count: int
    not_run_count: int
    accepted_risk_count: int
    gate_attention_count: int
    budget_attention_count: int
    status: str


@dataclass(frozen=True)
class DashboardRenderInputs:
    vault: Path
    policy: dict[str, Any]
    resolved_policy_path: Path
    generated_at: str
    current_fingerprint: str
    reports: DashboardReports
    signals: DashboardSignals
    gates: list[dict[str, Any]]
    status_counts: DashboardStatusCounts


def _load(vault: Path, rel_path: str) -> tuple[dict[str, Any], str]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(vault / rel_path)
    return payload, str(diagnostics.get("status", "unknown")).strip() or "unknown"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _issues_by_source(items: object) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(items, list):
        return grouped
    for item in items:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "")).strip() or "unknown"
        grouped.setdefault(source, []).append(item)
    return grouped


def _advisory_lifecycle_entries(
    closeout: dict[str, Any],
    *,
    generated_at: str,
) -> list[dict[str, Any]]:
    risks = closeout.get("accepted_risks", [])
    if not isinstance(risks, list):
        return []
    entries: list[dict[str, Any]] = []
    for risk in risks:
        if not isinstance(risk, dict):
            continue
        assessment = advisory_lifecycle_assessment(risk, generated_at=generated_at)
        if assessment["lifecycle_status"] == ADVISORY_LIFECYCLE_NOT_APPLICABLE:
            continue
        acceptance = risk.get("risk_acceptance")
        acceptance = acceptance if isinstance(acceptance, dict) else {}
        required_evidence = [
            str(item).strip()
            for item in risk.get("required_evidence", [])
            if str(item).strip()
        ]
        closure_action = str(acceptance.get("revalidation_condition", "")).strip()
        if closure_action:
            required_evidence.append(closure_action)
        entries.append(
            {
                "code": str(risk.get("code", "")).strip(),
                "source": str(risk.get("source", "")).strip(),
                "source_path": str(risk.get("source_path", CLOSEOUT_PATH)).strip()
                or CLOSEOUT_PATH,
                "risk_owner": str(acceptance.get("risk_owner", "")).strip(),
                "expires_at": str(acceptance.get("expires_at", "")).strip(),
                "closure_action": closure_action,
                "rollback_trigger": str(acceptance.get("rollback_trigger", "")).strip(),
                "required_evidence": required_evidence,
                **assessment,
            }
        )
    return entries


def _advisory_lifecycle_gate(
    closeout: dict[str, Any],
    *,
    generated_at: str,
) -> dict[str, Any] | None:
    entries = _advisory_lifecycle_entries(closeout, generated_at=generated_at)
    if not entries:
        return None
    summary = advisory_lifecycle_summary(entries)
    status = str(summary["advisory_backlog_status"])
    owner = next(
        (
            str(entry.get("risk_owner", "")).strip()
            for entry in entries
            if str(entry.get("risk_owner", "")).strip()
        ),
        "runtime-maintainer",
    )
    expiry = min(
        (
            str(entry.get("expires_at", "")).strip()
            for entry in entries
            if str(entry.get("expires_at", "")).strip()
        ),
        default="",
    )
    required_evidence = sorted(
        {
            str(item).strip()
            for entry in entries
            for item in entry.get("required_evidence", [])
            if str(item).strip()
        }
    )
    codes = [str(entry.get("code", "")).strip() for entry in entries]
    issue_count = int(summary["advisory_backlog_expired_count"]) + int(
        summary["advisory_backlog_missing_lifecycle_count"]
    )
    if issue_count:
        next_action = "Resolve expired or incomplete advisory accepted-risk lifecycle metadata before operator signoff."
    else:
        next_action = "Review advisory accepted-risk lifecycle before operator signoff."
    reason = (
        f"advisory_backlog_status={status}; "
        f"active={summary['advisory_backlog_active_count']}; "
        f"expired={summary['advisory_backlog_expired_count']}; "
        f"metadata_missing={summary['advisory_backlog_missing_lifecycle_count']}"
    )
    return {
        "gate_id": "advisory_lifecycle_review",
        "source_path": CLOSEOUT_PATH,
        "checked_in_state": "attention",
        "live_rerun_state": {
            "status": "attention",
            "reason": reason,
        },
        "authoritative_for_release": False,
        "accepted_risk": {
            "count": len(entries),
            "codes": codes,
        },
        "owner": owner,
        "expiry": expiry,
        "next_action": next_action,
        "required_evidence": required_evidence or [next_action],
        "claims": [
            {
                "claim": f"advisory accepted-risk lifecycle status is {status}",
                "provenance_label": "checked_in_json_confirmed",
            },
            {
                "claim": f"advisory accepted-risk codes requiring operator review: {', '.join(codes)}",
                "provenance_label": "checked_in_json_confirmed",
            },
        ],
    }


def _risk_owner_and_expiry(risks: list[dict[str, Any]]) -> tuple[str, str]:
    owners: set[str] = set()
    expiries: list[str] = []
    for risk in risks:
        acceptance = risk.get("risk_acceptance")
        if not isinstance(acceptance, dict):
            continue
        owner = str(acceptance.get("risk_owner", "")).strip()
        expiry = str(acceptance.get("expires_at", "")).strip()
        if owner:
            owners.add(owner)
        if expiry:
            expiries.append(expiry)
    expiries.sort()
    return ", ".join(sorted(owners)), (expiries[0] if expiries else "")


def _next_action(blockers: list[dict[str, Any]], risks: list[dict[str, Any]]) -> str:
    for blocker in blockers:
        required = blocker.get("required_evidence")
        if isinstance(required, list):
            for item in required:
                text = str(item).strip()
                if text:
                    return text
        message = str(blocker.get("message", "")).strip()
        if message:
            return message
    for risk in risks:
        acceptance = risk.get("risk_acceptance")
        if isinstance(acceptance, dict):
            text = str(acceptance.get("revalidation_condition", "")).strip()
            if text:
                return text
    return "none"


def _live_rerun_state(
    component: dict[str, Any], *, current_fingerprint: str
) -> dict[str, str]:
    component_fingerprint = str(component.get("source_tree_fingerprint", "")).strip()
    currentness_status = str(component.get("currentness_status", "")).strip()
    if not component_fingerprint:
        return {
            "status": "not_run",
            "reason": "component has no source_tree_fingerprint",
        }
    if component_fingerprint != current_fingerprint:
        return {
            "status": "not_run",
            "reason": "component fingerprint differs from current source tree",
        }
    if currentness_status != "current":
        return {
            "status": "not_run",
            "reason": f"component currentness_status={currentness_status or 'unknown'}",
        }
    if bool(component.get("ready")):
        return {
            "status": "pass",
            "reason": "checked-in component matches current source tree",
        }
    return {
        "status": "fail",
        "reason": "checked-in component matches current source tree but is not ready",
    }


def _component_evidence_label(live: dict[str, str]) -> str:
    reason = str(live.get("reason", "")).strip()
    if "matches current source tree" in reason:
        return "fingerprint_equivalent_to_checked_in"
    return "diagnostic_workspace_only"


def _component_gate(
    component: dict[str, Any],
    *,
    blockers: list[dict[str, Any]],
    accepted_risks: list[dict[str, Any]],
    current_fingerprint: str,
) -> dict[str, Any]:
    ready = bool(component.get("ready"))
    live = _live_rerun_state(component, current_fingerprint=current_fingerprint)
    owner, expiry = _risk_owner_and_expiry(accepted_risks)
    checked_state = "pass" if ready else ("attention" if accepted_risks else "fail")
    if ready and blockers:
        checked_state = "attention"
    if live["status"] == "fail" and accepted_risks:
        live = {
            "status": "attention",
            "reason": "checked-in component matches current source tree and is covered by accepted risk",
        }
    if live["status"] == "pass" and blockers:
        live = {
            "status": "attention",
            "reason": "checked-in component is source-clean but has non-source lane blockers",
        }
    claim_label = _component_evidence_label(live)
    return {
        "gate_id": str(component.get("name", "")).strip(),
        "source_path": str(component.get("path", "")).strip(),
        "checked_in_state": checked_state,
        "live_rerun_state": live,
        "authoritative_for_release": checked_state == "pass"
        and live["status"] == "pass",
        "accepted_risk": {
            "count": len(accepted_risks),
            "codes": [str(item.get("code", "")).strip() for item in accepted_risks],
        },
        "owner": owner or "runtime-maintainer",
        "expiry": expiry,
        "next_action": _next_action(blockers, accepted_risks),
        "required_evidence": [
            str(evidence)
            for blocker in blockers
            for evidence in blocker.get("required_evidence", [])
            if str(evidence).strip()
        ],
        "claims": [
            {
                "claim": f"{component.get('name', 'gate')} checked-in release evidence state is {checked_state}",
                "provenance_label": "checked_in_json_confirmed",
            },
            {
                "claim": (
                    f"{component.get('name', 'gate')} fingerprint/currentness diagnostic state "
                    f"is {live['status']}"
                ),
                "provenance_label": claim_label,
            },
        ],
    }


def _signoff_revalidation_gate(
    payload: dict[str, Any], load_status: str
) -> dict[str, Any]:
    status = (
        str(payload.get("status", "")).strip() if load_status == "ok" else "not_run"
    )
    required_actions = payload.get("required_actions", [])
    required_evidence = [
        str(item.get("action", "") or item.get("summary", "")).strip()
        for item in required_actions
        if isinstance(item, dict)
        and str(item.get("action", "") or item.get("summary", "")).strip()
    ]
    signoff_payload = payload.get("signoff")
    signoff: dict[str, Any] = (
        signoff_payload if isinstance(signoff_payload, dict) else {}
    )
    return {
        "gate_id": "learning_readiness_signoff_revalidation",
        "source_path": SIGNOFF_REVALIDATION_PATH,
        "checked_in_state": status or "not_run",
        "live_rerun_state": {
            "status": "not_run" if load_status != "ok" else status,
            "reason": "loaded checked-in revalidation report"
            if load_status == "ok"
            else f"load_status={load_status}",
        },
        "authoritative_for_release": status == "pass",
        "accepted_risk": {
            "count": 0,
            "codes": [],
        },
        "owner": str(signoff.get("risk_owner", "")).strip() or "runtime-maintainer",
        "expiry": str(signoff.get("expires_at", "")).strip(),
        "next_action": required_evidence[0] if required_evidence else "none",
        "required_evidence": required_evidence,
        "claims": [
            {
                "claim": f"learning readiness signoff revalidation state is {status or 'not_run'}",
                "provenance_label": "checked_in_json_confirmed"
                if load_status == "ok"
                else "diagnostic_workspace_only",
            }
        ],
    }


def _test_failure_lane_gate(lane: dict[str, Any]) -> dict[str, Any]:
    lane_id = str(lane.get("lane_id", "")).strip()
    status = str(lane.get("status", "")).strip() or "not_run"
    failed_nodeids = [
        str(item).strip()
        for item in lane.get("failed_nodeids", [])
        if str(item).strip()
    ]
    next_action = str(lane.get("next_action", "")).strip() or "none"
    return {
        "gate_id": f"test_failure_lane_{lane_id}",
        "source_path": str(lane.get("source_path", "")).strip()
        or "ops/reports/test-execution-summary.json",
        "checked_in_state": status,
        "live_rerun_state": {
            "status": status,
            "reason": str(lane.get("summary", "")).strip()
            or f"{lane_id} status={status}",
        },
        "authoritative_for_release": status == "pass",
        "accepted_risk": {
            "count": 0,
            "codes": [],
        },
        "owner": "runtime-maintainer",
        "expiry": "",
        "next_action": next_action,
        "required_evidence": [next_action] if next_action != "none" else [],
        "claims": [
            {
                "claim": f"{lane_id} release test lane state is {status}",
                "provenance_label": "checked_in_json_confirmed",
            },
            *[
                {
                    "claim": f"{lane_id} failing test: {nodeid}",
                    "provenance_label": "checked_in_json_confirmed",
                }
                for nodeid in failed_nodeids
            ],
        ],
    }


def _freshness_debt_summary(
    payload: dict[str, Any], load_status: str
) -> dict[str, Any]:
    if load_status != "ok":
        return {
            "load_status": load_status,
            "status": "unknown",
            "stable_debt_count": 0,
            "schema_invalid_artifact_count": 0,
        }
    summary_payload = payload.get("summary")
    summary: dict[str, Any] = (
        summary_payload if isinstance(summary_payload, dict) else {}
    )
    return {
        "load_status": load_status,
        "status": str(payload.get("status", "")).strip(),
        "stable_debt_count": int(
            summary.get(
                "stable_debt_count", summary.get("stable_contract_debt_issue_count", 0)
            )
            or 0
        ),
        "schema_invalid_artifact_count": int(
            summary.get("schema_invalid_artifact_count", 0) or 0
        ),
    }


def _release_smoke_boundedness_signal(closeout: dict[str, Any]) -> dict[str, Any]:
    gate = closeout.get("release_smoke_boundedness_gate")
    if not isinstance(gate, dict):
        return {
            "path": "ops/reports/release-smoke-report.json",
            "status": "unknown",
            "archive_budget_pass": False,
            "failing_budget_count": 0,
            "top_offender_count": 0,
            "summary": "release smoke boundedness gate unavailable from closeout summary",
        }
    return {
        "path": str(gate.get("path", "ops/reports/release-smoke-report.json")).strip()
        or "ops/reports/release-smoke-report.json",
        "status": str(gate.get("status", "unknown")).strip() or "unknown",
        "archive_budget_pass": bool(gate.get("archive_budget_pass", False)),
        "failing_budget_count": int(gate.get("failing_budget_count", 0) or 0),
        "top_offender_count": int(gate.get("top_offender_count", 0) or 0),
        "summary": str(gate.get("summary", "")).strip()
        or "release smoke boundedness gate loaded",
    }


def _finalizer_evidence_digests(vault: Path) -> FinalizerEvidenceDigests:
    fixed_point_path = vault / FIXED_POINT_PATH
    cost_trend_path = vault / FIXED_POINT_COST_TREND_PATH
    return FinalizerEvidenceDigests(
        fixed_point_digest=_sha256_file(fixed_point_path)
        if fixed_point_path.is_file()
        else "",
        cost_trend_digest=_sha256_file(cost_trend_path)
        if cost_trend_path.is_file()
        else "",
    )


def _missing_expensive_prerequisites(load_status: str) -> dict[str, Any]:
    return {
        "targets": [],
        "configured_target_count": 0,
        "observed_target_count": 0,
        "first_iteration_run_count": 0,
        "post_first_iteration_selected_count": 0,
        "post_first_iteration_run_count": 0,
        "skipped_post_first_iteration_selection_count": 0,
        "total_duration_ms": 0,
        "skip_policy_effective": False,
        "summary": f"fixed-point report load_status={load_status}",
    }


def _missing_finalizer_evidence_basis(
    digests: FinalizerEvidenceDigests, cost_trend_load_status: str
) -> dict[str, Any]:
    return {
        "fixed_point_report_path": FIXED_POINT_PATH,
        "fixed_point_report_digest": digests.fixed_point_digest,
        "current_fixed_point_report_digest": digests.fixed_point_digest,
        "fixed_point_generated_at": "",
        "cost_trend_path": FIXED_POINT_COST_TREND_PATH,
        "cost_trend_load_status": cost_trend_load_status,
        "cost_trend_digest": digests.cost_trend_digest,
        "cost_trend_sample_count": 0,
        "cost_trend_latest_fixed_point_digest": "",
        "sampled_fixed_point_report_digest": "",
        "basis_relation_to_current_fixed_point": "cost_trend_unavailable",
    }


def _missing_finalizer_duration_signal(
    load_status: str,
    cost_trend_load_status: str,
    digests: FinalizerEvidenceDigests,
) -> dict[str, Any]:
    return {
        "path": FIXED_POINT_PATH,
        "load_status": load_status,
        "fixed_point_report_status": "unknown",
        "status": "unknown",
        "converged": False,
        "iteration_count": 0,
        "command_run_count": 0,
        "total_duration_ms": 0,
        "writer_costs": [],
        "expensive_prerequisites_once": _missing_expensive_prerequisites(
            load_status
        ),
        "threshold_summary": {
            "status": "not_evaluated",
            "breached_writer_count": 0,
            "breached_writers": [],
            "summary": "fixed-point cost thresholds were not evaluated",
        },
        "evidence_basis": _missing_finalizer_evidence_basis(
            digests, cost_trend_load_status
        ),
        "summary": "fixed-point duration evidence unavailable",
    }


def _finalizer_duration_sections(
    fixed_point: dict[str, Any], cost_trend: dict[str, Any]
) -> FinalizerDurationSections:
    duration = fixed_point.get("duration_summary")
    duration_summary = duration if isinstance(duration, dict) else {}
    expensive = duration_summary.get("expensive_prerequisites_once")
    threshold = cost_trend.get("threshold_summary")
    latest = cost_trend.get("latest_sample")
    return FinalizerDurationSections(
        duration_summary=duration_summary,
        expensive_prerequisites=expensive if isinstance(expensive, dict) else {},
        writer_costs=[
            item
            for item in duration_summary.get("writer_costs", [])
            if isinstance(item, dict)
        ],
        threshold_summary=threshold if isinstance(threshold, dict) else {},
        trend_latest_sample=latest if isinstance(latest, dict) else {},
    )


def _cost_trend_basis_relation(
    *,
    cost_trend_load_status: str,
    sampled_fixed_point_digest: str,
    fixed_point_digest: str,
) -> str:
    if cost_trend_load_status != "ok":
        return "cost_trend_unavailable"
    if not sampled_fixed_point_digest:
        return "sample_missing"
    if sampled_fixed_point_digest == fixed_point_digest:
        return "sampled_current_fixed_point"
    return "sampled_different_fixed_point"


def _finalizer_threshold_status(threshold_summary: dict[str, Any]) -> str:
    status = (
        str(threshold_summary.get("status", "not_evaluated")).strip()
        or "not_evaluated"
    )
    return status if status in {"pass", "attention"} else "not_evaluated"


def _finalizer_signal_status(report_status: str, threshold_status: str) -> str:
    if threshold_status == "attention":
        return "attention"
    return "pass" if report_status == "pass" else report_status


def _writer_cost_records(writer_costs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": str(item.get("name", "")).strip(),
            "target": str(item.get("target", "")).strip(),
            "run_count": int(item.get("run_count", 0) or 0),
            "selected_iteration_count": int(
                item.get("selected_iteration_count", 0) or 0
            ),
            "total_duration_ms": int(item.get("total_duration_ms", 0) or 0),
            "average_duration_ms": int(item.get("average_duration_ms", 0) or 0),
            "max_duration_ms": int(item.get("max_duration_ms", 0) or 0),
            "skipped_after_first_iteration_count": int(
                item.get("skipped_after_first_iteration_count", 0) or 0
            ),
        }
        for item in writer_costs
        if str(item.get("target", "")).strip()
    ]


def _expensive_prerequisites_payload(expensive: dict[str, Any]) -> dict[str, Any]:
    return {
        "targets": [
            str(target).strip()
            for target in expensive.get("targets", [])
            if str(target).strip()
        ],
        "configured_target_count": int(
            expensive.get("configured_target_count", 0) or 0
        ),
        "observed_target_count": int(expensive.get("observed_target_count", 0) or 0),
        "first_iteration_run_count": int(
            expensive.get("first_iteration_run_count", 0) or 0
        ),
        "post_first_iteration_selected_count": int(
            expensive.get("post_first_iteration_selected_count", 0) or 0
        ),
        "post_first_iteration_run_count": int(
            expensive.get("post_first_iteration_run_count", 0) or 0
        ),
        "skipped_post_first_iteration_selection_count": int(
            expensive.get("skipped_post_first_iteration_selection_count", 0) or 0
        ),
        "total_duration_ms": int(expensive.get("total_duration_ms", 0) or 0),
        "skip_policy_effective": bool(expensive.get("skip_policy_effective", False)),
        "summary": str(expensive.get("summary", "")).strip()
        or "fixed-point expensive prerequisite duration evidence loaded",
    }


def _finalizer_threshold_summary_payload(
    threshold_summary: dict[str, Any],
    *,
    threshold_status: str,
    cost_trend_load_status: str,
) -> dict[str, Any]:
    return {
        "status": threshold_status,
        "breached_writer_count": int(
            threshold_summary.get("breached_writer_count", 0) or 0
        ),
        "breached_writers": [
            str(item).strip()
            for item in threshold_summary.get("breached_writers", [])
            if str(item).strip()
        ],
        "summary": str(threshold_summary.get("summary", "")).strip()
        or (
            "fixed-point cost trend thresholds loaded"
            if cost_trend_load_status == "ok"
            else f"fixed-point cost trend load_status={cost_trend_load_status}"
        ),
    }


def _finalizer_evidence_basis(
    fixed_point: dict[str, Any],
    cost_trend: dict[str, Any],
    sections: FinalizerDurationSections,
    digests: FinalizerEvidenceDigests,
    *,
    cost_trend_load_status: str,
    sampled_fixed_point_digest: str,
    basis_relation: str,
) -> dict[str, Any]:
    return {
        "fixed_point_report_path": FIXED_POINT_PATH,
        "fixed_point_report_digest": digests.fixed_point_digest,
        "current_fixed_point_report_digest": digests.fixed_point_digest,
        "fixed_point_generated_at": str(fixed_point.get("generated_at", "")).strip(),
        "cost_trend_path": FIXED_POINT_COST_TREND_PATH,
        "cost_trend_load_status": cost_trend_load_status,
        "cost_trend_digest": digests.cost_trend_digest,
        "cost_trend_sample_count": int(cost_trend.get("sample_count", 0) or 0)
        if cost_trend_load_status == "ok"
        else 0,
        "cost_trend_latest_fixed_point_digest": str(
            sections.trend_latest_sample.get("fixed_point_report_digest", "")
        ).strip(),
        "sampled_fixed_point_report_digest": sampled_fixed_point_digest,
        "basis_relation_to_current_fixed_point": basis_relation,
    }


def _finalizer_duration_signal(
    vault: Path,
    fixed_point: dict[str, Any],
    load_status: str,
    cost_trend: dict[str, Any],
    cost_trend_load_status: str,
) -> dict[str, Any]:
    digests = _finalizer_evidence_digests(vault)
    if load_status != "ok":
        return _missing_finalizer_duration_signal(
            load_status, cost_trend_load_status, digests
        )
    sections = _finalizer_duration_sections(fixed_point, cost_trend)
    sampled_digest = str(
        sections.trend_latest_sample.get("fixed_point_report_digest", "")
    ).strip()
    basis_relation = _cost_trend_basis_relation(
        cost_trend_load_status=cost_trend_load_status,
        sampled_fixed_point_digest=sampled_digest,
        fixed_point_digest=digests.fixed_point_digest,
    )
    threshold_status = _finalizer_threshold_status(sections.threshold_summary)
    report_status = str(fixed_point.get("status", "unknown")).strip() or "unknown"
    return {
        "path": FIXED_POINT_PATH,
        "load_status": load_status,
        "fixed_point_report_status": report_status,
        "status": _finalizer_signal_status(report_status, threshold_status),
        "converged": bool(fixed_point.get("converged", False)),
        "iteration_count": int(
            sections.duration_summary.get(
                "iteration_count", fixed_point.get("iteration_count", 0)
            )
            or 0
        ),
        "command_run_count": int(
            sections.duration_summary.get("command_run_count", 0) or 0
        ),
        "total_duration_ms": int(
            sections.duration_summary.get("total_duration_ms", 0) or 0
        ),
        "writer_costs": _writer_cost_records(sections.writer_costs),
        "expensive_prerequisites_once": _expensive_prerequisites_payload(
            sections.expensive_prerequisites
        ),
        "threshold_summary": _finalizer_threshold_summary_payload(
            sections.threshold_summary,
            threshold_status=threshold_status,
            cost_trend_load_status=cost_trend_load_status,
        ),
        "evidence_basis": _finalizer_evidence_basis(
            fixed_point,
            cost_trend,
            sections,
            digests,
            cost_trend_load_status=cost_trend_load_status,
            sampled_fixed_point_digest=sampled_digest,
            basis_relation=basis_relation,
        ),
        "summary": str(sections.duration_summary.get("summary", "")).strip()
        or "fixed-point duration evidence loaded",
    }


def _coverage_status(value: object) -> str:
    if not isinstance(value, int | float):
        return "unknown"
    if value >= 1.0:
        return "full"
    if value > 0:
        return "partial"
    return "none"


def _summary_coverage_status(summary: dict[str, Any], key: str, ratio_key: str) -> str:
    status = str(summary.get(key, "")).strip()
    if status in {"full", "partial", "none", "no_evidence", "not_applicable"}:
        return status
    return _coverage_status(summary.get(ratio_key))


def _confirmed_evidence_summary(
    value: object, blocking_ids: list[str]
) -> dict[str, Any]:
    summary = value if isinstance(value, dict) else {}
    evidence_status = (
        str(
            summary.get(
                "evidence_cohort_status",
                summary.get("confirmed_evidence_status", "not_ready"),
            )
        ).strip()
        or "not_ready"
    )
    legacy_summary = summary.get("legacy_reconstruction_summary")
    return {
        "evidence_cohort_status": evidence_status,
        "confirmed_evidence_status": evidence_status,
        "valid_run_count": int(summary.get("valid_run_count", 0) or 0),
        "min_required_run_count": int(summary.get("min_required_run_count", 0) or 0),
        "eligible_family_count": int(summary.get("eligible_family_count", 0) or 0),
        "selected_valid_run_ids": [
            str(item).strip()
            for item in summary.get("selected_valid_run_ids", [])
            if str(item).strip()
        ],
        "blocking_predicate_ids": [
            str(item).strip()
            for item in summary.get("blocking_predicate_ids", blocking_ids)
            if str(item).strip()
        ],
        "rejected_run_count": int(summary.get("rejected_run_count", 0) or 0),
        "rejected_run_diagnostics": [
            item
            for item in summary.get("rejected_run_diagnostics", [])
            if isinstance(item, dict)
        ],
        "legacy_reconstruction_summary": legacy_summary
        if isinstance(legacy_summary, dict)
        else {
            "status": "not_used",
            "reconstruction_needed_count": 0,
            "reconstructed_run_count": 0,
            "blocked_run_count": 0,
            "run_diagnostics": [],
        },
    }


def _missing_learning_delta_claim_model() -> dict[str, Any]:
    return improvement_claim_model(
        ImprovementClaimInputs(
            guard_status="unknown",
            claims_learning_improved=False,
            learning_claim_evidence_complete=False,
            bounded_learning_claim_allowed=False,
            confirmed_learning_improvement_allowed=False,
            improvement_claim_status="not_ready",
            evidence_cohort_status="not_ready",
            claim_level="none",
            bundle_status="not_evaluated",
            blocking_predicate_ids=[],
            learning_claim_blocker_status="not_evaluated",
            same_eval_run_count=0,
            same_eval_reason_coverage_status="unknown",
            strict_secondary_improvement_coverage_status="unknown",
            behavior_delta_digest_coverage_status="unknown",
        )
    )


def _missing_learning_delta_guard_summary(load_status: str) -> dict[str, Any]:
    return {
        "path": LEARNING_DELTA_SCOREBOARD_PATH,
        "load_status": load_status,
        "status": "unknown",
        "claims_learning_improved": False,
        "learning_claim_allowed": False,
        "learning_likely": False,
        "bounded_learning_claim_allowed": False,
        "confirmed_learning_improvement_allowed": False,
        "improvement_claim_status": "not_ready",
        "confirmed_learning_improvement_status": "not_ready",
        "evidence_cohort_status": "not_ready",
        "learning_claim_blocker_status": "not_evaluated",
        "confirmed_blocking_predicate_ids": [],
        "confirmed_evidence_summary": _confirmed_evidence_summary({}, []),
        "confirmed_predicate_results": [],
        "claim_level": "none",
        "claim_scope": "",
        "learning_claim_unlock_review_status": "unknown",
        "learning_claim_unlock_review_approved": False,
        "learning_claim_unlock_review_revocation_status": "not_evaluated",
        "learning_claim_evidence_bundle_status": "not_evaluated",
        "claim_wording_allowed": False,
        "claim_wording_policy_status": "blocked",
        "confirmed_wording_allowed": False,
        "confirmed_wording_policy_status": "blocked",
        "self_improvement_claim_model": _missing_learning_delta_claim_model(),
        "learning_claim_unlock_review_source": "",
        "same_eval_run_count": 0,
        "telemetry_coverage_ratio": 0.0,
        "telemetry_coverage_status": "unknown",
        "same_eval_reason_coverage_ratio": 0.0,
        "same_eval_reason_coverage_status": "unknown",
        "strict_secondary_improvement_coverage_ratio": 0.0,
        "strict_secondary_improvement_coverage_status": "unknown",
        "behavior_delta_digest_coverage_ratio": 0.0,
        "behavior_delta_digest_coverage_status": "unknown",
        "placeholder_audit_status": "unknown",
        "placeholder_count": 0,
        "reason": f"learning delta scoreboard load_status={load_status}",
    }


def _learning_delta_sections(payload: dict[str, Any]) -> LearningDeltaSections:
    summary = payload.get("summary")
    guard = payload.get("learning_claim_guard")
    unlock = payload.get("learning_claim_unlock_review")
    placeholder = payload.get("external_report_placeholder_audit")
    return LearningDeltaSections(
        summary=summary if isinstance(summary, dict) else {},
        guard=guard if isinstance(guard, dict) else {},
        unlock=unlock if isinstance(unlock, dict) else {},
        placeholder_audit=placeholder if isinstance(placeholder, dict) else {},
    )


def _confirmed_predicate_results(unlock: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in unlock.get("confirmed_predicate_results", [])
        if isinstance(item, dict)
    ]


def _confirmed_blocking_predicate_ids(
    summary: dict[str, Any], predicate_results: list[dict[str, Any]]
) -> list[str]:
    explicit_ids = [
        str(item).strip()
        for item in summary.get("confirmed_blocking_predicate_ids", [])
        if str(item).strip()
    ]
    if explicit_ids:
        return explicit_ids
    return [
        str(item.get("id", "")).strip()
        for item in predicate_results
        if str(item.get("id", "")).strip()
        and str(item.get("status", "")).strip() != "pass"
    ]


def _confirmed_summary_payload(
    payload: dict[str, Any], unlock: dict[str, Any]
) -> object:
    value = payload.get("confirmed_evidence_summary")
    return value if isinstance(value, dict) else unlock.get("confirmed_evidence_summary")


def _learning_delta_coverage(summary: dict[str, Any]) -> LearningDeltaCoverage:
    return LearningDeltaCoverage(
        telemetry_ratio=float(summary.get("telemetry_coverage_ratio", 0.0) or 0.0),
        reason_ratio=float(
            summary.get("same_eval_reason_coverage_ratio", 0.0) or 0.0
        ),
        strict_secondary_ratio=float(
            summary.get("strict_secondary_improvement_coverage_ratio", 0.0) or 0.0
        ),
        digest_ratio=float(
            summary.get("behavior_delta_digest_coverage_ratio", 0.0) or 0.0
        ),
    )


def _improvement_claim_status(summary: dict[str, Any]) -> str:
    return (
        str(
            summary.get(
                "improvement_claim_status",
                summary.get("confirmed_learning_improvement_status", "not_ready"),
            )
        ).strip()
        or "not_ready"
    )


def _evidence_cohort_status(
    summary: dict[str, Any], confirmed_summary: dict[str, Any]
) -> str:
    return (
        str(
            summary.get(
                "evidence_cohort_status",
                confirmed_summary.get("evidence_cohort_status", "not_ready"),
            )
        ).strip()
        or "not_ready"
    )


def _learning_claim_bundle_status(summary: dict[str, Any]) -> str:
    return (
        str(
            summary.get("learning_claim_evidence_bundle_status", "not_evaluated")
        ).strip()
        or "not_evaluated"
    )


def _confirmed_wording_allowed(
    *,
    summary: dict[str, Any],
    claim_level: str,
    confirmed_status: str,
    evidence_cohort_status: str,
    bundle_status: str,
    blocking_predicate_ids: list[str],
) -> bool:
    if "claim_wording_allowed" in summary:
        return bool(summary.get("claim_wording_allowed"))
    return (
        claim_level == "confirmed_learning_improvement"
        and bool(summary.get("confirmed_learning_improvement_allowed"))
        and confirmed_status == "auto_confirmed"
        and evidence_cohort_status == "auto_confirmed"
        and bundle_status == "active"
        and not blocking_predicate_ids
    )


def _learning_delta_claim_model(
    payload: dict[str, Any],
    sections: LearningDeltaSections,
    *,
    confirmed_status: str,
    evidence_cohort_status: str,
    claim_level: str,
    bundle_status: str,
    blocking_predicate_ids: list[str],
    learning_claim_blocker_status_value: str,
) -> dict[str, Any]:
    summary = sections.summary
    raw_claim_model = summary.get("self_improvement_claim_model")
    if not isinstance(raw_claim_model, dict):
        raw_claim_model = payload.get("self_improvement_claim_model")
    if isinstance(raw_claim_model, dict):
        return raw_claim_model
    return improvement_claim_model(
        ImprovementClaimInputs(
            guard_status=str(
                sections.guard.get("status", payload.get("status", "unknown"))
            ).strip()
            or "unknown",
            claims_learning_improved=bool(summary.get("claims_learning_improved")),
            learning_claim_evidence_complete=bool(
                summary.get("learning_claim_evidence_complete")
            ),
            bounded_learning_claim_allowed=bool(
                summary.get("bounded_learning_claim_allowed")
            ),
            confirmed_learning_improvement_allowed=bool(
                summary.get("confirmed_learning_improvement_allowed")
            ),
            improvement_claim_status=confirmed_status,
            evidence_cohort_status=evidence_cohort_status,
            claim_level=claim_level,
            bundle_status=bundle_status,
            blocking_predicate_ids=blocking_predicate_ids,
            learning_claim_blocker_status=learning_claim_blocker_status_value,
            same_eval_run_count=int(summary.get("same_eval_run_count", 0) or 0),
            same_eval_reason_coverage_status=_summary_coverage_status(
                summary,
                "same_eval_reason_coverage_status",
                "same_eval_reason_coverage_ratio",
            ),
            strict_secondary_improvement_coverage_status=_summary_coverage_status(
                summary,
                "strict_secondary_improvement_coverage_status",
                "strict_secondary_improvement_coverage_ratio",
            ),
            behavior_delta_digest_coverage_status=_summary_coverage_status(
                summary,
                "behavior_delta_digest_coverage_status",
                "behavior_delta_digest_coverage_ratio",
            ),
        )
    )


def _learning_delta_decision(payload: dict[str, Any]) -> LearningDeltaDecision:
    sections = _learning_delta_sections(payload)
    predicate_results = _confirmed_predicate_results(sections.unlock)
    blocking_ids = _confirmed_blocking_predicate_ids(sections.summary, predicate_results)
    confirmed_summary = _confirmed_evidence_summary(
        _confirmed_summary_payload(payload, sections.unlock),
        blocking_ids,
    )
    confirmed_status = _improvement_claim_status(sections.summary)
    evidence_status = _evidence_cohort_status(sections.summary, confirmed_summary)
    has_confirmed_predicates = bool(predicate_results)
    blocker_status = (
        str(
            sections.summary.get(
                "learning_claim_blocker_status",
                learning_claim_blocker_status(blocking_ids)
                if has_confirmed_predicates
                else "not_evaluated",
            )
        ).strip()
        or ("clear" if has_confirmed_predicates else "not_evaluated")
    )
    claim_level = str(sections.summary.get("claim_level", "none")).strip() or "none"
    bundle_status = _learning_claim_bundle_status(sections.summary)
    wording_allowed = _confirmed_wording_allowed(
        summary=sections.summary,
        claim_level=claim_level,
        confirmed_status=confirmed_status,
        evidence_cohort_status=evidence_status,
        bundle_status=bundle_status,
        blocking_predicate_ids=blocking_ids,
    )
    claim_model = _learning_delta_claim_model(
        payload,
        sections,
        confirmed_status=confirmed_status,
        evidence_cohort_status=evidence_status,
        claim_level=claim_level,
        bundle_status=bundle_status,
        blocking_predicate_ids=blocking_ids,
        learning_claim_blocker_status_value=blocker_status,
    )
    return LearningDeltaDecision(
        sections=sections,
        confirmed_predicate_results=predicate_results,
        confirmed_blocking_predicate_ids=blocking_ids,
        confirmed_summary=confirmed_summary,
        coverage=_learning_delta_coverage(sections.summary),
        confirmed_status=confirmed_status,
        evidence_cohort_status=evidence_status,
        learning_claim_blocker_status=blocker_status,
        claim_level=claim_level,
        bundle_status=bundle_status,
        confirmed_wording_allowed=wording_allowed,
        claim_model=claim_model,
        claim_wording_policy_status=str(
            sections.summary.get("claim_wording_policy_status", "")
        ).strip()
        or ("pre_seal_ready" if wording_allowed else "blocked"),
    )


def _loaded_learning_delta_guard_summary(
    payload: dict[str, Any], load_status: str
) -> dict[str, Any]:
    decision = _learning_delta_decision(payload)
    summary = decision.sections.summary
    guard = decision.sections.guard
    placeholder = decision.sections.placeholder_audit
    return {
        "path": LEARNING_DELTA_SCOREBOARD_PATH,
        "load_status": load_status,
        "status": str(guard.get("status", payload.get("status", "unknown"))).strip()
        or "unknown",
        "claims_learning_improved": bool(summary.get("claims_learning_improved")),
        "learning_claim_allowed": bool(summary.get("learning_claim_allowed")),
        "learning_likely": bool(
            summary.get("learning_likely", summary.get("claims_learning_improved"))
        ),
        "bounded_learning_claim_allowed": bool(
            summary.get("bounded_learning_claim_allowed")
        ),
        "confirmed_learning_improvement_allowed": bool(
            summary.get("confirmed_learning_improvement_allowed")
        ),
        "improvement_claim_status": decision.confirmed_status,
        "confirmed_learning_improvement_status": decision.confirmed_status,
        "evidence_cohort_status": decision.evidence_cohort_status,
        "learning_claim_blocker_status": decision.learning_claim_blocker_status,
        "confirmed_blocking_predicate_ids": decision.confirmed_blocking_predicate_ids,
        "confirmed_evidence_summary": decision.confirmed_summary,
        "confirmed_predicate_results": decision.confirmed_predicate_results,
        "claim_level": decision.claim_level,
        "claim_scope": str(summary.get("claim_scope", "")).strip(),
        "learning_claim_unlock_review_status": str(
            summary.get("learning_claim_unlock_review_status", "unknown")
        ).strip()
        or "unknown",
        "learning_claim_unlock_review_approved": bool(
            summary.get("learning_claim_unlock_review_approved")
        ),
        "learning_claim_unlock_review_revocation_status": str(
            summary.get(
                "learning_claim_unlock_review_revocation_status", "not_evaluated"
            )
        ).strip()
        or "not_evaluated",
        "learning_claim_evidence_bundle_status": decision.bundle_status,
        "claim_wording_allowed": decision.confirmed_wording_allowed,
        "claim_wording_policy_status": decision.claim_wording_policy_status,
        "confirmed_wording_allowed": decision.confirmed_wording_allowed,
        "confirmed_wording_policy_status": decision.claim_wording_policy_status,
        "self_improvement_claim_model": decision.claim_model,
        "learning_claim_unlock_review_source": str(
            decision.sections.unlock.get("source_path", "")
        ).strip(),
        "same_eval_run_count": int(summary.get("same_eval_run_count", 0) or 0),
        "telemetry_coverage_ratio": decision.coverage.telemetry_ratio,
        "telemetry_coverage_status": _summary_coverage_status(
            summary, "telemetry_coverage_status", "telemetry_coverage_ratio"
        ),
        "same_eval_reason_coverage_ratio": decision.coverage.reason_ratio,
        "same_eval_reason_coverage_status": _summary_coverage_status(
            summary,
            "same_eval_reason_coverage_status",
            "same_eval_reason_coverage_ratio",
        ),
        "strict_secondary_improvement_coverage_ratio": (
            decision.coverage.strict_secondary_ratio
        ),
        "strict_secondary_improvement_coverage_status": _summary_coverage_status(
            summary,
            "strict_secondary_improvement_coverage_status",
            "strict_secondary_improvement_coverage_ratio",
        ),
        "behavior_delta_digest_coverage_ratio": decision.coverage.digest_ratio,
        "behavior_delta_digest_coverage_status": _summary_coverage_status(
            summary,
            "behavior_delta_digest_coverage_status",
            "behavior_delta_digest_coverage_ratio",
        ),
        "placeholder_audit_status": str(
            placeholder.get("status", "unknown")
        ).strip()
        or "unknown",
        "placeholder_count": int(
            placeholder.get("placeholder_count", summary.get("placeholder_count", 0))
            or 0
        ),
        "reason": str(guard.get("reason", "")).strip()
        or "learning delta scoreboard guard status loaded",
    }


def _learning_delta_guard_summary(
    payload: dict[str, Any], load_status: str
) -> dict[str, Any]:
    if load_status != "ok":
        return _missing_learning_delta_guard_summary(load_status)
    return _loaded_learning_delta_guard_summary(payload, load_status)


def _learning_delta_guard_gate(guard_summary: dict[str, Any]) -> dict[str, Any]:
    load_status = str(guard_summary.get("load_status", "unknown")).strip() or "unknown"
    guard_status = str(guard_summary.get("status", "unknown")).strip() or "unknown"
    claims_learning_improved = bool(guard_summary.get("claims_learning_improved"))
    learning_claim_allowed = bool(guard_summary.get("learning_claim_allowed"))
    reason = str(guard_summary.get("reason", "")).strip()
    if load_status != "ok":
        checked_in_state = "fail"
        next_action = (
            "Regenerate learning-delta-scoreboard before release dashboard signoff."
        )
        reason = reason or f"learning delta scoreboard load_status={load_status}"
    elif guard_status == "pass":
        checked_in_state = "pass"
        next_action = "none"
    elif _learning_claim_blocked_only_by_unlock_review(guard_summary):
        checked_in_state = "attention"
        next_action = (
            "Obtain learning-claim-unlock-review approval before claiming runtime learning improvement; "
            "source release evidence may proceed without the learning claim."
        )
    else:
        checked_in_state = "fail"
        next_action = "Resolve learning claim guard blockers before claiming runtime learning improvement."

    return {
        "gate_id": "learning_delta_scoreboard_guard",
        "source_path": LEARNING_DELTA_SCOREBOARD_PATH,
        "checked_in_state": checked_in_state,
        "live_rerun_state": {
            "status": checked_in_state,
            "reason": reason
            or f"learning_delta_scoreboard_guard status={guard_status}",
        },
        "authoritative_for_release": checked_in_state == "pass",
        "accepted_risk": {
            "count": 0,
            "codes": [],
        },
        "owner": "runtime-maintainer",
        "expiry": "",
        "next_action": next_action,
        "required_evidence": [next_action] if next_action != "none" else [],
        "claims": [
            {
                "claim": (
                    "learning delta scoreboard guard is "
                    f"{guard_status}; claims_learning_improved={claims_learning_improved}; "
                    f"bounded_learning_claim_allowed={guard_summary.get('bounded_learning_claim_allowed')}; "
                    f"confirmed_learning_improvement_allowed="
                    f"{guard_summary.get('confirmed_learning_improvement_allowed')}; "
                    f"learning_claim_allowed={learning_claim_allowed}"
                ),
                "provenance_label": "checked_in_json_confirmed"
                if load_status == "ok"
                else "diagnostic_workspace_only",
            },
            {
                "claim": (
                    "learning claim unlock review is "
                    f"{guard_summary.get('learning_claim_unlock_review_status')}; "
                    f"approved={guard_summary.get('learning_claim_unlock_review_approved')}; "
                    f"revocation={guard_summary.get('learning_claim_unlock_review_revocation_status')}; "
                    f"bundle={guard_summary.get('learning_claim_evidence_bundle_status')}; "
                    f"source={guard_summary.get('learning_claim_unlock_review_source') or 'none'}"
                ),
                "provenance_label": "checked_in_json_confirmed"
                if load_status == "ok"
                else "diagnostic_workspace_only",
            },
            {
                "claim": (
                    "confirmed learning predicates are "
                    + (
                        ", ".join(
                            f"{item.get('id')}={item.get('status')}"
                            for item in guard_summary.get(
                                "confirmed_predicate_results", []
                            )
                            if isinstance(item, dict)
                        )
                        or "not_available"
                    )
                    + "; blocking="
                    + (
                        ",".join(
                            str(item)
                            for item in guard_summary.get(
                                "confirmed_blocking_predicate_ids", []
                            )
                            if str(item).strip()
                        )
                        or "none"
                    )
                ),
                "provenance_label": "checked_in_json_confirmed"
                if load_status == "ok"
                else "diagnostic_workspace_only",
            },
            {
                "claim": (
                    "same-eval evidence coverage is "
                    f"telemetry={guard_summary.get('telemetry_coverage_status')}, "
                    f"reason={guard_summary.get('same_eval_reason_coverage_status')}, "
                    f"strict_secondary={guard_summary.get('strict_secondary_improvement_coverage_status')}, "
                    f"digest={guard_summary.get('behavior_delta_digest_coverage_status')}"
                ),
                "provenance_label": "checked_in_json_confirmed"
                if load_status == "ok"
                else "diagnostic_workspace_only",
            },
        ],
    }


def _learning_claim_blocked_only_by_unlock_review(
    guard_summary: dict[str, Any],
) -> bool:
    if str(guard_summary.get("status", "")).strip() != "blocked":
        return False
    if not bool(guard_summary.get("claims_learning_improved")):
        return False
    if bool(guard_summary.get("learning_claim_allowed")):
        return False
    if (
        str(guard_summary.get("learning_claim_unlock_review_status", "")).strip()
        != "required"
    ):
        return False
    if bool(guard_summary.get("learning_claim_unlock_review_approved")):
        return False
    coverage_keys = (
        "telemetry_coverage_status",
        "same_eval_reason_coverage_status",
        "strict_secondary_improvement_coverage_status",
        "behavior_delta_digest_coverage_status",
    )
    if any(str(guard_summary.get(key, "")).strip() != "full" for key in coverage_keys):
        return False
    return str(guard_summary.get("placeholder_audit_status", "")).strip() == "pass"


def _closeout_input_status(payload: dict[str, Any], load_status: str) -> dict[str, Any]:
    status_view = release_status_v2_view_with_readiness_fallback(payload)
    status = (
        str(status_view["compatibility_status_value"]).strip()
        if load_status == "ok"
        else "unknown"
    )
    release_authority_status = str(status_view["release_authority_status"]).strip() or "unknown"
    semantic_release_status = str(status_view["semantic_release_status"]).strip() or "unknown"
    sealed_release_status = str(status_view["sealed_release_status"]).strip() or "unknown"
    blocker_reason_ids = [str(reason) for reason in status_view["blocker_reason_ids"]]
    used_legacy_fallback_fields = [
        str(field) for field in status_view["used_legacy_fallback_fields"]
    ]
    checked_in_release_ready = bool(payload.get("checked_in_release_ready"))
    conditional_release_ready = bool(payload.get("conditional_release_ready"))
    clean_release_ready = bool(payload.get("clean_release_ready"))
    live_make_check = payload.get("live_make_check")
    live_make_check = live_make_check if isinstance(live_make_check, dict) else {}
    live_make_check_status = str(live_make_check.get("status", "unknown")).strip() or "unknown"
    live_make_check_ready = bool(live_make_check.get("ready", False))
    live_make_check_blocking = bool(live_make_check.get("blocking", load_status == "ok"))

    if load_status != "ok":
        release_authority_status = RELEASE_STATE_BLOCKED
        semantic_release_status = RELEASE_STATE_BLOCKED
        sealed_release_status = "unknown"
        blocker_reason_ids = []
        used_legacy_fallback_fields = []
        machine_release_allowed = False
        operator_release_allowed = False
        requires_accepted_risk_review = False
    else:
        if release_authority_status == RELEASE_STATE_UNKNOWN:
            if clean_release_ready:
                release_authority_status = RELEASE_STATE_CLEAN_PASS
                semantic_release_status = RELEASE_STATE_CLEAN_PASS
            elif conditional_release_ready:
                release_authority_status = RELEASE_STATE_CONDITIONAL_PASS
                semantic_release_status = RELEASE_STATE_CONDITIONAL_PASS
            elif checked_in_release_ready:
                release_authority_status = RELEASE_STATE_UNKNOWN
            else:
                release_authority_status = RELEASE_STATE_BLOCKED
                semantic_release_status = RELEASE_STATE_BLOCKED
        machine_release_allowed = (
            release_authority_status == RELEASE_STATE_CLEAN_PASS
            and REASON_MACHINE_RELEASE_NOT_ALLOWED not in blocker_reason_ids
        )
        operator_release_allowed = release_authority_status in {
            RELEASE_STATE_CLEAN_PASS,
            RELEASE_STATE_CONDITIONAL_PASS,
        }
        requires_accepted_risk_review = (
            release_authority_status == RELEASE_STATE_CONDITIONAL_PASS
        )

    return {
        "path": CLOSEOUT_PATH,
        "load_status": load_status,
        "status": status,
        "release_readiness_state": release_authority_status,
        "release_authority_status": release_authority_status,
        "semantic_release_status": semantic_release_status,
        "sealed_release_status": sealed_release_status,
        "status_v2_blocker_reason_ids": blocker_reason_ids,
        "status_v2_used_legacy_fallback_fields": used_legacy_fallback_fields,
        "machine_release_allowed": bool(machine_release_allowed),
        "operator_release_allowed": bool(operator_release_allowed),
        "requires_accepted_risk_review": bool(requires_accepted_risk_review),
        "live_make_check_status": live_make_check_status,
        "live_make_check_ready": live_make_check_ready,
        "live_make_check_blocking": live_make_check_blocking,
        "summary": (
            f"release_authority_status={release_authority_status}; "
            f"sealed_release_status={sealed_release_status}; "
            f"machine_release_allowed={bool(machine_release_allowed)}; "
            f"operator_release_allowed={bool(operator_release_allowed)}; "
            f"requires_accepted_risk_review={bool(requires_accepted_risk_review)}; "
            f"live_make_check_status={live_make_check_status}"
        ),
    }


def _closeout_decision_gate(closeout_input: dict[str, Any]) -> dict[str, Any]:
    load_status = str(closeout_input.get("load_status", "unknown")).strip() or "unknown"
    state = (
        str(
            closeout_input.get("release_readiness_state", RELEASE_STATE_BLOCKED)
        ).strip()
        or RELEASE_STATE_BLOCKED
    )
    machine_release_allowed = bool(closeout_input.get("machine_release_allowed"))
    operator_release_allowed = bool(closeout_input.get("operator_release_allowed"))
    requires_accepted_risk_review = bool(
        closeout_input.get("requires_accepted_risk_review")
    )
    summary = str(closeout_input.get("summary", "")).strip()
    release_authority_status = str(
        closeout_input.get("release_authority_status", state)
    ).strip() or state
    sealed_release_status = str(
        closeout_input.get("sealed_release_status", "unknown")
    ).strip() or "unknown"

    if load_status != "ok":
        checked_in_state = "fail"
        live_rerun_state = {
            "status": "fail",
            "reason": f"release closeout load_status={load_status}",
        }
        claim_label = "diagnostic_workspace_only"
        next_action = (
            "Regenerate the release closeout summary before relying on the dashboard."
        )
    elif machine_release_allowed:
        checked_in_state = "pass"
        live_rerun_state = {
            "status": "pass",
            "reason": "release closeout machine gate allows release",
        }
        claim_label = "checked_in_json_confirmed"
        next_action = "none"
    elif operator_release_allowed and requires_accepted_risk_review:
        checked_in_state = "attention"
        live_rerun_state = {
            "status": "attention",
            "reason": "release closeout requires accepted-risk operator review before release",
        }
        claim_label = "checked_in_json_confirmed"
        next_action = "Review accepted_risks before operator release signoff."
    else:
        checked_in_state = "fail"
        live_rerun_state = {
            "status": "fail",
            "reason": summary or f"release closeout state is {state}",
        }
        claim_label = "checked_in_json_confirmed"
        next_action = "Resolve release closeout blockers before release."

    return {
        "gate_id": "release_closeout_decision",
        "source_path": CLOSEOUT_PATH,
        "checked_in_state": checked_in_state,
        "live_rerun_state": live_rerun_state,
        "authoritative_for_release": load_status == "ok" and machine_release_allowed,
        "accepted_risk": {"count": 0, "codes": []},
        "owner": "runtime-maintainer",
        "expiry": "",
        "next_action": next_action,
        "required_evidence": [next_action] if next_action != "none" else [],
        "claims": [
            {
                "claim": (
                    "release closeout authoritative decision is "
                    f"release_authority_status={release_authority_status}; "
                    f"sealed_release_status={sealed_release_status}"
                ),
                "provenance_label": claim_label,
            },
            {
                "claim": (
                    "release closeout machine/operator decision is "
                    f"machine_release_allowed={machine_release_allowed}, "
                    f"operator_release_allowed={operator_release_allowed}, "
                    f"requires_accepted_risk_review={requires_accepted_risk_review}"
                ),
                "provenance_label": claim_label,
            },
        ],
    }


def _load_dashboard_reports(vault: Path) -> DashboardReports:
    closeout, closeout_load_status = _load(vault, CLOSEOUT_PATH)
    fixed_point, fixed_point_load_status = _load(vault, FIXED_POINT_PATH)
    cost_trend, cost_trend_load_status = _load(vault, FIXED_POINT_COST_TREND_PATH)
    revalidation, revalidation_load_status = _load(vault, SIGNOFF_REVALIDATION_PATH)
    freshness, freshness_load_status = _load(vault, ARTIFACT_FRESHNESS_PATH)
    learning_scoreboard, learning_scoreboard_load_status = _load(
        vault, LEARNING_DELTA_SCOREBOARD_PATH
    )
    return DashboardReports(
        closeout=closeout,
        closeout_load_status=closeout_load_status,
        fixed_point=fixed_point,
        fixed_point_load_status=fixed_point_load_status,
        cost_trend=cost_trend,
        cost_trend_load_status=cost_trend_load_status,
        revalidation=revalidation,
        revalidation_load_status=revalidation_load_status,
        freshness=freshness,
        freshness_load_status=freshness_load_status,
        learning_scoreboard=learning_scoreboard,
        learning_scoreboard_load_status=learning_scoreboard_load_status,
    )


def _dashboard_signals(vault: Path, reports: DashboardReports) -> DashboardSignals:
    return DashboardSignals(
        closeout_input=_closeout_input_status(
            reports.closeout, reports.closeout_load_status
        ),
        finalizer_duration=_finalizer_duration_signal(
            vault,
            reports.fixed_point,
            reports.fixed_point_load_status,
            reports.cost_trend,
            reports.cost_trend_load_status,
        ),
        learning_guard=_learning_delta_guard_summary(
            reports.learning_scoreboard,
            reports.learning_scoreboard_load_status,
        ),
    )


def _dashboard_gates(
    reports: DashboardReports,
    signals: DashboardSignals,
    *,
    current_fingerprint: str,
    generated_at: str,
) -> list[dict[str, Any]]:
    blockers = _issues_by_source(reports.closeout.get("blockers", []))
    risks = _issues_by_source(reports.closeout.get("accepted_risks", []))
    gates = [_closeout_decision_gate(signals.closeout_input)]
    gates.extend(
        _component_gate(
            component,
            blockers=blockers.get(str(component.get("name", "")), []),
            accepted_risks=risks.get(str(component.get("name", "")), []),
            current_fingerprint=current_fingerprint,
        )
        for component in reports.closeout.get("components", [])
        if isinstance(component, dict)
    )
    gates.extend(
        _test_failure_lane_gate(lane)
        for lane in reports.closeout.get("test_failure_lanes", [])
        if isinstance(lane, dict)
    )
    gates.append(
        _signoff_revalidation_gate(
            reports.revalidation, reports.revalidation_load_status
        )
    )
    advisory_gate = _advisory_lifecycle_gate(reports.closeout, generated_at=generated_at)
    if advisory_gate is not None:
        gates.append(advisory_gate)
    gates.append(_learning_delta_guard_gate(signals.learning_guard))
    return gates


def _required_input_fail_count(reports: DashboardReports) -> int:
    return sum(
        1
        for load_status in (
            reports.closeout_load_status,
            reports.freshness_load_status,
            reports.learning_scoreboard_load_status,
        )
        if load_status != "ok"
    )


def _accepted_risk_count(closeout: dict[str, Any]) -> int:
    summary = closeout.get("summary")
    count = int(
        summary.get("accepted_risk_instance_count", 0)
        if isinstance(summary, dict)
        else 0
    )
    if count == 0 and isinstance(closeout.get("accepted_risks"), list):
        return len(closeout.get("accepted_risks", []))
    return count


def _gate_fail_count(gates: list[dict[str, Any]]) -> int:
    return sum(
        1
        for gate in gates
        if gate["checked_in_state"] == "fail"
        or gate["live_rerun_state"]["status"] == "fail"
    )


def _gate_not_run_count(gates: list[dict[str, Any]]) -> int:
    return sum(1 for gate in gates if gate["live_rerun_state"]["status"] == "not_run")


def _gate_attention_count(gates: list[dict[str, Any]]) -> int:
    return sum(
        1
        for gate in gates
        if gate["checked_in_state"] == "attention"
        or gate["live_rerun_state"]["status"] == "attention"
    )


def _dashboard_status(
    *,
    fail_count: int,
    required_input_fail_count: int,
    not_run_count: int,
    gate_attention_count: int,
    budget_attention_count: int,
) -> str:
    if fail_count or required_input_fail_count:
        return "fail"
    if not_run_count or gate_attention_count or budget_attention_count:
        return "attention"
    return "pass"


def _dashboard_status_counts(
    reports: DashboardReports,
    signals: DashboardSignals,
    gates: list[dict[str, Any]],
) -> DashboardStatusCounts:
    required_input_fail_count = _required_input_fail_count(reports)
    fail_count = _gate_fail_count(gates)
    not_run_count = _gate_not_run_count(gates)
    gate_attention_count = _gate_attention_count(gates)
    budget_attention_count = (
        1 if signals.finalizer_duration["status"] == "attention" else 0
    )
    status = _dashboard_status(
        fail_count=fail_count,
        required_input_fail_count=required_input_fail_count,
        not_run_count=not_run_count,
        gate_attention_count=gate_attention_count,
        budget_attention_count=budget_attention_count,
    )
    return DashboardStatusCounts(
        required_input_fail_count=required_input_fail_count,
        fail_count=fail_count,
        not_run_count=not_run_count,
        accepted_risk_count=_accepted_risk_count(reports.closeout),
        gate_attention_count=gate_attention_count,
        budget_attention_count=budget_attention_count,
        status=status,
    )


def _dashboard_inputs_payload(
    reports: DashboardReports, signals: DashboardSignals
) -> dict[str, Any]:
    return {
        "release_closeout_summary": signals.closeout_input,
        "release_closeout_fixed_point": {
            "path": FIXED_POINT_PATH,
            "load_status": reports.fixed_point_load_status,
            "status": signals.finalizer_duration["fixed_point_report_status"],
            "converged": signals.finalizer_duration["converged"],
        },
        "release_closeout_fixed_point_cost_trend": {
            "path": FIXED_POINT_COST_TREND_PATH,
            "load_status": reports.cost_trend_load_status,
            "status": str(reports.cost_trend.get("status", "unknown")).strip()
            if reports.cost_trend_load_status == "ok"
            else "unknown",
        },
        "learning_readiness_signoff_revalidation": {
            "path": SIGNOFF_REVALIDATION_PATH,
            "load_status": reports.revalidation_load_status,
            "status": str(reports.revalidation.get("status", "")).strip(),
        },
        "artifact_freshness": _freshness_debt_summary(
            reports.freshness, reports.freshness_load_status
        ),
        "learning_delta_scoreboard": signals.learning_guard,
    }


def _accepted_risk_delta_payload(closeout: dict[str, Any]) -> dict[str, Any]:
    return closeout.get(
        "accepted_risk_delta",
        {
            "status": "no_previous_report",
            "previous_report_generated_at": "",
            "added_count": 0,
            "removed_count": 0,
            "unchanged_count": 0,
            "added": [],
            "removed": [],
            "unchanged": [],
            "summary": "No release closeout accepted-risk delta was available.",
        },
    )


def _dashboard_summary_payload(
    gates: list[dict[str, Any]],
    counts: DashboardStatusCounts,
    learning_guard: dict[str, Any],
) -> dict[str, Any]:
    return {
        "gate_count": len(gates),
        "authoritative_gate_count": sum(
            1 for gate in gates if gate["authoritative_for_release"]
        ),
        "checked_in_fail_count": sum(
            1 for gate in gates if gate["checked_in_state"] == "fail"
        ),
        "live_rerun_fail_count": sum(
            1 for gate in gates if gate["live_rerun_state"]["status"] == "fail"
        ),
        "live_rerun_not_run_count": counts.not_run_count,
        "accepted_risk_count": counts.accepted_risk_count,
        "gate_attention_count": counts.gate_attention_count,
        "required_input_fail_count": counts.required_input_fail_count,
        "learning_claim_guard_status": learning_guard["status"],
        "learning_claim_allowed": learning_guard["learning_claim_allowed"],
        "learning_likely": learning_guard["learning_likely"],
        "bounded_learning_claim_allowed": learning_guard[
            "bounded_learning_claim_allowed"
        ],
        "confirmed_learning_improvement_allowed": learning_guard[
            "confirmed_learning_improvement_allowed"
        ],
        "improvement_claim_status": learning_guard["improvement_claim_status"],
        "confirmed_learning_improvement_status": learning_guard[
            "confirmed_learning_improvement_status"
        ],
        "evidence_cohort_status": learning_guard["evidence_cohort_status"],
        "learning_claim_blocker_status": learning_guard["learning_claim_blocker_status"],
        "confirmed_blocking_predicate_ids": learning_guard[
            "confirmed_blocking_predicate_ids"
        ],
        "confirmed_evidence_summary": learning_guard["confirmed_evidence_summary"],
        "claim_level": learning_guard["claim_level"],
        "claim_scope": learning_guard["claim_scope"],
        "learning_claim_unlock_review_status": learning_guard[
            "learning_claim_unlock_review_status"
        ],
        "learning_claim_unlock_review_approved": learning_guard[
            "learning_claim_unlock_review_approved"
        ],
        "learning_claim_unlock_review_revocation_status": learning_guard[
            "learning_claim_unlock_review_revocation_status"
        ],
        "learning_claim_evidence_bundle_status": learning_guard[
            "learning_claim_evidence_bundle_status"
        ],
        "claim_wording_allowed": learning_guard["claim_wording_allowed"],
        "claim_wording_policy_status": learning_guard["claim_wording_policy_status"],
        "confirmed_wording_allowed": learning_guard["confirmed_wording_allowed"],
        "confirmed_wording_policy_status": learning_guard[
            "confirmed_wording_policy_status"
        ],
        "self_improvement_claim_model": learning_guard[
            "self_improvement_claim_model"
        ],
        "same_eval_reason_coverage_status": learning_guard[
            "same_eval_reason_coverage_status"
        ],
        "strict_secondary_improvement_coverage_status": learning_guard[
            "strict_secondary_improvement_coverage_status"
        ],
        "behavior_delta_digest_coverage_status": learning_guard[
            "behavior_delta_digest_coverage_status"
        ],
        "placeholder_audit_status": learning_guard["placeholder_audit_status"],
    }


def _dashboard_budget_signals(
    reports: DashboardReports, signals: DashboardSignals
) -> dict[str, Any]:
    return {
        "release_smoke_boundedness": _release_smoke_boundedness_signal(
            reports.closeout
        ),
        "fixed_point_finalizer_cost": signals.finalizer_duration,
    }


def _render_dashboard_report(inputs: DashboardRenderInputs) -> dict[str, Any]:
    return {
        **build_canonical_report_envelope(
            inputs.vault,
            generated_at=inputs.generated_at,
            artifact_kind="release_evidence_dashboard",
            producer=PRODUCER,
            source_command="python -m ops.scripts.release_evidence_dashboard --vault . --out ops/reports/release-evidence-dashboard.json",
            resolved_policy_path=inputs.resolved_policy_path,
            schema_path=RELEASE_EVIDENCE_DASHBOARD_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/release/release_evidence_dashboard.py",
                "ops/scripts/release/advisory_lifecycle_runtime.py",
                "ops/scripts/release/release_closeout_fixed_point.py",
                "ops/scripts/release/release_closeout_fixed_point_cost_trend.py",
                "ops/scripts/release/release_closeout_summary.py",
                "ops/scripts/core/artifact_freshness_runtime.py",
                "ops/scripts/learning/learning_delta_scoreboard.py",
            ],
            file_inputs={
                "release_closeout_summary": CLOSEOUT_PATH,
                "release_closeout_fixed_point": FIXED_POINT_PATH,
                "release_closeout_fixed_point_cost_trend": FIXED_POINT_COST_TREND_PATH,
                "learning_readiness_signoff_revalidation": SIGNOFF_REVALIDATION_PATH,
                "artifact_freshness": ARTIFACT_FRESHNESS_PATH,
                "learning_delta_scoreboard": LEARNING_DELTA_SCOREBOARD_PATH,
            },
            text_inputs={
                "current_source_tree_fingerprint": inputs.current_fingerprint
            },
        ),
        "vault": report_path(inputs.vault, inputs.vault),
        "policy": {
            "path": report_path(inputs.vault, inputs.resolved_policy_path),
            "version": inputs.policy.get("version"),
        },
        "status": inputs.status_counts.status,
        "source_tree_fingerprint_current": inputs.current_fingerprint,
        "inputs": _dashboard_inputs_payload(inputs.reports, inputs.signals),
        "budget_signals": _dashboard_budget_signals(inputs.reports, inputs.signals),
        "confirmed_evidence_summary": inputs.signals.learning_guard[
            "confirmed_evidence_summary"
        ],
        "accepted_risk_delta": _accepted_risk_delta_payload(inputs.reports.closeout),
        "summary": _dashboard_summary_payload(
            inputs.gates,
            inputs.status_counts,
            inputs.signals.learning_guard,
        ),
        "gates": inputs.gates,
    }


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    current_fingerprint = release_source_tree_fingerprint(vault)
    reports = _load_dashboard_reports(vault)
    signals = _dashboard_signals(vault, reports)
    gates = _dashboard_gates(
        reports,
        signals,
        current_fingerprint=current_fingerprint,
        generated_at=generated_at,
    )
    status_counts = _dashboard_status_counts(reports, signals, gates)
    return _render_dashboard_report(
        DashboardRenderInputs(
            vault=vault,
            policy=policy,
            resolved_policy_path=resolved_policy_path,
            generated_at=generated_at,
            current_fingerprint=current_fingerprint,
            reports=reports,
            signals=signals,
            gates=gates,
            status_counts=status_counts,
        )
    )


def write_report(vault: Path, report: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=RELEASE_EVIDENCE_DASHBOARD_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release evidence dashboard schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a release evidence dashboard from closeout reports"
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Write dashboard output and exit zero even when dashboard status is fail.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, policy_path=args.policy_path)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    if args.no_fail:
        return 0
    return 0 if report["status"] in {"pass", "attention"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
