from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from ops.scripts.core.command_runtime import TimedProcessResult, run_with_timeout
from ops.scripts.core.output_runtime import display_path, sanitize_report_text
from ops.scripts.core.runtime_context import RuntimeContext

DEFAULT_OUT = "tmp/goal-runtime-local-evidence-refresh.json"
PRODUCER = "ops.scripts.goal_runtime_local_evidence_refresh"
SOURCE_COMMAND = "make goal-runtime-local-evidence-refresh"
DEFAULT_MAX_ITERATIONS = 6
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_TARGET_SEQUENCE = (
    "goal-runtime-refresh",
    "goal-runtime-local-readiness",
    "goal-runtime-local-session-synopsis",
    "goal-runtime-local-negative-lessons",
    "goal-runtime-local-remediation-backlog",
)
DEFAULT_TRACKED_PATHS = (
    "runs/goal-auto-improve-trial/state/codex-goal-contract.json",
    "runs/goal-auto-improve-trial/state/goal-run-status.json",
    "runs/goal-auto-improve-trial/state/auto-improve-readiness.json",
    "runs/goal-auto-improve-trial/state/session-synopsis.json",
    "runs/goal-auto-improve-trial/state/self-improvement-negative-lessons.json",
    "runs/goal-auto-improve-trial/state/remediation-backlog.json",
)
SEMANTIC_VOLATILE_KEYS = frozenset(
    {
        "contract_sha256",
        "currentness",
        "generated_at",
        "input_fingerprints",
        "source_tree_fingerprint",
    }
)
SEMANTIC_VOLATILE_PATHS = (
    ("run", "started_at"),
    ("run", "updated_at"),
    ("observability", "last_heartbeat_at"),
    ("observability", "last_checkpoint_at"),
    ("periodic_evidence", "checkpoints", "*", "due_at"),
)

CommandRunner = Callable[
    [Sequence[str], Path, int, Mapping[str, str]], TimedProcessResult
]


class GoalRuntimeLocalEvidenceRefreshCommandPayload(TypedDict):
    target: str
    command: list[str]
    returncode: int
    timed_out: bool
    timeout_seconds: int
    termination_reason: str
    stdout_tail: str
    stderr_tail: str
    status: str


class GoalRuntimeLocalEvidenceRefreshIteration(TypedDict):
    iteration_index: int
    command_results: list[GoalRuntimeLocalEvidenceRefreshCommandPayload]
    changed_paths: list[str]
    missing_paths: list[str]
    status: str


class GoalRuntimeLocalEvidenceRefreshSummary(TypedDict):
    iteration_count: int
    command_count: int
    converged_iteration: int
    changed_path_count: int
    missing_path_count: int


class GoalRuntimeLocalEvidenceRefreshReport(TypedDict):
    artifact_kind: str
    producer: str
    source_command: str
    generated_at: str
    vault: str
    status: str
    reason: str
    converged: bool
    summary: GoalRuntimeLocalEvidenceRefreshSummary
    max_iterations: int
    timeout_seconds: int
    target_sequence: list[str]
    tracked_paths: list[str]
    digest_mode: str
    semantic_volatile_keys: list[str]
    semantic_volatile_paths: list[str]
    final_digest_map: dict[str, str]
    iterations: list[GoalRuntimeLocalEvidenceRefreshIteration]


@dataclass(frozen=True)
class GoalRuntimeLocalEvidenceRefreshRequest:
    vault: Path
    out_path: str = DEFAULT_OUT
    python_executable: str = sys.executable
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    targets: Sequence[str] = DEFAULT_TARGET_SEQUENCE
    tracked_paths: Sequence[str] = DEFAULT_TRACKED_PATHS
    make_variables: Sequence[str] = ()
    runtime_utc_now: str | None = None


def _runtime_utc_now(requested: str | None, env: Mapping[str, str]) -> str:
    explicit = (requested or "").strip()
    if explicit:
        return explicit
    injected = env.get("LLMWIKI_RUNTIME_UTC_NOW", "").strip()
    if injected:
        return injected
    return RuntimeContext(display_timezone=dt.UTC).isoformat_z()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _matches_semantic_volatile_path(path: tuple[str, ...]) -> bool:
    for volatile_path in SEMANTIC_VOLATILE_PATHS:
        if len(path) != len(volatile_path):
            continue
        if all(
            expected in ("*", actual)
            for actual, expected in zip(path, volatile_path, strict=False)
        ):
            return True
    return False


def _semantic_payload(value: object, path: tuple[str, ...] = ()) -> object:
    if isinstance(value, dict):
        if (
            value.get("name") == "urn:openai:artifact-envelope"
            and isinstance(value.get("value"), str)
        ):
            try:
                embedded = json.loads(value["value"])
            except json.JSONDecodeError:
                embedded = value["value"]
            return {
                **{
                    str(key): _semantic_payload(item, (*path, str(key)))
                    for key, item in value.items()
                    if str(key) not in SEMANTIC_VOLATILE_KEYS
                    and not _matches_semantic_volatile_path((*path, str(key)))
                    and str(key) != "value"
                },
                "value": _semantic_payload(embedded, (*path, "value")),
            }
        return {
            str(key): _semantic_payload(item, (*path, str(key)))
            for key, item in value.items()
            if str(key) not in SEMANTIC_VOLATILE_KEYS
            and not _matches_semantic_volatile_path((*path, str(key)))
        }
    if isinstance(value, list):
        return [_semantic_payload(item, (*path, "*")) for item in value]
    return value


def _semantic_digest(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return _sha256_file(path)
    normalized = json.dumps(
        _semantic_payload(payload),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _digest_map(vault: Path, tracked_paths: Sequence[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for relative_path in tracked_paths:
        path = vault / relative_path
        digests[relative_path] = _semantic_digest(path) if path.is_file() else "missing"
    return digests


def _changed_paths(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    return [path for path in after if before.get(path) != after.get(path)]


def _missing_paths(digests: Mapping[str, str]) -> list[str]:
    return [path for path, digest in digests.items() if digest == "missing"]


def _tail(text: str, *, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _run_command(
    argv: Sequence[str],
    cwd: Path,
    timeout_seconds: int,
    env: Mapping[str, str],
) -> TimedProcessResult:
    return run_with_timeout(
        list(argv),
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        env=env,
    )


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


def _command_payload(
    result: TimedProcessResult,
    *,
    vault: Path,
    target: str,
) -> GoalRuntimeLocalEvidenceRefreshCommandPayload:
    return {
        "target": target,
        "command": [sanitize_report_text(vault, item) for item in result.args],
        "returncode": result.returncode,
        "timed_out": result.timed_out,
        "timeout_seconds": result.timeout_seconds,
        "termination_reason": result.termination_reason,
        "stdout_tail": sanitize_report_text(vault, _tail(result.stdout)),
        "stderr_tail": sanitize_report_text(vault, _tail(result.stderr)),
        "status": "pass" if result.returncode == 0 and not result.timed_out else "fail",
    }


def _write_report(
    vault: Path,
    report: GoalRuntimeLocalEvidenceRefreshReport,
    out_path: str,
) -> Path:
    destination = vault / out_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def run_refresh(
    request: GoalRuntimeLocalEvidenceRefreshRequest,
    *,
    command_runner: CommandRunner = _run_command,
    base_env: Mapping[str, str] | None = None,
) -> GoalRuntimeLocalEvidenceRefreshReport:
    vault = request.vault.resolve()
    if request.max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")
    env = dict(base_env or os.environ)
    runtime_utc_now = _runtime_utc_now(request.runtime_utc_now, env)
    env["LLMWIKI_RUNTIME_UTC_NOW"] = runtime_utc_now
    previous_digests = _digest_map(vault, request.tracked_paths)
    iterations: list[GoalRuntimeLocalEvidenceRefreshIteration] = []
    status = "fail"
    reason = "not_converged"
    converged_iteration = 0
    final_digests = previous_digests

    for iteration_index in range(1, request.max_iterations + 1):
        before_digests = previous_digests
        command_results: list[GoalRuntimeLocalEvidenceRefreshCommandPayload] = []
        failed = False
        print(f"goal-runtime-local-evidence-refresh: iteration {iteration_index}")
        for target in request.targets:
            command = _make_command(
                target,
                vault=vault,
                python_executable=request.python_executable,
                make_variables=request.make_variables,
            )
            result = command_runner(command, vault, request.timeout_seconds, env)
            payload = _command_payload(result, vault=vault, target=target)
            command_results.append(payload)
            print(
                "  "
                f"{target}: {payload['status']}"
                f" (returncode={payload['returncode']})"
            )
            if payload["status"] != "pass":
                failed = True
                break
        after_digests = _digest_map(vault, request.tracked_paths)
        changed_paths = _changed_paths(before_digests, after_digests)
        missing_paths = _missing_paths(after_digests)
        iterations.append(
            {
                "iteration_index": iteration_index,
                "command_results": command_results,
                "changed_paths": changed_paths,
                "missing_paths": missing_paths,
                "status": "fail"
                if failed
                else "pass"
                if not changed_paths and not missing_paths
                else "changed",
            }
        )
        final_digests = after_digests
        if failed:
            reason = "command_failed"
            break
        if missing_paths:
            reason = "tracked_outputs_missing"
        elif not changed_paths:
            status = "pass"
            reason = "converged"
            converged_iteration = iteration_index
            break
        previous_digests = after_digests

    command_count = sum(len(iteration["command_results"]) for iteration in iterations)
    summary: GoalRuntimeLocalEvidenceRefreshSummary = {
        "iteration_count": len(iterations),
        "command_count": command_count,
        "converged_iteration": converged_iteration,
        "changed_path_count": len(_changed_paths(previous_digests, final_digests)),
        "missing_path_count": len(_missing_paths(final_digests)),
    }
    return {
        "artifact_kind": "goal_runtime_local_evidence_refresh",
        "producer": PRODUCER,
        "source_command": SOURCE_COMMAND,
        "generated_at": runtime_utc_now,
        "vault": display_path(vault, vault),
        "status": status,
        "reason": reason,
        "converged": status == "pass",
        "summary": summary,
        "max_iterations": request.max_iterations,
        "timeout_seconds": request.timeout_seconds,
        "target_sequence": list(request.targets),
        "tracked_paths": list(request.tracked_paths),
        "digest_mode": "semantic_without_envelope_fingerprints_or_clock_fields",
        "semantic_volatile_keys": sorted(SEMANTIC_VOLATILE_KEYS),
        "semantic_volatile_paths": [".".join(path) for path in SEMANTIC_VOLATILE_PATHS],
        "final_digest_map": final_digests,
        "iterations": iterations,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh run-local goal runtime evidence until tracked outputs reach a "
            "digest fixed point."
        )
    )
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output report path.")
    parser.add_argument("--python", default=sys.executable, help="Python executable for nested make.")
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--runtime-utc-now", default=None)
    parser.add_argument("--make-variable", action="append", default=[])
    parser.add_argument("--target", action="append", default=None)
    parser.add_argument("--codex-goal-contract", default=DEFAULT_TRACKED_PATHS[0])
    parser.add_argument("--goal-run-status", default=DEFAULT_TRACKED_PATHS[1])
    parser.add_argument("--auto-improve-readiness", default=DEFAULT_TRACKED_PATHS[2])
    parser.add_argument("--session-synopsis", default=DEFAULT_TRACKED_PATHS[3])
    parser.add_argument("--negative-lessons", default=DEFAULT_TRACKED_PATHS[4])
    parser.add_argument("--remediation-backlog", default=DEFAULT_TRACKED_PATHS[5])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    targets = tuple(args.target) if args.target else DEFAULT_TARGET_SEQUENCE
    tracked_paths = (
        args.codex_goal_contract,
        args.goal_run_status,
        args.auto_improve_readiness,
        args.session_synopsis,
        args.negative_lessons,
        args.remediation_backlog,
    )
    report = run_refresh(
        GoalRuntimeLocalEvidenceRefreshRequest(
            vault=Path(args.vault),
            out_path=args.out,
            python_executable=args.python,
            max_iterations=args.max_iterations,
            timeout_seconds=args.timeout_seconds,
            targets=targets,
            tracked_paths=tracked_paths,
            make_variables=tuple(args.make_variable),
            runtime_utc_now=args.runtime_utc_now,
        )
    )
    destination = _write_report(Path(args.vault).resolve(), report, args.out)
    print(display_path(Path(args.vault).resolve(), destination))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
