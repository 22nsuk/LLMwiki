from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ops.scripts.core.codex_exec_model_output_runtime import scope_freeze_input_digest
from ops.scripts.core.schema_constants_runtime import EXECUTOR_REPORT_SCHEMA_PATH

DEFAULT_SCOPE_FREEZE_REL = "runs/run-executor/scope-freeze.json"
DEFAULT_GENERATED_AT = "2026-04-15T00:00:00Z"


def _routing_report_rel(run_id: str, role: str) -> str:
    return f"runs/{run_id}/subagent-routing.{role}.json"


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"expected JSON object at {path}")
    return payload


def build_valid_model_output_payload(
    vault: Path,
    *,
    run_id: str,
    role: str,
    notes: list[str],
    scope_freeze_rel: str = DEFAULT_SCOPE_FREEZE_REL,
    routing_report_rel: str | None = None,
    generated_at: str = DEFAULT_GENERATED_AT,
    status: str = "pass",
) -> dict[str, Any]:
    routing_rel = routing_report_rel or _routing_report_rel(run_id, role)
    routing_report = _load_json_object(vault / routing_rel)
    scope_freeze = _load_json_object(vault / scope_freeze_rel)
    routing_decision = routing_report["routing_decision"]
    artifacts_root = f"runs/{run_id}"
    return {
        "$schema": EXECUTOR_REPORT_SCHEMA_PATH,
        "run_id": run_id,
        "role": role,
        "input_digest": scope_freeze_input_digest(scope_freeze),
        "generated_at": generated_at,
        "executor": {
            "name": "codex_exec",
            "sandbox_mode": routing_decision["sandbox_mode"],
            "model": routing_decision["model"],
            "reasoning_effort": routing_decision["reasoning_effort"],
        },
        "status": status,
        "command": {"argv": ["codex", "exec", "-"]},
        "artifacts": {
            "prompt": f"{artifacts_root}/{role}-prompt.md",
            "output_last_message": f"{artifacts_root}/{role}-last-message.json",
            "stdout": f"{artifacts_root}/{role}.stdout-trace.txt",
            "stderr": f"{artifacts_root}/{role}.stderr-trace.txt",
            "command_log_summary": f"{artifacts_root}/{role}-command-log-summary.json",
            "timeout_failure": None,
        },
        "result": {
            "returncode": 0,
            "timed_out": False,
            "timeout_seconds": 1800,
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
            "routing_report": routing_rel,
            "scope_freeze": scope_freeze_rel,
            "dependency_preflight": {
                "role_requires_project_check": role != "worker",
                "status": "not_required" if role == "worker" else "not_checked",
                "command": {
                    "argv": [],
                    "project_check_lane": (
                        "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest "
                        "-p no:cacheprovider <focused-selector>"
                    ),
                },
                "python": {
                    "path": "",
                    "executable": "",
                    "version": "",
                    "exists": False,
                },
                "required_modules": [],
                "returncode": 0,
            },
            "notes": notes,
        },
    }


def write_valid_model_output(
    path: Path,
    vault: Path,
    *,
    run_id: str,
    role: str,
    notes: list[str],
    scope_freeze_rel: str = DEFAULT_SCOPE_FREEZE_REL,
    routing_report_rel: str | None = None,
    generated_at: str = DEFAULT_GENERATED_AT,
    status: str = "pass",
) -> None:
    payload = build_valid_model_output_payload(
        vault,
        run_id=run_id,
        role=role,
        notes=notes,
        scope_freeze_rel=scope_freeze_rel,
        routing_report_rel=routing_report_rel,
        generated_at=generated_at,
        status=status,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
