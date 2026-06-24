from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from .codex_exec_dependency_preflight_runtime import (
    PROJECT_CHECK_LANE,
    dependency_preflight_template,
)
from .codex_exec_execution_types_runtime import (
    ExecutorContractError,
    PromptMaterializationRequest,
)
from .codex_exec_model_output_runtime import scope_freeze_input_digest
from .codex_exec_sanitize_runtime import (
    _display_command_argv,
    _sanitize_argv,
    _sanitize_json_strings,
    _sanitize_path_text,
)
from .output_runtime import write_output_text
from .schema_constants_runtime import EXECUTOR_REPORT_SCHEMA_PATH

EXECUTOR_REPORT_SCHEMA = EXECUTOR_REPORT_SCHEMA_PATH
PROJECT_FULL_REGRESSION_LANE = "make test-all"
PROJECT_RELEASE_EVIDENCE_LANE = "make test-execution-summary-full-current-or-refresh"


def load_agent_profile(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ExecutorContractError(
            f"unable to read agent profile {path.name}: {exc}"
        ) from exc
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ExecutorContractError(
            f"unable to parse agent profile {path.name}: {exc}"
        ) from exc


def uses_external_workspace(*, artifact_root: Path, workspace_root: Path) -> bool:
    try:
        return artifact_root.resolve() != workspace_root.resolve()
    except OSError:
        return artifact_root.absolute() != workspace_root.absolute()


def executor_report_template(
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
        "input_digest": scope_freeze_input_digest(request.scope_freeze),
        "generated_at": request.context.isoformat_z(),
        "executor": {
            "name": "codex_exec",
            "sandbox_mode": sandbox_mode,
            "model": request.routing_report["routing_decision"]["model"],
            "reasoning_effort": request.routing_report["routing_decision"][
                "reasoning_effort"
            ],
        },
        "status": "pass",
        "command": {"argv": sanitized_command_argv},
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
                "observation_mode": "communicate",
            },
        },
        "diagnostics": {
            "routing_report": request.routing_report_rel,
            "scope_freeze": request.scope_freeze_rel,
            "dependency_preflight": dependency_preflight_template(
                request.role, request.workspace_root, sanitize_roots
            ),
            "notes": [],
        },
    }


def worker_structural_budget_guardrails(role: str) -> str:
    if role != "worker":
        return ""
    return "Worker structural budget guardrails:\n- The parent run creates `changed-files-manifest.json` and `structural-complexity-budget.json` after worker execution; do not generate or require those artifacts inside the worker phase.\n- Repo-health re-checks structural budget using the actual changed source and `tests/**` files, and a non-pass result can skip promotion even when executor roles report pass.\n- Before editing, inspect the primary target's current shape and choose a patch that keeps touched files at or below their existing line, function, and branch footprint when possible.\n- Keep touched structure bounded: prefer reusing existing helpers, simplifying adjacent code, and focused assertions over broad branches, copied fixtures, or large new test blocks.\n- For structural-complexity repairs, make the first patch a measured simplification or decomposition slice; for non-structural fixes, do not add compatibility aliases, broad fallback branches, or large fixtures unless the proposal explicitly needs them.\n- If the smallest correct fix must add substantial structure, explain why in `diagnostics.notes` and include the focused validation that covers the added behavior.\n\n"


def same_session_repair_context_block(
    request: PromptMaterializationRequest, *, sanitize_roots: list[Path]
) -> str:
    if not request.repair_context:
        return ""
    repair_context = _sanitize_json_strings(
        request.repair_context, roots=sanitize_roots
    )
    return f"Same-session repair context:\n- The parent wrapper scheduled this run after a prior parent validation failure.\n- Treat this as a bounded same-session repair attempt: re-evaluate the candidate from the supplied evidence and run the full role responsibility, not a worker-only retry.\n- repair_context: `{request.repair_context_rel}`\n```json\n{json.dumps(repair_context, ensure_ascii=False, indent=2)}\n```\n\n"


def executor_prompt_text(
    request: PromptMaterializationRequest,
    *,
    sandbox_mode: str,
    sanitize_roots: list[Path],
    template: dict[str, Any],
) -> str:
    profile_name = _sanitize_path_text(
        str(request.profile.get("name", request.role)), roots=sanitize_roots
    )
    profile_description = _sanitize_path_text(
        str(request.profile.get("description", "")), roots=sanitize_roots
    )
    developer_instructions = _sanitize_path_text(
        request.profile.get("developer_instructions", "").strip(), roots=sanitize_roots
    )
    workspace_root = _sanitize_path_text(
        str(request.workspace_root), roots=sanitize_roots
    )
    scope_freeze = _sanitize_json_strings(request.scope_freeze, roots=sanitize_roots)
    routing_report = _sanitize_json_strings(
        request.routing_report, roots=sanitize_roots
    )
    template = _sanitize_json_strings(template, roots=sanitize_roots)
    external_sandbox_note = ""
    if uses_external_workspace(
        artifact_root=request.artifact_root, workspace_root=request.workspace_root
    ):
        external_sandbox_note = "- This executor is running inside a disposable mechanism workspace copy. Treat the role sandbox_mode above as the write contract, and rely on the parent apply guardrails for live-repo mutation.\n"
    structural_budget_guardrails = worker_structural_budget_guardrails(request.role)
    same_session_repair_context = same_session_repair_context_block(
        request, sanitize_roots=sanitize_roots
    )
    return f"You are executing the `{request.role}` role for LLM Wiki vNext.\n\nRole profile:\n- name: `{profile_name}`\n- description: {profile_description}\n- sandbox_mode: `{sandbox_mode}`\n\nDeveloper instructions:\n{developer_instructions}\n\nRun context:\n- run_id: `{request.run_id}`\n- workspace_root: `{workspace_root}`\n- proposal_snapshot: `{request.proposal_snapshot_rel}`\n- scope_freeze: `{request.scope_freeze_rel}`\n- routing_report: `{request.routing_report_rel}`\n\nRepository write boundary:\n- worker may only mutate `ops/**`, `tests/**`, and bounded files required by the selected proposal.\n- reviewer, validator, and auditor roles are read-only for source and control files, even when a temp workspace grants write access for caches or replay checks.\n- never edit `raw/`, `wiki/`, or non-log `system/` pages.\n- do not rewrite unrelated files or expand scope.\n\n{structural_budget_guardrails}Execution environment guidance:\n- Required Python focused check lane uses workspace-local `.venv/bin/python`: `{PROJECT_CHECK_LANE}`.\n- Use `{PROJECT_FULL_REGRESSION_LANE}` for developer full regression and `{PROJECT_RELEASE_EVIDENCE_LANE}` for release-grade full-suite evidence.\n- Do not run bare `python -m pytest` or selectorless `.venv/bin/python -m pytest` when `.venv/bin/python` is present.\n- In reviewer, validator, and auditor roles, keep pytest cache-safe with `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider`.\n- If dependencies are genuinely absent, report the exact blocked `.venv/bin/python` command and missing dependency surface; do not use network dependency setup as a fallback unless the parent task explicitly asks for environment bootstrap.\n{external_sandbox_note}\nRepository-required local skills:\n- If `AGENTS.md` or `AGENTS.local.md` names a required skill that is absent from the system-provided available skills list, check for a local skill body at `$CODEX_HOME/skills/<skill>/SKILL.md` or `~/.codex/skills/<skill>/SKILL.md`.\n- When that local skill body exists and is readable, read and apply it before continuing; do not fail solely because the system available-skills list omitted a readable local required skill.\n- If the required local skill body is absent or unreadable, report the exact missing skill path surface as a blocker.\n\nExecutor phase boundary:\n- Worker mutations are checked by a post-worker repo-health preflight before reviewer, validator, or auditor execution.\n- Executor roles still run before final repo-health capture, candidate artifacts, changed-files manifest, behavior delta, final promotion report, and workspace apply.\n- Validator/reviewer/auditor roles should not fail only because post-executor artifacts such as `candidate-mechanism-assessment.json`, `candidate-eval.json`, `candidate-lint.json`, `changed-files-manifest.json`, or finalized `promotion-report.json` are not available yet.\n- Treat those post-executor artifacts as highest-value next checks unless the current prompt explicitly asks you to validate a completed run directory.\n\n{same_session_repair_context}Scope freeze summary:\n```json\n{json.dumps(scope_freeze, ensure_ascii=False, indent=2)}\n```\n\nRouting summary:\n```json\n{json.dumps(routing_report, ensure_ascii=False, indent=2)}\n```\n\nFinal response requirements:\n- Return JSON only.\n- Match this schema-compatible shape exactly.\n- Set `status` to `fail` if you are blocked, timed out, or if reviewer/validator/auditor found a material issue.\n- Keep `executor`, `artifacts`, and `result` aligned with the template below.\n- Put concise evidence in `diagnostics.notes`.\n\nJSON template:\n```json\n{json.dumps(template, ensure_ascii=False, indent=2)}\n```\n"


def materialize_prompt(request: PromptMaterializationRequest) -> Path:
    prompt_path = request.artifact_root / request.artifacts.prompt_rel
    sandbox_mode = request.routing_report["routing_decision"]["sandbox_mode"]
    sanitize_roots = [request.artifact_root, request.workspace_root]
    sanitized_command_argv = _sanitize_argv(
        _display_command_argv(request.command_argv), roots=sanitize_roots
    )
    template = executor_report_template(
        request,
        sandbox_mode=sandbox_mode,
        sanitized_command_argv=sanitized_command_argv,
        sanitize_roots=sanitize_roots,
    )
    prompt_text = executor_prompt_text(
        request,
        sandbox_mode=sandbox_mode,
        sanitize_roots=sanitize_roots,
        template=template,
    )
    write_output_text(prompt_path, prompt_text)
    return prompt_path
