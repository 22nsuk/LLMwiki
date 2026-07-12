#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
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
    from ops.scripts.core.command_runtime import (
        CommandHeartbeat,
        TimedProcessResult,
        run_with_timeout,
    )
    from ops.scripts.core.output_runtime import display_path, sanitize_report_text
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_constants_runtime import (
        TEST_EXECUTION_SUMMARY_SCHEMA_PATH,
    )
    from ops.scripts.core.source_revision_runtime import resolve_source_revision
    from ops.scripts.core.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
    from ops.scripts.test.test_execution_command_runtime import (
        build_execution_environment,
        classify_interpreter_path,
        classify_status,
        display_command as _display_command,
        parse_pytest_counts,
        semantic_command,
        semantic_command_text as _semantic_command_text,
        tail_text as _tail_text,
        toolchain_fingerprint as _toolchain_fingerprint,
    )
    from ops.scripts.test.test_execution_derivation_runtime import (
        build_collection_manifest,
        derive_subset_summary,
        load_collection_manifest_digest,
        parse_junit_testcases,
        rebind_collection_manifest_reference,
        subset_summary_parity,
        validate_collection_manifest_payload,
        validate_collection_manifest_schema,
        write_collection_manifest,
    )
    from ops.scripts.test.test_execution_deselection_runtime import (
        deselection_lifecycle as _deselection_lifecycle,
        load_deselection_policy as _load_deselection_policy,
        load_deselection_policy_payload as _load_deselection_policy_payload,
        parse_utc_timestamp as _parse_utc_timestamp,
        pytest_stdout_deselected_count as _pytest_stdout_deselected_count,
        structured_deselected_tests,
    )
    from ops.scripts.test.test_execution_evidence_runtime import (
        evidence_artifact_consistency as _evidence_artifact_consistency,
        failed_nodeids as _failed_nodeids,
        junit_artifact_identity,
        nodeid_outcome_consistency as _nodeid_outcome_consistency,
        sha256_file as _sha256_file,
        sha256_text as _sha256_text,
        write_execution_log,
        write_failed_nodeids_artifact,
    )
    from ops.scripts.test.test_execution_reuse_runtime import (
        REUSE_MISMATCH_CODES,
        REUSE_MISMATCH_COMMAND_IDENTITY,
        REUSE_MISMATCH_INTERPRETER_TOOLCHAIN,
        REUSE_MISMATCH_MISSING_SUMMARY,
        REUSE_MISMATCH_SOURCE_REVISION,
        REUSE_MISMATCH_SOURCE_TREE,
        ReuseCurrentnessRequest,
        reuse_currentness_diagnostics_from_state,
    )
    from ops.scripts.test.test_execution_selection_runtime import (
        FULL_SUITE_COMMAND,
        FULL_SUITE_SCOPES,
        FULL_SUITE_SHARD_PREFIX,
        RELEASE_BUILDER_FULL_SCOPES,
        REPORT_CONTRACT_SUMMARY_SUITE,
        apply_toolchain_contract_to_coverage as _apply_toolchain_contract_to_coverage,
        pytest_args as _pytest_args,
        pytest_collect_modifiers as _pytest_collect_modifiers,
        pytest_collection_filter_args as _pytest_collection_filter_args,
        pytest_deselected_nodeids as _pytest_deselected_nodeids,
        pytest_selector_args as _pytest_selector_args,
        suite_coverage as _suite_coverage,
        suite_scope_for_key as _suite_scope_for_key,
    )
else:
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.core.command_runtime import (
        CommandHeartbeat,
        TimedProcessResult,
        run_with_timeout,
    )
    from ops.scripts.core.output_runtime import display_path, sanitize_report_text
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_constants_runtime import (
        TEST_EXECUTION_SUMMARY_SCHEMA_PATH,
    )
    from ops.scripts.core.source_revision_runtime import resolve_source_revision
    from ops.scripts.core.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
    from ops.scripts.test.test_execution_command_runtime import (
        build_execution_environment,
        classify_interpreter_path,
        classify_status,
        display_command as _display_command,
        parse_pytest_counts,
        semantic_command,
        semantic_command_text as _semantic_command_text,
        tail_text as _tail_text,
        toolchain_fingerprint as _toolchain_fingerprint,
    )
    from ops.scripts.test.test_execution_derivation_runtime import (
        build_collection_manifest,
        derive_subset_summary,
        load_collection_manifest_digest,
        parse_junit_testcases,
        rebind_collection_manifest_reference,
        subset_summary_parity,
        validate_collection_manifest_payload,
        validate_collection_manifest_schema,
        write_collection_manifest,
    )
    from ops.scripts.test.test_execution_deselection_runtime import (
        deselection_lifecycle as _deselection_lifecycle,
        load_deselection_policy as _load_deselection_policy,
        load_deselection_policy_payload as _load_deselection_policy_payload,
        parse_utc_timestamp as _parse_utc_timestamp,
        pytest_stdout_deselected_count as _pytest_stdout_deselected_count,
        structured_deselected_tests,
    )
    from ops.scripts.test.test_execution_evidence_runtime import (
        evidence_artifact_consistency as _evidence_artifact_consistency,
        failed_nodeids as _failed_nodeids,
        junit_artifact_identity,
        nodeid_outcome_consistency as _nodeid_outcome_consistency,
        sha256_file as _sha256_file,
        sha256_text as _sha256_text,
        write_execution_log,
        write_failed_nodeids_artifact,
    )
    from ops.scripts.test.test_execution_reuse_runtime import (
        REUSE_MISMATCH_CODES,
        REUSE_MISMATCH_COMMAND_IDENTITY,
        REUSE_MISMATCH_INTERPRETER_TOOLCHAIN,
        REUSE_MISMATCH_MISSING_SUMMARY,
        REUSE_MISMATCH_SOURCE_REVISION,
        REUSE_MISMATCH_SOURCE_TREE,
        ReuseCurrentnessRequest,
        reuse_currentness_diagnostics_from_state,
    )
    from ops.scripts.test.test_execution_selection_runtime import (
        FULL_SUITE_COMMAND,
        FULL_SUITE_SCOPES,
        FULL_SUITE_SHARD_PREFIX,
        RELEASE_BUILDER_FULL_SCOPES,
        REPORT_CONTRACT_SUMMARY_SUITE,
        apply_toolchain_contract_to_coverage as _apply_toolchain_contract_to_coverage,
        pytest_args as _pytest_args,
        pytest_collect_modifiers as _pytest_collect_modifiers,
        pytest_collection_filter_args as _pytest_collection_filter_args,
        pytest_deselected_nodeids as _pytest_deselected_nodeids,
        pytest_selector_args as _pytest_selector_args,
        suite_coverage as _suite_coverage,
        suite_scope_for_key as _suite_scope_for_key,
    )


_REUSE_COMPAT_EXPORTS = (
    REUSE_MISMATCH_CODES,
    REUSE_MISMATCH_COMMAND_IDENTITY,
    REUSE_MISMATCH_INTERPRETER_TOOLCHAIN,
    REUSE_MISMATCH_MISSING_SUMMARY,
    REUSE_MISMATCH_SOURCE_REVISION,
    REUSE_MISMATCH_SOURCE_TREE,
    reuse_currentness_diagnostics_from_state,
)
_COMMAND_COMPAT_EXPORTS = (
    classify_interpreter_path,
    classify_status,
    parse_pytest_counts,
    semantic_command,
)
_SELECTION_COMPAT_EXPORTS = (
    FULL_SUITE_COMMAND,
    FULL_SUITE_SCOPES,
    FULL_SUITE_SHARD_PREFIX,
    RELEASE_BUILDER_FULL_SCOPES,
    REPORT_CONTRACT_SUMMARY_SUITE,
    _apply_toolchain_contract_to_coverage,
    _pytest_args,
    _pytest_collection_filter_args,
    _pytest_collect_modifiers,
    _pytest_deselected_nodeids,
    _pytest_selector_args,
    _suite_coverage,
    _suite_scope_for_key,
)
_DESELECTION_COMPAT_EXPORTS = (
    _deselection_lifecycle,
    _load_deselection_policy,
    _load_deselection_policy_payload,
    _parse_utc_timestamp,
    _pytest_stdout_deselected_count,
    structured_deselected_tests,
)


DEFAULT_OUT = "ops/reports/test-execution-summary.json"
PRODUCER = "ops.scripts.test_execution_summary"
DEFAULT_TIMEOUT_SECONDS = 5400
DEFAULT_SHARD_DIR = "ops/reports/test-execution-summary-shards"
DEFAULT_FULL_SUITE_SHARD_DIR = "ops/reports/test-execution-summary-full-shards"


@dataclass(frozen=True)
class TestExecutionReportRequest:
    command: list[str]
    result: TimedProcessResult
    duration_ms: int
    suite: str
    policy_path: str | None = None
    context: RuntimeContext | None = None
    collect_nodeids: bool = False
    collect_nodeid_digest: dict[str, Any] | None = None
    evidence_artifacts: list[dict[str, Any]] | None = None
    deselection_policy_path: str | None = None


@dataclass(frozen=True)
class TestExecutionObservations:
    counts: dict[str, int]
    target_paths: list[str]
    test_target_fingerprints: list[dict[str, str]]
    deselected_tests: list[dict[str, Any]]
    deselection_lifecycle: dict[str, Any]
    pytest_marker_deselected_count: int
    policy_deselected_count: int
    collect_nodeid_digest: dict[str, Any]
    nodeid_outcome_consistency: dict[str, Any]
    evidence_artifacts: list[dict[str, Any]]
    evidence_artifact_consistency: dict[str, Any]
    execution_environment: dict[str, Any]
    coverage: dict[str, Any]
    status: str


@dataclass(frozen=True)
class TestExecutionRenderInputs:
    vault: Path
    request: TestExecutionReportRequest
    policy: dict[str, Any]
    resolved_policy_path: Path
    generated_at: str
    observations: TestExecutionObservations


def _pytest_file_candidates(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    candidates = [*path.rglob("test_*.py"), *path.rglob("*_test.py")]
    return sorted({candidate.resolve() for candidate in candidates if candidate.is_file()})


def resolve_pytest_target_paths(vault: Path, command: list[str]) -> list[str]:
    target_paths: list[str] = []
    seen: set[str] = set()
    for selector in _pytest_selector_args(command):
        path_selector = selector.split("::", 1)[0]
        if not path_selector:
            continue
        candidate = Path(path_selector)
        if not candidate.is_absolute():
            candidate = vault / candidate
        for path in _pytest_file_candidates(candidate.resolve()):
            rel_path = report_path(vault, path)
            if rel_path not in seen:
                seen.add(rel_path)
                target_paths.append(rel_path)
    return sorted(target_paths)


def build_test_target_fingerprints(vault: Path, target_paths: list[str]) -> list[dict[str, str]]:
    fingerprints: list[dict[str, str]] = []
    for rel_path in target_paths:
        path = (vault / rel_path).resolve()
        if path.is_file():
            fingerprints.append({"path": rel_path, "sha256": _sha256_file(path)})
    return fingerprints


def _collect_nodeids(stdout: str) -> list[str]:
    return sorted(
        line.strip()
        for line in stdout.splitlines()
        if line.strip() and ".py::" in line and not line.lstrip().startswith("=")
    )


def collect_pytest_nodeid_digest(
    vault: Path,
    command: list[str],
    *,
    timeout_seconds: int,
    collection_manifest_out: str | None = None,
    suite: str = "pytest",
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
    deselected_tests: list[dict[str, Any]] | None = None,
    deselection_lifecycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selectors = _pytest_selector_args(command)
    collect_command = [
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
        "--capture=no",
        *selectors,
        *_pytest_collect_modifiers(command),
    ]
    collect_env = dict(os.environ)
    collect_env["PYTHONDONTWRITEBYTECODE"] = "1"
    started_at = time.monotonic()
    result = run_with_timeout(
        collect_command,
        cwd=vault,
        timeout_seconds=timeout_seconds,
        env=collect_env,
    )
    elapsed_ms = max(0, round((time.monotonic() - started_at) * 1000))
    command_text = _display_command(vault, collect_command)
    if result.returncode != 0 or result.timed_out:
        return {
            "status": "failed",
            "command": command_text,
            "nodeid_count": 0,
            "sha256": "",
            "reason": result.termination_reason,
            "duration_ms": elapsed_ms,
        }
    nodeids = _collect_nodeids(result.stdout)
    digest_input = "\n".join(nodeids)
    if digest_input:
        digest_input = f"{digest_input}\n"
    digest = {
        "status": "collected",
        "command": command_text,
        "nodeid_count": len(nodeids),
        "sha256": _sha256_text(digest_input),
        "reason": "",
        "duration_ms": elapsed_ms,
    }
    if collection_manifest_out:
        manifest = build_collection_manifest(
            vault,
            suite=suite,
            semantic_command=_semantic_command_text(vault, command),
            nodeids=nodeids,
            selection_kind=(
                "selector_subset"
                if _pytest_selector_args(command) or _pytest_collect_modifiers(command)
                else "full_suite"
            ),
            policy_path=policy_path,
            context=context,
            deselected_tests=list(deselected_tests or []),
            deselection_lifecycle=dict(deselection_lifecycle or {}),
        )
        digest.update(write_collection_manifest(vault, manifest, collection_manifest_out))
    return digest


_BUILD_REPORT_KWARGS = {
    "command",
    "result",
    "duration_ms",
    "suite",
    "policy_path",
    "context",
    "collect_nodeids",
    "collect_nodeid_digest",
    "evidence_artifacts",
    "deselection_policy_path",
}


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _test_execution_report_request(
    request: TestExecutionReportRequest | None,
    legacy_kwargs: dict[str, Any],
) -> TestExecutionReportRequest:
    if request is not None:
        if legacy_kwargs:
            names = ", ".join(sorted(legacy_kwargs))
            raise TypeError(f"build_report request cannot be combined with legacy keyword arguments: {names}")
        if not isinstance(request, TestExecutionReportRequest):
            raise TypeError("build_report request must be a TestExecutionReportRequest")
        return request

    missing = {"command", "result", "duration_ms", "suite"} - set(legacy_kwargs)
    extra = set(legacy_kwargs) - _BUILD_REPORT_KWARGS
    if missing or extra:
        parts: list[str] = []
        if missing:
            parts.append(f"missing required keyword arguments: {', '.join(sorted(missing))}")
        if extra:
            parts.append(f"unexpected keyword arguments: {', '.join(sorted(extra))}")
        raise TypeError("; ".join(parts))

    result = legacy_kwargs["result"]
    context = legacy_kwargs.get("context")
    if not isinstance(result, TimedProcessResult):
        raise TypeError("build_report result must be a TimedProcessResult")
    if context is not None and not isinstance(context, RuntimeContext):
        raise TypeError("build_report context must be a RuntimeContext")

    return TestExecutionReportRequest(
        command=[str(item) for item in legacy_kwargs["command"]],
        result=result,
        duration_ms=int(legacy_kwargs["duration_ms"]),
        suite=str(legacy_kwargs["suite"]),
        policy_path=_optional_text(legacy_kwargs.get("policy_path")),
        context=context,
        collect_nodeids=bool(legacy_kwargs.get("collect_nodeids", False)),
        collect_nodeid_digest=legacy_kwargs.get("collect_nodeid_digest"),
        evidence_artifacts=legacy_kwargs.get("evidence_artifacts"),
        deselection_policy_path=_optional_text(legacy_kwargs.get("deselection_policy_path")),
    )


def _default_collect_nodeid_digest() -> dict[str, Any]:
    return {
        "status": "skipped",
        "command": "",
        "nodeid_count": 0,
        "sha256": "",
        "reason": "collect-nodeids was not requested",
    }


def _collect_only_duration_ms(collect_nodeid_digest: dict[str, Any]) -> int:
    try:
        return max(0, int(collect_nodeid_digest.get("duration_ms", 0) or 0))
    except (TypeError, ValueError):
        return 0


def _duration_telemetry(request: TestExecutionReportRequest, observations: TestExecutionObservations) -> dict[str, Any]:
    collect_only_duration_ms = _collect_only_duration_ms(observations.collect_nodeid_digest)
    command_duration_ms = max(0, int(request.duration_ms))
    return {
        "command_duration_ms": command_duration_ms,
        "collect_only_duration_ms": collect_only_duration_ms,
        "total_wall_time_ms": command_duration_ms + collect_only_duration_ms,
        "total_wall_time_source": "command_plus_collect_only",
    }


def _test_execution_observations(
    vault: Path,
    request: TestExecutionReportRequest,
    *,
    generated_at: str,
) -> TestExecutionObservations:
    counts = parse_pytest_counts(request.result.stdout, request.result.stderr)
    target_paths = resolve_pytest_target_paths(vault, request.command)
    test_target_fingerprints = build_test_target_fingerprints(vault, target_paths)
    deselected_tests = structured_deselected_tests(
        request.command,
        vault=vault,
        deselection_policy_path=request.deselection_policy_path,
    )
    deselection_lifecycle = _deselection_lifecycle(
        deselected_tests,
        generated_at=generated_at,
        policy_payload=_load_deselection_policy_payload(vault, request.deselection_policy_path),
    )
    policy_deselected_count = len(deselected_tests)
    pytest_marker_deselected_count = max(
        0,
        _pytest_stdout_deselected_count(request.result.stdout) - policy_deselected_count,
    )
    collect_nodeid_digest = request.collect_nodeid_digest
    if collect_nodeid_digest is None:
        collect_nodeid_digest = _default_collect_nodeid_digest()
    nodeid_outcome_consistency = _nodeid_outcome_consistency(counts, collect_nodeid_digest)
    evidence_artifacts = list(request.evidence_artifacts or [])
    evidence_artifact_consistency = _evidence_artifact_consistency(
        vault,
        counts=counts,
        evidence_artifacts=evidence_artifacts,
    )
    execution_environment = build_execution_environment(vault, request.command)
    coverage = _apply_toolchain_contract_to_coverage(
        _suite_coverage(suite=request.suite, command=request.command),
        execution_environment,
    )
    return TestExecutionObservations(
        counts=counts,
        target_paths=target_paths,
        test_target_fingerprints=test_target_fingerprints,
        deselected_tests=deselected_tests,
        deselection_lifecycle=deselection_lifecycle,
        pytest_marker_deselected_count=pytest_marker_deselected_count,
        policy_deselected_count=policy_deselected_count,
        collect_nodeid_digest=collect_nodeid_digest,
        nodeid_outcome_consistency=nodeid_outcome_consistency,
        evidence_artifacts=evidence_artifacts,
        evidence_artifact_consistency=evidence_artifact_consistency,
        execution_environment=execution_environment,
        coverage=coverage,
        status=classify_status(request.result, counts),
    )


def _test_execution_source_command(vault: Path, request: TestExecutionReportRequest) -> str:
    collect_option = " --collect-nodeids" if request.collect_nodeids else ""
    base = f"python -m ops.scripts.test_execution_summary --vault . --suite {request.suite}{collect_option}"
    if request.deselection_policy_path:
        return (
            f"{base} --deselection-policy {shlex.quote(request.deselection_policy_path)} -- "
            f"{_display_command(vault, request.command)}"
        )
    return f"{base} -- {_display_command(vault, request.command)}"


def _test_execution_file_inputs(request: TestExecutionReportRequest) -> dict[str, str] | None:
    if not request.deselection_policy_path:
        return None
    return {"deselection_policy": request.deselection_policy_path}


def _test_execution_text_inputs(
    vault: Path,
    request: TestExecutionReportRequest,
    observations: TestExecutionObservations,
) -> dict[str, str]:
    return {
        "wrapped_command": _display_command(vault, request.command),
        "suite": request.suite,
        "suite_coverage": json.dumps(observations.coverage, sort_keys=True, separators=(",", ":")),
        "deselected_tests": json.dumps(
            observations.deselected_tests,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "deselection_lifecycle": json.dumps(
            observations.deselection_lifecycle,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "nodeid_outcome_consistency": json.dumps(
            observations.nodeid_outcome_consistency,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "evidence_artifacts": json.dumps(
            observations.evidence_artifacts,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "evidence_artifact_consistency": json.dumps(
            observations.evidence_artifact_consistency,
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


def _render_test_execution_summary(inputs: TestExecutionRenderInputs) -> dict[str, Any]:
    vault = inputs.vault
    request = inputs.request
    observations = inputs.observations
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=inputs.generated_at,
            artifact_kind="test_execution_summary",
            producer=PRODUCER,
            source_command=_test_execution_source_command(vault, request),
            resolved_policy_path=inputs.resolved_policy_path,
            schema_path=TEST_EXECUTION_SUMMARY_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/test/test_execution_summary.py",
                "ops/scripts/core/command_runtime.py",
            ],
            text_inputs=_test_execution_text_inputs(vault, request, observations),
            file_inputs=_test_execution_file_inputs(request),
            path_group_inputs={"test_targets": observations.target_paths} if observations.target_paths else None,
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, inputs.resolved_policy_path),
            "version": inputs.policy.get("version"),
        },
        "suite": request.suite,
        **observations.coverage,
        "status": observations.status,
        "command": _display_command(vault, request.command),
        "semantic_command": _semantic_command_text(vault, request.command),
        "toolchain_fingerprint": _toolchain_fingerprint(observations.execution_environment),
        "returncode": request.result.returncode,
        "timed_out": request.result.timed_out,
        "timeout_seconds": request.result.timeout_seconds,
        "termination_reason": request.result.termination_reason,
        "duration_ms": request.duration_ms,
        "duration_telemetry": _duration_telemetry(request, observations),
        "counts": observations.counts,
        "execution_environment": observations.execution_environment,
        "test_target_fingerprints": observations.test_target_fingerprints,
        "deselected_tests": observations.deselected_tests,
        "deselection_lifecycle": observations.deselection_lifecycle,
        "pytest_marker_deselected_count": observations.pytest_marker_deselected_count,
        "policy_deselected_count": observations.policy_deselected_count,
        "pytest_collect_nodeid_digest": observations.collect_nodeid_digest,
        "nodeid_outcome_consistency": observations.nodeid_outcome_consistency,
        "evidence_artifacts": observations.evidence_artifacts,
        "evidence_artifact_consistency": observations.evidence_artifact_consistency,
        "stdout_tail": sanitize_report_text(vault, _tail_text(request.result.stdout)),
        "stderr_tail": sanitize_report_text(vault, _tail_text(request.result.stderr)),
        "release_contract_diagnosis": _build_release_contract_diagnosis(
            suite=request.suite,
            status=observations.status,
            command=_display_command(vault, request.command),
            duration_ms=request.duration_ms,
            generated_at=inputs.generated_at,
            deselection_lifecycle=observations.deselection_lifecycle,
        ),
    }


def build_report(
    vault: Path,
    request: TestExecutionReportRequest | None = None,
    **legacy_kwargs: Any,
) -> dict[str, Any]:
    request = _test_execution_report_request(request, legacy_kwargs)
    policy, resolved_policy_path = load_policy(vault, request.policy_path)
    runtime_context = request.context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    observations = _test_execution_observations(
        vault,
        request,
        generated_at=generated_at,
    )
    return _render_test_execution_summary(
        TestExecutionRenderInputs(
            vault=vault,
            request=request,
            policy=policy,
            resolved_policy_path=resolved_policy_path,
            generated_at=generated_at,
            observations=observations,
        )
    )


def _build_release_contract_diagnosis(
    *,
    suite: str,
    status: str,
    command: str,
    duration_ms: int,
    generated_at: str,
    deselection_lifecycle: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build release contract diagnosis entries for this test execution."""
    diagnosis: list[dict[str, Any]] = []

    # Pytest contract summary (the actual executed suite)
    lane = "clean" if status == "pass" else "blocked"
    blocker_conditions: list[str] = []
    if status == "fail":
        blocker_conditions.append("pytest_suite_failed")
    if deselection_lifecycle.get("status") != "pass":
        blocker_conditions.append("deselection_lifecycle_not_pass")

    diagnosis.append(
        {
            "name": "pytest_contract_summary",
            "status": "clean_pass" if status == "pass" else "blocked",
            "lane": lane,
            "command": command,
            "duration_seconds": round(duration_ms / 1000, 2),
            "checked_at": generated_at,
            "blocker_conditions": blocker_conditions,
            "accepted_risk_family": None,
            "risk_acceptance_ref": None,
            "reason": "",
        }
    )

    # Static checks (ruff, mypy) are executed via `make static` in the
    # release-evidence-closeout recipe. They do not run inside this pytest
    # wrapper, so they are recorded as externally executed.
    diagnosis.append(
        {
            "name": "static_checks",
            "status": "not_run",
            "lane": "blocked",
            "command": "make static",
            "duration_seconds": None,
            "checked_at": None,
            "blocker_conditions": ["external_static_evidence_not_captured_by_summary"],
            "accepted_risk_family": None,
            "risk_acceptance_ref": None,
            "reason": "not executed inside this pytest summary; use release-builder evidence before treating static checks as covered",
        }
    )

    return diagnosis


def reuse_currentness_diagnostics(
    existing: dict[str, Any],
    *,
    vault: Path,
    command: list[str],
    suite: str,
    collect_nodeids: bool,
    collect_nodeid_digest: dict[str, Any] | None,
    deselection_policy_path: str | None = None,
) -> dict[str, Any]:
    target_paths = resolve_pytest_target_paths(vault, command)
    current_target_fingerprints = build_test_target_fingerprints(vault, target_paths)
    current_deselected_tests = structured_deselected_tests(
        command,
        vault=vault,
        deselection_policy_path=deselection_policy_path,
    )
    policy, _ = load_policy(vault)
    generated_at = RuntimeContext.from_policy(policy).isoformat_z()
    current_lifecycle = _deselection_lifecycle(
        current_deselected_tests,
        generated_at=generated_at,
        policy_payload=_load_deselection_policy_payload(vault, deselection_policy_path),
    )
    current_execution_environment = build_execution_environment(vault, command)
    return reuse_currentness_diagnostics_from_state(
        ReuseCurrentnessRequest(
            existing=existing,
            suite=suite,
            current_source_revision=resolve_source_revision(vault).revision,
            current_source_tree_fingerprint=release_source_tree_fingerprint(vault),
            current_semantic_command=_semantic_command_text(vault, command),
            current_toolchain_fingerprint=_toolchain_fingerprint(current_execution_environment),
            current_display_command=_display_command(vault, command),
            current_target_fingerprints=current_target_fingerprints,
            current_deselected_tests=current_deselected_tests,
            current_deselection_lifecycle=current_lifecycle,
            collect_nodeids=collect_nodeids,
            collect_nodeid_digest=collect_nodeid_digest,
        )
    )


def reusable_summary_diagnostics_for_path(
    vault: Path,
    path_value: str | Path,
    *,
    command: list[str],
    suite: str,
    collect_nodeids: bool,
    collect_nodeid_digest: dict[str, Any] | None,
    deselection_policy_path: str | None = None,
) -> dict[str, Any]:
    path = Path(path_value)
    try:
        existing = _load_summary(vault, path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {
            "reusable": False,
            "path": report_path(vault, path if path.is_absolute() else vault / path),
            "reason": REUSE_MISMATCH_MISSING_SUMMARY,
            "load_error": type(exc).__name__,
            "current_source_revision": resolve_source_revision(vault).revision,
            "observed_source_revision": "",
            "current_source_tree_fingerprint": release_source_tree_fingerprint(vault),
            "observed_source_tree_fingerprint": "",
            "executable_path_differs_only": False,
            "checks": {"artifact_kind": False, "status": False},
        }
    diagnostics = reuse_currentness_diagnostics(
        existing,
        vault=vault,
        command=command,
        suite=suite,
        collect_nodeids=collect_nodeids,
        collect_nodeid_digest=collect_nodeid_digest,
        deselection_policy_path=deselection_policy_path,
    )
    diagnostics["path"] = report_path(vault, path if path.is_absolute() else vault / path)
    return diagnostics


def reusable_summary_is_current(
    existing: dict[str, Any],
    *,
    vault: Path,
    command: list[str],
    suite: str,
    collect_nodeids: bool,
    collect_nodeid_digest: dict[str, Any] | None,
    deselection_policy_path: str | None = None,
) -> bool:
    return bool(
        reuse_currentness_diagnostics(
            existing,
            vault=vault,
            command=command,
            suite=suite,
            collect_nodeids=collect_nodeids,
            collect_nodeid_digest=collect_nodeid_digest,
            deselection_policy_path=deselection_policy_path,
        )["reusable"]
    )


def build_reused_report(
    vault: Path,
    *,
    existing: dict[str, Any],
    command: list[str],
    suite: str,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
    collect_nodeids: bool = False,
    collect_nodeid_digest: dict[str, Any] | None = None,
    deselection_policy_path: str | None = None,
) -> dict[str, Any]:
    result = TimedProcessResult(
        args=[str(item) for item in command],
        returncode=0,
        stdout=str(existing.get("stdout_tail", "")),
        stderr=str(existing.get("stderr_tail", "")),
        timed_out=False,
        timeout_seconds=int(existing.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS) or DEFAULT_TIMEOUT_SECONDS),
        termination_reason="reused_current_summary",
    )
    report = build_report(
        vault,
        command=command,
        result=result,
        duration_ms=int(existing.get("duration_ms", 0) or 0),
        suite=suite,
        policy_path=policy_path,
        context=context,
        collect_nodeids=collect_nodeids,
        collect_nodeid_digest=collect_nodeid_digest,
        evidence_artifacts=[
            item for item in existing.get("evidence_artifacts", []) if isinstance(item, dict)
        ],
        deselection_policy_path=deselection_policy_path,
    )
    report["counts"] = dict(existing.get("counts", {}))
    report["nodeid_outcome_consistency"] = _nodeid_outcome_consistency(
        report["counts"],
        collect_nodeid_digest or dict(existing.get("pytest_collect_nodeid_digest", {})),
    )
    report["evidence_artifact_consistency"] = _evidence_artifact_consistency(
        vault,
        counts=report["counts"],
        evidence_artifacts=[
            item for item in existing.get("evidence_artifacts", []) if isinstance(item, dict)
        ],
    )
    report["termination_reason"] = "reused_current_summary"
    report["stdout_tail"] = str(existing.get("stdout_tail", ""))
    report["stderr_tail"] = str(existing.get("stderr_tail", ""))
    report["summary_mode"] = "reused"
    report["reused_from"] = str(existing.get("generated_at", ""))
    return report


def _load_summary(vault: Path, path_value: str | Path) -> dict[str, Any]:
    from ops.scripts.test.test_execution_aggregate_runtime import (
        load_test_execution_summary,
    )

    return load_test_execution_summary(vault, path_value)


def reusable_aggregate_summary_diagnostics(
    vault: Path,
    path_value: str | Path,
    *,
    suite: str,
) -> dict[str, Any]:
    from ops.scripts.test.test_execution_aggregate_runtime import (
        reusable_aggregate_summary_diagnostics as _diagnostics,
    )

    return _diagnostics(vault, path_value, suite=suite)


def _summary_shard_paths(vault: Path, aggregate_from: list[str], aggregate_dir: str) -> list[str]:
    from ops.scripts.test.test_execution_aggregate_runtime import summary_shard_paths

    return summary_shard_paths(vault, aggregate_from, aggregate_dir)


def build_aggregate_report(
    vault: Path,
    *,
    shard_paths: list[str],
    suite: str,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    from ops.scripts.test.test_execution_aggregate_runtime import (
        build_aggregate_report as _build_aggregate_report,
    )

    return _build_aggregate_report(
        vault,
        shard_paths=shard_paths,
        suite=suite,
        policy_path=policy_path,
        context=context,
    )


def write_report(vault: Path, report: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=TEST_EXECUTION_SUMMARY_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="test execution summary schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a test command and write a schema-backed execution summary")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--suite", default="pytest")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--heartbeat-interval-seconds",
        type=int,
        default=0,
        help="Emit stderr progress heartbeats while the wrapped test command is quiet; 0 disables.",
    )
    parser.add_argument(
        "--heartbeat-label",
        default="",
        help="Optional shard or lane label included in heartbeat lines.",
    )
    parser.add_argument("--collect-nodeids", action="store_true")
    parser.add_argument("--collect-timeout-seconds", type=int, default=300)
    parser.add_argument("--collection-manifest")
    parser.add_argument("--collection-only", action="store_true")
    parser.add_argument("--derive-subset-from-full", action="store_true")
    parser.add_argument("--full-summary")
    parser.add_argument("--full-collection-manifest")
    parser.add_argument("--selection-manifest")
    parser.add_argument("--parity-direct-summary")
    parser.add_argument("--junit-xml-path")
    parser.add_argument("--execution-log-out")
    parser.add_argument("--failed-nodeids-out")
    parser.add_argument("--deselection-policy")
    parser.add_argument("--aggregate", action="store_true")
    parser.add_argument("--aggregate-dir", default=DEFAULT_SHARD_DIR)
    parser.add_argument("--aggregate-from", action="append", default=[])
    parser.add_argument("--reuse-if-current", action="store_true")
    parser.add_argument("--reuse-from")
    parser.add_argument(
        "--refresh-revision-if-same-tree",
        action="store_true",
        help=(
            "Rewrite passing evidence from the same source tree, command, "
            "and toolchain with the current source_revision instead of rerunning pytest."
        ),
    )
    parser.add_argument(
        "--reuse-only",
        action="store_true",
        help=(
            "With --reuse-if-current, fail without executing the test command or "
            "collect-only when reusable evidence is stale."
        ),
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if args.heartbeat_interval_seconds < 0:
        parser.error("--heartbeat-interval-seconds must be >= 0")
    if not args.command and not args.aggregate and not args.aggregate_from and not args.derive_subset_from_full:
        parser.error("test command required for non-aggregate summaries; pass -- <command>")
    if args.derive_subset_from_full and not all(
        (args.full_summary, args.junit_xml_path, args.full_collection_manifest, args.selection_manifest)
    ):
        parser.error(
            "--derive-subset-from-full requires --full-summary, --junit-xml-path, "
            "--full-collection-manifest, and --selection-manifest"
        )
    return args


def _write_and_print_report(vault: Path, report: dict[str, Any], out_path: str | None) -> None:
    destination = write_report(vault, report, out_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nwritten_to={display_path(vault, destination)}")


def _run_aggregate_cli(vault: Path, args: argparse.Namespace) -> int:
    shard_paths = _summary_shard_paths(vault, list(args.aggregate_from), args.aggregate_dir)
    if not shard_paths:
        print(f"no test execution summary shards found under {args.aggregate_dir}", file=sys.stderr)
        return 1
    report = build_aggregate_report(
        vault,
        shard_paths=shard_paths,
        suite=args.suite,
        policy_path=args.policy,
    )
    digest = report.get("pytest_collect_nodeid_digest")
    if (
        args.refresh_revision_if_same_tree
        and isinstance(digest, dict)
        and digest.get("manifest_path")
    ):
        report["pytest_collect_nodeid_digest"] = (
            rebind_collection_manifest_reference(vault, digest)
        )
    _write_and_print_report(vault, report, args.out)
    return 0 if report["status"] == "pass" else 1


def _collect_nodeid_digest_for_args(vault: Path, args: argparse.Namespace) -> dict[str, Any] | None:
    if not args.collect_nodeids:
        return None
    if args.reuse_only:
        try:
            existing = _load_summary(vault, args.reuse_from or args.out)
        except (OSError, json.JSONDecodeError, ValueError):
            return None
        existing_digest = existing.get("pytest_collect_nodeid_digest")
        return dict(existing_digest) if isinstance(existing_digest, dict) else None
    if args.collection_manifest and not args.collection_only:
        return load_collection_manifest_digest(vault, args.collection_manifest)
    policy, _ = load_policy(vault, args.policy)
    runtime_context = RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    deselected_tests = structured_deselected_tests(
        args.command,
        vault=vault,
        deselection_policy_path=args.deselection_policy,
    )
    deselection_lifecycle = _deselection_lifecycle(
        deselected_tests,
        generated_at=generated_at,
        policy_payload=_load_deselection_policy_payload(vault, args.deselection_policy),
    )
    return collect_pytest_nodeid_digest(
        vault,
        args.command,
        timeout_seconds=args.collect_timeout_seconds,
        collection_manifest_out=args.out if args.collection_only else None,
        suite=args.suite,
        policy_path=args.policy,
        context=runtime_context,
        deselected_tests=deselected_tests,
        deselection_lifecycle=deselection_lifecycle,
    )


def _load_json_object(vault: Path, path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    if not path.is_absolute():
        path = vault / path
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {display_path(vault, path)}")
    return payload


def _run_collection_only_cli(vault: Path, args: argparse.Namespace) -> int:
    digest = _collect_nodeid_digest_for_args(vault, args)
    print(json.dumps(digest or {"status": "failed"}, ensure_ascii=False, indent=2))
    return 0 if isinstance(digest, dict) and digest.get("status") == "collected" else 1


def _run_derived_subset_cli(vault: Path, args: argparse.Namespace) -> int:
    try:
        full_summary = _load_summary(vault, args.full_summary)
        full_manifest = _load_json_object(vault, args.full_collection_manifest)
        selected_manifest = _load_json_object(vault, args.selection_manifest)
        blockers = [
            *validate_collection_manifest_payload(full_manifest),
            *validate_collection_manifest_payload(selected_manifest),
        ]
        if blockers:
            raise ValueError("; ".join(blockers))
        validate_collection_manifest_schema(vault, full_manifest)
        validate_collection_manifest_schema(vault, selected_manifest)
        junit_path = Path(args.junit_xml_path)
        if not junit_path.is_absolute():
            junit_path = vault / junit_path
        junit_evidence = parse_junit_testcases(
            junit_path.read_bytes(), expected_nodeids=full_manifest["nodeids"]
        )
        report = derive_subset_summary(
            full_summary, junit_evidence, full_manifest, selected_manifest
        )
        _write_and_print_report(vault, report, args.out)
        if args.parity_direct_summary:
            parity = subset_summary_parity(
                report, _load_summary(vault, args.parity_direct_summary)
            )
            print(json.dumps({"derived_direct_parity": parity}, ensure_ascii=False, indent=2))
            if parity["status"] != "pass":
                return 1
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"derived subset authority failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


def _reused_report_for_args(
    vault: Path,
    args: argparse.Namespace,
    *,
    collect_nodeid_digest: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if args.reuse_if_current:
        reuse_path = args.reuse_from or args.out
        try:
            existing = _load_summary(vault, reuse_path)
        except (OSError, json.JSONDecodeError, ValueError):
            existing = {}
        diagnostics = (
            reuse_currentness_diagnostics(
                existing,
                vault=vault,
                command=args.command,
                suite=args.suite,
                collect_nodeids=args.collect_nodeids,
                collect_nodeid_digest=collect_nodeid_digest,
                deselection_policy_path=args.deselection_policy,
            )
            if existing
            else {}
        )
        if existing and (
            diagnostics.get("reusable")
            or (
                args.refresh_revision_if_same_tree
                and diagnostics.get("reason") == REUSE_MISMATCH_SOURCE_REVISION
                and diagnostics.get("result_reusable")
            )
        ):
            return build_reused_report(
                vault,
                existing=existing,
                command=args.command,
                suite=args.suite,
                policy_path=args.policy,
                collect_nodeids=args.collect_nodeids,
                collect_nodeid_digest=collect_nodeid_digest,
                deselection_policy_path=args.deselection_policy,
            )
    return None


def _exact_reuse_only_diagnostics(
    vault: Path,
    args: argparse.Namespace,
    *,
    collect_nodeid_digest: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not args.reuse_only or args.refresh_revision_if_same_tree:
        return None
    try:
        existing = _load_summary(vault, args.reuse_from or args.out)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    diagnostics = reuse_currentness_diagnostics(
        existing,
        vault=vault,
        command=args.command,
        suite=args.suite,
        collect_nodeids=args.collect_nodeids,
        collect_nodeid_digest=collect_nodeid_digest,
        deselection_policy_path=args.deselection_policy,
    )
    if not diagnostics.get("reusable"):
        return None
    return {
        "summary_mode": "reused",
        "write_status": "not_written",
        "reused_from": str(existing.get("generated_at", "")),
        "reuse_diagnostics": diagnostics,
    }


def _interrupted_report(
    vault: Path,
    args: argparse.Namespace,
    *,
    started_at: float,
    collect_nodeid_digest: dict[str, Any] | None,
) -> dict[str, Any]:
    elapsed_ms = max(0, round((time.monotonic() - started_at) * 1000))
    result = TimedProcessResult(
        args=[str(item) for item in args.command],
        returncode=130,
        stdout="",
        stderr="KeyboardInterrupt",
        timed_out=False,
        timeout_seconds=args.timeout_seconds,
        termination_reason="interrupted",
    )
    return build_report(
        vault,
        command=args.command,
        result=result,
        duration_ms=elapsed_ms,
        suite=args.suite,
        policy_path=args.policy,
        collect_nodeids=args.collect_nodeids,
        collect_nodeid_digest=collect_nodeid_digest,
        evidence_artifacts=[],
        deselection_policy_path=args.deselection_policy,
    )


def _evidence_artifacts_for_args(
    vault: Path,
    args: argparse.Namespace,
    result: TimedProcessResult,
) -> list[dict[str, Any]]:
    evidence_artifacts: list[dict[str, Any]] = []
    counts = parse_pytest_counts(result.stdout, result.stderr)
    if args.execution_log_out:
        evidence_artifacts.append(write_execution_log(vault, args.execution_log_out, result))
    if args.junit_xml_path:
        evidence_artifacts.append(
            junit_artifact_identity(
                vault,
                args.junit_xml_path,
                counts=counts,
            )
        )
    if args.failed_nodeids_out:
        evidence_artifacts.append(
            write_failed_nodeids_artifact(
                vault,
                args.failed_nodeids_out,
                failed_nodeids=_failed_nodeids(result.stdout),
                expected_count=int(counts.get("failed", 0) or 0) + int(counts.get("errors", 0) or 0),
            )
        )
    return evidence_artifacts


def _execution_heartbeat_callback(
    vault: Path,
    args: argparse.Namespace,
) -> Callable[[CommandHeartbeat], None] | None:
    if int(args.heartbeat_interval_seconds or 0) <= 0:
        return None
    heartbeat_label = str(args.heartbeat_label or "").strip()
    execution_log_out = str(args.execution_log_out or "").strip()
    display_log_path = (
        display_path(vault, vault / execution_log_out)
        if execution_log_out
        else ""
    )

    def emit_heartbeat(heartbeat: CommandHeartbeat) -> None:
        fields = [
            "test-execution-summary-heartbeat",
            f"suite={args.suite}",
            f"heartbeat={heartbeat.heartbeat_index}",
            f"elapsed_seconds={heartbeat.elapsed_seconds:.1f}",
            f"quiet_seconds={heartbeat.quiet_seconds}",
            f"timeout_seconds={heartbeat.timeout_seconds}",
        ]
        if heartbeat_label:
            fields.insert(2, f"shard={heartbeat_label}")
        if display_log_path:
            fields.append(f"log={display_log_path}")
        print(" ".join(fields), file=sys.stderr, flush=True)

    return emit_heartbeat


def _executed_report_for_args(
    vault: Path,
    args: argparse.Namespace,
    *,
    collect_nodeid_digest: dict[str, Any] | None,
) -> tuple[dict[str, Any], int]:
    started_at = time.monotonic()
    try:
        heartbeat_callback = _execution_heartbeat_callback(vault, args)
        if heartbeat_callback is None:
            result = run_with_timeout(
                args.command,
                cwd=vault,
                timeout_seconds=args.timeout_seconds,
            )
        else:
            result = run_with_timeout(
                args.command,
                cwd=vault,
                timeout_seconds=args.timeout_seconds,
                heartbeat_interval_seconds=args.heartbeat_interval_seconds,
                heartbeat_callback=heartbeat_callback,
            )
    except KeyboardInterrupt:
        return (
            _interrupted_report(
                vault,
                args,
                started_at=started_at,
                collect_nodeid_digest=collect_nodeid_digest,
            ),
            130,
        )

    elapsed_ms = max(0, round((time.monotonic() - started_at) * 1000))
    report = build_report(
        vault,
        command=args.command,
        result=result,
        duration_ms=elapsed_ms,
        suite=args.suite,
        policy_path=args.policy,
        collect_nodeids=args.collect_nodeids,
        collect_nodeid_digest=collect_nodeid_digest,
        evidence_artifacts=_evidence_artifacts_for_args(vault, args, result),
        deselection_policy_path=args.deselection_policy,
    )
    return report, 0 if report["status"] == "pass" else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.reuse_only:
        args.reuse_if_current = True
    vault = Path(args.vault).resolve()
    if args.derive_subset_from_full:
        return _run_derived_subset_cli(vault, args)
    if args.collection_only:
        return _run_collection_only_cli(vault, args)
    if args.aggregate or args.aggregate_from:
        if args.reuse_if_current:
            diagnostics = reusable_aggregate_summary_diagnostics(
                vault,
                args.reuse_from or args.out,
                suite=args.suite,
            )
            if (
                args.refresh_revision_if_same_tree
                and not diagnostics.get("reusable")
                and diagnostics.get("result_reusable")
            ):
                return _run_aggregate_cli(vault, args)
            if diagnostics["reusable"]:
                print(json.dumps({"summary_mode": "reused", **diagnostics}, ensure_ascii=False, indent=2))
                return 0
            print(
                json.dumps(
                    {"summary_mode": "aggregate", "reuse_diagnostics": diagnostics},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            if args.reuse_only:
                return 1
        return _run_aggregate_cli(vault, args)

    collect_nodeid_digest = _collect_nodeid_digest_for_args(vault, args)
    exact_reuse = _exact_reuse_only_diagnostics(
        vault,
        args,
        collect_nodeid_digest=collect_nodeid_digest,
    )
    if exact_reuse is not None:
        print(json.dumps(exact_reuse, ensure_ascii=False, indent=2))
        return 0
    report = _reused_report_for_args(
        vault,
        args,
        collect_nodeid_digest=collect_nodeid_digest,
    )
    if report is not None:
        _write_and_print_report(vault, report, args.out)
        return 0
    if args.reuse_only:
        diagnostics = reusable_summary_diagnostics_for_path(
            vault,
            args.reuse_from or args.out,
            command=args.command,
            suite=args.suite,
            collect_nodeids=args.collect_nodeids,
            collect_nodeid_digest=collect_nodeid_digest,
            deselection_policy_path=args.deselection_policy,
        )
        print(
            json.dumps(
                {
                    "summary_mode": "single",
                    "reuse_diagnostics": diagnostics,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    report, returncode = _executed_report_for_args(
        vault,
        args,
        collect_nodeid_digest=collect_nodeid_digest,
    )
    _write_and_print_report(vault, report, args.out)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
