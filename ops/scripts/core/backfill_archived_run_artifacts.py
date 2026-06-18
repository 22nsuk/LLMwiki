#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.artifact_freshness_runtime import (
        EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY,
        ENVELOPE_REQUIRED_FIELDS,
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        read_json_object,
        write_schema_validated_json,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_constants_runtime import (
        BEHAVIOR_DELTA_SCHEMA_PATH,
        CANDIDATE_CHANGED_FILES_SNAPSHOT_SCHEMA_PATH,
        CHANGED_FILES_MANIFEST_SCHEMA_PATH,
        COMMAND_LOG_SUMMARY_SCHEMA_PATH,
        GENERATED_ARTIFACT_CONVERGENCE_SCHEMA_PATH,
        MECHANISM_ASSESSMENT_SCHEMA_PATH,
        PLANNING_VALIDATION_SCHEMA_PATH,
        PROMOTION_REPORT_SCHEMA_PATH,
        PROPOSAL_SNAPSHOT_SCHEMA_PATH,
        RAW_INTAKE_ABSORPTION_MATRIX_SCHEMA_PATH,
        RAW_INTAKE_FINAL_TREE_VALIDATION_REPORT_SCHEMA_PATH,
        RAW_INTAKE_PROMOTION_PROFILE_BUNDLE_SCHEMA_PATH,
        RAW_INTAKE_PROMOTION_REPORT_SCHEMA_PATH,
        RAW_MARKDOWN_NORMALIZATION_REPORT_SCHEMA_PATH,
        ROLLBACK_REHEARSAL_REPORT_SCHEMA_PATH,
        RUN_ARTIFACT_FINGERPRINT_SCHEMA_PATH,
        RUN_LEDGER_SCHEMA_PATH,
        RUN_TELEMETRY_SCHEMA_PATH,
        SAME_SESSION_REPAIR_CONTEXT_SCHEMA_PATH,
        SHADOW_APPLY_REPORT_SCHEMA_PATH,
        SOURCE_SLUG_CURATION_MANIFEST_SCHEMA_PATH,
        SOURCE_SLUG_CURATION_VALIDATION_REPORT_SCHEMA_PATH,
        TIMEOUT_FAILURE_SCHEMA_PATH,
    )
    from ops.scripts.core.schema_runtime import (
        load_schema_with_vault_override,
        validate_with_schema,
    )
else:
    from .artifact_freshness_runtime import (
        EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY,
        ENVELOPE_REQUIRED_FIELDS,
        build_canonical_report_envelope,
    )
    from .artifact_io_runtime import read_json_object, write_schema_validated_json
    from .output_runtime import display_path
    from .policy_runtime import load_policy, report_path
    from .runtime_context import RuntimeContext
    from .schema_constants_runtime import (
        BEHAVIOR_DELTA_SCHEMA_PATH,
        CANDIDATE_CHANGED_FILES_SNAPSHOT_SCHEMA_PATH,
        CHANGED_FILES_MANIFEST_SCHEMA_PATH,
        COMMAND_LOG_SUMMARY_SCHEMA_PATH,
        GENERATED_ARTIFACT_CONVERGENCE_SCHEMA_PATH,
        MECHANISM_ASSESSMENT_SCHEMA_PATH,
        PLANNING_VALIDATION_SCHEMA_PATH,
        PROMOTION_REPORT_SCHEMA_PATH,
        PROPOSAL_SNAPSHOT_SCHEMA_PATH,
        RAW_INTAKE_ABSORPTION_MATRIX_SCHEMA_PATH,
        RAW_INTAKE_FINAL_TREE_VALIDATION_REPORT_SCHEMA_PATH,
        RAW_INTAKE_PROMOTION_PROFILE_BUNDLE_SCHEMA_PATH,
        RAW_INTAKE_PROMOTION_REPORT_SCHEMA_PATH,
        RAW_MARKDOWN_NORMALIZATION_REPORT_SCHEMA_PATH,
        ROLLBACK_REHEARSAL_REPORT_SCHEMA_PATH,
        RUN_ARTIFACT_FINGERPRINT_SCHEMA_PATH,
        RUN_LEDGER_SCHEMA_PATH,
        RUN_TELEMETRY_SCHEMA_PATH,
        SAME_SESSION_REPAIR_CONTEXT_SCHEMA_PATH,
        SHADOW_APPLY_REPORT_SCHEMA_PATH,
        SOURCE_SLUG_CURATION_MANIFEST_SCHEMA_PATH,
        SOURCE_SLUG_CURATION_VALIDATION_REPORT_SCHEMA_PATH,
        TIMEOUT_FAILURE_SCHEMA_PATH,
    )
    from .schema_runtime import load_schema_with_vault_override, validate_with_schema


PRODUCER = "ops.scripts.backfill_archived_run_artifacts"
SCRIPT_PATH = "ops/scripts/core/backfill_archived_run_artifacts.py"
RUN_ARTIFACT_SCAN_ROOT = Path("runs")
BACKFILL_PROVENANCE_PROPERTY = "urn:openai:archived-run-backfill"
ARCHIVE_REASON = "run_artifact_embedded_envelope_backfill"
RUN_TELEMETRY_DISCARD_NON_REGRESSION_CHECK_IDS = (
    "candidate_eval_pass",
    "eval_score_improves",
    "lint_non_regression",
    "structural_complexity_non_regression",
    "tests_non_regression",
)
RUN_TELEMETRY_PROMOTION_CHECK_STATUS_VALUES = frozenset({"PASS", "WARN", "FAIL"})


@dataclass(frozen=True)
class TimestampCandidate:
    label: str
    normalized: str


@dataclass(frozen=True)
class ArchivedRunArtifactSpec:
    filename: str
    schema_path: str
    artifact_kind: str
    source_paths: tuple[str, ...]
    derive_generated_at: Callable[[Path, Path, str, dict[str, Any]], tuple[str, str]]


def _parse_timestamp(value: str, *, context: str) -> dt.datetime:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{context} is missing a timestamp")
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{context} has an invalid timestamp: {text!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{context} must include timezone information: {text!r}")
    return parsed.astimezone(dt.UTC)


def _isoformat_z(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalized_timestamp(value: str, *, context: str) -> str:
    return _isoformat_z(_parse_timestamp(value, context=context))


def _artifact_mtime_is_newer(path: Path, generated_at: str, *, context: str) -> bool:
    generated = _parse_timestamp(generated_at, context=context).replace(microsecond=0)
    mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.UTC).replace(microsecond=0)
    return mtime > generated


def _timestamp_candidate(label: str, value: Any, *, context: str) -> TimestampCandidate | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return TimestampCandidate(label=label, normalized=_normalized_timestamp(value, context=context))


def _max_timestamp_candidate(candidates: list[TimestampCandidate], *, context: str) -> TimestampCandidate:
    if not candidates:
        raise ValueError(f"{context} does not contain any timestamp candidates")
    return max(candidates, key=lambda item: _parse_timestamp(item.normalized, context=f"{context}:{item.label}"))


def _nested_string(payload: dict[str, Any], *keys: str) -> str | None:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current if isinstance(current, str) else None


def _report_path(vault: Path, path: Path) -> str:
    return report_path(vault, path)


def _load_json_if_exists(vault: Path, path: Path) -> tuple[str, dict[str, Any]] | None:
    if not path.is_file():
        return None
    rel_path = _report_path(vault, path)
    return rel_path, read_json_object(path, context=rel_path)


def _changed_files_manifest_generated_at(
    vault: Path,
    artifact_path: Path,
    rel_path: str,
    payload: dict[str, Any],
) -> tuple[str, str]:
    del vault, artifact_path
    generated_at = _normalized_timestamp(str(payload.get("generated_at", "")), context=f"{rel_path}:generated_at")
    return generated_at, "payload.generated_at"


def _payload_generated_at(
    vault: Path,
    artifact_path: Path,
    rel_path: str,
    payload: dict[str, Any],
) -> tuple[str, str]:
    del vault, artifact_path
    generated_at = _normalized_timestamp(str(payload.get("generated_at", "")), context=f"{rel_path}:generated_at")
    return generated_at, "payload.generated_at"


def _promotion_check_statuses(payload: dict[str, Any]) -> dict[str, str]:
    checks = payload.get("checks")
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


def _non_regression_statuses(statuses: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for check_id in RUN_TELEMETRY_DISCARD_NON_REGRESSION_CHECK_IDS:
        status = str(statuses.get(check_id, "")).strip().upper()
        if not status:
            normalized[check_id] = "MISSING"
        elif status in RUN_TELEMETRY_PROMOTION_CHECK_STATUS_VALUES:
            normalized[check_id] = status
        else:
            normalized[check_id] = "UNKNOWN"
    return normalized


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


def _same_run_report_path(vault: Path, run_id: str, rel_path: object) -> Path | None:
    normalized = _normalized_repo_relative_path(rel_path)
    if not normalized:
        return None
    if not normalized.startswith(f"runs/{run_id}/"):
        return None
    vault_root = vault.resolve()
    resolved_path = (vault_root / normalized).resolve()
    if not resolved_path.is_relative_to(vault_root):
        return None
    if not resolved_path.is_relative_to((vault_root / "runs" / run_id).resolve()):
        return None
    return resolved_path


def _run_telemetry_non_regression_statuses_from_promotion_report(
    vault: Path,
    run_id: str,
    evidence: dict[str, Any],
) -> dict[str, str] | None:
    promotion_report_path = _same_run_report_path(vault, run_id, evidence.get("promotion_report"))
    if promotion_report_path is None or not promotion_report_path.is_file():
        return None
    promotion_report = read_json_object(
        promotion_report_path,
        context=report_path(vault, promotion_report_path),
    )
    return _non_regression_statuses(_promotion_check_statuses(promotion_report))


def _run_telemetry_non_regression_statuses_from_booleans(
    evidence: dict[str, Any],
) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for check_id in RUN_TELEMETRY_DISCARD_NON_REGRESSION_CHECK_IDS:
        value = evidence.get(check_id)
        statuses[check_id] = "PASS" if value is True else "UNKNOWN"
    return statuses


def _normalize_legacy_run_telemetry_payload(
    vault: Path,
    rel_path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if Path(rel_path).name != "run-telemetry.json":
        return payload
    evidence = payload.get("discard_non_regression_evidence")
    if not isinstance(evidence, dict) or "non_regression_check_statuses" in evidence:
        return payload
    run_id = str(payload.get("run_id", "")).strip()
    statuses = (
        _run_telemetry_non_regression_statuses_from_promotion_report(vault, run_id, evidence)
        if run_id
        else None
    )
    normalized_payload = dict(payload)
    normalized_evidence = dict(evidence)
    normalized_evidence["non_regression_check_statuses"] = (
        statuses
        if statuses is not None
        else _run_telemetry_non_regression_statuses_from_booleans(evidence)
    )
    normalized_payload["discard_non_regression_evidence"] = normalized_evidence
    return normalized_payload


def _date_suffix_timestamp(rel_path: str) -> tuple[str, str]:
    matches = re.findall(r"\d{4}-\d{2}-\d{2}", rel_path)
    if matches:
        return f"{matches[-1]}T00:00:00Z", "filename.date_suffix"
    raise ValueError(f"{rel_path} does not contain a date suffix")


def _related_json_generated_at(
    vault: Path,
    rel_path: str,
    payload: dict[str, Any],
    field: str,
) -> tuple[str, str] | None:
    candidate = payload.get(field)
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    related = vault / candidate
    if not related.is_file():
        return None
    related_payload = read_json_object(related, context=candidate)
    generated_at = str(related_payload.get("generated_at", "")).strip()
    if generated_at:
        return _normalized_timestamp(generated_at, context=f"{candidate}:generated_at"), f"{field}.generated_at"
    embedded_text = _embedded_envelope_text(related_payload)
    if embedded_text:
        try:
            embedded = json.loads(embedded_text)
        except json.JSONDecodeError:
            embedded = {}
        if isinstance(embedded, dict) and isinstance(embedded.get("generated_at"), str):
            return (
                _normalized_timestamp(embedded["generated_at"], context=f"{candidate}:embedded.generated_at"),
                f"{field}.embedded_envelope.generated_at",
            )
    return None


def _raw_intake_generated_at(
    vault: Path,
    artifact_path: Path,
    rel_path: str,
    payload: dict[str, Any],
) -> tuple[str, str]:
    del artifact_path
    generated_at = str(payload.get("generated_at", "")).strip()
    if generated_at:
        return _normalized_timestamp(generated_at, context=f"{rel_path}:generated_at"), "payload.generated_at"
    for field in ("generated_from", "manifest"):
        related = _related_json_generated_at(vault, rel_path, payload, field)
        if related is not None:
            return related
    return _date_suffix_timestamp(rel_path)


def _run_ledger_generated_at(
    vault: Path,
    artifact_path: Path,
    rel_path: str,
    payload: dict[str, Any],
) -> tuple[str, str]:
    del vault, artifact_path
    candidates: list[TimestampCandidate] = []
    for index, event in enumerate(payload.get("events", [])):
        if not isinstance(event, dict):
            continue
        candidate = _timestamp_candidate(
            f"events[{index}].ts",
            event.get("ts"),
            context=f"{rel_path}:events[{index}].ts",
        )
        if candidate is not None:
            candidates.append(candidate)
    selected = _max_timestamp_candidate(candidates, context=rel_path)
    return selected.normalized, selected.label


def _promotion_report_generated_at(
    vault: Path,
    artifact_path: Path,
    rel_path: str,
    payload: dict[str, Any],
) -> tuple[str, str]:
    candidates = [
        _timestamp_candidate("history.ts", _nested_string(payload, "history", "ts"), context=f"{rel_path}:history.ts"),
        _timestamp_candidate("signoff.ts", _nested_string(payload, "signoff", "ts"), context=f"{rel_path}:signoff.ts"),
        _timestamp_candidate(
            "decision_record.decided_at",
            _nested_string(payload, "decision_record", "decided_at"),
            context=f"{rel_path}:decision_record.decided_at",
        ),
        _timestamp_candidate(
            "decision_record.effective_at",
            _nested_string(payload, "decision_record", "effective_at"),
            context=f"{rel_path}:decision_record.effective_at",
        ),
    ]
    filtered_candidates = [item for item in candidates if item is not None]
    if not filtered_candidates:
        ledger_result = _load_json_if_exists(vault, artifact_path.with_name("run-ledger.json"))
        if ledger_result is not None:
            ledger_rel_path, ledger_payload = ledger_result
            generated_at, source = _run_ledger_generated_at(
                vault,
                artifact_path.with_name("run-ledger.json"),
                ledger_rel_path,
                ledger_payload,
            )
            filtered_candidates.append(TimestampCandidate(label=f"run-ledger.{source}", normalized=generated_at))
    selected = _max_timestamp_candidate(filtered_candidates, context=rel_path)
    return selected.normalized, selected.label


def _planning_validation_generated_at(
    vault: Path,
    artifact_path: Path,
    rel_path: str,
    payload: dict[str, Any],
) -> tuple[str, str]:
    candidates: list[TimestampCandidate] = []
    signoff_candidate = _timestamp_candidate(
        "signoff.ts",
        _nested_string(payload, "signoff", "ts"),
        context=f"{rel_path}:signoff.ts",
    )
    if signoff_candidate is not None:
        candidates.append(signoff_candidate)

    promotion_result = _load_json_if_exists(vault, artifact_path.with_name("promotion-report.json"))
    if promotion_result is not None:
        promotion_rel_path, promotion_payload = promotion_result
        generated_at, source = _promotion_report_generated_at(vault, artifact_path.with_name("promotion-report.json"), promotion_rel_path, promotion_payload)
        candidates.append(TimestampCandidate(label=f"promotion-report.{source}", normalized=generated_at))

    ledger_result = _load_json_if_exists(vault, artifact_path.with_name("run-ledger.json"))
    if ledger_result is not None:
        ledger_rel_path, ledger_payload = ledger_result
        generated_at, source = _run_ledger_generated_at(vault, artifact_path.with_name("run-ledger.json"), ledger_rel_path, ledger_payload)
        candidates.append(TimestampCandidate(label=f"run-ledger.{source}", normalized=generated_at))

    selected = _max_timestamp_candidate(candidates, context=rel_path)
    return selected.normalized, selected.label


def _proposal_snapshot_generated_at(
    vault: Path,
    artifact_path: Path,
    rel_path: str,
    payload: dict[str, Any],
) -> tuple[str, str]:
    del vault, artifact_path
    captured_at = _normalized_timestamp(
        str(payload.get("captured_at", "")),
        context=f"{rel_path}:captured_at",
    )
    return captured_at, "payload.captured_at"


ARCHIVED_RUN_ARTIFACT_SPECS = {
    "changed-files-manifest.json": ArchivedRunArtifactSpec(
        filename="changed-files-manifest.json",
        schema_path=CHANGED_FILES_MANIFEST_SCHEMA_PATH,
        artifact_kind="changed_files_manifest",
        source_paths=(SCRIPT_PATH, "ops/scripts/mechanism/mechanism_run_workspace_runtime.py"),
        derive_generated_at=_changed_files_manifest_generated_at,
    ),
    "candidate-changed-files-snapshot.json": ArchivedRunArtifactSpec(
        filename="candidate-changed-files-snapshot.json",
        schema_path=CANDIDATE_CHANGED_FILES_SNAPSHOT_SCHEMA_PATH,
        artifact_kind="candidate_changed_files_snapshot",
        source_paths=(
            SCRIPT_PATH,
            "ops/scripts/mechanism/mechanism_run_candidate_snapshot_runtime.py",
            "ops/scripts/mechanism/mechanism_run_workspace_runtime.py",
        ),
        derive_generated_at=_payload_generated_at,
    ),
    "planning-validation.json": ArchivedRunArtifactSpec(
        filename="planning-validation.json",
        schema_path=PLANNING_VALIDATION_SCHEMA_PATH,
        artifact_kind="planning_validation",
        source_paths=(
            SCRIPT_PATH,
            "ops/scripts/mechanism/finalize_run_state_runtime.py",
            "ops/scripts/mechanism/planning_gate_validate_runtime.py",
        ),
        derive_generated_at=_planning_validation_generated_at,
    ),
    "proposal-snapshot.json": ArchivedRunArtifactSpec(
        filename="proposal-snapshot.json",
        schema_path=PROPOSAL_SNAPSHOT_SCHEMA_PATH,
        artifact_kind="proposal_snapshot",
        source_paths=(
            SCRIPT_PATH,
            "ops/scripts/mechanism/mechanism_run_scaffold_runtime.py",
            "ops/scripts/mechanism/mechanism_run_scaffold_templates_runtime.py",
        ),
        derive_generated_at=_proposal_snapshot_generated_at,
    ),
    "promotion-report.json": ArchivedRunArtifactSpec(
        filename="promotion-report.json",
        schema_path=PROMOTION_REPORT_SCHEMA_PATH,
        artifact_kind="promotion_report",
        source_paths=(
            SCRIPT_PATH,
            "ops/scripts/mechanism/promotion_gate_mechanism_report_runtime.py",
        ),
        derive_generated_at=_promotion_report_generated_at,
    ),
    "run-ledger.json": ArchivedRunArtifactSpec(
        filename="run-ledger.json",
        schema_path=RUN_LEDGER_SCHEMA_PATH,
        artifact_kind="run_ledger",
        source_paths=(SCRIPT_PATH, "ops/scripts/mechanism/mechanism_run_ledger_runtime.py"),
        derive_generated_at=_run_ledger_generated_at,
    ),
    "behavior-delta.json": ArchivedRunArtifactSpec(
        filename="behavior-delta.json",
        schema_path=BEHAVIOR_DELTA_SCHEMA_PATH,
        artifact_kind="behavior_delta",
        source_paths=(SCRIPT_PATH, "ops/scripts/core/behavior_delta_runtime.py"),
        derive_generated_at=_payload_generated_at,
    ),
    "run-artifact-fingerprint.json": ArchivedRunArtifactSpec(
        filename="run-artifact-fingerprint.json",
        schema_path=RUN_ARTIFACT_FINGERPRINT_SCHEMA_PATH,
        artifact_kind="run_artifact_fingerprint",
        source_paths=(
            SCRIPT_PATH,
            "ops/scripts/core/observability_artifact_fingerprint_runtime.py",
        ),
        derive_generated_at=_payload_generated_at,
    ),
    "command-log-summary.json": ArchivedRunArtifactSpec(
        filename="command-log-summary.json",
        schema_path=COMMAND_LOG_SUMMARY_SCHEMA_PATH,
        artifact_kind="command_log_summary",
        source_paths=(
            SCRIPT_PATH,
            "ops/scripts/core/command_log_summary_runtime.py",
            "ops/scripts/core/command_log_summary_backfill.py",
        ),
        derive_generated_at=_payload_generated_at,
    ),
    "baseline-mechanism-assessment.json": ArchivedRunArtifactSpec(
        filename="baseline-mechanism-assessment.json",
        schema_path=MECHANISM_ASSESSMENT_SCHEMA_PATH,
        artifact_kind="mechanism_assessment_report",
        source_paths=(SCRIPT_PATH, "ops/scripts/mechanism/mechanism_assess.py"),
        derive_generated_at=_payload_generated_at,
    ),
    "candidate-mechanism-assessment.json": ArchivedRunArtifactSpec(
        filename="candidate-mechanism-assessment.json",
        schema_path=MECHANISM_ASSESSMENT_SCHEMA_PATH,
        artifact_kind="mechanism_assessment_report",
        source_paths=(SCRIPT_PATH, "ops/scripts/mechanism/mechanism_assess.py"),
        derive_generated_at=_payload_generated_at,
    ),
    "raw-markdown-normalization-report.json": ArchivedRunArtifactSpec(
        filename="raw-markdown-normalization-report.json",
        schema_path=RAW_MARKDOWN_NORMALIZATION_REPORT_SCHEMA_PATH,
        artifact_kind="raw_markdown_normalization_report",
        source_paths=(SCRIPT_PATH, "ops/scripts/registry/raw_markdown_normalize.py"),
        derive_generated_at=_payload_generated_at,
    ),
    "run-telemetry.json": ArchivedRunArtifactSpec(
        filename="run-telemetry.json",
        schema_path=RUN_TELEMETRY_SCHEMA_PATH,
        artifact_kind="run_telemetry",
        source_paths=(SCRIPT_PATH, "ops/scripts/core/experiment_telemetry_runtime.py"),
        derive_generated_at=_payload_generated_at,
    ),
    "same-session-repair-context.json": ArchivedRunArtifactSpec(
        filename="same-session-repair-context.json",
        schema_path=SAME_SESSION_REPAIR_CONTEXT_SCHEMA_PATH,
        artifact_kind="same_session_repair_context",
        source_paths=(
            SCRIPT_PATH,
            "ops/scripts/mechanism/run_mechanism_experiment_runtime.py",
        ),
        derive_generated_at=_payload_generated_at,
    ),
    "generated-artifact-convergence.json": ArchivedRunArtifactSpec(
        filename="generated-artifact-convergence.json",
        schema_path=GENERATED_ARTIFACT_CONVERGENCE_SCHEMA_PATH,
        artifact_kind="generated_artifact_convergence",
        source_paths=(
            SCRIPT_PATH,
            "ops/scripts/mechanism/post_mutation_generated_artifact_convergence_runtime.py",
        ),
        derive_generated_at=_payload_generated_at,
    ),
    "timeout-failure.json": ArchivedRunArtifactSpec(
        filename="timeout-failure.json",
        schema_path=TIMEOUT_FAILURE_SCHEMA_PATH,
        artifact_kind="timeout_failure",
        source_paths=(
            SCRIPT_PATH,
            "ops/scripts/core/experiment_telemetry_runtime.py",
        ),
        derive_generated_at=_payload_generated_at,
    ),
    "shadow-apply-report.json": ArchivedRunArtifactSpec(
        filename="shadow-apply-report.json",
        schema_path=SHADOW_APPLY_REPORT_SCHEMA_PATH,
        artifact_kind="shadow_apply_report",
        source_paths=(
            SCRIPT_PATH,
            "ops/scripts/core/filesystem_runtime.py",
            "ops/scripts/mechanism/mechanism_run_workspace_runtime.py",
        ),
        derive_generated_at=_payload_generated_at,
    ),
    "rollback-rehearsal-report.json": ArchivedRunArtifactSpec(
        filename="rollback-rehearsal-report.json",
        schema_path=ROLLBACK_REHEARSAL_REPORT_SCHEMA_PATH,
        artifact_kind="rollback_rehearsal_report",
        source_paths=(
            SCRIPT_PATH,
            "ops/scripts/core/filesystem_runtime.py",
            "ops/scripts/mechanism/mechanism_run_workspace_runtime.py",
        ),
        derive_generated_at=_payload_generated_at,
    ),
    "raw-intake-absorption-matrix-2026-04-22.json": ArchivedRunArtifactSpec(
        filename="raw-intake-absorption-matrix-2026-04-22.json",
        schema_path=RAW_INTAKE_ABSORPTION_MATRIX_SCHEMA_PATH,
        artifact_kind="raw_intake_absorption_matrix",
        source_paths=(
            SCRIPT_PATH,
            "mk/registry.mk",
            "ops/scripts/registry/raw_intake_route_proposal.py",
            "ops/scripts/registry/raw_intake_source_quality.py",
        ),
        derive_generated_at=_raw_intake_generated_at,
    ),
    "source-english-summary-slug-manifest-2026-04-22.json": ArchivedRunArtifactSpec(
        filename="source-english-summary-slug-manifest-2026-04-22.json",
        schema_path=SOURCE_SLUG_CURATION_MANIFEST_SCHEMA_PATH,
        artifact_kind="source_slug_curation_manifest",
        source_paths=(SCRIPT_PATH, "ops/scripts/core/source_slug_curation.py"),
        derive_generated_at=_raw_intake_generated_at,
    ),
    "raw-intake-promotion-profiles-2026-04-22.json": ArchivedRunArtifactSpec(
        filename="raw-intake-promotion-profiles-2026-04-22.json",
        schema_path=RAW_INTAKE_PROMOTION_PROFILE_BUNDLE_SCHEMA_PATH,
        artifact_kind="raw_intake_promotion_profile_bundle",
        source_paths=(
            SCRIPT_PATH,
            "ops/scripts/registry/raw_intake_promotion_scaffold_runtime.py",
        ),
        derive_generated_at=_raw_intake_generated_at,
    ),
    "raw-intake-promotion-render-after-concept-integration-2026-04-22.json": ArchivedRunArtifactSpec(
        filename="raw-intake-promotion-render-after-concept-integration-2026-04-22.json",
        schema_path=RAW_INTAKE_PROMOTION_REPORT_SCHEMA_PATH,
        artifact_kind="raw_intake_promotion_report",
        source_paths=(SCRIPT_PATH, "ops/scripts/registry/raw_intake_promotion.py"),
        derive_generated_at=_raw_intake_generated_at,
    ),
    "raw-intake-promotion-validate-after-concept-integration-2026-04-22.json": ArchivedRunArtifactSpec(
        filename="raw-intake-promotion-validate-after-concept-integration-2026-04-22.json",
        schema_path=RAW_INTAKE_PROMOTION_REPORT_SCHEMA_PATH,
        artifact_kind="raw_intake_promotion_report",
        source_paths=(
            SCRIPT_PATH,
            "ops/scripts/registry/raw_intake_promotion_validation_runtime.py",
        ),
        derive_generated_at=_raw_intake_generated_at,
    ),
    "raw-intake-promotion-validate-final-tree-2026-04-22.json": ArchivedRunArtifactSpec(
        filename="raw-intake-promotion-validate-final-tree-2026-04-22.json",
        schema_path=RAW_INTAKE_PROMOTION_REPORT_SCHEMA_PATH,
        artifact_kind="raw_intake_promotion_report",
        source_paths=(
            SCRIPT_PATH,
            "ops/scripts/registry/raw_intake_promotion_validation_runtime.py",
        ),
        derive_generated_at=_raw_intake_generated_at,
    ),
    "source-english-summary-slug-validate-final-tree-2026-04-22.json": ArchivedRunArtifactSpec(
        filename="source-english-summary-slug-validate-final-tree-2026-04-22.json",
        schema_path=SOURCE_SLUG_CURATION_VALIDATION_REPORT_SCHEMA_PATH,
        artifact_kind="source_slug_curation_validation_report",
        source_paths=(SCRIPT_PATH, "ops/scripts/core/source_slug_curation.py"),
        derive_generated_at=_raw_intake_generated_at,
    ),
    "raw-registry-preflight-final-tree-2026-04-22.json": ArchivedRunArtifactSpec(
        filename="raw-registry-preflight-final-tree-2026-04-22.json",
        schema_path=RAW_INTAKE_FINAL_TREE_VALIDATION_REPORT_SCHEMA_PATH,
        artifact_kind="raw_intake_final_tree_validation_report",
        source_paths=(SCRIPT_PATH, "ops/scripts/registry/raw_registry_preflight.py"),
        derive_generated_at=_raw_intake_generated_at,
    ),
    "wiki-lint-final-tree-2026-04-22.json": ArchivedRunArtifactSpec(
        filename="wiki-lint-final-tree-2026-04-22.json",
        schema_path=RAW_INTAKE_FINAL_TREE_VALIDATION_REPORT_SCHEMA_PATH,
        artifact_kind="raw_intake_final_tree_validation_report",
        source_paths=(SCRIPT_PATH, "ops/scripts/eval/wiki_lint.py"),
        derive_generated_at=_raw_intake_generated_at,
    ),
    "wiki-stage2-final-tree-2026-04-22.json": ArchivedRunArtifactSpec(
        filename="wiki-stage2-final-tree-2026-04-22.json",
        schema_path=RAW_INTAKE_FINAL_TREE_VALIDATION_REPORT_SCHEMA_PATH,
        artifact_kind="raw_intake_final_tree_validation_report",
        source_paths=(SCRIPT_PATH, "ops/scripts/eval/wiki_stage2_eval.py"),
        derive_generated_at=_raw_intake_generated_at,
    ),
}


def _source_command(rel_path: str) -> str:
    return f"python -m ops.scripts.backfill_archived_run_artifacts --vault . --path {rel_path}"


def _metadata_properties(payload: dict[str, Any]) -> list[dict[str, str]]:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return []
    properties = metadata.get("properties")
    if not isinstance(properties, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in properties:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if isinstance(name, str) and isinstance(value, str):
            normalized.append({"name": name, "value": value})
    return normalized


def _embedded_envelope_text(payload: dict[str, Any]) -> str | None:
    for item in _metadata_properties(payload):
        if item.get("name") == EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY:
            value = item.get("value")
            if isinstance(value, str) and value.strip():
                return value
    return None


def _has_artifact_envelope(payload: dict[str, Any]) -> bool:
    if all(field in payload for field in ENVELOPE_REQUIRED_FIELDS):
        return True
    embedded_text = _embedded_envelope_text(payload)
    if not embedded_text:
        return False
    try:
        embedded_payload = json.loads(embedded_text)
    except json.JSONDecodeError:
        return False
    return isinstance(embedded_payload, dict) and all(field in embedded_payload for field in ENVELOPE_REQUIRED_FIELDS)


def _set_metadata_property(payload: dict[str, Any], *, name: str, value: str) -> dict[str, Any]:
    properties = [item for item in _metadata_properties(payload) if item.get("name") != name]
    properties.append({"name": name, "value": value})
    normalized = dict(payload)
    normalized["metadata"] = {"properties": sorted(properties, key=lambda item: item["name"])}
    return normalized


def _validate_existing_payload(vault: Path, rel_path: str, payload: dict[str, Any], schema_path: str) -> None:
    schema = load_schema_with_vault_override(vault, schema_path)
    errors = validate_with_schema(payload, schema)
    if errors:
        joined = "; ".join(errors)
        raise ValueError(f"{rel_path} does not validate before backfill: {joined}")


def _backfill_provenance_block(
    *,
    rel_path: str,
    generated_at: str,
    generated_at_source: str,
    normalized_at: str,
) -> dict[str, Any]:
    return {
        "archive_reason": ARCHIVE_REASON,
        "source_artifact": rel_path,
        "generated_at": generated_at,
        "generated_at_source": generated_at_source,
        "normalized_at": normalized_at,
        "helper": PRODUCER,
        "envelope_mode": "metadata.properties",
    }


def _build_backfilled_payload(
    vault: Path,
    *,
    artifact_path: Path,
    rel_path: str,
    payload: dict[str, Any],
    original_text: str,
    spec: ArchivedRunArtifactSpec,
    generated_at: str,
    generated_at_source: str,
    normalized_at: str,
    resolved_policy_path: Path,
) -> dict[str, Any]:
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind=spec.artifact_kind,
        producer=PRODUCER,
        source_command=_source_command(rel_path),
        resolved_policy_path=resolved_policy_path,
        schema_path=spec.schema_path,
        source_paths=list(spec.source_paths),
        text_inputs={
            "archived_run_payload_before_backfill": original_text,
            "target_rel_path": rel_path,
            "generated_at_source": generated_at_source,
            "envelope_mode": "metadata.properties",
        },
    )
    envelope["artifact_status"] = "archived"
    envelope["retention_policy"] = "archive"
    envelope["currentness"] = {
        "status": "current",
        "checked_at": normalized_at,
    }
    embedded_envelope = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
    provenance = json.dumps(
        _backfill_provenance_block(
            rel_path=rel_path,
            generated_at=generated_at,
            generated_at_source=generated_at_source,
            normalized_at=normalized_at,
        ),
        ensure_ascii=False,
        sort_keys=True,
    )
    backfilled = _set_metadata_property(
        payload,
        name=EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY,
        value=embedded_envelope,
    )
    return _set_metadata_property(
        backfilled,
        name=BACKFILL_PROVENANCE_PROPERTY,
        value=provenance,
    )


def _is_supported_run_artifact_path(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/")
    return normalized.startswith("runs/") and "/tmp/" not in normalized


def _is_archive_run_artifact_path(rel_path: str) -> bool:
    return rel_path.replace("\\", "/").startswith("runs/archive/")


def _archived_run_artifact_spec_for_filename(filename: str) -> ArchivedRunArtifactSpec | None:
    spec = ARCHIVED_RUN_ARTIFACT_SPECS.get(filename)
    if spec is not None:
        return spec
    if filename.startswith("promotion-report.") and filename.endswith(".json"):
        return ARCHIVED_RUN_ARTIFACT_SPECS["promotion-report.json"]
    if filename.endswith("-timeout-failure.json"):
        return ARCHIVED_RUN_ARTIFACT_SPECS["timeout-failure.json"]
    return None


def run_artifact_spec_for_filename(filename: str) -> ArchivedRunArtifactSpec | None:
    return _archived_run_artifact_spec_for_filename(filename)


def derive_run_artifact_generated_at(
    vault: Path,
    artifact_path: Path,
    rel_path: str,
    payload: dict[str, Any],
    *,
    spec: ArchivedRunArtifactSpec | None = None,
) -> tuple[str, str]:
    resolved_spec = spec or _archived_run_artifact_spec_for_filename(artifact_path.name)
    if resolved_spec is None:
        raise ValueError(f"unsupported run artifact path: {rel_path}")
    return resolved_spec.derive_generated_at(vault, artifact_path, rel_path, payload)


def _discover_supported_rel_paths(vault: Path) -> list[str]:
    scan_root = vault / RUN_ARTIFACT_SCAN_ROOT
    if not scan_root.exists():
        return []
    discovered: list[str] = []
    for path in sorted(scan_root.rglob("*.json")):
        if _archived_run_artifact_spec_for_filename(path.name) is None:
            continue
        rel_path = _report_path(vault, path)
        if _is_supported_run_artifact_path(rel_path):
            discovered.append(rel_path)
    return discovered


def backfill_archived_run_artifacts(
    vault: Path,
    rel_paths: list[str] | None = None,
    *,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> list[str]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    normalized_at = runtime_context.isoformat_z()
    target_rel_paths = rel_paths or _discover_supported_rel_paths(vault)
    written: list[str] = []
    for rel_path in target_rel_paths:
        artifact_path = vault / rel_path
        spec = _archived_run_artifact_spec_for_filename(artifact_path.name)
        if spec is None:
            raise ValueError(f"unsupported run artifact path: {rel_path}")
        if not _is_supported_run_artifact_path(rel_path):
            raise ValueError(f"run artifact backfill only supports runs/ paths: {rel_path}")
        original_text = artifact_path.read_text(encoding="utf-8")
        original_payload = read_json_object(artifact_path, context=rel_path)
        payload = _normalize_legacy_run_telemetry_payload(vault, rel_path, original_payload)
        _validate_existing_payload(vault, rel_path, payload, spec.schema_path)
        if _has_artifact_envelope(payload):
            if payload != original_payload:
                schema = load_schema_with_vault_override(vault, spec.schema_path)
                write_schema_validated_json(
                    artifact_path,
                    payload,
                    schema,
                    context=rel_path,
                    trailing_newline=True,
                )
                written.append(_report_path(vault, artifact_path))
            continue
        generated_at, generated_at_source = spec.derive_generated_at(vault, artifact_path, rel_path, payload)
        backfilled_payload = _build_backfilled_payload(
            vault,
            artifact_path=artifact_path,
            rel_path=rel_path,
            payload=payload,
            original_text=original_text,
            spec=spec,
            generated_at=generated_at,
            generated_at_source=generated_at_source,
            normalized_at=normalized_at,
            resolved_policy_path=resolved_policy_path,
        )
        schema = load_schema_with_vault_override(vault, spec.schema_path)
        write_schema_validated_json(
            artifact_path,
            backfilled_payload,
            schema,
            context=rel_path,
            trailing_newline=True,
        )
        written.append(_report_path(vault, artifact_path))
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=(
            "Embed canonical artifact envelopes into schema-backed historical run artifacts "
            "that cannot safely accept top-level envelope fields."
        )
    )
    ap.add_argument("--vault", type=Path, default=Path("."))
    ap.add_argument(
        "--path",
        dest="paths",
        action="append",
        help=(
            "Specific run artifact path(s) to backfill in place. "
            "Defaults to all supported JSON artifacts under runs/."
        ),
    )
    ap.add_argument("--policy-path")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    written = backfill_archived_run_artifacts(
        args.vault,
        rel_paths=args.paths,
        policy_path=args.policy_path,
    )
    for rel_path in written:
        print(display_path(args.vault, args.vault / rel_path))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
