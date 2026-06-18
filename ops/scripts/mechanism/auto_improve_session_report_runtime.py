from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_freshness_runtime import (
    build_canonical_report_envelope,
    embed_artifact_envelope_metadata,
)
from ops.scripts.core.artifact_io_runtime import (
    read_json_object,
    write_schema_validated_json,
)
from ops.scripts.core.observability_artifacts_runtime import (
    write_routing_provenance_aggregate,
)
from ops.scripts.core.observability_artifacts_shared_runtime import (
    resolve_auto_improve_session_report_rel,
)
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import AUTO_IMPROVE_SESSION_SCHEMA_PATH
from ops.scripts.core.schema_runtime import load_schema_with_vault_override

from .auto_improve_loop_decision_runtime import _ensure_session_loop_state
from .auto_improve_session_runtime import (
    build_session_rollups,
    normalize_session_report,
)

AUTO_IMPROVE_SESSION_SCHEMA = AUTO_IMPROVE_SESSION_SCHEMA_PATH


def _parse_utc_timestamp(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC).replace(microsecond=0)


def _format_utc_timestamp(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _session_generated_at(session: dict, *, context: RuntimeContext) -> str:
    generated = _parse_utc_timestamp(context.isoformat_z())
    observed_times: list[dt.datetime] = []
    for decision in session.get("next_run_decisions", []):
        if not isinstance(decision, dict):
            continue
        observed = _parse_utc_timestamp(decision.get("observed_at"))
        if observed is not None:
            observed_times.append(observed)

    latest_observed = max(observed_times, default=None)
    if latest_observed is not None and (generated is None or latest_observed > generated):
        return _format_utc_timestamp(latest_observed)
    if generated is not None:
        return _format_utc_timestamp(generated)
    return context.isoformat_z()


def _write_session_report(vault: Path, session: dict, *, context: RuntimeContext) -> Path:
    session = normalize_session_report(vault, dict(session))
    _ensure_session_loop_state(session, context=context)
    session["rollups"] = build_session_rollups(vault, session)
    policy, resolved_policy_path = load_policy(vault)
    generated_at = _session_generated_at(session, context=context)
    session["generated_at"] = generated_at
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind="auto_improve_session",
        producer="ops.scripts.auto_improve_runtime",
        source_command="python -m ops.scripts.mechanism.auto_improve_runtime",
        resolved_policy_path=resolved_policy_path,
        schema_path=AUTO_IMPROVE_SESSION_SCHEMA,
        source_paths=[
            "ops/scripts/mechanism/auto_improve_runtime.py",
            "ops/scripts/mechanism/auto_improve_error_runtime.py",
            "ops/scripts/mechanism/auto_improve_learning_preflight_runtime.py",
            "ops/scripts/mechanism/auto_improve_loop_decision_runtime.py",
            "ops/scripts/mechanism/_auto_improve_maintenance_completion_runtime.py",
            "ops/scripts/mechanism/auto_improve_maintenance_decision_runtime.py",
            "ops/scripts/mechanism/auto_improve_promotion_stop_runtime.py",
            "ops/scripts/mechanism/auto_improve_session_report_runtime.py",
            "ops/scripts/mechanism/auto_improve_session_start_runtime.py",
            "ops/scripts/mechanism/auto_improve_session_completion_runtime.py",
            "ops/scripts/mechanism/auto_improve_session_runtime.py",
            "ops/scripts/mechanism/auto_improve_value_runtime.py",
            "ops/scripts/mechanism/auto_improve_next_run_decision_runtime.py",
            "ops/scripts/core/artifact_freshness_runtime.py",
        ],
        text_inputs={
            "session_id": str(session.get("session_id", "")),
            "status": str(session.get("status", "")),
            "policy_version": str(policy.get("version", "")),
        },
    )
    session = embed_artifact_envelope_metadata(session, envelope)
    schema = load_schema_with_vault_override(vault, AUTO_IMPROVE_SESSION_SCHEMA)
    destination = vault / session["path"]
    write_schema_validated_json(
        destination,
        session,
        schema,
        context="auto improve session schema validation failed",
    )
    write_routing_provenance_aggregate(vault, session, context=context)
    return destination


def _load_session_report(vault: Path, session_id: str) -> dict:
    rel_path = resolve_auto_improve_session_report_rel(vault, session_id)
    if not rel_path:
        rel_path = f"ops/reports/auto-improve-sessions/{session_id}.json"
    path = vault / rel_path
    return read_json_object(path)


def refresh_auto_improve_session_report(
    vault: Path,
    *,
    session_id: str,
    policy_path: str | None = None,
    executor_name: str = "codex_exec",
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, _resolved_policy_path = load_policy(vault, policy_path)
    refresh_context = context or RuntimeContext.from_policy(policy, executor_id=executor_name)
    session = _load_session_report(vault, session_id)
    destination = _write_session_report(vault, session, context=refresh_context)
    refreshed = read_json_object(destination)
    return {
        "session_id": session_id,
        "session_report": report_path(vault, destination),
        "generated_at": str(refreshed.get("generated_at", "")).strip(),
        "status": str(refreshed.get("status", "")).strip(),
        "stop_reason": str(refreshed.get("stop_reason", "")).strip(),
        "completion_class": str(refreshed.get("completion_class", "")).strip(),
    }
