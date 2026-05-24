#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    resolve_schema_backed_report_output_path,
    write_schema_backed_report,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy
from .release_authority_vocabulary import (
    REASON_MACHINE_RELEASE_NOT_ALLOWED,
    release_authority_vocabulary_payload,
)
from .release_status_v2 import (
    decide_legacy_strict_clean_sealed_status,
    decide_sealed_release_status,
    release_status_v2_payload,
    release_status_v2_view_with_readiness_fallback,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.wiki_manifest import build_manifest, release_manifest_excludes_path


DEFAULT_OUT = "ops/reports/release-closeout-batch-manifest.json"
PRODUCER = "ops.scripts.release_closeout_batch_manifest"
SCHEMA_PATH = "ops/schemas/release-closeout-batch-manifest.schema.json"
BATCH_POLICY_PATH = "ops/policies/release-closeout-batch.json"
FINALITY_ATTESTATION_PATH = "ops/reports/release-closeout-finality-attestation.json"
SOURCE_EVIDENCE_PATH_LIMIT = 50
FILESYSTEM_MTIME_BASIS = "filesystem_mtime"
ZIP_MEMBER_TIMESTAMP_BASIS = "zip_member_timestamp"
DEFAULT_ZIP_TIMESTAMP_TIMEZONE = "UTC"
LOCAL_WORKSPACE_PROFILE = "local_workspace"
SOURCE_CONTENT_PACKAGE_PROFILE = "source_content_package"
AUDIT_PACK_TARGET = "release-audit-pack"
AUDIT_PACK_SOURCE_OF_TRUTH = "release-closeout-batch-manifest.json"
ZIP_PATH_SAMPLE_LIMIT = 50
SEALED_RELEASE_STATUSES = {"sealed_clean_pass", "sealed_conditional_pass"}
TEST_EXECUTION_SUMMARY_FULL_PATH = "ops/reports/test-execution-summary-full.json"
ARCHIVE_SELF_DESCRIPTION_PATH = "release-archive-self-description.json"
ALLOWED_DISTRIBUTION_VIRTUAL_PATHS = {ARCHIVE_SELF_DESCRIPTION_PATH}
SEALED_DISTRIBUTION_RETIRED_RISK_CODES = {"external_report_strict_unavailable"}


@dataclass(frozen=True)
class BatchArtifactInventory:
    artifacts: list[dict[str, Any]]
    present_count: int
    current_count: int
    required_present_count: int
    required_current_count: int
    required_count: int


@dataclass(frozen=True)
class DashboardDecisionInputs:
    accepted_risk_count: int
    gate_attention_count: int


@dataclass(frozen=True)
class LearningLaneDecisionInputs:
    learning_lane_status: str
    auto_improve_lane_status: str
    learning_claim_guard_status: str
    learning_claim_allowed: bool
    claims_learning_improved: bool
    learning_claim_blocking_family_count: int
    advisory_lifecycle_family_count: int


@dataclass(frozen=True)
class ReleaseDecisionInputs:
    release_readiness_state: str
    release_authority_status: str
    semantic_release_status: str
    closeout_sealed_release_status: str
    status_v2_blocker_reason_ids: list[str]
    status_v2_used_legacy_fallback_fields: list[str]
    clean_release_ready: bool
    machine_release_allowed: bool
    artifact_freshness_status: str
    artifact_freshness_schema_invalid_count: int
    accepted_risk_family_count: int
    accepted_risk_count: int
    gate_attention_count: int
    learning_lane_status: str
    auto_improve_lane_status: str
    learning_claim_guard_status: str
    learning_claim_allowed: bool
    claims_learning_improved: bool
    learning_claim_blocking_family_count: int
    advisory_lifecycle_family_count: int
    accepted_risks: list[Any]
    source_tree_coherence_status: str


@dataclass(frozen=True)
class BatchStatusDecision:
    status: str
    status_v2: dict[str, Any]
    batch_integrity_status: str
    release_authority_status: str
    semantic_release_status: str
    sealed_release_status: str
    release_authority_vocabulary: dict[str, Any]
    external_source_zip_bound: dict[str, Any]
    artifact_generation_status: str
    artifact_digest_sealing_status: str
    source_tree_rebuild_status: str
    clean_lane_status: str
    machine_release_status: str
    operator_release_status: str
    source_tree_coherence_integrity: str


@dataclass(frozen=True)
class BatchManifestLoadedSources:
    policy: dict[str, Any]
    resolved_policy_path: Path
    batch_policy: dict[str, Any]
    closeout: dict[str, Any]
    distribution_package: dict[str, Any]
    optional_payloads: list[dict[str, Any]]
    finality: dict[str, Any]
    source_command: str
    zip_metadata_path: Path | None
    zip_timestamp_timezone: str


@dataclass(frozen=True)
class BatchManifestPreparedState:
    generated_at: str
    batch_id: str
    dependency_order: list[Any]
    artifact_specs: list[dict[str, Any]]
    inventory: BatchArtifactInventory
    release: ReleaseDecisionInputs
    decision: BatchStatusDecision
    downstream_input_digest_mismatch: dict[str, Any]
    audit_materialization: dict[str, Any]


@dataclass(frozen=True)
class BatchManifestRenderInputs:
    vault: Path
    generated_at: str
    batch_id: str
    resolved_policy_path: Path
    dependency_order: list[Any]
    artifact_specs: list[dict[str, Any]]
    inventory: BatchArtifactInventory
    release: ReleaseDecisionInputs
    decision: BatchStatusDecision
    distribution_package: dict[str, Any]
    downstream_input_digest_mismatch: dict[str, Any]
    optional_payloads: list[dict[str, Any]]
    audit_materialization: dict[str, Any]
    finality: dict[str, Any]
    source_command: str
    zip_metadata_path: Path | None
    zip_timestamp_timezone: str


def _source_freshness_temporal_authority(timestamp_semantics: str) -> str:
    if timestamp_semantics == "archive_member_timestamp":
        return "archive_member_timestamp"
    if timestamp_semantics == "filesystem_timestamp":
        return "filesystem_mtime"
    return "not_claimed"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(payload: Any) -> str:
    return _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _load_batch_policy(vault: Path) -> dict[str, Any]:
    path = vault / BATCH_POLICY_PATH
    return _load_json(path)


def _finality_pointer() -> dict[str, Any]:
    return {
        "finality_required": True,
        "finality_attestation_path": FINALITY_ATTESTATION_PATH,
        "binding_authority": "release-closeout-finality-attestation",
        "summary": (
            "batch manifest records release evidence inventory and release authority only; "
            "fixed-point, batch, and self-check digest binding is owned by the finality attestation"
        ),
    }


def _parse_utc_z(value: str) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).replace(microsecond=0)


def _mtime_iso_z(path: Path) -> str:
    timestamp = path.stat().st_mtime
    return (
        dt.datetime.fromtimestamp(timestamp, dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _timezone_for_zip_timestamps(name: str) -> dt.tzinfo:
    value = str(name).strip() or DEFAULT_ZIP_TIMESTAMP_TIMEZONE
    if value.upper() == "UTC":
        return dt.timezone.utc
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        return dt.timezone.utc


def _zip_info_mtime_iso_z(info: zipfile.ZipInfo, *, timezone_assumption: str) -> str:
    local_tz = _timezone_for_zip_timestamps(timezone_assumption)
    timestamp = dt.datetime(*info.date_time, tzinfo=local_tz)
    return (
        timestamp.astimezone(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _normalize_zip_member_path(path: str) -> str:
    normalized = path.replace("\\", "/").lstrip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _zip_member_mtimes(
    zip_metadata_path: Path, *, timezone_assumption: str
) -> dict[str, str]:
    mtimes: dict[str, str] = {}
    with zipfile.ZipFile(zip_metadata_path) as archive:
        for info in archive.infolist():
            rel_path = _normalize_zip_member_path(info.filename)
            if not rel_path or rel_path.endswith("/"):
                continue
            mtime = _zip_info_mtime_iso_z(
                info,
                timezone_assumption=timezone_assumption,
            )
            candidates = [rel_path]
            if "/" in rel_path:
                candidates.append(rel_path.split("/", 1)[1])
            for candidate in candidates:
                current = mtimes.get(candidate)
                if current is None or mtime > current:
                    mtimes[candidate] = mtime
    return mtimes


def _zip_member_timestamp_semantics(zip_metadata_path: Path) -> str:
    with zipfile.ZipFile(zip_metadata_path) as archive:
        timestamps = {
            info.date_time for info in archive.infolist() if not info.is_dir()
        }
    return _zip_timestamp_semantics(timestamps)


def _manifest_file_digest(manifest: dict[str, Any]) -> str:
    files = [
        {
            "path": str(item.get("path", "")),
            "sha256": str(item.get("sha256", "")),
            "size_bytes": int(item.get("size_bytes", 0) or 0),
        }
        for item in manifest.get("files", [])
        if isinstance(item, dict)
    ]
    files.sort(key=lambda item: str(item["path"]))
    return _sha256_json({"files": files})


def _root_prefix_for_members(names: list[str]) -> str:
    first_parts = {name.split("/", 1)[0] for name in names if name and "/" in name}
    if len(first_parts) != 1:
        return ""
    prefix = next(iter(first_parts))
    return prefix if all(name.startswith(f"{prefix}/") for name in names) else ""


def _strip_zip_root_prefix(name: str, root_prefix: str) -> str:
    if root_prefix and name.startswith(f"{root_prefix}/"):
        return name.split("/", 1)[1]
    return name


def _zip_timestamp_text(value: tuple[int, int, int, int, int, int] | None) -> str:
    if value is None:
        return ""
    year, month, day, hour, minute, second = value
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}"


def _zip_timestamp_semantics(
    timestamps: set[tuple[int, int, int, int, int, int]],
) -> str:
    if not timestamps:
        return "not_applicable"
    if timestamps == {(1980, 1, 1, 0, 0, 0)}:
        return "normalized_archive_timestamp"
    return "archive_member_timestamp"


def _zip_manifest(zip_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(zip_path) as archive:
        infos = archive.infolist()
        file_infos = [info for info in infos if not info.is_dir()]
        normalized_names = [
            _normalize_zip_member_path(info.filename) for info in file_infos
        ]
        root_prefix = _root_prefix_for_members(normalized_names)
        files = []
        timestamps = {info.date_time for info in file_infos}
        for info, normalized_name in zip(file_infos, normalized_names, strict=True):
            rel_path = _strip_zip_root_prefix(normalized_name, root_prefix)
            content = archive.read(info.filename)
            files.append(
                {
                    "path": rel_path,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size_bytes": len(content),
                }
            )
        files.sort(key=lambda item: str(item["path"]))
        timestamp_min = min(timestamps) if timestamps else None
        timestamp_max = max(timestamps) if timestamps else None
        return {
            "files": files,
            "root_prefix": root_prefix,
            "entry_count": len(infos),
            "file_count": len(file_infos),
            "directory_entry_count": len(infos) - len(file_infos),
            "uncompressed_size_bytes": sum(info.file_size for info in file_infos),
            "timestamp_unique_count": len(timestamps),
            "timestamp_min": _zip_timestamp_text(timestamp_min),
            "timestamp_max": _zip_timestamp_text(timestamp_max),
            "timestamp_semantics": _zip_timestamp_semantics(timestamps),
        }


def _resolve_optional_zip_path(vault: Path, raw_path: Path | None) -> Path | None:
    if raw_path is None:
        return None
    return raw_path if raw_path.is_absolute() else (vault / raw_path).resolve()


def _distribution_package(
    vault: Path,
    *,
    distribution_zip_path: Path | None,
) -> dict[str, Any]:
    source_manifest = build_manifest(vault, vault / "ops/manifest.json")
    source_files = [
        item for item in source_manifest.get("files", []) if isinstance(item, dict)
    ]
    source_manifest_digest = _manifest_file_digest(source_manifest)
    source_paths = {str(item.get("path", "")) for item in source_files}
    base: dict[str, Any] = {
        "status": "not_provided",
        "archive_profile": LOCAL_WORKSPACE_PROFILE,
        "path": "",
        "sha256": "",
        "entry_count": 0,
        "file_count": 0,
        "directory_entry_count": 0,
        "uncompressed_size_bytes": 0,
        "root_prefix": "",
        "timestamp_semantics": "not_applicable",
        "timestamp_unique_count": 0,
        "timestamp_min": "",
        "timestamp_max": "",
        "source_manifest_file_count": len(source_files),
        "source_manifest_digest": source_manifest_digest,
        "archive_manifest_digest": "",
        "path_set_matches_release_manifest": False,
        "content_digest_matches_release_manifest": False,
        "zip_only_path_count": 0,
        "allowed_virtual_zip_path_count": 0,
        "manifest_only_path_count": 0,
        "zip_only_paths": [],
        "allowed_virtual_zip_paths": [],
        "manifest_only_paths": [],
        "summary": "distribution package not provided; manifest represents local workspace evidence only",
    }
    resolved_zip_path = _resolve_optional_zip_path(vault, distribution_zip_path)
    if resolved_zip_path is None:
        return base
    base["path"] = display_path(vault, resolved_zip_path)
    if not resolved_zip_path.is_file():
        base.update(
            {
                "status": "invalid",
                "summary": "distribution package path is missing or not a file",
            }
        )
        return base
    try:
        archive_manifest = _zip_manifest(resolved_zip_path)
    except (OSError, zipfile.BadZipFile):
        base.update(
            {
                "status": "invalid",
                "summary": "distribution package could not be read as a ZIP archive",
            }
        )
        return base
    archive_files = archive_manifest["files"]
    archive_paths = {str(item.get("path", "")) for item in archive_files}
    archive_by_path = {str(item["path"]): item for item in archive_files}
    source_by_path = {str(item["path"]): item for item in source_files}
    raw_zip_only_paths = archive_paths - source_paths
    allowed_virtual_zip_paths = sorted(
        path
        for path in raw_zip_only_paths
        if path in ALLOWED_DISTRIBUTION_VIRTUAL_PATHS
    )
    zip_only_paths = sorted(raw_zip_only_paths - ALLOWED_DISTRIBUTION_VIRTUAL_PATHS)
    manifest_only_paths = sorted(source_paths - archive_paths)
    shared_paths = source_paths & archive_paths
    content_matches = (
        not zip_only_paths
        and not manifest_only_paths
        and all(
            str(archive_by_path[path].get("sha256", ""))
            == str(source_by_path[path].get("sha256", ""))
            for path in shared_paths
        )
    )
    path_set_matches = not zip_only_paths and not manifest_only_paths
    status = "materialized" if path_set_matches and content_matches else "drift"
    base.update(
        {
            "status": status,
            "archive_profile": SOURCE_CONTENT_PACKAGE_PROFILE,
            "sha256": _sha256_file(resolved_zip_path),
            "entry_count": archive_manifest["entry_count"],
            "file_count": archive_manifest["file_count"],
            "directory_entry_count": archive_manifest["directory_entry_count"],
            "uncompressed_size_bytes": archive_manifest["uncompressed_size_bytes"],
            "root_prefix": archive_manifest["root_prefix"],
            "timestamp_semantics": archive_manifest["timestamp_semantics"],
            "timestamp_unique_count": archive_manifest["timestamp_unique_count"],
            "timestamp_min": archive_manifest["timestamp_min"],
            "timestamp_max": archive_manifest["timestamp_max"],
            "archive_manifest_digest": _manifest_file_digest(archive_manifest),
            "path_set_matches_release_manifest": path_set_matches,
            "content_digest_matches_release_manifest": content_matches,
            "zip_only_path_count": len(zip_only_paths),
            "allowed_virtual_zip_path_count": len(allowed_virtual_zip_paths),
            "manifest_only_path_count": len(manifest_only_paths),
            "zip_only_paths": zip_only_paths[:ZIP_PATH_SAMPLE_LIMIT],
            "allowed_virtual_zip_paths": allowed_virtual_zip_paths[
                :ZIP_PATH_SAMPLE_LIMIT
            ],
            "manifest_only_paths": manifest_only_paths[:ZIP_PATH_SAMPLE_LIMIT],
            "summary": (
                f"distribution package status={status}; "
                f"archive_profile={SOURCE_CONTENT_PACKAGE_PROFILE}; "
                f"path_set_matches_release_manifest={path_set_matches}; "
                f"content_digest_matches_release_manifest={content_matches}; "
                f"allowed_virtual_zip_path_count={len(allowed_virtual_zip_paths)}; "
                f"file_count={archive_manifest['file_count']}"
            ),
        }
    )
    return base


def _distribution_unsealed_status(distribution_package: dict[str, Any]) -> str:
    status = (
        str(distribution_package.get("status", "not_provided")).strip()
        or "not_provided"
    )
    if (
        status == "materialized"
        and bool(distribution_package.get("path_set_matches_release_manifest"))
        and bool(distribution_package.get("content_digest_matches_release_manifest"))
    ):
        return ""
    if status == "not_provided":
        return "unsealed_distribution_not_provided"
    if status == "invalid":
        return "unsealed_distribution_invalid"
    return "unsealed_distribution_drift"


def _external_source_zip_bound(
    distribution_package: dict[str, Any],
    *,
    release_authority_status: str,
    sealed_release_status: str,
) -> dict[str, Any]:
    distribution_status = (
        str(distribution_package.get("status", "not_provided")).strip()
        or "not_provided"
    )
    path_matches = bool(distribution_package.get("path_set_matches_release_manifest"))
    content_matches = bool(
        distribution_package.get("content_digest_matches_release_manifest")
    )
    if distribution_status == "not_provided":
        status = "not_bound"
    elif distribution_status == "invalid":
        status = "invalid"
    elif distribution_status == "materialized" and path_matches and content_matches:
        status = "bound"
    else:
        status = "drift"
    return {
        "status": status,
        "source": "distribution_package"
        if distribution_status != "not_provided"
        else "not_provided",
        "path": str(distribution_package.get("path", "")),
        "sha256": str(distribution_package.get("sha256", "")),
        "path_set_matches_release_manifest": path_matches,
        "content_digest_matches_release_manifest": content_matches,
        "release_authority_status": release_authority_status,
        "sealed_release_status": sealed_release_status,
        "summary": (
            f"external_source_zip_bound status={status}; "
            f"distribution_package.status={distribution_status}; "
            f"release_authority_status={release_authority_status}; "
            f"sealed_release_status={sealed_release_status}"
        ),
    }


def _evidence_set_digest(artifacts: list[dict[str, Any]]) -> str:
    normalized = [
        {
            "path": str(item.get("path", "")),
            "digest": str(item.get("digest", "")),
            "artifact_kind": str(item.get("artifact_kind", "")),
            "role": str(item.get("role", "")),
            "required": bool(item.get("required", False)),
        }
        for item in artifacts
    ]
    normalized.sort(key=lambda item: str(item["path"]))
    return _sha256_json(normalized)


def _safe_optional_payload_path(value: object) -> str:
    rel_path = str(value or "").replace("\\", "/").strip()
    path = Path(rel_path)
    if path.is_absolute() or ".." in path.parts or not rel_path:
        return ""
    return rel_path


def _optional_audit_payloads(vault: Path) -> list[dict[str, Any]]:
    summary = _load_json(vault / TEST_EXECUTION_SUMMARY_FULL_PATH)
    evidence_artifacts = summary.get("evidence_artifacts")
    if not isinstance(evidence_artifacts, list):
        return []
    payloads: list[dict[str, Any]] = []
    for item in evidence_artifacts:
        if not isinstance(item, dict):
            continue
        rel_path = _safe_optional_payload_path(item.get("path"))
        if not rel_path:
            continue
        source_path = vault / rel_path
        expected_sha = str(item.get("sha256", "")).strip()
        actual_sha = _sha256_file(source_path) if source_path.is_file() else ""
        available = source_path.is_file() and (
            not expected_sha or actual_sha == expected_sha
        )
        payloads.append(
            {
                "kind": str(item.get("kind", "")).strip() or "evidence_payload",
                "path": rel_path,
                "sha256": expected_sha or actual_sha,
                "size_bytes": int(item.get("size_bytes", 0) or 0),
                "required": False,
                "include_in_default_pack": False,
                "source": f"{TEST_EXECUTION_SUMMARY_FULL_PATH}.evidence_artifacts",
                "status": "available" if available else "missing_or_mismatch",
            }
        )
    return payloads


def _optional_payload_policy(optional_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    available_count = sum(
        1 for item in optional_payloads if item.get("status") == "available"
    )
    status = (
        "not_available"
        if not optional_payloads
        else "available"
        if available_count == len(optional_payloads)
        else "listed_unavailable"
    )
    return {
        "status": status,
        "include_by_default": False,
        "source_report": TEST_EXECUTION_SUMMARY_FULL_PATH,
        "payload_count": len(optional_payloads),
        "available_payload_count": available_count,
        "payload_kinds": sorted(
            {str(item.get("kind", "")) for item in optional_payloads}
        ),
        "summary": (
            "JUnit/log payload files are optional portable audit-pack payloads; "
            "checked-in JSON digests remain authoritative unless payloads are included explicitly"
        ),
    }


def _audit_materialization(
    artifacts: list[dict[str, Any]], optional_payloads: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "mode": "referenced_checked_in_artifacts",
        "bundle_required": False,
        "optional_bundle_target": AUDIT_PACK_TARGET,
        "bundle_source_of_truth": AUDIT_PACK_SOURCE_OF_TRUTH,
        "artifact_count": len(artifacts),
        "evidence_set_digest": _evidence_set_digest(artifacts),
        "optional_payload_policy": _optional_payload_policy(optional_payloads),
        "optional_payloads": optional_payloads,
        "summary": (
            "canonical evidence is referenced by this batch manifest; "
            "release-audit-pack can materialize a portable copy without creating new authority"
        ),
    }


def _source_evidence_freshness(
    vault: Path,
    generated_at: str,
    *,
    zip_metadata_path: Path | None = None,
    zip_timestamp_timezone: str = DEFAULT_ZIP_TIMESTAMP_TIMEZONE,
) -> dict[str, Any]:
    generated_dt = _parse_utc_z(generated_at)
    source_file_count = 0
    latest_source_mtime = ""
    latest_source_path = ""
    changed_after_generated_at: list[dict[str, str]] = []
    missing_zip_members: list[str] = []
    zip_mtimes: dict[str, str] = {}
    basis = FILESYSTEM_MTIME_BASIS
    timestamp_semantics = "filesystem_timestamp"
    resolved_zip_metadata_path: Path | None = None
    if zip_metadata_path is not None:
        basis = ZIP_MEMBER_TIMESTAMP_BASIS
        resolved_zip_metadata_path = zip_metadata_path
        if not resolved_zip_metadata_path.is_absolute():
            resolved_zip_metadata_path = (vault / resolved_zip_metadata_path).resolve()
        try:
            zip_mtimes = _zip_member_mtimes(
                resolved_zip_metadata_path,
                timezone_assumption=zip_timestamp_timezone,
            )
            timestamp_semantics = _zip_member_timestamp_semantics(
                resolved_zip_metadata_path
            )
        except (OSError, zipfile.BadZipFile):
            zip_mtimes = {}
            timestamp_semantics = "not_applicable"

    for path in sorted(vault.rglob("*")):
        try:
            if path.is_symlink() or not path.is_file():
                continue
            rel_path = path.relative_to(vault).as_posix()
        except OSError:
            continue
        if release_manifest_excludes_path(rel_path):
            continue
        if basis == ZIP_MEMBER_TIMESTAMP_BASIS:
            mtime = zip_mtimes.get(rel_path, "")
            if not mtime:
                missing_zip_members.append(rel_path)
        else:
            try:
                mtime = _mtime_iso_z(path)
            except OSError:
                continue
        source_file_count += 1
        if not latest_source_mtime or mtime > latest_source_mtime:
            latest_source_mtime = mtime
            latest_source_path = rel_path
        if generated_dt is None or not mtime:
            continue
        mtime_dt = _parse_utc_z(mtime)
        if mtime_dt is not None and mtime_dt > generated_dt:
            changed_after_generated_at.append({"path": rel_path, "mtime": mtime})

    changed_after_generated_at.sort(key=lambda item: (item["mtime"], item["path"]))
    missing_zip_members.sort()
    changed_count = len(changed_after_generated_at)
    missing_count = len(missing_zip_members)
    if generated_dt is None:
        status = "unknown"
    elif changed_count or missing_count:
        status = "fail"
    else:
        status = "pass"
    return {
        "status": status,
        "basis": basis,
        "timestamp_semantics": timestamp_semantics,
        "source_freshness_temporal_authority": _source_freshness_temporal_authority(
            timestamp_semantics
        ),
        "source_freshness_content_authority": "source_tree_fingerprint",
        "generated_at": generated_at,
        "zip_metadata_path": (
            ""
            if resolved_zip_metadata_path is None
            else display_path(vault, resolved_zip_metadata_path)
        ),
        "archive_timestamp_has_timezone": False
        if basis == ZIP_MEMBER_TIMESTAMP_BASIS
        else True,
        "timestamp_timezone_assumption": (
            str(zip_timestamp_timezone).strip() or DEFAULT_ZIP_TIMESTAMP_TIMEZONE
            if basis == ZIP_MEMBER_TIMESTAMP_BASIS
            else "UTC"
        ),
        "source_file_count": source_file_count,
        "latest_source_mtime": latest_source_mtime,
        "latest_source_path": latest_source_path,
        "changed_after_generated_at_count": changed_count,
        "changed_after_generated_at_path_limit": SOURCE_EVIDENCE_PATH_LIMIT,
        "changed_after_generated_at": changed_after_generated_at[
            :SOURCE_EVIDENCE_PATH_LIMIT
        ],
        "missing_zip_member_count": missing_count,
        "missing_zip_member_path_limit": SOURCE_EVIDENCE_PATH_LIMIT,
        "missing_zip_members": missing_zip_members[:SOURCE_EVIDENCE_PATH_LIMIT],
        "summary": (
            f"source_evidence_freshness status={status}; basis={basis}; "
            f"changed_after_generated_at_count={changed_count}; "
            f"missing_zip_member_count={missing_count}; "
            f"source_file_count={source_file_count}"
        ),
    }


def _downstream_input_digest_mismatch(
    *,
    vault: Path,
    closeout_report: dict[str, Any],
) -> dict[str, Any]:
    closeout_input_fingerprints = closeout_report.get("input_fingerprints")
    closeout_components = closeout_report.get("components")
    if not isinstance(closeout_input_fingerprints, dict) or not isinstance(
        closeout_components, list
    ):
        return {
            "status": "no_closeout_snapshot",
            "compared_input_count": 0,
            "mismatch_count": 0,
            "mismatches": [],
            "summary": "Closeout summary input_fingerprints/components were unavailable for downstream digest comparison.",
        }

    mismatches: list[dict[str, str]] = []
    compared_input_count = 0
    for component in closeout_components:
        if not isinstance(component, dict):
            continue
        name = str(component.get("name", "")).strip()
        source_path = str(component.get("path", "")).strip()
        if not name or not source_path:
            continue
        expected_digest = (
            str(closeout_input_fingerprints.get(name, "")).strip() or "missing"
        )
        artifact_path = vault / source_path
        actual_digest = (
            _sha256_file(artifact_path) if artifact_path.exists() else "missing"
        )
        compared_input_count += 1
        if expected_digest == actual_digest:
            continue
        mismatches.append(
            {
                "component_name": name,
                "source_path": source_path,
                "expected_digest": expected_digest,
                "actual_digest": actual_digest,
            }
        )

    status = "mismatch" if mismatches else "match"
    return {
        "status": status,
        "compared_input_count": compared_input_count,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "summary": (
            f"downstream_input_digest_mismatch status={status}; "
            f"mismatch_count={len(mismatches)}; compared_input_count={compared_input_count}"
        ),
    }


def _dict_child(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def _status_text(payload: dict[str, Any], key: str, default: str = "unknown") -> str:
    return str(payload.get(key, default)).strip() or default


def _risk_code(risk: object) -> str:
    return str(risk.get("code", "")).strip() if isinstance(risk, dict) else ""


def _materialized_distribution_package(distribution_package: dict[str, Any]) -> bool:
    return (
        str(distribution_package.get("status", "")).strip() == "materialized"
        and bool(str(distribution_package.get("path", "")).strip())
        and bool(str(distribution_package.get("sha256", "")).strip())
        and bool(distribution_package.get("path_set_matches_release_manifest"))
        and bool(distribution_package.get("content_digest_matches_release_manifest"))
    )


def _distribution_retired_risk_codes(distribution_package: dict[str, Any]) -> set[str]:
    if not _materialized_distribution_package(distribution_package):
        return set()
    return set(SEALED_DISTRIBUTION_RETIRED_RISK_CODES)


def _active_release_risks(
    accepted_risks: object,
    *,
    retired_codes: set[str],
) -> list[Any]:
    risks = accepted_risks if isinstance(accepted_risks, list) else []
    if not retired_codes:
        return risks
    return [risk for risk in risks if _risk_code(risk) not in retired_codes]


def _retired_risk_adjusted_count(
    raw_count: int,
    accepted_risks: object,
    active_risks: list[Any],
) -> int:
    risks = accepted_risks if isinstance(accepted_risks, list) else []
    retired_count = max(0, len(risks) - len(active_risks))
    if not retired_count:
        return max(0, raw_count)
    if raw_count == len(risks):
        return len(active_risks)
    return max(0, raw_count - retired_count)


def _gate_attention_codes(gate: object) -> list[str]:
    if not isinstance(gate, dict):
        return []
    accepted_risk = gate.get("accepted_risk")
    accepted_risk = accepted_risk if isinstance(accepted_risk, dict) else {}
    codes = accepted_risk.get("codes", [])
    return [str(code).strip() for code in codes if str(code).strip()] if isinstance(codes, list) else []


def _gate_is_attention(gate: object) -> bool:
    if not isinstance(gate, dict):
        return False
    live = gate.get("live_rerun_state")
    live = live if isinstance(live, dict) else {}
    return (
        str(gate.get("checked_in_state", "")).strip() == "attention"
        or str(live.get("status", "")).strip() == "attention"
    )


def _retired_gate_attention_count(
    gates: object,
    *,
    retired_codes: set[str],
) -> int:
    if not retired_codes or not isinstance(gates, list):
        return 0
    count = 0
    for gate in gates:
        if not _gate_is_attention(gate):
            continue
        codes = set(_gate_attention_codes(gate))
        if codes and codes <= retired_codes:
            count += 1
    return count


def _artifact_record(
    vault: Path, spec: dict[str, Any]
) -> tuple[dict[str, Any], bool, bool, bool]:
    rel_path = str(spec["path"])
    path = vault / rel_path
    payload, _diagnostics = load_optional_json_object_with_diagnostics(path)
    exists = path.exists()
    digest = _sha256_file(path) if exists else "0" * 64
    currentness = payload.get("currentness", {}) if payload else {}
    currentness_status = (
        str(currentness.get("status", "unknown"))
        if isinstance(currentness, dict)
        else "unknown"
    )
    required = bool(spec.get("required", False))
    return (
        {
            "path": rel_path,
            "artifact_kind": str(payload.get("artifact_kind", ""))
            if payload
            else "",
            "digest": digest,
            "generated_at": str(payload.get("generated_at", "")) if payload else "",
            "producer": str(payload.get("producer", "")) if payload else "",
            "source_tree_fingerprint": str(
                payload.get("source_tree_fingerprint", "")
            )
            if payload
            else "",
            "currentness_status": currentness_status,
            "role": str(spec.get("role", "")),
            "required": required,
        },
        exists,
        currentness_status == "current",
        required,
    )


def _build_artifact_inventory(
    vault: Path, artifact_specs: list[dict[str, Any]]
) -> BatchArtifactInventory:
    artifacts: list[dict[str, Any]] = []
    present_count = 0
    current_count = 0
    required_present_count = 0
    required_current_count = 0
    required_count = sum(1 for spec in artifact_specs if spec.get("required"))

    for spec in artifact_specs:
        artifact, exists, current, required = _artifact_record(vault, spec)
        artifacts.append(artifact)
        present_count += int(exists)
        current_count += int(current)
        required_present_count += int(required and exists)
        required_current_count += int(required and current)

    return BatchArtifactInventory(
        artifacts=artifacts,
        present_count=present_count,
        current_count=current_count,
        required_present_count=required_present_count,
        required_current_count=required_current_count,
        required_count=required_count,
    )


def _all_required_present(inventory: BatchArtifactInventory) -> bool:
    return inventory.required_present_count == inventory.required_count


def _all_required_current(inventory: BatchArtifactInventory) -> bool:
    return inventory.required_current_count == inventory.required_count


def _dashboard_decision_inputs(
    vault: Path,
    closeout: dict[str, Any],
    distribution_package: dict[str, Any],
) -> DashboardDecisionInputs:
    dashboard = _load_json(vault / "ops/reports/release-evidence-dashboard.json")
    dashboard_summary = _dict_child(dashboard, "summary")
    closeout_summary = _dict_child(closeout, "summary")
    retired_codes = _distribution_retired_risk_codes(distribution_package)
    accepted_risks = closeout.get("accepted_risks", [])
    active_risks = _active_release_risks(
        accepted_risks,
        retired_codes=retired_codes,
    )
    accepted_risk_count = int(
        dashboard_summary.get(
            "accepted_risk_count",
            closeout_summary.get("accepted_risk_instance_count", 0),
        )
        or 0
    )
    accepted_risk_count = _retired_risk_adjusted_count(
        accepted_risk_count,
        accepted_risks,
        active_risks,
    )
    gate_attention_count = int(dashboard_summary.get("gate_attention_count", 0) or 0)
    gate_attention_count = max(
        0,
        gate_attention_count
        - _retired_gate_attention_count(
            dashboard.get("gates", []),
            retired_codes=retired_codes,
        ),
    )
    return DashboardDecisionInputs(
        accepted_risk_count=accepted_risk_count,
        gate_attention_count=gate_attention_count,
    )


def _learning_lane_decision_inputs(vault: Path) -> LearningLaneDecisionInputs:
    lane_summary_report = _load_json(vault / "ops/reports/release-lane-summary.json")
    lane_summary = _dict_child(lane_summary_report, "lane_summary")
    return LearningLaneDecisionInputs(
        learning_lane_status=_status_text(lane_summary, "learning_lane_status"),
        auto_improve_lane_status=_status_text(
            lane_summary, "auto_improve_lane_status"
        ),
        learning_claim_guard_status=_status_text(
            lane_summary, "learning_claim_guard_status"
        ),
        learning_claim_allowed=bool(
            lane_summary.get("learning_claim_allowed", False)
        ),
        claims_learning_improved=bool(
            lane_summary.get("claims_learning_improved", False)
        ),
        learning_claim_blocking_family_count=int(
            lane_summary.get("learning_claim_blocking_family_count", 0) or 0
        ),
        advisory_lifecycle_family_count=int(
            lane_summary.get("advisory_lifecycle_family_count", 0) or 0
        ),
    )


def _release_decision_inputs(
    vault: Path,
    closeout: dict[str, Any],
    distribution_package: dict[str, Any],
) -> ReleaseDecisionInputs:
    artifact_freshness_gate = _dict_child(closeout, "artifact_freshness_gate")
    closeout_summary = _dict_child(closeout, "summary")
    dashboard = _dashboard_decision_inputs(vault, closeout, distribution_package)
    lane = _learning_lane_decision_inputs(vault)
    accepted_risks = closeout.get("accepted_risks", [])
    retired_codes = _distribution_retired_risk_codes(distribution_package)
    active_risks = _active_release_risks(
        accepted_risks,
        retired_codes=retired_codes,
    )
    closeout_status_view = release_status_v2_view_with_readiness_fallback(closeout)
    release_authority_status = str(closeout_status_view["release_authority_status"])
    semantic_release_status = str(closeout_status_view["semantic_release_status"])
    closeout_sealed_release_status = str(closeout_status_view["sealed_release_status"])
    status_v2_blocker_reason_ids = [
        str(reason) for reason in closeout_status_view["blocker_reason_ids"]
    ]
    status_v2_used_legacy_fallback_fields = [
        str(field) for field in closeout_status_view["used_legacy_fallback_fields"]
    ]
    if release_authority_status in {"clean_pass", "conditional_pass", "blocked"}:
        release_readiness_state = release_authority_status
    else:
        release_readiness_state = "unknown"
    if bool(closeout_status_view["status_v2_available"]) or status_v2_blocker_reason_ids:
        machine_release_allowed = (
            release_authority_status == "clean_pass"
            and REASON_MACHINE_RELEASE_NOT_ALLOWED
            not in set(status_v2_blocker_reason_ids)
        )
    else:
        machine_release_allowed = (
            release_authority_status == "clean_pass"
            and bool(closeout.get("machine_release_allowed"))
        )
    return ReleaseDecisionInputs(
        release_readiness_state=release_readiness_state,
        release_authority_status=release_authority_status,
        semantic_release_status=semantic_release_status,
        closeout_sealed_release_status=closeout_sealed_release_status,
        status_v2_blocker_reason_ids=status_v2_blocker_reason_ids,
        status_v2_used_legacy_fallback_fields=status_v2_used_legacy_fallback_fields,
        clean_release_ready=release_authority_status == "clean_pass",
        machine_release_allowed=machine_release_allowed,
        artifact_freshness_status=_status_text(artifact_freshness_gate, "status"),
        artifact_freshness_schema_invalid_count=int(
            artifact_freshness_gate.get("schema_invalid_artifact_count", 0) or 0
        ),
        accepted_risk_family_count=_retired_risk_adjusted_count(
            int(closeout_summary.get("accepted_risk_family_count", 0) or 0),
            accepted_risks,
            active_risks,
        ),
        accepted_risk_count=dashboard.accepted_risk_count,
        gate_attention_count=dashboard.gate_attention_count,
        learning_lane_status=lane.learning_lane_status,
        auto_improve_lane_status=lane.auto_improve_lane_status,
        learning_claim_guard_status=lane.learning_claim_guard_status,
        learning_claim_allowed=lane.learning_claim_allowed,
        claims_learning_improved=lane.claims_learning_improved,
        learning_claim_blocking_family_count=lane.learning_claim_blocking_family_count,
        advisory_lifecycle_family_count=_retired_risk_adjusted_count(
            lane.advisory_lifecycle_family_count,
            accepted_risks,
            active_risks,
        ),
        accepted_risks=active_risks,
        source_tree_coherence_status=_status_text(
            _dict_child(closeout, "source_tree_coherence"), "status"
        ),
    )


def _batch_status_decision(
    inventory: BatchArtifactInventory,
    release: ReleaseDecisionInputs,
    distribution_package: dict[str, Any],
) -> BatchStatusDecision:
    all_required_present = _all_required_present(inventory)
    all_required_current = _all_required_current(inventory)
    batch_integrity_status = (
        "pass" if (all_required_present and all_required_current) else "fail"
    )
    release_authority_status = release.release_authority_status
    semantic_release_status = release.semantic_release_status
    distribution_unsealed_status = _distribution_unsealed_status(distribution_package)
    sealed_release_status = decide_sealed_release_status(
        batch_integrity_status=batch_integrity_status,
        distribution_unsealed_status=distribution_unsealed_status,
        clean_release_ready=release.clean_release_ready,
        machine_release_allowed=release.machine_release_allowed,
        release_readiness_state=release.release_authority_status,
    )
    release_authority_vocabulary = release_authority_vocabulary_payload(
        release_authority_status=release_authority_status,
        semantic_release_status=semantic_release_status,
        sealed_release_status=sealed_release_status,
        machine_release_allowed=release.machine_release_allowed,
        clean_release_ready=release.clean_release_ready,
        batch_integrity_status=batch_integrity_status,
        distribution_package=distribution_package,
    )
    external_source_zip_bound = _external_source_zip_bound(
        distribution_package,
        release_authority_status=release_authority_status,
        sealed_release_status=sealed_release_status,
    )
    status = decide_legacy_strict_clean_sealed_status(
        all_required_present=all_required_present,
        all_required_current=all_required_current,
        clean_release_ready=release.clean_release_ready,
        machine_release_allowed=release.machine_release_allowed,
        sealed_release_status=sealed_release_status,
    )
    status_v2 = release_status_v2_payload(
        status=status,
        release_authority_status=release_authority_status,
        semantic_release_status=semantic_release_status,
        sealed_release_status=sealed_release_status,
        release_authority_vocabulary=release_authority_vocabulary,
    )
    return BatchStatusDecision(
        status=status,
        status_v2=status_v2,
        batch_integrity_status=batch_integrity_status,
        release_authority_status=release_authority_status,
        semantic_release_status=semantic_release_status,
        sealed_release_status=sealed_release_status,
        release_authority_vocabulary=release_authority_vocabulary,
        external_source_zip_bound=external_source_zip_bound,
        artifact_generation_status="pass" if all_required_present else "fail",
        artifact_digest_sealing_status=batch_integrity_status,
        source_tree_rebuild_status=release.source_tree_coherence_status,
        clean_lane_status="pass" if release.clean_release_ready else "fail",
        machine_release_status="allowed"
        if release.machine_release_allowed
        else "blocked",
        operator_release_status="allowed"
        if release.release_authority_status in {"clean_pass", "conditional_pass"}
        else "blocked",
        source_tree_coherence_integrity="pass"
        if release.source_tree_coherence_status == "pass"
        else "fail",
    )


def _batch_manifest_source_command(
    vault: Path,
    *,
    zip_metadata_path: Path | None,
    distribution_zip_path: Path | None,
    zip_timestamp_timezone: str,
) -> str:
    source_command = "python -m ops.scripts.release_closeout_batch_manifest --vault ."
    if zip_metadata_path is not None:
        source_command = (
            f"{source_command} --zip-metadata {display_path(vault, zip_metadata_path)} "
            f"--zip-timestamp-timezone {zip_timestamp_timezone}"
        )
    if distribution_zip_path is not None:
        source_command = (
            f"{source_command} --distribution-zip "
            f"{display_path(vault, distribution_zip_path)}"
        )
    return source_command


def _batch_manifest_summary(
    artifact_specs: list[dict[str, Any]], inventory: BatchArtifactInventory
) -> dict[str, int]:
    return {
        "artifact_count": len(artifact_specs),
        "present_count": inventory.present_count,
        "current_count": inventory.current_count,
        "required_count": inventory.required_count,
        "required_present_count": inventory.required_present_count,
        "required_current_count": inventory.required_current_count,
    }


def _status_semantics() -> dict[str, str]:
    return {
        "top_level_status_meaning": "legacy_strict_clean_sealed_claim",
        "release_authority_status_meaning": "semantic_release_authority_from_closeout",
        "sealed_release_status_meaning": "artifact_distribution_seal_state",
        "next_migration_candidate": "rename_or_replace_top_level_status_with_sealed_status",
        "summary": (
            "top-level status remains a legacy strict clean+sealed claim; "
            "release_authority_status is semantic authority and sealed_release_status is artifact/package finality"
        ),
    }


def _coherence_payload(inventory: BatchArtifactInventory) -> dict[str, Any]:
    all_required_present = _all_required_present(inventory)
    return {
        "status": "pass" if all_required_present else "fail",
        "all_required_present": all_required_present,
        "all_required_current": _all_required_current(inventory),
    }


def _integrity_layers(decision: BatchStatusDecision) -> dict[str, str]:
    return {
        "artifact_inventory_integrity": decision.artifact_generation_status,
        "artifact_content_integrity": decision.artifact_digest_sealing_status,
        "source_tree_coherence_integrity": decision.source_tree_coherence_integrity,
        "source_tree_coherence_status": decision.source_tree_rebuild_status,
    }


def _release_decision_snapshot(release: ReleaseDecisionInputs) -> dict[str, Any]:
    return {
        "clean_release_ready": release.clean_release_ready,
        "machine_release_allowed": release.machine_release_allowed,
        "release_readiness_state": release.release_readiness_state,
        "release_authority_status": release.release_authority_status,
        "semantic_release_status": release.semantic_release_status,
        "closeout_sealed_release_status": release.closeout_sealed_release_status,
        "status_v2_blocker_reason_ids": release.status_v2_blocker_reason_ids,
        "status_v2_used_legacy_fallback_fields": release.status_v2_used_legacy_fallback_fields,
        "artifact_freshness_status": release.artifact_freshness_status,
        "artifact_freshness_schema_invalid_artifact_count": release.artifact_freshness_schema_invalid_count,
        "auto_improve_lane_status": release.auto_improve_lane_status,
        "learning_lane_status": release.learning_lane_status,
        "learning_claim_guard_status": release.learning_claim_guard_status,
        "learning_claim_allowed": release.learning_claim_allowed,
        "claims_learning_improved": release.claims_learning_improved,
        "learning_claim_blocking_family_count": release.learning_claim_blocking_family_count,
        "advisory_lifecycle_family_count": release.advisory_lifecycle_family_count,
        "accepted_risk_count": release.accepted_risk_count,
        "gate_attention_count": release.gate_attention_count,
        "accepted_risk_family_count": release.accepted_risk_family_count,
        "accepted_risks": release.accepted_risks,
    }


def _envelope_text_inputs(inputs: BatchManifestRenderInputs) -> dict[str, str]:
    source_evidence_basis = (
        ZIP_MEMBER_TIMESTAMP_BASIS
        if inputs.zip_metadata_path is not None
        else FILESYSTEM_MTIME_BASIS
    )
    return {
        "batch_id": inputs.batch_id,
        "artifact_count": str(len(inputs.artifact_specs)),
        "source_evidence_basis": source_evidence_basis,
        "zip_timestamp_timezone": inputs.zip_timestamp_timezone
        if inputs.zip_metadata_path is not None
        else "",
        "distribution_zip_sha256": str(inputs.distribution_package.get("sha256", "")),
        "distribution_zip_path": str(inputs.distribution_package.get("path", "")),
        "external_source_zip_bound_status": str(
            inputs.decision.external_source_zip_bound["status"]
        ),
        "evidence_set_digest": str(
            inputs.audit_materialization["evidence_set_digest"]
        ),
        "optional_payload_count": str(len(inputs.optional_payloads)),
        "finality_attestation_path": str(inputs.finality["finality_attestation_path"]),
        "finality_required": str(inputs.finality["finality_required"]),
    }


def _render_batch_manifest_report(inputs: BatchManifestRenderInputs) -> dict[str, Any]:
    decision = inputs.decision
    inventory = inputs.inventory
    return {
        **build_canonical_report_envelope(
            inputs.vault,
            generated_at=inputs.generated_at,
            artifact_kind="release_closeout_batch_manifest",
            producer=PRODUCER,
            source_command=inputs.source_command,
            resolved_policy_path=inputs.resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=["ops/scripts/release/release_closeout_batch_manifest.py"],
            text_inputs=_envelope_text_inputs(inputs),
        ),
        "batch_id": inputs.batch_id,
        "distribution_package": inputs.distribution_package,
        "external_source_zip_bound": decision.external_source_zip_bound,
        "audit_materialization": inputs.audit_materialization,
        "artifacts": inventory.artifacts,
        "dependency_order": inputs.dependency_order,
        "status": decision.status,
        "status_semantics": _status_semantics(),
        "status_v2": decision.status_v2,
        "status_v2_preview": decision.status_v2,
        "summary": _batch_manifest_summary(inputs.artifact_specs, inventory),
        "batch_integrity_status": decision.batch_integrity_status,
        "release_authority_status": decision.release_authority_status,
        "semantic_release_status": decision.semantic_release_status,
        "sealed_release_status": decision.sealed_release_status,
        "release_authority_vocabulary": decision.release_authority_vocabulary,
        "artifact_generation_status": decision.artifact_generation_status,
        "artifact_digest_sealing_status": decision.artifact_digest_sealing_status,
        "source_tree_rebuild_status": decision.source_tree_rebuild_status,
        "clean_lane_status": decision.clean_lane_status,
        "auto_improve_lane_status": inputs.release.auto_improve_lane_status,
        "learning_lane_status": inputs.release.learning_lane_status,
        "machine_release_status": decision.machine_release_status,
        "operator_release_status": decision.operator_release_status,
        "finality": inputs.finality,
        "coherence": _coherence_payload(inventory),
        "integrity_layers": _integrity_layers(decision),
        "downstream_input_digest_mismatch": inputs.downstream_input_digest_mismatch,
        "source_evidence_freshness": _source_evidence_freshness(
            inputs.vault,
            inputs.generated_at,
            zip_metadata_path=inputs.zip_metadata_path,
            zip_timestamp_timezone=inputs.zip_timestamp_timezone,
        ),
        "release_decision_snapshot": _release_decision_snapshot(inputs.release),
    }


def _load_batch_manifest_sources(
    vault: Path,
    *,
    zip_metadata_path: Path | None = None,
    distribution_zip_path: Path | None = None,
    zip_timestamp_timezone: str = DEFAULT_ZIP_TIMESTAMP_TIMEZONE,
) -> BatchManifestLoadedSources:
    policy, resolved_policy_path = load_policy(vault)
    effective_distribution_zip_path = distribution_zip_path or zip_metadata_path
    return BatchManifestLoadedSources(
        policy=policy,
        resolved_policy_path=resolved_policy_path,
        batch_policy=_load_batch_policy(vault),
        closeout=_load_json(vault / "ops/reports/release-closeout-summary.json"),
        distribution_package=_distribution_package(
            vault,
            distribution_zip_path=effective_distribution_zip_path,
        ),
        optional_payloads=_optional_audit_payloads(vault),
        finality=_finality_pointer(),
        source_command=_batch_manifest_source_command(
            vault,
            zip_metadata_path=zip_metadata_path,
            distribution_zip_path=distribution_zip_path,
            zip_timestamp_timezone=zip_timestamp_timezone,
        ),
        zip_metadata_path=zip_metadata_path,
        zip_timestamp_timezone=zip_timestamp_timezone,
    )


def _prepare_batch_manifest_state(
    vault: Path,
    loaded: BatchManifestLoadedSources,
    *,
    generated_at: str,
) -> BatchManifestPreparedState:
    batch_id = f"batch-{generated_at.replace(':', '-').replace('Z', '')}"
    dependency_order = list(loaded.batch_policy.get("dependency_order", []))
    artifact_specs = [
        dict(spec)
        for spec in loaded.batch_policy.get("artifacts", [])
        if isinstance(spec, dict)
    ]
    inventory = _build_artifact_inventory(vault, artifact_specs)
    release = _release_decision_inputs(
        vault,
        loaded.closeout,
        loaded.distribution_package,
    )
    decision = _batch_status_decision(inventory, release, loaded.distribution_package)
    return BatchManifestPreparedState(
        generated_at=generated_at,
        batch_id=batch_id,
        dependency_order=dependency_order,
        artifact_specs=artifact_specs,
        inventory=inventory,
        release=release,
        decision=decision,
        downstream_input_digest_mismatch=_downstream_input_digest_mismatch(
            vault=vault,
            closeout_report=loaded.closeout,
        ),
        audit_materialization=_audit_materialization(
            inventory.artifacts, loaded.optional_payloads
        ),
    )


def _batch_manifest_render_inputs(
    vault: Path,
    loaded: BatchManifestLoadedSources,
    prepared: BatchManifestPreparedState,
) -> BatchManifestRenderInputs:
    return BatchManifestRenderInputs(
        vault=vault,
        generated_at=prepared.generated_at,
        batch_id=prepared.batch_id,
        resolved_policy_path=loaded.resolved_policy_path,
        dependency_order=prepared.dependency_order,
        artifact_specs=prepared.artifact_specs,
        inventory=prepared.inventory,
        release=prepared.release,
        decision=prepared.decision,
        distribution_package=loaded.distribution_package,
        downstream_input_digest_mismatch=prepared.downstream_input_digest_mismatch,
        optional_payloads=loaded.optional_payloads,
        audit_materialization=prepared.audit_materialization,
        finality=loaded.finality,
        source_command=loaded.source_command,
        zip_metadata_path=loaded.zip_metadata_path,
        zip_timestamp_timezone=loaded.zip_timestamp_timezone,
    )


def build_batch_manifest(
    vault: Path,
    *,
    context: RuntimeContext | None = None,
    zip_metadata_path: Path | None = None,
    distribution_zip_path: Path | None = None,
    zip_timestamp_timezone: str = DEFAULT_ZIP_TIMESTAMP_TIMEZONE,
) -> dict[str, Any]:
    loaded = _load_batch_manifest_sources(
        vault,
        zip_metadata_path=zip_metadata_path,
        distribution_zip_path=distribution_zip_path,
        zip_timestamp_timezone=zip_timestamp_timezone,
    )
    runtime_context = context or RuntimeContext.from_policy(loaded.policy)
    generated_at = runtime_context.isoformat_z()
    prepared = _prepare_batch_manifest_state(
        vault,
        loaded,
        generated_at=generated_at,
    )
    return _render_batch_manifest_report(
        _batch_manifest_render_inputs(vault, loaded, prepared)
    )


def write_report(
    vault: Path, report: dict[str, Any], out_path: str | None = None
) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release closeout batch manifest schema validation failed",
        )
    )


def _strip_generated_at(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: _strip_generated_at(v) for k, v in obj.items() if k != "generated_at"
        }
    if isinstance(obj, list):
        return [_strip_generated_at(item) for item in obj]
    return obj


def _artifact_digest_mismatches(
    existing: dict[str, Any], current: dict[str, Any]
) -> list[dict[str, str]]:
    existing_by_path = {
        str(item.get("path", "")): item
        for item in existing.get("artifacts", [])
        if isinstance(item, dict) and item.get("path")
    }
    current_by_path = {
        str(item.get("path", "")): item
        for item in current.get("artifacts", [])
        if isinstance(item, dict) and item.get("path")
    }
    mismatches: list[dict[str, str]] = []
    for rel_path in sorted(set(existing_by_path) | set(current_by_path)):
        expected = str(existing_by_path.get(rel_path, {}).get("digest", "missing"))
        actual = str(current_by_path.get(rel_path, {}).get("digest", "missing"))
        if expected != actual:
            mismatches.append(
                {
                    "path": rel_path,
                    "expected_digest": expected,
                    "actual_digest": actual,
                }
            )
    return mismatches


def _check_manifest(
    vault: Path,
    out_path: str | None,
    *,
    zip_metadata_path: Path | None = None,
    distribution_zip_path: Path | None = None,
    zip_timestamp_timezone: str = DEFAULT_ZIP_TIMESTAMP_TIMEZONE,
) -> int:
    destination = resolve_schema_backed_report_output_path(
        vault, out_path, default_relative_path=DEFAULT_OUT
    )
    if not destination.exists():
        print(
            f"checked-in manifest not found: {display_path(vault, destination)}",
            file=sys.stderr,
        )
        return 1
    existing = json.loads(destination.read_text(encoding="utf-8"))
    existing_generated_at = _parse_utc_z(str(existing.get("generated_at", "")))
    replay_context = (
        RuntimeContext(
            display_timezone=dt.timezone.utc, clock=lambda: existing_generated_at
        )
        if existing_generated_at is not None
        else None
    )
    report = build_batch_manifest(
        vault,
        context=replay_context,
        zip_metadata_path=zip_metadata_path,
        distribution_zip_path=distribution_zip_path,
        zip_timestamp_timezone=zip_timestamp_timezone,
    )
    existing_source_freshness = _source_evidence_freshness(
        vault,
        str(existing.get("generated_at", "")),
        zip_metadata_path=zip_metadata_path,
        zip_timestamp_timezone=zip_timestamp_timezone,
    )
    digest_mismatches = _artifact_digest_mismatches(existing, report)
    # Remove timestamp-dependent fields before comparison; batch_id and
    # currentness.checked_at change between promote and verify.
    for payload in (report, existing):
        payload.pop("batch_id", None)
        if isinstance(payload.get("currentness"), dict):
            payload["currentness"].pop("checked_at", None)
        if isinstance(payload.get("input_fingerprints"), dict):
            payload["input_fingerprints"].pop("batch_id", None)
    content_matches = _strip_generated_at(report) == _strip_generated_at(existing)
    source_freshness_passes = existing_source_freshness.get("status") == "pass"
    if content_matches and source_freshness_passes:
        print(f"batch manifest check passed: {display_path(vault, destination)}")
        return 0
    if not content_matches:
        print(
            f"batch manifest check failed: content differs from {display_path(vault, destination)}",
            file=sys.stderr,
        )
    if not source_freshness_passes:
        print(
            "batch manifest check failed: source files changed after checked-in manifest generated_at",
            file=sys.stderr,
        )
        print(existing_source_freshness["summary"], file=sys.stderr)
        for item in existing_source_freshness.get("changed_after_generated_at", []):
            print(f"- {item['path']}: mtime {item['mtime']}", file=sys.stderr)
        for rel_path in existing_source_freshness.get("missing_zip_members", []):
            print(f"- {rel_path}: missing from ZIP metadata", file=sys.stderr)
    if digest_mismatches:
        print("artifact digest mismatches:", file=sys.stderr)
        for item in digest_mismatches:
            expected = item["expected_digest"]
            actual = item["actual_digest"]
            print(
                f"- {item['path']}: expected {expected[:12]}..., actual {actual[:12]}...",
                file=sys.stderr,
            )
    return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the release closeout batch manifest"
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify checked-in manifest matches current state without writing",
    )
    parser.add_argument(
        "--zip-metadata",
        default="",
        help="Use ZIP member timestamps for source freshness instead of filesystem mtimes.",
    )
    parser.add_argument(
        "--distribution-zip",
        default="",
        help=(
            "Bind the batch manifest to this source distribution ZIP. "
            "Defaults to --zip-metadata when omitted."
        ),
    )
    parser.add_argument(
        "--zip-timestamp-timezone",
        default=DEFAULT_ZIP_TIMESTAMP_TIMEZONE,
        help="Timezone used to interpret timezone-less ZIP member timestamps.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    zip_metadata_path = Path(args.zip_metadata) if args.zip_metadata else None
    distribution_zip_path = (
        Path(args.distribution_zip) if args.distribution_zip else None
    )
    if args.check:
        return _check_manifest(
            vault,
            args.out,
            zip_metadata_path=zip_metadata_path,
            distribution_zip_path=distribution_zip_path,
            zip_timestamp_timezone=args.zip_timestamp_timezone,
        )
    report = build_batch_manifest(
        vault,
        zip_metadata_path=zip_metadata_path,
        distribution_zip_path=distribution_zip_path,
        zip_timestamp_timezone=args.zip_timestamp_timezone,
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
