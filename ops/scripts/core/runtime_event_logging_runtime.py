from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .output_runtime import write_output_text
from .run_id_runtime import reject_template_placeholder_run_id
from .runtime_context import RuntimeContext
from .schema_constants_runtime import RUNTIME_EVENT_SCHEMA_PATH
from .schema_runtime import load_schema_with_vault_override, validate_or_raise

RUNTIME_EVENT_LOG_DIR = "ops/reports/runtime-events"
RUN_RUNTIME_EVENT_LOG_FILENAME = "runtime-events.jsonl"
RUNTIME_EVENT_SCHEMA = RUNTIME_EVENT_SCHEMA_PATH


@dataclass(frozen=True)
class RuntimeEventRequest:
    context: RuntimeContext
    component: str
    phase: str
    decision: str = ""
    artifact_path: str = ""
    duration_ms: int | None = None
    run_id: str = ""
    session_id: str = ""
    policy_version: Any = ""
    proposal_id: str = ""
    candidate_id: str = ""
    blocker: str = ""
    blocker_kind: str = ""
    decision_reason: str = ""


@dataclass(frozen=True)
class AppendRuntimeEventRequest:
    event: RuntimeEventRequest
    log_rel_path: str | None = None


def _component_slug(component: str) -> str:
    text = component.strip().lower().replace("_", "-").replace(" ", "-")
    slug = "".join(ch for ch in text if ch.isalnum() or ch == "-").strip("-")
    return slug or "runtime"


def runtime_event_log_rel(
    *,
    component: str,
    run_id: str = "",
    session_id: str = "",
) -> str:
    if run_id:
        return f"runs/{run_id}/{RUN_RUNTIME_EVENT_LOG_FILENAME}"
    component_slug = _component_slug(component)
    if session_id:
        return f"{RUNTIME_EVENT_LOG_DIR}/{component_slug}/{session_id}.jsonl"
    return f"{RUNTIME_EVENT_LOG_DIR}/{component_slug}.jsonl"


def _runtime_event_request(
    request: RuntimeEventRequest | None,
    legacy_fields: dict[str, Any],
) -> RuntimeEventRequest:
    if request is not None:
        if legacy_fields:
            raise TypeError("build_runtime_event accepts either a request object or legacy keyword fields")
        return request
    return RuntimeEventRequest(**legacy_fields)


def _append_runtime_event_request(
    request: AppendRuntimeEventRequest | RuntimeEventRequest | None,
    legacy_fields: dict[str, Any],
) -> AppendRuntimeEventRequest:
    log_rel_path = legacy_fields.pop("log_rel_path", None)
    if isinstance(request, AppendRuntimeEventRequest):
        if legacy_fields or log_rel_path is not None:
            raise TypeError("append_runtime_event accepts either an append request object or legacy fields")
        return request
    event_request = _runtime_event_request(request, legacy_fields)
    return AppendRuntimeEventRequest(event=event_request, log_rel_path=log_rel_path)


def _normalized_duration_ms(duration_ms: int | None) -> int | None:
    if duration_ms is None:
        return None
    return max(0, int(duration_ms))


def _runtime_event_payload(request: RuntimeEventRequest) -> dict[str, Any]:
    return {
        "$schema": RUNTIME_EVENT_SCHEMA,
        "ts": request.context.isoformat_z(),
        "run_id": request.run_id,
        "session_id": request.session_id or request.context.session_id,
        "phase": request.phase,
        "component": request.component,
        "decision": request.decision,
        "decision_reason": request.decision_reason,
        "artifact_path": request.artifact_path,
        "duration_ms": _normalized_duration_ms(request.duration_ms),
        "policy_version": request.policy_version,
        "proposal_id": request.proposal_id,
        "candidate_id": request.candidate_id,
        "blocker": request.blocker,
        "blocker_kind": request.blocker_kind,
    }


def build_runtime_event(
    request: RuntimeEventRequest | None = None,
    **legacy_fields: Any,
) -> dict[str, Any]:
    event_request = _runtime_event_request(request, legacy_fields)
    return _runtime_event_payload(event_request)


def append_runtime_event(
    vault: Path,
    request: AppendRuntimeEventRequest | RuntimeEventRequest | None = None,
    **legacy_fields: Any,
) -> str:
    append_request = _append_runtime_event_request(request, legacy_fields)
    event_request = append_request.event
    if event_request.run_id:
        reject_template_placeholder_run_id(event_request.run_id)
    event = build_runtime_event(event_request)
    schema = load_schema_with_vault_override(vault, RUNTIME_EVENT_SCHEMA)
    validate_or_raise(event, schema, context="runtime event schema validation failed")
    rel_path = append_request.log_rel_path or runtime_event_log_rel(
        component=event_request.component,
        run_id=event_request.run_id,
        session_id=event["session_id"],
    )
    path = vault / rel_path
    try:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        if existing and not existing.endswith("\n"):
            existing += "\n"
        line = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
        write_output_text(path, existing + line)
    except OSError:
        return ""
    return rel_path
