#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    promote_schema_validated_json,
    resolve_repo_artifact_path,
    write_schema_backed_report,
)
from ops.scripts.command_runtime import TimedProcessResult, run_with_timeout
from ops.scripts.output_runtime import display_path, sanitize_report_text
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint


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
DEFAULT_MAX_ITERATIONS = 5
DEFAULT_TIMEOUT_SECONDS = 600
ARTIFACT_FRESHNESS_REPORT_PATH = "ops/reports/artifact-freshness-report.json"
DEFAULT_BOOTSTRAP_CANDIDATE_PREFIX = "tmp/release-closeout-fixed-point.bootstrap"
FIXED_POINT_SCHEMA_DEBT_ISSUE = "schema_validation_failed"

CommandRunner = Callable[[Sequence[str], Path, int, Mapping[str, str]], dict[str, Any]]


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
class _FixedPointIterationState:
    iterations: list[dict[str, Any]]
    final_digest_map: dict[str, str]
    final_changed_paths: list[str]
    status: str
    reason: str
    converged: bool
    converged_iteration: int


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


def _load_finalizer_policy(vault: Path) -> dict[str, Any]:
    path = vault / POLICY_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def _policy_runtime(vault: Path) -> _FixedPointPolicyRuntime:
    policy = _load_finalizer_policy(vault)
    writers = _writer_specs(policy)
    tracked_artifacts = _tracked_artifacts(policy, writers)
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
    for item in writers:
        if not isinstance(item, dict):
            raise ValueError("writer specs must be objects")
        target = str(item.get("target", "")).strip()
        if not target:
            raise ValueError("writer target is required")
        if target in seen_targets:
            raise ValueError(f"duplicate writer target: {target}")
        seen_targets.add(target)
        produces = [
            str(path).strip() for path in item.get("produces", []) if str(path).strip()
        ]
        if not produces:
            raise ValueError(f"writer {target} must produce at least one path")
        normalized.append(
            {
                "name": str(item.get("name", target)).strip() or target,
                "target": target,
                "produces": produces,
                "depends_on": [
                    str(dep).strip()
                    for dep in item.get("depends_on", [])
                    if str(dep).strip()
                ],
                "expensive_prerequisites_once": [
                    str(dep).strip()
                    for dep in item.get("expensive_prerequisites_once", [])
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
    return normalized


def _tracked_artifacts(
    policy: dict[str, Any], writers: list[dict[str, Any]]
) -> list[dict[str, str]]:
    producer_by_path = {
        str(path): str(writer["name"])
        for writer in writers
        for path in writer["produces"]
    }
    raw_paths = policy.get("tracked_artifacts")
    paths = (
        [str(path).strip() for path in raw_paths if str(path).strip()]
        if isinstance(raw_paths, list)
        else sorted(producer_by_path)
    )
    return [
        {
            "name": producer_by_path.get(path, Path(path).stem),
            "path": path,
        }
        for path in paths
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


def _initial_iteration_targets(writers: list[dict[str, Any]]) -> list[str]:
    prerequisites = _dedupe_preserve_order(
        [
            str(target)
            for writer in writers
            for target in writer["expensive_prerequisites_once"]
        ]
    )
    return [*prerequisites, *[str(writer["target"]) for writer in writers]]


def fixed_point_initial_targets_from_policy(vault: Path) -> list[str]:
    policy = _load_finalizer_policy(vault)
    return _initial_iteration_targets(_writer_specs(policy))


def fixed_point_writer_specs_from_policy(vault: Path) -> list[dict[str, Any]]:
    policy = _load_finalizer_policy(vault)
    return _writer_specs(policy)


def _downstream_targets_for_changed_paths(
    changed_paths: Sequence[str],
    *,
    writers: list[dict[str, Any]],
    producer_by_path: dict[str, str],
    downstream_by_target: dict[str, set[str]],
) -> list[str]:
    changed_producers = {
        producer_by_path[path] for path in changed_paths if path in producer_by_path
    }
    selected = {
        downstream
        for producer in changed_producers
        for downstream in downstream_by_target.get(producer, set())
    }
    return [
        str(writer["target"]) for writer in writers if str(writer["target"]) in selected
    ]


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


def _digest_map(
    vault: Path, tracked_artifacts: Sequence[dict[str, str]]
) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in tracked_artifacts:
        rel_path = item["path"]
        path = vault / rel_path
        result[rel_path] = _sha256_file(path) if path.is_file() else "missing"
    return result


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
    payload["duration_ms"] = int(round((time.monotonic() - started_at) * 1000))
    return payload


def _command_result_payload(result: TimedProcessResult, *, vault: Path) -> dict[str, Any]:
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


def _run_iteration(
    vault: Path,
    *,
    targets: Sequence[str],
    python_executable: str,
    make_variables: Sequence[str],
    timeout_seconds: int,
    command_runner: CommandRunner,
    runtime_env: Mapping[str, str],
) -> tuple[list[dict[str, Any]], bool]:
    command_results: list[dict[str, Any]] = []
    failed = False
    for target in targets:
        command = _make_command(
            target,
            vault=vault,
            python_executable=python_executable,
            make_variables=make_variables,
        )
        result = command_runner(command, vault, timeout_seconds, runtime_env)
        payload = {
            "target": target,
            "command": [
                sanitize_report_text(vault, str(item))
                for item in result.get("command", command)
            ],
            "returncode": int(result.get("returncode", 1)),
            "timed_out": bool(result.get("timed_out", False)),
            "timeout_seconds": int(result.get("timeout_seconds", timeout_seconds)),
            "termination_reason": str(result.get("termination_reason", "")),
            "duration_ms": int(result.get("duration_ms", 0) or 0),
            "stdout_tail": sanitize_report_text(vault, str(result.get("stdout_tail", ""))),
            "stderr_tail": sanitize_report_text(vault, str(result.get("stderr_tail", ""))),
            "status": str(result.get("status", "fail")),
        }
        command_results.append(payload)
        if payload["status"] != "pass":
            failed = True
            break
    return command_results, failed


def _selected_targets_by_iteration(
    iterations: Sequence[dict[str, Any]],
) -> dict[int, set[str]]:
    return {
        int(iteration.get("iteration_index", index)): {
            str(target)
            for target in iteration.get("selected_targets", [])
            if str(target).strip()
        }
        for index, iteration in enumerate(iterations, start=1)
        if isinstance(iteration, dict)
    }


def _duration_command_runs(iterations: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    command_runs: list[dict[str, Any]] = []
    for iteration in iterations:
        iteration_index = int(iteration.get("iteration_index", 0) or 0)
        for result in iteration.get("command_results", []):
            if not isinstance(result, dict):
                continue
            command_runs.append(
                {
                    "iteration_index": iteration_index,
                    "target": str(result.get("target", "")).strip(),
                    "duration_ms": int(result.get("duration_ms", 0) or 0),
                }
            )
    return command_runs


def _writer_cost_rows(
    *,
    iteration_count: int,
    writers: Sequence[dict[str, Any]],
    selected_by_iteration: dict[int, set[str]],
    command_runs: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    writer_targets = [str(writer["target"]) for writer in writers]
    writer_by_target = {str(writer["target"]): writer for writer in writers}
    writer_costs: list[dict[str, Any]] = []
    for target in writer_targets:
        runs = [item for item in command_runs if item["target"] == target]
        durations = [int(item["duration_ms"]) for item in runs]
        selected_iterations = [
            index
            for index in range(1, iteration_count + 1)
            if target in selected_by_iteration.get(index, set())
        ]
        run_iterations = [int(item["iteration_index"]) for item in runs]
        total = sum(durations)
        run_count = len(runs)
        writer = writer_by_target[target]
        writer_costs.append(
            {
                "name": str(writer["name"]),
                "target": target,
                "produces": [str(path) for path in writer["produces"]],
                "run_count": run_count,
                "selected_iteration_count": len(selected_iterations),
                "total_duration_ms": total,
                "average_duration_ms": int(round(total / run_count))
                if run_count
                else 0,
                "max_duration_ms": max(durations) if durations else 0,
                "first_iteration": min(run_iterations) if run_iterations else 0,
                "last_iteration": max(run_iterations) if run_iterations else 0,
                "skipped_iteration_count": max(
                    0, iteration_count - len(selected_iterations)
                ),
                "skipped_after_first_iteration_count": sum(
                    1
                    for index in range(2, iteration_count + 1)
                    if target not in selected_by_iteration.get(index, set())
                ),
            }
        )
    return writer_costs


def _expensive_prerequisite_summary(
    *,
    iteration_count: int,
    writers: Sequence[dict[str, Any]],
    selected_by_iteration: dict[int, set[str]],
    command_runs: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    expensive_targets = _dedupe_preserve_order(
        [
            str(target)
            for writer in writers
            for target in writer["expensive_prerequisites_once"]
        ]
    )
    expensive_run_targets = {
        target
        for item in command_runs
        if (target := str(item["target"])) in set(expensive_targets)
    }
    expensive_selected_count = sum(
        1
        for index in range(2, iteration_count + 1)
        for target in expensive_targets
        if target in selected_by_iteration.get(index, set())
    )
    expensive_first_runs = [
        item
        for item in command_runs
        if item["target"] in expensive_targets and int(item["iteration_index"]) == 1
    ]
    expensive_post_first_runs = [
        item
        for item in command_runs
        if item["target"] in expensive_targets and int(item["iteration_index"]) > 1
    ]
    post_first_opportunities = max(0, iteration_count - 1) * len(expensive_targets)
    skip_policy_effective = bool(
        expensive_targets
        and iteration_count > 1
        and expensive_selected_count == 0
        and not expensive_post_first_runs
    )
    return {
        "targets": expensive_targets,
        "configured_target_count": len(expensive_targets),
        "observed_target_count": len(expensive_run_targets),
        "first_iteration_run_count": len(expensive_first_runs),
        "post_first_iteration_selected_count": expensive_selected_count,
        "post_first_iteration_run_count": len(expensive_post_first_runs),
        "skipped_post_first_iteration_selection_count": max(
            0, post_first_opportunities - expensive_selected_count
        ),
        "total_duration_ms": sum(
            int(item["duration_ms"])
            for item in command_runs
            if item["target"] in expensive_targets
        ),
        "skip_policy_effective": skip_policy_effective,
        "summary": (
            "expensive prerequisites were selected only in iteration 1"
            if skip_policy_effective
            else "expensive prerequisite skip policy has no post-first evidence or selected post-first work"
        ),
    }


def _duration_summary(
    iterations: Sequence[dict[str, Any]],
    *,
    writers: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    iteration_count = len(iterations)
    selected_by_iteration = _selected_targets_by_iteration(iterations)
    command_runs = _duration_command_runs(iterations)
    writer_costs = _writer_cost_rows(
        iteration_count=iteration_count,
        writers=writers,
        selected_by_iteration=selected_by_iteration,
        command_runs=command_runs,
    )
    expensive_summary = _expensive_prerequisite_summary(
        iteration_count=iteration_count,
        writers=writers,
        selected_by_iteration=selected_by_iteration,
        command_runs=command_runs,
    )
    total_duration_ms = sum(int(item["duration_ms"]) for item in command_runs)
    return {
        "iteration_count": iteration_count,
        "command_run_count": len(command_runs),
        "total_duration_ms": total_duration_ms,
        "writer_costs": writer_costs,
        "expensive_prerequisites_once": expensive_summary,
        "summary": (
            f"{len(writer_costs)} writers ran {len(command_runs)} commands across "
            f"{iteration_count} iterations; total_duration_ms={total_duration_ms}; "
            "expensive_prerequisite_skip_effective="
            f"{expensive_summary['skip_policy_effective']}"
        ),
    }


def _run_target(
    vault: Path,
    *,
    target: str,
    python_executable: str,
    make_variables: Sequence[str],
    timeout_seconds: int,
    command_runner: CommandRunner,
    runtime_env: Mapping[str, str],
) -> dict[str, Any]:
    command_results, _failed = _run_iteration(
        vault,
        targets=[target],
        python_executable=python_executable,
        make_variables=make_variables,
        timeout_seconds=timeout_seconds,
        command_runner=command_runner,
        runtime_env=runtime_env,
    )
    return command_results[0]


def _fixed_point_freshness_debt_record(vault: Path) -> dict[str, Any]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(
        vault / ARTIFACT_FRESHNESS_REPORT_PATH
    )
    if diagnostics.get("status") != "ok":
        return {
            "path": DEFAULT_OUT,
            "present": False,
            "has_schema_debt": False,
            "load_status": str(diagnostics.get("status", "unknown")),
            "issues": [],
            "schema_validation_errors": [],
        }
    artifact_records = payload.get("artifact_records")
    if not isinstance(artifact_records, list):
        artifact_records = []
    for item in artifact_records:
        if not isinstance(item, dict) or item.get("path") != DEFAULT_OUT:
            continue
        raw_issues = item.get("issues")
        issues: list[Any] = raw_issues if isinstance(raw_issues, list) else []
        raw_schema_validation_errors = item.get("schema_validation_errors")
        schema_validation_errors: list[Any] = (
            raw_schema_validation_errors
            if isinstance(raw_schema_validation_errors, list)
            else []
        )
        has_schema_debt = (
            str(item.get("schema_validation_status", "")).strip() == "fail"
            and FIXED_POINT_SCHEMA_DEBT_ISSUE in issues
        )
        return {
            "path": DEFAULT_OUT,
            "present": True,
            "has_schema_debt": has_schema_debt,
            "load_status": "ok",
            "issues": [str(issue) for issue in issues],
            "schema_validation_errors": [
                str(error) for error in schema_validation_errors
            ],
        }
    return {
        "path": DEFAULT_OUT,
        "present": False,
        "has_schema_debt": False,
        "load_status": "ok",
        "issues": [],
        "schema_validation_errors": [],
    }


def _load_fixed_point_digest_map(vault: Path) -> tuple[dict[str, str], dict[str, Any]]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(vault / DEFAULT_OUT)
    status = str(diagnostics.get("status", "unknown"))
    if status != "ok":
        return {}, {
            "path": DEFAULT_OUT,
            "load_status": status,
            "status": "missing",
            "digest_count": 0,
            "summary": "fixed-point report is unavailable; run release-closeout-fixed-point",
        }
    raw_digest_map = payload.get("final_digest_map")
    digest_map = {
        str(path): str(digest)
        for path, digest in raw_digest_map.items()
        if isinstance(path, str) and isinstance(digest, str)
    } if isinstance(raw_digest_map, dict) else {}
    report_status = str(payload.get("status", "unknown")).strip() or "unknown"
    return digest_map, {
        "path": DEFAULT_OUT,
        "load_status": "ok",
        "status": report_status,
        "digest_count": len(digest_map),
        "summary": f"fixed-point report status={report_status}; digest_count={len(digest_map)}",
    }


def _artifact_freshness_records(vault: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
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
    issues = [str(issue) for issue in raw_issues] if isinstance(raw_issues, list) else []
    schema_validation_status = str(
        freshness_record.get("schema_validation_status", "")
    ).strip()
    freshness_status = "attention" if issues or schema_validation_status == "fail" else "pass"
    return schema_validation_status, issues if freshness_status == "attention" else issues


def _dry_run_tracked_artifact_record(
    vault: Path,
    item: dict[str, str],
    *,
    baseline_digest_map: dict[str, str],
    current_digest_map: dict[str, str],
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
    baseline_digest = baseline_digest_map.get(rel_path, "missing")
    current_digest = current_digest_map.get(rel_path, "missing")
    digest_status = "current" if baseline_digest == current_digest else "changed"
    freshness_record = freshness_records.get(rel_path, {})
    schema_validation_status, issues = _freshness_signal(freshness_record)
    freshness_status = "attention" if issues or schema_validation_status == "fail" else "pass"
    refresh_needed = (
        load_status != "ok"
        or digest_status != "current"
        or source_tree_status != "current"
        or freshness_status != "pass"
    )
    return {
        "name": str(item["name"]),
        "path": rel_path,
        "producer_target": producer_by_path.get(rel_path, ""),
        "load_status": load_status,
        "baseline_digest": baseline_digest,
        "current_digest": current_digest,
        "digest_status": digest_status,
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
    baseline_digest_map: dict[str, str],
    current_digest_map: dict[str, str],
    freshness_records: dict[str, dict[str, Any]],
    current_source_tree_fingerprint: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    tracked_records = [
        _dry_run_tracked_artifact_record(
            vault,
            item,
            baseline_digest_map=baseline_digest_map,
            current_digest_map=current_digest_map,
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
        return _initial_iteration_targets(runtime.writers)
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
        if record["baseline_digest"] == "missing":
            reasons.append(f"{path}:baseline_digest_missing")
        if record["current_digest"] == "missing":
            reasons.append(f"{path}:current_digest_missing")
        if record["source_tree_status"] in {"missing", "unreadable"}:
            reasons.append(f"{path}:source_tree_fingerprint_{record['source_tree_status']}")
    return _dedupe_preserve_order(reasons)


def _dry_run_drift_reasons(tracked_records: Sequence[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    for record in tracked_records:
        path = str(record["path"])
        if (
            record["digest_status"] == "changed"
            and record["baseline_digest"] != "missing"
            and record["current_digest"] != "missing"
        ):
            reasons.append(f"{path}:digest_changed")
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


def _expected_digest_to_settle(
    writes: Sequence[str],
    *,
    tracked_by_path: Mapping[str, dict[str, Any]],
) -> dict[str, str]:
    expected: dict[str, str] = {}
    for path in writes:
        record = tracked_by_path.get(path)
        digest = str(record.get("current_digest", "unknown")) if record else "unknown"
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
        return "fixed-point baseline evidence is unavailable; run the bootstrap writer chain"
    affected = set(affected_paths)
    direct_paths = [path for path in writes if path in affected]
    if direct_paths:
        reason_parts: list[str] = []
        for path in direct_paths:
            record = tracked_by_path.get(path, {})
            path_reasons = []
            if record.get("digest_status") != "current":
                path_reasons.append("digest drift")
            if record.get("source_tree_status") != "current":
                path_reasons.append(f"source tree {record.get('source_tree_status')}")
            if record.get("freshness_status") != "pass":
                path_reasons.append("freshness attention")
            if record.get("load_status") != "ok":
                path_reasons.append(f"load {record.get('load_status')}")
            reason_parts.append(f"{path} ({', '.join(path_reasons) or 'refresh needed'})")
        return "refreshes affected artifact(s): " + "; ".join(reason_parts)
    upstream_paths: list[str] = []
    for path in affected_paths:
        producer = runtime.producer_by_path.get(path, "")
        if target in runtime.downstream_by_target.get(producer, set()):
            upstream_paths.append(path)
    if upstream_paths:
        return "downstream of affected artifact(s): " + ", ".join(upstream_paths)
    return "included in the fixed-point bootstrap/prerequisite writer set"


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
                "expected_digest_to_settle": _expected_digest_to_settle(
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
    runtime_context = context or RuntimeContext(display_timezone=dt.timezone.utc)
    generated_at = runtime_context.isoformat_z()
    runtime = _policy_runtime(vault)
    baseline_digest_map, fixed_point_summary = _load_fixed_point_digest_map(vault)
    current_digest_map = _digest_map(vault, runtime.tracked_artifacts)
    freshness_records, freshness_summary = _artifact_freshness_records(vault)
    current_source_tree_fingerprint = release_source_tree_fingerprint(vault)
    tracked_records, affected_paths = _dry_run_tracked_records(
        vault,
        runtime,
        baseline_digest_map=baseline_digest_map,
        current_digest_map=current_digest_map,
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
        source_paths=["ops/scripts/release_closeout_fixed_point.py"],
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


def _promote_fixed_point_candidate(vault: Path, candidate_path: Path) -> Path:
    destination_path = resolve_repo_artifact_path(
        vault,
        DEFAULT_OUT,
        default_relative_path=DEFAULT_OUT,
    )
    return promote_schema_validated_json(
        vault,
        candidate_path=candidate_path,
        destination_path=destination_path,
        schema_path=SCHEMA_PATH,
        expected_artifact_kind="release_closeout_fixed_point_report",
        expected_producer=PRODUCER,
        context=f"release closeout fixed-point bootstrap promotion failed for {display_path(vault, destination_path)}",
    )


def bootstrap_post_promote_freshness(
    vault: Path,
    *,
    max_bootstrap_passes: int = 2,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    python_executable: str | None = None,
    make_variables: Sequence[str] = (),
    candidate_prefix: str = DEFAULT_BOOTSTRAP_CANDIDATE_PREFIX,
    context: RuntimeContext | None = None,
    command_runner: CommandRunner = _default_runner,
) -> dict[str, Any]:
    if max_bootstrap_passes < 1:
        raise ValueError("max_bootstrap_passes must be >= 1")
    runtime_context = context or RuntimeContext(display_timezone=dt.timezone.utc)
    generated_at = runtime_context.isoformat_z()
    active_python = python_executable or sys.executable
    runtime_env = {**os.environ, "LLMWIKI_RUNTIME_UTC_NOW": generated_at}
    initial_debt = _fixed_point_freshness_debt_record(vault)
    passes: list[dict[str, Any]] = []

    if not initial_debt["has_schema_debt"]:
        return {
            "status": "pass",
            "bootstrap_required": False,
            "generated_at": generated_at,
            "max_bootstrap_passes": max_bootstrap_passes,
            "passes": passes,
            "initial_fixed_point_freshness_debt": initial_debt,
            "final_fixed_point_freshness_debt": initial_debt,
        }

    final_debt = initial_debt
    for pass_index in range(1, max_bootstrap_passes + 1):
        artifact_freshness_result = _run_target(
            vault,
            target="artifact-freshness",
            python_executable=active_python,
            make_variables=make_variables,
            timeout_seconds=timeout_seconds,
            command_runner=command_runner,
            runtime_env=runtime_env,
        )
        pass_record: dict[str, Any] = {
            "pass_index": pass_index,
            "artifact_freshness_result": artifact_freshness_result,
            "fixed_point_candidate_path": "",
            "fixed_point_promoted_path": "",
            "fixed_point_status": "not_run",
            "post_pass_fixed_point_freshness_debt": final_debt,
        }
        if artifact_freshness_result["status"] != "pass":
            passes.append(pass_record)
            return {
                "status": "fail",
                "bootstrap_required": True,
                "generated_at": generated_at,
                "max_bootstrap_passes": max_bootstrap_passes,
                "passes": passes,
                "initial_fixed_point_freshness_debt": initial_debt,
                "final_fixed_point_freshness_debt": final_debt,
                "reason": "artifact_freshness_refresh_failed",
            }

        report = build_report(
            vault,
            max_iterations=max_iterations,
            timeout_seconds=timeout_seconds,
            python_executable=active_python,
            make_variables=make_variables,
            context=runtime_context,
            command_runner=command_runner,
        )
        candidate_path = write_report(
            vault, report, f"{candidate_prefix}-{pass_index}.json"
        )
        promoted_path = _promote_fixed_point_candidate(vault, candidate_path)
        final_debt = _fixed_point_freshness_debt_record(vault)
        pass_record.update(
            {
                "fixed_point_candidate_path": display_path(vault, candidate_path),
                "fixed_point_promoted_path": display_path(vault, promoted_path),
                "fixed_point_status": str(report.get("status", "unknown")),
                "post_pass_fixed_point_freshness_debt": final_debt,
            }
        )
        passes.append(pass_record)
        if not final_debt["has_schema_debt"]:
            return {
                "status": "pass",
                "bootstrap_required": True,
                "generated_at": generated_at,
                "max_bootstrap_passes": max_bootstrap_passes,
                "passes": passes,
                "initial_fixed_point_freshness_debt": initial_debt,
                "final_fixed_point_freshness_debt": final_debt,
            }

    return {
        "status": "fail",
        "bootstrap_required": True,
        "generated_at": generated_at,
        "max_bootstrap_passes": max_bootstrap_passes,
        "passes": passes,
        "initial_fixed_point_freshness_debt": initial_debt,
        "final_fixed_point_freshness_debt": final_debt,
        "reason": "fixed_point_freshness_schema_debt_persisted",
    }


def _fixed_point_iteration_state(
    vault: Path,
    *,
    runtime: _FixedPointPolicyRuntime,
    max_iterations: int,
    timeout_seconds: int,
    python_executable: str,
    make_variables: Sequence[str],
    runtime_env: Mapping[str, str],
    command_runner: CommandRunner,
) -> _FixedPointIterationState:
    next_targets = _initial_iteration_targets(runtime.writers)
    iterations: list[dict[str, Any]] = []
    previous_digest_map: dict[str, str] | None = None
    converged = False
    converged_iteration = 0
    failed = False

    for iteration_index in range(1, max_iterations + 1):
        command_results, command_failed = _run_iteration(
            vault,
            targets=next_targets,
            python_executable=python_executable,
            make_variables=make_variables,
            timeout_seconds=timeout_seconds,
            command_runner=command_runner,
            runtime_env=runtime_env,
        )
        current_digest_map = _digest_map(vault, runtime.tracked_artifacts)
        changed_paths = _changed_paths(previous_digest_map, current_digest_map)
        iterations.append(
            {
                "iteration_index": iteration_index,
                "status": "fail" if command_failed else "pass",
                "selected_targets": list(next_targets),
                "command_results": command_results,
                "digest_map": current_digest_map,
                "digest_changed": previous_digest_map is None or bool(changed_paths),
                "changed_paths": changed_paths,
            }
        )
        if command_failed:
            failed = True
            break
        if previous_digest_map is not None and current_digest_map == previous_digest_map:
            converged = True
            converged_iteration = iteration_index
            break
        next_targets = _downstream_targets_for_changed_paths(
            changed_paths,
            writers=runtime.writers,
            producer_by_path=runtime.producer_by_path,
            downstream_by_target=runtime.downstream_by_target,
        )
        previous_digest_map = current_digest_map

    final_digest_map = (
        iterations[-1]["digest_map"]
        if iterations
        else _digest_map(vault, runtime.tracked_artifacts)
    )
    final_changed_paths = (
        iterations[-1]["changed_paths"] if iterations else sorted(final_digest_map)
    )
    if failed:
        status = "fail"
        reason = "iteration_command_failed"
    elif converged:
        status = "pass"
        reason = "digest_map_converged"
    else:
        status = "non_converged"
        reason = "digest_map_changed_until_iteration_budget_exhausted"
    return _FixedPointIterationState(
        iterations=iterations,
        final_digest_map=final_digest_map,
        final_changed_paths=final_changed_paths,
        status=status,
        reason=reason,
        converged=converged,
        converged_iteration=converged_iteration,
    )


def _fixed_point_envelope(
    vault: Path,
    *,
    runtime: _FixedPointPolicyRuntime,
    generated_at: str,
    max_iterations: int,
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
        source_paths=["ops/scripts/release_closeout_fixed_point.py"],
        path_group_inputs={"tracked_artifacts": runtime.tracked_paths},
        text_inputs={
            "policy_version": str(runtime.policy.get("version", "")),
            "max_iterations": str(max_iterations),
            "timeout_seconds": str(timeout_seconds),
            "writer_targets": "\n".join(runtime.writer_targets),
            "initial_iteration_targets": "\n".join(
                _initial_iteration_targets(runtime.writers)
            ),
            "make_variables": "\n".join(
                sanitize_report_text(vault, item) for item in make_variables
            ),
        },
        source_tree_excluded_files=(DEFAULT_OUT,),
    )


def build_report(
    vault: Path,
    *,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    python_executable: str | None = None,
    make_variables: Sequence[str] = (),
    context: RuntimeContext | None = None,
    command_runner: CommandRunner = _default_runner,
) -> dict[str, Any]:
    if max_iterations < 1:
        raise ValueError("max_iterations must be >= 1")
    runtime_context = context or RuntimeContext(display_timezone=dt.timezone.utc)
    generated_at = runtime_context.isoformat_z()
    active_python = python_executable or sys.executable
    runtime = _policy_runtime(vault)
    runtime_env = {**os.environ, "LLMWIKI_RUNTIME_UTC_NOW": generated_at}
    iteration_state = _fixed_point_iteration_state(
        vault,
        runtime=runtime,
        max_iterations=max_iterations,
        timeout_seconds=timeout_seconds,
        python_executable=active_python,
        make_variables=make_variables,
        runtime_env=runtime_env,
        command_runner=command_runner,
    )
    duration_summary = _duration_summary(
        iteration_state.iterations,
        writers=runtime.writers,
    )
    envelope = _fixed_point_envelope(
        vault,
        runtime=runtime,
        generated_at=generated_at,
        max_iterations=max_iterations,
        timeout_seconds=timeout_seconds,
        make_variables=make_variables,
    )
    return {
        **envelope,
        "vault": display_path(vault, vault),
        "policy": {
            "path": POLICY_PATH,
            "version": int(runtime.policy.get("version", 1) or 1),
        },
        "status": iteration_state.status,
        "max_iterations": max_iterations,
        "iteration_count": len(iteration_state.iterations),
        "converged": iteration_state.converged,
        "converged_iteration": iteration_state.converged_iteration,
        "tracked_artifacts": runtime.tracked_artifacts,
        "command_sequence": runtime.writer_targets,
        "iterations": iteration_state.iterations,
        "final_digest_map": iteration_state.final_digest_map,
        "duration_summary": duration_summary,
        "convergence_summary": {
            "reason": iteration_state.reason,
            "changed_path_count": len(iteration_state.final_changed_paths),
            "changed_paths": iteration_state.final_changed_paths,
            "previous_iteration": max(0, len(iteration_state.iterations) - 1),
            "current_iteration": len(iteration_state.iterations),
        },
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
    targets = [str(target) for target in raw_targets] if isinstance(raw_targets, list) else []
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
        description="Run release closeout report writers until their digest map reaches a fixed point.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS)
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
        "--bootstrap-post-promote",
        action="store_true",
        help="After canonical promotion, refresh artifact-freshness and the fixed-point report if freshness still records fixed-point schema debt.",
    )
    parser.add_argument("--bootstrap-max-passes", type=int, default=2)
    parser.add_argument(
        "--bootstrap-candidate-prefix", default=DEFAULT_BOOTSTRAP_CANDIDATE_PREFIX
    )
    parser.add_argument(
        "--make-variable",
        action="append",
        default=[],
        help="Additional KEY=VALUE assignment forwarded to every nested make invocation.",
    )
    parser.add_argument("--no-fail", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    if args.bootstrap_post_promote:
        result = bootstrap_post_promote_freshness(
            vault,
            max_bootstrap_passes=args.bootstrap_max_passes,
            max_iterations=args.max_iterations,
            timeout_seconds=args.timeout_seconds,
            python_executable=args.python,
            make_variables=tuple(args.make_variable),
            candidate_prefix=args.bootstrap_candidate_prefix,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        if args.no_fail:
            return 0
        return 0 if result["status"] == "pass" else 1
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
        if args.fail_on_refresh_required and report["refresh_required"] and not args.no_fail:
            return 1
        return 0
    report = build_report(
        vault,
        max_iterations=args.max_iterations,
        timeout_seconds=args.timeout_seconds,
        python_executable=args.python,
        make_variables=tuple(args.make_variable),
    )
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    if args.no_fail:
        return 0
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
