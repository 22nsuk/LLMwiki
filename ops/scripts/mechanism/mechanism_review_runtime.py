from __future__ import annotations

from pathlib import Path

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from .mechanism_review_candidate_runtime import (
    apply_historical_calibration,
    bootstrap_diagnostics,
    build_candidate_for_history,
    candidate_requirements_by_type,
    candidate_slug,
    candidate_template,
    clamp_priority,
    family_spec,
    format_threshold_ratio,
    historical_calibration_summary,
    non_trigger_detail,
    non_trigger_diagnostics,
    sorted_run_ids,
    trend_candidate_requirements_for_policy,
)
from .mechanism_review_candidate_runtime import (
    build_candidates as build_review_candidates,
)
from .mechanism_review_history_runtime import (
    MechanismRunSnapshot,
    group_snapshots_by_targets,
    load_artifact,
    load_mechanism_run_snapshots,
    load_optional_json,
    read_json,
)
from .mechanism_review_outcome_metrics_calibration_runtime import (
    build_outcome_metrics_calibration_diagnostics,
)
from .mechanism_review_session_calibration_runtime import (
    accumulate_session_calibration_diagnostics,
    any_positive_counter_value,
    apply_session_calibration,
    build_session_calibration_diagnostics,
    counter_has_positive_value,
    empty_session_calibration_diagnostics_entry,
    session_calibration_summary,
    session_report_for_run,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import report_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import (
    EVAL_REPORT_SCHEMA_PATH,
    MECHANISM_ASSESSMENT_SCHEMA_PATH,
    MECHANISM_REVIEW_SCHEMA_PATH,
    PROMOTION_REPORT_SCHEMA_PATH,
)
from ops.scripts.schema_runtime import load_schema_with_vault_override, validate_with_schema

PROMOTION_REPORT_SCHEMA = PROMOTION_REPORT_SCHEMA_PATH
MECHANISM_ASSESSMENT_SCHEMA = MECHANISM_ASSESSMENT_SCHEMA_PATH
EVAL_REPORT_SCHEMA = EVAL_REPORT_SCHEMA_PATH
MECHANISM_REVIEW_SCHEMA = MECHANISM_REVIEW_SCHEMA_PATH
PRODUCER = "ops.scripts.mechanism_review_runtime"
SOURCE_COMMAND = "python -m ops.scripts.mechanism_review"


__all__ = [
    "EVAL_REPORT_SCHEMA",
    "MECHANISM_ASSESSMENT_SCHEMA",
    "MECHANISM_REVIEW_SCHEMA",
    "PROMOTION_REPORT_SCHEMA",
    "build_candidates",
    "build_report",
]


_read_json = read_json
_load_optional_json = load_optional_json
_load_artifact = load_artifact
_load_mechanism_run_snapshots = load_mechanism_run_snapshots
_group_snapshots_by_targets = group_snapshots_by_targets

_sorted_run_ids = sorted_run_ids
_candidate_slug = candidate_slug
_clamp_priority = clamp_priority
_family_spec = family_spec
_candidate_template = candidate_template
_trend_candidate_requirements = trend_candidate_requirements_for_policy
_candidate_requirements_by_type = candidate_requirements_by_type
_format_threshold_ratio = format_threshold_ratio
_non_trigger_detail = non_trigger_detail
_non_trigger_diagnostics = non_trigger_diagnostics
_bootstrap_diagnostics = bootstrap_diagnostics
_build_candidate_for_history = build_candidate_for_history
_historical_calibration_summary = historical_calibration_summary
_apply_historical_calibration = apply_historical_calibration
_counter_has_positive_value = counter_has_positive_value
_any_positive_counter_value = any_positive_counter_value
_empty_session_calibration_diagnostics_entry = empty_session_calibration_diagnostics_entry
_accumulate_session_calibration_diagnostics = accumulate_session_calibration_diagnostics
_build_session_calibration_diagnostics = build_session_calibration_diagnostics
_build_outcome_metrics_calibration_diagnostics = build_outcome_metrics_calibration_diagnostics


def _session_report_for_run(
    vault: Path,
    run_id: str,
    cache: dict[str, dict | None],
    run_cache: dict[str, tuple[str, dict | None]],
) -> tuple[str, dict | None]:
    return session_report_for_run(
        vault,
        run_id,
        cache,
        run_cache,
        load_optional_json_func=_load_optional_json,
    )


def _session_calibration_summary(
    vault: Path,
    policy: dict,
    candidate: dict,
    session_report_cache: dict[str, dict | None],
    run_session_cache: dict[str, tuple[str, dict | None]],
) -> dict:
    return session_calibration_summary(
        vault,
        policy,
        candidate,
        session_report_cache,
        run_session_cache,
        load_optional_json_func=_load_optional_json,
    )


def _apply_session_calibration(
    vault: Path,
    policy: dict,
    candidate: dict,
    session_report_cache: dict[str, dict | None],
    run_session_cache: dict[str, tuple[str, dict | None]],
) -> dict:
    return apply_session_calibration(
        vault,
        policy,
        candidate,
        session_report_cache,
        run_session_cache,
        load_optional_json_func=_load_optional_json,
    )


def build_candidates(vault: Path, policy: dict, snapshots: list[MechanismRunSnapshot]) -> list[dict]:
    return build_review_candidates(
        vault,
        policy,
        snapshots,
        load_optional_json_func=_load_optional_json,
    )


def _report_status(*, enabled: bool, bootstrap: dict, candidates: list[dict]) -> str:
    if not enabled:
        return "attention"
    if str(bootstrap.get("status", "")).strip() != "ready":
        return "attention"
    if not candidates:
        return "attention"
    return "pass"


def _candidate_blocker(
    *,
    blocker_type: str,
    reason: str,
    detail: str,
    source: str,
    candidate_type: str | None = None,
    primary_targets: list[str] | None = None,
    run_id: str | None = None,
    path: str | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "blocker_type": blocker_type,
        "reason": reason,
        "detail": detail,
        "source": source,
    }
    if candidate_type:
        item["candidate_type"] = candidate_type
    if primary_targets:
        item["primary_targets"] = primary_targets
    if run_id:
        item["run_id"] = run_id
    if path:
        item["path"] = path
    return item


def _schema_blockers(skipped_runs: list[dict]) -> list[dict]:
    blockers: list[dict] = []
    for item in skipped_runs:
        reason = str(item.get("reason", "")).strip()
        if reason not in {
            "promotion_report_invalid_json",
            "promotion_report_schema_invalid",
            "promotion_report_missing_input",
            "run_artifact_invalid",
        }:
            continue
        blockers.append(
            _candidate_blocker(
                blocker_type="schema",
                reason=reason,
                detail=str(item.get("detail", "")).strip() or reason,
                source="skipped_runs",
                run_id=str(item.get("run_id", "")).strip() or None,
                path=str(item.get("path", "")).strip() or None,
            )
        )
    return blockers


def _history_blockers(bootstrap: dict, excluded_runs: list[dict]) -> list[dict]:
    blockers: list[dict] = []
    bootstrap_status = str(bootstrap.get("status", "")).strip()
    if bootstrap_status == "no_history":
        blockers.append(
            _candidate_blocker(
                blocker_type="history",
                reason="no_history",
                detail=str(bootstrap.get("summary", "")).strip() or "no comparable run history",
                source="bootstrap",
            )
        )
    elif bootstrap_status == "bootstrap_history_insufficient":
        for group in bootstrap.get("target_groups_under_min_history", []):
            if not isinstance(group, dict):
                continue
            primary_targets = [
                str(target) for target in group.get("primary_targets", []) if str(target).strip()
            ]
            latest_run_id = str(group.get("latest_run_id", "")).strip() or None
            for blocked in group.get("blocked_candidate_types", []):
                if not isinstance(blocked, dict):
                    continue
                candidate_type = str(blocked.get("candidate_type", "")).strip()
                additional_runs_needed = int(blocked.get("additional_runs_needed", 0))
                detail = (
                    f"needs {additional_runs_needed} additional comparable run"
                    f"{'' if additional_runs_needed == 1 else 's'}"
                )
                blockers.append(
                    _candidate_blocker(
                        blocker_type="history",
                        reason="bootstrap_history_insufficient",
                        detail=detail,
                        source="bootstrap",
                        candidate_type=candidate_type or None,
                        primary_targets=primary_targets,
                        run_id=latest_run_id,
                    )
                )
    for item in excluded_runs:
        blockers.append(
            _candidate_blocker(
                blocker_type="history",
                reason=f"history_{str(item.get('status', '')).strip() or 'excluded'}",
                detail=str(item.get("reason", "")).strip() or "run excluded from active history",
                source="excluded_runs",
                run_id=str(item.get("run_id", "")).strip() or None,
                path=str(item.get("path", "")).strip() or None,
            )
        )
    return blockers


def _threshold_blockers(bootstrap: dict) -> list[dict]:
    blockers: list[dict] = []
    for group in bootstrap.get("non_trigger_diagnostics", []):
        if not isinstance(group, dict):
            continue
        primary_targets = [
            str(target) for target in group.get("primary_targets", []) if str(target).strip()
        ]
        latest_run_id = str(group.get("latest_run_id", "")).strip() or None
        for diagnostic in group.get("candidate_diagnostics", []):
            if not isinstance(diagnostic, dict):
                continue
            candidate_type = str(diagnostic.get("candidate_type", "")).strip()
            blockers.append(
                _candidate_blocker(
                    blocker_type="threshold",
                    reason="threshold_not_triggered",
                    detail=str(diagnostic.get("detail", "")).strip()
                    or "candidate thresholds were not triggered",
                    source="non_trigger_diagnostics",
                    candidate_type=candidate_type or None,
                    primary_targets=primary_targets,
                    run_id=latest_run_id,
                )
            )
    return blockers


def _calibration_blockers(session_calibration: dict, outcome_metrics_calibration: dict) -> list[dict]:
    blockers: list[dict] = []
    session_status = str(session_calibration.get("status", "")).strip()
    if session_status and session_status != "active":
        blockers.append(
            _candidate_blocker(
                blocker_type="session",
                reason=f"session_calibration_{session_status}",
                detail=f"session_calibration.status={session_status}",
                source="session_calibration",
            )
        )
    outcome_status = str(outcome_metrics_calibration.get("status", "")).strip()
    if outcome_status and outcome_status != "active":
        blockers.append(
            _candidate_blocker(
                blocker_type="outcome",
                reason=f"outcome_metrics_calibration_{outcome_status}",
                detail=f"outcome_metrics_calibration.status={outcome_status}",
                source="outcome_metrics_calibration",
            )
        )
    for gap in outcome_metrics_calibration.get("evidence_gaps", []):
        text = str(gap).strip()
        if not text:
            continue
        blockers.append(
            _candidate_blocker(
                blocker_type="outcome",
                reason="outcome_metrics_evidence_gap",
                detail=text,
                source="outcome_metrics_calibration",
            )
        )
    return blockers


def _candidate_blockers(
    *,
    candidates: list[dict],
    skipped_runs: list[dict],
    excluded_runs: list[dict],
    bootstrap: dict,
    session_calibration: dict,
    outcome_metrics_calibration: dict,
) -> list[dict]:
    if candidates:
        return []
    blockers = [
        *_history_blockers(bootstrap, excluded_runs),
        *_threshold_blockers(bootstrap),
        *_schema_blockers(skipped_runs),
        *_calibration_blockers(session_calibration, outcome_metrics_calibration),
    ]
    if not blockers:
        blockers.append(
            _candidate_blocker(
                blocker_type="threshold",
                reason="candidate_queue_empty_without_specific_blocker",
                detail="candidates_emitted=0 but no specific mechanism review blocker was detected",
                source="mechanism_review",
            )
        )
    return blockers


def build_report(
    vault: Path,
    policy: dict,
    policy_path: Path,
    *,
    max_runs: int | None = None,
    max_candidates: int | None = None,
    context: RuntimeContext | None = None,
) -> dict:
    runtime_context = context or RuntimeContext.from_policy(policy)
    mechanism_policy = dict(policy["mechanism_review"])
    if max_runs is not None:
        mechanism_policy["max_runs"] = max_runs
    if max_candidates is not None:
        mechanism_policy["max_candidates"] = max_candidates
    effective_policy = dict(policy)
    effective_policy["mechanism_review"] = mechanism_policy

    snapshots, skipped_runs, excluded_runs, discovered = _load_mechanism_run_snapshots(
        vault,
        effective_policy,
        max_runs=mechanism_policy["max_runs"],
    )
    candidates = (
        build_candidates(vault, effective_policy, snapshots) if mechanism_policy["enabled"] else []
    )
    bootstrap = _bootstrap_diagnostics(effective_policy, snapshots, candidates)
    status = _report_status(
        enabled=bool(mechanism_policy["enabled"]),
        bootstrap=bootstrap,
        candidates=candidates,
    )
    session_calibration = _build_session_calibration_diagnostics(
        candidates,
        enabled=bool(mechanism_policy["calibration"]["enabled"]),
    )
    outcome_metrics_calibration = _build_outcome_metrics_calibration_diagnostics(
        vault,
        effective_policy,
        candidates,
        load_optional_json_func=_load_optional_json,
    )
    generated_at = runtime_context.isoformat_z()
    report = {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="mechanism_review_candidates_report",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=policy_path,
            schema_path=MECHANISM_REVIEW_SCHEMA,
            source_paths=["ops/scripts/mechanism_review_runtime.py"],
            path_group_inputs={
                "promotion_reports": sorted(snapshot.promotion_report_path for snapshot in snapshots),
                "excluded_promotion_reports": sorted(
                    item["path"] for item in excluded_runs if isinstance(item.get("path"), str)
                ),
                "skipped_artifacts": sorted(
                    item["path"] for item in skipped_runs if isinstance(item.get("path"), str)
                ),
            },
            text_inputs={
                "mechanism_review_enabled": str(bool(mechanism_policy["enabled"])),
                "mechanism_review_max_runs": str(mechanism_policy["max_runs"]),
                "mechanism_review_max_candidates": str(mechanism_policy["max_candidates"]),
            },
        ),
        "vault": display_path(vault, vault),
        "policy": {
            "path": report_path(vault, policy_path),
            "version": policy["version"],
        },
        "status": status,
        "summary": {
            "runs_discovered": discovered,
            "runs_considered": len(snapshots),
            "runs_excluded": len(excluded_runs),
            "runs_skipped": len(skipped_runs),
            "candidates_emitted": len(candidates),
        },
        "diagnostics": {
            "skipped_runs": skipped_runs,
            "excluded_runs": excluded_runs,
            "bootstrap": bootstrap,
            "session_calibration": session_calibration,
            "outcome_metrics_calibration": outcome_metrics_calibration,
            "candidate_blockers": _candidate_blockers(
                candidates=candidates,
                skipped_runs=skipped_runs,
                excluded_runs=excluded_runs,
                bootstrap=bootstrap,
                session_calibration=session_calibration,
                outcome_metrics_calibration=outcome_metrics_calibration,
            ),
        },
        "candidates": candidates,
    }
    schema = load_schema_with_vault_override(vault, MECHANISM_REVIEW_SCHEMA)
    errors = validate_with_schema(report, schema)
    if errors:
        raise ValueError(f"mechanism review report schema validation failed: {errors[0]}")
    return report
