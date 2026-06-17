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

from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    promote_schema_validated_json,
    resolve_repo_artifact_path,
    write_schema_backed_report,
)
from ops.scripts.core.command_runtime import TimedProcessResult, run_with_timeout
from ops.scripts.core.generated_artifact_semantic_digest import (
    canonical_digest,
    semantic_digest_maps,
    semantic_file_digest,
)
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
DEFAULT_MAX_ITERATIONS = 5
DEFAULT_TIMEOUT_SECONDS = 600
ARTIFACT_FRESHNESS_REPORT_PATH = "ops/reports/artifact-freshness-report.json"
DEFAULT_BOOTSTRAP_CANDIDATE_PREFIX = "tmp/release-closeout-fixed-point.bootstrap"
FIXED_POINT_SCHEMA_DEBT_ISSUE = "schema_validation_failed"
FIXED_POINT_FRESHNESS_DEBT_ISSUES = {
    FIXED_POINT_SCHEMA_DEBT_ISSUE,
    "source_revision_mismatch",
    "source_tree_fingerprint_mismatch",
    "source_revision_unknown",
    "source_tree_fingerprint_unknown",
}
SEMANTIC_REUSE_FEEDBACK_TARGETS = frozenset(
    {
        "generated-artifact-index-body",
        "artifact-freshness",
        "external-report-action-matrix",
    }
)

CommandRunner = Callable[[Sequence[str], Path, int, Mapping[str, str]], dict[str, Any]]
ProgressSink = Callable[[str], None]


@dataclass(frozen=True)
class _FixedPointPolicyRuntime:
    policy: dict[str, Any]
    writers: list[dict[str, Any]]
    tracked_artifacts: list[dict[str, str]]
    tracked_paths: list[str]
    writer_targets: list[str]
    feedback_targets: list[str]
    feedback_exempt_targets: set[str]
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


@dataclass(frozen=True)
class _FixedPointIterationConfig:
    initial_targets: Sequence[str]
    baseline_before_first_iteration: bool
    max_iterations: int
    timeout_seconds: int
    python_executable: str
    make_variables: Sequence[str]
    runtime_env: Mapping[str, str]
    command_runner: CommandRunner
    progress_sink: ProgressSink | None = None


@dataclass
class _IterationExecutionContext:
    vault: Path
    python_executable: str
    make_variables: Sequence[str]
    timeout_seconds: int
    command_runner: CommandRunner
    runtime_env: Mapping[str, str]
    progress_sink: ProgressSink | None = None
    progress_prefix: str = "release-closeout-fixed-point"
    writer_by_target: Mapping[str, dict[str, Any]] | None = None
    semantic_reuse_signatures: dict[str, dict[str, Any]] | None = None
    tracked_paths: Sequence[str] = ()


@dataclass(frozen=True)
class _FixedPointIterationSnapshot:
    record: dict[str, Any]
    digest_map: dict[str, str]
    semantic_digest_map: dict[str, str]
    changed_paths: list[str]
    semantic_changed_paths: list[str]


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
    return json.loads(path.read_text(encoding="utf-8"))


def _policy_runtime(vault: Path) -> _FixedPointPolicyRuntime:
    policy = _load_finalizer_policy(vault)
    writers = _writer_specs(policy)
    tracked_artifacts = _tracked_artifacts(policy, writers)
    tracked_paths = [item["path"] for item in tracked_artifacts]
    writer_targets = [str(writer["target"]) for writer in writers]
    feedback_targets = _feedback_targets(policy, writers)
    feedback_exempt_targets = _feedback_exempt_targets(policy, writers)
    return _FixedPointPolicyRuntime(
        policy=policy,
        writers=writers,
        tracked_artifacts=tracked_artifacts,
        tracked_paths=tracked_paths,
        writer_targets=writer_targets,
        feedback_targets=feedback_targets,
        feedback_exempt_targets=feedback_exempt_targets,
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


def _feedback_targets(
    policy: dict[str, Any], writers: list[dict[str, Any]]
) -> list[str]:
    raw_targets = policy.get("feedback_refresh_targets", [])
    targets = (
        [str(target).strip() for target in raw_targets if str(target).strip()]
        if isinstance(raw_targets, list)
        else []
    )
    known = {str(writer["target"]) for writer in writers}
    unknown = sorted(set(targets) - known)
    if unknown:
        raise ValueError(
            f"{POLICY_PATH} feedback_refresh_targets contain unknown targets: {unknown}"
        )
    return _dedupe_preserve_order(targets)


def _feedback_exempt_targets(
    policy: dict[str, Any], writers: list[dict[str, Any]]
) -> set[str]:
    raw_targets = policy.get("feedback_refresh_exempt_targets", [])
    targets = (
        {str(target).strip() for target in raw_targets if str(target).strip()}
        if isinstance(raw_targets, list)
        else set()
    )
    known = {str(writer["target"]) for writer in writers}
    unknown = sorted(targets - known)
    if unknown:
        raise ValueError(
            f"{POLICY_PATH} feedback_refresh_exempt_targets contain unknown targets: {unknown}"
        )
    return targets


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


def _validated_initial_targets(
    targets: Sequence[str] | None,
    *,
    runtime: _FixedPointPolicyRuntime,
) -> list[str]:
    if targets is None:
        return _initial_iteration_targets(runtime.writers)
    requested = _dedupe_preserve_order(
        [str(target).strip() for target in targets if str(target).strip()]
    )
    if not requested:
        raise ValueError("initial_targets must include at least one target")
    known = {
        str(writer["target"]) for writer in runtime.writers
    } | {
        str(target)
        for writer in runtime.writers
        for target in writer["expensive_prerequisites_once"]
    }
    unknown = sorted(set(requested) - known)
    if unknown:
        raise ValueError(f"unknown initial target(s): {unknown}")
    return requested


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


def _next_iteration_targets(
    changed_paths: Sequence[str],
    *,
    runtime: _FixedPointPolicyRuntime,
) -> list[str]:
    if not changed_paths:
        return []
    feedback_targets = _feedback_targets_for_changed_paths(
        changed_paths,
        runtime=runtime,
    )
    downstream_targets = _downstream_targets_for_changed_paths(
        changed_paths,
        writers=runtime.writers,
        producer_by_path=runtime.producer_by_path,
        downstream_by_target=runtime.downstream_by_target,
    )
    return _dedupe_preserve_order([*feedback_targets, *downstream_targets])


def _feedback_targets_for_changed_paths(
    changed_paths: Sequence[str],
    *,
    runtime: _FixedPointPolicyRuntime,
) -> list[str]:
    feedback_target_set = set(runtime.feedback_targets)
    for path in changed_paths:
        producer = runtime.producer_by_path.get(path)
        if (
            producer
            and producer not in feedback_target_set
            and producer not in runtime.feedback_exempt_targets
        ):
            return list(runtime.feedback_targets)
    return []


def _digest_map(
    vault: Path, tracked_artifacts: Sequence[dict[str, str]]
) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in tracked_artifacts:
        rel_path = item["path"]
        path = vault / rel_path
        result[rel_path] = _sha256_file(path) if path.is_file() else "missing"
    return result


def _writer_by_target(writers: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(writer["target"]): dict(writer) for writer in writers}


def _writer_output_reuse_signature(
    vault: Path,
    writer: dict[str, Any],
    *,
    tracked_paths: Sequence[str],
) -> tuple[dict[str, Any] | None, str]:
    outputs: list[dict[str, str]] = []
    output_paths = {str(path) for path in writer.get("produces", [])}
    for rel_path in sorted(output_paths):
        path = vault / rel_path
        if not path.is_file():
            return None, f"{rel_path}:output_missing"
        payload, load_status = _json_payload(path)
        if load_status != "ok":
            return None, f"{rel_path}:output_{load_status}"
        input_fingerprints = payload.get("input_fingerprints")
        if not isinstance(input_fingerprints, dict):
            return None, f"{rel_path}:input_fingerprints_missing"
        semantic_mode, semantic_digest = semantic_file_digest(path)
        outputs.append(
            {
                "path": rel_path,
                "input_fingerprint_digest": canonical_digest(input_fingerprints),
                "semantic_digest": semantic_digest,
                "semantic_digest_mode": semantic_mode,
            }
        )
    if not outputs:
        return None, "writer_outputs_missing"
    context_paths = [path for path in tracked_paths if path not in output_paths]
    context_semantic_digest_map, _context_modes = semantic_digest_maps(
        vault, context_paths
    )
    return {
        "outputs": outputs,
        "tracked_context_semantic_digest": canonical_digest(
            context_semantic_digest_map
        ),
    }, ""


def _semantic_reuse_skip_result(
    *,
    vault: Path,
    target: str,
    command: Sequence[str],
    timeout_seconds: int,
    reuse_signature: dict[str, Any],
) -> dict[str, Any]:
    return {
        "target": target,
        "command": [sanitize_report_text(vault, str(item)) for item in command],
        "returncode": 0,
        "timed_out": False,
        "timeout_seconds": timeout_seconds,
        "termination_reason": "semantic_reuse_skipped",
        "duration_ms": 0,
        "stdout_tail": "",
        "stderr_tail": "",
        "status": "skipped",
        "skip_reason": "writer_input_fingerprints_and_output_semantic_digest_unchanged",
        "reuse_signature": reuse_signature,
    }


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


def _run_iteration(
    *,
    targets: Sequence[str],
    context: _IterationExecutionContext,
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
        if (
            writer is not None
            and context.semantic_reuse_signatures is not None
            and target in SEMANTIC_REUSE_FEEDBACK_TARGETS
        ):
            reuse_signature, _reuse_blocker = _writer_output_reuse_signature(
                context.vault,
                writer,
                tracked_paths=context.tracked_paths,
            )
            if (
                reuse_signature is not None
                and context.semantic_reuse_signatures.get(target) == reuse_signature
            ):
                payload = _semantic_reuse_skip_result(
                    vault=context.vault,
                    target=target,
                    command=command,
                    timeout_seconds=context.timeout_seconds,
                    reuse_signature=reuse_signature,
                )
                command_results.append(payload)
                _emit_progress(
                    context.progress_sink,
                    (
                        f"{context.progress_prefix}: skipped target={target} "
                        "reason=semantic_reuse"
                    ),
                )
                continue
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
            "termination_reason": str(result.get("termination_reason", "")),
            "duration_ms": int(result.get("duration_ms", 0) or 0),
            "stdout_tail": sanitize_report_text(
                context.vault, str(result.get("stdout_tail", ""))
            ),
            "stderr_tail": sanitize_report_text(
                context.vault, str(result.get("stderr_tail", ""))
            ),
            "status": str(result.get("status", "fail")),
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
        if (
            writer is not None
            and context.semantic_reuse_signatures is not None
            and target in SEMANTIC_REUSE_FEEDBACK_TARGETS
        ):
            reuse_signature, _reuse_blocker = _writer_output_reuse_signature(
                context.vault,
                writer,
                tracked_paths=context.tracked_paths,
            )
            if reuse_signature is not None:
                context.semantic_reuse_signatures[target] = reuse_signature
    return command_results, failed


def _fixed_point_iteration_snapshot(
    vault: Path,
    *,
    runtime: _FixedPointPolicyRuntime,
    iteration_index: int,
    selected_targets: Sequence[str],
    command_results: Sequence[dict[str, Any]],
    command_failed: bool,
    previous_digest_map: dict[str, str] | None,
    previous_semantic_digest_map: dict[str, str] | None,
) -> _FixedPointIterationSnapshot:
    current_digest_map = _digest_map(vault, runtime.tracked_artifacts)
    current_semantic_digest_map, current_semantic_digest_modes = semantic_digest_maps(
        vault, runtime.tracked_paths
    )
    changed_paths = _changed_paths(previous_digest_map, current_digest_map)
    semantic_changed_paths = _changed_paths(
        previous_semantic_digest_map,
        current_semantic_digest_map,
    )
    return _FixedPointIterationSnapshot(
        record={
            "iteration_index": iteration_index,
            "status": "fail" if command_failed else "pass",
            "selected_targets": list(selected_targets),
            "command_results": list(command_results),
            "digest_map": current_digest_map,
            "digest_changed": previous_digest_map is None or bool(changed_paths),
            "changed_paths": changed_paths,
            "semantic_digest_map": current_semantic_digest_map,
            "semantic_digest_modes": current_semantic_digest_modes,
            "semantic_changed_paths": semantic_changed_paths,
        },
        digest_map=current_digest_map,
        semantic_digest_map=current_semantic_digest_map,
        changed_paths=changed_paths,
        semantic_changed_paths=semantic_changed_paths,
    )


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


def _duration_command_runs(
    iterations: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    command_runs: list[dict[str, Any]] = []
    for iteration in iterations:
        iteration_index = int(iteration.get("iteration_index", 0) or 0)
        for result in iteration.get("command_results", []):
            if not isinstance(result, dict):
                continue
            if str(result.get("status", "")).strip() == "skipped":
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
                "average_duration_ms": round(total / run_count) if run_count else 0,
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
    progress_sink: ProgressSink | None = None,
    progress_prefix: str = "release-closeout-fixed-point",
) -> dict[str, Any]:
    command_results, _failed = _run_iteration(
        targets=[target],
        context=_IterationExecutionContext(
            vault=vault,
            python_executable=python_executable,
            make_variables=make_variables,
            timeout_seconds=timeout_seconds,
            command_runner=command_runner,
            runtime_env=runtime_env,
            progress_sink=progress_sink,
            progress_prefix=progress_prefix,
        ),
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
            "has_freshness_debt": False,
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
        currentness_status = str(item.get("currentness_status", "")).strip()
        source_revision_status = str(item.get("source_revision_status", "")).strip()
        source_tree_fingerprint_status = str(
            item.get("source_tree_fingerprint_status", "")
        ).strip()
        has_freshness_debt = (
            has_schema_debt
            or currentness_status in {"stale", "unknown"}
            or source_revision_status in {"stale", "unknown"}
            or source_tree_fingerprint_status in {"stale", "unknown"}
            or any(str(issue) in FIXED_POINT_FRESHNESS_DEBT_ISSUES for issue in issues)
        )
        return {
            "path": DEFAULT_OUT,
            "present": True,
            "has_schema_debt": has_schema_debt,
            "has_freshness_debt": has_freshness_debt,
            "load_status": "ok",
            "currentness_status": currentness_status,
            "source_revision_status": source_revision_status,
            "source_tree_fingerprint_status": source_tree_fingerprint_status,
            "issues": [str(issue) for issue in issues],
            "schema_validation_errors": [
                str(error) for error in schema_validation_errors
            ],
        }
    return {
        "path": DEFAULT_OUT,
        "present": False,
        "has_schema_debt": False,
        "has_freshness_debt": False,
        "load_status": "ok",
        "issues": [],
        "schema_validation_errors": [],
    }


def _semantic_digest_map_from_fixed_point(payload: dict[str, Any]) -> dict[str, str]:
    raw_iterations = payload.get("iterations")
    if not isinstance(raw_iterations, list):
        return {}
    for iteration in reversed(raw_iterations):
        if not isinstance(iteration, dict):
            continue
        raw_semantic_map = iteration.get("semantic_digest_map")
        if isinstance(raw_semantic_map, dict):
            return {
                str(path): str(digest)
                for path, digest in raw_semantic_map.items()
                if isinstance(path, str) and isinstance(digest, str)
            }
    return {}


def _load_fixed_point_digest_maps(
    vault: Path,
) -> tuple[dict[str, str], dict[str, str], dict[str, Any]]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(
        vault / DEFAULT_OUT
    )
    status = str(diagnostics.get("status", "unknown"))
    if status != "ok":
        return {}, {}, {
            "path": DEFAULT_OUT,
            "load_status": status,
            "status": "missing",
            "digest_count": 0,
            "summary": "fixed-point report is unavailable; run release-closeout-fixed-point",
        }
    raw_digest_map = payload.get("final_digest_map")
    digest_map = (
        {
            str(path): str(digest)
            for path, digest in raw_digest_map.items()
            if isinstance(path, str) and isinstance(digest, str)
        }
        if isinstance(raw_digest_map, dict)
        else {}
    )
    semantic_digest_map = _semantic_digest_map_from_fixed_point(payload)
    report_status = str(payload.get("status", "unknown")).strip() or "unknown"
    return digest_map, semantic_digest_map, {
        "path": DEFAULT_OUT,
        "load_status": "ok",
        "status": report_status,
        "digest_count": len(digest_map),
        "summary": f"fixed-point report status={report_status}; digest_count={len(digest_map)}",
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
    baseline_digest_map: dict[str, str],
    baseline_semantic_digest_map: dict[str, str],
    current_digest_map: dict[str, str],
    current_semantic_digest_map: dict[str, str],
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
    baseline_semantic_digest = baseline_semantic_digest_map.get(rel_path, "unknown")
    current_semantic_digest = current_semantic_digest_map.get(rel_path, "unknown")
    semantic_digest_status = (
        "unknown"
        if "unknown" in {baseline_semantic_digest, current_semantic_digest}
        else "current"
        if baseline_semantic_digest == current_semantic_digest
        else "changed"
    )
    freshness_record = freshness_records.get(rel_path, {})
    schema_validation_status, issues = _freshness_signal(freshness_record)
    freshness_status = (
        "attention" if issues or schema_validation_status == "fail" else "pass"
    )
    digest_refresh_required = (
        semantic_digest_status == "changed"
        or (semantic_digest_status == "unknown" and digest_status != "current")
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
        "baseline_digest": baseline_digest,
        "current_digest": current_digest,
        "digest_status": digest_status,
        "baseline_semantic_digest": baseline_semantic_digest,
        "current_semantic_digest": current_semantic_digest,
        "semantic_digest_status": semantic_digest_status,
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
    baseline_semantic_digest_map: dict[str, str],
    current_digest_map: dict[str, str],
    current_semantic_digest_map: dict[str, str],
    freshness_records: dict[str, dict[str, Any]],
    current_source_tree_fingerprint: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    tracked_records = [
        _dry_run_tracked_artifact_record(
            vault,
            item,
            baseline_digest_map=baseline_digest_map,
            baseline_semantic_digest_map=baseline_semantic_digest_map,
            current_digest_map=current_digest_map,
            current_semantic_digest_map=current_semantic_digest_map,
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
            reasons.append(
                f"{path}:source_tree_fingerprint_{record['source_tree_status']}"
            )
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
        if record["semantic_digest_status"] == "changed":
            reasons.append(f"{path}:semantic_digest_changed")
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
            if record.get("semantic_digest_status") == "changed":
                path_reasons.append("semantic digest drift")
            elif record.get("digest_status") != "current":
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
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    runtime = _policy_runtime(vault)
    (
        baseline_digest_map,
        baseline_semantic_digest_map,
        fixed_point_summary,
    ) = _load_fixed_point_digest_maps(vault)
    current_digest_map = _digest_map(vault, runtime.tracked_artifacts)
    current_semantic_digest_map, _current_semantic_digest_modes = semantic_digest_maps(
        vault, runtime.tracked_paths
    )
    freshness_records, freshness_summary = _artifact_freshness_records(vault)
    current_source_tree_fingerprint = release_source_tree_fingerprint(vault)
    tracked_records, affected_paths = _dry_run_tracked_records(
        vault,
        runtime,
        baseline_digest_map=baseline_digest_map,
        baseline_semantic_digest_map=baseline_semantic_digest_map,
        current_digest_map=current_digest_map,
        current_semantic_digest_map=current_semantic_digest_map,
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


def _bootstrap_freshness_result(
    *,
    status: str,
    bootstrap_required: bool,
    generated_at: str,
    max_bootstrap_passes: int,
    passes: list[dict[str, Any]],
    initial_debt: dict[str, Any],
    final_debt: dict[str, Any],
    reason: str = "",
) -> dict[str, Any]:
    result = {
        "status": status,
        "bootstrap_required": bootstrap_required,
        "generated_at": generated_at,
        "max_bootstrap_passes": max_bootstrap_passes,
        "passes": passes,
        "initial_fixed_point_freshness_debt": initial_debt,
        "final_fixed_point_freshness_debt": final_debt,
    }
    if reason:
        result["reason"] = reason
    return result


def _initial_iteration_digest_maps(
    vault: Path,
    runtime: _FixedPointPolicyRuntime,
    *,
    baseline_before_first_iteration: bool,
) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    if not baseline_before_first_iteration:
        return None, None
    semantic_digest_map, _ = semantic_digest_maps(vault, runtime.tracked_paths)
    return _digest_map(vault, runtime.tracked_artifacts), semantic_digest_map


def _fixed_point_iteration_result(
    vault: Path,
    runtime: _FixedPointPolicyRuntime,
    *,
    iterations: list[dict[str, Any]],
    failed: bool,
    converged: bool,
    converged_iteration: int,
) -> _FixedPointIterationState:
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


def _bootstrap_pass_record(
    pass_index: int,
    *,
    artifact_freshness_result: dict[str, Any],
    post_pass_debt: dict[str, Any],
) -> dict[str, Any]:
    return {
        "pass_index": pass_index,
        "artifact_freshness_result": artifact_freshness_result,
        "fixed_point_candidate_path": "",
        "fixed_point_promoted_path": "",
        "fixed_point_status": "not_run",
        "post_pass_fixed_point_freshness_debt": post_pass_debt,
    }


def _refresh_bootstrap_artifact_freshness(
    vault: Path,
    *,
    pass_index: int,
    max_bootstrap_passes: int,
    active_python: str,
    make_variables: Sequence[str],
    timeout_seconds: int,
    runtime_env: Mapping[str, str],
    command_runner: CommandRunner,
    progress_sink: ProgressSink | None,
) -> dict[str, Any]:
    _emit_progress(
        progress_sink,
        (
            "release-closeout-fixed-point: "
            f"bootstrap-post-promote pass={pass_index}/{max_bootstrap_passes} "
            "refresh=artifact-freshness"
        ),
    )
    return _run_target(
        vault,
        target="artifact-freshness",
        python_executable=active_python,
        make_variables=make_variables,
        timeout_seconds=timeout_seconds,
        command_runner=command_runner,
        runtime_env=runtime_env,
        progress_sink=progress_sink,
        progress_prefix="release-closeout-fixed-point bootstrap-post-promote",
    )


def _rebuild_bootstrap_fixed_point_candidate(
    vault: Path,
    *,
    pass_index: int,
    max_iterations: int,
    timeout_seconds: int,
    active_python: str,
    make_variables: Sequence[str],
    candidate_prefix: str,
    runtime_context: RuntimeContext,
    command_runner: CommandRunner,
    progress_sink: ProgressSink | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    report, rebuild_mode, rebase_reason = _bootstrap_fixed_point_candidate_report(
        vault,
        pass_index=pass_index,
        max_iterations=max_iterations,
        timeout_seconds=timeout_seconds,
        active_python=active_python,
        make_variables=make_variables,
        runtime_context=runtime_context,
        command_runner=command_runner,
        progress_sink=progress_sink,
    )
    candidate_path = write_report(
        vault, report, f"{candidate_prefix}-{pass_index}.json"
    )
    promoted_path = _promote_fixed_point_candidate(vault, candidate_path)
    _emit_progress(
        progress_sink,
        (
            "release-closeout-fixed-point: "
            f"bootstrap-post-promote pass={pass_index} promoted={display_path(vault, promoted_path)}"
        ),
    )
    final_debt = _fixed_point_freshness_debt_record(vault)
    pass_record_updates = {
        "fixed_point_candidate_path": display_path(vault, candidate_path),
        "fixed_point_promoted_path": display_path(vault, promoted_path),
        "fixed_point_status": str(report.get("status", "unknown")),
        "fixed_point_rebuild_mode": rebuild_mode,
        "fixed_point_rebase_reason": rebase_reason,
        "post_pass_fixed_point_freshness_debt": final_debt,
    }
    return pass_record_updates, final_debt


def _bootstrap_fixed_point_candidate_report(
    vault: Path,
    *,
    pass_index: int,
    max_iterations: int,
    timeout_seconds: int,
    active_python: str,
    make_variables: Sequence[str],
    runtime_context: RuntimeContext,
    command_runner: CommandRunner,
    progress_sink: ProgressSink | None,
) -> tuple[dict[str, Any], str, str]:
    rebase_report, rebase_reason = _rebased_bootstrap_fixed_point_report(
        vault,
        max_iterations=max_iterations,
        timeout_seconds=timeout_seconds,
        make_variables=make_variables,
        runtime_context=runtime_context,
    )
    if rebase_report is not None:
        _emit_progress(
            progress_sink,
            (
                "release-closeout-fixed-point: "
                f"bootstrap-post-promote pass={pass_index} "
                f"rebase=fixed-point-candidate reason={rebase_reason}"
            ),
        )
        return rebase_report, "rebase_existing_converged_report", rebase_reason

    _emit_progress(
        progress_sink,
        (
            "release-closeout-fixed-point: "
            f"bootstrap-post-promote pass={pass_index} "
            f"rebase=skipped reason={rebase_reason} rebuild=fixed-point-candidate"
        ),
    )
    report = build_report(
        vault,
        max_iterations=max_iterations,
        timeout_seconds=timeout_seconds,
        python_executable=active_python,
        make_variables=make_variables,
        context=runtime_context,
        command_runner=command_runner,
        progress_sink=progress_sink,
    )
    return report, "full_fixed_point_rebuild", rebase_reason


def _rebased_bootstrap_fixed_point_report(
    vault: Path,
    *,
    max_iterations: int,
    timeout_seconds: int,
    make_variables: Sequence[str],
    runtime_context: RuntimeContext,
) -> tuple[dict[str, Any] | None, str]:
    existing, diagnostics = load_optional_json_object_with_diagnostics(
        vault / DEFAULT_OUT
    )
    load_status = str(diagnostics.get("status", "unknown"))
    if load_status != "ok":
        return None, f"existing_fixed_point_report_{load_status}"
    runtime = _policy_runtime(vault)
    blocker = _bootstrap_rebase_blocker(
        vault,
        existing,
        runtime=runtime,
        max_iterations=max_iterations,
    )
    if blocker:
        return None, blocker
    generated_at = runtime_context.isoformat_z()
    current_digest_map = _digest_map(vault, runtime.tracked_artifacts)
    previous_digest_map = {
        str(path): str(digest)
        for path, digest in existing.get("final_digest_map", {}).items()
        if isinstance(path, str) and isinstance(digest, str)
    }
    changed_paths = _changed_paths(previous_digest_map, current_digest_map)
    iteration_count = int(existing.get("iteration_count", 0) or 0)
    envelope = _fixed_point_envelope(
        vault,
        runtime=runtime,
        generated_at=generated_at,
        initial_targets=_initial_iteration_targets(runtime.writers),
        baseline_before_first_iteration=False,
        max_iterations=max_iterations,
        timeout_seconds=timeout_seconds,
        make_variables=make_variables,
    )
    report = {
        **envelope,
        "vault": display_path(vault, vault),
        "policy": {
            "path": POLICY_PATH,
            "version": int(runtime.policy.get("version", 1) or 1),
        },
        "status": "pass",
        "max_iterations": max_iterations,
        "iteration_count": iteration_count,
        "converged": True,
        "converged_iteration": int(existing.get("converged_iteration", 0) or 0),
        "tracked_artifacts": runtime.tracked_artifacts,
        "command_sequence": runtime.writer_targets,
        "iterations": existing["iterations"],
        "final_digest_map": current_digest_map,
        "duration_summary": existing["duration_summary"],
        "convergence_summary": {
            "reason": "bootstrap_post_promote_rebased_after_artifact_freshness",
            "changed_path_count": len(changed_paths),
            "changed_paths": changed_paths,
            "previous_iteration": iteration_count,
            "current_iteration": iteration_count,
        },
        "bootstrap_post_promote_rebase": {
            "status": "applied",
            "reason": "artifact_freshness_refreshed_after_canonical_promotion",
            "source_report_generated_at": str(existing.get("generated_at", "")),
            "source_report_iteration_count": iteration_count,
            "updated_digest_path_count": len(changed_paths),
            "updated_digest_paths": changed_paths,
            "summary": (
                "Reused an already converged fixed-point writer run after the "
                "post-promote artifact-freshness refresh; only the envelope and "
                "final digest map were rewritten."
            ),
        },
    }
    return report, "existing_converged_report_rebased"


def _bootstrap_rebase_blocker(
    vault: Path,
    existing: dict[str, Any],
    *,
    runtime: _FixedPointPolicyRuntime,
    max_iterations: int,
) -> str:
    if str(existing.get("artifact_kind", "")) != "release_closeout_fixed_point_report":
        return "existing_fixed_point_artifact_kind_mismatch"
    if str(existing.get("producer", "")) != PRODUCER:
        return "existing_fixed_point_producer_mismatch"
    if str(existing.get("status", "")) != "pass":
        return "existing_fixed_point_not_pass"
    if not bool(existing.get("converged", False)):
        return "existing_fixed_point_not_converged"
    if int(existing.get("max_iterations", 0) or 0) != max_iterations:
        return "existing_fixed_point_max_iterations_mismatch"
    if int(existing.get("iteration_count", 0) or 0) < 1:
        return "existing_fixed_point_iteration_count_missing"
    if not isinstance(existing.get("iterations"), list):
        return "existing_fixed_point_iterations_missing"
    if not isinstance(existing.get("duration_summary"), dict):
        return "existing_fixed_point_duration_summary_missing"
    existing_command_sequence = [
        str(target) for target in existing.get("command_sequence", [])
    ]
    if existing_command_sequence != runtime.writer_targets:
        return "existing_fixed_point_command_sequence_mismatch"
    existing_paths = [
        str(item.get("path", ""))
        for item in existing.get("tracked_artifacts", [])
        if isinstance(item, dict)
    ]
    if existing_paths != runtime.tracked_paths:
        return "existing_fixed_point_tracked_artifacts_mismatch"
    current_source_tree = release_source_tree_fingerprint(
        vault,
        extra_excluded_files=(DEFAULT_OUT,),
    )
    if str(existing.get("source_tree_fingerprint", "")) != current_source_tree:
        return "existing_fixed_point_source_tree_stale"
    return ""


def _bootstrap_no_freshness_debt_result(
    *,
    generated_at: str,
    max_bootstrap_passes: int,
    initial_debt: dict[str, Any],
    progress_sink: ProgressSink | None,
) -> dict[str, Any]:
    _emit_progress(
        progress_sink,
        "release-closeout-fixed-point: bootstrap-post-promote skipped fixed_point_freshness_debt=false",
    )
    return _bootstrap_freshness_result(
        status="pass",
        bootstrap_required=False,
        generated_at=generated_at,
        max_bootstrap_passes=max_bootstrap_passes,
        passes=[],
        initial_debt=initial_debt,
        final_debt=initial_debt,
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
    progress_sink: ProgressSink | None = None,
) -> dict[str, Any]:
    if max_bootstrap_passes < 1:
        raise ValueError("max_bootstrap_passes must be >= 1")
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    active_python = python_executable or sys.executable
    runtime_env = {**os.environ, "LLMWIKI_RUNTIME_UTC_NOW": generated_at}
    initial_debt = _fixed_point_freshness_debt_record(vault)
    passes: list[dict[str, Any]] = []

    if not initial_debt["has_freshness_debt"]:
        return _bootstrap_no_freshness_debt_result(
            generated_at=generated_at,
            max_bootstrap_passes=max_bootstrap_passes,
            initial_debt=initial_debt,
            progress_sink=progress_sink,
        )

    final_debt = initial_debt
    for pass_index in range(1, max_bootstrap_passes + 1):
        artifact_freshness_result = _refresh_bootstrap_artifact_freshness(
            vault,
            pass_index=pass_index,
            max_bootstrap_passes=max_bootstrap_passes,
            active_python=active_python,
            make_variables=make_variables,
            timeout_seconds=timeout_seconds,
            runtime_env=runtime_env,
            command_runner=command_runner,
            progress_sink=progress_sink,
        )
        pass_record = _bootstrap_pass_record(
            pass_index,
            artifact_freshness_result=artifact_freshness_result,
            post_pass_debt=final_debt,
        )
        if artifact_freshness_result["status"] != "pass":
            _emit_progress(
                progress_sink,
                (
                    "release-closeout-fixed-point: "
                    f"bootstrap-post-promote pass={pass_index} status=fail "
                    "reason=artifact_freshness_refresh_failed"
                ),
            )
            passes.append(pass_record)
            return _bootstrap_freshness_result(
                status="fail",
                bootstrap_required=True,
                generated_at=generated_at,
                max_bootstrap_passes=max_bootstrap_passes,
                passes=passes,
                initial_debt=initial_debt,
                final_debt=final_debt,
                reason="artifact_freshness_refresh_failed",
            )

        pass_record_updates, final_debt = _rebuild_bootstrap_fixed_point_candidate(
            vault,
            pass_index=pass_index,
            max_iterations=max_iterations,
            timeout_seconds=timeout_seconds,
            active_python=active_python,
            make_variables=make_variables,
            candidate_prefix=candidate_prefix,
            runtime_context=runtime_context,
            command_runner=command_runner,
            progress_sink=progress_sink,
        )
        pass_record.update(pass_record_updates)
        passes.append(pass_record)
        if not final_debt["has_freshness_debt"]:
            _emit_progress(
                progress_sink,
                (
                    "release-closeout-fixed-point: "
                    f"bootstrap-post-promote pass={pass_index} status=pass fixed_point_freshness_debt=false"
                ),
            )
            return _bootstrap_freshness_result(
                status="pass",
                bootstrap_required=True,
                generated_at=generated_at,
                max_bootstrap_passes=max_bootstrap_passes,
                passes=passes,
                initial_debt=initial_debt,
                final_debt=final_debt,
            )

    _emit_progress(
        progress_sink,
        "release-closeout-fixed-point: bootstrap-post-promote status=fail reason=fixed_point_freshness_debt_persisted",
    )
    return _bootstrap_freshness_result(
        status="fail",
        bootstrap_required=True,
        generated_at=generated_at,
        max_bootstrap_passes=max_bootstrap_passes,
        passes=passes,
        initial_debt=initial_debt,
        final_debt=final_debt,
        reason="fixed_point_freshness_debt_persisted",
    )


def _fixed_point_iteration_state(
    vault: Path,
    *,
    runtime: _FixedPointPolicyRuntime,
    config: _FixedPointIterationConfig,
) -> _FixedPointIterationState:
    next_targets = list(config.initial_targets)
    iterations: list[dict[str, Any]] = []
    previous_digest_map, previous_semantic_digest_map = _initial_iteration_digest_maps(
        vault,
        runtime,
        baseline_before_first_iteration=config.baseline_before_first_iteration,
    )
    converged = False
    converged_iteration = 0
    failed = False
    writer_by_target = _writer_by_target(runtime.writers)
    semantic_reuse_signatures: dict[str, dict[str, Any]] = {}

    for iteration_index in range(1, config.max_iterations + 1):
        _emit_progress(
            config.progress_sink,
            (
                "release-closeout-fixed-point: "
                f"iteration={iteration_index}/{config.max_iterations} "
                f"targets={','.join(next_targets)}"
            ),
        )
        command_results, command_failed = _run_iteration(
            targets=next_targets,
            context=_IterationExecutionContext(
                vault=vault,
                python_executable=config.python_executable,
                make_variables=config.make_variables,
                timeout_seconds=config.timeout_seconds,
                command_runner=config.command_runner,
                runtime_env=config.runtime_env,
                progress_sink=config.progress_sink,
                writer_by_target=writer_by_target,
                semantic_reuse_signatures=semantic_reuse_signatures,
                tracked_paths=runtime.tracked_paths,
            ),
        )
        snapshot = _fixed_point_iteration_snapshot(
            vault,
            runtime=runtime,
            iteration_index=iteration_index,
            selected_targets=next_targets,
            command_results=command_results,
            command_failed=command_failed,
            previous_digest_map=previous_digest_map,
            previous_semantic_digest_map=previous_semantic_digest_map,
        )
        iterations.append(snapshot.record)
        if command_failed:
            failed = True
            _emit_progress(
                config.progress_sink,
                (
                    "release-closeout-fixed-point: "
                    f"iteration={iteration_index} status=fail "
                    f"changed_path_count={len(snapshot.changed_paths)}"
                ),
            )
            break
        if (
            previous_digest_map is not None
            and snapshot.digest_map == previous_digest_map
        ):
            converged = True
            converged_iteration = iteration_index
            _emit_progress(
                config.progress_sink,
                (
                    "release-closeout-fixed-point: "
                    f"iteration={iteration_index} status=converged changed_path_count=0"
                ),
            )
            break
        next_targets = _next_iteration_targets(
            snapshot.semantic_changed_paths,
            runtime=runtime,
        )
        _emit_progress(
            config.progress_sink,
            (
                "release-closeout-fixed-point: "
                f"iteration={iteration_index} status=changed "
                f"changed_path_count={len(snapshot.changed_paths)} "
                f"semantic_changed_path_count={len(snapshot.semantic_changed_paths)} "
                f"next_target_count={len(next_targets)}"
            ),
        )
        previous_digest_map = snapshot.digest_map
        previous_semantic_digest_map = snapshot.semantic_digest_map

    return _fixed_point_iteration_result(
        vault,
        runtime,
        iterations=iterations,
        failed=failed,
        converged=converged,
        converged_iteration=converged_iteration,
    )


def _fixed_point_envelope(
    vault: Path,
    *,
    runtime: _FixedPointPolicyRuntime,
    generated_at: str,
    initial_targets: Sequence[str],
    baseline_before_first_iteration: bool,
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
        source_paths=[
            "ops/scripts/release/release_closeout_fixed_point.py",
            "ops/scripts/core/generated_artifact_semantic_digest.py",
        ],
        path_group_inputs={"tracked_artifacts": runtime.tracked_paths},
        text_inputs={
            "policy_version": str(runtime.policy.get("version", "")),
            "max_iterations": str(max_iterations),
            "timeout_seconds": str(timeout_seconds),
            "writer_targets": "\n".join(runtime.writer_targets),
            "feedback_targets": "\n".join(runtime.feedback_targets),
            "initial_iteration_targets": "\n".join(initial_targets),
            "baseline_before_first_iteration": str(
                baseline_before_first_iteration
            ).lower(),
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
    initial_targets: Sequence[str] | None = None,
    baseline_before_first_iteration: bool = False,
    context: RuntimeContext | None = None,
    command_runner: CommandRunner = _default_runner,
    progress_sink: ProgressSink | None = None,
) -> dict[str, Any]:
    if max_iterations < 1:
        raise ValueError("max_iterations must be >= 1")
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    active_python = python_executable or sys.executable
    runtime = _policy_runtime(vault)
    selected_initial_targets = _validated_initial_targets(
        initial_targets,
        runtime=runtime,
    )
    runtime_env = {**os.environ, "LLMWIKI_RUNTIME_UTC_NOW": generated_at}
    iteration_state = _fixed_point_iteration_state(
        vault,
        runtime=runtime,
        config=_FixedPointIterationConfig(
            initial_targets=selected_initial_targets,
            baseline_before_first_iteration=baseline_before_first_iteration,
            max_iterations=max_iterations,
            timeout_seconds=timeout_seconds,
            python_executable=active_python,
            make_variables=make_variables,
            runtime_env=runtime_env,
            command_runner=command_runner,
            progress_sink=progress_sink,
        ),
    )
    duration_summary = _duration_summary(
        iteration_state.iterations,
        writers=runtime.writers,
    )
    envelope = _fixed_point_envelope(
        vault,
        runtime=runtime,
        generated_at=generated_at,
        initial_targets=selected_initial_targets,
        baseline_before_first_iteration=baseline_before_first_iteration,
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
        help="After canonical promotion, refresh artifact-freshness and the fixed-point report if freshness still records fixed-point debt.",
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
    parser.add_argument(
        "--initial-target",
        action="append",
        default=[],
        help=(
            "Restrict the first fixed-point iteration to this writer target. "
            "May be repeated; later iterations still follow policy dependencies."
        ),
    )
    parser.add_argument(
        "--baseline-before-first-iteration",
        action="store_true",
        help=(
            "Capture digest baselines before the first iteration so narrow initial "
            "target slices expand only from artifacts that actually changed."
        ),
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
            progress_sink=_stderr_progress,
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
        if (
            args.fail_on_refresh_required
            and report["refresh_required"]
            and not args.no_fail
        ):
            return 1
        return 0
    report = build_report(
        vault,
        max_iterations=args.max_iterations,
        timeout_seconds=args.timeout_seconds,
        python_executable=args.python,
        make_variables=tuple(args.make_variable),
        initial_targets=tuple(args.initial_target) or None,
        baseline_before_first_iteration=args.baseline_before_first_iteration,
        progress_sink=_stderr_progress,
    )
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    if args.no_fail:
        return 0
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
