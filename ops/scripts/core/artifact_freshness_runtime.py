from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import sys
import time
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

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
ARTIFACT_ENVELOPE_SCHEMA_PATH = "ops/schemas/artifact-envelope.schema.json"
ROOT_EPHEMERAL_PATTERNS = [
    "pytest_*.log",
    "pytest_*.xml",
    "pytest_*_output.txt",
    "pytest_*_requested*.txt",
]
JSON_ARTIFACT_GLOBS = [
    "ops/reports/**/*.json",
    "ops/operator/**/*.json",
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
ENVELOPE_REQUIRED_FIELDS = [
    "$schema",
    "artifact_kind",
    "generated_at",
    "producer",
    "source_command",
    "source_revision",
    "source_tree_fingerprint",
    "input_fingerprints",
    "schema_version",
    "artifact_status",
    "retention_policy",
    "encoding",
    "currentness",
]
TOP_DEBT_LIMIT = 10
TOP_DEBT_FILE_LIMIT = 10
DEBT_QUEUE_PATH_LIMIT = 20
OWNER_SURFACE_PREFIXES = (
    ("ops/reports/", "ops_reports"),
    ("ops/operator/", "operator_reports"),
    ("runs/", "runs"),
    ("external-reports/", "external_reports"),
)
EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY = "urn:openai:artifact-envelope"
STABLE_CONTRACT_ISSUES = (
    "missing_artifact_envelope",
    "unknown_currentness",
    "missing_schema",
    "schema_validation_failed",
    "schema_unavailable",
)
MTIME_SENSITIVE_ISSUES = (
    "generated_at_older_than_file_mtime",
)
MTIME_SOURCES = (
    "filesystem",
    "zip_info",
    "embedded_currentness",
)
PROGRESS_FORMATS = ("none", "jsonl")
ADVISORY_ONLY_MTIME_DRIFT_PATHS = {
    "ops/reports/generated-artifact-index.json",
}
TEST_TARGET_FINGERPRINT_ISSUES = (
    "test_target_fingerprint_mismatch",
    "test_target_missing",
)
SCHEMALESS_HISTORICAL_BOOTSTRAP_REPORTS = {
    "ops/reports/eval-initial-2026-04-12.json",
    "ops/reports/lint-initial-2026-04-12.json",
    "ops/reports/manifest-2026-04-12.json",
    "ops/reports/archive/eval-initial-2026-04-12.json",
    "ops/reports/archive/lint-initial-2026-04-12.json",
    "ops/reports/archive/manifest-2026-04-12.json",
}
RAW_INTAKE_RUN_ARTIFACT_PREFIX = "runs/run-20260422-raw-intake-registration-and-promotion/"
NONCANONICAL_JSON_ARCHIVE_PATHS = {
    (
        "runs/run-20260422-raw-intake-registration-and-promotion/"
        "promotion/concept-continuity-integration-2026-04-22.json"
    ),
    (
        "runs/run-20260422-raw-intake-registration-and-promotion/"
        "registration/source-english-summary-reregistration-2026-04-22.json"
    ),
}
NONCANONICAL_ARCHIVED_RUN_AUXILIARY_FILENAMES = {
    "scope-freeze.json",
    "subagent-routing.validator.json",
    "subagent-routing.worker.json",
    "validator-executor-report.json",
    "validator-last-message.json",
    "worker-executor-report.json",
    "worker-last-message.json",
}
NON_SEALING_ARTIFACT_PATHS = {
    "ops/reports/archive-execution-manifest.json",
    "ops/reports/make-target-inventory.json",
    "ops/reports/release-closeout-batch-manifest.json",
    "ops/reports/release-evidence-closeout-self-check.json",
    "ops/reports/release-workflow-order-guard.json",
    "ops/reports/workflow-dependency-planner.json",
}


def _is_noncanonical_json_archive_path(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/")
    if normalized in NONCANONICAL_JSON_ARCHIVE_PATHS:
        return True
    if not normalized.startswith("runs/"):
        return False
    filename = Path(normalized).name
    if filename in NONCANONICAL_ARCHIVED_RUN_AUXILIARY_FILENAMES:
        return True
    if filename.startswith("subagent-routing.") and filename.endswith(".json"):
        return True
    if filename.endswith("-executor-report.json"):
        return True
    return bool(filename.endswith("-last-message.json"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "missing"


def _fingerprint_paths(vault: Path, rel_paths: list[str]) -> str:
    digest = hashlib.sha256()
    for rel_path in sorted(rel_paths):
        path = vault / rel_path
        digest.update(rel_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _canonical_source_path(vault: Path, rel_path: str) -> str:
    normalized = Path(rel_path).as_posix()
    if (vault / normalized).exists():
        return normalized
    parts = normalized.split("/")
    if len(parts) == 3 and parts[:2] == ["ops", "scripts"] and parts[2].endswith(".py"):
        matches = sorted((vault / "ops" / "scripts").glob(f"*/{parts[2]}"))
        if len(matches) == 1:
            return report_path(vault, matches[0])
    return normalized


def _canonical_source_paths(vault: Path, rel_paths: Sequence[str]) -> list[str]:
    canonical: dict[str, None] = {}
    for rel_path in rel_paths:
        normalized = str(rel_path).strip()
        if not normalized:
            continue
        canonical[_canonical_source_path(vault, normalized)] = None
    return sorted(canonical)


def _resolve_artifact_path(vault: Path, path: str | Path) -> Path:
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    return (vault / resolved).resolve()


@dataclass(frozen=True)
class CanonicalReportEnvelopeRequest:
    vault: Path
    generated_at: str
    artifact_kind: str
    producer: str
    source_command: str
    resolved_policy_path: Path
    schema_path: str
    source_paths: list[str]
    file_inputs: Mapping[str, str | Path] | None = None
    path_group_inputs: Mapping[str, list[str]] | None = None
    text_inputs: Mapping[str, str] | None = None
    source_tree_excluded_files: tuple[str, ...] = ()

    @classmethod
    def from_legacy_args(
        cls,
        vault: Path,
        **legacy_kwargs: Any,
    ) -> CanonicalReportEnvelopeRequest:
        required_keys = {
            "generated_at",
            "artifact_kind",
            "producer",
            "source_command",
            "resolved_policy_path",
            "schema_path",
            "source_paths",
        }
        optional_keys = {
            "file_inputs",
            "path_group_inputs",
            "text_inputs",
            "source_tree_excluded_files",
        }
        missing = sorted(required_keys - legacy_kwargs.keys())
        unexpected = sorted(set(legacy_kwargs) - required_keys - optional_keys)
        if missing:
            raise TypeError(f"missing legacy envelope arguments: {', '.join(missing)}")
        if unexpected:
            raise TypeError(f"unexpected legacy envelope arguments: {', '.join(unexpected)}")
        return cls(
            vault=vault,
            generated_at=str(legacy_kwargs["generated_at"]),
            artifact_kind=str(legacy_kwargs["artifact_kind"]),
            producer=str(legacy_kwargs["producer"]),
            source_command=str(legacy_kwargs["source_command"]),
            resolved_policy_path=Path(legacy_kwargs["resolved_policy_path"]),
            schema_path=str(legacy_kwargs["schema_path"]),
            source_paths=[str(path) for path in legacy_kwargs["source_paths"]],
            file_inputs=legacy_kwargs.get("file_inputs"),
            path_group_inputs=legacy_kwargs.get("path_group_inputs"),
            text_inputs=legacy_kwargs.get("text_inputs"),
            source_tree_excluded_files=tuple(legacy_kwargs.get("source_tree_excluded_files", ())),
        )


def _coerce_canonical_report_envelope_request(
    request: CanonicalReportEnvelopeRequest | Path,
    **legacy_kwargs: Any,
) -> CanonicalReportEnvelopeRequest:
    if isinstance(request, CanonicalReportEnvelopeRequest):
        if legacy_kwargs:
            unexpected = ", ".join(sorted(legacy_kwargs))
            raise TypeError(f"unexpected legacy envelope arguments with request object: {unexpected}")
        return request
    return CanonicalReportEnvelopeRequest.from_legacy_args(Path(request), **legacy_kwargs)


def artifact_input_fingerprints(
    vault: Path,
    *,
    resolved_policy_path: Path,
    schema_path: str,
    source_paths: Sequence[str] | None = None,
    file_inputs: Mapping[str, str | Path] | None = None,
    path_group_inputs: Mapping[str, list[str]] | None = None,
    text_inputs: Mapping[str, str] | None = None,
) -> dict[str, str]:
    fingerprints = {
        "policy": _sha256_file(resolved_policy_path),
        "schema": _sha256_file(vault / schema_path),
        "artifact_envelope_schema": _sha256_file(vault / ARTIFACT_ENVELOPE_SCHEMA_PATH),
    }
    if source_paths is not None:
        fingerprints["source_paths"] = _fingerprint_paths(
            vault,
            _canonical_source_paths(vault, source_paths),
        )
    for name, path in sorted((file_inputs or {}).items()):
        fingerprints[str(name)] = _sha256_file(_resolve_artifact_path(vault, path))
    for name, rel_paths in sorted((path_group_inputs or {}).items()):
        fingerprints[str(name)] = _fingerprint_paths(vault, [str(item) for item in rel_paths])
    for name, text in sorted((text_inputs or {}).items()):
        fingerprints[str(name)] = _sha256_text(str(text))
    return fingerprints


def build_canonical_report_envelope(
    request: CanonicalReportEnvelopeRequest | Path,
    **legacy_kwargs: Any,
) -> dict[str, Any]:
    envelope_request = _coerce_canonical_report_envelope_request(request, **legacy_kwargs)
    source_revision = resolve_source_revision(envelope_request.vault)
    return {
        "$schema": envelope_request.schema_path,
        "artifact_kind": envelope_request.artifact_kind,
        "generated_at": envelope_request.generated_at,
        "producer": envelope_request.producer,
        "source_command": envelope_request.source_command,
        "source_revision": source_revision.revision,
        "source_tree_fingerprint": release_source_tree_fingerprint(
            envelope_request.vault,
            extra_excluded_files=envelope_request.source_tree_excluded_files,
        ),
        "input_fingerprints": artifact_input_fingerprints(
        envelope_request.vault,
        resolved_policy_path=envelope_request.resolved_policy_path,
        schema_path=envelope_request.schema_path,
        source_paths=envelope_request.source_paths,
        file_inputs=envelope_request.file_inputs,
        path_group_inputs=envelope_request.path_group_inputs,
        text_inputs=envelope_request.text_inputs,
        ),
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "canonical_report",
        "encoding": "utf-8",
        "currentness": {
            "status": "current",
            "checked_at": envelope_request.generated_at,
        },
    }


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


@dataclass
class ArtifactFreshnessContext:
    vault: Path
    progress_format: str = "none"
    progress_stream: TextIO = field(default_factory=lambda: sys.stderr)
    schema_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    validator_cache: dict[str, Any] = field(default_factory=dict)
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
        if self.progress_format != "jsonl":
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
        self.phase_timings.append(
            {
                "phase": phase,
                "elapsed_seconds": 0.0,
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


def _text_artifact_paths(vault: Path) -> list[Path]:
    paths: list[Path] = []
    for pattern in TEXT_ARTIFACT_GLOBS:
        paths.extend(_glob_files(vault, pattern))
    return [
        path
        for path in _unique_paths(paths)
        if report_path(vault, path) not in NON_SEALING_ARTIFACT_PATHS
    ]


def _json_artifact_paths(vault: Path) -> list[Path]:
    paths: list[Path] = []
    for pattern in JSON_ARTIFACT_GLOBS:
        paths.extend(_glob_files(vault, pattern))
    return [
        path
        for path in _unique_paths(paths)
        if report_path(vault, path) not in NON_SEALING_ARTIFACT_PATHS
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


def _parse_generated_at(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.UTC)
    except ValueError:
        return None


def _mtime_utc(path: Path) -> dt.datetime | None:
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.UTC)
    except OSError:
        return None


def _zip_info_mtime(info: zipfile.ZipInfo) -> dt.datetime:
    return dt.datetime(*info.date_time, tzinfo=dt.UTC)


def _normalize_zip_member_path(path: str) -> str:
    normalized = path.replace("\\", "/").lstrip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _zip_info_mtimes(zip_metadata_path: Path) -> dict[str, dt.datetime]:
    mtimes: dict[str, dt.datetime] = {}
    with zipfile.ZipFile(zip_metadata_path) as archive:
        for info in archive.infolist():
            rel_path = _normalize_zip_member_path(info.filename)
            if not rel_path or rel_path.endswith("/"):
                continue
            current = mtimes.get(rel_path)
            candidate = _zip_info_mtime(info)
            if current is None or candidate > current:
                mtimes[rel_path] = candidate
    return mtimes


def load_zip_info_mtimes(zip_metadata_path: Path | None) -> dict[str, dt.datetime]:
    if zip_metadata_path is None:
        return {}
    return _zip_info_mtimes(zip_metadata_path)


def _mtime_for_source(path: Path, rel_path: str, *, mtime_source: str, zip_mtimes: Mapping[str, dt.datetime]) -> dt.datetime | None:
    if mtime_source == "filesystem":
        return _mtime_utc(path)
    if mtime_source == "zip_info":
        return zip_mtimes.get(rel_path)
    if mtime_source == "embedded_currentness":
        return None
    raise ValueError(f"unsupported mtime_source: {mtime_source}")


def mtime_for_artifact_source(
    path: Path,
    rel_path: str,
    *,
    mtime_source: str,
    zip_mtimes: Mapping[str, dt.datetime],
) -> dt.datetime | None:
    return _mtime_for_source(path, rel_path, mtime_source=mtime_source, zip_mtimes=zip_mtimes)


def _format_mtime(value: dt.datetime | None) -> str:
    if value is None:
        return ""
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _owner_surface(rel_path: str) -> str:
    for prefix, surface in OWNER_SURFACE_PREFIXES:
        if rel_path.startswith(prefix):
            return surface
    if any(fnmatch.fnmatch(rel_path, pattern) for pattern in ROOT_EPHEMERAL_PATTERNS):
        return "root_ephemeral"
    return "repo_root"


def _currentness_status(payload: dict[str, Any]) -> str:
    normalized_payload = _normalized_artifact_payload(payload)
    currentness = normalized_payload.get("currentness")
    if not isinstance(currentness, dict):
        return "unknown"
    status = str(currentness.get("status", "")).strip()
    return status or "unknown"


def _has_artifact_envelope(payload: dict[str, Any]) -> bool:
    normalized_payload = _normalized_artifact_payload(payload)
    if not all(field in normalized_payload for field in ENVELOPE_REQUIRED_FIELDS):
        return False
    currentness = normalized_payload.get("currentness")
    input_fingerprints = normalized_payload.get("input_fingerprints")
    return isinstance(currentness, dict) and isinstance(input_fingerprints, dict)


def _artifact_metadata_properties(payload: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return []
    properties = metadata.get("properties")
    if not isinstance(properties, list):
        return []
    return [item for item in properties if isinstance(item, dict)]


def embed_artifact_envelope_metadata(payload: dict[str, Any], envelope: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    normalized_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    properties = normalized_metadata.get("properties")
    normalized_properties = [
        item
        for item in properties
        if isinstance(item, dict) and str(item.get("name", "")).strip() != EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY
    ] if isinstance(properties, list) else []
    normalized_properties.append(
        {
            "name": EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY,
            "value": json.dumps(envelope, ensure_ascii=False, sort_keys=True),
        }
    )
    normalized_metadata["properties"] = sorted(
        normalized_properties,
        key=lambda item: str(item.get("name", "")),
    )
    normalized = dict(payload)
    normalized["metadata"] = normalized_metadata
    return normalized


def _embedded_artifact_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    for item in _artifact_metadata_properties(payload):
        name = str(item.get("name", "")).strip()
        if name != EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY:
            continue
        value = item.get("value")
        if not isinstance(value, str) or not value.strip():
            return {}
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _envelope_field_missing(field: str, value: Any) -> bool:
    if value is None:
        return True
    if field in {"currentness", "input_fingerprints"}:
        return not isinstance(value, dict)
    return not str(value).strip()


def _normalized_artifact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return payload
    embedded_envelope = _embedded_artifact_envelope(payload)
    if not embedded_envelope:
        return payload
    normalized = dict(payload)
    for envelope_field in ENVELOPE_REQUIRED_FIELDS:
        if envelope_field not in embedded_envelope:
            continue
        if _envelope_field_missing(envelope_field, normalized.get(envelope_field)):
            normalized[envelope_field] = embedded_envelope[envelope_field]
    return normalized


def canonical_artifact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _normalized_artifact_payload(payload)


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


def _schema_contract(
    rel_path: str,
    *,
    has_schema: bool,
    schema_validation_status: str,
) -> dict[str, str]:
    if _is_noncanonical_json_archive_path(rel_path):
        return {
            "status": "not_applicable",
            "classification": "noncanonical_archived_run_note",
            "reason": (
                "auxiliary run JSON is retained for audit context "
                "but is not canonical release evidence"
            ),
            "recommended_next_action": "none",
        }
    if has_schema:
        if schema_validation_status == "pass":
            return {
                "status": "present",
                "classification": "schema_backed",
                "reason": "artifact declares a loadable schema and validates against it",
                "recommended_next_action": "none",
            }
        if schema_validation_status == "fail":
            return {
                "status": "invalid",
                "classification": "schema_invalid",
                "reason": "artifact declares a schema but current payload fails validation",
                "recommended_next_action": "regenerate_artifact_from_current_schema",
            }
        if schema_validation_status == "schema_unavailable":
            return {
                "status": "unavailable",
                "classification": "schema_reference_unavailable",
                "reason": "artifact declares a schema path or URI that cannot be loaded in this vault",
                "recommended_next_action": "add_schema_or_exclude_noncanonical_json",
            }
        return {
            "status": "not_applicable",
            "classification": "schema_not_applicable",
            "reason": "artifact payload was not schema-validated",
            "recommended_next_action": "none",
        }

    if rel_path in SCHEMALESS_HISTORICAL_BOOTSTRAP_REPORTS:
        return {
            "status": "missing",
            "classification": "historical_bootstrap_report_pending_schema_decision",
            "reason": "bootstrap ops report predates the generated artifact schema contract",
            "recommended_next_action": "add_schema_or_exclude_noncanonical_json",
        }
    if rel_path == "ops/reports/review-archive-report.json":
        return {
            "status": "missing",
            "classification": "review_archive_report_pending_schema_decision",
            "reason": "review archive report is generated but has no declared schema contract yet",
            "recommended_next_action": "add_schema_or_exclude_noncanonical_json",
        }
    if rel_path.startswith(RAW_INTAKE_RUN_ARTIFACT_PREFIX):
        return {
            "status": "missing",
            "classification": "raw_intake_run_artifact_family_pending_schema",
            "reason": "raw-intake run artifact belongs to a family that needs shared schema or archive classification",
            "recommended_next_action": "add_schema_or_exclude_noncanonical_json",
        }
    if rel_path.startswith("runs/"):
        return {
            "status": "missing",
            "classification": "run_artifact_pending_schema_decision",
            "reason": "run-local JSON artifact lacks a declared schema or noncanonical archive classification",
            "recommended_next_action": "add_schema_or_exclude_noncanonical_json",
        }
    if rel_path.startswith("ops/reports/"):
        return {
            "status": "missing",
            "classification": "ops_report_pending_schema_decision",
            "reason": "ops report lacks a declared schema or noncanonical archive classification",
            "recommended_next_action": "add_schema_or_exclude_noncanonical_json",
        }
    if rel_path.startswith("ops/operator/"):
        return {
            "status": "missing",
            "classification": "operator_report_pending_schema_decision",
            "reason": "operator report lacks a declared schema or noncanonical archive classification",
            "recommended_next_action": "add_schema_or_exclude_noncanonical_json",
        }
    return {
        "status": "missing",
        "classification": "json_artifact_pending_schema_decision",
        "reason": "JSON artifact lacks a declared schema or noncanonical classification",
        "recommended_next_action": "add_schema_or_exclude_noncanonical_json",
    }


def _recommended_next_action(issues: list[str], schema_validation_status: str) -> str:
    if any(issue.startswith(("read_failed", "utf8_decode_failed", "json_decode_failed")) for issue in issues):
        return "repair_or_remove_unreadable_artifact"
    if schema_validation_status == "fail":
        return "regenerate_artifact_from_current_schema"
    if "missing_artifact_envelope" in issues:
        return "backfill_artifact_envelope"
    if "missing_schema" in issues or schema_validation_status == "schema_unavailable":
        return "add_schema_or_exclude_noncanonical_json"
    if _matching_issues(issues, TEST_TARGET_FINGERPRINT_ISSUES):
        return "regenerate_test_execution_summary"
    if "generated_at_older_than_file_mtime" in issues:
        return "regenerate_artifact_or_refresh_timestamp"
    if "missing_generated_at" in issues:
        return "backfill_generated_at_or_mark_legacy_noncanonical"
    if "unknown_currentness" in issues:
        return "backfill_currentness_metadata"
    return "none"


def _matching_issues(issues: list[str], prefixes: tuple[str, ...]) -> list[str]:
    return sorted(issue for issue in issues if issue.startswith(prefixes))


def _mtime_drift_is_advisory_only(rel_path: str) -> bool:
    return rel_path in ADVISORY_ONLY_MTIME_DRIFT_PATHS


def _contract_issue_class(
    *,
    issues: list[str],
    stable_contract_issues: list[str],
    mtime_sensitive_issues: list[str],
    schema_validation_status: str,
) -> str:
    if any(issue.startswith(("read_failed", "utf8_decode_failed", "json_decode_failed")) for issue in issues):
        return "artifact_unreadable"
    if schema_validation_status == "fail":
        return "stable_contract_failure"
    if stable_contract_issues:
        return "stable_contract_debt"
    if mtime_sensitive_issues:
        return "mtime_sensitive_attention"
    if issues:
        return "operational_attention"
    return "clean"


def _safe_to_backfill(
    *,
    utf8_ok: bool,
    json_ok: bool,
    schema_validation_status: str,
    mtime_status: str,
) -> bool:
    if not utf8_ok or not json_ok:
        return False
    if schema_validation_status == "fail":
        return False
    return mtime_status != "stale"


def canonical_report_loading_issue(path: Path, payload: dict[str, Any]) -> str | None:
    if not _has_artifact_envelope(payload):
        return "missing_artifact_envelope"

    normalized_payload = _normalized_artifact_payload(payload)

    artifact_status = str(normalized_payload.get("artifact_status", "")).strip() or "unknown"
    if artifact_status != "current":
        return f"artifact_status={artifact_status}"

    currentness_status = _currentness_status(normalized_payload)
    if currentness_status != "current":
        return f"currentness_status={currentness_status}"

    # File mtime drift is reported separately as freshness attention, but it is not a
    # hard loading blocker for otherwise valid canonical reports. Cross-platform file
    # copies and checkout behavior can legitimately produce an mtime one second newer
    # than generated_at, and downstream loaders should still consume the report.
    del path

    return None


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
        elif schema_validation_status == "schema_unavailable":
            issues.append("schema_unavailable")
    return schema_validation_status, schema_validation_errors, issues


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
    if mtime_status == "stale" and not _mtime_drift_is_advisory_only(rel_path):
        issues.append("generated_at_older_than_file_mtime")
    if not noncanonical_archive:
        issues.extend(_test_target_fingerprint_issues(vault, normalized_payload))
    schema_validation_status, schema_validation_errors, schema_issues = _artifact_record_schema_state(
        vault,
        payload,
        noncanonical_archive=noncanonical_archive,
        freshness_context=freshness_context,
    )
    issues.extend(schema_issues)
    safe_to_backfill = _safe_to_backfill(
        utf8_ok=utf8_ok,
        json_ok=json_ok,
        schema_validation_status=schema_validation_status,
        mtime_status=mtime_status,
    )
    mtime_sensitive = mtime_status == "stale"
    issues = sorted(set(issues))
    stable_contract_issues = _matching_issues(issues, STABLE_CONTRACT_ISSUES)
    mtime_sensitive_issues = sorted(set(mtime_sensitive_issues + _matching_issues(issues, MTIME_SENSITIVE_ISSUES)))

    return {
        "path": rel_path,
        "owner_surface": _owner_surface(rel_path),
        "artifact_kind": str(normalized_payload.get("artifact_kind", "json_artifact")).strip() or "json_artifact",
        "utf8_ok": utf8_ok,
        "json_ok": json_ok,
        "has_schema": bool(fields["has_schema"]),
        "has_generated_at": bool(fields["has_generated_at"]),
        "has_artifact_envelope": bool(fields["has_envelope"]),
        "generated_at": generated_at,
        "artifact_status": str(fields["artifact_status"]),
        "retention_policy": str(fields["retention_policy"]),
        "currentness_status": currentness_status,
        "file_mtime_utc": _format_mtime(source_mtime),
        "mtime_source": mtime_source,
        "mtime_status": mtime_status,
        "mtime_sensitive": mtime_sensitive,
        "schema_validation_status": schema_validation_status,
        "schema_validation_errors": schema_validation_errors,
        "safe_to_backfill": safe_to_backfill,
        "recommended_next_action": _recommended_next_action(issues, schema_validation_status),
        "contract_issue_class": _contract_issue_class(
            issues=issues,
            stable_contract_issues=stable_contract_issues,
            mtime_sensitive_issues=mtime_sensitive_issues,
            schema_validation_status=schema_validation_status,
        ),
        "stable_contract_issues": stable_contract_issues,
        "mtime_sensitive_issues": mtime_sensitive_issues,
        "schema_contract": _schema_contract(
            rel_path,
            has_schema=bool(fields["has_schema"]),
            schema_validation_status=schema_validation_status,
        ),
        "issues": issues,
    }


def _status(
    *,
    root_ephemeral_count: int,
    non_utf8_count: int,
    missing_envelope_count: int,
    missing_schema_count: int,
    stale_count: int,
    unknown_currentness_count: int,
    schema_invalid_count: int,
    schema_unavailable_count: int,
) -> str:
    if root_ephemeral_count or non_utf8_count or schema_invalid_count:
        return "fail"
    if missing_envelope_count or missing_schema_count or stale_count or unknown_currentness_count or schema_unavailable_count:
        return "attention"
    return "pass"


def _issue_action(issue: str) -> str:
    return _recommended_next_action([issue], "fail" if issue == "schema_validation_failed" else "pass")


def _issue_priority(issue: str) -> int:
    ordered = {
        "root_ephemeral_artifact": 0,
        "utf8_decode_failed": 1,
        "read_failed": 1,
        "json_decode_failed": 2,
        "json_root_not_object": 2,
        "schema_validation_failed": 3,
        "missing_artifact_envelope": 4,
        "missing_schema": 5,
        "schema_unavailable": 6,
        "generated_at_older_than_file_mtime": 7,
        "test_target_fingerprint_mismatch": 7,
        "test_target_missing": 7,
        "unknown_currentness": 8,
        "missing_generated_at": 9,
    }
    for prefix, priority in ordered.items():
        if issue.startswith(prefix):
            return priority
    return 100


def _primary_issue(issues: list[str]) -> str:
    return min(issues, key=lambda issue: (_issue_priority(issue), issue)) if issues else "none"


def _top_debt(
    artifact_records: list[dict[str, Any]],
    root_ephemeral: list[dict[str, str]],
    non_utf8: list[dict[str, str]],
) -> list[dict[str, Any]]:
    by_issue: dict[str, dict[str, Any]] = {}

    def add(issue: str, owner_surface: str, *, safe_to_backfill: bool, mtime_sensitive: bool) -> None:
        item = by_issue.setdefault(
            issue,
            {
                "issue": issue,
                "count": 0,
                "owner_surface_counts": {},
                "safe_to_backfill_count": 0,
                "mtime_sensitive_count": 0,
                "recommended_next_action": _issue_action(issue),
            },
        )
        item["count"] += 1
        item["owner_surface_counts"][owner_surface] = item["owner_surface_counts"].get(owner_surface, 0) + 1
        if safe_to_backfill:
            item["safe_to_backfill_count"] += 1
        if mtime_sensitive:
            item["mtime_sensitive_count"] += 1

    for record in artifact_records:
        for issue in record["issues"]:
            add(
                issue,
                record["owner_surface"],
                safe_to_backfill=bool(record["safe_to_backfill"]),
                mtime_sensitive=bool(record["mtime_sensitive"]),
            )
    for item in root_ephemeral:
        add("root_ephemeral_artifact", _owner_surface(item["path"]), safe_to_backfill=False, mtime_sensitive=False)
    for item in non_utf8:
        add(item["issue"], _owner_surface(item["path"]), safe_to_backfill=False, mtime_sensitive=False)

    return sorted(
        by_issue.values(),
        key=lambda item: (-item["count"], item["issue"]),
    )[:TOP_DEBT_LIMIT]


def _top_debt_files(
    artifact_records: list[dict[str, Any]],
    root_ephemeral: list[dict[str, str]],
    non_utf8: list[dict[str, str]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in artifact_records:
        issues = list(record["issues"])
        if not issues:
            continue
        primary_issue = _primary_issue(issues)
        items.append(
            {
                "path": record["path"],
                "owner_surface": record["owner_surface"],
                "primary_issue": primary_issue,
                "issues": issues,
                "recommended_next_action": record["recommended_next_action"],
                "expected_debt_reduction": len(issues),
                "safe_to_backfill": bool(record["safe_to_backfill"]),
                "mtime_sensitive": bool(record["mtime_sensitive"]),
            }
        )
    for item in root_ephemeral:
        items.append(
            {
                "path": item["path"],
                "owner_surface": _owner_surface(item["path"]),
                "primary_issue": "root_ephemeral_artifact",
                "issues": ["root_ephemeral_artifact"],
                "recommended_next_action": "remove_root_ephemeral_artifact",
                "expected_debt_reduction": 1,
                "safe_to_backfill": False,
                "mtime_sensitive": False,
            }
        )
    for item in non_utf8:
        items.append(
            {
                "path": item["path"],
                "owner_surface": _owner_surface(item["path"]),
                "primary_issue": item["issue"],
                "issues": [item["issue"]],
                "recommended_next_action": "repair_non_utf8_artifact",
                "expected_debt_reduction": 1,
                "safe_to_backfill": False,
                "mtime_sensitive": False,
            }
        )
    return sorted(
        items,
        key=lambda item: (
            _issue_priority(str(item["primary_issue"])),
            not bool(item["safe_to_backfill"]),
            bool(item["mtime_sensitive"]),
            -int(item["expected_debt_reduction"]),
            str(item["owner_surface"]),
            str(item["path"]),
        ),
    )[:TOP_DEBT_FILE_LIMIT]


def _owner_surface_rollup(artifact_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    surfaces: dict[str, dict[str, Any]] = {}
    for record in artifact_records:
        surface = record["owner_surface"]
        item = surfaces.setdefault(
            surface,
            {
                "surface": surface,
                "artifact_count": 0,
                "issue_count": 0,
                "safe_to_backfill_count": 0,
                "mtime_sensitive_count": 0,
                "recommended_next_action": "none",
            },
        )
        item["artifact_count"] += 1
        item["issue_count"] += len(record["issues"])
        if record["safe_to_backfill"]:
            item["safe_to_backfill_count"] += 1
        if record["mtime_sensitive"]:
            item["mtime_sensitive_count"] += 1
        if item["recommended_next_action"] == "none" and record["recommended_next_action"] != "none":
            item["recommended_next_action"] = record["recommended_next_action"]
    return sorted(surfaces.values(), key=lambda item: (-item["issue_count"], item["surface"]))


def _debt_queue_path(record: dict[str, Any], issues: list[str]) -> dict[str, Any]:
    return {
        "path": record["path"],
        "owner_surface": record["owner_surface"],
        "primary_issue": _primary_issue(issues),
        "issues": issues,
        "safe_to_backfill": bool(record["safe_to_backfill"]),
        "mtime_sensitive": bool(record["mtime_sensitive"]),
    }


def _debt_queue(
    *,
    queue_id: str,
    records: list[dict[str, Any]],
    issue_selector: str,
    exit_condition: str,
    recommended_next_action: str,
) -> dict[str, Any]:
    paths: list[dict[str, Any]] = []
    for record in records:
        if issue_selector == "stable":
            issues = list(record["stable_contract_issues"])
        elif issue_selector == "mtime":
            issues = list(record["mtime_sensitive_issues"])
        else:
            issues = list(record["issues"])
        if not issues:
            continue
        paths.append(_debt_queue_path(record, issues))
    paths = sorted(paths, key=lambda item: (str(item["owner_surface"]), str(item["path"])))
    issue_count = sum(len(item["issues"]) for item in paths)
    return {
        "queue": queue_id,
        "status": "open" if paths else "complete",
        "item_count": len(paths),
        "issue_count": issue_count,
        "safe_to_backfill_count": sum(1 for item in paths if item["safe_to_backfill"]),
        "mtime_sensitive_count": sum(1 for item in paths if item["mtime_sensitive"]),
        "exit_condition": exit_condition,
        "recommended_next_action": recommended_next_action if paths else "none",
        "paths": paths[:DEBT_QUEUE_PATH_LIMIT],
    }


def _debt_queues(artifact_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs_historical = [
        record
        for record in artifact_records
        if record["owner_surface"] == "runs" and record["stable_contract_issues"]
    ]
    ops_reports = [
        record
        for record in artifact_records
        if record["owner_surface"] == "ops_reports" and record["stable_contract_issues"]
    ]
    operator_reports = [
        record
        for record in artifact_records
        if record["owner_surface"] == "operator_reports" and record["stable_contract_issues"]
    ]
    mtime_sensitive = [
        record
        for record in artifact_records
        if record["mtime_sensitive_issues"]
    ]
    return [
        _debt_queue(
            queue_id="runs_historical_archive",
            records=runs_historical,
            issue_selector="stable",
            exit_condition=(
                "Run-local historical JSON artifacts are archived, classified as noncanonical, "
                "or gain schema-backed artifact envelope/currentness metadata."
            ),
            recommended_next_action="archive_or_classify_historical_run_artifacts",
        ),
        _debt_queue(
            queue_id="ops_reports_producer_refresh",
            records=ops_reports,
            issue_selector="stable",
            exit_condition=(
                "Ops report producers emit schema-backed current artifacts, or legacy reports move "
                "to an archive namespace with explicit retention metadata."
            ),
            recommended_next_action="refresh_ops_report_producers",
        ),
        _debt_queue(
            queue_id="operator_reports_producer_refresh",
            records=operator_reports,
            issue_selector="stable",
            exit_condition=(
                "Operator reports emit schema-backed current artifacts, or move to an archive namespace "
                "with explicit retention metadata."
            ),
            recommended_next_action="refresh_operator_report_producers",
        ),
        _debt_queue(
            queue_id="mtime_sensitive_regeneration",
            records=mtime_sensitive,
            issue_selector="mtime",
            exit_condition=(
                "Mtime-sensitive artifacts are regenerated so generated_at and test target fingerprints "
                "match the current source tree, or are marked archived with archive retention."
            ),
            recommended_next_action="regenerate_mtime_sensitive_artifacts",
        ),
    ]


def _report_next_action(
    *,
    root_ephemeral_count: int,
    non_utf8_count: int,
    schema_invalid_count: int,
    missing_envelope_count: int,
    missing_schema_count: int,
    stale_count: int,
    unknown_currentness_count: int,
) -> str:
    if root_ephemeral_count:
        return "remove_root_ephemeral_artifacts"
    if non_utf8_count:
        return "repair_non_utf8_artifacts"
    if schema_invalid_count:
        return "regenerate_schema_invalid_artifacts"
    if missing_envelope_count:
        return "backfill_artifact_envelopes"
    if missing_schema_count:
        return "add_missing_artifact_schemas"
    if stale_count:
        return "regenerate_stale_artifacts"
    if unknown_currentness_count:
        return "backfill_currentness_metadata"
    return "none"


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
            1 for record in artifact_records if "generated_at_older_than_file_mtime" in record["issues"]
        ),
        unknown_currentness_count=sum(
            1 for record in artifact_records if "unknown_currentness" in record["issues"]
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
            if _matching_issues(record["issues"], TEST_TARGET_FINGERPRINT_ISSUES)
        ),
        operational_attention_issue_count=sum(
            len(_matching_issues(record["issues"], TEST_TARGET_FINGERPRINT_ISSUES))
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
    report_status = _status(
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
        source_paths=["ops/scripts/artifact_freshness_runtime.py"],
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
        "recommended_next_action": _report_next_action(
            root_ephemeral_count=len(scan_inputs.root_ephemeral),
            non_utf8_count=len(scan_inputs.non_utf8),
            schema_invalid_count=counts.schema_invalid_count,
            missing_envelope_count=counts.missing_envelope_count,
            missing_schema_count=counts.missing_schema_count,
            stale_count=counts.stale_count,
            unknown_currentness_count=counts.unknown_currentness_count,
        ),
        "safe_to_backfill": counts.safe_to_backfill_count > 0
        and counts.schema_invalid_count == 0
        and not scan_inputs.non_utf8,
        "mtime_sensitive": counts.mtime_sensitive_count > 0,
        "summary": _artifact_freshness_summary_payload(scan_inputs, counts),
        "top_debt": _top_debt(
            scan_inputs.artifact_records,
            scan_inputs.root_ephemeral,
            scan_inputs.non_utf8,
        ),
        "top_debt_files": _top_debt_files(
            scan_inputs.artifact_records,
            scan_inputs.root_ephemeral,
            scan_inputs.non_utf8,
        ),
        "debt_queues": _debt_queues(scan_inputs.artifact_records),
        "owner_surface": _owner_surface_rollup(scan_inputs.artifact_records),
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
