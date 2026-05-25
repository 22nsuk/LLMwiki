from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ops.scripts.policy_runtime import report_path
from ops.scripts.promotion_decision_registry_runtime import decision_from_report
from ops.scripts.schema_constants_runtime import (
    CHANGED_FILES_MANIFEST_SCHEMA_PATH,
    EVAL_REPORT_SCHEMA_PATH,
    MECHANISM_ASSESSMENT_SCHEMA_PATH,
    PROMOTION_REPORT_SCHEMA_PATH,
)
from ops.scripts.schema_runtime import (
    load_schema_with_vault_override,
    validate_with_schema,
)

from .current_target_path_runtime import current_repo_target_paths

PROMOTION_REPORT_SCHEMA = PROMOTION_REPORT_SCHEMA_PATH
MECHANISM_ASSESSMENT_SCHEMA = MECHANISM_ASSESSMENT_SCHEMA_PATH
EVAL_REPORT_SCHEMA = EVAL_REPORT_SCHEMA_PATH
CHANGED_FILES_MANIFEST_SCHEMA = CHANGED_FILES_MANIFEST_SCHEMA_PATH


__all__ = [
    "EVAL_REPORT_SCHEMA",
    "MECHANISM_ASSESSMENT_SCHEMA",
    "PROMOTION_REPORT_SCHEMA",
    "MechanismRunSnapshot",
    "group_snapshots_by_targets",
    "load_artifact",
    "load_mechanism_run_snapshots",
    "load_optional_json",
    "read_json",
]


@dataclass(frozen=True)
class MechanismRunSnapshot:
    run_id: str
    promotion_report_path: str
    primary_targets: list[str]
    supporting_targets: list[str]
    decision: str
    baseline_eval: dict
    candidate_eval: dict
    baseline_mechanism: dict
    candidate_mechanism: dict
    changed_files_manifest: dict = field(default_factory=dict)


@dataclass(frozen=True)
class _MechanismHistorySchemas:
    promotion: dict
    mechanism: dict
    eval: dict
    changed_files_manifest: dict


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_optional_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def load_artifact(
    vault: Path,
    rel_path: str,
    schema: dict,
) -> tuple[dict | None, str | None]:
    resolved = (vault / rel_path).resolve()
    if not resolved.exists():
        return None, f"missing artifact: {rel_path}"
    try:
        payload = read_json(resolved)
    except json.JSONDecodeError as exc:
        return None, f"invalid json in {rel_path}: line {exc.lineno} column {exc.colno}"
    errors = validate_with_schema(payload, schema)
    if errors:
        return None, f"schema validation failed for {rel_path}: {errors[0]}"
    return payload, None


def skipped_run_triage(reason: str, detail: str) -> dict[str, object] | None:
    if reason == "run_artifact_invalid" and detail.startswith("missing artifact:"):
        return {
            "status": "operator_decision_required",
            "problem": "missing_promotion_input_artifact",
            "recommended_action": "restore_missing_artifact_or_archive_run_history",
            "options": [
                "restore the missing artifact from ledgered evidence",
                "archive or quarantine the promotion report history",
                "mark the run non-history if superseded by a later run",
            ],
        }
    if reason == "promotion_report_missing_input":
        return {
            "status": "operator_decision_required",
            "problem": "promotion_report_input_reference_missing",
            "recommended_action": "repair_promotion_inputs_or_archive_run_history",
            "options": [
                "repair the promotion report input reference",
                "archive or quarantine the promotion report history",
                "mark the run non-history if superseded by a later run",
            ],
        }
    return None


def skipped_run_failure(
    *,
    run_id: str,
    reason: str,
    path: str,
    detail: str,
) -> dict[str, object]:
    failure: dict[str, object] = {
        "run_id": run_id,
        "reason": reason,
        "path": path,
        "detail": detail,
    }
    triage = skipped_run_triage(reason, detail)
    if triage is not None:
        failure["triage"] = triage
    return failure


def _load_mechanism_history_schemas(vault: Path) -> _MechanismHistorySchemas:
    return _MechanismHistorySchemas(
        promotion=load_schema_with_vault_override(vault, PROMOTION_REPORT_SCHEMA),
        mechanism=load_schema_with_vault_override(vault, MECHANISM_ASSESSMENT_SCHEMA),
        eval=load_schema_with_vault_override(vault, EVAL_REPORT_SCHEMA),
        changed_files_manifest=load_schema_with_vault_override(vault, CHANGED_FILES_MANIFEST_SCHEMA),
    )


def _load_promotion_report(
    vault: Path,
    promotion_path: Path,
    promotion_schema: dict,
) -> tuple[dict | None, dict | None]:
    run_id = promotion_path.parent.name
    try:
        promotion_report = read_json(promotion_path)
    except json.JSONDecodeError as exc:
        return None, {
            "run_id": run_id,
            "reason": "promotion_report_invalid_json",
            "path": report_path(vault, promotion_path),
            "detail": f"line {exc.lineno} column {exc.colno}",
        }

    promotion_errors = validate_with_schema(promotion_report, promotion_schema)
    if promotion_errors:
        return None, {
            "run_id": promotion_report.get("run_id", run_id),
            "reason": "promotion_report_schema_invalid",
            "path": report_path(vault, promotion_path),
            "detail": promotion_errors[0],
        }
    return promotion_report, None


def _promotion_history_exclusion(
    vault: Path,
    promotion_report: dict,
    promotion_path: Path,
) -> dict[str, object] | None:
    history = promotion_report.get("history", {})
    history_status = history.get("status", "active") if isinstance(history, dict) else "active"
    if history_status == "active":
        return None
    return {
        "run_id": promotion_report["run_id"],
        "status": history_status,
        "reason": history.get("reason", "") if isinstance(history, dict) else "",
        "path": report_path(vault, promotion_path),
    }


def _load_required_promotion_inputs(
    vault: Path,
    promotion_report: dict,
    promotion_path: Path,
    schemas: _MechanismHistorySchemas,
) -> tuple[dict[str, dict], dict | None]:
    inputs = promotion_report.get("inputs", {})
    required_input_paths = (
        ("baseline_eval_report", schemas.eval),
        ("candidate_eval_report", schemas.eval),
        ("baseline_mechanism_report", schemas.mechanism),
        ("candidate_mechanism_report", schemas.mechanism),
    )
    loaded_inputs: dict[str, dict] = {}
    for key, schema in required_input_paths:
        rel_path = inputs.get(key)
        if not isinstance(rel_path, str) or not rel_path.strip():
            return loaded_inputs, skipped_run_failure(
                run_id=promotion_report["run_id"],
                reason="promotion_report_missing_input",
                path=report_path(vault, promotion_path),
                detail=f"missing inputs.{key}",
            )
        artifact, error = load_artifact(vault, rel_path, schema)
        if error is not None:
            return loaded_inputs, skipped_run_failure(
                run_id=promotion_report["run_id"],
                reason="run_artifact_invalid",
                path=rel_path,
                detail=error,
            )
        if artifact is None:
            return loaded_inputs, skipped_run_failure(
                run_id=promotion_report["run_id"],
                reason="run_artifact_invalid",
                path=rel_path,
                detail="artifact loader returned no payload",
            )
        loaded_inputs[key] = artifact
    return loaded_inputs, None


def _load_changed_files_manifest(
    vault: Path,
    promotion_report: dict,
    changed_files_schema: dict,
) -> tuple[dict, dict | None]:
    inputs = promotion_report.get("inputs", {})
    changed_files_manifest_rel = inputs.get("changed_files_manifest")
    if not isinstance(changed_files_manifest_rel, str) or not changed_files_manifest_rel.strip():
        return {}, None
    artifact, error = load_artifact(vault, changed_files_manifest_rel, changed_files_schema)
    if error is None:
        return artifact or {}, None
    return {}, skipped_run_failure(
        run_id=promotion_report["run_id"],
        reason="run_artifact_invalid",
        path=changed_files_manifest_rel,
        detail=error,
    )


def load_mechanism_run_snapshots(
    vault: Path,
    policy: dict,
    *,
    max_runs: int,
) -> tuple[list[MechanismRunSnapshot], list[dict], list[dict], int]:
    del policy
    schemas = _load_mechanism_history_schemas(vault)
    promotion_paths = _promotion_report_paths(vault)

    discovered = 0
    skipped_runs: list[dict] = []
    excluded_runs: list[dict] = []
    snapshots: list[MechanismRunSnapshot] = []

    for promotion_path in promotion_paths:
        promotion_report, load_failure = _load_promotion_report(vault, promotion_path, schemas.promotion)
        if load_failure is not None:
            skipped_runs.append(load_failure)
            continue
        if promotion_report is None:
            continue

        if promotion_report["artifact_class"] != "system_mechanism":
            continue

        discovered += 1
        exclusion = _promotion_history_exclusion(vault, promotion_report, promotion_path)
        if exclusion is not None:
            excluded_runs.append(exclusion)
            continue
        if len(snapshots) >= max_runs:
            continue

        loaded_inputs, failure = _load_required_promotion_inputs(
            vault,
            promotion_report,
            promotion_path,
            schemas,
        )
        if failure is not None:
            skipped_runs.append(failure)
            continue

        changed_files_manifest, failure = _load_changed_files_manifest(
            vault,
            promotion_report,
            schemas.changed_files_manifest,
        )
        if failure is not None:
            skipped_runs.append(failure)
            continue

        snapshots.append(
            MechanismRunSnapshot(
                run_id=promotion_report["run_id"],
                promotion_report_path=report_path(vault, promotion_path),
                primary_targets=current_repo_target_paths(
                    vault,
                    list(promotion_report["primary_targets"]),
                ),
                supporting_targets=current_repo_target_paths(
                    vault,
                    list(promotion_report["supporting_targets"]),
                ),
                decision=decision_from_report(promotion_report, require_record=False),
                baseline_eval=loaded_inputs["baseline_eval_report"],
                candidate_eval=loaded_inputs["candidate_eval_report"],
                baseline_mechanism=loaded_inputs["baseline_mechanism_report"],
                candidate_mechanism=loaded_inputs["candidate_mechanism_report"],
                changed_files_manifest=changed_files_manifest,
            )
        )

    return snapshots, skipped_runs, excluded_runs, discovered


def _promotion_report_paths(vault: Path) -> list[Path]:
    paths = {
        *list((vault / "runs").glob("*/promotion-report.json")),
        *list((vault / "runs" / "archive").glob("*/promotion-report.json")),
    }
    return sorted(paths, key=lambda path: path.parent.name, reverse=True)


def group_snapshots_by_targets(
    snapshots: list[MechanismRunSnapshot],
) -> dict[tuple[str, ...], list[MechanismRunSnapshot]]:
    grouped: dict[tuple[str, ...], list[MechanismRunSnapshot]] = {}
    for snapshot in snapshots:
        key = tuple(snapshot.primary_targets)
        grouped.setdefault(key, []).append(snapshot)
    for group in grouped.values():
        group.sort(key=lambda snapshot: snapshot.run_id)
    return grouped
