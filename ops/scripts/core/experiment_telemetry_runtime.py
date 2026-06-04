from __future__ import annotations

import json
from pathlib import Path

from .artifact_io_runtime import read_json_object, write_vault_schema_validated_json
from .output_runtime import write_output_text
from .run_artifact_envelope_runtime import maybe_embed_run_artifact_envelope
from .runtime_context import RuntimeContext
from .schema_constants_runtime import (
    RUN_LEDGER_SCHEMA_PATH,
    RUN_TELEMETRY_SCHEMA_PATH,
    TIMEOUT_FAILURE_SCHEMA_PATH,
)

RUN_LEDGER_SCHEMA = RUN_LEDGER_SCHEMA_PATH
RUN_TELEMETRY_SCHEMA = RUN_TELEMETRY_SCHEMA_PATH
TIMEOUT_FAILURE_SCHEMA = TIMEOUT_FAILURE_SCHEMA_PATH


def run_rel(run_id: str, filename: str) -> str:
    return f"runs/{run_id}/{filename}"


def _normalize_timeout_result(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    if not any(key in value for key in ("timed_out", "timeout_seconds", "termination_reason")):
        return None
    timeout_seconds = value.get("timeout_seconds", 0)
    if not isinstance(timeout_seconds, int):
        timeout_seconds = 0
    return {
        "timed_out": bool(value.get("timed_out", False)),
        "timeout_seconds": timeout_seconds,
        "termination_reason": str(value.get("termination_reason", "")),
        "launch_succeeded": bool(value.get("launch_succeeded", True)),
        "signal_sent": str(value.get("signal_sent", "none")),
        "final_state_observed": str(value.get("final_state_observed", "")),
        "stdout_received": bool(value.get("stdout_received", False)),
        "stderr_received": bool(value.get("stderr_received", False)),
    }


def load_json(path: Path) -> dict:
    return read_json_object(path)


def load_run_ledger(vault: Path, run_id: str) -> dict:
    return load_json(vault / run_rel(run_id, "run-ledger.json"))


def write_run_ledger(vault: Path, run_id: str, ledger: dict) -> None:
    rel_path = run_rel(run_id, "run-ledger.json")
    ledger = maybe_embed_run_artifact_envelope(
        vault,
        rel_path,
        ledger,
        schema_path=RUN_LEDGER_SCHEMA,
    )
    write_vault_schema_validated_json(
        vault,
        rel_path,
        ledger,
        RUN_LEDGER_SCHEMA,
        context=f"schema validation failed for {rel_path}",
    )


def append_ledger_event(
    vault: Path,
    run_id: str,
    *,
    event_type: str,
    summary: str,
    artifacts: list[str],
    decision: str,
    context: RuntimeContext,
    status: str | None = None,
    decision_event: dict | None = None,
) -> None:
    ledger = load_run_ledger(vault, run_id)
    event: dict[str, object] = {
        "ts": context.isoformat_z(),
        "type": event_type,
        "summary": summary,
        "artifacts": artifacts,
        "decision": decision,
    }
    if decision_event is not None:
        event["decision_event"] = decision_event
    normalized_existing: list[tuple[object, object, object, tuple[object, ...], str]] = []
    for item in ledger.get("events", []):
        if not isinstance(item, dict):
            continue
        item_artifacts = item.get("artifacts", [])
        if not isinstance(item_artifacts, list):
            item_artifacts = []
        normalized_existing.append(
            (
                item.get("type"),
                item.get("summary"),
                item.get("decision"),
                tuple(item_artifacts),
                json.dumps(item.get("decision_event", {}), sort_keys=True),
            )
        )
    key = (
        event_type,
        summary,
        decision,
        tuple(artifacts),
        json.dumps(event.get("decision_event", {}), sort_keys=True),
    )
    if key not in normalized_existing:
        ledger.setdefault("events", []).append(event)
    if status is not None:
        ledger["status"] = status
    write_run_ledger(vault, run_id, ledger)


def write_command_logs(
    vault: Path,
    run_id: str,
    prefix: str,
    result: dict,
) -> list[str]:
    stdout_rel = run_rel(run_id, f"{prefix}.stdout.txt")
    stderr_rel = run_rel(run_id, f"{prefix}.stderr.txt")
    write_output_text(vault / stdout_rel, result["stdout"])
    write_output_text(vault / stderr_rel, result["stderr"])
    return [stdout_rel, stderr_rel]


def timeout_failure_rel(run_id: str, phase: str, *, role: str = "") -> str:
    if phase == "executor":
        prefix = f"{role}-executor" if role else "executor"
    else:
        prefix = phase.replace("_", "-")
    return run_rel(run_id, f"{prefix}-timeout-failure.json")


def write_timeout_failure_artifact(
    vault: Path,
    run_id: str,
    *,
    phase: str,
    command: dict,
    result: dict,
    artifacts: dict,
    context: RuntimeContext,
    role: str = "",
    diagnostics: dict | None = None,
) -> str:
    if not bool(result.get("timed_out", False)):
        raise ValueError("timeout failure artifact requires timed_out=true")
    normalized_result = _normalize_timeout_result(result) or {
        "timed_out": True,
        "timeout_seconds": int(result.get("timeout_seconds", 0)),
        "termination_reason": "timeout",
        "launch_succeeded": bool(result.get("launch_succeeded", True)),
        "signal_sent": str(result.get("signal_sent", "none")),
        "final_state_observed": str(result.get("final_state_observed", "")),
        "stdout_received": bool(result.get("stdout_received", False)),
        "stderr_received": bool(result.get("stderr_received", False)),
    }
    payload = {
        "$schema": TIMEOUT_FAILURE_SCHEMA,
        "run_id": run_id,
        "generated_at": context.isoformat_z(),
        "phase": phase,
        "command": command,
        "result": {
            "returncode": int(result.get("returncode", -1)),
            **normalized_result,
        },
        "artifacts": artifacts,
    }
    if role:
        payload["role"] = role
    if diagnostics is not None:
        payload["diagnostics"] = diagnostics
    rel_path = timeout_failure_rel(run_id, phase, role=role)
    payload = maybe_embed_run_artifact_envelope(
        vault,
        rel_path,
        payload,
        schema_path=TIMEOUT_FAILURE_SCHEMA,
    )
    write_vault_schema_validated_json(
        vault,
        rel_path,
        payload,
        TIMEOUT_FAILURE_SCHEMA,
        context=f"schema validation failed for {rel_path}",
    )
    return rel_path


def write_run_telemetry(vault: Path, run_id: str, payload: dict) -> str:
    normalized_payload = dict(payload)
    normalized_payload.setdefault("$schema", RUN_TELEMETRY_SCHEMA)
    normalized_payload.setdefault("run_id", run_id)
    command_timeouts = normalized_payload.get("command_timeouts")
    if isinstance(command_timeouts, dict):
        normalized_payload["command_timeouts"] = {
            key: normalized
            for key, value in command_timeouts.items()
            if (normalized := _normalize_timeout_result(value)) is not None
        }
    if normalized_payload["run_id"] != run_id:
        raise ValueError(
            "run telemetry payload run_id must match destination run id: "
            f"{normalized_payload['run_id']} != {run_id}"
        )
    rel_path = run_rel(run_id, "run-telemetry.json")
    normalized_payload = maybe_embed_run_artifact_envelope(
        vault,
        rel_path,
        normalized_payload,
        schema_path=RUN_TELEMETRY_SCHEMA,
    )
    write_vault_schema_validated_json(
        vault,
        rel_path,
        normalized_payload,
        RUN_TELEMETRY_SCHEMA,
        context=f"schema validation failed for {rel_path}",
    )
    return rel_path
