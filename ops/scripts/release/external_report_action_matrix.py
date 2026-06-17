#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.core.gate_effect_vocabulary import (
        GATE_EFFECT_NONE,
        GATE_EFFECTS,
        strongest_gate_effect,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.release.external_report_action_catalog import (
        ACTION_CATALOG,
        SPRINT_PRIORITIES,
    )
    from ops.scripts.release.external_report_inventory_runtime import (
        REFERENCE_MANIFEST,
        active_report_paths,
        archived_report_count,
        archived_report_paths,
        reference_manifest_alignment,
    )
    from ops.scripts.release.external_report_lifecycle_runtime import (
        action_status_reason_details,
        action_status_reason_ids,
        archive_reconciliation_observation_inventory,
        archive_reconciliation_observation_paths,
        archived_report_action_basis_records,
        canonical_artifact_freshness_state,
        coverage_with_action_basis,
        external_report_action_lifecycle_record,
        external_report_action_lifecycle_summary,
        report_coverage_item,
        status_from_evidence,
    )
else:
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.core.gate_effect_vocabulary import (
        GATE_EFFECT_NONE,
        GATE_EFFECTS,
        strongest_gate_effect,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext

    from .external_report_action_catalog import ACTION_CATALOG, SPRINT_PRIORITIES
    from .external_report_inventory_runtime import (
        REFERENCE_MANIFEST,
        active_report_paths,
        archived_report_count,
        archived_report_paths,
        reference_manifest_alignment,
    )
    from .external_report_lifecycle_runtime import (
        action_status_reason_details,
        action_status_reason_ids,
        archive_reconciliation_observation_inventory,
        archive_reconciliation_observation_paths,
        archived_report_action_basis_records,
        canonical_artifact_freshness_state,
        coverage_with_action_basis,
        external_report_action_lifecycle_record,
        external_report_action_lifecycle_summary,
        report_coverage_item,
        status_from_evidence,
    )


DEFAULT_OUT = "ops/reports/external-report-action-matrix.json"
PRODUCER = "ops.scripts.external_report_action_matrix"
SCHEMA_PATH = "ops/schemas/external-report-action-matrix.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.external_report_action_matrix --vault ."
SOURCE_ACTION_STATUSES = ("implemented", "partially_automated", "planned")
VERIFICATION_READINESS_STATUSES = (
    "ready",
    "release_run_pending",
    "promotion_readiness_pending",
    "operator_pending",
    "certificate_pending",
    "certificate_noncertifiable",
    "artifact_freshness_pending",
    "readback_pending",
    "source_action_required",
)
AUTHORITY_OR_OPERATOR_READINESS_STATUSES = (
    "release_run_pending",
    "promotion_readiness_pending",
    "operator_pending",
    "certificate_pending",
    "certificate_noncertifiable",
    "readback_pending",
)


def _verification_readiness_status(
    *,
    current_status: str,
    status_reason_ids: list[str],
    status_reason_details: list[dict[str, Any]],
) -> str:
    if current_status == "implemented":
        return "ready"
    scopes = {
        str(detail.get("blocking_scope", "")).strip()
        for detail in status_reason_details
        if isinstance(detail, dict) and str(detail.get("blocking_scope", "")).strip()
    }
    gate_effects = {
        str(detail.get("gate_effect", "")).strip()
        for detail in status_reason_details
        if isinstance(detail, dict) and str(detail.get("gate_effect", "")).strip()
    }
    reason_text = " ".join(status_reason_ids)
    if "goal_runtime_status" in scopes:
        return "certificate_pending"
    if "unattended_promotion" in scopes and any(
        reason.startswith("goal_runtime_") for reason in status_reason_ids
    ):
        if any(
            token in reason_text
            for token in (
                "failure_budget_exhausted",
                "noncertifiable",
                "closed_failure",
                "quarantined",
            )
        ):
            return "certificate_noncertifiable"
        return "certificate_pending"
    if (
        "supply_chain_external_verification" in scopes
        or "github_live_governance" in scopes
        or "operator_review_required" in gate_effects
    ):
        return "operator_pending"
    if scopes.intersection({"release_run", "sealed_release"}):
        return "release_run_pending"
    if "unattended_promotion" in scopes:
        return "promotion_readiness_pending"
    if "artifact_freshness" in scopes:
        return "artifact_freshness_pending"
    if "release_preseal" in scopes:
        return "readback_pending"
    if current_status == "requires_release_run_verification":
        return "readback_pending"
    return "source_action_required"


def _source_action_status(current_status: str, verification_readiness_status: str) -> str:
    if current_status == "implemented" or verification_readiness_status != "source_action_required":
        return "implemented"
    if current_status == "planned":
        return "planned"
    return "partially_automated"


def _reason_detail_summary(
    details: list[dict[str, Any]],
) -> dict[str, Any]:
    scopes = sorted(
        {
            str(detail.get("blocking_scope", "")).strip()
            for detail in details
            if str(detail.get("blocking_scope", "")).strip()
        }
    )
    effects = {
        str(detail.get("gate_effect", "")).strip()
        for detail in details
        if str(detail.get("gate_effect", "")).strip()
    }
    ordered_effects = [effect for effect in GATE_EFFECTS if effect in effects]
    return {
        "blocking_scopes": scopes,
        "gate_effects": ordered_effects,
        "strongest_gate_effect": strongest_gate_effect(ordered_effects)
        if ordered_effects
        else GATE_EFFECT_NONE,
    }


def _action_items(vault: Path, coverage: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_by_action: dict[str, list[str]] = {str(action["action_id"]): [] for action in ACTION_CATALOG}
    for item in coverage:
        for action_id in item["matched_action_ids"]:
            source_by_action.setdefault(str(action_id), []).append(str(item["path"]))
    action_items: list[dict[str, Any]] = []
    for action in ACTION_CATALOG:
        status, evidence = status_from_evidence(vault, action)
        action_id = str(action["action_id"])
        existing_count = sum(1 for item in evidence if item["exists"])
        status_reason_ids = action_status_reason_ids(
            vault,
            action_id,
            status,
            evidence,
            existing_count=existing_count,
            expected_count=len(evidence),
        )
        status_reason_details = action_status_reason_details(
            status_reason_ids,
            fallback_target=str(action["recommended_target"]),
        )
        status_reason_details = _enrich_action_status_reason_details(
            vault,
            action_id=action_id,
            status_reason_details=status_reason_details,
        )
        reason_detail_summary = _reason_detail_summary(status_reason_details)
        verification_readiness_status = _verification_readiness_status(
            current_status=status,
            status_reason_ids=status_reason_ids,
            status_reason_details=status_reason_details,
        )
        source_action_status = _source_action_status(status, verification_readiness_status)
        sprint_priority = SPRINT_PRIORITIES.get(action_id)
        item = {
            "action_id": action_id,
            "priority": action["priority"],
            "theme": action["theme"],
            "current_status": status,
            "source_action_status": source_action_status,
            "verification_readiness_status": verification_readiness_status,
            "status_reason_ids": status_reason_ids,
            "status_reason_details": status_reason_details,
            **reason_detail_summary,
            "source_report_paths": sorted(set(source_by_action[action_id])),
            "recommended_target": _recommended_target(
                str(action["recommended_target"]),
                status_reason_details,
            ),
            "evidence": evidence,
        }
        if sprint_priority:
            item["sprint_priority"] = sprint_priority
        item.update(external_report_action_lifecycle_record(item))
        action_items.append(item)
    return action_items


def _enrich_action_status_reason_details(
    vault: Path,
    *,
    action_id: str,
    status_reason_details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if action_id != "artifact_freshness_performance_observability":
        return status_reason_details
    source_identity_targets = _artifact_freshness_source_identity_targets(vault)
    if not source_identity_targets:
        return status_reason_details

    enriched: list[dict[str, Any]] = []
    for detail in status_reason_details:
        if detail.get("reason_id") != "artifact_freshness_source_identity_resettle":
            enriched.append(detail)
            continue
        current_targets = detail.get("recommended_targets")
        merged_targets = _dedupe_preserve_order(
            [
                *(current_targets if isinstance(current_targets, list) else []),
                *source_identity_targets,
            ]
        )
        enriched.append({**detail, "recommended_targets": merged_targets})
    return enriched


def _artifact_freshness_source_identity_targets(vault: Path) -> list[str]:
    try:
        payload = json.loads(
            (vault / "ops/reports/artifact-freshness-report.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    stale_routing = payload.get("stale_routing")
    if not isinstance(stale_routing, dict):
        return []
    if stale_routing.get("classification") != "source_identity_only":
        return []

    targets: list[str] = []
    targets.extend(_string_items(stale_routing.get("recommended_targets")))
    owner_routes = stale_routing.get("source_identity_owner_routes")
    if isinstance(owner_routes, list):
        for route in owner_routes:
            if not isinstance(route, dict):
                continue
            targets.extend(_string_items(route.get("recommended_targets")))
    return _dedupe_preserve_order(targets)


def _string_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _recommended_target(
    fallback_target: str,
    status_reason_details: list[dict[str, Any]],
) -> str:
    """Prefer the current blocker owner over the static catalog target."""
    for detail in status_reason_details:
        targets = detail.get("recommended_targets")
        if not isinstance(targets, list):
            continue
        for target in targets:
            if not isinstance(target, str) or not target:
                continue
            if (
                target.endswith(("-check", "-plan-check", "-plan"))
            ):
                continue
            return target
    for detail in status_reason_details:
        targets = detail.get("recommended_targets")
        if isinstance(targets, list):
            for target in targets:
                if isinstance(target, str) and target:
                    return target
    return fallback_target


def _report_coverage(vault: Path, paths: list[Path]) -> list[dict[str, Any]]:
    return [report_coverage_item(vault, path) for path in paths]


def _active_action_resolution_summary(actions: list[dict[str, Any]]) -> dict[str, Any]:
    active_by_readiness: dict[str, list[str]] = {}
    active_actions: list[dict[str, Any]] = []
    for action in actions:
        if not action.get("is_active"):
            continue
        active_actions.append(action)
        action_id = str(action.get("action_id", "")).strip()
        readiness = str(action.get("verification_readiness_status", "")).strip()
        if not action_id or not readiness:
            continue
        active_by_readiness.setdefault(readiness, []).append(action_id)

    for action_ids in active_by_readiness.values():
        action_ids.sort()

    source_action_required_count = len(active_by_readiness.get("source_action_required", []))
    artifact_freshness_pending_count = len(
        active_by_readiness.get("artifact_freshness_pending", [])
    )
    release_or_operator_pending_count = sum(
        len(active_by_readiness.get(status, []))
        for status in AUTHORITY_OR_OPERATOR_READINESS_STATUSES
    )
    if source_action_required_count:
        status = "source_action_available"
        recommended_lane = "source-action"
    elif artifact_freshness_pending_count:
        status = "artifact_freshness_pending"
        recommended_lane = _active_recommended_targets(
            active_actions,
            readiness_status="artifact_freshness_pending",
            fallback="artifact-freshness",
        )[0]
    elif release_or_operator_pending_count:
        status = "release_or_operator_authority_required"
        recommended_lane = "release-or-operator-authority"
    else:
        status = "no_active_blockers"
        recommended_lane = "none"
    if artifact_freshness_pending_count:
        recommended_targets = _active_recommended_targets(
            active_actions,
            readiness_status="artifact_freshness_pending",
            fallback=recommended_lane,
        )
    elif source_action_required_count:
        recommended_targets = _active_recommended_targets(
            active_actions,
            readiness_status="source_action_required",
            fallback=recommended_lane,
        )
    elif release_or_operator_pending_count:
        recommended_targets = _active_recommended_targets_for_statuses(
            active_actions,
            readiness_statuses=AUTHORITY_OR_OPERATOR_READINESS_STATUSES,
            fallback=recommended_lane,
        )
    else:
        recommended_targets = [recommended_lane]

    return {
        "status": status,
        "code_action_available": source_action_required_count > 0,
        "recommended_lane": recommended_lane,
        "recommended_targets": recommended_targets,
        "source_action_required_count": source_action_required_count,
        "artifact_freshness_pending_count": artifact_freshness_pending_count,
        "release_or_operator_pending_count": release_or_operator_pending_count,
        "active_action_ids_by_verification_readiness_status": active_by_readiness,
    }


def _active_recommended_targets(
    actions: list[dict[str, Any]],
    *,
    readiness_status: str,
    fallback: str,
) -> list[str]:
    return _active_recommended_targets_for_statuses(
        actions,
        readiness_statuses=(readiness_status,),
        fallback=fallback,
    )


def _active_recommended_targets_for_statuses(
    actions: list[dict[str, Any]],
    *,
    readiness_statuses: tuple[str, ...],
    fallback: str,
) -> list[str]:
    selected_statuses = {status for status in readiness_statuses if status}
    targets: list[str] = []
    for action in actions:
        readiness = str(action.get("verification_readiness_status", "")).strip()
        if readiness not in selected_statuses:
            continue
        target = str(action.get("recommended_target", "")).strip()
        if target:
            targets.append(target)
        for detail in action.get("status_reason_details", []):
            if not isinstance(detail, dict):
                continue
            targets.extend(_string_items(detail.get("recommended_targets")))
    deduped = _dedupe_preserve_order(targets)
    return deduped or [fallback]


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _summary(
    *,
    coverage: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    archived_report_count: int,
    manifest_alignment: dict[str, Any],
    canonical_artifact_freshness_state_record: dict[str, Any],
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    source_action_status_counts: dict[str, int] = dict.fromkeys(SOURCE_ACTION_STATUSES, 0)
    verification_readiness_status_counts: dict[str, int] = dict.fromkeys(
        VERIFICATION_READINESS_STATUSES,
        0,
    )
    gate_effect_action_counts: dict[str, int] = dict.fromkeys(GATE_EFFECTS, 0)
    blocking_scope_action_counts: dict[str, int] = {}
    sprint_backlog: dict[str, int] = {"P0": 0, "P1": 0, "P2": 0}
    for action in actions:
        status = str(action["current_status"])
        status_counts[status] = status_counts.get(status, 0) + 1
        source_action_status = str(action.get("source_action_status", "")).strip()
        if source_action_status not in source_action_status_counts:
            source_action_status_counts[source_action_status] = 0
        source_action_status_counts[source_action_status] += 1
        verification_readiness_status = str(
            action.get("verification_readiness_status", "")
        ).strip()
        if verification_readiness_status not in verification_readiness_status_counts:
            verification_readiness_status_counts[verification_readiness_status] = 0
        verification_readiness_status_counts[verification_readiness_status] += 1
        strongest_effect = str(action.get("strongest_gate_effect", GATE_EFFECT_NONE)).strip()
        if strongest_effect not in gate_effect_action_counts:
            gate_effect_action_counts[strongest_effect] = 0
        gate_effect_action_counts[strongest_effect] += 1
        for scope in action.get("blocking_scopes", []):
            if not isinstance(scope, str) or not scope:
                continue
            blocking_scope_action_counts[scope] = blocking_scope_action_counts.get(scope, 0) + 1
        sprint_priority = action.get("sprint_priority")
        if sprint_priority and sprint_priority in sprint_backlog:
            sprint_backlog[sprint_priority] += 1
    lifecycle_summary = external_report_action_lifecycle_summary(
        actions,
        canonical_artifact_freshness_state_record=canonical_artifact_freshness_state_record,
    )
    return {
        "active_report_count": len(coverage),
        "archived_report_count": archived_report_count,
        "action_item_count": len(actions),
        "implemented_count": status_counts.get("implemented", 0),
        "partially_automated_count": status_counts.get("partially_automated", 0),
        "requires_release_run_verification_count": status_counts.get("requires_release_run_verification", 0),
        "planned_count": status_counts.get("planned", 0),
        "source_action_status_counts": source_action_status_counts,
        "verification_readiness_status_counts": verification_readiness_status_counts,
        "unresolved_source_action_count": sum(
            1 for action in actions if action.get("source_action_status") != "implemented"
        ),
        "verification_readiness_pending_count": sum(
            1 for action in actions if action.get("verification_readiness_status") != "ready"
        ),
        "gate_effect_action_counts": gate_effect_action_counts,
        "blocking_scope_action_counts": blocking_scope_action_counts,
        "unmatched_active_report_count": sum(
            1 for item in coverage if int(item["matched_action_count"]) == 0
        ),
        "reference_manifest_alignment_status": manifest_alignment["status"],
        "reference_manifest_missing_active_report_count": len(
            manifest_alignment["missing_active_report_paths"]
        ),
        "reference_manifest_stale_reference_count": len(manifest_alignment["stale_reference_paths"]),
        "sprint_backlog": sprint_backlog,
        "active_action_resolution_summary": _active_action_resolution_summary(actions),
        **lifecycle_summary,
    }


def _stabilize_self_evidence(actions: list[dict[str, Any]], *, status: str) -> None:
    for action in actions:
        for evidence in action.get("evidence", []):
            if not isinstance(evidence, dict):
                continue
            if evidence.get("path") == DEFAULT_OUT:
                evidence["status"] = status
                evidence["producer"] = PRODUCER


def build_report(
    vault: Path,
    *,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    policy, resolved_policy_path = load_policy(resolved_vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    report_paths = active_report_paths(resolved_vault)
    archive_paths = archived_report_paths(resolved_vault)
    coverage = _report_coverage(resolved_vault, report_paths)
    actions = _action_items(resolved_vault, coverage)
    statuses = {
        str(action["action_id"]): str(action["current_status"])
        for action in actions
    }
    coverage = coverage_with_action_basis(coverage, statuses)
    archived_report_action_basis = archived_report_action_basis_records(
        resolved_vault,
        statuses,
    )
    manifest_alignment = reference_manifest_alignment(resolved_vault)
    canonical_artifact_freshness_state_record = canonical_artifact_freshness_state(resolved_vault)
    summary = _summary(
        coverage=coverage,
        actions=actions,
        archived_report_count=archived_report_count(resolved_vault),
        manifest_alignment=manifest_alignment,
        canonical_artifact_freshness_state_record=canonical_artifact_freshness_state_record,
    )
    status = (
        "attention"
        if (
            summary["planned_count"]
            or summary["partially_automated_count"]
            or summary["requires_release_run_verification_count"]
            or summary["unmatched_active_report_count"]
            or summary["reference_manifest_alignment_status"] != "current"
        )
        else "pass"
    )
    _stabilize_self_evidence(actions, status=status)
    return {
        **build_canonical_report_envelope(
            resolved_vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="external_report_action_matrix",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/release/external_report_action_matrix.py",
                "ops/scripts/release/external_report_action_catalog.py",
                "ops/scripts/release/external_report_inventory_runtime.py",
                "ops/scripts/release/external_report_lifecycle_runtime.py",
                "ops/scripts/release/external_report_reference_manifest.py",
            ],
            file_inputs={
                "external_report_reference_manifest": REFERENCE_MANIFEST,
            },
            path_group_inputs={
                "active_external_reports": [report_path(resolved_vault, path) for path in report_paths],
                "archived_external_reports": [
                    report_path(resolved_vault, path) for path in archive_paths
                ],
                "archive_reconciliation_observation_paths": archive_reconciliation_observation_paths(
                    resolved_vault
                ),
            },
            text_inputs={
                "archive_reconciliation_observations": json.dumps(
                    archive_reconciliation_observation_inventory(resolved_vault),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "action_catalog": json.dumps(ACTION_CATALOG, ensure_ascii=False, sort_keys=True),
            },
        ),
        "vault": report_path(resolved_vault, resolved_vault),
        "status": status,
        "policy": {
            "path": report_path(resolved_vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "summary": summary,
        "reference_manifest_alignment": manifest_alignment,
        "active_report_coverage": coverage,
        "archived_report_action_basis": archived_report_action_basis,
        "action_items": actions,
        "archive_policy": {
            "active_root": "external-reports",
            "archive_root": "external-reports/archive",
            "reference_manifest": REFERENCE_MANIFEST,
            "archive_excluded_from_action_matching": True,
        },
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="external report action matrix schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a lifecycle/action matrix for non-archived external reports.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, context=None, policy_path=args.policy_path)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
