#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_binding_runtime import (
    BINDING_MODES,
    binding_file_digest,
)
from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    resolve_repo_artifact_path,
    write_schema_backed_report,
)
from ops.scripts.core.command_runtime import TimedProcessResult, run_with_timeout
from ops.scripts.core.output_runtime import display_path, sanitize_report_text
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.source_tree_fingerprint_runtime import (
    release_source_tree_fingerprint,
)

DEFAULT_OUT = "ops/reports/release-closeout-fixed-point.json"
DEFAULT_DRY_RUN_OUT = "tmp/release-closeout-post-check-finalizer.json"
DEFAULT_DRY_RUN_RECOMMENDED_TARGETS_OUT = (
    "tmp/release-closeout-post-check-finalizer-recommended-targets.txt"
)
DEFAULT_DRY_RUN_PLAN_OUT = "tmp/release-closeout-post-check-finalizer-plan.json"
PRODUCER = "ops.scripts.release_closeout_fixed_point"
SCHEMA_PATH = "ops/schemas/release-closeout-fixed-point.schema.json"
DRY_RUN_SCHEMA_PATH = "ops/schemas/release-closeout-post-check-finalizer.schema.json"
POLICY_PATH = "ops/policies/release-closeout-fixed-point.json"
SOURCE_COMMAND = "make release-closeout-fixed-point"
DRY_RUN_SOURCE_COMMAND = "make release-closeout-post-check-finalizer-dry-run"
DEFAULT_TIMEOUT_SECONDS = 600
ARTIFACT_FRESHNESS_REPORT_PATH = "ops/reports/artifact-freshness-report.json"

CommandRunner = Callable[[Sequence[str], Path, int, Mapping[str, str]], dict[str, Any]]
ProgressSink = Callable[[str], None]


@dataclass(frozen=True)
class _FixedPointPolicyRuntime:
    policy: dict[str, Any]
    writers: list[dict[str, Any]]
    tracked_artifacts: list[dict[str, str]]
    tracked_paths: list[str]
    writer_targets: list[str]
    producer_by_path: dict[str, str]
    downstream_by_target: dict[str, set[str]]


@dataclass(frozen=True)
class _FixedPointExecutionState:
    execution: dict[str, Any]
    raw_digest_map: dict[str, str]
    binding_digest_map: dict[str, str]
    binding_mode_map: dict[str, str]
    status: str


@dataclass(frozen=True)
class _FixedPointExecutionConfig:
    selected_targets: Sequence[str]
    timeout_seconds: int
    python_executable: str
    make_variables: Sequence[str]
    runtime_env: Mapping[str, str]
    command_runner: CommandRunner
    progress_sink: ProgressSink | None = None


@dataclass
class _ExecutionContext:
    vault: Path
    python_executable: str
    make_variables: Sequence[str]
    timeout_seconds: int
    command_runner: CommandRunner
    runtime_env: Mapping[str, str]
    progress_sink: ProgressSink | None = None
    progress_prefix: str = "release-closeout-fixed-point"
    writer_by_target: Mapping[str, dict[str, Any]] | None = None
    tracked_artifacts: Sequence[dict[str, str]] = ()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tail(text: str, *, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _emit_progress(progress_sink: ProgressSink | None, message: str) -> None:
    if progress_sink is not None:
        progress_sink(message)


def _stderr_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _load_finalizer_policy(vault: Path) -> dict[str, Any]:
    path = vault / POLICY_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{POLICY_PATH} must contain a JSON object")
    return payload


def _policy_runtime(vault: Path) -> _FixedPointPolicyRuntime:
    policy = _load_finalizer_policy(vault)
    writers = _writer_specs(policy)
    tracked_artifacts = _tracked_artifacts(writers)
    tracked_paths = [item["path"] for item in tracked_artifacts]
    writer_targets = [str(writer["target"]) for writer in writers]
    return _FixedPointPolicyRuntime(
        policy=policy,
        writers=writers,
        tracked_artifacts=tracked_artifacts,
        tracked_paths=tracked_paths,
        writer_targets=writer_targets,
        producer_by_path=_producer_by_path(writers),
        downstream_by_target=_downstream_by_target(writers),
    )


def _writer_specs(policy: dict[str, Any]) -> list[dict[str, Any]]:
    writers = policy.get("writers")
    if not isinstance(writers, list) or not writers:
        raise ValueError(f"{POLICY_PATH} must define non-empty writers")
    normalized: list[dict[str, Any]] = []
    seen_targets: set[str] = set()
    producer_by_path: dict[str, str] = {}
    for item in writers:
        if not isinstance(item, dict):
            raise ValueError("writer specs must be objects")
        target = str(item.get("target", "")).strip()
        if not target:
            raise ValueError("writer target is required")
        if target in seen_targets:
            raise ValueError(f"duplicate writer target: {target}")
        seen_targets.add(target)
        binding_mode = str(item.get("binding_mode", "")).strip()
        if binding_mode not in BINDING_MODES:
            raise ValueError(
                f"writer {target} has missing or invalid binding_mode: "
                f"{binding_mode or '<missing>'}"
            )
        produces = [
            str(path).strip() for path in item.get("produces", []) if str(path).strip()
        ]
        if not produces:
            raise ValueError(f"writer {target} must produce at least one path")
        for path in produces:
            previous_producer = producer_by_path.get(path)
            if previous_producer is not None:
                raise ValueError(
                    f"duplicate produced path {path}: "
                    f"{previous_producer} and {target}"
                )
            producer_by_path[path] = target
        normalized.append(
            {
                "name": str(item.get("name", target)).strip() or target,
                "target": target,
                "binding_mode": binding_mode,
                "produces": produces,
                "depends_on": [
                    str(dep).strip()
                    for dep in item.get("depends_on", [])
                    if str(dep).strip()
                ],
                "expensive_prerequisites": [
                    str(dep).strip()
                    for dep in item.get("expensive_prerequisites", [])
                    if str(dep).strip()
                ],
            }
        )
    known = {str(item["target"]) for item in normalized}
    for item in normalized:
        unknown_deps = sorted(set(item["depends_on"]) - known)
        if unknown_deps:
            raise ValueError(
                f"writer {item['target']} has unknown depends_on targets: {unknown_deps}"
            )
    _validate_acyclic_writer_graph(normalized)
    positions = {
        str(writer["target"]): index for index, writer in enumerate(normalized)
    }
    for writer in normalized:
        target = str(writer["target"])
        late_dependencies = [
            dependency
            for dependency in writer["depends_on"]
            if positions[str(dependency)] >= positions[target]
        ]
        if late_dependencies:
            raise ValueError(
                f"writer policy order is not topological: {target} appears before "
                f"dependencies {late_dependencies}"
            )
    return normalized


def _validate_acyclic_writer_graph(writers: Sequence[dict[str, Any]]) -> None:
    dependencies = {
        str(writer["target"]): [str(item) for item in writer["depends_on"]]
        for writer in writers
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(target: str, trail: list[str]) -> None:
        if target in visiting:
            cycle_start = trail.index(target)
            cycle = [*trail[cycle_start:], target]
            raise ValueError(f"writer dependency cycle: {' -> '.join(cycle)}")
        if target in visited:
            return
        visiting.add(target)
        trail.append(target)
        for dependency in dependencies[target]:
            visit(dependency, trail)
        trail.pop()
        visiting.remove(target)
        visited.add(target)

    for target in dependencies:
        visit(target, [])


def _tracked_artifacts(writers: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "name": str(writer["name"]),
            "path": str(path),
            "binding_mode": str(writer["binding_mode"]),
        }
        for writer in writers
        for path in writer["produces"]
    ]


def _producer_by_path(writers: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(path): str(writer["target"])
        for writer in writers
        for path in writer["produces"]
    }


def _downstream_by_target(writers: list[dict[str, Any]]) -> dict[str, set[str]]:
    direct: dict[str, set[str]] = {str(writer["target"]): set() for writer in writers}
    for writer in writers:
        target = str(writer["target"])
        for dependency in writer["depends_on"]:
            direct.setdefault(str(dependency), set()).add(target)
    downstream: dict[str, set[str]] = {}
    for target in direct:
        seen: set[str] = set()
        stack = list(direct[target])
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(direct.get(current, set()))
        downstream[target] = seen
    return downstream


def _dedupe_preserve_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _all_writer_targets(writers: list[dict[str, Any]]) -> list[str]:
    return [str(writer["target"]) for writer in writers]


def _validated_initial_targets(
    targets: Sequence[str] | None,
    *,
    runtime: _FixedPointPolicyRuntime,
) -> list[str]:
    if targets is None:
        return _all_writer_targets(runtime.writers)
    return _downstream_closed_writer_targets(
        targets,
        writer_targets=runtime.writer_targets,
        downstream_by_target=runtime.downstream_by_target,
    )


def _downstream_closed_writer_targets(
    targets: Sequence[str],
    *,
    writer_targets: Sequence[str],
    downstream_by_target: Mapping[str, set[str]],
) -> list[str]:
    requested = _dedupe_preserve_order(
        [str(target).strip() for target in targets if str(target).strip()]
    )
    if not requested:
        raise ValueError("initial_targets must include at least one target")
    known = set(writer_targets)
    unknown = sorted(set(requested) - known)
    if unknown:
        raise ValueError(f"unknown initial target(s): {unknown}")
    selected = {
        target
        for initial_target in requested
        for target in {
            initial_target,
            *downstream_by_target.get(initial_target, set()),
        }
    }
    return [target for target in writer_targets if target in selected]


def fixed_point_execution_targets_from_policy(vault: Path) -> list[str]:
    runtime = _policy_runtime(vault)
    return _execution_targets(runtime.writer_targets, runtime=runtime)


def fixed_point_writer_specs_from_policy(vault: Path) -> list[dict[str, Any]]:
    policy = _load_finalizer_policy(vault)
    return _writer_specs(policy)


def fixed_point_downstream_closed_writer_targets(
    writers: Sequence[dict[str, Any]],
    targets: Sequence[str],
) -> list[str]:
    normalized_writers = list(writers)
    return _downstream_closed_writer_targets(
        targets,
        writer_targets=_all_writer_targets(normalized_writers),
        downstream_by_target=_downstream_by_target(normalized_writers),
    )


def fixed_point_output_paths_at_or_downstream(
    vault: Path,
    target: str,
) -> set[str]:
    runtime = _policy_runtime(vault)
    if target not in runtime.writer_targets:
        raise ValueError(f"unknown fixed-point writer target: {target}")
    selected_targets = {target, *runtime.downstream_by_target[target]}
    return {
        str(path)
        for writer in runtime.writers
        if str(writer["target"]) in selected_targets
        for path in writer["produces"]
    }


def _execution_targets(
    selected_targets: Sequence[str], *, runtime: _FixedPointPolicyRuntime
) -> list[str]:
    selected = set(selected_targets)
    execution_targets: list[str] = []
    for writer in runtime.writers:
        target = str(writer["target"])
        if target not in selected:
            continue
        execution_targets.extend(
            str(item) for item in writer["expensive_prerequisites"]
        )
        execution_targets.append(target)
    return _dedupe_preserve_order(execution_targets)


def _targets_for_affected_paths(
    affected_paths: Sequence[str],
    *,
    writers: list[dict[str, Any]],
    producer_by_path: dict[str, str],
    downstream_by_target: dict[str, set[str]],
) -> list[str]:
    affected_producers = {
        producer_by_path[path] for path in affected_paths if path in producer_by_path
    }
    selected = {
        target
        for producer in affected_producers
        for target in {producer, *downstream_by_target.get(producer, set())}
    }
    return [
        str(writer["target"]) for writer in writers if str(writer["target"]) in selected
    ]


def _raw_digest_map(
    vault: Path, tracked_artifacts: Sequence[dict[str, str]]
) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in tracked_artifacts:
        rel_path = item["path"]
        path = vault / rel_path
        result[rel_path] = _sha256_file(path) if path.is_file() else "missing"
    return result


def _binding_maps(
    vault: Path, tracked_artifacts: Sequence[dict[str, str]]
) -> tuple[dict[str, str], dict[str, str]]:
    digest_map: dict[str, str] = {}
    mode_map: dict[str, str] = {}
    for item in tracked_artifacts:
        rel_path = item["path"]
        binding_mode = item["binding_mode"]
        _projection_mode, digest = binding_file_digest(
            vault / rel_path,
            binding_mode=binding_mode,
        )
        digest_map[rel_path] = digest
        mode_map[rel_path] = binding_mode
    return digest_map, mode_map


def _writer_by_target(writers: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(writer["target"]): dict(writer) for writer in writers}


def _changed_paths(
    previous: dict[str, str] | None, current: dict[str, str]
) -> list[str]:
    if previous is None:
        return sorted(current)
    return sorted(
        path for path, digest in current.items() if previous.get(path) != digest
    )


def _default_runner(
    argv: Sequence[str],
    cwd: Path,
    timeout_seconds: int,
    env: Mapping[str, str],
) -> dict[str, Any]:
    started_at = time.monotonic()
    result = run_with_timeout(
        list(argv),
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        env=env,
    )
    payload = _command_result_payload(result, vault=cwd)
    payload["duration_ms"] = round((time.monotonic() - started_at) * 1000)
    return payload


def _command_result_payload(
    result: TimedProcessResult, *, vault: Path
) -> dict[str, Any]:
    return {
        "command": [sanitize_report_text(vault, str(item)) for item in result.args],
        "returncode": result.returncode,
        "timed_out": result.timed_out,
        "timeout_seconds": result.timeout_seconds,
        "termination_reason": result.termination_reason,
        "stdout_tail": sanitize_report_text(vault, _tail(result.stdout)),
        "stderr_tail": sanitize_report_text(vault, _tail(result.stderr)),
        "status": "pass" if result.returncode == 0 and not result.timed_out else "fail",
    }


def _make_command(
    target: str,
    *,
    vault: Path,
    python_executable: str,
    make_variables: Sequence[str],
) -> list[str]:
    return [
        "make",
        target,
        f"PYTHON={python_executable}",
        f"VAULT={vault.as_posix()}",
        *make_variables,
    ]


def _run_execution(
    *,
    targets: Sequence[str],
    context: _ExecutionContext,
) -> tuple[list[dict[str, Any]], bool]:
    command_results: list[dict[str, Any]] = []
    failed = False
    for target in targets:
        command = _make_command(
            target,
            vault=context.vault,
            python_executable=context.python_executable,
            make_variables=context.make_variables,
        )
        writer = (context.writer_by_target or {}).get(target)
        before_digest_map = _raw_digest_map(
            context.vault, context.tracked_artifacts
        )
        _emit_progress(
            context.progress_sink,
            (
                f"{context.progress_prefix}: start target={target} "
                f"timeout_seconds={context.timeout_seconds}"
            ),
        )
        result = context.command_runner(
            command,
            context.vault,
            context.timeout_seconds,
            context.runtime_env,
        )
        after_digest_map = _raw_digest_map(context.vault, context.tracked_artifacts)
        tracked_paths_changed = _changed_paths(before_digest_map, after_digest_map)
        declared_produces = (
            {str(path) for path in writer["produces"]} if writer is not None else set()
        )
        undeclared_tracked_writes = sorted(
            set(tracked_paths_changed) - declared_produces
        )
        command_status = str(result.get("status", "fail"))
        termination_reason = str(result.get("termination_reason", ""))
        issues: list[str] = []
        if undeclared_tracked_writes:
            command_status = "fail"
            termination_reason = "undeclared_tracked_write"
            issues.append("undeclared_tracked_write")
        payload = {
            "target": target,
            "command": [
                sanitize_report_text(context.vault, str(item))
                for item in result.get("command", command)
            ],
            "returncode": int(result.get("returncode", 1)),
            "timed_out": bool(result.get("timed_out", False)),
            "timeout_seconds": int(
                result.get("timeout_seconds", context.timeout_seconds)
            ),
            "termination_reason": termination_reason,
            "duration_ms": int(result.get("duration_ms", 0) or 0),
            "stdout_tail": sanitize_report_text(
                context.vault, str(result.get("stdout_tail", ""))
            ),
            "stderr_tail": sanitize_report_text(
                context.vault, str(result.get("stderr_tail", ""))
            ),
            "status": command_status,
            "tracked_paths_changed": tracked_paths_changed,
            "undeclared_tracked_writes": undeclared_tracked_writes,
            "issues": issues,
        }
        command_results.append(payload)
        _emit_progress(
            context.progress_sink,
            (
                f"{context.progress_prefix}: done target={target} "
                f"status={payload['status']} duration_ms={payload['duration_ms']}"
            ),
        )
        if payload["status"] != "pass":
            failed = True
            break
    return command_results, failed


def _duration_summary(
    execution: Mapping[str, Any],
    *,
    writers: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    command_results = [
        item
        for item in execution.get("command_results", [])
        if isinstance(item, dict)
    ]
    selected_targets = {
        str(target)
        for target in execution.get("selected_targets", [])
        if str(target).strip()
    }
    writer_costs: list[dict[str, Any]] = []
    for writer in writers:
        target = str(writer["target"])
        runs = [item for item in command_results if item.get("target") == target]
        durations = [int(item.get("duration_ms", 0) or 0) for item in runs]
        total_duration_ms = sum(durations)
        writer_costs.append(
            {
                "name": str(writer["name"]),
                "target": target,
                "produces": [str(path) for path in writer["produces"]],
                "run_count": len(runs),
                "selected": target in selected_targets,
                "total_duration_ms": total_duration_ms,
                "average_duration_ms": (
                    round(total_duration_ms / len(runs)) if runs else 0
                ),
                "max_duration_ms": max(durations) if durations else 0,
            }
        )
    expensive_targets = _dedupe_preserve_order(
        [
            str(target)
            for writer in writers
            for target in writer["expensive_prerequisites"]
        ]
    )
    expensive_runs = [
        item for item in command_results if item.get("target") in expensive_targets
    ]
    expensive_duration_ms = sum(
        int(item.get("duration_ms", 0) or 0) for item in expensive_runs
    )
    total_duration_ms = sum(
        int(item.get("duration_ms", 0) or 0) for item in command_results
    )
    return {
        "execution_pass_count": 1,
        "command_run_count": len(command_results),
        "total_duration_ms": total_duration_ms,
        "writer_costs": writer_costs,
        "expensive_prerequisites": {
            "targets": expensive_targets,
            "configured_target_count": len(expensive_targets),
            "observed_target_count": len(
                {str(item.get("target", "")) for item in expensive_runs}
            ),
            "run_count": len(expensive_runs),
            "total_duration_ms": expensive_duration_ms,
            "summary": (
                f"{len(expensive_runs)} prerequisite commands ran once in the "
                "single execution pass"
            ),
        },
        "summary": (
            f"{len(writer_costs)} writers ran {len(command_results)} commands in "
            f"one execution pass; total_duration_ms={total_duration_ms}"
        ),
    }


def _normalized_string_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(path): str(item)
        for path, item in value.items()
        if isinstance(path, str) and isinstance(item, str)
    }


def _valid_digest_map(value: Mapping[str, str]) -> bool:
    return all(
        digest == "missing"
        or (
            len(digest) == 64
            and all(character in "0123456789abcdef" for character in digest)
        )
        for digest in value.values()
    )


def _fixed_point_authority_unavailable(
    *,
    load_status: str,
    status: str,
    summary: str,
) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, Any]]:
    return {}, {}, {}, {
        "path": DEFAULT_OUT,
        "load_status": load_status,
        "status": status,
        "digest_count": 0,
        "summary": summary,
    }


def _load_fixed_point_authority(
    vault: Path,
    *,
    runtime: _FixedPointPolicyRuntime,
) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, Any]]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(
        vault / DEFAULT_OUT
    )
    load_status = str(diagnostics.get("status", "unknown"))
    if load_status != "ok":
        return _fixed_point_authority_unavailable(
            load_status=load_status,
            status="missing",
            summary=(
                "fixed-point report is unavailable; run "
                "release-closeout-fixed-point"
            ),
        )
    if payload.get("schema_version") != 2:
        return _fixed_point_authority_unavailable(
            load_status="unsupported_schema_version",
            status="not_authoritative",
            summary="only schema_version=2 fixed-point reports are current authority",
        )
    report_status = str(payload.get("status", "unknown")).strip() or "unknown"
    currentness = payload.get("currentness")
    currentness_status = (
        str(currentness.get("status", "")).strip()
        if isinstance(currentness, dict)
        else ""
    )
    if (
        payload.get("artifact_kind") != "release_closeout_fixed_point_report"
        or payload.get("producer") != PRODUCER
        or report_status != "pass"
        or payload.get("artifact_status") != "current"
        or currentness_status != "current"
        or payload.get("execution_pass_count") != 1
    ):
        return _fixed_point_authority_unavailable(
            load_status="not_current_authority",
            status=report_status,
            summary="schema_version=2 fixed-point report is not current pass authority",
        )
    raw_digest_map = _normalized_string_map(payload.get("raw_digest_map"))
    binding_digest_map = _normalized_string_map(payload.get("binding_digest_map"))
    binding_mode_map = _normalized_string_map(payload.get("binding_mode_map"))
    expected_paths = set(runtime.tracked_paths)
    expected_mode_map = {
        item["path"]: item["binding_mode"] for item in runtime.tracked_artifacts
    }
    execution = payload.get("execution")
    execution_is_consistent = (
        isinstance(execution, dict)
        and execution.get("status") == "pass"
        and _normalized_string_map(execution.get("raw_digest_map"))
        == raw_digest_map
        and _normalized_string_map(execution.get("binding_digest_map"))
        == binding_digest_map
        and _normalized_string_map(execution.get("binding_mode_map"))
        == binding_mode_map
    )
    if (
        set(raw_digest_map) != expected_paths
        or set(binding_digest_map) != expected_paths
        or binding_mode_map != expected_mode_map
        or not _valid_digest_map(raw_digest_map)
        or not _valid_digest_map(binding_digest_map)
        or not execution_is_consistent
    ):
        return _fixed_point_authority_unavailable(
            load_status="invalid_v2_authority",
            status=report_status,
            summary=(
                "schema_version=2 fixed-point digest or binding-mode maps are invalid"
            ),
        )
    return raw_digest_map, binding_digest_map, binding_mode_map, {
        "path": DEFAULT_OUT,
        "load_status": "ok",
        "status": report_status,
        "digest_count": len(raw_digest_map),
        "summary": (
            f"fixed-point v2 status={report_status}; "
            f"digest_count={len(raw_digest_map)}"
        ),
    }


def _artifact_freshness_records(
    vault: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(
        vault / ARTIFACT_FRESHNESS_REPORT_PATH
    )
    status = str(diagnostics.get("status", "unknown"))
    if status != "ok":
        return {}, {
            "path": ARTIFACT_FRESHNESS_REPORT_PATH,
            "load_status": status,
            "status": "missing",
            "summary": "artifact freshness report is unavailable",
        }
    records: dict[str, dict[str, Any]] = {}
    raw_records = payload.get("artifact_records")
    if isinstance(raw_records, list):
        for item in raw_records:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "")).strip()
            if path:
                records[path] = item
    report_status = str(payload.get("status", "unknown")).strip() or "unknown"
    return records, {
        "path": ARTIFACT_FRESHNESS_REPORT_PATH,
        "load_status": "ok",
        "status": report_status,
        "summary": f"artifact_freshness status={report_status}; record_count={len(records)}",
    }


def _json_payload(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, "unreadable"
    return payload if isinstance(payload, dict) else {}, "ok"


def _source_tree_status(
    *,
    load_status: str,
    source_tree_fingerprint: str,
    current_source_tree_fingerprint: str,
) -> str:
    if load_status != "ok":
        return load_status
    if not source_tree_fingerprint:
        return "missing"
    if source_tree_fingerprint == current_source_tree_fingerprint:
        return "current"
    return "stale"


def _freshness_signal(freshness_record: dict[str, Any]) -> tuple[str, list[str]]:
    raw_issues = freshness_record.get("issues")
    issues = (
        [str(issue) for issue in raw_issues] if isinstance(raw_issues, list) else []
    )
    schema_validation_status = str(
        freshness_record.get("schema_validation_status", "")
    ).strip()
    return schema_validation_status, issues


def _dry_run_tracked_artifact_record(
    vault: Path,
    item: dict[str, str],
    *,
    baseline_raw_digest_map: dict[str, str],
    baseline_binding_digest_map: dict[str, str],
    baseline_binding_mode_map: dict[str, str],
    current_raw_digest_map: dict[str, str],
    current_binding_digest_map: dict[str, str],
    freshness_records: dict[str, dict[str, Any]],
    current_source_tree_fingerprint: str,
    producer_by_path: dict[str, str],
) -> dict[str, Any]:
    rel_path = str(item["path"])
    payload, load_status = _json_payload(vault / rel_path)
    source_tree_fingerprint = str(payload.get("source_tree_fingerprint", "")).strip()
    source_tree_status = _source_tree_status(
        load_status=load_status,
        source_tree_fingerprint=source_tree_fingerprint,
        current_source_tree_fingerprint=current_source_tree_fingerprint,
    )
    baseline_raw_digest = baseline_raw_digest_map.get(rel_path, "missing")
    current_raw_digest = current_raw_digest_map.get(rel_path, "missing")
    raw_digest_status = (
        "current" if baseline_raw_digest == current_raw_digest else "changed"
    )
    declared_binding_mode = str(item["binding_mode"])
    baseline_binding_digest = baseline_binding_digest_map.get(rel_path, "unknown")
    current_binding_digest = current_binding_digest_map.get(rel_path, "unknown")
    binding_digest_status = (
        "unknown"
        if baseline_binding_mode_map.get(rel_path) != declared_binding_mode
        or "unknown" in {baseline_binding_digest, current_binding_digest}
        else "current"
        if baseline_binding_digest == current_binding_digest
        else "changed"
    )
    freshness_record = freshness_records.get(rel_path, {})
    schema_validation_status, issues = _freshness_signal(freshness_record)
    freshness_status = (
        "attention" if issues or schema_validation_status == "fail" else "pass"
    )
    digest_refresh_required = (
        binding_digest_status == "changed"
        or (binding_digest_status == "unknown" and raw_digest_status != "current")
    )
    refresh_needed = (
        load_status != "ok"
        or digest_refresh_required
        or source_tree_status != "current"
        or freshness_status != "pass"
    )
    return {
        "name": str(item["name"]),
        "path": rel_path,
        "producer_target": producer_by_path.get(rel_path, ""),
        "load_status": load_status,
        "binding_mode": declared_binding_mode,
        "baseline_raw_digest": baseline_raw_digest,
        "current_raw_digest": current_raw_digest,
        "raw_digest_status": raw_digest_status,
        "baseline_binding_digest": baseline_binding_digest,
        "current_binding_digest": current_binding_digest,
        "binding_digest_status": binding_digest_status,
        "source_tree_fingerprint": source_tree_fingerprint,
        "source_tree_status": source_tree_status,
        "schema_validation_status": schema_validation_status or "unknown",
        "freshness_status": freshness_status,
        "issues": issues,
        "refresh_needed": refresh_needed,
    }


def _dry_run_tracked_records(
    vault: Path,
    runtime: _FixedPointPolicyRuntime,
    *,
    baseline_raw_digest_map: dict[str, str],
    baseline_binding_digest_map: dict[str, str],
    baseline_binding_mode_map: dict[str, str],
    current_raw_digest_map: dict[str, str],
    current_binding_digest_map: dict[str, str],
    freshness_records: dict[str, dict[str, Any]],
    current_source_tree_fingerprint: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    tracked_records = [
        _dry_run_tracked_artifact_record(
            vault,
            item,
            baseline_raw_digest_map=baseline_raw_digest_map,
            baseline_binding_digest_map=baseline_binding_digest_map,
            baseline_binding_mode_map=baseline_binding_mode_map,
            current_raw_digest_map=current_raw_digest_map,
            current_binding_digest_map=current_binding_digest_map,
            freshness_records=freshness_records,
            current_source_tree_fingerprint=current_source_tree_fingerprint,
            producer_by_path=runtime.producer_by_path,
        )
        for item in runtime.tracked_artifacts
    ]
    affected_paths = _dedupe_preserve_order(
        [record["path"] for record in tracked_records if record["refresh_needed"]]
    )
    return tracked_records, affected_paths


def _dry_run_recommended_targets(
    affected_paths: Sequence[str],
    *,
    fixed_point_summary: dict[str, Any],
    runtime: _FixedPointPolicyRuntime,
) -> list[str]:
    if fixed_point_summary["load_status"] != "ok":
        return _all_writer_targets(runtime.writers)
    return _targets_for_affected_paths(
        affected_paths,
        writers=runtime.writers,
        producer_by_path=runtime.producer_by_path,
        downstream_by_target=runtime.downstream_by_target,
    )


def _dry_run_evidence_gap_reasons(
    *,
    fixed_point_summary: dict[str, Any],
    freshness_summary: dict[str, Any],
    tracked_records: Sequence[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if fixed_point_summary["load_status"] != "ok":
        reasons.append("fixed_point_report_unavailable")
    if int(fixed_point_summary.get("digest_count", 0) or 0) == 0:
        reasons.append("fixed_point_digest_map_empty")
    if freshness_summary["load_status"] != "ok":
        reasons.append("artifact_freshness_report_unavailable")
    for record in tracked_records:
        path = str(record["path"])
        if record["load_status"] != "ok":
            reasons.append(f"{path}:artifact_unavailable")
        if record["baseline_raw_digest"] == "missing":
            reasons.append(f"{path}:baseline_raw_digest_missing")
        if record["current_raw_digest"] == "missing":
            reasons.append(f"{path}:current_raw_digest_missing")
        if record["source_tree_status"] in {"missing", "unreadable"}:
            reasons.append(
                f"{path}:source_tree_fingerprint_{record['source_tree_status']}"
            )
    return _dedupe_preserve_order(reasons)


def _dry_run_drift_reasons(tracked_records: Sequence[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    for record in tracked_records:
        path = str(record["path"])
        if (
            record["raw_digest_status"] == "changed"
            and record["baseline_raw_digest"] != "missing"
            and record["current_raw_digest"] != "missing"
        ):
            reasons.append(f"{path}:raw_digest_changed")
        if record["binding_digest_status"] == "changed":
            reasons.append(f"{path}:binding_digest_changed")
        if record["source_tree_status"] == "stale":
            reasons.append(f"{path}:source_tree_stale")
        if record["freshness_status"] == "attention":
            reasons.append(f"{path}:artifact_freshness_attention")
    return _dedupe_preserve_order(reasons)


def _dry_run_diagnostic_status(
    *,
    evidence_gap_reasons: Sequence[str],
    drift_reasons: Sequence[str],
    refresh_required: bool,
) -> str:
    has_evidence_gap = bool(evidence_gap_reasons)
    has_drift = bool(drift_reasons)
    if has_evidence_gap and has_drift:
        return "mixed_attention"
    if has_evidence_gap:
        return "evidence_insufficient"
    if has_drift or refresh_required:
        return "drift_detected"
    return "settled"


def _target_writes(
    target: str,
    *,
    writers_by_target: Mapping[str, dict[str, Any]],
) -> list[str]:
    writer = writers_by_target.get(target)
    if not writer:
        return []
    return [str(path) for path in writer["produces"]]


def _expected_raw_digest_to_settle(
    writes: Sequence[str],
    *,
    tracked_by_path: Mapping[str, dict[str, Any]],
) -> dict[str, str]:
    expected: dict[str, str] = {}
    for path in writes:
        record = tracked_by_path.get(path)
        digest = (
            str(record.get("current_raw_digest", "unknown"))
            if record
            else "unknown"
        )
        expected[path] = digest if digest and digest != "missing" else "unknown"
    return expected


def _target_why(
    target: str,
    *,
    writes: Sequence[str],
    affected_paths: Sequence[str],
    fixed_point_summary: dict[str, Any],
    runtime: _FixedPointPolicyRuntime,
    tracked_by_path: Mapping[str, dict[str, Any]],
) -> str:
    if fixed_point_summary["load_status"] != "ok":
        return "single-pass baseline evidence is unavailable; run the writer graph"
    affected = set(affected_paths)
    direct_paths = [path for path in writes if path in affected]
    if direct_paths:
        reason_parts: list[str] = []
        for path in direct_paths:
            record = tracked_by_path.get(path, {})
            path_reasons = []
            if record.get("binding_digest_status") == "changed":
                path_reasons.append("binding digest drift")
            elif record.get("raw_digest_status") != "current":
                path_reasons.append("raw digest drift")
            if record.get("source_tree_status") != "current":
                path_reasons.append(f"source tree {record.get('source_tree_status')}")
            if record.get("freshness_status") != "pass":
                path_reasons.append("freshness attention")
            if record.get("load_status") != "ok":
                path_reasons.append(f"load {record.get('load_status')}")
            reason_parts.append(
                f"{path} ({', '.join(path_reasons) or 'refresh needed'})"
            )
        return "refreshes affected artifact(s): " + "; ".join(reason_parts)
    upstream_paths: list[str] = []
    for path in affected_paths:
        producer = runtime.producer_by_path.get(path, "")
        if target in runtime.downstream_by_target.get(producer, set()):
            upstream_paths.append(path)
    if upstream_paths:
        return "downstream of affected artifact(s): " + ", ".join(upstream_paths)
    return "included in the single-pass prerequisite writer set"


def _dry_run_closeout_plan(
    *,
    generated_at: str,
    diagnostic_status: str,
    refresh_required: bool,
    recommended_targets: Sequence[str],
    affected_paths: Sequence[str],
    fixed_point_summary: dict[str, Any],
    runtime: _FixedPointPolicyRuntime,
    tracked_records: Sequence[dict[str, Any]],
    evidence_gap_reasons: Sequence[str],
    drift_reasons: Sequence[str],
) -> dict[str, Any]:
    writers_by_target = {str(writer["target"]): writer for writer in runtime.writers}
    tracked_by_path = {str(record["path"]): record for record in tracked_records}
    target_plans = []
    for target in recommended_targets:
        writes = _target_writes(target, writers_by_target=writers_by_target)
        target_plans.append(
            {
                "target": target,
                "why": _target_why(
                    target,
                    writes=writes,
                    affected_paths=affected_paths,
                    fixed_point_summary=fixed_point_summary,
                    runtime=runtime,
                    tracked_by_path=tracked_by_path,
                ),
                "writes": writes,
                "expected_raw_digest_to_settle": _expected_raw_digest_to_settle(
                    writes,
                    tracked_by_path=tracked_by_path,
                ),
                "safe_to_run_in_dry_run": False,
            }
        )
    return {
        "artifact_kind": "release_closeout_post_check_finalizer_plan",
        "generated_at": generated_at,
        "status": diagnostic_status,
        "refresh_required": refresh_required,
        "safe_to_run_in_dry_run": True,
        "mutating_finalizer_target": "release-closeout-fixed-point",
        "affected_paths": list(affected_paths),
        "evidence_gap_reasons": list(evidence_gap_reasons),
        "drift_reasons": list(drift_reasons),
        "recommended_target_count": len(target_plans),
        "recommended_targets": target_plans,
        "summary": (
            f"diagnostic_status={diagnostic_status}; "
            f"recommended_target_count={len(target_plans)}"
        ),
    }


def build_dry_run_report(
    vault: Path,
    *,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    runtime = _policy_runtime(vault)
    (
        baseline_raw_digest_map,
        baseline_binding_digest_map,
        baseline_binding_mode_map,
        fixed_point_summary,
    ) = _load_fixed_point_authority(vault, runtime=runtime)
    current_raw_digest_map = _raw_digest_map(vault, runtime.tracked_artifacts)
    current_binding_digest_map, _current_binding_mode_map = _binding_maps(
        vault, runtime.tracked_artifacts
    )
    freshness_records, freshness_summary = _artifact_freshness_records(vault)
    current_source_tree_fingerprint = release_source_tree_fingerprint(vault)
    tracked_records, affected_paths = _dry_run_tracked_records(
        vault,
        runtime,
        baseline_raw_digest_map=baseline_raw_digest_map,
        baseline_binding_digest_map=baseline_binding_digest_map,
        baseline_binding_mode_map=baseline_binding_mode_map,
        current_raw_digest_map=current_raw_digest_map,
        current_binding_digest_map=current_binding_digest_map,
        freshness_records=freshness_records,
        current_source_tree_fingerprint=current_source_tree_fingerprint,
    )
    recommended_targets = _dry_run_recommended_targets(
        affected_paths,
        fixed_point_summary=fixed_point_summary,
        runtime=runtime,
    )
    refresh_required = bool(recommended_targets)
    evidence_gap_reasons = _dry_run_evidence_gap_reasons(
        fixed_point_summary=fixed_point_summary,
        freshness_summary=freshness_summary,
        tracked_records=tracked_records,
    )
    drift_reasons = _dry_run_drift_reasons(tracked_records)
    diagnostic_status = _dry_run_diagnostic_status(
        evidence_gap_reasons=evidence_gap_reasons,
        drift_reasons=drift_reasons,
        refresh_required=refresh_required,
    )
    closeout_plan = _dry_run_closeout_plan(
        generated_at=generated_at,
        diagnostic_status=diagnostic_status,
        refresh_required=refresh_required,
        recommended_targets=recommended_targets,
        affected_paths=affected_paths,
        fixed_point_summary=fixed_point_summary,
        runtime=runtime,
        tracked_records=tracked_records,
        evidence_gap_reasons=evidence_gap_reasons,
        drift_reasons=drift_reasons,
    )
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind="release_closeout_post_check_finalizer",
        producer=PRODUCER,
        source_command=DRY_RUN_SOURCE_COMMAND,
        resolved_policy_path=vault / POLICY_PATH,
        schema_path=DRY_RUN_SCHEMA_PATH,
        source_paths=["ops/scripts/release/release_closeout_fixed_point.py"],
        path_group_inputs={
            "tracked_artifacts": runtime.tracked_paths,
        },
        text_inputs={
            "policy_version": str(runtime.policy.get("version", "")),
            "writer_targets": "\n".join(runtime.writer_targets),
            "current_source_tree_fingerprint": current_source_tree_fingerprint,
        },
        source_tree_excluded_files=(DEFAULT_OUT,),
    )
    return {
        **envelope,
        "vault": display_path(vault, vault),
        "policy": {
            "path": POLICY_PATH,
            "version": int(runtime.policy.get("version", 1) or 1),
        },
        "mode": "dry_run",
        "status": "attention" if refresh_required else "pass",
        "diagnostic_status": diagnostic_status,
        "refresh_required": refresh_required,
        "current_source_tree_fingerprint": current_source_tree_fingerprint,
        "fixed_point_report": fixed_point_summary,
        "artifact_freshness_report": freshness_summary,
        "tracked_artifacts": tracked_records,
        "affected_path_count": len(affected_paths),
        "affected_paths": affected_paths,
        "recommended_targets": recommended_targets,
        "closeout_plan": closeout_plan,
        "mutating_finalizer_target": "release-closeout-fixed-point",
        "summary": (
            f"refresh_required={str(refresh_required).lower()}; "
            f"diagnostic_status={diagnostic_status}; "
            f"affected_path_count={len(affected_paths)}; "
            f"recommended_target_count={len(recommended_targets)}"
        ),
    }


def _fixed_point_execution_state(
    vault: Path,
    *,
    runtime: _FixedPointPolicyRuntime,
    config: _FixedPointExecutionConfig,
) -> _FixedPointExecutionState:
    previous_raw_digest_map = _raw_digest_map(vault, runtime.tracked_artifacts)
    previous_binding_digest_map, _ = _binding_maps(
        vault, runtime.tracked_artifacts
    )
    execution_targets = _execution_targets(config.selected_targets, runtime=runtime)
    _emit_progress(
        config.progress_sink,
        (
            "release-closeout-fixed-point: pass=1/1 "
            f"targets={','.join(config.selected_targets)}"
        ),
    )
    command_results, command_failed = _run_execution(
        targets=execution_targets,
        context=_ExecutionContext(
            vault=vault,
            python_executable=config.python_executable,
            make_variables=config.make_variables,
            timeout_seconds=config.timeout_seconds,
            command_runner=config.command_runner,
            runtime_env=config.runtime_env,
            progress_sink=config.progress_sink,
            writer_by_target=_writer_by_target(runtime.writers),
            tracked_artifacts=runtime.tracked_artifacts,
        ),
    )
    raw_digest_map = _raw_digest_map(vault, runtime.tracked_artifacts)
    binding_digest_map, binding_mode_map = _binding_maps(
        vault, runtime.tracked_artifacts
    )
    raw_changed_paths = _changed_paths(previous_raw_digest_map, raw_digest_map)
    binding_changed_paths = _changed_paths(
        previous_binding_digest_map, binding_digest_map
    )
    undeclared_write = any(
        "undeclared_tracked_write" in result.get("issues", [])
        for result in command_results
    )
    status = "fail" if command_failed else "pass"
    reason = (
        "undeclared_tracked_write"
        if undeclared_write
        else "command_failed"
        if command_failed
        else "single_topological_pass_completed"
    )
    execution = {
        "status": status,
        "reason": reason,
        "selected_targets": list(config.selected_targets),
        "command_results": command_results,
        "raw_digest_map": raw_digest_map,
        "raw_digest_changed": bool(raw_changed_paths),
        "raw_changed_paths": raw_changed_paths,
        "binding_digest_map": binding_digest_map,
        "binding_mode_map": binding_mode_map,
        "binding_changed_paths": binding_changed_paths,
    }
    _emit_progress(
        config.progress_sink,
        (
            "release-closeout-fixed-point: "
            f"pass=1/1 status={status} "
            f"changed_path_count={len(raw_changed_paths)}"
        ),
    )
    return _FixedPointExecutionState(
        execution=execution,
        raw_digest_map=raw_digest_map,
        binding_digest_map=binding_digest_map,
        binding_mode_map=binding_mode_map,
        status=status,
    )


def _fixed_point_envelope(
    vault: Path,
    *,
    runtime: _FixedPointPolicyRuntime,
    generated_at: str,
    selected_targets: Sequence[str],
    timeout_seconds: int,
    make_variables: Sequence[str],
) -> dict[str, Any]:
    return build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind="release_closeout_fixed_point_report",
        producer=PRODUCER,
        source_command=SOURCE_COMMAND,
        resolved_policy_path=vault / POLICY_PATH,
        schema_path=SCHEMA_PATH,
        source_paths=[
            "ops/scripts/release/release_closeout_fixed_point.py",
            "ops/scripts/core/artifact_binding_runtime.py",
        ],
        path_group_inputs={"tracked_artifacts": runtime.tracked_paths},
        text_inputs={
            "policy_version": str(runtime.policy.get("version", "")),
            "execution_pass_count": "1",
            "timeout_seconds": str(timeout_seconds),
            "writer_targets": "\n".join(runtime.writer_targets),
            "selected_targets": "\n".join(selected_targets),
            "make_variables": "\n".join(
                sanitize_report_text(vault, item) for item in make_variables
            ),
        },
        source_tree_excluded_files=(DEFAULT_OUT,),
    )


def build_report(
    vault: Path,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    python_executable: str | None = None,
    make_variables: Sequence[str] = (),
    initial_targets: Sequence[str] | None = None,
    context: RuntimeContext | None = None,
    command_runner: CommandRunner = _default_runner,
    progress_sink: ProgressSink | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    active_python = python_executable or sys.executable
    runtime = _policy_runtime(vault)
    selected_targets = _validated_initial_targets(
        initial_targets,
        runtime=runtime,
    )
    runtime_env = {**os.environ, "LLMWIKI_RUNTIME_UTC_NOW": generated_at}
    execution_state = _fixed_point_execution_state(
        vault,
        runtime=runtime,
        config=_FixedPointExecutionConfig(
            selected_targets=selected_targets,
            timeout_seconds=timeout_seconds,
            python_executable=active_python,
            make_variables=make_variables,
            runtime_env=runtime_env,
            command_runner=command_runner,
            progress_sink=progress_sink,
        ),
    )
    duration_summary = _duration_summary(
        execution_state.execution,
        writers=runtime.writers,
    )
    envelope = _fixed_point_envelope(
        vault,
        runtime=runtime,
        generated_at=generated_at,
        selected_targets=selected_targets,
        timeout_seconds=timeout_seconds,
        make_variables=make_variables,
    )
    return {
        **envelope,
        "schema_version": 2,
        "vault": display_path(vault, vault),
        "policy": {
            "path": POLICY_PATH,
            "version": int(runtime.policy.get("version", 1) or 1),
        },
        "status": execution_state.status,
        "execution_pass_count": 1,
        "tracked_artifacts": runtime.tracked_artifacts,
        "command_sequence": runtime.writer_targets,
        "execution": execution_state.execution,
        "raw_digest_map": execution_state.raw_digest_map,
        "binding_digest_map": execution_state.binding_digest_map,
        "binding_mode_map": execution_state.binding_mode_map,
        "duration_summary": duration_summary,
    }


def write_report(
    vault: Path,
    report: dict[str, Any],
    out_path: str | None = None,
) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release closeout fixed-point schema validation failed",
            trailing_newline=True,
        )
    )


def write_dry_run_report(
    vault: Path,
    report: dict[str, Any],
    out_path: str | None = None,
) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=DRY_RUN_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_DRY_RUN_OUT,
            context="release closeout post-check finalizer dry-run schema validation failed",
            trailing_newline=True,
        )
    )


def write_dry_run_recommended_targets(
    vault: Path,
    report: dict[str, Any],
    out_path: str | None = None,
) -> Path:
    destination = resolve_repo_artifact_path(
        vault,
        out_path,
        default_relative_path=DEFAULT_DRY_RUN_RECOMMENDED_TARGETS_OUT,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw_targets = report.get("recommended_targets")
    targets = (
        [str(target) for target in raw_targets] if isinstance(raw_targets, list) else []
    )
    contents = "\n".join(targets) if targets else "no recommended targets"
    destination.write_text(f"{contents}\n", encoding="utf-8")
    return destination


def write_dry_run_plan(
    vault: Path,
    report: dict[str, Any],
    out_path: str | None = None,
) -> Path:
    destination = resolve_repo_artifact_path(
        vault,
        out_path,
        default_relative_path=DEFAULT_DRY_RUN_PLAN_OUT,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw_plan = report.get("closeout_plan")
    plan = raw_plan if isinstance(raw_plan, dict) else {}
    destination.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run release closeout report writers once in policy topological order.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report which fixed-point artifacts need a post-check refresh; do not run writer targets.",
    )
    parser.add_argument(
        "--fail-on-refresh-required",
        action="store_true",
        help="With --dry-run, return non-zero when canonical artifacts still need refresh.",
    )
    parser.add_argument(
        "--recommended-targets-out",
        help=(
            "With --dry-run, write recommended_targets as newline-delimited text for "
            "CI artifact upload."
        ),
    )
    parser.add_argument(
        "--plan-out",
        help="With --dry-run, write the bounded closeout handoff plan as JSON.",
    )
    parser.add_argument(
        "--make-variable",
        action="append",
        default=[],
        help="Additional KEY=VALUE assignment forwarded to every nested make invocation.",
    )
    parser.add_argument(
        "--initial-target",
        action="append",
        default=[],
        help=(
            "Select this writer target and its downstream dependency closure for "
            "the single execution pass. May be repeated."
        ),
    )
    parser.add_argument("--no-fail", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    if args.dry_run:
        report = build_dry_run_report(vault)
        path = write_dry_run_report(vault, report, args.out)
        print(display_path(vault, path))
        if args.recommended_targets_out:
            targets_path = write_dry_run_recommended_targets(
                vault,
                report,
                args.recommended_targets_out,
            )
            print(display_path(vault, targets_path))
        if args.plan_out:
            plan_path = write_dry_run_plan(vault, report, args.plan_out)
            print(display_path(vault, plan_path))
        if (
            args.fail_on_refresh_required
            and report["refresh_required"]
            and not args.no_fail
        ):
            return 1
        return 0
    report = build_report(
        vault,
        timeout_seconds=args.timeout_seconds,
        python_executable=args.python,
        make_variables=tuple(args.make_variable),
        initial_targets=tuple(args.initial_target) or None,
        progress_sink=_stderr_progress,
    )
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    if args.no_fail:
        return 0
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
