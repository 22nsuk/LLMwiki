#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import shlex
import subprocess
import sys
import tempfile
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        describe_output_file,
        read_json_object,
        write_schema_backed_report,
    )
    from ops.scripts.command_runtime import run_with_timeout
    from ops.scripts.output_runtime import display_path, resolve_output_path
    from ops.scripts.path_portability_runtime import (
        INFOZIP_C_LOCALE_COMPONENT_BYTE_LIMIT,
        infozip_c_locale_escape_byte_len,
        python_unicode_escape_byte_len,
        utf8_byte_len,
    )
    from ops.scripts.policy_runtime import (
        load_policy,
        release_archive_root_name_from_policy,
        zip_normalization_from_policy,
    )
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import RELEASE_SMOKE_SCHEMA_PATH
    from ops.scripts.schema_runtime import load_schema, validate_with_schema
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
    from ops.scripts.wiki_manifest import build_manifest, exclusion_policy, sha256_file
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        describe_output_file,
        read_json_object,
        write_schema_backed_report,
    )
    from ops.scripts.command_runtime import run_with_timeout
    from ops.scripts.output_runtime import display_path, resolve_output_path
    from ops.scripts.path_portability_runtime import (
        INFOZIP_C_LOCALE_COMPONENT_BYTE_LIMIT,
        infozip_c_locale_escape_byte_len,
        python_unicode_escape_byte_len,
        utf8_byte_len,
    )
    from ops.scripts.policy_runtime import (
        load_policy,
        release_archive_root_name_from_policy,
        zip_normalization_from_policy,
    )
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import RELEASE_SMOKE_SCHEMA_PATH
    from ops.scripts.schema_runtime import load_schema, validate_with_schema
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
    from ops.scripts.wiki_manifest import build_manifest, exclusion_policy, sha256_file


RELEASE_SMOKE_SCHEMA = RELEASE_SMOKE_SCHEMA_PATH
TAIL_LINE_COUNT = 40
EPHEMERAL_REPORT_PREFIX = "<tmp>"
PRODUCER = "ops.scripts.release_smoke"
FAST_PROFILE = "fast"
FULL_PROFILE = "full"
DEFAULT_REPORT_OUT = "ops/reports/release-smoke-report.json"
FAST_DEFAULT_REPORT_OUT = "ops/reports/release-smoke-report-fast.json"
PROFILE_DEFAULT_REPORT_OUTS = {
    FAST_PROFILE: FAST_DEFAULT_REPORT_OUT,
    FULL_PROFILE: DEFAULT_REPORT_OUT,
}
SMOKE_COMMAND_TIMEOUT_SECONDS = 5400
ZIP_PATH_BYTE_LIMIT = 65_535
ZIP_COMPONENT_BYTE_LIMIT = 255
POSIX_ESCAPE_EXPANDED_FILENAME_BYTE_LIMIT = 255
INFOZIP_C_LOCALE_FILENAME_BYTE_LIMIT = INFOZIP_C_LOCALE_COMPONENT_BYTE_LIMIT
TOP_ARCHIVE_OFFENDER_LIMIT = 10
ARCHIVE_SELF_DESCRIPTION_PATH = "release-archive-self-description.json"
DEFAULT_ARCHIVE_ROOT_NAME = "LLMwiki"
FUTURE_MTIME_GRACE_SECONDS = 60
FUTURE_MTIME_PREVIEW_LIMIT = 10
EVIDENCE_LINKAGE_PATHS = (
    "build/release/release-run-manifest.json",
    "build/release/release-closeout-batch-manifest.json",
    "build/release/release-evidence-closeout-self-check.json",
    "build/release/operator-release-summary.json",
    "build/release/external-report-reference-manifest.json",
    "ops/reports/learning-claim-evidence-bundle.json",
    "ops/reports/learning-confirmed-evidence-cohort.json",
    "ops/reports/learning-delta-scoreboard.json",
    "ops/reports/test-execution-summary-full.json",
)
SMOKE_COMMAND_SPECS = (
    (
        "raw_registry_preflight",
        ("-m", "ops.scripts.registry.raw_registry_preflight"),
        ("--release-archive-profile",),
    ),
    (
        "wiki_lint",
        ("-m", "ops.scripts.eval.wiki_lint"),
        ("--release-archive-profile",),
    ),
    (
        "wiki_eval",
        ("-m", "ops.scripts.eval.wiki_eval"),
        ("--release-archive-profile", "--require-max-score"),
    ),
    (
        "wiki_stage2_eval",
        ("-m", "ops.scripts.eval.wiki_stage2_eval"),
        ("--require-max-score",),
    ),
    (
        "planning_gate_validate",
        ("-m", "ops.scripts.mechanism.planning_gate_validate"),
        (),
    ),
)
PROFILE_SMOKE_COMMAND_SPECS = {
    FAST_PROFILE: (),
    FULL_PROFILE: SMOKE_COMMAND_SPECS,
}
PROFILE_SOURCE_COMMANDS = {
    FAST_PROFILE: "python -m ops.scripts.release.release_smoke --vault . --profile fast",
    FULL_PROFILE: "python -m ops.scripts.release.release_smoke --vault . --profile full",
}


class ReleaseArchiveBuildError(RuntimeError):
    def __init__(self, message: str, *, archive_write: dict) -> None:
        super().__init__(message)
        self.archive_write = archive_write


@dataclass(frozen=True)
class ReleaseSmokeReportRequest:
    vault: Path
    archive_path: Path
    extracted_vault: Path
    source_manifest: dict[str, Any]
    extracted_manifest: dict[str, Any]
    command_results: list[dict[str, Any]]
    resolved_policy_path: Path
    policy_version: int | str
    profile: str = FULL_PROFILE
    archive_root_name: str | None = None
    context: RuntimeContext | None = None
    ephemeral_root: Path | None = None
    output_parent_preflight: dict[str, Any] | None = None
    archive_reproducibility: dict[str, Any] | None = None


@dataclass(frozen=True)
class ReleaseSmokePartialReportRequest:
    vault: Path
    archive_path: Path
    extracted_vault: Path
    source_manifest: dict[str, Any] | None
    extracted_manifest: dict[str, Any] | None
    command_results: list[dict[str, Any]]
    resolved_policy_path: Path
    policy_version: int | str
    phase: str
    message: str
    profile: str = FULL_PROFILE
    archive_root_name: str | None = None
    error: str = ""
    context: RuntimeContext | None = None
    started_at_monotonic: float | None = None
    ephemeral_root: Path | None = None
    output_parent_preflight: dict[str, Any] | None = None
    archive_write: dict[str, Any] | None = None
    archive_reproducibility: dict[str, Any] | None = None


@dataclass
class _ReleaseSmokeExecution:
    args: argparse.Namespace
    vault: Path
    policy: dict[str, Any]
    resolved_policy_path: Path
    context: RuntimeContext
    archive_root_name: str
    out_path: str | None
    temp_root: Path
    archive_path: Path
    report_path: Path
    extract_root: Path
    extracted_vault: Path
    ephemeral_root: Path | None
    output_preflight: dict[str, Any]
    source_manifest: dict[str, Any] | None = None
    extracted_manifest: dict[str, Any] | None = None
    command_results: list[dict[str, Any]] = field(default_factory=list)
    archive_write: dict[str, Any] | None = None
    archive_reproducibility: dict[str, Any] | None = None
    started_at: float = 0.0
    phase: str = "output_parent_preflight"


def _smoke_command_specs(profile: str) -> tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]:
    try:
        return PROFILE_SMOKE_COMMAND_SPECS[profile]
    except KeyError as exc:  # pragma: no cover - parse_args guards this for CLI callers
        raise ValueError(f"unsupported release smoke profile: {profile}") from exc


def _source_command(profile: str) -> str:
    try:
        return PROFILE_SOURCE_COMMANDS[profile]
    except KeyError as exc:  # pragma: no cover - parse_args guards this for CLI callers
        raise ValueError(f"unsupported release smoke profile: {profile}") from exc


def _release_archive_root_name(policy: dict) -> str:
    try:
        return release_archive_root_name_from_policy(policy)
    except ValueError:
        return DEFAULT_ARCHIVE_ROOT_NAME


def default_report_out(profile: str) -> str:
    try:
        return PROFILE_DEFAULT_REPORT_OUTS[profile]
    except KeyError as exc:  # pragma: no cover - parse_args/build_report guard this for callers
        raise ValueError(f"unsupported release smoke profile: {profile}") from exc


def _normalized_zip_info(
    arcname: str,
    *,
    timestamp_utc: dt.datetime,
    file_mode: int,
) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(
        filename=arcname,
        date_time=timestamp_utc.astimezone(dt.UTC).timetuple()[:6],
    )
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (file_mode & 0xFFFF) << 16
    return info


def _manifest_digest(manifest: dict) -> str:
    normalized = {
        "files": sorted(
            (
                {
                    "path": str(item.get("path", "")),
                    "sha256": str(item.get("sha256", "")),
                    "size_bytes": int(item.get("size_bytes", 0) or 0),
                }
                for item in manifest.get("files", [])
                if isinstance(item, dict)
            ),
            key=lambda item: str(item["path"]),
        )
    }
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _top_level_surfaces(manifest: dict) -> list[str]:
    surfaces = set()
    for entry in manifest.get("files", []):
        if not isinstance(entry, dict):
            continue
        rel_path = str(entry.get("path", "")).strip()
        if not rel_path:
            continue
        surfaces.add(rel_path.split("/", 1)[0])
    return sorted(surfaces)


def _path_in_manifest(manifest: dict, prefix: str) -> bool:
    return any(
        isinstance(entry, dict)
        and (str(entry.get("path", "")) == prefix.rstrip("/") or str(entry.get("path", "")).startswith(prefix))
        for entry in manifest.get("files", [])
    )


def _evidence_linkage(vault: Path, manifest: dict) -> list[dict]:
    linked = []
    manifest_paths = {
        str(entry.get("path", ""))
        for entry in manifest.get("files", [])
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    for rel_path in EVIDENCE_LINKAGE_PATHS:
        path = vault / rel_path
        exists = path.is_file()
        linked.append(
            {
                "path": rel_path,
                "exists": exists,
                "included_in_zip": rel_path in manifest_paths,
                "sha256": sha256_file(path) if exists else "",
                "size_bytes": path.stat().st_size if exists else 0,
            }
        )
    return linked


def _git_commit(vault: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=vault,
        check=False,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _archive_self_description(vault: Path, manifest: dict, *, profile: str, archive_root_name: str) -> dict:
    policy_obj = manifest.get("exclusion_policy")
    policy = policy_obj if isinstance(policy_obj, dict) else {}
    return {
        "schema_version": 1,
        "artifact_kind": "release_archive_self_description",
        "producer": PRODUCER,
        "profile": profile,
        "git_commit": _git_commit(vault),
        "source_tree_fingerprint": release_source_tree_fingerprint(vault),
        "archive_root_name": archive_root_name,
        "archive_member_path": _archive_member_name(archive_root_name, ARCHIVE_SELF_DESCRIPTION_PATH),
        "source_manifest": {
            "digest": _manifest_digest(manifest),
            "file_count": len(manifest.get("files", [])),
        },
        "surfaces": {
            "included_top_level_surfaces": _top_level_surfaces(manifest),
            "excluded_prefixes": list(policy.get("excluded_prefixes", [])),
            "excluded_files": list(policy.get("excluded_files", [])),
            "excluded_cache_dirs": list(policy.get("excluded_cache_dirs", [])),
            "excluded_suffixes": list(policy.get("excluded_suffixes", [])),
            "tmp_included": _path_in_manifest(manifest, "tmp/"),
            "external_reports_included": _path_in_manifest(manifest, "external-reports/"),
            "runs_included": _path_in_manifest(manifest, "runs/"),
            "ops_reports_included": _path_in_manifest(manifest, "ops/reports/"),
        },
        "evidence_linkage": {
            "embedded_evidence_policy": "digest_link_only",
            "linkage_phase": "pre_seal_package_build_snapshot",
            "post_seal_authority": "build/release/release-sealed-run-manifest.json",
            "source_package_embeds_report_payloads": False,
            "linked_artifacts": _evidence_linkage(vault, manifest),
        },
    }


def _add_archive_self_description(
    vault: Path,
    manifest: dict,
    *,
    profile: str,
    archive_root_name: str,
    timestamp_utc: dt.datetime,
    file_mode: int,
    zf: zipfile.ZipFile,
) -> dict:
    description = _archive_self_description(
        vault,
        manifest,
        profile=profile,
        archive_root_name=archive_root_name,
    )
    payload = json.dumps(description, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    zf.writestr(
        _normalized_zip_info(
            _archive_member_name(archive_root_name, ARCHIVE_SELF_DESCRIPTION_PATH),
            timestamp_utc=timestamp_utc,
            file_mode=file_mode,
        ),
        payload,
    )
    self_entry = {
        "path": ARCHIVE_SELF_DESCRIPTION_PATH,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }
    enriched_manifest = copy.deepcopy(manifest)
    enriched_manifest["files"] = sorted(
        [*enriched_manifest.get("files", []), self_entry],
        key=lambda item: str(item["path"]),
    )
    enriched_manifest["archive_self_description"] = {
        "path": ARCHIVE_SELF_DESCRIPTION_PATH,
        "archive_root_name": archive_root_name,
        "archive_member_path": _archive_member_name(archive_root_name, ARCHIVE_SELF_DESCRIPTION_PATH),
        "sha256": self_entry["sha256"],
        "size_bytes": self_entry["size_bytes"],
        "profile": profile,
        "source_manifest_digest": description["source_manifest"]["digest"],
        "source_manifest_file_count": description["source_manifest"]["file_count"],
        "tmp_included": description["surfaces"]["tmp_included"],
        "external_reports_included": description["surfaces"]["external_reports_included"],
        "evidence_linkage_phase": description["evidence_linkage"]["linkage_phase"],
        "post_seal_authority": description["evidence_linkage"]["post_seal_authority"],
        "evidence_linked_artifact_count": len(description["evidence_linkage"]["linked_artifacts"]),
    }
    return enriched_manifest


def _archive_write_state(
    vault: Path,
    *,
    archive_path: Path,
    temp_path: Path,
    status: str,
    archive_replaced: bool,
    phase: str,
    quarantine_path: Path | None = None,
    error: str = "",
) -> dict:
    return {
        "status": status,
        "phase": phase,
        "archive_path": display_path(vault, archive_path),
        "temp_path": display_path(vault, temp_path),
        "quarantine_path": display_path(vault, quarantine_path) if quarantine_path is not None else "",
        "archive_replaced": archive_replaced,
        "error": error,
    }


def _quarantine_partial_archive(
    vault: Path,
    *,
    archive_path: Path,
    temp_path: Path,
    phase: str,
    error: str,
) -> dict:
    quarantine_path: Path | None = None
    if temp_path.exists():
        quarantine_path = archive_path.with_name(f".{archive_path.name}.{time.monotonic_ns()}.quarantine")
        quarantine_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.replace(quarantine_path)
    return _archive_write_state(
        vault,
        archive_path=archive_path,
        temp_path=temp_path,
        quarantine_path=quarantine_path,
        status="fail",
        archive_replaced=False,
        phase=phase,
        error=error,
    )


def _self_description_members(zf: zipfile.ZipFile, archive_root_name: str) -> list[str]:
    expected_member = _archive_member_name(archive_root_name, ARCHIVE_SELF_DESCRIPTION_PATH)
    return [
        info.filename
        for info in zf.infolist()
        if info.filename.replace("\\", "/") == expected_member
    ]


def _verify_release_archive(archive_path: Path, archive_root_name: str) -> None:
    with zipfile.ZipFile(archive_path) as zf:
        bad_member = zf.testzip()
        if bad_member is not None:
            raise ValueError(f"release archive integrity check failed for member: {bad_member}")
        self_description_member = _archive_member_name(archive_root_name, ARCHIVE_SELF_DESCRIPTION_PATH)
        self_description_members = _self_description_members(zf, archive_root_name)
        if len(self_description_members) != 1:
            raise ValueError(
                "release archive self-description member count must be exactly 1; "
                f"found {len(self_description_members)} at {self_description_member}"
            )
        payload = json.loads(zf.read(self_description_member).decode("utf-8"))
        if payload.get("artifact_kind") != "release_archive_self_description":
            raise ValueError("release archive self-description has invalid artifact_kind")


def _iso_from_timestamp(timestamp: float) -> str:
    return (
        dt.datetime.fromtimestamp(timestamp, tz=dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _future_mtime_files(
    vault: Path,
    manifest: dict,
    *,
    now_timestamp: float | None = None,
    grace_seconds: int = FUTURE_MTIME_GRACE_SECONDS,
) -> list[dict[str, Any]]:
    now = time.time() if now_timestamp is None else now_timestamp
    cutoff = now + grace_seconds
    future_files: list[dict[str, Any]] = []
    for entry in manifest.get("files", []):
        if not isinstance(entry, dict):
            continue
        rel_path = str(entry.get("path", "")).strip()
        if not rel_path:
            continue
        path = vault / rel_path
        if not path.is_file():
            continue
        mtime = path.stat().st_mtime
        if mtime <= cutoff:
            continue
        future_files.append(
            {
                "path": rel_path,
                "mtime_utc": _iso_from_timestamp(mtime),
                "seconds_after_now": round(mtime - now),
            }
        )
    return sorted(
        future_files,
        key=lambda item: (-int(item["seconds_after_now"]), str(item["path"])),
    )


def _future_mtime_error(future_files: list[dict[str, Any]]) -> str:
    preview = ", ".join(
        f"{item['path']}@{item['mtime_utc']}"
        for item in future_files[:FUTURE_MTIME_PREVIEW_LIMIT]
    )
    suffix = ""
    if len(future_files) > FUTURE_MTIME_PREVIEW_LIMIT:
        suffix = f"; +{len(future_files) - FUTURE_MTIME_PREVIEW_LIMIT} more"
    return (
        f"future mtime files in release archive input: count={len(future_files)}; "
        f"grace_seconds={FUTURE_MTIME_GRACE_SECONDS}; {preview}{suffix}"
    )


def build_release_archive(
    vault: Path,
    archive_path: Path,
    *,
    profile: str = FULL_PROFILE,
    archive_root_name: str | None = None,
) -> dict:
    policy, _ = load_policy(vault)
    zip_normalization = zip_normalization_from_policy(policy)
    resolved_archive_root_name = archive_root_name or release_archive_root_name_from_policy(policy)
    manifest = build_manifest(vault, archive_path)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = archive_path.with_name(f".{archive_path.name}.{time.monotonic_ns()}.tmp")
    if any(entry.get("path") == ARCHIVE_SELF_DESCRIPTION_PATH for entry in manifest.get("files", [])):
        archive_write = _archive_write_state(
            vault,
            archive_path=archive_path,
            temp_path=temp_path,
            status="fail",
            archive_replaced=False,
            phase="preflight_self_description_replay",
            error=(
                f"{ARCHIVE_SELF_DESCRIPTION_PATH} already exists in source tree; "
                "run release packaging from the full-vault source, not from an extracted source package"
            ),
        )
        raise ReleaseArchiveBuildError(
            "release archive build failed before writing duplicate self-description",
            archive_write=archive_write,
        )
    future_mtime_files = _future_mtime_files(vault, manifest)
    if future_mtime_files:
        archive_write = _archive_write_state(
            vault,
            archive_path=archive_path,
            temp_path=temp_path,
            status="fail",
            archive_replaced=False,
            phase="preflight_future_mtime",
            error=_future_mtime_error(future_mtime_files),
        )
        raise ReleaseArchiveBuildError(
            "release archive build failed before writing future-mtime inputs",
            archive_write=archive_write,
        )
    phase = "write_temp_archive"
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for entry in manifest["files"]:
                file_path = vault / entry["path"]
                arcname = _archive_member_name(resolved_archive_root_name, entry["path"])
                zf.writestr(
                    _normalized_zip_info(
                        arcname,
                        timestamp_utc=zip_normalization["timestamp_utc"],
                        file_mode=zip_normalization["file_mode"],
                    ),
                    file_path.read_bytes(),
                )
            manifest = _add_archive_self_description(
                vault,
                manifest,
                profile=profile,
                archive_root_name=resolved_archive_root_name,
                timestamp_utc=zip_normalization["timestamp_utc"],
                file_mode=zip_normalization["file_mode"],
                zf=zf,
            )
        phase = "verify_temp_archive"
        _verify_release_archive(temp_path, resolved_archive_root_name)
        phase = "atomic_replace"
        temp_path.replace(archive_path)
    except (Exception, KeyboardInterrupt) as exc:  # broad-exception: platform_cleanup_boundary
        error = f"{type(exc).__name__}: {exc}"
        archive_write = _quarantine_partial_archive(
            vault,
            archive_path=archive_path,
            temp_path=temp_path,
            phase=phase,
            error=error,
        )
        raise ReleaseArchiveBuildError("release archive build failed before atomic replace", archive_write=archive_write) from exc
    return manifest


def _archive_reproducibility_not_run() -> dict[str, Any]:
    return {
        "status": "not_run",
        "run_count": 0,
        "first_archive_sha256": "",
        "second_archive_sha256": "",
        "same_archive_sha256": False,
        "first_source_manifest_digest": "",
        "second_source_manifest_digest": "",
        "same_source_manifest_digest": False,
        "summary": "archive reproducibility check was not run",
    }


def _archive_reproducibility(
    *,
    first_manifest: dict[str, Any],
    second_manifest: dict[str, Any],
    first_archive_sha256: str,
    second_archive_sha256: str,
) -> dict[str, Any]:
    first_manifest_digest = _manifest_digest(first_manifest)
    second_manifest_digest = _manifest_digest(second_manifest)
    same_archive = first_archive_sha256 == second_archive_sha256
    same_manifest = first_manifest_digest == second_manifest_digest
    status = "pass" if same_archive and same_manifest else "fail"
    return {
        "status": status,
        "run_count": 2,
        "first_archive_sha256": first_archive_sha256,
        "second_archive_sha256": second_archive_sha256,
        "same_archive_sha256": same_archive,
        "first_source_manifest_digest": first_manifest_digest,
        "second_source_manifest_digest": second_manifest_digest,
        "same_source_manifest_digest": same_manifest,
        "summary": (
            f"archive_reproducibility={status}; "
            f"same_archive_sha256={str(same_archive).lower()}; "
            f"same_source_manifest_digest={str(same_manifest).lower()}"
        ),
    }


def _archive_member_name(archive_root_name: str, rel_path: str) -> str:
    normalized_rel_path = rel_path.replace("\\", "/").lstrip("/")
    return f"{archive_root_name}/{normalized_rel_path}"


def _byte_len(value: str) -> int:
    return utf8_byte_len(value)


def _escape_expanded_byte_len(value: str) -> int:
    return infozip_c_locale_escape_byte_len(value)


def _budget_status(actual: int, limit: int) -> str:
    return "pass" if actual <= limit else "fail"


def _archive_budget(archive_root_name: str, manifest: dict) -> dict:
    top_offenders = []
    max_zip_path_bytes = 0
    max_zip_component_bytes = 0
    max_posix_escape_expanded_filename_bytes = 0
    for entry in manifest["files"]:
        rel_path = entry["path"]
        archive_path = _archive_member_name(archive_root_name, rel_path)
        components = archive_path.split("/")
        zip_path_bytes = _byte_len(archive_path)
        zip_component_bytes = max((_byte_len(component) for component in components), default=0)
        posix_escape_expanded_filename_bytes = max(
            (_escape_expanded_byte_len(component) for component in components),
            default=0,
        )
        python_unicode_escape_filename_bytes = max(
            (python_unicode_escape_byte_len(component) for component in components),
            default=0,
        )
        max_zip_path_bytes = max(max_zip_path_bytes, zip_path_bytes)
        max_zip_component_bytes = max(max_zip_component_bytes, zip_component_bytes)
        max_posix_escape_expanded_filename_bytes = max(
            max_posix_escape_expanded_filename_bytes,
            posix_escape_expanded_filename_bytes,
        )
        top_offenders.append(
            {
                "path": rel_path,
                "archive_path": archive_path,
                "size_bytes": int(entry.get("size_bytes", 0)),
                "zip_path_bytes": zip_path_bytes,
                "zip_component_bytes": zip_component_bytes,
                "python_unicode_escape_filename_bytes": python_unicode_escape_filename_bytes,
                "posix_escape_expanded_filename_bytes": posix_escape_expanded_filename_bytes,
                "infozip_c_locale_escape_filename_bytes": posix_escape_expanded_filename_bytes,
                "max_budget_ratio": max(
                    zip_path_bytes / ZIP_PATH_BYTE_LIMIT,
                    zip_component_bytes / ZIP_COMPONENT_BYTE_LIMIT,
                    posix_escape_expanded_filename_bytes / POSIX_ESCAPE_EXPANDED_FILENAME_BYTE_LIMIT,
                ),
            }
        )

    top_offenders = sorted(
        top_offenders,
        key=lambda item: (
            -item["max_budget_ratio"],
            -item["zip_path_bytes"],
            -item["zip_component_bytes"],
            item["path"],
        ),
    )[:TOP_ARCHIVE_OFFENDER_LIMIT]
    zip_path_budget = {
        "limit_bytes": ZIP_PATH_BYTE_LIMIT,
        "max_bytes": max_zip_path_bytes,
        "status": _budget_status(max_zip_path_bytes, ZIP_PATH_BYTE_LIMIT),
    }
    zip_component_budget = {
        "limit_bytes": ZIP_COMPONENT_BYTE_LIMIT,
        "max_bytes": max_zip_component_bytes,
        "status": _budget_status(max_zip_component_bytes, ZIP_COMPONENT_BYTE_LIMIT),
    }
    posix_escape_expanded_filename_budget = {
        "limit_bytes": POSIX_ESCAPE_EXPANDED_FILENAME_BYTE_LIMIT,
        "max_bytes": max_posix_escape_expanded_filename_bytes,
        "status": _budget_status(
            max_posix_escape_expanded_filename_bytes,
            POSIX_ESCAPE_EXPANDED_FILENAME_BYTE_LIMIT,
        ),
    }
    blocking_budget_fail_count = sum(
        1
        for item in (zip_path_budget, zip_component_budget)
        if item["status"] == "fail"
    )
    platform_warning_count = 1 if posix_escape_expanded_filename_budget["status"] == "fail" else 0
    return {
        "pass": blocking_budget_fail_count == 0,
        "zip_path_byte_budget": zip_path_budget,
        "zip_component_byte_budget": zip_component_budget,
        "posix_escape_expanded_filename_budget": posix_escape_expanded_filename_budget,
        "blocking_budget_fail_count": blocking_budget_fail_count,
        "platform_warning_count": platform_warning_count,
        "platform_path_diagnostics": {
            "status": "warn" if platform_warning_count else "pass",
            "blocker_count": blocking_budget_fail_count,
            "warning_count": platform_warning_count,
            "diagnostics": [
                {
                    "id": "zip_path_byte_budget",
                    "status": zip_path_budget["status"],
                    "severity": "blocker",
                },
                {
                    "id": "zip_component_byte_budget",
                    "status": zip_component_budget["status"],
                    "severity": "blocker",
                },
                {
                    "id": "infozip_c_locale_escape_filename_budget",
                    "status": posix_escape_expanded_filename_budget["status"],
                    "severity": "warn",
                },
            ],
        },
        "top_offenders": top_offenders,
    }


def _archive_class(archive_root_name: str, source_manifest: dict) -> dict:
    return {
        "name": "release_smoke_zip",
        "format": "zip",
        "compression": "ZIP_DEFLATED",
        "root_prefix": archive_root_name,
        "member_path_template": f"{archive_root_name}/<manifest path>",
        "path_encoding": "utf-8",
        "zip_create_system": 3,
        "manifest_exclusion_policy": source_manifest.get("exclusion_policy") or exclusion_policy(),
    }


def output_parent_preflight(
    vault: Path,
    outputs: dict[str, Path],
    *,
    ephemeral_root: Path | None = None,
) -> dict:
    checks = []
    for name, path in outputs.items():
        parent = path.parent
        display = _display_release_path(vault, path, ephemeral_root=ephemeral_root)
        parent_display = _display_release_path(vault, parent, ephemeral_root=ephemeral_root)
        try:
            parent.mkdir(parents=True, exist_ok=True)
            if not parent.is_dir():
                raise NotADirectoryError(parent)
            probe_path = parent / f".{path.name}.preflight-{time.monotonic_ns()}.tmp"
            with probe_path.open("wb") as handle:
                handle.write(b"")
            probe_path.unlink(missing_ok=True)
            checks.append(
                {
                    "name": name,
                    "path": display,
                    "parent": parent_display,
                    "status": "pass",
                    "reason": "parent writable",
                }
            )
        except OSError as exc:
            checks.append(
                {
                    "name": name,
                    "path": display,
                    "parent": parent_display,
                    "status": "fail",
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
    return {
        "status": "pass" if all(item["status"] == "pass" for item in checks) else "fail",
        "checks": checks,
    }


def ensure_output_parent_preflight(vault: Path, outputs: dict[str, Path]) -> dict:
    preflight = output_parent_preflight(vault, outputs)
    if preflight["status"] != "pass":
        failures = [
            f"{item['name']} parent is not writable ({item['path']}): {item['reason']}"
            for item in preflight["checks"]
            if item["status"] != "pass"
        ]
        raise ValueError("; ".join(failures))
    return preflight


def extract_release_archive(archive_path: Path, extract_root: Path, archive_root_name: str = DEFAULT_ARCHIVE_ROOT_NAME) -> Path:
    with zipfile.ZipFile(archive_path) as zf:
        zf.extractall(extract_root)
    extracted_vault = extract_root / archive_root_name
    if not extracted_vault.exists():
        raise ValueError(f"release archive did not unpack expected root folder '{archive_root_name}'")
    return extracted_vault


def compare_manifests(source_manifest: dict, extracted_manifest: dict) -> dict:
    source_files = {entry["path"]: entry for entry in source_manifest["files"]}
    extracted_files = {entry["path"]: entry for entry in extracted_manifest["files"]}

    missing_paths = sorted(set(source_files) - set(extracted_files))
    unexpected_paths = sorted(set(extracted_files) - set(source_files))

    sha_mismatches = []
    size_mismatches = []
    for path in sorted(set(source_files) & set(extracted_files)):
        source_entry = source_files[path]
        extracted_entry = extracted_files[path]
        if source_entry["sha256"] != extracted_entry["sha256"]:
            sha_mismatches.append(
                {
                    "path": path,
                    "expected_sha256": source_entry["sha256"],
                    "actual_sha256": extracted_entry["sha256"],
                }
            )
        if source_entry["size_bytes"] != extracted_entry["size_bytes"]:
            size_mismatches.append(
                {
                    "path": path,
                    "expected_size_bytes": source_entry["size_bytes"],
                    "actual_size_bytes": extracted_entry["size_bytes"],
                }
            )

    return {
        "pass": not missing_paths and not unexpected_paths and not sha_mismatches and not size_mismatches,
        "expected_file_count": len(source_files),
        "extracted_file_count": len(extracted_files),
        "missing_paths": missing_paths,
        "unexpected_paths": unexpected_paths,
        "sha_mismatches": sha_mismatches,
        "size_mismatches": size_mismatches,
    }


def _tail_text(text: str, max_lines: int = TAIL_LINE_COUNT) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[-max_lines:])


def build_smoke_commands(vault: Path, python_bin: str, *, profile: str = FULL_PROFILE) -> list[tuple[str, list[str]]]:
    commands = []
    for name, module_args, extra_args in _smoke_command_specs(profile):
        commands.append(
            (
                name,
                [python_bin, *module_args, "--vault", ".", *extra_args],
            )
        )
    return commands


def run_smoke_commands(
    vault: Path,
    python_bin: str,
    *,
    profile: str = FULL_PROFILE,
    on_result: Callable[[list[dict]], None] | None = None,
) -> list[dict]:
    results = []
    for name, command in build_smoke_commands(vault, python_bin, profile=profile):
        started_at = time.monotonic()
        completed = run_with_timeout(
            command,
            cwd=vault,
            timeout_seconds=SMOKE_COMMAND_TIMEOUT_SECONDS,
        )
        results.append(
            {
                "name": name,
                "command": shlex.join(["python", *command[1:]]),
                "pass": completed.returncode == 0 and not completed.timed_out,
                "returncode": completed.returncode,
                "timed_out": completed.timed_out,
                "timeout_seconds": completed.timeout_seconds,
                "termination_reason": completed.termination_reason,
                "duration_ms": round((time.monotonic() - started_at) * 1000),
                "stdout_tail": _tail_text(completed.stdout),
                "stderr_tail": _tail_text(completed.stderr),
            }
        )
        if on_result is not None:
            on_result(list(results))
    return results


def _display_release_path(vault: Path, path: Path, *, ephemeral_root: Path | None = None) -> str:
    if ephemeral_root is not None:
        try:
            relative = path.relative_to(ephemeral_root)
        except ValueError:
            pass
        else:
            relative_text = relative.as_posix()
            if relative_text == ".":
                return EPHEMERAL_REPORT_PREFIX
            return f"{EPHEMERAL_REPORT_PREFIX}/{relative_text}"
    return display_path(vault, path)


def _render_release_smoke_report(request: ReleaseSmokeReportRequest) -> dict[str, Any]:
    manifest_comparison = compare_manifests(
        request.source_manifest,
        request.extracted_manifest,
    )
    resolved_archive_root_name = request.archive_root_name or DEFAULT_ARCHIVE_ROOT_NAME
    archive_budget = _archive_budget(
        resolved_archive_root_name,
        request.source_manifest,
    )
    archive_reproducibility = request.archive_reproducibility or _archive_reproducibility_not_run()
    status = (
        "pass"
        if manifest_comparison["pass"]
        and archive_budget["pass"]
        and all(item["pass"] for item in request.command_results)
        and archive_reproducibility["status"] in {"pass", "not_run"}
        else "fail"
    )
    runtime_context = request.context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    archive_display_path = _display_release_path(
        request.vault,
        request.archive_path,
        ephemeral_root=request.ephemeral_root,
    )
    report = {
        **build_canonical_report_envelope(
            request.vault,
            generated_at=generated_at,
            artifact_kind="release_smoke_report",
            producer=PRODUCER,
            source_command=_source_command(request.profile),
            resolved_policy_path=request.resolved_policy_path,
            schema_path=RELEASE_SMOKE_SCHEMA,
            source_paths=[
                "ops/scripts/release_smoke.py",
                "ops/scripts/command_runtime.py",
                "ops/scripts/wiki_manifest.py",
            ],
        ),
        "vault": display_path(request.vault, request.vault),
        "policy": {
            "path": display_path(request.vault, request.resolved_policy_path),
            "version": request.policy_version,
        },
        "generated_at": generated_at,
        "profile": request.profile,
        "status": status,
        "archive_path": archive_display_path,
        "archive_file": {
            "path": archive_display_path,
            **describe_output_file(request.archive_path),
        },
        "archive_class": _archive_class(
            resolved_archive_root_name,
            request.source_manifest,
        ),
        "archive_budget": archive_budget,
        "archive_reproducibility": archive_reproducibility,
        **(
            {"archive_self_description": request.source_manifest["archive_self_description"]}
            if isinstance(request.source_manifest.get("archive_self_description"), dict)
            else {}
        ),
        "extracted_vault": _display_release_path(
            request.vault,
            request.extracted_vault,
            ephemeral_root=request.ephemeral_root,
        ),
        "packed_file_count": len(request.source_manifest["files"]),
        "manifest_comparison": manifest_comparison,
        "commands": request.command_results,
    }
    if request.output_parent_preflight is not None:
        report["output_parent_preflight"] = request.output_parent_preflight
    return report


def build_report(request: ReleaseSmokeReportRequest) -> dict[str, Any]:
    return _render_release_smoke_report(request)


def _empty_manifest() -> dict:
    return {"files": [], "exclusion_policy": exclusion_policy()}


def _partial_manifest_comparison(source_manifest: dict, extracted_manifest: dict | None) -> dict:
    source_files = {
        entry["path"]: entry
        for entry in source_manifest.get("files", [])
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    extracted_files = {
        entry["path"]: entry
        for entry in (extracted_manifest or {}).get("files", [])
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    return {
        "pass": False,
        "expected_file_count": len(source_files),
        "extracted_file_count": len(extracted_files),
        "missing_paths": sorted(set(source_files) - set(extracted_files)),
        "unexpected_paths": sorted(set(extracted_files) - set(source_files)),
        "sha_mismatches": [],
        "size_mismatches": [],
    }


def _render_partial_release_smoke_report(
    request: ReleaseSmokePartialReportRequest,
) -> dict[str, Any]:
    runtime_context = request.context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    manifest = request.source_manifest or _empty_manifest()
    resolved_archive_root_name = request.archive_root_name or DEFAULT_ARCHIVE_ROOT_NAME
    archive_display_path = _display_release_path(
        request.vault,
        request.archive_path,
        ephemeral_root=request.ephemeral_root,
    )
    elapsed_ms = (
        0
        if request.started_at_monotonic is None
        else max(0, round((time.monotonic() - request.started_at_monotonic) * 1000))
    )
    report = {
        **build_canonical_report_envelope(
            request.vault,
            generated_at=generated_at,
            artifact_kind="release_smoke_report",
            producer=PRODUCER,
            source_command=_source_command(request.profile),
            resolved_policy_path=request.resolved_policy_path,
            schema_path=RELEASE_SMOKE_SCHEMA,
            source_paths=[
                "ops/scripts/release_smoke.py",
                "ops/scripts/command_runtime.py",
                "ops/scripts/wiki_manifest.py",
            ],
        ),
        "vault": display_path(request.vault, request.vault),
        "policy": {
            "path": display_path(request.vault, request.resolved_policy_path),
            "version": request.policy_version,
        },
        "generated_at": generated_at,
        "profile": request.profile,
        "status": "fail",
        "archive_path": archive_display_path,
        "archive_file": {
            "path": archive_display_path,
            **describe_output_file(request.archive_path),
        },
        "archive_class": _archive_class(resolved_archive_root_name, manifest),
        "archive_budget": _archive_budget(resolved_archive_root_name, manifest),
        "archive_reproducibility": request.archive_reproducibility
        or _archive_reproducibility_not_run(),
        "extracted_vault": _display_release_path(
            request.vault,
            request.extracted_vault,
            ephemeral_root=request.ephemeral_root,
        ),
        "packed_file_count": len(manifest.get("files", [])),
        "manifest_comparison": _partial_manifest_comparison(
            manifest,
            request.extracted_manifest,
        ),
        "commands": request.command_results,
        "partial_report": {
            "is_partial": True,
            "phase": request.phase,
            "elapsed_ms": elapsed_ms,
            "completed_command_count": len(request.command_results),
            "message": request.message,
            "error": request.error,
        },
    }
    if request.archive_write is not None:
        report["partial_report"]["archive_write"] = request.archive_write
    if request.output_parent_preflight is not None:
        report["output_parent_preflight"] = request.output_parent_preflight
    return report


def build_partial_report(request: ReleaseSmokePartialReportRequest) -> dict[str, Any]:
    return _render_partial_release_smoke_report(request)


def write_report(vault: Path, report: dict, out_path: str | None) -> Path | None:
    profile = str(report.get("profile", FULL_PROFILE)).strip() or FULL_PROFILE
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=RELEASE_SMOKE_SCHEMA,
            out_path=out_path,
            default_relative_path=default_report_out(profile),
            context="release smoke report schema validation failed",
            trailing_newline=False,
        )
    )


def _expected_envelope(
    vault: Path,
    *,
    profile: str,
    resolved_policy_path: Path,
    context: RuntimeContext,
) -> dict:
    return build_canonical_report_envelope(
        vault,
        generated_at=context.isoformat_z(),
        artifact_kind="release_smoke_report",
        producer=PRODUCER,
        source_command=_source_command(profile),
        resolved_policy_path=resolved_policy_path,
        schema_path=RELEASE_SMOKE_SCHEMA,
        source_paths=[
            "ops/scripts/release_smoke.py",
            "ops/scripts/command_runtime.py",
            "ops/scripts/wiki_manifest.py",
        ],
    )


def release_smoke_reuse_diagnostics(
    vault: Path,
    report_path: Path,
    *,
    profile: str,
    resolved_policy_path: Path,
    context: RuntimeContext,
) -> dict:
    diagnostics = {
        "reusable": False,
        "path": display_path(vault, report_path),
        "reason": "",
    }
    if not report_path.exists():
        diagnostics["reason"] = "report_missing"
        return diagnostics
    try:
        payload = read_json_object(report_path, context=display_path(vault, report_path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        diagnostics["reason"] = f"report_unreadable:{type(exc).__name__}"
        return diagnostics

    schema = load_schema(vault / RELEASE_SMOKE_SCHEMA)
    schema_errors = validate_with_schema(payload, schema)
    if schema_errors:
        diagnostics["reason"] = f"schema_invalid:{schema_errors[0]}"
        return diagnostics

    expected = _expected_envelope(
        vault,
        profile=profile,
        resolved_policy_path=resolved_policy_path,
        context=context,
    )
    checks = {
        "artifact_kind": payload.get("artifact_kind") == "release_smoke_report",
        "producer": payload.get("producer") == PRODUCER,
        "source_command": payload.get("source_command") == _source_command(profile),
        "profile": payload.get("profile") == profile,
        "status": payload.get("status") == "pass",
        "archive_file": isinstance(payload.get("archive_file"), dict)
        and payload["archive_file"].get("exists") is True,
        "currentness": isinstance(payload.get("currentness"), dict)
        and payload["currentness"].get("status") == "current",
        "source_revision": payload.get("source_revision") == expected.get("source_revision"),
        "source_tree_fingerprint": payload.get("source_tree_fingerprint") == expected.get("source_tree_fingerprint"),
        "input_fingerprints": payload.get("input_fingerprints") == expected.get("input_fingerprints"),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        diagnostics["reason"] = f"not_current:{','.join(failed)}"
        diagnostics["checks"] = checks
        return diagnostics

    diagnostics.update(
        {
            "reusable": True,
            "reason": "current_passing_release_smoke_report",
            "generated_at": str(payload.get("generated_at", "")),
            "source_tree_fingerprint": str(payload.get("source_tree_fingerprint", "")),
            "command_count": len(payload.get("commands", [])) if isinstance(payload.get("commands"), list) else 0,
        }
    )
    return diagnostics


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--python-bin", default=sys.executable)
    ap.add_argument("--profile", choices=[FAST_PROFILE, FULL_PROFILE], default=FULL_PROFILE)
    ap.add_argument("--archive-out")
    ap.add_argument("--out")
    ap.add_argument(
        "--archive-root-name",
        help="Fixed root folder name to use inside the release source ZIP.",
    )
    ap.add_argument("--reuse-if-current", action="store_true")
    ap.add_argument("--reuse-from")
    ap.add_argument(
        "--reuse-only",
        action="store_true",
        help="With --reuse-if-current, fail instead of executing when the reusable report is stale.",
    )
    return ap.parse_args(argv)


def _maybe_exit_with_reused_report(
    args: argparse.Namespace,
    *,
    vault: Path,
    resolved_policy_path: Path,
    context: RuntimeContext,
) -> None:
    if args.reuse_if_current:
        reuse_path = resolve_output_path(
            vault,
            args.reuse_from or args.out,
            default_relative_path=default_report_out(args.profile),
        )
        diagnostics = release_smoke_reuse_diagnostics(
            vault,
            reuse_path,
            profile=args.profile,
            resolved_policy_path=resolved_policy_path,
            context=context,
        )
        if diagnostics["reusable"]:
            print(json.dumps({"summary_mode": "reused", **diagnostics}, ensure_ascii=False, indent=2))
            print(f"\nreused_from={display_path(vault, reuse_path)}")
            raise SystemExit(0)
        print(json.dumps({"summary_mode": "executed", "reuse_diagnostics": diagnostics}, ensure_ascii=False, indent=2))
        if bool(getattr(args, "reuse_only", False)):
            raise SystemExit(1)


def _release_smoke_execution(
    args: argparse.Namespace,
    *,
    vault: Path,
    policy: dict[str, Any],
    resolved_policy_path: Path,
    context: RuntimeContext,
    archive_root_name: str,
    out_path: str | None,
    temp_root: Path,
) -> _ReleaseSmokeExecution:
    archive_path = (
        resolve_output_path(
            vault,
            args.archive_out,
            default_relative_path=f"tmp/{archive_root_name}-release-smoke.zip",
        )
        if args.archive_out
        else (temp_root / f"{archive_root_name}-release-smoke.zip").resolve()
    )
    report_path = resolve_output_path(
        vault,
        out_path,
        default_relative_path=default_report_out(args.profile),
    )
    extract_root = temp_root / "unpacked"
    output_preflight = output_parent_preflight(
        vault,
        {"archive": archive_path, "report": report_path},
        ephemeral_root=temp_root,
    )
    return _ReleaseSmokeExecution(
        args=args,
        vault=vault,
        policy=policy,
        resolved_policy_path=resolved_policy_path,
        context=context,
        archive_root_name=archive_root_name,
        out_path=out_path,
        temp_root=temp_root,
        archive_path=archive_path,
        report_path=report_path,
        extract_root=extract_root,
        extracted_vault=extract_root / archive_root_name,
        ephemeral_root=temp_root,
        output_preflight=output_preflight,
        started_at=time.monotonic(),
    )


def _partial_report(execution: _ReleaseSmokeExecution, *, phase: str, message: str, error: str = "") -> dict[str, Any]:
    return build_partial_report(
        ReleaseSmokePartialReportRequest(
            vault=execution.vault,
            archive_path=execution.archive_path,
            extracted_vault=execution.extracted_vault,
            source_manifest=execution.source_manifest,
            extracted_manifest=execution.extracted_manifest,
            command_results=execution.command_results,
            resolved_policy_path=execution.resolved_policy_path,
            policy_version=execution.policy["version"],
            profile=execution.args.profile,
            archive_root_name=execution.archive_root_name,
            phase=phase,
            message=message,
            error=error,
            context=execution.context,
            started_at_monotonic=execution.started_at,
            ephemeral_root=execution.ephemeral_root,
            output_parent_preflight=execution.output_preflight,
            archive_write=execution.archive_write,
            archive_reproducibility=execution.archive_reproducibility,
        )
    )


def _write_partial_report(
    execution: _ReleaseSmokeExecution,
    *,
    phase: str,
    message: str,
    error: str = "",
) -> Path | None:
    return write_report(
        execution.vault,
        _partial_report(execution, phase=phase, message=message, error=error),
        execution.out_path,
    )


def _output_preflight_error(output_preflight: dict[str, Any]) -> str:
    return "; ".join(
        f"{item['name']} parent is not writable ({item['path']}): {item['reason']}"
        for item in output_preflight["checks"]
        if item["status"] != "pass"
    )


def _exit_output_preflight_failure(execution: _ReleaseSmokeExecution) -> None:
    partial_report = _partial_report(
        execution,
        phase=execution.phase,
        message="release smoke output preflight failed",
        error=_output_preflight_error(execution.output_preflight),
    )
    report_parent_writable = any(
        item["name"] == "report" and item["status"] == "pass"
        for item in execution.output_preflight["checks"]
    )
    destination = write_report(execution.vault, partial_report, execution.out_path) if report_parent_writable else None
    print(json.dumps(partial_report, ensure_ascii=False, indent=2))
    if destination is not None:
        print(f"\nwritten_to={display_path(execution.vault, destination)}")
    raise SystemExit(1)


def _run_smoke_commands_with_progress(execution: _ReleaseSmokeExecution) -> None:
    def record_command_progress(results: list[dict]) -> None:
        execution.command_results = results
        _write_partial_report(
            execution,
            phase="smoke_commands",
            message=f"completed {len(results)} of {len(_smoke_command_specs(execution.args.profile))} smoke commands",
        )

    execution.command_results = run_smoke_commands(
        execution.extracted_vault,
        execution.args.python_bin,
        profile=execution.args.profile,
        on_result=record_command_progress,
    )


def _write_final_report(execution: _ReleaseSmokeExecution) -> None:
    report = build_report(
        ReleaseSmokeReportRequest(
            vault=execution.vault,
            archive_path=execution.archive_path,
            extracted_vault=execution.extracted_vault,
            source_manifest=cast(dict[str, Any], execution.source_manifest),
            extracted_manifest=cast(dict[str, Any], execution.extracted_manifest),
            command_results=execution.command_results,
            resolved_policy_path=execution.resolved_policy_path,
            policy_version=execution.policy["version"],
            profile=execution.args.profile,
            archive_root_name=execution.archive_root_name,
            context=execution.context,
            ephemeral_root=execution.ephemeral_root,
            output_parent_preflight=execution.output_preflight,
            archive_reproducibility=execution.archive_reproducibility,
        )
    )
    destination = write_report(execution.vault, report, execution.out_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if destination is not None:
        print(f"\nwritten_to={display_path(execution.vault, destination)}")
    raise SystemExit(0 if report["status"] == "pass" else 1)


def _execute_release_smoke(execution: _ReleaseSmokeExecution) -> None:
    if execution.output_preflight["status"] != "pass":
        _exit_output_preflight_failure(execution)
    execution.phase = "initialized"
    try:
        _write_partial_report(execution, phase=execution.phase, message="release smoke initialized")
        execution.phase = "build_archive"
        first_manifest = build_release_archive(
            execution.vault,
            execution.archive_path,
            profile=execution.args.profile,
            archive_root_name=execution.archive_root_name,
        )
        first_archive_sha256 = sha256_file(execution.archive_path)
        execution.source_manifest = first_manifest
        execution.phase = "archive_reproducibility_check"
        second_manifest = build_release_archive(
            execution.vault,
            execution.archive_path,
            profile=execution.args.profile,
            archive_root_name=execution.archive_root_name,
        )
        second_archive_sha256 = sha256_file(execution.archive_path)
        execution.source_manifest = second_manifest
        execution.archive_reproducibility = _archive_reproducibility(
            first_manifest=first_manifest,
            second_manifest=second_manifest,
            first_archive_sha256=first_archive_sha256,
            second_archive_sha256=second_archive_sha256,
        )
        execution.archive_write = _archive_write_state(
            execution.vault,
            archive_path=execution.archive_path,
            temp_path=execution.archive_path,
            status="pass",
            archive_replaced=True,
            phase="atomic_replace",
        )
        _write_partial_report(
            execution,
            phase="archive_reproducibility_checked",
            message="release archive built twice and reproducibility checked",
        )
        execution.phase = "extract_archive"
        execution.extracted_vault = extract_release_archive(
            execution.archive_path,
            execution.extract_root,
            execution.archive_root_name,
        )
        _write_partial_report(execution, phase="archive_extracted", message="release archive extracted")
        execution.phase = "build_extracted_manifest"
        execution.extracted_manifest = build_manifest(
            execution.extracted_vault,
            execution.extracted_vault / "ops" / "manifest.json",
        )
        _write_partial_report(execution, phase="manifest_built", message="extracted manifest built")
        execution.phase = "smoke_commands"
        _run_smoke_commands_with_progress(execution)
        _write_final_report(execution)
    except (Exception, KeyboardInterrupt) as exc:  # broad-exception: cli_boundary
        if isinstance(exc, ReleaseArchiveBuildError):
            execution.archive_write = exc.archive_write
        partial_report = _partial_report(
            execution,
            phase=execution.phase,
            message="release smoke stopped before final report",
            error=f"{type(exc).__name__}: {exc}",
        )
        destination = write_report(execution.vault, partial_report, execution.out_path)
        print(json.dumps(partial_report, ensure_ascii=False, indent=2))
        if destination is not None:
            print(f"\nwritten_to={display_path(execution.vault, destination)}")
        raise


def main() -> None:
    args = parse_args()
    vault = Path(args.vault).resolve()
    policy, resolved_policy_path = load_policy(vault)
    context = RuntimeContext.from_policy(policy)
    archive_root_name = getattr(args, "archive_root_name", None) or _release_archive_root_name(policy)
    _maybe_exit_with_reused_report(
        args,
        vault=vault,
        resolved_policy_path=resolved_policy_path,
        context=context,
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        execution = _release_smoke_execution(
            args,
            vault=vault,
            policy=policy,
            resolved_policy_path=resolved_policy_path,
            context=context,
            archive_root_name=archive_root_name,
            out_path=args.out,
            temp_root=Path(temp_dir).resolve(),
        )
        _execute_release_smoke(execution)


if __name__ == "__main__":
    main()
