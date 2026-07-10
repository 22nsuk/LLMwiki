#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
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
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_constants_runtime import (
        GENERATED_ARTIFACT_INDEX_SCHEMA_PATH,
    )
    from ops.scripts.core.source_revision_runtime import resolve_source_revision
    from ops.scripts.core.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
    from ops.scripts.mechanism.improvement_observations_runtime import (
        improvement_observation_paths,
    )
    from ops.scripts.release.external_report_action_matrix import (
        build_report as build_action_matrix_report,
    )
    from ops.scripts.release.external_report_inventory_runtime import (
        REFERENCE_MANIFEST,
        active_report_paths,
    )
    from ops.scripts.release.external_report_lifecycle_runtime import (
        action_statuses,
        archived_report_action_basis_records,
        content_lifecycle_inventory,
        lifecycle_decision,
        report_lifecycle_profiles,
    )
else:
    from ops.scripts.mechanism.improvement_observations_runtime import (
        improvement_observation_paths,
    )
    from ops.scripts.release.external_report_action_matrix import (
        build_report as build_action_matrix_report,
    )
    from ops.scripts.release.external_report_inventory_runtime import (
        REFERENCE_MANIFEST,
        active_report_paths,
    )
    from ops.scripts.release.external_report_lifecycle_runtime import (
        action_statuses,
        archived_report_action_basis_records,
        content_lifecycle_inventory,
        lifecycle_decision,
        report_lifecycle_profiles,
    )

    from .artifact_freshness_runtime import build_canonical_report_envelope
    from .artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from .output_runtime import display_path
    from .policy_runtime import load_policy, report_path
    from .runtime_context import RuntimeContext
    from .schema_constants_runtime import GENERATED_ARTIFACT_INDEX_SCHEMA_PATH
    from .source_revision_runtime import resolve_source_revision
    from .source_tree_fingerprint_runtime import release_source_tree_fingerprint


DEFAULT_OUT = "ops/reports/generated-artifact-index.json"
PRODUCER = "ops.scripts.generated_artifact_index"
EXTERNAL_REPORT_ACTION_MATRIX_PATH = "ops/reports/external-report-action-matrix.json"
SOURCE_COMMAND = (
    "python -m ops.scripts.generated_artifact_index "
    "--vault . "
    "--policy-path ops/policies/wiki-maintainer-policy.yaml"
)
COMPACT_YYYYMMDD_RE = re.compile(r"(?<!\d)(20\d{6})(?!\d)")
DASHED_YYYYMMDD_RE = re.compile(r"(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)")
COMPACT_YYMMDD_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
RUN_ID_DATE_RE = re.compile(r"run-(20\d{6})")
TASK_IMPROVEMENT_OBSERVATIONS_PREFIX = "ops/reports/task-improvement-observations/"
NON_SEALING_INDEX_REPORTS = {
    "ops/reports/archive-execution-manifest.json",
    "ops/reports/make-target-inventory.json",
    "ops/reports/release-closeout-batch-manifest.json",
    "ops/reports/release-evidence-closeout-self-check.json",
    "ops/reports/release-workflow-order-guard.json",
    "ops/reports/workflow-dependency-planner.json",
}


def tracking_policy() -> dict[str, Any]:
    return {
        "policy_id": "generated_artifact_tracking_policy",
        "commit_policy": (
            "Track decision-grade canonical_report artifacts in stable top-level namespaces; "
            "move superseded archive artifacts to archive namespaces; keep ephemeral run-local "
            "or dry-run outputs out of stable commit surfaces unless promoted by a schema-backed writer."
        ),
        "decision_grade_surfaces": [
            "ops/reports stable current reports",
            "ops/operator operator-only reports",
            "external-reports private reference manifest and active review reports",
            "runs active mechanism histories",
        ],
        "retention_classes": ["canonical_report", "archive", "ephemeral"],
        "archive_execution_target": "archive-execution-manifest",
    }


def _compact_date(value: str) -> str:
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"


def _short_date(value: str) -> str:
    return f"20{value[0:2]}-{value[2:4]}-{value[4:6]}"


def date_token(text: str) -> str:
    dashed = DASHED_YYYYMMDD_RE.search(text)
    if dashed is not None:
        return dashed.group(1)
    compact = COMPACT_YYYYMMDD_RE.search(text)
    if compact is not None:
        return _compact_date(compact.group(1))
    short = COMPACT_YYMMDD_RE.search(text)
    if short is not None:
        return _short_date(short.group(1))
    return ""


def _family_key(path: Path) -> str:
    stem = path.stem
    stem = DASHED_YYYYMMDD_RE.sub("", stem)
    stem = COMPACT_YYYYMMDD_RE.sub("", stem)
    stem = COMPACT_YYMMDD_RE.sub("", stem)
    stem = re.sub(r"^current[-_]+", "", stem)
    stem = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_").lower()
    return stem or path.stem.lower()


def _file_records(vault: Path, root_rel: str) -> list[dict[str, str]]:
    root = vault / root_rel
    if not root.exists():
        return []
    records = []
    for path in sorted(item for item in root.iterdir() if item.is_file()):
        records.append(
            {
                "path": report_path(vault, path),
                "family": _family_key(path),
                "date": date_token(path.name),
            }
        )
    return records


def _canonical_inventory_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _task_improvement_observation_reports(vault: Path) -> list[str]:
    return [
        path
        for path in improvement_observation_paths(vault)
        if path.startswith(TASK_IMPROVEMENT_OBSERVATIONS_PREFIX)
    ]


def _is_sealing_index_report(record: dict[str, str]) -> bool:
    return record["path"] != DEFAULT_OUT and record["path"] not in NON_SEALING_INDEX_REPORTS


def _ops_report_inventory(vault: Path) -> list[dict[str, str]]:
    return [record for record in _file_records(vault, "ops/reports") if _is_sealing_index_report(record)]


def _operator_report_inventory(vault: Path) -> list[dict[str, str]]:
    return _file_records(vault, "ops/operator")


def _external_root_report_records(vault: Path) -> list[dict[str, str]]:
    paths = active_report_paths(vault)
    reference_manifest = vault / REFERENCE_MANIFEST
    if reference_manifest.is_file():
        paths.append(reference_manifest)
    return [
        {
            "path": report_path(vault, path),
            "family": _family_key(path),
            "date": date_token(path.name),
        }
        for path in sorted(paths)
    ]


def _external_report_inventory(
    vault: Path,
    *,
    status_by_action: dict[str, str] | None = None,
    archived_report_basis: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    statuses = status_by_action or _external_report_lifecycle_statuses(vault)
    archived_basis = archived_report_basis
    if archived_basis is None:
        archived_basis = archived_report_action_basis_records(vault, statuses)
    return {
        "root_records": _external_root_report_records(vault),
        "content_lifecycle_profiles": content_lifecycle_inventory(vault),
        "archived_report_action_basis": archived_basis,
        "archive_file_count": len(archived_basis),
    }


def _action_matrix_basis_state(vault: Path) -> dict[str, Any]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(
        vault / EXTERNAL_REPORT_ACTION_MATRIX_PATH
    )
    current_revision = resolve_source_revision(vault).revision
    current_fingerprint = release_source_tree_fingerprint(vault)
    base = {
        "path": EXTERNAL_REPORT_ACTION_MATRIX_PATH,
        "status": "current",
        "reason_id": "action_matrix_basis_current",
        "source_revision": "",
        "source_tree_fingerprint": "",
        "current_source_revision": current_revision,
        "current_source_tree_fingerprint": current_fingerprint,
        "input_fingerprint_mismatch_keys": [],
    }
    if diagnostics.get("missing"):
        return {
            **base,
            "status": "missing",
            "reason_id": "action_matrix_missing",
        }
    if not isinstance(payload, dict):
        return {
            **base,
            "status": "unreadable",
            "reason_id": "action_matrix_unreadable",
        }
    source_revision = str(payload.get("source_revision", "")).strip()
    source_tree_fingerprint = str(payload.get("source_tree_fingerprint", "")).strip()
    base.update(
        {
            "source_revision": source_revision,
            "source_tree_fingerprint": source_tree_fingerprint,
        }
    )
    if payload.get("artifact_kind") != "external_report_action_matrix":
        return {
            **base,
            "status": "invalid",
            "reason_id": "action_matrix_wrong_artifact_kind",
        }
    if payload.get("artifact_status") != "current":
        return {
            **base,
            "status": "stale",
            "reason_id": "action_matrix_artifact_not_current",
        }
    if str(payload.get("currentness", {}).get("status", "")) != "current":
        return {
            **base,
            "status": "stale",
            "reason_id": "action_matrix_currentness_not_current",
        }
    if (
        not source_revision
        or not source_tree_fingerprint
        or source_revision != current_revision
        or source_tree_fingerprint != current_fingerprint
    ):
        return {
            **base,
            "status": "source_identity_mismatch",
            "reason_id": "action_matrix_source_identity_mismatch",
        }
    if not isinstance(payload.get("action_items"), list):
        return {
            **base,
            "status": "invalid",
            "reason_id": "action_matrix_action_items_invalid",
        }
    stored_fingerprints = payload.get("input_fingerprints")
    if not isinstance(stored_fingerprints, dict):
        return {
            **base,
            "status": "invalid",
            "reason_id": "action_matrix_input_fingerprints_invalid",
        }
    try:
        live_fingerprints = build_action_matrix_report(vault).get("input_fingerprints")
    except (OSError, TypeError, ValueError, RuntimeError):
        return {
            **base,
            "status": "stale",
            "reason_id": "action_matrix_input_fingerprints_unverifiable",
        }
    if not isinstance(live_fingerprints, dict):
        return {
            **base,
            "status": "stale",
            "reason_id": "action_matrix_input_fingerprints_unverifiable",
        }
    mismatch_keys = sorted(
        {
            str(key)
            for key in set(stored_fingerprints) | set(live_fingerprints)
            if stored_fingerprints.get(key) != live_fingerprints.get(key)
        }
    )
    if mismatch_keys:
        return {
            **base,
            "status": "stale",
            "reason_id": "action_matrix_input_fingerprint_mismatch",
            "input_fingerprint_mismatch_keys": mismatch_keys,
        }
    return base


def _action_matrix_statuses(
    vault: Path,
    *,
    basis_state: dict[str, Any] | None = None,
) -> dict[str, str]:
    basis = basis_state or _action_matrix_basis_state(vault)
    if basis.get("status") != "current":
        return {}
    payload, diagnostics = load_optional_json_object_with_diagnostics(
        vault / EXTERNAL_REPORT_ACTION_MATRIX_PATH
    )
    if diagnostics.get("missing") or not isinstance(payload, dict):
        return {}
    if payload.get("artifact_kind") != "external_report_action_matrix":
        return {}
    if payload.get("artifact_status") != "current":
        return {}
    if str(payload.get("currentness", {}).get("status", "")) != "current":
        return {}
    action_items = payload.get("action_items")
    if not isinstance(action_items, list):
        return {}
    statuses: dict[str, str] = {}
    for item in action_items:
        if not isinstance(item, dict):
            continue
        action_id = str(item.get("action_id", "")).strip()
        current_status = str(item.get("current_status", "")).strip()
        if action_id and current_status:
            statuses[action_id] = current_status
    return statuses


def _external_report_lifecycle_statuses(
    vault: Path,
    *,
    action_matrix_basis: dict[str, Any] | None = None,
) -> dict[str, str]:
    statuses = action_statuses(vault)
    statuses.update(_action_matrix_statuses(vault, basis_state=action_matrix_basis))
    return statuses


def _external_report_decision_fields(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_type": str(decision.get("report_type", "")),
        "content_sha256": str(decision.get("content_sha256", "")),
        "matched_action_ids": [str(action_id) for action_id in decision.get("matched_action_ids", [])],
        "matched_action_count": int(decision.get("matched_action_count") or 0),
        "unresolved_action_ids": [
            str(action_id) for action_id in decision.get("unresolved_action_ids", [])
        ],
        "unresolved_action_count": int(decision.get("unresolved_action_count") or 0),
        "unmatched_recommendation_count": int(
            decision.get("unmatched_recommendation_count") or 0
        ),
        "operator_only_rationale": str(decision.get("operator_only_rationale", "")),
        "archive_decision_code": str(decision.get("archive_decision_code", "")),
    }


def _external_report_decision_reason(decision: dict[str, Any]) -> str:
    reason = str(decision["reason"])
    unresolved_action_ids = [
        str(action_id) for action_id in decision.get("unresolved_action_ids", []) if str(action_id)
    ]
    if (
        unresolved_action_ids
        and "unique unresolved action themes not covered by another active report" in reason
    ):
        return (
            "External report remains active after structured action review: "
            f"{len(unresolved_action_ids)} unresolved action_id(s): "
            f"{', '.join(unresolved_action_ids)}."
        )
    if unresolved_action_ids and "no unique unresolved action themes" in reason:
        return (
            f"{reason} Remaining unresolved action_id(s): "
            f"{', '.join(unresolved_action_ids)}."
        )
    return reason


def _ops_reports(vault: Path) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int]]:
    root_records = [
        record
        for record in _file_records(vault, "ops/reports")
        if record["path"] not in NON_SEALING_INDEX_REPORTS
    ]
    task_observation_reports = _task_improvement_observation_reports(vault)
    current = [
        {
            "surface": "ops_reports",
            "family": record["family"],
            "path": record["path"],
            "role": "current_stable_report",
            "date": record["date"],
            "reason": "Top-level ops/reports files with stable names are current operational reports.",
        }
        for record in root_records
        if not record["date"]
    ]
    archive_candidates = [
        {
            "surface": "ops_reports",
            "family": record["family"],
            "path": record["path"],
            "suggested_archive_path": f"ops/reports/archive/{Path(record['path']).name}",
            "date": record["date"],
            "reason": "Dated top-level ops report should move under an archive namespace after a stable current report exists.",
        }
        for record in root_records
        if record["date"]
    ]
    return current, archive_candidates, {
        "ops_reports_root_file_count": len(root_records),
        "task_improvement_observation_count": len(task_observation_reports),
    }


def _operator_reports(vault: Path) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int]]:
    root_records = _file_records(vault, "ops/operator")
    current = [
        {
            "surface": "operator_reports",
            "family": record["family"],
            "path": record["path"],
            "role": "operator_only_report",
            "date": record["date"],
            "reason": "Top-level ops/operator files are current operator-only reports outside release authority sealing inventory.",
        }
        for record in root_records
        if not record["date"]
    ]
    archive_candidates = [
        {
            "surface": "operator_reports",
            "family": record["family"],
            "path": record["path"],
            "suggested_archive_path": f"ops/operator/archive/{Path(record['path']).name}",
            "date": record["date"],
            "reason": "Dated top-level operator report should move under an operator archive namespace after superseded.",
        }
        for record in root_records
        if record["date"]
    ]
    return current, archive_candidates, {
        "operator_reports_root_file_count": len(root_records),
    }


def _external_reports(
    vault: Path,
    *,
    status_by_action: dict[str, str] | None = None,
    archived_report_basis: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    root_records = _external_root_report_records(vault)
    record_by_path = {record["path"]: record for record in root_records}
    root_paths = [vault / record["path"] for record in root_records]
    lifecycle_profiles = report_lifecycle_profiles(vault, root_paths)
    statuses = status_by_action or _external_report_lifecycle_statuses(vault)
    archived_basis = archived_report_basis
    if archived_basis is None:
        archived_basis = archived_report_action_basis_records(vault, statuses)
    current: list[dict[str, Any]] = []
    archive_candidates: list[dict[str, Any]] = []
    for profile in lifecycle_profiles:
        record = record_by_path[str(profile["path"])]
        name = Path(record["path"]).name
        decision = lifecycle_decision(
            profile,
            profiles=lifecycle_profiles,
            statuses=statuses,
        )
        if decision["archive_recommended"]:
            archive_candidates.append(
                {
                    "surface": "external_reports",
                    "family": record["family"],
                    "path": record["path"],
                    "suggested_archive_path": f"external-reports/archive/{name}",
                    "date": record["date"],
                    "reason": _external_report_decision_reason(decision),
                    "superseded_by": decision["superseded_by"],
                    **_external_report_decision_fields(decision),
                }
            )
            continue
        current.append(
            {
                "surface": "external_reports",
                "family": record["family"],
                "path": record["path"],
                "role": (
                    "current_reference_manifest"
                    if profile["report_type"] == "reference_manifest"
                    else "current_review_report"
                ),
                "date": record["date"],
                "reason": _external_report_decision_reason(decision),
                **_external_report_decision_fields(decision),
            }
        )
    return current, archive_candidates, {
        "external_reports_root_file_count": len(root_records),
        "external_reports_archive_file_count": len(archived_basis),
    }


def _run_date(path: Path) -> str:
    match = RUN_ID_DATE_RE.search(path.name)
    if match is None:
        return date_token(path.name)
    return _compact_date(match.group(1))


def _optional_json_issue(label: str, diagnostics: dict[str, Any]) -> str | None:
    if diagnostics.get("missing"):
        return f"{label}:missing"
    if diagnostics.get("decode_error"):
        return f"{label}:decode_error"
    if diagnostics.get("type_error"):
        return f"{label}:type_error"
    status = str(diagnostics.get("status", "")).strip()
    if status and status != "ok":
        return f"{label}:{status}"
    return None


def _run_state(vault: Path, run_dir: Path) -> dict[str, str]:
    promotion, promotion_diagnostics = load_optional_json_object_with_diagnostics(run_dir / "promotion-report.json")
    ledger, ledger_diagnostics = load_optional_json_object_with_diagnostics(run_dir / "run-ledger.json")
    history = promotion.get("history", {}) if isinstance(promotion.get("history"), dict) else {}
    history_status = str(history.get("status", "")).strip() or "unknown"
    ledger_status = str(ledger.get("status", "")).strip() or "unknown"
    decision = str(promotion.get("decision", "")).strip()
    load_issues = [
        issue
        for issue in (
            _optional_json_issue("promotion-report.json", promotion_diagnostics),
            _optional_json_issue("run-ledger.json", ledger_diagnostics),
        )
        if issue is not None
    ]
    return {
        "path": report_path(vault, run_dir),
        "run_id": run_dir.name,
        "date": _run_date(run_dir),
        "history_status": history_status,
        "ledger_status": ledger_status,
        "decision": decision,
        "load_issue_summary": ", ".join(load_issues),
    }


def _runs(vault: Path) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int]]:
    root = vault / "runs"
    if not root.exists():
        return [], [], {"run_directory_count": 0, "run_archive_directory_count": 0}
    run_dirs = sorted(path for path in root.iterdir() if path.is_dir() and path.name != "archive")
    run_records = [_run_state(vault, path) for path in run_dirs]
    current = [
        {
            "surface": "runs",
            "family": "mechanism_run",
            "path": record["path"],
            "role": "run_history_record",
            "date": record["date"],
            "reason": (
                "Run state is indexed from promotion-report.history.status; physical location is secondary."
                + (
                    f" Load issues: {record['load_issue_summary']}."
                    if record["load_issue_summary"]
                    else ""
                )
            ),
        }
        for record in run_records
        if record["history_status"] != "archived"
    ]
    archive_candidates = [
        {
            "surface": "runs",
            "family": "mechanism_run",
            "path": record["path"],
            "suggested_archive_path": f"runs/archive/{Path(record['path']).name}",
            "date": record["date"],
            "reason": (
                "promotion-report.history.status=archived but the run remains in the top-level runs namespace."
                + (
                    f" Load issues: {record['load_issue_summary']}."
                    if record["load_issue_summary"]
                    else ""
                )
            ),
        }
        for record in run_records
        if record["history_status"] == "archived"
    ]
    archive_root = root / "archive"
    archived_dir_count = sum(1 for path in archive_root.iterdir() if path.is_dir()) if archive_root.exists() else 0
    return current, archive_candidates, {
        "run_directory_count": len(run_records),
        "run_archive_directory_count": archived_dir_count,
    }


def archive_rules() -> list[dict[str, str]]:
    return [
        {
            "surface": "ops_reports",
            "canonical_rule": "Stable top-level ops/reports/*.json filenames are current operational artifacts.",
            "archive_rule": "Dated one-off top-level ops reports should move to ops/reports/archive after superseded.",
            "gate_effect": "advisory",
        },
        {
            "surface": "external_reports",
            "canonical_rule": "The private reference manifest stays current as release provenance; root narrative external reports stay current only when they carry unique unresolved action themes.",
            "archive_rule": "Root narrative external reports become archive candidates when their structured action themes are implemented, explicitly superseded, or fully covered by a broader active report.",
            "gate_effect": "advisory",
        },
        {
            "surface": "operator_reports",
            "canonical_rule": "Stable top-level ops/operator files are current operator-only artifacts.",
            "archive_rule": "Dated one-off top-level operator reports should move to ops/operator/archive after superseded.",
            "gate_effect": "advisory",
        },
        {
            "surface": "runs",
            "canonical_rule": "promotion-report.history.status is the canonical active/archived/quarantined state.",
            "archive_rule": "Archived run directories may move under runs/archive without changing run state.",
            "gate_effect": "advisory",
        },
    ]


def _decision_relevance(surface: str) -> str:
    if surface == "ops_reports":
        return "operator_preflight"
    if surface == "operator_reports":
        return "operator_reference"
    if surface == "external_reports":
        return "review_context"
    return "run_history"


def _decorate_relationships(
    current: list[dict[str, Any]],
    archive_candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    current_with_relationships: list[dict[str, Any]] = []
    archive_with_relationships: list[dict[str, Any]] = []
    for record in current:
        surface = str(record.get("surface", "")).strip()
        family = str(record.get("family", "")).strip()
        supersedes = [str(path) for path in record.get("supersedes", [])]
        if surface != "runs" and family:
            supersedes.extend(
                str(item["path"])
                for item in archive_candidates
                if (
                    str(record.get("path")) in item.get("superseded_by", [])
                    or (
                        surface != "external_reports"
                        and item.get("surface") == surface
                        and item.get("family") == family
                    )
                )
            )
        current_with_relationships.append(
            {
                **record,
                "supersedes": sorted(set(supersedes)),
                "superseded_by": [str(path) for path in record.get("superseded_by", [])],
                "decision_relevance": _decision_relevance(surface),
            }
        )
    for record in archive_candidates:
        surface = str(record.get("surface", "")).strip()
        family = str(record.get("family", "")).strip()
        superseded_by = [str(path) for path in record.get("superseded_by", [])]
        if surface != "runs" and family:
            superseded_by.extend(
                str(item["path"])
                for item in current
                if (
                    surface != "external_reports"
                    and item.get("surface") == surface
                    and item.get("family") == family
                )
            )
        archive_with_relationships.append(
            {
                **record,
                "supersedes": [],
                "superseded_by": sorted(set(superseded_by)),
                "decision_relevance": _decision_relevance(surface),
            }
        )
    return current_with_relationships, archive_with_relationships


def _operator_digest(
    *,
    canonical_reports: list[dict[str, Any]],
    archive_candidates: list[dict[str, Any]],
) -> tuple[list[str], list[str], list[str]]:
    now = [
        f"{len(canonical_reports)} canonical artifact(s) are currently indexed.",
        f"{len(archive_candidates)} archive candidate(s) remain in active namespaces.",
    ]
    if archive_candidates:
        next_steps = [
            "Archive the root-level candidates after confirming their content lifecycle decision and linked replacement evidence.",
        ]
        why_blocked = sorted(
            {str(item["reason"]) for item in archive_candidates if item.get("reason")}
        )
    else:
        next_steps = ["No archive hygiene action is currently recommended."]
        why_blocked = []
    return now, next_steps, why_blocked


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    ops_current, ops_archive, ops_summary = _ops_reports(vault)
    operator_current, operator_archive, operator_summary = _operator_reports(vault)
    action_matrix_basis = _action_matrix_basis_state(vault)
    action_matrix_statuses = _action_matrix_statuses(
        vault,
        basis_state=action_matrix_basis,
    )
    external_statuses = _external_report_lifecycle_statuses(
        vault,
        action_matrix_basis=action_matrix_basis,
    )
    archived_external_report_basis = archived_report_action_basis_records(
        vault,
        external_statuses,
    )
    external_current, external_archive, external_summary = _external_reports(
        vault,
        status_by_action=external_statuses,
        archived_report_basis=archived_external_report_basis,
    )
    runs_current, runs_archive, runs_summary = _runs(vault)
    archive_candidates = [*ops_archive, *operator_archive, *external_archive, *runs_archive]
    canonical_reports = [*ops_current, *operator_current, *external_current, *runs_current]
    canonical_reports, archive_candidates = _decorate_relationships(
        canonical_reports,
        archive_candidates,
    )
    now, next_steps, why_blocked = _operator_digest(
        canonical_reports=canonical_reports,
        archive_candidates=archive_candidates,
    )
    generated_at = runtime_context.isoformat_z()
    task_observation_reports = _task_improvement_observation_reports(vault)
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="generated_artifact_index_report",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=GENERATED_ARTIFACT_INDEX_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/core/generated_artifact_index.py",
                "ops/scripts/release/external_report_inventory_runtime.py",
                "ops/scripts/release/external_report_lifecycle_runtime.py",
            ],
            path_group_inputs={
                "run_promotion_reports": [
                    path.relative_to(vault).as_posix()
                    for path in sorted((vault / "runs").glob("*/promotion-report.json"))
                ],
            },
            text_inputs={
                "ops_report_inventory": _canonical_inventory_text(_ops_report_inventory(vault)),
                "operator_report_inventory": _canonical_inventory_text(_operator_report_inventory(vault)),
                "external_report_inventory": _canonical_inventory_text(
                    _external_report_inventory(
                        vault,
                        status_by_action=external_statuses,
                        archived_report_basis=archived_external_report_basis,
                    )
                ),
                "external_report_action_matrix_statuses": _canonical_inventory_text(
                    action_matrix_statuses
                ),
                "external_report_action_matrix_basis": _canonical_inventory_text(
                    action_matrix_basis
                ),
                "task_improvement_observation_inventory": _canonical_inventory_text(task_observation_reports),
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": "attention" if archive_candidates else "pass",
        "archive_rules": archive_rules(),
        "tracking_policy": tracking_policy(),
        "now": now,
        "next": next_steps,
        "why_blocked": why_blocked,
        "summary": {
            **ops_summary,
            **operator_summary,
            **external_summary,
            **runs_summary,
            "canonical_report_count": len(canonical_reports),
            "archive_candidate_count": len(archive_candidates),
        },
        "canonical_reports": canonical_reports,
        "archive_candidates": archive_candidates,
        "external_report_action_matrix_basis": action_matrix_basis,
        "archived_external_report_basis": archived_external_report_basis,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=GENERATED_ARTIFACT_INDEX_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="generated artifact index schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Index current and archive-candidate generated artifacts")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, policy_path=args.policy_path)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
