from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from .artifact_envelope_runtime import (
    CanonicalReportEnvelopeRequest,
    artifact_input_fingerprints,
    build_canonical_report_envelope,
    resolve_artifact_path as _resolve_artifact_path,
)
from .artifact_freshness_debt_runtime import (
    MTIME_SENSITIVE_ISSUES,
    OPERATIONAL_ATTENTION_ISSUES,
    ROOT_EPHEMERAL_PATTERNS,
    STABLE_CONTRACT_ISSUES,
    artifact_freshness_gate_effect,
    artifact_freshness_status,
    artifact_record_gate_effect,
    contract_issue_class,
    debt_queues,
    is_run_local_artifact,
    matching_issues,
    owner_surface,
    owner_surface_rollup,
    recommended_next_action,
    report_next_action,
    stale_routing,
    top_debt,
    top_debt_files,
)
from .artifact_freshness_mtime_runtime import (
    format_mtime as _format_mtime,
    load_zip_info_mtimes,
    mtime_for_source as _mtime_for_source,
    parse_generated_at as _parse_generated_at,
    zip_info_mtimes as _zip_info_mtimes,
)
from .artifact_freshness_payload_runtime import (
    EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY,
    ENVELOPE_REQUIRED_FIELDS,
    canonical_artifact_payload,
    canonical_report_loading_issue,
    computed_currentness_status as _computed_currentness_status,
    currentness_status as _currentness_status,
    embed_artifact_envelope_metadata,
    has_artifact_envelope as _has_artifact_envelope,
    normalized_artifact_payload as _normalized_artifact_payload,
)
from .artifact_freshness_schema_runtime import (
    NONCANONICAL_ARCHIVED_RUN_AUXILIARY_FILENAMES,
    NONCANONICAL_JSON_ARCHIVE_PATHS,
    RAW_INTAKE_RUN_ARTIFACT_PREFIX,
    SCHEMALESS_HISTORICAL_BOOTSTRAP_REPORTS,
    is_noncanonical_json_archive_path as _is_noncanonical_json_archive_path,
    safe_to_backfill as _safe_to_backfill,
    schema_contract as _schema_contract,
)
from .artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    write_schema_backed_report,
)
from .output_runtime import display_path
from .policy_runtime import load_policy, report_path
from .runtime_context import RuntimeContext
from .schema_constants_runtime import ARTIFACT_FRESHNESS_REPORT_SCHEMA_PATH
from .schema_runtime import (
    build_validator_for_schema,
    load_schema_with_vault_override,
    validate_with_schema,
    validate_with_validator,
)
from .source_revision_runtime import resolve_source_revision
from .source_tree_fingerprint_runtime import release_source_tree_fingerprint

DEFAULT_OUT = "ops/reports/artifact-freshness-report.json"
PRODUCER = "ops.scripts.artifact_freshness_runtime"
SOURCE_COMMAND = "python -m ops.scripts.artifact_freshness_runtime"
JSON_ARTIFACT_GLOBS = [
    "ops/reports/**/*.json",
    "ops/operator/**/*.json",
    "external-reports/report-reference-manifest.json",
    "runs/**/*.json",
]
TEXT_ARTIFACT_GLOBS = [
    "ops/reports/**/*.json",
    "ops/operator/**/*.json",
    "external-reports/**/*.md",
    "runs/**/*.json",
    *ROOT_EPHEMERAL_PATTERNS,
]
RUN_LOG_PLACEHOLDER_GLOBS = [
    "runs/**/mutation-command.stdout.txt",
    "runs/**/mutation-command.stderr.txt",
    "runs/**/repo-health.stdout.txt",
    "runs/**/repo-health.stderr.txt",
]
MTIME_SOURCES = (
    "filesystem",
    "zip_info",
    "embedded_currentness",
)
_MTIME_COMPAT_EXPORTS = (
    load_zip_info_mtimes,
)
_PAYLOAD_COMPAT_EXPORTS = (
    EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY,
    ENVELOPE_REQUIRED_FIELDS,
    canonical_artifact_payload,
    canonical_report_loading_issue,
    embed_artifact_envelope_metadata,
)
PROGRESS_FORMATS = ("none", "jsonl", "jsonl-stable")
OWNER_VERIFIED_NON_GRAPH_FRESHNESS_EXCLUSION_PATHS = {
    "ops/reports/archive-execution-manifest.json",
    "ops/reports/make-target-inventory.json",
    "ops/reports/release-closeout-finality-attestation.json",
    "ops/reports/release-closeout-fixed-point.json",
    "ops/reports/release-workflow-order-guard.json",
    "ops/reports/workflow-dependency-planner.json",
}
_SCHEMA_COMPAT_EXPORTS = (
    NONCANONICAL_ARCHIVED_RUN_AUXILIARY_FILENAMES,
    NONCANONICAL_JSON_ARCHIVE_PATHS,
    RAW_INTAKE_RUN_ARTIFACT_PREFIX,
    SCHEMALESS_HISTORICAL_BOOTSTRAP_REPORTS,
)


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "missing"


@dataclass(frozen=True)
class _ArtifactFreshnessScanInputs:
    policy: dict[str, Any]
    resolved_policy_path: Path
    runtime_context: RuntimeContext
    resolved_zip_metadata_path: Path | None
    text_paths: list[Path]
    json_paths: list[Path]
    root_ephemeral: list[dict[str, str]]
    run_log_placeholders: list[dict[str, Any]]
    non_utf8: list[dict[str, Any]]
    artifact_records: list[dict[str, Any]]
    phase_timings: list[dict[str, Any]]


@dataclass(frozen=True)
class _ArtifactFreshnessCountSummary:
    stale_count: int
    unknown_currentness_count: int
    source_revision_provenance_only_count: int
    missing_schema_count: int
    missing_envelope_count: int
    schema_invalid_count: int
    schema_unavailable_count: int
    mtime_sensitive_count: int
    safe_to_backfill_count: int
    stable_contract_debt_artifact_count: int
    stable_contract_debt_issue_count: int
    mtime_sensitive_attention_artifact_count: int
    mtime_sensitive_attention_issue_count: int
    operational_attention_artifact_count: int
    operational_attention_issue_count: int


@dataclass(frozen=True)
class _ArtifactRecordCurrentnessState:
    declared_currentness_status: str
    source_tree_fingerprint_status: str
    source_revision_status: str
    input_fingerprint_status: str
    input_fingerprint_mismatch_keys: list[str]
    currentness_status: str
    issues: list[str]


@dataclass(frozen=True)
class _ArtifactRecordPayloadInputs:
    rel_path: str
    fields: dict[str, Any]
    normalized_payload: dict[str, Any]
    currentness: _ArtifactRecordCurrentnessState
    source_mtime: dt.datetime | None
    mtime_source: str
    mtime_status: str
    mtime_sensitive: bool
    schema_validation_status: str
    schema_validation_errors: list[str]
    safe_to_backfill: bool
    issues: list[str]
    stable_contract_issues: list[str]
    mtime_sensitive_issues: list[str]


@dataclass
class ArtifactFreshnessContext:
    vault: Path
    progress_format: str = "none"
    progress_stream: TextIO = field(default_factory=lambda: sys.stderr)
    schema_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    validator_cache: dict[str, Any] = field(default_factory=dict)
    source_revision_cache: str | None = None
    source_tree_fingerprint_cache: str | None = None
    phase_timings: list[dict[str, Any]] = field(default_factory=list)
    started_at: float = field(default_factory=time.perf_counter)

    def emit_progress(
        self,
        phase: str,
        *,
        done: int = 0,
        total: int = 0,
        current_path: str = "",
    ) -> None:
        if self.progress_format not in {"jsonl", "jsonl-stable"}:
            return
        event = {
            "phase": phase,
            "done": done,
            "total": total,
            "elapsed_seconds": round(time.perf_counter() - self.started_at, 3),
            "current_path": current_path,
        }
        print(json.dumps(event, sort_keys=True), file=self.progress_stream, flush=True)

    def record_phase_timing(
        self,
        phase: str,
        started_at: float,
        *,
        done: int = 0,
        total: int = 0,
        current_path: str = "",
    ) -> None:
        elapsed_seconds = (
            round(max(0.0, time.perf_counter() - started_at), 6)
            if self.progress_format == "jsonl"
            else 0.0
        )
        self.phase_timings.append(
            {
                "phase": phase,
                "elapsed_seconds": elapsed_seconds,
                "done": done,
                "total": total,
            }
        )
        self.emit_progress(phase, done=done, total=total, current_path=current_path)

    def schema_for(self, schema_path: str) -> dict[str, Any]:
        cached = self.schema_cache.get(schema_path)
        if cached is None:
            cached = load_schema_with_vault_override(self.vault, schema_path)
            self.schema_cache[schema_path] = cached
        return cached

    def validator_for(self, schema_path: str) -> Any:
        cached = self.validator_cache.get(schema_path)
        if cached is None:
            cached = build_validator_for_schema(self.schema_for(schema_path))
            self.validator_cache[schema_path] = cached
        return cached

    def validate_payload(self, payload: dict[str, Any]) -> tuple[str, list[str]]:
        schema_path = payload.get("$schema")
        if not isinstance(schema_path, str) or not schema_path.strip():
            return "missing_schema", ["missing $schema"]
        try:
            validator = self.validator_for(schema_path)
        except (OSError, ValueError, json.JSONDecodeError, ModuleNotFoundError) as exc:
            return "schema_unavailable", [f"schema load failed for {schema_path}: {exc.__class__.__name__}"]
        try:
            errors = validate_with_validator(payload, validator)
        except ValueError as exc:
            return "schema_unavailable", [f"schema validation setup failed for {schema_path}: {exc.__class__.__name__}"]
        if errors:
            return "fail", errors
        return "pass", []

    def current_source_tree_fingerprint(self) -> str:
        if self.source_tree_fingerprint_cache is None:
            self.source_tree_fingerprint_cache = release_source_tree_fingerprint(self.vault)
        return self.source_tree_fingerprint_cache

    def current_source_revision(self) -> str:
        if self.source_revision_cache is None:
            self.source_revision_cache = resolve_source_revision(self.vault).revision
        return self.source_revision_cache


def _input_fingerprints(vault: Path, policy_path: Path) -> dict[str, str]:
    return artifact_input_fingerprints(
        vault,
        resolved_policy_path=policy_path,
        schema_path=ARTIFACT_FRESHNESS_REPORT_SCHEMA_PATH,
        text_inputs={
            "root_ephemeral_patterns": "\n".join(ROOT_EPHEMERAL_PATTERNS),
        },
    )


def _glob_files(vault: Path, pattern: str) -> list[Path]:
    return sorted(path for path in vault.glob(pattern) if path.is_file())


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in sorted(paths):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _root_ephemeral_artifacts(vault: Path) -> list[dict[str, str]]:
    offenders: list[dict[str, str]] = []
    for pattern in ROOT_EPHEMERAL_PATTERNS:
        for path in _glob_files(vault, pattern):
            offenders.append(
                {
                    "path": report_path(vault, path),
                    "matched_pattern": pattern,
                }
            )
    return sorted(offenders, key=lambda item: (item["path"], item["matched_pattern"]))


def _run_log_placeholders(vault: Path) -> list[dict[str, Any]]:
    placeholders: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pattern in RUN_LOG_PLACEHOLDER_GLOBS:
        for path in _glob_files(vault, pattern):
            rel_path = report_path(vault, path)
            if rel_path in seen:
                continue
            seen.add(rel_path)
            try:
                size_bytes = path.stat().st_size
            except OSError:
                continue
            if size_bytes != 0:
                continue
            placeholders.append(
                {
                    "path": rel_path,
                    "artifact_role": "run_log_placeholder",
                    "size_bytes": size_bytes,
                    "classification": "empty_run_command_log_placeholder",
                }
            )
    return sorted(placeholders, key=lambda item: item["path"])


def _owner_verified_freshness_exclusion_paths(vault: Path) -> set[str]:
    from ops.scripts.release.release_closeout_fixed_point import (
        fixed_point_output_paths_at_or_downstream,
    )

    return OWNER_VERIFIED_NON_GRAPH_FRESHNESS_EXCLUSION_PATHS | (
        fixed_point_output_paths_at_or_downstream(vault, "artifact-freshness")
    )


def _text_artifact_paths(vault: Path) -> list[Path]:
    excluded_paths = _owner_verified_freshness_exclusion_paths(vault)
    paths: list[Path] = []
    for pattern in TEXT_ARTIFACT_GLOBS:
        paths.extend(_glob_files(vault, pattern))
    return [
        path
        for path in _unique_paths(paths)
        if report_path(vault, path) not in excluded_paths
    ]


def _json_artifact_paths(vault: Path) -> list[Path]:
    excluded_paths = _owner_verified_freshness_exclusion_paths(vault)
    paths: list[Path] = []
    for pattern in JSON_ARTIFACT_GLOBS:
        paths.extend(_glob_files(vault, pattern))
    return [
        path
        for path in _unique_paths(paths)
        if report_path(vault, path) not in excluded_paths
    ]


def _non_utf8_text_artifacts(vault: Path, paths: list[Path]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for path in paths:
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            issues.append({"path": report_path(vault, path), "issue": "utf8_decode_failed"})
        except OSError as exc:
            issues.append({"path": report_path(vault, path), "issue": f"read_failed:{exc.__class__.__name__}"})
    return issues


def mtime_for_artifact_source(
    path: Path,
    rel_path: str,
    *,
    mtime_source: str,
    zip_mtimes: Mapping[str, dt.datetime],
) -> dt.datetime | None:
    return _mtime_for_source(path, rel_path, mtime_source=mtime_source, zip_mtimes=zip_mtimes)


def format_artifact_mtime(value: dt.datetime | None) -> str:
    return _format_mtime(value)


def _archive_retention_exempts_mtime(payload: dict[str, Any]) -> bool:
    normalized_payload = _normalized_artifact_payload(payload)
    artifact_status = str(normalized_payload.get("artifact_status", "")).strip()
    retention_policy = str(normalized_payload.get("retention_policy", "")).strip()
    return artifact_status == "archived" and retention_policy == "archive"


def _mtime_status(
    path: Path,
    rel_path: str,
    generated_at: str,
    *,
    payload: dict[str, Any] | None = None,
    mtime_source: str,
    zip_mtimes: Mapping[str, dt.datetime],
) -> str:
    if payload and _archive_retention_exempts_mtime(payload):
        return "current"
    if mtime_source == "embedded_currentness":
        return "unknown"
    parsed_generated_at = _parse_generated_at(generated_at)
    mtime = _mtime_for_source(path, rel_path, mtime_source=mtime_source, zip_mtimes=zip_mtimes)
    if parsed_generated_at is None or mtime is None:
        return "unknown"
    if mtime.replace(microsecond=0) > parsed_generated_at.replace(microsecond=0):
        return "stale"
    return "current"


def _test_target_fingerprints(payload: dict[str, Any]) -> list[dict[str, str]]:
    if str(payload.get("artifact_kind", "")).strip() != "test_execution_summary":
        return []
    targets = payload.get("test_target_fingerprints")
    if not isinstance(targets, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in targets:
        if not isinstance(item, dict):
            continue
        rel_path = str(item.get("path", "")).strip()
        sha256 = str(item.get("sha256", "")).strip()
        if rel_path:
            normalized.append({"path": rel_path, "sha256": sha256})
    return normalized


def _test_target_mtime_status(
    vault: Path,
    generated_at: str,
    payload: dict[str, Any],
    *,
    mtime_source: str,
    zip_mtimes: Mapping[str, dt.datetime],
) -> str:
    if mtime_source == "embedded_currentness":
        return "current"
    parsed_generated_at = _parse_generated_at(generated_at)
    if parsed_generated_at is None:
        return "unknown"
    for target in _test_target_fingerprints(payload):
        mtime = _mtime_for_source(
            vault / target["path"],
            target["path"],
            mtime_source=mtime_source,
            zip_mtimes=zip_mtimes,
        )
        if mtime is None:
            continue
        if mtime.replace(microsecond=0) > parsed_generated_at.replace(microsecond=0):
            return "stale"
    return "current"


def _test_target_fingerprint_issues(vault: Path, payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for target in _test_target_fingerprints(payload):
        path = vault / target["path"]
        if not path.is_file():
            issues.append(f"test_target_missing:{target['path']}")
            continue
        if _sha256_file(path) != target["sha256"]:
            issues.append(f"test_target_fingerprint_mismatch:{target['path']}")
    return issues


def _requires_source_tree_fingerprint_check(rel_path: str) -> bool:
    if not rel_path.startswith("ops/reports/"):
        return False
    report_name = rel_path.removeprefix("ops/reports/")
    return "/" not in report_name


def _requires_canonical_currentness_check(rel_path: str) -> bool:
    return (
        _requires_source_tree_fingerprint_check(rel_path)
        or rel_path == "external-reports/report-reference-manifest.json"
    )


def _source_tree_fingerprint_status(
    *,
    vault: Path,
    rel_path: str,
    normalized_payload: dict[str, Any],
    schema_validation_status: str,
    freshness_context: ArtifactFreshnessContext | None,
) -> str:
    if not _requires_canonical_currentness_check(rel_path):
        return "not_applicable"
    if schema_validation_status != "pass":
        return "not_applicable"
    if str(normalized_payload.get("artifact_status", "")).strip() != "current":
        return "not_applicable"
    if str(normalized_payload.get("retention_policy", "")).strip() != "canonical_report":
        return "not_applicable"
    observed = str(normalized_payload.get("source_tree_fingerprint", "")).strip()
    if not observed:
        return "unknown"
    current = (
        freshness_context.current_source_tree_fingerprint()
        if freshness_context is not None
        else release_source_tree_fingerprint(vault)
    )
    return "current" if observed == current else "stale"


def _source_revision_status(
    *,
    vault: Path,
    rel_path: str,
    normalized_payload: dict[str, Any],
    schema_validation_status: str,
    freshness_context: ArtifactFreshnessContext | None,
) -> str:
    if not _requires_canonical_currentness_check(rel_path):
        return "not_applicable"
    if schema_validation_status != "pass":
        return "not_applicable"
    if str(normalized_payload.get("artifact_status", "")).strip() != "current":
        return "not_applicable"
    if str(normalized_payload.get("retention_policy", "")).strip() != "canonical_report":
        return "not_applicable"
    observed = str(normalized_payload.get("source_revision", "")).strip()
    if not observed:
        return "unknown"
    current = (
        freshness_context.current_source_revision()
        if freshness_context is not None
        else resolve_source_revision(vault).revision
    )
    if observed == current:
        return "current"
    return "provenance_only"


def _schema_validation(
    vault: Path,
    payload: dict[str, Any],
    freshness_context: ArtifactFreshnessContext | None = None,
) -> tuple[str, list[str]]:
    if freshness_context is not None:
        return freshness_context.validate_payload(payload)
    schema_path = payload.get("$schema")
    if not isinstance(schema_path, str) or not schema_path.strip():
        return "missing_schema", ["missing $schema"]
    try:
        schema = load_schema_with_vault_override(vault, schema_path)
    except (OSError, ValueError, json.JSONDecodeError, ModuleNotFoundError) as exc:
        return "schema_unavailable", [f"schema load failed for {schema_path}: {exc.__class__.__name__}"]
    try:
        errors = validate_with_schema(payload, schema)
    except ValueError as exc:
        return "schema_unavailable", [f"schema validation setup failed for {schema_path}: {exc.__class__.__name__}"]
    if errors:
        return "fail", errors
    return "pass", []


def _read_json_artifact_payload(path: Path) -> tuple[dict[str, Any], bool, bool, list[str]]:
    payload: dict[str, Any] = {}
    issues: list[str] = []
    text = ""
    utf8_ok = True
    json_ok = True
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        utf8_ok = False
        json_ok = False
        issues.append("utf8_decode_failed")
    except OSError as exc:
        utf8_ok = False
        json_ok = False
        issues.append(f"read_failed:{exc.__class__.__name__}")

    if utf8_ok:
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            json_ok = False
            issues.append("json_decode_failed")
        else:
            if isinstance(decoded, dict):
                payload = decoded
            else:
                json_ok = False
                issues.append("json_root_not_object")

    return payload, utf8_ok, json_ok, issues


def _artifact_record_fields(
    payload: dict[str, Any],
    *,
    noncanonical_archive: bool,
) -> dict[str, Any]:
    normalized_payload = _normalized_artifact_payload(payload)
    generated_at = str(normalized_payload.get("generated_at", "")).strip()
    artifact_status = str(normalized_payload.get("artifact_status", "")).strip()
    retention_policy = str(normalized_payload.get("retention_policy", "")).strip()
    currentness_status = _currentness_status(normalized_payload) if normalized_payload else "unknown"
    if noncanonical_archive:
        currentness_status = "not_applicable"
        artifact_status = artifact_status or "archived"
        retention_policy = retention_policy or "archive"
    return {
        "normalized_payload": normalized_payload,
        "generated_at": generated_at,
        "artifact_status": artifact_status,
        "retention_policy": retention_policy,
        "currentness_status": currentness_status,
        "has_schema": "$schema" in payload,
        "has_generated_at": bool(generated_at),
        "has_envelope": _has_artifact_envelope(normalized_payload),
    }


def _append_artifact_record_contract_issues(
    issues: list[str],
    *,
    noncanonical_archive: bool,
    has_schema: bool,
    has_generated_at: bool,
    has_envelope: bool,
    currentness_status: str,
) -> None:
    if noncanonical_archive:
        return
    if not has_schema:
        issues.append("missing_schema")
    if not has_generated_at:
        issues.append("missing_generated_at")
    if not has_envelope:
        issues.append("missing_artifact_envelope")
    if currentness_status == "unknown":
        issues.append("unknown_currentness")


def _artifact_record_mtime_state(
    vault: Path,
    path: Path,
    *,
    rel_path: str,
    generated_at: str,
    normalized_payload: dict[str, Any],
    noncanonical_archive: bool,
    mtime_source: str,
    zip_mtimes: Mapping[str, dt.datetime],
) -> tuple[dt.datetime | None, str, list[str]]:
    source_mtime = _mtime_for_source(path, rel_path, mtime_source=mtime_source, zip_mtimes=zip_mtimes)
    if noncanonical_archive:
        return source_mtime, "current", []

    mtime_status = _mtime_status(
        path,
        rel_path,
        generated_at,
        payload=normalized_payload,
        mtime_source=mtime_source,
        zip_mtimes=zip_mtimes,
    )
    if mtime_status == "current":
        mtime_status = _test_target_mtime_status(
            vault,
            generated_at,
            normalized_payload,
            mtime_source=mtime_source,
            zip_mtimes=zip_mtimes,
        )
    mtime_sensitive_issues = (
        ["generated_at_older_than_file_mtime"] if mtime_status == "stale" else []
    )
    return source_mtime, mtime_status, mtime_sensitive_issues


def _artifact_record_schema_state(
    vault: Path,
    rel_path: str,
    payload: dict[str, Any],
    *,
    noncanonical_archive: bool,
    freshness_context: ArtifactFreshnessContext | None,
) -> tuple[str, list[str], list[str]]:
    schema_validation_status = "not_applicable"
    schema_validation_errors: list[str] = []
    issues: list[str] = []
    if payload and not noncanonical_archive:
        schema_validation_status, schema_validation_errors = _schema_validation(
            vault,
            payload,
            freshness_context,
        )
        if schema_validation_status == "fail":
            issues.append("schema_validation_failed")
            if is_run_local_artifact(rel_path):
                schema_validation_status = "historical_schema_drift"
        elif schema_validation_status == "schema_unavailable":
            issues.append("schema_unavailable")
    return schema_validation_status, schema_validation_errors, issues


def _artifact_record_currentness_state(
    vault: Path,
    *,
    rel_path: str,
    normalized_payload: dict[str, Any],
    declared_currentness_status: str,
    schema_validation_status: str,
    freshness_context: ArtifactFreshnessContext | None,
) -> _ArtifactRecordCurrentnessState:
    source_tree_fingerprint_status = _source_tree_fingerprint_status(
        vault=vault,
        rel_path=rel_path,
        normalized_payload=normalized_payload,
        schema_validation_status=schema_validation_status,
        freshness_context=freshness_context,
    )
    source_revision_status = _source_revision_status(
        vault=vault,
        rel_path=rel_path,
        normalized_payload=normalized_payload,
        schema_validation_status=schema_validation_status,
        freshness_context=freshness_context,
    )
    input_fingerprint_status = "not_applicable"
    input_fingerprint_mismatch_keys: list[str] = []
    currentness_status = _computed_currentness_status(
        declared_currentness_status=declared_currentness_status,
        source_tree_fingerprint_status=source_tree_fingerprint_status,
        source_revision_status=source_revision_status,
        input_fingerprint_status=input_fingerprint_status,
    )
    issues: list[str] = []
    if source_tree_fingerprint_status == "stale":
        issues.append("source_tree_fingerprint_mismatch")
    elif source_tree_fingerprint_status == "unknown":
        issues.append("source_tree_fingerprint_unknown")
    if source_revision_status == "unknown":
        issues.append("source_revision_unknown")
    if input_fingerprint_status == "stale":
        issues.extend(
            f"input_fingerprint_mismatch:{key}"
            for key in input_fingerprint_mismatch_keys
        )
    elif input_fingerprint_status == "unknown":
        issues.append("input_fingerprint_unknown")
    return _ArtifactRecordCurrentnessState(
        declared_currentness_status=declared_currentness_status,
        source_tree_fingerprint_status=source_tree_fingerprint_status,
        source_revision_status=source_revision_status,
        input_fingerprint_status=input_fingerprint_status,
        input_fingerprint_mismatch_keys=input_fingerprint_mismatch_keys,
        currentness_status=currentness_status,
        issues=issues,
    )


def _json_artifact_record_payload(inputs: _ArtifactRecordPayloadInputs) -> dict[str, Any]:
    fields = inputs.fields
    rel_path = inputs.rel_path
    return {
        "path": rel_path,
        "owner_surface": owner_surface(rel_path),
        "artifact_kind": str(inputs.normalized_payload.get("artifact_kind", "json_artifact")).strip()
        or "json_artifact",
        "utf8_ok": bool(fields["utf8_ok"]),
        "json_ok": bool(fields["json_ok"]),
        "has_schema": bool(fields["has_schema"]),
        "has_generated_at": bool(fields["has_generated_at"]),
        "has_artifact_envelope": bool(fields["has_envelope"]),
        "generated_at": str(fields["generated_at"]),
        "artifact_status": str(fields["artifact_status"]),
        "retention_policy": str(fields["retention_policy"]),
        "declared_currentness_status": inputs.currentness.declared_currentness_status,
        "source_revision_status": inputs.currentness.source_revision_status,
        "source_tree_fingerprint_status": inputs.currentness.source_tree_fingerprint_status,
        "input_fingerprint_status": inputs.currentness.input_fingerprint_status,
        "input_fingerprint_mismatch_keys": inputs.currentness.input_fingerprint_mismatch_keys,
        "currentness_status": inputs.currentness.currentness_status,
        "file_mtime_utc": _format_mtime(inputs.source_mtime),
        "mtime_source": inputs.mtime_source,
        "mtime_status": inputs.mtime_status,
        "mtime_sensitive": inputs.mtime_sensitive,
        "schema_validation_status": inputs.schema_validation_status,
        "schema_validation_errors": inputs.schema_validation_errors,
        "safe_to_backfill": inputs.safe_to_backfill,
        "recommended_next_action": recommended_next_action(
            inputs.issues,
            inputs.schema_validation_status,
            rel_path=rel_path,
        ),
        "contract_issue_class": contract_issue_class(
            rel_path=rel_path,
            issues=inputs.issues,
            stable_contract_issues=inputs.stable_contract_issues,
            mtime_sensitive_issues=inputs.mtime_sensitive_issues,
            schema_validation_status=inputs.schema_validation_status,
        ),
        "gate_effect": artifact_record_gate_effect(
            rel_path=rel_path,
            issues=inputs.issues,
            stable_contract_issues=inputs.stable_contract_issues,
            mtime_sensitive_issues=inputs.mtime_sensitive_issues,
        ),
        "stable_contract_issues": inputs.stable_contract_issues,
        "mtime_sensitive_issues": inputs.mtime_sensitive_issues,
        "schema_contract": _schema_contract(
            rel_path,
            has_schema=bool(fields["has_schema"]),
            schema_validation_status=inputs.schema_validation_status,
        ),
        "issues": inputs.issues,
    }


def _json_artifact_record(
    vault: Path,
    path: Path,
    *,
    mtime_source: str,
    zip_mtimes: Mapping[str, dt.datetime],
    freshness_context: ArtifactFreshnessContext | None = None,
) -> dict[str, Any]:
    rel_path = report_path(vault, path)
    noncanonical_archive = _is_noncanonical_json_archive_path(rel_path)
    payload, utf8_ok, json_ok, issues = _read_json_artifact_payload(path)
    fields = _artifact_record_fields(payload, noncanonical_archive=noncanonical_archive)
    normalized_payload = fields["normalized_payload"]
    generated_at = str(fields["generated_at"])
    currentness_status = str(fields["currentness_status"])
    _append_artifact_record_contract_issues(
        issues,
        noncanonical_archive=noncanonical_archive,
        has_schema=bool(fields["has_schema"]),
        has_generated_at=bool(fields["has_generated_at"]),
        has_envelope=bool(fields["has_envelope"]),
        currentness_status=currentness_status,
    )
    source_mtime, mtime_status, mtime_sensitive_issues = _artifact_record_mtime_state(
        vault,
        path,
        rel_path=rel_path,
        generated_at=generated_at,
        normalized_payload=normalized_payload,
        noncanonical_archive=noncanonical_archive,
        mtime_source=mtime_source,
        zip_mtimes=zip_mtimes,
    )
    if mtime_status == "stale":
        issues.append("generated_at_older_than_file_mtime")
    if not noncanonical_archive:
        issues.extend(_test_target_fingerprint_issues(vault, normalized_payload))
    schema_validation_status, schema_validation_errors, schema_issues = _artifact_record_schema_state(
        vault,
        rel_path,
        payload,
        noncanonical_archive=noncanonical_archive,
        freshness_context=freshness_context,
    )
    issues.extend(schema_issues)
    currentness = _artifact_record_currentness_state(
        vault=vault,
        rel_path=rel_path,
        normalized_payload=normalized_payload,
        declared_currentness_status=currentness_status,
        schema_validation_status=schema_validation_status,
        freshness_context=freshness_context,
    )
    issues.extend(currentness.issues)
    safe_to_backfill = _safe_to_backfill(
        utf8_ok=utf8_ok,
        json_ok=json_ok,
        schema_validation_status=schema_validation_status,
        mtime_status=mtime_status,
    ) and (
        currentness.source_tree_fingerprint_status != "stale"
        and currentness.input_fingerprint_status != "stale"
    )
    mtime_sensitive = mtime_status == "stale"
    issues = sorted(set(issues))
    stable_contract_issues = matching_issues(issues, STABLE_CONTRACT_ISSUES)
    mtime_sensitive_issues = sorted(set(mtime_sensitive_issues + matching_issues(issues, MTIME_SENSITIVE_ISSUES)))

    return _json_artifact_record_payload(
        _ArtifactRecordPayloadInputs(
            rel_path=rel_path,
            fields={**fields, "utf8_ok": utf8_ok, "json_ok": json_ok},
            normalized_payload=normalized_payload,
            currentness=currentness,
            source_mtime=source_mtime,
            mtime_source=mtime_source,
            mtime_status=mtime_status,
            mtime_sensitive=mtime_sensitive,
            schema_validation_status=schema_validation_status,
            schema_validation_errors=schema_validation_errors,
            safe_to_backfill=safe_to_backfill,
            issues=issues,
            stable_contract_issues=stable_contract_issues,
            mtime_sensitive_issues=mtime_sensitive_issues,
        )
    )


def _collect_artifact_freshness_scan_inputs(
    vault: Path,
    *,
    policy_path: str | None,
    context: RuntimeContext | None,
    mtime_source: str,
    zip_metadata_path: str | Path | None,
    progress: str = "none",
) -> _ArtifactFreshnessScanInputs:
    freshness_context = ArtifactFreshnessContext(vault=vault, progress_format=progress)
    started_at = time.perf_counter()
    policy, resolved_policy_path = load_policy(vault, policy_path)
    freshness_context.record_phase_timing("policy_load", started_at)
    runtime_context = context or RuntimeContext.from_policy(policy)
    resolved_zip_metadata_path = (
        _resolve_artifact_path(vault, zip_metadata_path) if zip_metadata_path is not None else None
    )
    started_at = time.perf_counter()
    zip_mtimes = _zip_info_mtimes(resolved_zip_metadata_path) if resolved_zip_metadata_path is not None else {}
    freshness_context.record_phase_timing("zip_metadata_load", started_at, done=len(zip_mtimes), total=len(zip_mtimes))
    started_at = time.perf_counter()
    text_paths = _text_artifact_paths(vault)
    json_paths = _json_artifact_paths(vault)
    freshness_context.record_phase_timing(
        "artifact_path_scan",
        started_at,
        done=len(text_paths) + len(json_paths),
        total=len(text_paths) + len(json_paths),
    )
    started_at = time.perf_counter()
    root_ephemeral = _root_ephemeral_artifacts(vault)
    run_log_placeholders = _run_log_placeholders(vault)
    non_utf8 = _non_utf8_text_artifacts(vault, text_paths)
    freshness_context.record_phase_timing(
        "text_artifact_scan",
        started_at,
        done=len(text_paths),
        total=len(text_paths),
    )
    artifact_records: list[dict[str, Any]] = []
    total_json_paths = len(json_paths)
    started_at = time.perf_counter()
    freshness_context.emit_progress("json_schema_validation", done=0, total=total_json_paths)
    for index, path in enumerate(json_paths, start=1):
        artifact_records.append(
            _json_artifact_record(
                vault,
                path,
                mtime_source=mtime_source,
                zip_mtimes=zip_mtimes,
                freshness_context=freshness_context,
            )
        )
        if index == total_json_paths or index % 100 == 0:
            freshness_context.emit_progress(
                "json_schema_validation",
                done=index,
                total=total_json_paths,
                current_path=report_path(vault, path),
            )
    freshness_context.record_phase_timing(
        "json_schema_validation",
        started_at,
        done=total_json_paths,
        total=total_json_paths,
    )
    return _ArtifactFreshnessScanInputs(
        policy=policy,
        resolved_policy_path=resolved_policy_path,
        runtime_context=runtime_context,
        resolved_zip_metadata_path=resolved_zip_metadata_path,
        text_paths=text_paths,
        json_paths=json_paths,
        root_ephemeral=root_ephemeral,
        run_log_placeholders=run_log_placeholders,
        non_utf8=non_utf8,
        artifact_records=artifact_records,
        phase_timings=freshness_context.phase_timings,
    )


def _summarize_artifact_freshness_counts(
    artifact_records: list[dict[str, Any]],
) -> _ArtifactFreshnessCountSummary:
    return _ArtifactFreshnessCountSummary(
        stale_count=sum(
            1
            for record in artifact_records
            if record["currentness_status"] == "stale"
            or "generated_at_older_than_file_mtime" in record["issues"]
        ),
        unknown_currentness_count=sum(
            1
            for record in artifact_records
            if record["currentness_status"] == "unknown"
            or "unknown_currentness" in record["issues"]
        ),
        source_revision_provenance_only_count=sum(
            1
            for record in artifact_records
            if record["source_revision_status"] == "provenance_only"
        ),
        missing_schema_count=sum(1 for record in artifact_records if "missing_schema" in record["issues"]),
        missing_envelope_count=sum(
            1 for record in artifact_records if "missing_artifact_envelope" in record["issues"]
        ),
        schema_invalid_count=sum(
            1 for record in artifact_records if record["schema_validation_status"] == "fail"
        ),
        schema_unavailable_count=sum(
            1 for record in artifact_records if record["schema_validation_status"] == "schema_unavailable"
        ),
        mtime_sensitive_count=sum(1 for record in artifact_records if record["mtime_sensitive"]),
        safe_to_backfill_count=sum(1 for record in artifact_records if record["safe_to_backfill"]),
        stable_contract_debt_artifact_count=sum(
            1 for record in artifact_records if record["stable_contract_issues"]
        ),
        stable_contract_debt_issue_count=sum(
            len(record["stable_contract_issues"]) for record in artifact_records
        ),
        mtime_sensitive_attention_artifact_count=sum(
            1 for record in artifact_records if record["mtime_sensitive_issues"]
        ),
        mtime_sensitive_attention_issue_count=sum(
            len(record["mtime_sensitive_issues"]) for record in artifact_records
        ),
        operational_attention_artifact_count=sum(
            1
            for record in artifact_records
            if matching_issues(record["issues"], OPERATIONAL_ATTENTION_ISSUES)
        ),
        operational_attention_issue_count=sum(
            len(matching_issues(record["issues"], OPERATIONAL_ATTENTION_ISSUES))
            for record in artifact_records
        ),
    )


def _artifact_freshness_summary_payload(
    scan_inputs: _ArtifactFreshnessScanInputs,
    counts: _ArtifactFreshnessCountSummary,
) -> dict[str, int]:
    return {
        "artifact_count": len(scan_inputs.artifact_records),
        "json_artifact_count": len(scan_inputs.json_paths),
        "scanned_text_artifact_count": len(scan_inputs.text_paths),
        "stale_artifact_count": counts.stale_count,
        "mtime_sensitive_artifact_count": counts.mtime_sensitive_count,
        "root_ephemeral_artifact_count": len(scan_inputs.root_ephemeral),
        "run_log_placeholder_count": len(scan_inputs.run_log_placeholders),
        "unknown_currentness_artifact_count": counts.unknown_currentness_count,
        "source_revision_provenance_only_artifact_count": (
            counts.source_revision_provenance_only_count
        ),
        "non_utf8_text_artifact_count": len(scan_inputs.non_utf8),
        "missing_schema_count": counts.missing_schema_count,
        "missing_artifact_envelope_count": counts.missing_envelope_count,
        "schema_invalid_artifact_count": counts.schema_invalid_count,
        "schema_unavailable_artifact_count": counts.schema_unavailable_count,
        "safe_to_backfill_artifact_count": counts.safe_to_backfill_count,
        "stable_contract_debt_artifact_count": counts.stable_contract_debt_artifact_count,
        "stable_contract_debt_issue_count": counts.stable_contract_debt_issue_count,
        "mtime_sensitive_attention_artifact_count": counts.mtime_sensitive_attention_artifact_count,
        "mtime_sensitive_attention_issue_count": counts.mtime_sensitive_attention_issue_count,
        "operational_attention_artifact_count": counts.operational_attention_artifact_count,
        "operational_attention_issue_count": counts.operational_attention_issue_count,
    }


def _assemble_artifact_freshness_payload(
    vault: Path,
    *,
    scan_inputs: _ArtifactFreshnessScanInputs,
    counts: _ArtifactFreshnessCountSummary,
    source_command: str,
    mtime_source: str,
) -> dict[str, Any]:
    report_status = artifact_freshness_status(
        root_ephemeral_count=len(scan_inputs.root_ephemeral),
        non_utf8_count=len(scan_inputs.non_utf8),
        missing_envelope_count=counts.missing_envelope_count,
        missing_schema_count=counts.missing_schema_count,
        stale_count=counts.stale_count,
        unknown_currentness_count=counts.unknown_currentness_count,
        schema_invalid_count=counts.schema_invalid_count,
        schema_unavailable_count=counts.schema_unavailable_count,
    )
    generated_at = scan_inputs.runtime_context.isoformat_z()
    envelope_request = CanonicalReportEnvelopeRequest(
        vault=vault,
        generated_at=generated_at,
        artifact_kind="artifact_freshness_report",
        producer=PRODUCER,
        source_command=source_command,
        resolved_policy_path=scan_inputs.resolved_policy_path,
        schema_path=ARTIFACT_FRESHNESS_REPORT_SCHEMA_PATH,
        source_paths=[
            "ops/scripts/core/artifact_freshness_runtime.py",
            "ops/scripts/core/artifact_freshness_debt_runtime.py",
        ],
        file_inputs=(
            {"zip_metadata": scan_inputs.resolved_zip_metadata_path}
            if scan_inputs.resolved_zip_metadata_path is not None
            else None
        ),
        text_inputs={
            "mtime_source": mtime_source,
            "root_ephemeral_patterns": "\n".join(ROOT_EPHEMERAL_PATTERNS),
        },
    )
    return {
        **build_canonical_report_envelope(envelope_request),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, scan_inputs.resolved_policy_path),
            "version": scan_inputs.policy.get("version"),
        },
        "mtime_source": mtime_source,
        "zip_metadata_path": (
            report_path(vault, scan_inputs.resolved_zip_metadata_path)
            if scan_inputs.resolved_zip_metadata_path is not None
            else ""
        ),
        "status": report_status,
        "gate_effect": artifact_freshness_gate_effect(
            root_ephemeral=scan_inputs.root_ephemeral,
            non_utf8=scan_inputs.non_utf8,
            artifact_records=scan_inputs.artifact_records,
        ),
        "recommended_next_action": report_next_action(
            root_ephemeral_count=len(scan_inputs.root_ephemeral),
            non_utf8_count=len(scan_inputs.non_utf8),
            schema_invalid_count=counts.schema_invalid_count,
            missing_envelope_count=counts.missing_envelope_count,
            missing_schema_count=counts.missing_schema_count,
            stale_count=counts.stale_count,
            unknown_currentness_count=counts.unknown_currentness_count,
        ),
        "stale_routing": stale_routing(
            scan_inputs.artifact_records,
            root_ephemeral_count=len(scan_inputs.root_ephemeral),
            non_utf8_count=len(scan_inputs.non_utf8),
        ),
        "safe_to_backfill": counts.safe_to_backfill_count > 0
        and counts.schema_invalid_count == 0
        and not scan_inputs.non_utf8,
        "mtime_sensitive": counts.mtime_sensitive_count > 0,
        "summary": _artifact_freshness_summary_payload(scan_inputs, counts),
        "top_debt": top_debt(
            scan_inputs.artifact_records,
            scan_inputs.root_ephemeral,
            scan_inputs.non_utf8,
        ),
        "top_debt_files": top_debt_files(
            scan_inputs.artifact_records,
            scan_inputs.root_ephemeral,
            scan_inputs.non_utf8,
        ),
        "debt_queues": debt_queues(scan_inputs.artifact_records),
        "owner_surface": owner_surface_rollup(scan_inputs.artifact_records),
        "phase_timings": scan_inputs.phase_timings,
        "root_ephemeral_patterns": ROOT_EPHEMERAL_PATTERNS,
        "root_ephemeral_artifacts": scan_inputs.root_ephemeral,
        "run_log_placeholders": scan_inputs.run_log_placeholders,
        "non_utf8_text_artifacts": scan_inputs.non_utf8,
        "artifact_records": scan_inputs.artifact_records,
    }


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
    source_command: str = SOURCE_COMMAND,
    mtime_source: str = "filesystem",
    zip_metadata_path: str | Path | None = None,
    progress: str = "none",
) -> dict[str, Any]:
    if mtime_source not in MTIME_SOURCES:
        raise ValueError(f"unsupported mtime_source: {mtime_source}")
    if progress not in PROGRESS_FORMATS:
        raise ValueError(f"unsupported progress format: {progress}")
    if mtime_source == "zip_info" and zip_metadata_path is None:
        raise ValueError("zip_metadata_path is required when mtime_source is zip_info")
    scan_inputs = _collect_artifact_freshness_scan_inputs(
        vault,
        policy_path=policy_path,
        context=context,
        mtime_source=mtime_source,
        zip_metadata_path=zip_metadata_path,
        progress=progress,
    )
    counts = _summarize_artifact_freshness_counts(scan_inputs.artifact_records)
    return _assemble_artifact_freshness_payload(
        vault,
        scan_inputs=scan_inputs,
        counts=counts,
        source_command=source_command,
        mtime_source=mtime_source,
    )


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=ARTIFACT_FRESHNESS_REPORT_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="artifact freshness report schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report generated artifact freshness and root ephemeral test artifacts")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--mtime-source", choices=MTIME_SOURCES, default="filesystem")
    parser.add_argument("--zip-metadata")
    parser.add_argument("--progress", choices=PROGRESS_FORMATS, default="none")
    parser.add_argument("--fail-on-fail", action="store_true")
    parser.add_argument("--fail-on-attention", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        vault,
        policy_path=args.policy_path,
        mtime_source=args.mtime_source,
        zip_metadata_path=args.zip_metadata,
        progress=args.progress,
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    if args.fail_on_attention and report["status"] != "pass":
        return 1
    if args.fail_on_fail and report["status"] == "fail":
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
