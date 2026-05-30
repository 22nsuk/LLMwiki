#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
import time
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifact_freshness_runtime import build_canonical_report_envelope
from .artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    read_json_object,
    write_schema_backed_report,
)
from .command_runtime import CommandHeartbeat, run_with_timeout
from .output_runtime import display_path, resolve_vault_path, sanitize_report_text
from .policy_runtime import (
    load_policy,
    release_archive_root_name_from_policy,
    report_path,
)
from .runtime_context import RuntimeContext
from .schema_runtime import load_schema, validate_with_schema
from .source_revision_runtime import resolve_source_revision
from .source_tree_fingerprint_runtime import release_source_tree_fingerprint

DEFAULT_OUT = "ops/reports/source-package-clean-extract.json"
PRODUCER = "ops.scripts.source_package_clean_extract"
SCHEMA_PATH = "ops/schemas/source-package-clean-extract.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.source_package_clean_extract --vault ."
DEFAULT_TIMEOUT_SECONDS = 5400
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30
ARCHIVE_SELF_DESCRIPTION_PATH = "release-archive-self-description.json"


@dataclass(frozen=True)
class SourcePackageCleanExtractRequest:
    vault: Path
    source_zip: Path
    source_python: str
    ruff_targets: str
    mypy_targets: str
    test_summary_out: str
    deselection_policy: str
    pytest_mark_expr: str
    tests: str
    deselects: str
    pytest_flags: str
    zip_smoke_report: str
    extract_root: Path | None = None
    extract_parent: Path | None = None
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    heartbeat_interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    context: RuntimeContext | None = None
    policy_path: str | None = None


@dataclass(frozen=True)
class _BuildContext:
    policy: dict[str, Any]
    resolved_policy_path: Path
    runtime_context: RuntimeContext
    generated_at: str


@dataclass(frozen=True)
class _ExtractPaths:
    source_zip: Path
    extract_parent: Path
    extract_root: Path
    archive_root_name: str
    archive_root_source: str


@dataclass(frozen=True)
class _CleanExtractExecution:
    source_zip_exists: bool
    source_zip_digest: str
    extract_status: str
    extract_summary: str
    command_results: list[dict[str, Any]]
    test_summary_path: Path
    test_summary: dict[str, Any]
    test_summary_load_status: str
    deselection_budget: dict[str, Any]
    zip_smoke: dict[str, Any]
    command_status: str
    script_output_surfaces_status: str
    source_package_reproducibility_status: str
    heartbeat_observability: dict[str, Any]
    status: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tail(text: str, *, limit: int = 4000) -> str:
    return text if len(text) <= limit else text[-limit:]


def _command_payload(
    name: str,
    command: Sequence[str],
    *,
    cwd: Path,
    display_vault: Path,
    temp_roots: Sequence[Path] = (),
    timeout_seconds: int,
    heartbeat_interval_seconds: int,
) -> dict[str, Any]:
    started_at = time.monotonic()
    heartbeat_events: list[dict[str, Any]] = []

    def record_heartbeat(event: CommandHeartbeat) -> None:
        heartbeat_events.append(
            {
                "heartbeat_index": event.heartbeat_index,
                "elapsed_seconds": round(event.elapsed_seconds, 3),
                "timeout_seconds": event.timeout_seconds,
                "quiet_seconds": event.quiet_seconds,
                "observation_mode": event.observation_mode,
            }
        )

    result = run_with_timeout(
        list(command),
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        heartbeat_callback=record_heartbeat,
    )
    return {
        "name": name,
        "command": [
            sanitize_report_text(display_vault, item, temp_roots=temp_roots)
            for item in command
        ],
        "returncode": result.returncode,
        "timed_out": result.timed_out,
        "timeout_seconds": result.timeout_seconds,
        "termination_reason": result.termination_reason,
        "duration_ms": int(round((time.monotonic() - started_at) * 1000)),
        "heartbeat_count": result.heartbeat_count,
        "heartbeat_interval_seconds": result.heartbeat_interval_seconds,
        "quiet_seconds": result.quiet_seconds,
        "observation_mode": result.observation_mode,
        "heartbeat_events": heartbeat_events,
        "stdout_tail": sanitize_report_text(
            display_vault,
            _tail(result.stdout),
            temp_roots=temp_roots,
        ),
        "stderr_tail": sanitize_report_text(
            display_vault,
            _tail(result.stderr),
            temp_roots=temp_roots,
        ),
        "status": "pass" if result.returncode == 0 and not result.timed_out else "fail",
    }


def _load_optional(vault: Path, rel_path: str) -> tuple[dict[str, Any], str]:
    raw_payload, diagnostics = load_optional_json_object_with_diagnostics(vault / rel_path)
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    return payload, str(diagnostics.get("status", "unknown")).strip() or "unknown"


def _archive_root_name_from_zip(source_zip: Path, fallback_root_name: str) -> tuple[str, str]:
    if not source_zip.is_file():
        return fallback_root_name, "policy_fallback"
    try:
        with zipfile.ZipFile(source_zip) as archive:
            root_names = set()
            for info in archive.infolist():
                normalized = info.filename.replace("\\", "/")
                if "/" in normalized and not normalized.startswith("/"):
                    root_names.add(normalized.split("/", 1)[0])
                if not normalized.endswith(f"/{ARCHIVE_SELF_DESCRIPTION_PATH}"):
                    continue
                payload = json.loads(archive.read(info.filename).decode("utf-8"))
                archive_root_name = str(payload.get("archive_root_name", "")).strip()
                if archive_root_name:
                    return archive_root_name, "archive_self_description"
            if len(root_names) == 1:
                return next(iter(root_names)), "zip_root_prefix"
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile):
        return fallback_root_name, "policy_fallback"
    return fallback_root_name, "policy_fallback"


def _resolve_extract_paths(
    *,
    source_zip: Path,
    policy: dict[str, Any],
    extract_root: Path | None,
    extract_parent: Path | None,
) -> tuple[Path, Path, str, str]:
    policy_root_name = release_archive_root_name_from_policy(policy)
    if extract_root is not None:
        resolved_extract_root = extract_root.resolve()
        return (
            resolved_extract_root.parent,
            resolved_extract_root,
            resolved_extract_root.name,
            "explicit_extract_root",
        )
    archive_root_name, archive_root_source = _archive_root_name_from_zip(source_zip, policy_root_name)
    resolved_extract_parent = (extract_parent or (source_zip.parent / "extract")).resolve()
    return (
        resolved_extract_parent,
        resolved_extract_parent / archive_root_name,
        archive_root_name,
        archive_root_source,
    )


def _extract_zip(source_zip: Path, extract_parent: Path, extract_root: Path) -> tuple[str, str]:
    if not source_zip.is_file():
        return "fail", "source zip is missing"
    try:
        if extract_parent.exists():
            shutil.rmtree(extract_parent)
        extract_parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source_zip) as archive:
            archive.extractall(extract_parent)
    except (OSError, zipfile.BadZipFile) as exc:
        return "fail", str(exc)
    return ("pass", "source package extracted") if extract_root.is_dir() else ("fail", "expected extract root was not created")


def _deselection_budget_status(test_summary: dict[str, Any], load_status: str) -> dict[str, Any]:
    raw_lifecycle = test_summary.get("deselection_lifecycle")
    lifecycle: dict[str, Any] = raw_lifecycle if isinstance(raw_lifecycle, dict) else {}
    if load_status != "ok":
        return {
            "status": "unknown",
            "load_status": load_status,
            "actual_deselected_count": 0,
            "max_allowed_deselected_count": 0,
            "over_budget": False,
            "expires_at": "",
            "next_action": "source package test summary unavailable",
        }
    return {
        "status": str(lifecycle.get("status", "unknown")).strip() or "unknown",
        "load_status": load_status,
        "actual_deselected_count": int(lifecycle.get("actual_deselected_count", 0) or 0),
        "max_allowed_deselected_count": int(lifecycle.get("max_allowed_deselected_count", 0) or 0),
        "over_budget": bool(lifecycle.get("over_budget", False)),
        "expires_at": str(lifecycle.get("expires_at", "")).strip(),
        "next_action": str(lifecycle.get("next_action", "")).strip() or "none",
    }


def _zip_smoke_status(vault: Path, rel_path: str) -> dict[str, Any]:
    payload, load_status = _load_optional(vault, rel_path)
    raw_archive_budget = payload.get("archive_budget")
    archive_budget: dict[str, Any] = raw_archive_budget if isinstance(raw_archive_budget, dict) else {}
    raw_manifest_comparison = payload.get("manifest_comparison")
    manifest_comparison: dict[str, Any] = (
        raw_manifest_comparison if isinstance(raw_manifest_comparison, dict) else {}
    )
    return {
        "path": rel_path,
        "load_status": load_status,
        "status": str(payload.get("status", "unknown")).strip() if payload else "unknown",
        "manifest_comparison_pass": bool(manifest_comparison.get("pass")),
        "archive_budget_pass": bool(archive_budget.get("pass", False)),
    }


def _clean_extract_request(
    vault_or_request: Path | SourcePackageCleanExtractRequest,
    legacy_fields: dict[str, Any],
) -> SourcePackageCleanExtractRequest:
    if isinstance(vault_or_request, SourcePackageCleanExtractRequest):
        if legacy_fields:
            raise TypeError("build_report accepts either a request object or legacy keyword fields")
        return vault_or_request
    return SourcePackageCleanExtractRequest(vault=vault_or_request, **legacy_fields)


def _build_context(request: SourcePackageCleanExtractRequest) -> _BuildContext:
    policy, resolved_policy_path = load_policy(request.vault, request.policy_path)
    runtime_context = request.context or RuntimeContext.from_policy(policy)
    return _BuildContext(
        policy=policy,
        resolved_policy_path=resolved_policy_path,
        runtime_context=runtime_context,
        generated_at=runtime_context.isoformat_z(),
    )


def _extract_paths(request: SourcePackageCleanExtractRequest, policy: dict[str, Any]) -> _ExtractPaths:
    source_zip = request.source_zip.resolve()
    extract_parent, extract_root, archive_root_name, archive_root_source = _resolve_extract_paths(
        source_zip=source_zip,
        policy=policy,
        extract_root=request.extract_root,
        extract_parent=request.extract_parent,
    )
    return _ExtractPaths(
        source_zip=source_zip,
        extract_parent=extract_parent,
        extract_root=extract_root,
        archive_root_name=archive_root_name,
        archive_root_source=archive_root_source,
    )


def _source_package_test_command(request: SourcePackageCleanExtractRequest) -> list[str]:
    return [
        request.source_python,
        "-m",
        "ops.scripts.test_execution_summary",
        "--vault",
        ".",
        "--out",
        request.test_summary_out,
        "--suite",
        "source-package",
        "--collect-nodeids",
        "--deselection-policy",
        request.deselection_policy,
        "--",
        request.source_python,
        "-m",
        "pytest",
        "-m",
        request.pytest_mark_expr,
        *shlex.split(request.tests),
        *shlex.split(request.deselects),
        *shlex.split(request.pytest_flags),
    ]


def _script_output_surfaces_command(request: SourcePackageCleanExtractRequest) -> list[str]:
    return [
        request.source_python,
        "-m",
        "ops.scripts.script_output_surfaces",
        "--vault",
        ".",
        "--out",
        "ops/script-output-surfaces.json",
    ]


def _clean_extract_commands(
    request: SourcePackageCleanExtractRequest,
    paths: _ExtractPaths,
    extract_status: str,
) -> list[dict[str, Any]]:
    if extract_status != "pass":
        return []
    commands = [
        ("script-output-surfaces", _script_output_surfaces_command(request)),
        ("ruff", [request.source_python, "-m", "ruff", "check", *shlex.split(request.ruff_targets)]),
        ("mypy", [request.source_python, "-m", "mypy", *shlex.split(request.mypy_targets)]),
        ("source-package-pytest", _source_package_test_command(request)),
    ]
    return [
        _command_payload(
            name,
            command,
            cwd=paths.extract_root,
            display_vault=request.vault,
            temp_roots=(paths.extract_parent,),
            timeout_seconds=request.timeout_seconds,
            heartbeat_interval_seconds=request.heartbeat_interval_seconds,
        )
        for name, command in commands
    ]


def _command_status(command_results: list[dict[str, Any]]) -> str:
    if command_results and all(item["status"] == "pass" for item in command_results):
        return "pass"
    return "fail"


def _source_package_reproducibility_status(
    *,
    zip_smoke: dict[str, Any],
    extract_status: str,
) -> str:
    if (
        zip_smoke["status"] == "pass"
        and zip_smoke["manifest_comparison_pass"]
        and zip_smoke["archive_budget_pass"]
        and extract_status == "pass"
    ):
        return "pass"
    return "fail"


def _heartbeat_observability(command_results: list[dict[str, Any]]) -> dict[str, Any]:
    if not command_results:
        return {
            "status": "not_run",
            "command_count": 0,
            "heartbeat_enabled_command_count": 0,
            "heartbeat_event_count": 0,
            "max_heartbeat_count": 0,
            "max_quiet_seconds": 0,
            "quiet_command_names": [],
            "unobserved_command_names": [],
            "next_action": "source package commands did not run",
        }

    heartbeat_enabled = [
        item
        for item in command_results
        if item.get("observation_mode") == "process_heartbeat"
        and int(item.get("heartbeat_interval_seconds", 0) or 0) > 0
    ]
    unobserved = [
        str(item.get("name", "")).strip()
        for item in command_results
        if item not in heartbeat_enabled
    ]
    quiet_commands = [
        str(item.get("name", "")).strip()
        for item in command_results
        if int(item.get("quiet_seconds", 0) or 0) > 0
    ]
    heartbeat_event_count = sum(
        len(item.get("heartbeat_events", []))
        for item in command_results
        if isinstance(item.get("heartbeat_events"), list)
    )
    max_heartbeat_count = max(
        int(item.get("heartbeat_count", 0) or 0) for item in command_results
    )
    max_quiet_seconds = max(
        int(item.get("quiet_seconds", 0) or 0) for item in command_results
    )
    status = "pass" if len(heartbeat_enabled) == len(command_results) else "attention"
    if status == "attention":
        next_action = "route all source-package replay commands through heartbeat-enabled command runtime"
    elif heartbeat_event_count > 0:
        next_action = "inspect heartbeat_events for long quiet nested replay phases"
    else:
        next_action = "none"
    return {
        "status": status,
        "command_count": len(command_results),
        "heartbeat_enabled_command_count": len(heartbeat_enabled),
        "heartbeat_event_count": heartbeat_event_count,
        "max_heartbeat_count": max_heartbeat_count,
        "max_quiet_seconds": max_quiet_seconds,
        "quiet_command_names": [name for name in quiet_commands if name],
        "unobserved_command_names": [name for name in unobserved if name],
        "next_action": next_action,
    }


def _overall_status(
    *,
    source_zip_exists: bool,
    extract_status: str,
    command_status: str,
    deselection_budget: dict[str, Any],
    source_package_reproducibility_status: str,
) -> str:
    if (
        source_zip_exists
        and extract_status == "pass"
        and command_status == "pass"
        and deselection_budget["status"] == "pass"
        and source_package_reproducibility_status == "pass"
    ):
        return "pass"
    return "fail"


def _clean_extract_execution(
    request: SourcePackageCleanExtractRequest,
    paths: _ExtractPaths,
) -> _CleanExtractExecution:
    source_zip_exists = paths.source_zip.is_file()
    source_zip_digest = _sha256_file(paths.source_zip) if source_zip_exists else ""
    extract_status, extract_summary = _extract_zip(paths.source_zip, paths.extract_parent, paths.extract_root)
    command_results = _clean_extract_commands(request, paths, extract_status)

    test_summary_path = paths.extract_root / request.test_summary_out
    test_summary_payload, load_diagnostics = load_optional_json_object_with_diagnostics(test_summary_path)
    test_summary = test_summary_payload
    test_summary_load_status = str(load_diagnostics.get("status", "unknown")).strip() or "unknown"
    deselection_budget = _deselection_budget_status(test_summary, test_summary_load_status)
    zip_smoke = _zip_smoke_status(request.vault, request.zip_smoke_report)
    command_status = _command_status(command_results)
    script_output_surfaces_status = _named_command_status(command_results, "script-output-surfaces")
    heartbeat_observability = _heartbeat_observability(command_results)
    reproducibility_status = _source_package_reproducibility_status(
        zip_smoke=zip_smoke,
        extract_status=extract_status,
    )
    status = _overall_status(
        source_zip_exists=source_zip_exists,
        extract_status=extract_status,
        command_status=command_status,
        deselection_budget=deselection_budget,
        source_package_reproducibility_status=reproducibility_status,
    )
    return _CleanExtractExecution(
        source_zip_exists=source_zip_exists,
        source_zip_digest=source_zip_digest,
        extract_status=extract_status,
        extract_summary=extract_summary,
        command_results=command_results,
        test_summary_path=test_summary_path,
        test_summary=test_summary,
        test_summary_load_status=test_summary_load_status,
        deselection_budget=deselection_budget,
        zip_smoke=zip_smoke,
        command_status=command_status,
        script_output_surfaces_status=script_output_surfaces_status,
        source_package_reproducibility_status=reproducibility_status,
        heartbeat_observability=heartbeat_observability,
        status=status,
    )


def _named_command_status(command_results: list[dict[str, Any]], command_name: str) -> str:
    return next((item["status"] for item in command_results if item["name"] == command_name), "not_run")


def _canonical_envelope(
    request: SourcePackageCleanExtractRequest,
    build_context: _BuildContext,
    paths: _ExtractPaths,
    execution: _CleanExtractExecution,
) -> dict[str, Any]:
    return build_canonical_report_envelope(
        request.vault,
        generated_at=build_context.generated_at,
        artifact_kind="source_package_clean_extract",
        producer=PRODUCER,
        source_command=SOURCE_COMMAND,
        resolved_policy_path=build_context.resolved_policy_path,
        schema_path=SCHEMA_PATH,
        source_paths=["ops/scripts/core/source_package_clean_extract.py"],
        file_inputs={
            "source_zip": display_path(request.vault, paths.source_zip),
            "zip_smoke_report": request.zip_smoke_report,
        },
        text_inputs={
            "source_python": sanitize_report_text(request.vault, request.source_python),
            "archive_root_name": paths.archive_root_name,
            "archive_root_source": paths.archive_root_source,
            "ruff_targets": request.ruff_targets,
            "mypy_targets": request.mypy_targets,
            "pytest_mark_expr": request.pytest_mark_expr,
            "tests": request.tests,
            "deselects": request.deselects,
            "pytest_flags": request.pytest_flags,
            "test_summary_out": request.test_summary_out,
            "deselection_policy": request.deselection_policy,
            "heartbeat_interval_seconds": str(request.heartbeat_interval_seconds),
            "script_output_surfaces_out": "ops/script-output-surfaces.json",
            "status": execution.status,
        },
    )


def _render_report(
    request: SourcePackageCleanExtractRequest,
    build_context: _BuildContext,
    paths: _ExtractPaths,
    execution: _CleanExtractExecution,
) -> dict[str, Any]:
    command_results = execution.command_results
    test_summary = execution.test_summary
    return {
        **_canonical_envelope(request, build_context, paths, execution),
        "vault": report_path(request.vault, request.vault),
        "policy": {
            "path": report_path(request.vault, build_context.resolved_policy_path),
            "version": build_context.policy.get("version"),
        },
        "status": execution.status,
        "source_zip": {
            "path": display_path(request.vault, paths.source_zip),
            "exists": execution.source_zip_exists,
            "sha256": execution.source_zip_digest,
        },
        "extract": {
            "parent": display_path(request.vault, paths.extract_parent),
            "root": display_path(request.vault, paths.extract_root),
            "archive_root_name": paths.archive_root_name,
            "archive_root_source": paths.archive_root_source,
            "status": execution.extract_status,
            "summary": execution.extract_summary,
        },
        "commands": command_results,
        "script_output_surfaces_status": execution.script_output_surfaces_status,
        "ruff_status": _named_command_status(command_results, "ruff"),
        "mypy_status": _named_command_status(command_results, "mypy"),
        "test_source_package_status": _named_command_status(command_results, "source-package-pytest"),
        "test_source_package_summary": {
            "path": display_path(request.vault, execution.test_summary_path),
            "load_status": execution.test_summary_load_status,
            "status": str(test_summary.get("status", "unknown")).strip() if test_summary else "unknown",
        },
        "deselection_budget_status": execution.deselection_budget,
        "source_package_reproducibility_status": execution.source_package_reproducibility_status,
        "heartbeat_observability": execution.heartbeat_observability,
        "zip_smoke_report": execution.zip_smoke,
    }


def build_report(
    vault_or_request: Path | SourcePackageCleanExtractRequest,
    **legacy_fields: Any,
) -> dict[str, Any]:
    request = _clean_extract_request(vault_or_request, legacy_fields)
    build_context = _build_context(request)
    paths = _extract_paths(request, build_context.policy)
    execution = _clean_extract_execution(request, paths)
    return _render_report(request, build_context, paths, execution)


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="source package clean extract schema validation failed",
            trailing_newline=True,
        )
    )


def reusable_report_diagnostics(
    request: SourcePackageCleanExtractRequest,
    path_value: str | Path,
) -> dict[str, Any]:
    path = resolve_vault_path(request.vault, path_value)
    diagnostics: dict[str, Any] = {
        "reusable": False,
        "path": display_path(request.vault, path),
        "reason": "",
    }
    if not path.is_file():
        diagnostics["reason"] = "report_missing"
        return diagnostics
    try:
        payload = read_json_object(path, context=display_path(request.vault, path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        diagnostics["reason"] = f"report_unreadable:{type(exc).__name__}"
        return diagnostics
    schema_errors = validate_with_schema(payload, load_schema(request.vault / SCHEMA_PATH))
    if schema_errors:
        diagnostics["reason"] = f"schema_invalid:{schema_errors[0]}"
        return diagnostics
    build_context = _build_context(request)
    paths = _extract_paths(request, build_context.policy)
    source_zip_exists = paths.source_zip.is_file()
    source_zip_digest = _sha256_file(paths.source_zip) if source_zip_exists else ""
    expected_input_fingerprints = _canonical_envelope(
        request,
        build_context,
        paths,
        _CleanExtractExecution(
            source_zip_exists=source_zip_exists,
            source_zip_digest=source_zip_digest,
            extract_status="pass",
            extract_summary="expected",
            command_results=[],
            test_summary_path=paths.extract_root / request.test_summary_out,
            test_summary={},
            test_summary_load_status="ok",
            deselection_budget={
                "status": "pass",
                "load_status": "ok",
                "actual_deselected_count": 0,
                "max_allowed_deselected_count": 0,
                "over_budget": False,
                "expires_at": "",
                "next_action": "none",
            },
            zip_smoke=_zip_smoke_status(request.vault, request.zip_smoke_report),
            command_status="pass",
            script_output_surfaces_status="pass",
            source_package_reproducibility_status="pass",
            heartbeat_observability={
                "status": "pass",
                "command_count": 0,
                "heartbeat_enabled_command_count": 0,
                "heartbeat_event_count": 0,
                "max_heartbeat_count": 0,
                "max_quiet_seconds": 0,
                "quiet_command_names": [],
                "unobserved_command_names": [],
                "next_action": "none",
            },
            status="pass",
        ),
    )["input_fingerprints"]
    checks = {
        "artifact_kind": payload.get("artifact_kind") == "source_package_clean_extract",
        "producer": payload.get("producer") == PRODUCER,
        "status": payload.get("status") == "pass",
        "currentness": isinstance(payload.get("currentness"), dict)
        and payload["currentness"].get("status") == "current",
        "source_revision": payload.get("source_revision") == resolve_source_revision(request.vault).revision,
        "source_tree_fingerprint": payload.get("source_tree_fingerprint") == release_source_tree_fingerprint(request.vault),
        "input_fingerprints": payload.get("input_fingerprints") == expected_input_fingerprints,
        "source_zip_exists": isinstance(payload.get("source_zip"), dict)
        and payload["source_zip"].get("exists") is True,
        "source_zip_sha256": isinstance(payload.get("source_zip"), dict)
        and payload["source_zip"].get("sha256") == source_zip_digest,
        "test_source_package_status": payload.get("test_source_package_status") == "pass",
        "deselection_budget_status": isinstance(payload.get("deselection_budget_status"), dict)
        and payload["deselection_budget_status"].get("status") == "pass",
        "source_package_reproducibility_status": payload.get("source_package_reproducibility_status") == "pass",
        "zip_smoke_report_status": isinstance(payload.get("zip_smoke_report"), dict)
        and payload["zip_smoke_report"].get("status") == "pass",
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        diagnostics["reason"] = f"not_current:{','.join(failed)}"
        diagnostics["checks"] = checks
        return diagnostics
    diagnostics.update(
        {
            "reusable": True,
            "reason": "current_passing_source_package_clean_extract",
            "generated_at": str(payload.get("generated_at", "")),
            "source_tree_fingerprint": str(payload.get("source_tree_fingerprint", "")),
        }
    )
    return diagnostics


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run and record clean-extract source package checks.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--source-zip", required=True)
    parser.add_argument("--extract-root")
    parser.add_argument(
        "--extract-parent",
        help=(
            "Directory where the source package root folder should be unpacked. "
            "The archive root name is read from release-archive-self-description.json, then policy, when omitted."
        ),
    )
    parser.add_argument("--source-python", required=True)
    parser.add_argument("--ruff-targets", required=True)
    parser.add_argument("--mypy-targets", required=True)
    parser.add_argument("--test-summary-out", required=True)
    parser.add_argument("--deselection-policy", required=True)
    parser.add_argument("--pytest-mark-expr", required=True)
    parser.add_argument("--tests", required=True)
    parser.add_argument("--deselects", default="")
    parser.add_argument("--pytest-flags", default="")
    parser.add_argument("--zip-smoke-report", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--reuse-if-current", action="store_true")
    parser.add_argument("--reuse-from")
    parser.add_argument(
        "--reuse-only",
        action="store_true",
        help="With --reuse-if-current, fail instead of rerunning when clean-extract evidence is stale.",
    )
    parser.add_argument(
        "--heartbeat-interval-seconds",
        type=int,
        default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if bool(args.extract_root) == bool(args.extract_parent):
        raise SystemExit("exactly one of --extract-root or --extract-parent is required")
    vault = Path(args.vault).resolve()
    request = SourcePackageCleanExtractRequest(
        vault=vault,
        source_zip=resolve_vault_path(vault, args.source_zip),
        extract_root=resolve_vault_path(vault, args.extract_root) if args.extract_root else None,
        extract_parent=resolve_vault_path(vault, args.extract_parent) if args.extract_parent else None,
        source_python=args.source_python,
        ruff_targets=args.ruff_targets,
        mypy_targets=args.mypy_targets,
        test_summary_out=args.test_summary_out,
        deselection_policy=args.deselection_policy,
        pytest_mark_expr=args.pytest_mark_expr,
        tests=args.tests,
        deselects=args.deselects,
        pytest_flags=args.pytest_flags,
        zip_smoke_report=args.zip_smoke_report,
        timeout_seconds=args.timeout_seconds,
        heartbeat_interval_seconds=args.heartbeat_interval_seconds,
        policy_path=args.policy_path,
    )
    if args.reuse_if_current:
        diagnostics = reusable_report_diagnostics(request, args.reuse_from or args.out)
        if diagnostics["reusable"]:
            print(json.dumps({"summary_mode": "reused", **diagnostics}, ensure_ascii=False, indent=2))
            return 0
        print(json.dumps({"summary_mode": "executed", "reuse_diagnostics": diagnostics}, ensure_ascii=False, indent=2))
        if args.reuse_only:
            return 1
    report = build_report(request)
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
