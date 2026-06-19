from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from .artifact_io_runtime import write_schema_validated_json
from .codex_exec_integrity_runtime import (
    _apply_non_worker_integrity_guard,
    _workspace_integrity_digests,
)
from .codex_exec_sanitize_runtime import (
    _display_command_argv,
    _sanitize_argv,
    _sanitize_json_strings,
    _sanitize_path_text,
)
from .command_log_summary_runtime import (
    command_log_summary_rel,
    command_log_trace_rel,
    write_command_log_summary,
)
from .command_runtime import run_with_timeout
from .experiment_telemetry_runtime import (
    append_ledger_event,
    run_rel,
    write_timeout_failure_artifact,
)
from .output_runtime import write_output_text
from .policy_runtime import report_path
from .runtime_context import RuntimeContext
from .runtime_event_logging_runtime import append_runtime_event
from .schema_constants_runtime import EXECUTOR_REPORT_SCHEMA_PATH
from .schema_runtime import load_schema

EXECUTOR_REPORT_SCHEMA = EXECUTOR_REPORT_SCHEMA_PATH
DEFAULT_CODEX_EXEC_TIMEOUT_SECONDS = 1800
NON_WORKER_PROJECT_CHECK_MODULES = (
    ("pytest", "pytest"),
    ("jsonschema", "jsonschema"),
    ("yaml", "PyYAML"),
)
PROJECT_CHECK_LANE = (
    "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider <focused-selector>"
)
PROJECT_FULL_REGRESSION_LANE = "make test-all"
PROJECT_RELEASE_EVIDENCE_LANE = "make test-execution-summary-full-current-or-refresh"
_CODEX_USAGE_LIMIT_RE = re.compile(
    r"(usage limit|try again at|upgrade to pro)",
    flags=re.IGNORECASE,
)
_CODEX_USAGE_LIMIT_RETRY_RE = re.compile(
    r"try again at\s+([^.\n\r]+)",
    flags=re.IGNORECASE,
)


class CodexExecError(Exception):
    pass


class ExecutorContractError(CodexExecError):
    pass


class ExecutorInfoPayload(TypedDict):
    name: str
    sandbox_mode: str
    model: str
    reasoning_effort: str


class ExecutorCommandPayload(TypedDict):
    argv: list[str]


class ExecutorArtifactsPayload(TypedDict):
    prompt: str
    output_last_message: str
    stdout: str
    stderr: str
    command_log_summary: str
    timeout_failure: str | None


class ExecutorObservabilityPayload(TypedDict):
    heartbeat_count: int
    heartbeat_interval_seconds: int
    quiet_seconds: int
    last_stdout_at: str
    last_stderr_at: str
    last_artifact_touch_at: str
    observation_mode: str


class ExecutorResultPayload(TypedDict):
    returncode: int
    timed_out: bool
    timeout_seconds: int
    termination_reason: str
    launch_succeeded: bool
    signal_sent: str
    final_state_observed: str
    stdout_received: bool
    stderr_received: bool
    observability: ExecutorObservabilityPayload


class ExecutorDiagnosticsPayload(TypedDict):
    routing_report: str
    scope_freeze: str
    dependency_preflight: ExecutorDependencyPreflightPayload
    notes: list[str]


class ExecutorDependencyCommandPayload(TypedDict):
    argv: list[str]
    project_check_lane: str


class ExecutorDependencyPythonPayload(TypedDict):
    path: str
    executable: str
    version: str
    exists: bool


class ExecutorDependencyModulePayload(TypedDict):
    import_name: str
    package: str
    status: str
    version: str
    detail: str


class ExecutorDependencyPreflightPayload(TypedDict):
    role_requires_project_check: bool
    status: str
    command: ExecutorDependencyCommandPayload
    python: ExecutorDependencyPythonPayload
    required_modules: list[ExecutorDependencyModulePayload]
    returncode: int


ExecutorReportPayload = TypedDict(
    "ExecutorReportPayload",
    {
        "$schema": str,
        "run_id": str,
        "role": str,
        "generated_at": str,
        "executor": ExecutorInfoPayload,
        "status": str,
        "command": ExecutorCommandPayload,
        "artifacts": ExecutorArtifactsPayload,
        "result": ExecutorResultPayload,
        "diagnostics": ExecutorDiagnosticsPayload,
    },
)


@dataclass(frozen=True)
class _ExecutorArtifacts:
    output_last_message_rel: str
    stdout_rel: str
    stderr_rel: str
    raw_stdout_rel: str
    raw_stderr_rel: str
    command_log_summary_rel: str
    prompt_rel: str


@dataclass(frozen=True)
class _ExecutionSummary:
    status: str
    decision: str
    notes: list[str]
    timed_out: bool
    timeout_seconds: int
    termination_reason: str


@dataclass(frozen=True)
class _ModelOutputRead:
    payload: dict[str, Any] | None
    status: str
    note: str
    raw_bytes: bytes | None = None


@dataclass(frozen=True)
class _SyntheticCompleted:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    timeout_seconds: int
    termination_reason: str
    launch_succeeded: bool
    signal_sent: str
    final_state_observed: str
    stdout_received: bool
    stderr_received: bool
    heartbeat_count: int
    heartbeat_interval_seconds: int
    quiet_seconds: int
    last_stdout_at: str
    last_stderr_at: str
    last_artifact_touch_at: str
    observation_mode: str


def _codex_usage_limit_note(stderr: str) -> str:
    if not _CODEX_USAGE_LIMIT_RE.search(stderr):
        return ""
    match = _CODEX_USAGE_LIMIT_RETRY_RE.search(stderr)
    if match:
        return f"codex exec blocked by usage limit; retry_after={match.group(1).strip()}"
    return "codex exec blocked by usage limit"


@dataclass(frozen=True)
class _ExecutionRequest:
    artifact_root: Path
    workspace_root: Path
    run_id: str
    role: str
    routing_report: dict[str, Any]
    scope_freeze: dict[str, Any]
    profile: dict[str, Any]
    routing_report_rel: str
    scope_freeze_rel: str
    proposal_snapshot_rel: str
    repair_context_rel: str
    repair_context: dict[str, Any] | None
    artifacts: _ExecutorArtifacts
    argv: list[str]
    sanitized_argv: list[str]
    prompt_path: Path
    timeout_seconds: int
    context: RuntimeContext


@dataclass(frozen=True)
class PromptMaterializationRequest:
    artifact_root: Path
    workspace_root: Path
    run_id: str
    role: str
    profile: dict[str, Any]
    routing_report: dict[str, Any]
    scope_freeze: dict[str, Any]
    proposal_snapshot_rel: str
    scope_freeze_rel: str
    routing_report_rel: str
    repair_context_rel: str
    repair_context: dict[str, Any] | None
    artifacts: _ExecutorArtifacts
    command_argv: list[str]
    timeout_seconds: int
    context: RuntimeContext


@dataclass(frozen=True)
class ExecutorReportRequest:
    run_id: str
    role: str
    routing_report: dict[str, Any]
    routing_report_rel: str
    scope_freeze_rel: str
    artifacts: _ExecutorArtifacts
    sanitized_argv: list[str]
    completed: object
    summary: _ExecutionSummary
    dependency_preflight: ExecutorDependencyPreflightPayload
    context: RuntimeContext


def _completed_timed_out(completed: object) -> bool:
    value = getattr(completed, "timed_out", False)
    if isinstance(value, bool):
        return value
    return False


def _completed_returncode(completed: object) -> int:
    value = getattr(completed, "returncode", 0)
    if isinstance(value, int):
        return value
    return 0


def _completed_timeout_seconds(completed: object, fallback: int) -> int:
    value = getattr(completed, "timeout_seconds", fallback)
    if isinstance(value, int):
        return value
    return fallback


def _completed_termination_reason(completed: object, *, timed_out: bool) -> str:
    fallback = "timeout" if timed_out else "completed"
    value = getattr(completed, "termination_reason", fallback)
    if value in {"completed", "timeout"}:
        return str(value)
    return fallback


def _completed_launch_succeeded(completed: object) -> bool:
    value = getattr(completed, "launch_succeeded", True)
    return bool(value)


def _completed_signal_sent(completed: object) -> str:
    return str(getattr(completed, "signal_sent", "none")).strip()


def _completed_final_state_observed(completed: object) -> str:
    return str(getattr(completed, "final_state_observed", "")).strip()


def _completed_stdout_received(completed: object) -> bool:
    return bool(getattr(completed, "stdout_received", False))


def _completed_stderr_received(completed: object) -> bool:
    return bool(getattr(completed, "stderr_received", False))


def _completed_int_attr(completed: object, name: str) -> int:
    value = getattr(completed, name, 0)
    if isinstance(value, int):
        return value
    return 0


def _completed_str_attr(completed: object, name: str, default: str = "") -> str:
    value = getattr(completed, name, default)
    if isinstance(value, str):
        return value.strip()
    return default


def _completed_observability(completed: object) -> ExecutorObservabilityPayload:
    return {
        "heartbeat_count": _completed_int_attr(completed, "heartbeat_count"),
        "heartbeat_interval_seconds": _completed_int_attr(completed, "heartbeat_interval_seconds"),
        "quiet_seconds": _completed_int_attr(completed, "quiet_seconds"),
        "last_stdout_at": _completed_str_attr(completed, "last_stdout_at"),
        "last_stderr_at": _completed_str_attr(completed, "last_stderr_at"),
        "last_artifact_touch_at": _completed_str_attr(completed, "last_artifact_touch_at"),
        "observation_mode": _completed_str_attr(completed, "observation_mode", "communicate"),
    }


def load_agent_profile(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ExecutorContractError(f"unable to read agent profile {path.name}: {exc}") from exc
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ExecutorContractError(f"unable to parse agent profile {path.name}: {exc}") from exc


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutorContractError(f"unable to load {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExecutorContractError(f"{label} root must be an object")
    return payload


def _load_optional_json_object(path: Path, *, label: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _load_json_object(path, label=label)


def _dependency_module_payloads(
    status: str,
    *,
    detail: str = "",
) -> list[ExecutorDependencyModulePayload]:
    return [
        {
            "import_name": module,
            "package": package,
            "status": status,
            "version": "",
            "detail": detail,
        }
        for module, package in NON_WORKER_PROJECT_CHECK_MODULES
    ]


def _dependency_preflight_command_payload(python_display: str) -> ExecutorDependencyCommandPayload:
    argv = [python_display, "-c", "<project-dependency-preflight>"] if python_display else []
    return {
        "argv": argv,
        "project_check_lane": PROJECT_CHECK_LANE,
    }


def _dependency_preflight_payload(
    *,
    role_requires_project_check: bool,
    status: str,
    python_path: str,
    python_executable: str,
    python_version: str,
    python_exists: bool,
    required_modules: list[ExecutorDependencyModulePayload],
    returncode: int,
) -> ExecutorDependencyPreflightPayload:
    return {
        "role_requires_project_check": role_requires_project_check,
        "status": status,
        "command": _dependency_preflight_command_payload(python_path),
        "python": {
            "path": python_path,
            "executable": python_executable,
            "version": python_version,
            "exists": python_exists,
        },
        "required_modules": required_modules,
        "returncode": returncode,
    }


def _dependency_preflight_template(
    role: str,
    workspace_root: Path,
    roots: list[Path],
) -> ExecutorDependencyPreflightPayload:
    if role == "worker":
        return _dependency_preflight_payload(
            role_requires_project_check=False,
            status="not_required",
            python_path="",
            python_executable="",
            python_version="",
            python_exists=False,
            required_modules=_dependency_module_payloads("not_checked"),
            returncode=0,
        )
    python_path = workspace_root / ".venv" / "bin" / "python"
    python_display = _sanitize_path_text(str(python_path), roots=roots)
    return _dependency_preflight_payload(
        role_requires_project_check=True,
        status="not_checked",
        python_path=python_display,
        python_executable="",
        python_version="",
        python_exists=python_path.exists(),
        required_modules=_dependency_module_payloads("not_checked"),
        returncode=0,
    )


def _executor_report_template(
    request: PromptMaterializationRequest,
    *,
    sandbox_mode: str,
    sanitized_command_argv: list[str],
    sanitize_roots: list[Path],
) -> dict[str, Any]:
    return {
        "$schema": EXECUTOR_REPORT_SCHEMA,
        "run_id": request.run_id,
        "role": request.role,
        "generated_at": request.context.isoformat_z(),
        "executor": {
            "name": "codex_exec",
            "sandbox_mode": sandbox_mode,
            "model": request.routing_report["routing_decision"]["model"],
            "reasoning_effort": request.routing_report["routing_decision"]["reasoning_effort"],
        },
        "status": "pass",
        "command": {
            "argv": sanitized_command_argv
        },
        "artifacts": {
            "prompt": request.artifacts.prompt_rel,
            "output_last_message": request.artifacts.output_last_message_rel,
            "stdout": request.artifacts.stdout_rel,
            "stderr": request.artifacts.stderr_rel,
            "command_log_summary": request.artifacts.command_log_summary_rel,
            "timeout_failure": None,
        },
        "result": {
            "returncode": 0,
            "timed_out": False,
            "timeout_seconds": request.timeout_seconds,
            "termination_reason": "completed",
            "launch_succeeded": True,
            "signal_sent": "none",
            "final_state_observed": "communicate",
            "stdout_received": True,
            "stderr_received": True,
            "observability": {
                "heartbeat_count": 0,
                "heartbeat_interval_seconds": 0,
                "quiet_seconds": 0,
                "last_stdout_at": "",
                "last_stderr_at": "",
                "last_artifact_touch_at": "",
                "observation_mode": "communicate"
            }
        },
        "diagnostics": {
            "routing_report": request.routing_report_rel,
            "scope_freeze": request.scope_freeze_rel,
            "dependency_preflight": _dependency_preflight_template(
                request.role,
                request.workspace_root,
                sanitize_roots,
            ),
            "notes": []
        }
    }


def _worker_structural_budget_guardrails(role: str) -> str:
    if role != "worker":
        return ""
    return (
        "Worker structural budget guardrails:\n"
        "- The parent run creates `changed-files-manifest.json` and "
        "`structural-complexity-budget.json` after worker execution; do not "
        "generate or require those artifacts inside the worker phase.\n"
        "- Repo-health re-checks structural budget using the actual changed "
        "source and `tests/**` files, and a non-pass result can skip "
        "promotion even when executor roles report pass.\n"
        "- Before editing, inspect the primary target's current shape and "
        "choose a patch that keeps touched files at or below their existing "
        "line, function, and branch footprint when possible.\n"
        "- Keep touched structure bounded: prefer reusing existing helpers, "
        "simplifying adjacent code, and focused assertions over broad "
        "branches, copied fixtures, or large new test blocks.\n"
        "- For structural-complexity repairs, make the first patch a "
        "measured simplification or decomposition slice; for non-structural "
        "fixes, do not add compatibility aliases, broad fallback branches, "
        "or large fixtures unless the proposal explicitly needs them.\n"
        "- If the smallest correct fix must add substantial structure, "
        "explain why in `diagnostics.notes` and include the focused "
        "validation that covers the added behavior.\n"
        "\n"
    )


def _same_session_repair_context_block(
    request: PromptMaterializationRequest,
    *,
    sanitize_roots: list[Path],
) -> str:
    if not request.repair_context:
        return ""
    repair_context = _sanitize_json_strings(request.repair_context, roots=sanitize_roots)
    return (
        "Same-session repair context:\n"
        "- The parent wrapper scheduled this run after a prior parent validation failure.\n"
        "- Treat this as a bounded same-session repair attempt: re-evaluate the candidate "
        "from the supplied evidence and run the full role responsibility, not a worker-only retry.\n"
        f"- repair_context: `{request.repair_context_rel}`\n"
        "```json\n"
        f"{json.dumps(repair_context, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
    )


def _executor_prompt_text(
    request: PromptMaterializationRequest,
    *,
    sandbox_mode: str,
    sanitize_roots: list[Path],
    template: dict[str, Any],
) -> str:
    profile_name = _sanitize_path_text(
        str(request.profile.get("name", request.role)),
        roots=sanitize_roots,
    )
    profile_description = _sanitize_path_text(
        str(request.profile.get("description", "")),
        roots=sanitize_roots,
    )
    developer_instructions = _sanitize_path_text(
        request.profile.get("developer_instructions", "").strip(),
        roots=sanitize_roots,
    )
    workspace_root = _sanitize_path_text(str(request.workspace_root), roots=sanitize_roots)
    scope_freeze = _sanitize_json_strings(request.scope_freeze, roots=sanitize_roots)
    routing_report = _sanitize_json_strings(request.routing_report, roots=sanitize_roots)
    template = _sanitize_json_strings(template, roots=sanitize_roots)
    external_sandbox_note = ""
    if _uses_external_workspace(
        artifact_root=request.artifact_root,
        workspace_root=request.workspace_root,
    ):
        external_sandbox_note = (
            "- This executor is running inside a disposable mechanism workspace copy. "
            "Treat the role sandbox_mode above as the write contract, and rely on the "
            "parent apply guardrails for live-repo mutation.\n"
        )
    structural_budget_guardrails = _worker_structural_budget_guardrails(request.role)
    same_session_repair_context = _same_session_repair_context_block(
        request,
        sanitize_roots=sanitize_roots,
    )
    return f"""You are executing the `{request.role}` role for LLM Wiki vNext.

Role profile:
- name: `{profile_name}`
- description: {profile_description}
- sandbox_mode: `{sandbox_mode}`

Developer instructions:
{developer_instructions}

Run context:
- run_id: `{request.run_id}`
- workspace_root: `{workspace_root}`
- proposal_snapshot: `{request.proposal_snapshot_rel}`
- scope_freeze: `{request.scope_freeze_rel}`
- routing_report: `{request.routing_report_rel}`

Repository write boundary:
- worker may only mutate `ops/**`, `tests/**`, and bounded files required by the selected proposal.
- reviewer, validator, and auditor roles are read-only for source and control files, even when a temp workspace grants write access for caches or replay checks.
- never edit `raw/`, `wiki/`, or non-log `system/` pages.
- do not rewrite unrelated files or expand scope.

{structural_budget_guardrails}Execution environment guidance:
- Required Python focused check lane uses workspace-local `.venv/bin/python`: `{PROJECT_CHECK_LANE}`.
- Use `{PROJECT_FULL_REGRESSION_LANE}` for developer full regression and `{PROJECT_RELEASE_EVIDENCE_LANE}` for release-grade full-suite evidence.
- Do not run bare `python -m pytest` or selectorless `.venv/bin/python -m pytest` when `.venv/bin/python` is present.
- In reviewer, validator, and auditor roles, keep pytest cache-safe with `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider`.
- If dependencies are genuinely absent, report the exact blocked `.venv/bin/python` command and missing dependency surface; do not use network dependency setup as a fallback unless the parent task explicitly asks for environment bootstrap.
{external_sandbox_note}
Repository-required local skills:
- If `AGENTS.md` or `AGENTS.local.md` names a required skill that is absent from the system-provided available skills list, check for a local skill body at `$CODEX_HOME/skills/<skill>/SKILL.md` or `~/.codex/skills/<skill>/SKILL.md`.
- When that local skill body exists and is readable, read and apply it before continuing; do not fail solely because the system available-skills list omitted a readable local required skill.
- If the required local skill body is absent or unreadable, report the exact missing skill path surface as a blocker.

Executor phase boundary:
- Worker mutations are checked by a post-worker repo-health preflight before reviewer, validator, or auditor execution.
- Executor roles still run before final repo-health capture, candidate artifacts, changed-files manifest, behavior delta, final promotion report, and workspace apply.
- Validator/reviewer/auditor roles should not fail only because post-executor artifacts such as `candidate-mechanism-assessment.json`, `candidate-eval.json`, `candidate-lint.json`, `changed-files-manifest.json`, or finalized `promotion-report.json` are not available yet.
- Treat those post-executor artifacts as highest-value next checks unless the current prompt explicitly asks you to validate a completed run directory.

{same_session_repair_context}Scope freeze summary:
```json
{json.dumps(scope_freeze, ensure_ascii=False, indent=2)}
```

Routing summary:
```json
{json.dumps(routing_report, ensure_ascii=False, indent=2)}
```

Final response requirements:
- Return JSON only.
- Match this schema-compatible shape exactly.
- Set `status` to `fail` if you are blocked, timed out, or if reviewer/validator/auditor found a material issue.
- Keep `executor`, `artifacts`, and `result` aligned with the template below.
- Put concise evidence in `diagnostics.notes`.

JSON template:
```json
{json.dumps(template, ensure_ascii=False, indent=2)}
```
"""


def _materialize_prompt(request: PromptMaterializationRequest) -> Path:
    prompt_path = request.artifact_root / request.artifacts.prompt_rel
    sandbox_mode = request.routing_report["routing_decision"]["sandbox_mode"]
    sanitize_roots = [request.artifact_root, request.workspace_root]
    sanitized_command_argv = _sanitize_argv(
        _display_command_argv(request.command_argv),
        roots=sanitize_roots,
    )
    template = _executor_report_template(
        request,
        sandbox_mode=sandbox_mode,
        sanitized_command_argv=sanitized_command_argv,
        sanitize_roots=sanitize_roots,
    )
    prompt_text = _executor_prompt_text(
        request,
        sandbox_mode=sandbox_mode,
        sanitize_roots=sanitize_roots,
        template=template,
    )
    write_output_text(prompt_path, prompt_text)
    return prompt_path


def _load_executor_inputs(
    *,
    artifact_root: Path,
    role: str,
    routing_report_rel: str,
    scope_freeze_rel: str,
    proposal_snapshot_rel: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    routing_path = artifact_root / routing_report_rel
    scope_path = artifact_root / scope_freeze_rel
    proposal_snapshot_path = artifact_root / proposal_snapshot_rel
    profile_path = artifact_root / ".codex" / "agents" / f"{role}.toml"

    routing_report = _load_json_object(routing_path, label=routing_report_rel)
    scope_freeze = _load_json_object(scope_path, label=scope_freeze_rel)
    if not proposal_snapshot_path.exists():
        raise ExecutorContractError(f"missing proposal snapshot: {proposal_snapshot_rel}")
    if not profile_path.exists():
        raise ExecutorContractError(
            f"missing agent profile: {report_path(artifact_root, profile_path)}"
        )
    profile = load_agent_profile(profile_path)
    return routing_report, scope_freeze, profile


def _uses_external_workspace(*, artifact_root: Path, workspace_root: Path) -> bool:
    try:
        return artifact_root.resolve() != workspace_root.resolve()
    except OSError:
        return artifact_root.absolute() != workspace_root.absolute()


def _codex_exec_argv(
    *,
    workspace_root: Path,
    routing_report: dict[str, Any],
    output_last_message_rel: str,
) -> list[str]:
    sandbox_mode = routing_report["routing_decision"]["sandbox_mode"]
    argv = [
        _codex_executable(workspace_root),
        "exec",
        "--cd",
        str(workspace_root),
        "-m",
        routing_report["routing_decision"]["model"],
        "-c",
        f'model_reasoning_effort="{routing_report["routing_decision"]["reasoning_effort"]}"',
        "--output-schema",
        str(workspace_root / EXECUTOR_REPORT_SCHEMA),
        "-o",
        str(workspace_root / output_last_message_rel),
        "-",
    ]
    if sandbox_mode == "workspace-write":
        argv.insert(2, "--full-auto")
        argv.insert(3, "--skip-git-repo-check")
    else:
        argv[2:2] = ["-s", sandbox_mode, "--skip-git-repo-check"]
    return argv


def _executor_artifacts(run_id: str, role: str) -> _ExecutorArtifacts:
    return _ExecutorArtifacts(
        output_last_message_rel=run_rel(run_id, f"{role}-last-message.json"),
        stdout_rel=command_log_trace_rel(run_id, role, "stdout"),
        stderr_rel=command_log_trace_rel(run_id, role, "stderr"),
        raw_stdout_rel=run_rel(run_id, f"{role}.stdout.txt"),
        raw_stderr_rel=run_rel(run_id, f"{role}.stderr.txt"),
        command_log_summary_rel=command_log_summary_rel(run_id),
        prompt_rel=run_rel(run_id, f"{role}-prompt.md"),
    )


def _model_output_path(root: Path, artifacts: _ExecutorArtifacts) -> Path:
    return root / artifacts.output_last_message_rel


def _clear_stale_model_output(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        raise ExecutorContractError(f"model output path is a directory: {path.name}")
    path.unlink()


def _clear_stale_model_outputs(
    *,
    artifact_root: Path,
    workspace_root: Path,
    artifacts: _ExecutorArtifacts,
) -> None:
    workspace_output = _model_output_path(workspace_root, artifacts)
    artifact_output = _model_output_path(artifact_root, artifacts)
    _clear_stale_model_output(workspace_output)
    if not _same_path(workspace_output, artifact_output):
        _clear_stale_model_output(artifact_output)


def _persist_executor_streams(
    *,
    artifact_root: Path,
    run_id: str,
    role: str,
    artifacts: _ExecutorArtifacts,
    completed: object,
    sanitize_roots: list[Path],
    context: RuntimeContext,
    sanitized_argv: list[str],
) -> None:
    stdout = _sanitize_path_text(str(getattr(completed, "stdout", "")), roots=sanitize_roots)
    stderr = _sanitize_path_text(str(getattr(completed, "stderr", "")), roots=sanitize_roots)
    write_output_text(
        artifact_root / artifacts.raw_stdout_rel,
        stdout,
    )
    write_output_text(
        artifact_root / artifacts.raw_stderr_rel,
        stderr,
    )
    write_command_log_summary(
        artifact_root,
        run_id,
        role,
        {
            "stdout": stdout,
            "stderr": stderr,
            "returncode": _completed_returncode(completed),
            "timed_out": _completed_timed_out(completed),
            "timeout_seconds": _completed_timeout_seconds(completed, fallback=0),
            "termination_reason": _completed_termination_reason(
                completed,
                timed_out=_completed_timed_out(completed),
            ),
        },
        raw_paths={
            "stdout": artifacts.raw_stdout_rel,
            "stderr": artifacts.raw_stderr_rel,
        },
        context=context,
        command_argv=sanitized_argv,
    )


def _read_model_output(path: Path) -> _ModelOutputRead:
    if not path.exists() and not path.is_symlink():
        return _ModelOutputRead(
            payload=None,
            status="missing",
            note=f"codex exec completed without model output: {path.name} was not written",
        )
    try:
        path_stat = path.lstat()
    except OSError as exc:
        return _ModelOutputRead(
            payload=None,
            status="invalid_file",
            note=f"codex exec wrote unreadable model output file: {exc}",
        )
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
        return _ModelOutputRead(
            payload=None,
            status="invalid_file",
            note="codex exec wrote invalid model output file: expected a regular file, not a symlink or special file",
        )
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            fd_stat = os.fstat(fd)
            if not stat.S_ISREG(fd_stat.st_mode):
                return _ModelOutputRead(
                    payload=None,
                    status="invalid_file",
                    note="codex exec wrote invalid model output file: expected a regular file, not a symlink or special file",
                )
            with os.fdopen(fd, "rb") as handle:
                fd = -1
                raw_bytes = handle.read()
        finally:
            if fd != -1:
                os.close(fd)
    except OSError as exc:
        return _ModelOutputRead(
            payload=None,
            status="invalid_file",
            note=f"codex exec wrote unreadable model output file: {exc}",
        )
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        return _ModelOutputRead(
            payload=None,
            status="invalid_json",
            note=f"codex exec wrote invalid UTF-8 model output JSON: {exc}",
            raw_bytes=raw_bytes,
        )
    except json.JSONDecodeError as exc:
        return _ModelOutputRead(
            payload=None,
            status="invalid_json",
            note=f"codex exec wrote invalid model output JSON: {exc}",
            raw_bytes=raw_bytes,
        )
    if not isinstance(payload, dict):
        return _ModelOutputRead(
            payload=None,
            status="invalid_root",
            note="codex exec wrote invalid model output: root must be an object",
            raw_bytes=raw_bytes,
        )
    return _ModelOutputRead(payload=payload, status="ok", note="", raw_bytes=raw_bytes)


def _summarize_execution(
    completed: object,
    model_output: _ModelOutputRead,
    *,
    fallback_timeout_seconds: int,
) -> _ExecutionSummary:
    timed_out = _completed_timed_out(completed)
    timeout_seconds = _completed_timeout_seconds(completed, fallback=fallback_timeout_seconds)
    termination_reason = _completed_termination_reason(completed, timed_out=timed_out)
    decision = "ready"
    status = "pass"
    notes: list[str] = []
    returncode = int(getattr(completed, "returncode", 0))
    if returncode != 0:
        status = "fail"
        decision = "blocked"
        if timed_out:
            notes.append(f"codex exec timed out after {timeout_seconds} seconds")
        else:
            notes.append(f"codex exec exited with {returncode}")
        usage_limit_note = _codex_usage_limit_note(str(getattr(completed, "stderr", "")))
        if usage_limit_note:
            notes.append(usage_limit_note)
    elif model_output.payload is None:
        status = "fail"
        decision = "blocked"
        notes.append(model_output.note)
    else:
        if "status" not in model_output.payload:
            status = "fail"
            decision = "blocked"
            notes.append("codex exec model output omitted required status field")
        returned_status = str(model_output.payload.get("status", "")).strip()
        if returned_status != "pass":
            status = "fail"
            decision = "blocked"
        diagnostics = model_output.payload.get("diagnostics", {})
        returned_notes = diagnostics.get("notes", []) if isinstance(diagnostics, dict) else []
        if isinstance(returned_notes, list):
            notes.extend(str(item) for item in returned_notes if str(item).strip())
    return _ExecutionSummary(
        status=status,
        decision=decision,
        notes=notes,
        timed_out=timed_out,
        timeout_seconds=timeout_seconds,
        termination_reason=termination_reason,
    )


def _build_executor_report(request: ExecutorReportRequest) -> ExecutorReportPayload:
    return {
        "$schema": EXECUTOR_REPORT_SCHEMA,
        "run_id": request.run_id,
        "role": request.role,
        "generated_at": request.context.isoformat_z(),
        "executor": {
            "name": "codex_exec",
            "sandbox_mode": request.routing_report["routing_decision"]["sandbox_mode"],
            "model": request.routing_report["routing_decision"]["model"],
            "reasoning_effort": request.routing_report["routing_decision"]["reasoning_effort"],
        },
        "status": request.summary.status,
        "command": {"argv": request.sanitized_argv},
        "artifacts": {
            "prompt": request.artifacts.prompt_rel,
            "output_last_message": request.artifacts.output_last_message_rel,
            "stdout": request.artifacts.stdout_rel,
            "stderr": request.artifacts.stderr_rel,
            "command_log_summary": request.artifacts.command_log_summary_rel,
            "timeout_failure": None,
        },
        "result": {
            "returncode": _completed_returncode(request.completed),
            "timed_out": request.summary.timed_out,
            "timeout_seconds": request.summary.timeout_seconds,
            "termination_reason": request.summary.termination_reason,
            "launch_succeeded": _completed_launch_succeeded(request.completed),
            "signal_sent": _completed_signal_sent(request.completed),
            "final_state_observed": _completed_final_state_observed(request.completed),
            "stdout_received": _completed_stdout_received(request.completed),
            "stderr_received": _completed_stderr_received(request.completed),
            "observability": _completed_observability(request.completed),
        },
        "diagnostics": {
            "routing_report": request.routing_report_rel,
            "scope_freeze": request.scope_freeze_rel,
            "dependency_preflight": request.dependency_preflight,
            "notes": request.summary.notes,
        },
    }


def _attach_timeout_failure(
    *,
    artifact_root: Path,
    report: ExecutorReportPayload,
    artifacts: _ExecutorArtifacts,
    routing_report_rel: str,
    scope_freeze_rel: str,
    sanitized_argv: list[str],
    completed: object,
    summary: _ExecutionSummary,
    context: RuntimeContext,
) -> str | None:
    if not summary.timed_out:
        return None
    run_id = str(report["run_id"])
    role = str(report["role"])
    timeout_failure_rel = write_timeout_failure_artifact(
        artifact_root,
        run_id,
        phase="executor",
        role=role,
        command={"argv": sanitized_argv},
        result={
            "returncode": _completed_returncode(completed),
            "timed_out": summary.timed_out,
            "timeout_seconds": summary.timeout_seconds,
            "termination_reason": summary.termination_reason,
            "launch_succeeded": _completed_launch_succeeded(completed),
            "signal_sent": _completed_signal_sent(completed),
            "final_state_observed": _completed_final_state_observed(completed),
            "stdout_received": _completed_stdout_received(completed),
            "stderr_received": _completed_stderr_received(completed),
        },
        artifacts={
            "prompt": artifacts.prompt_rel,
            "output_last_message": artifacts.output_last_message_rel,
            "stdout": artifacts.stdout_rel,
            "stderr": artifacts.stderr_rel,
            "command_log_summary": artifacts.command_log_summary_rel,
            "routing_report": routing_report_rel,
            "scope_freeze": scope_freeze_rel,
        },
        context=context,
        diagnostics={"notes": summary.notes},
    )
    report["artifacts"]["timeout_failure"] = timeout_failure_rel
    return timeout_failure_rel


def _executor_ledger_event_type(role: str, status: str) -> tuple[str, str | None]:
    if status == "pass":
        return "executor_completed", None
    if role == "reviewer":
        return "review_blocked", "blocked"
    if role == "validator" or role.endswith("auditor"):
        return "validation_blocked", "blocked"
    return "executor_completed", "blocked"


def _write_executor_report_and_ledger(
    *,
    artifact_root: Path,
    run_id: str,
    role: str,
    report: ExecutorReportPayload,
    routing_report_rel: str,
    scope_freeze_rel: str,
    prompt_rel: str,
    timeout_failure_rel: str | None,
    summary: _ExecutionSummary,
    context: RuntimeContext,
) -> None:
    schema = load_schema(artifact_root / EXECUTOR_REPORT_SCHEMA)
    report_rel = run_rel(run_id, f"{role}-executor-report.json")
    write_schema_validated_json(
        artifact_root / report_rel,
        report,
        schema,
        context=f"executor report schema validation failed for {role}",
    )
    event_type, status_value = _executor_ledger_event_type(role, summary.status)
    append_ledger_event(
        artifact_root,
        run_id,
        event_type=event_type,
        summary=f"Executed {role} via codex exec.",
        artifacts=[
            routing_report_rel,
            scope_freeze_rel,
            prompt_rel,
            report_rel,
            *([timeout_failure_rel] if timeout_failure_rel else []),
        ],
        decision=summary.decision if summary.status != "pass" else "ready",
        context=context,
        status=status_value,
    )


def _append_executor_runtime_event(
    *,
    artifact_root: Path,
    run_id: str,
    role: str,
    summary: _ExecutionSummary,
    started_at: float,
    scope_freeze: dict[str, Any],
    context: RuntimeContext,
) -> None:
    append_runtime_event(
        artifact_root,
        context=context,
        component="codex_exec_executor",
        phase="executor",
        decision=summary.decision,
        artifact_path=run_rel(run_id, f"{role}-executor-report.json"),
        duration_ms=round((time.monotonic() - started_at) * 1000),
        run_id=run_id,
        policy_version=_read_policy_version(scope_freeze),
        proposal_id=str(scope_freeze.get("proposal_id", "")).strip(),
        decision_reason="executor_summary_decision",
    )


def build_execution_request(
    *,
    artifact_root: Path,
    workspace_root: Path,
    run_id: str,
    role: str,
    routing_report_rel: str,
    scope_freeze_rel: str,
    proposal_snapshot_rel: str,
    repair_context_rel: str = "",
    context: RuntimeContext,
    timeout_seconds: int,
) -> _ExecutionRequest:
    artifacts = _executor_artifacts(run_id, role)
    routing_report, scope_freeze, profile = _load_executor_inputs(
        artifact_root=artifact_root,
        role=role,
        routing_report_rel=routing_report_rel,
        scope_freeze_rel=scope_freeze_rel,
        proposal_snapshot_rel=proposal_snapshot_rel,
    )
    repair_context = (
        _load_optional_json_object(
            artifact_root / repair_context_rel,
            label=repair_context_rel,
        )
        if repair_context_rel
        else None
    )
    argv = _codex_exec_argv(
        workspace_root=workspace_root,
        routing_report=routing_report,
        output_last_message_rel=artifacts.output_last_message_rel,
    )
    _clear_stale_model_outputs(
        artifact_root=artifact_root,
        workspace_root=workspace_root,
        artifacts=artifacts,
    )
    sanitized_argv = _sanitize_argv(
        _display_command_argv(argv),
        roots=[artifact_root, workspace_root],
    )
    prompt_path = _materialize_prompt(
        PromptMaterializationRequest(
            artifact_root=artifact_root,
            workspace_root=workspace_root,
            run_id=run_id,
            role=role,
            profile=profile,
            routing_report=routing_report,
            scope_freeze=scope_freeze,
            proposal_snapshot_rel=proposal_snapshot_rel,
            scope_freeze_rel=scope_freeze_rel,
            routing_report_rel=routing_report_rel,
            repair_context_rel=repair_context_rel,
            repair_context=repair_context,
            artifacts=artifacts,
            command_argv=argv,
            timeout_seconds=timeout_seconds,
            context=context,
        )
    )
    return _ExecutionRequest(
        artifact_root=artifact_root,
        workspace_root=workspace_root,
        run_id=run_id,
        role=role,
        routing_report=routing_report,
        scope_freeze=scope_freeze,
        profile=profile,
        routing_report_rel=routing_report_rel,
        scope_freeze_rel=scope_freeze_rel,
        proposal_snapshot_rel=proposal_snapshot_rel,
        repair_context_rel=repair_context_rel,
        repair_context=repair_context,
        artifacts=artifacts,
        argv=argv,
        sanitized_argv=sanitized_argv,
        prompt_path=prompt_path,
        timeout_seconds=timeout_seconds,
        context=context,
    )


def _workspace_virtualenv_bin(workspace_root: Path) -> Path | None:
    python_path = _workspace_virtualenv_python(workspace_root)
    if python_path is None:
        return None
    return python_path.parent


def _workspace_virtualenv_python(workspace_root: Path) -> Path | None:
    venv_root = workspace_root / ".venv"
    for rel_path in ("bin/python", "Scripts/python.exe", "Scripts/python"):
        python_path = venv_root / rel_path
        if python_path.exists():
            return python_path
    return None


def _trusted_workspace_python_source(artifact_root: Path) -> Path:
    repo_python = artifact_root / ".venv" / "bin" / "python"
    if repo_python.exists():
        return repo_python
    return Path(sys.executable).resolve()


def _expected_external_workspace_python_shim(artifact_root: Path) -> str:
    source_python = _trusted_workspace_python_source(artifact_root)
    return f"#!/bin/sh\nexec {shlex.quote(str(source_python))} \"$@\"\n"


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left.absolute() == right.absolute()


def _path_without_workspace_virtualenv(workspace_root: Path) -> str:
    path_text = os.environ.get("PATH", "")
    venv_bin = _workspace_virtualenv_bin(workspace_root)
    if venv_bin is None or not path_text:
        return path_text
    entries: list[str] = []
    for entry in path_text.split(os.pathsep):
        if entry and _same_path(Path(entry), venv_bin):
            continue
        entries.append(entry)
    return os.pathsep.join(entries)


def _path_is_inside_workspace(path: Path, workspace_root: Path) -> bool:
    try:
        path.resolve().relative_to(workspace_root.resolve())
        return True
    except (OSError, ValueError):
        try:
            path.absolute().relative_to(workspace_root.absolute())
            return True
        except ValueError:
            return False


def _path_has_workspace_entry(path_text: str, workspace_root: Path) -> bool:
    for entry in path_text.split(os.pathsep):
        if entry in {"", "."}:
            return True
        entry_path = Path(entry)
        if not entry_path.is_absolute():
            return True
        if _path_is_inside_workspace(entry_path, workspace_root):
            return True
    return False


def _workspace_codex_candidate_exists(workspace_root: Path) -> bool:
    venv_bin = _workspace_virtualenv_bin(workspace_root)
    candidates = [workspace_root / name for name in ("codex", "codex.exe", "codex.cmd")]
    if venv_bin is not None:
        candidates.extend(
            venv_bin / name
            for name in ("codex", "codex.exe", "codex.cmd", "codex.ps1", "codex.js")
        )
    return any(path.exists() for path in candidates)


def _codex_executable(workspace_root: Path) -> str:
    path_text = _path_without_workspace_virtualenv(workspace_root)
    if not path_text or _path_has_workspace_entry(path_text, workspace_root):
        if _workspace_codex_candidate_exists(workspace_root):
            raise ExecutorContractError(
                "unable to resolve codex from trusted PATH; refusing to launch a workspace codex"
            )
        raise ExecutorContractError(
            "unable to resolve codex from trusted PATH; refusing workspace-relative fallback"
        )
    resolved = shutil.which("codex", path=path_text)
    if resolved:
        return resolved
    if _workspace_codex_candidate_exists(workspace_root):
        raise ExecutorContractError(
            "unable to resolve codex from trusted PATH; refusing to launch a workspace codex"
        )
    return "codex"


def _execution_env(workspace_root: Path) -> dict[str, str] | None:
    venv_bin = _workspace_virtualenv_bin(workspace_root)
    if venv_bin is None:
        return None
    env = dict(os.environ)
    existing_path = env.get("PATH", "")
    env["PATH"] = (
        str(venv_bin)
        if not existing_path
        else f"{venv_bin}{os.pathsep}{existing_path}"
    )
    env["VIRTUAL_ENV"] = str(workspace_root / ".venv")
    return env


def _project_dependency_check_script() -> str:
    module_pairs = repr(list(NON_WORKER_PROJECT_CHECK_MODULES))
    return (
        "import importlib, importlib.metadata, json, sys\n"
        f"module_pairs = {module_pairs}\n"
        "payload = {\n"
        "    'python': {'executable': sys.executable, 'version': sys.version.split()[0]},\n"
        "    'modules': [],\n"
        "}\n"
        "failed = False\n"
        "for module, package in module_pairs:\n"
        "    item = {'import_name': module, 'package': package, 'status': 'available', 'version': '', 'detail': ''}\n"
        "    try:\n"
        "        importlib.import_module(module)\n"
        "    except Exception as exc:\n"
        "        failed = True\n"
        "        item['status'] = 'missing'\n"
        "        item['detail'] = f'{type(exc).__name__}: {exc}'\n"
        "    else:\n"
        "        try:\n"
        "            item['version'] = importlib.metadata.version(package)\n"
        "        except importlib.metadata.PackageNotFoundError:\n"
        "            item['version'] = 'unknown'\n"
        "    payload['modules'].append(item)\n"
        "print(json.dumps(payload, sort_keys=True))\n"
        "sys.exit(1 if failed else 0)\n"
    )


def _dependency_preflight_from_probe(
    request: _ExecutionRequest,
    *,
    python_path: Path,
    completed: subprocess.CompletedProcess[str],
) -> ExecutorDependencyPreflightPayload:
    roots = [request.artifact_root, request.workspace_root]
    python_display = _sanitize_path_text(str(python_path), roots=roots)
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    probe: dict[str, Any] = {}
    if stdout:
        try:
            loaded = json.loads(stdout)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            probe = loaded
    python_info = probe.get("python", {}) if isinstance(probe.get("python"), dict) else {}
    modules_by_name = {
        str(item.get("import_name", "")).strip(): item
        for item in probe.get("modules", [])
        if isinstance(item, dict)
    } if isinstance(probe.get("modules"), list) else {}
    unstructured_detail = ""
    if not probe and (stdout or stderr):
        unstructured_detail = _sanitize_path_text(
            "\n".join(item for item in (stdout, stderr) if item),
            roots=roots,
        )
    required_modules: list[ExecutorDependencyModulePayload] = []
    for module, package in NON_WORKER_PROJECT_CHECK_MODULES:
        item = modules_by_name.get(module)
        if item is None:
            required_modules.append(
                {
                    "import_name": module,
                    "package": package,
                    "status": "unknown" if completed.returncode == 0 else "missing",
                    "version": "",
                    "detail": unstructured_detail,
                }
            )
            continue
        required_modules.append(
            {
                "import_name": module,
                "package": package,
                "status": str(item.get("status", "unknown")).strip() or "unknown",
                "version": str(item.get("version", "")).strip(),
                "detail": _sanitize_path_text(
                    str(item.get("detail", "")).strip(),
                    roots=roots,
                ),
            }
        )
    return _dependency_preflight_payload(
        role_requires_project_check=True,
        status="pass" if completed.returncode == 0 else "fail",
        python_path=python_display,
        python_executable=_sanitize_path_text(
            str(python_info.get("executable", "")).strip(),
            roots=roots,
        ),
        python_version=str(python_info.get("version", "")).strip(),
        python_exists=True,
        required_modules=required_modules,
        returncode=int(completed.returncode),
    )


def _dependency_preflight_failure_summary(
    request: _ExecutionRequest,
    preflight: ExecutorDependencyPreflightPayload,
) -> _ExecutionSummary | None:
    if preflight.get("status") != "fail":
        return None
    python_display = str(preflight.get("python", {}).get("path", "")).strip()
    required = ", ".join(package for _module, package in NON_WORKER_PROJECT_CHECK_MODULES)
    module_details = []
    for item in preflight.get("required_modules", []):
        if not isinstance(item, dict) or str(item.get("status", "")).strip() == "available":
            continue
        package = str(item.get("package", "")).strip()
        module = str(item.get("import_name", "")).strip()
        detail = str(item.get("detail", "")).strip()
        if detail:
            module_details.append(f"{package} ({module}): {detail}")
    note = (
        f"executor dependency preflight blocked {request.role}: "
        f"{python_display} could not import required project check modules ({required})"
    )
    if module_details:
        note = f"{note}; {'; '.join(module_details)}"
    return _ExecutionSummary(
        status="fail",
        decision="blocked",
        notes=[note],
        timed_out=False,
        timeout_seconds=request.timeout_seconds,
        termination_reason="completed",
    )


def _external_workspace_python_issue(request: _ExecutionRequest, workspace_python: Path) -> str:
    if _same_path(request.workspace_root, request.artifact_root):
        return ""
    try:
        python_stat = workspace_python.lstat()
    except OSError as exc:
        return f"workspace virtualenv python shim is unreadable: {exc}"
    if not stat.S_ISREG(python_stat.st_mode):
        return "workspace virtualenv python shim must be a regular file"
    if not os.access(workspace_python, os.X_OK):
        return "workspace virtualenv python shim is not executable"
    try:
        actual = workspace_python.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"workspace virtualenv python shim is unreadable: {exc}"
    expected = _expected_external_workspace_python_shim(request.artifact_root)
    if actual != expected:
        return "workspace virtualenv python shim does not match the trusted parent interpreter"
    return ""


def _workspace_python_failure(
    *,
    request: _ExecutionRequest,
    workspace_python: Path,
    detail: str,
) -> tuple[ExecutorDependencyPreflightPayload, _ExecutionSummary]:
    roots = [request.artifact_root, request.workspace_root]
    python_display = _sanitize_path_text(str(workspace_python), roots=roots)
    preflight = _dependency_preflight_payload(
        role_requires_project_check=True,
        status="fail",
        python_path=python_display,
        python_executable="",
        python_version="",
        python_exists=True,
        required_modules=_dependency_module_payloads("not_checked", detail=detail),
        returncode=126,
    )
    return (
        preflight,
        _ExecutionSummary(
            status="fail",
            decision="blocked",
            notes=[
                (
                    f"executor dependency preflight blocked {request.role}: "
                    f"{python_display} failed workspace Python trust check; {detail}"
                )
            ],
            timed_out=False,
            timeout_seconds=request.timeout_seconds,
            termination_reason="completed",
        ),
    )


def _non_worker_dependency_preflight(
    request: _ExecutionRequest,
) -> tuple[ExecutorDependencyPreflightPayload, _ExecutionSummary | None]:
    roots = [request.artifact_root, request.workspace_root]
    if request.role == "worker":
        return (
            _dependency_preflight_template(request.role, request.workspace_root, roots),
            None,
        )
    workspace_python = _workspace_virtualenv_python(request.workspace_root)
    if workspace_python is None:
        missing_python = request.workspace_root / ".venv" / "bin" / "python"
        python_display = _sanitize_path_text(str(missing_python), roots=roots)
        preflight = _dependency_preflight_payload(
            role_requires_project_check=True,
            status="fail",
            python_path=python_display,
            python_executable="",
            python_version="",
            python_exists=False,
            required_modules=_dependency_module_payloads(
                "not_checked",
                detail="missing workspace virtualenv python",
            ),
            returncode=127,
        )
        return (
            preflight,
            _ExecutionSummary(
                status="fail",
                decision="blocked",
                notes=[
                    (
                        f"executor dependency preflight blocked {request.role}: "
                        "missing workspace virtualenv python at .venv/bin/python; "
                        "prepare an isolated workspace Python shim before "
                        "reviewer/validator/auditor execution"
                    )
                ],
                timed_out=False,
                timeout_seconds=request.timeout_seconds,
                termination_reason="completed",
            ),
        )

    workspace_python_issue = _external_workspace_python_issue(request, workspace_python)
    if workspace_python_issue:
        return _workspace_python_failure(
            request=request,
            workspace_python=workspace_python,
            detail=workspace_python_issue,
        )

    python_path = Path(sys.executable)
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONPATH", None)
    command = [str(python_path), "-c", _project_dependency_check_script()]
    try:
        completed = subprocess.run(
            command,
            cwd=Path(os.sep),
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        detail = _sanitize_path_text(str(exc), roots=roots)
        python_display = _sanitize_path_text(str(python_path), roots=roots)
        preflight = _dependency_preflight_payload(
            role_requires_project_check=True,
            status="fail",
            python_path=python_display,
            python_executable="",
            python_version="",
            python_exists=True,
            required_modules=_dependency_module_payloads("unknown", detail=detail),
            returncode=1,
        )
        return (
            preflight,
            _ExecutionSummary(
                status="fail",
                decision="blocked",
                notes=[
                    (
                        f"executor dependency preflight blocked {request.role}: "
                        f"{python_display} could not execute required project dependency check; "
                        f"{detail}"
                    )
                ],
                timed_out=False,
                timeout_seconds=request.timeout_seconds,
                termination_reason="completed",
            ),
        )
    preflight = _dependency_preflight_from_probe(
        request,
        python_path=python_path,
        completed=completed,
    )
    return preflight, _dependency_preflight_failure_summary(request, preflight)


def _synthetic_preflight_completed(request: _ExecutionRequest) -> _SyntheticCompleted:
    return _SyntheticCompleted(
        returncode=1,
        stdout="",
        stderr="",
        timed_out=False,
        timeout_seconds=request.timeout_seconds,
        termination_reason="completed",
        launch_succeeded=False,
        signal_sent="none",
        final_state_observed="preflight_blocked",
        stdout_received=False,
        stderr_received=False,
        heartbeat_count=0,
        heartbeat_interval_seconds=0,
        quiet_seconds=0,
        last_stdout_at="",
        last_stderr_at="",
        last_artifact_touch_at="",
        observation_mode="communicate",
    )


def launch_execution(request: _ExecutionRequest) -> object:
    return run_with_timeout(
        request.argv,
        cwd=request.workspace_root,
        input_text=request.prompt_path.read_text(encoding="utf-8"),
        timeout_seconds=request.timeout_seconds,
        env=_execution_env(request.workspace_root),
    )


def capture_execution_artifacts(request: _ExecutionRequest, completed: object) -> _ModelOutputRead:
    _persist_executor_streams(
        artifact_root=request.artifact_root,
        run_id=request.run_id,
        role=request.role,
        artifacts=request.artifacts,
        completed=completed,
        sanitize_roots=[request.artifact_root, request.workspace_root],
        context=request.context,
        sanitized_argv=request.sanitized_argv,
    )
    workspace_output = _model_output_path(request.workspace_root, request.artifacts)
    artifact_output = _model_output_path(request.artifact_root, request.artifacts)
    model_output = _read_model_output(workspace_output)
    if model_output.raw_bytes is not None and not _same_path(workspace_output, artifact_output):
        artifact_output.parent.mkdir(parents=True, exist_ok=True)
        artifact_output.write_bytes(model_output.raw_bytes)
    return model_output


def assess_execution_result(
    completed: object,
    model_output: _ModelOutputRead,
    *,
    timeout_seconds: int,
) -> _ExecutionSummary:
    return _summarize_execution(
        completed,
        model_output,
        fallback_timeout_seconds=timeout_seconds,
    )


def persist_execution_outcome(
    *,
    request: _ExecutionRequest,
    completed: object,
    summary: _ExecutionSummary,
    dependency_preflight: ExecutorDependencyPreflightPayload,
    started_at: float,
    context: RuntimeContext,
) -> ExecutorReportPayload:
    report = _build_executor_report(
        ExecutorReportRequest(
            run_id=request.run_id,
            role=request.role,
            routing_report=request.routing_report,
            routing_report_rel=request.routing_report_rel,
            scope_freeze_rel=request.scope_freeze_rel,
            artifacts=request.artifacts,
            sanitized_argv=request.sanitized_argv,
            completed=completed,
            summary=summary,
            dependency_preflight=dependency_preflight,
            context=context,
        )
    )
    timeout_failure_rel = _attach_timeout_failure(
        artifact_root=request.artifact_root,
        report=report,
        artifacts=request.artifacts,
        routing_report_rel=request.routing_report_rel,
        scope_freeze_rel=request.scope_freeze_rel,
        sanitized_argv=request.sanitized_argv,
        completed=completed,
        summary=summary,
        context=context,
    )
    _write_executor_report_and_ledger(
        artifact_root=request.artifact_root,
        run_id=request.run_id,
        role=request.role,
        report=report,
        routing_report_rel=request.routing_report_rel,
        scope_freeze_rel=request.scope_freeze_rel,
        prompt_rel=request.artifacts.prompt_rel,
        timeout_failure_rel=timeout_failure_rel,
        summary=summary,
        context=context,
    )
    _append_executor_runtime_event(
        artifact_root=request.artifact_root,
        run_id=request.run_id,
        role=request.role,
        summary=summary,
        started_at=started_at,
        scope_freeze=request.scope_freeze,
        context=context,
    )
    return report


def execute_codex_exec_role(
    *,
    artifact_root: Path,
    workspace_root: Path,
    run_id: str,
    role: str,
    routing_report_rel: str,
    scope_freeze_rel: str,
    proposal_snapshot_rel: str,
    repair_context_rel: str = "",
    context: RuntimeContext,
    timeout_seconds: int = DEFAULT_CODEX_EXEC_TIMEOUT_SECONDS,
) -> ExecutorReportPayload:
    started_at = time.monotonic()
    request = build_execution_request(
        artifact_root=artifact_root,
        workspace_root=workspace_root,
        run_id=run_id,
        role=role,
        routing_report_rel=routing_report_rel,
        scope_freeze_rel=scope_freeze_rel,
        proposal_snapshot_rel=proposal_snapshot_rel,
        repair_context_rel=repair_context_rel,
        context=context,
        timeout_seconds=timeout_seconds,
    )
    dependency_preflight, preflight_summary = _non_worker_dependency_preflight(request)
    if preflight_summary is not None:
        preflight_completed = _synthetic_preflight_completed(request)
        _persist_executor_streams(
            artifact_root=request.artifact_root,
            run_id=request.run_id,
            role=request.role,
            artifacts=request.artifacts,
            completed=preflight_completed,
            sanitize_roots=[request.artifact_root, request.workspace_root],
            context=context,
            sanitized_argv=request.sanitized_argv,
        )
        return persist_execution_outcome(
            request=request,
            completed=preflight_completed,
            summary=preflight_summary,
            dependency_preflight=dependency_preflight,
            started_at=started_at,
            context=context,
        )
    integrity_before = (
        _workspace_integrity_digests(request.workspace_root, run_id=request.run_id)
        if role != "worker"
        else None
    )
    completed = launch_execution(request)
    model_output = capture_execution_artifacts(request, completed)
    summary = assess_execution_result(
        completed,
        model_output,
        timeout_seconds=timeout_seconds,
    )
    integrity_after = (
        _workspace_integrity_digests(request.workspace_root, run_id=request.run_id)
        if role != "worker"
        else None
    )
    summary = _apply_non_worker_integrity_guard(
        summary,
        role=role,
        before=integrity_before,
        after=integrity_after,
    )
    return persist_execution_outcome(
        request=request,
        completed=completed,
        summary=summary,
        dependency_preflight=dependency_preflight,
        started_at=started_at,
        context=context,
    )


def _read_policy_version(scope_freeze: dict[str, Any]) -> Any:
    policy = scope_freeze.get("policy")
    if isinstance(policy, dict):
        return policy.get("version", "")
    return ""
