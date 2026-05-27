from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .source_tree_fingerprint_runtime import release_source_tree_fingerprint

STATUS_V2_SCHEMA_VERSION = 2
STATUS_V2_MIGRATION_READINESS_STATUS = "active"
STATUS_V2_RECOMMENDED_CONSUMER_FIELDS = [
    "release_authority_status",
    "sealed_release_status",
    "release_authority_vocabulary.blocker_reason_ids",
]
STATUS_V2_AXIS_FIELDS = (
    "release_authority_status",
    "semantic_release_status",
    "sealed_release_status",
)
RELEASE_READINESS_STATE_FALLBACK_VALUES = {
    "clean_pass",
    "conditional_pass",
    "blocked",
}
RELEASE_AUTHORITY_VERIFIED_STATUSES = frozenset({"clean_pass", "conditional_pass"})
MACHINE_RELEASE_NOT_ALLOWED_REASON_ID = "machine_release_not_allowed"


def _string_value(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_value(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _int_value(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def decide_sealed_release_status(
    *,
    batch_integrity_status: str,
    distribution_unsealed_status: str,
    clean_release_ready: bool,
    machine_release_allowed: bool,
    release_readiness_state: str,
) -> str:
    if batch_integrity_status != "pass":
        return "unsealed_artifact_incomplete"
    if distribution_unsealed_status:
        return distribution_unsealed_status
    if (
        clean_release_ready
        and machine_release_allowed
        and release_readiness_state == "clean_pass"
    ):
        return "sealed_clean_pass"
    if release_readiness_state == "conditional_pass":
        return "sealed_conditional_pass"
    return "unsealed_release_blocked"


def decide_legacy_strict_clean_sealed_status(
    *,
    all_required_present: bool,
    all_required_current: bool,
    clean_release_ready: bool,
    machine_release_allowed: bool,
    sealed_release_status: str,
) -> str:
    if (
        all_required_present
        and all_required_current
        and clean_release_ready
        and machine_release_allowed
        and sealed_release_status == "sealed_clean_pass"
    ):
        return "pass"
    return "fail"


def _status_classification(
    *,
    status: str,
    release_authority_status: str,
    sealed_release_status: str,
) -> str:
    if (
        status == "pass"
        and release_authority_status == "clean_pass"
        and sealed_release_status == "sealed_clean_pass"
    ):
        return "strict_clean_and_sealed"
    if release_authority_status == "clean_pass":
        return "semantic_clean_unsealed"
    if (
        release_authority_status == "conditional_pass"
        or sealed_release_status == "sealed_conditional_pass"
    ):
        return "conditional_release"
    return "blocked_or_unknown"


def release_status_v2_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Return release status axes with explicit legacy fallback diagnostics."""

    status_v2 = _dict_value(payload.get("status_v2"))
    status_axes = _dict_value(status_v2.get("status_axes"))
    vocabulary = _dict_value(payload.get("release_authority_vocabulary"))
    fallback_fields: list[str] = []
    axes: dict[str, str] = {}
    for field in STATUS_V2_AXIS_FIELDS:
        value = _string_value(status_axes.get(field))
        if value:
            axes[field] = value
            continue
        legacy_value = _string_value(payload.get(field))
        if legacy_value:
            axes[field] = legacy_value
            fallback_fields.append(field)
        else:
            axes[field] = "unknown"
            fallback_fields.append(field)

    compatibility_status_value = _string_value(status_v2.get("compatibility_status_value"))
    if not compatibility_status_value:
        compatibility_status_value = _string_value(payload.get("status")) or "unknown"
        fallback_fields.append("status")

    if status_v2:
        blocker_reason_ids = _string_list(status_v2.get("blocker_reason_ids"))
    else:
        blocker_reason_ids = _string_list(vocabulary.get("blocker_reason_ids"))
        if blocker_reason_ids:
            fallback_fields.append("release_authority_vocabulary.blocker_reason_ids")

    return {
        "schema_version": status_v2.get("schema_version", 0),
        "status_v2_available": bool(status_v2),
        "compatibility_status_value": compatibility_status_value,
        "release_authority_status": axes["release_authority_status"],
        "semantic_release_status": axes["semantic_release_status"],
        "sealed_release_status": axes["sealed_release_status"],
        "blocker_reason_ids": blocker_reason_ids,
        "used_legacy_fallback_fields": sorted(set(fallback_fields)),
    }


def release_status_v2_view_with_readiness_fallback(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Return v2 axes, accepting legacy release_readiness_state only during migration."""

    view = release_status_v2_view(payload)
    if view["release_authority_status"] != "unknown":
        return view
    legacy_readiness = _string_value(payload.get("release_readiness_state"))
    if legacy_readiness not in RELEASE_READINESS_STATE_FALLBACK_VALUES:
        return view
    return {
        **view,
        "release_authority_status": legacy_readiness,
        "semantic_release_status": legacy_readiness,
        "used_legacy_fallback_fields": sorted(
            {
                *view["used_legacy_fallback_fields"],
                "release_readiness_state",
            }
        ),
    }


def release_status_v2_payload(
    *,
    status: str,
    release_authority_status: str,
    semantic_release_status: str,
    sealed_release_status: str,
    release_authority_vocabulary: dict[str, Any],
    sealed_status_field: str = "sealed_release_status",
    proposed_top_level_status_replacement: str = "sealed_release_status",
    recommended_consumer_fields: list[str] | None = None,
    extra_status_axes: dict[str, str] | None = None,
) -> dict[str, Any]:
    authority_reason_ids = _string_list(
        release_authority_vocabulary.get("authority_reason_ids")
    )
    sealed_reason_ids = _string_list(release_authority_vocabulary.get("sealed_reason_ids"))
    blocker_reason_ids = _string_list(
        release_authority_vocabulary.get("blocker_reason_ids")
    )
    status_classification = _status_classification(
        status=status,
        release_authority_status=release_authority_status,
        sealed_release_status=sealed_release_status,
    )
    status_axes = {
        "release_authority_status": release_authority_status,
        "semantic_release_status": semantic_release_status,
        "sealed_release_status": sealed_release_status,
    }
    status_axes.update(extra_status_axes or {})
    return {
        "schema_version": STATUS_V2_SCHEMA_VERSION,
        "migration_readiness_status": STATUS_V2_MIGRATION_READINESS_STATUS,
        "compatibility_status_field": "status",
        "compatibility_status_value": status,
        "compatibility_status_deprecated": True,
        "compatibility_alias_retention": "one_to_two_releases",
        "status_axes": status_axes,
        "release_authority_status_field": "release_authority_status",
        "release_authority_status_value": release_authority_status,
        "semantic_release_status_field": "semantic_release_status",
        "semantic_release_status_value": semantic_release_status,
        "sealed_status_field": sealed_status_field,
        "sealed_status_value": sealed_release_status,
        "proposed_top_level_status_replacement": proposed_top_level_status_replacement,
        "status_classification": status_classification,
        "authority_reason_ids": authority_reason_ids,
        "sealed_reason_ids": sealed_reason_ids,
        "blocker_reason_ids": blocker_reason_ids,
        "recommended_consumer_fields": recommended_consumer_fields
        or STATUS_V2_RECOMMENDED_CONSUMER_FIELDS,
        "summary": (
            f"status_v2={status_classification}; legacy status={status}; "
            f"release_authority_status={release_authority_status}; "
            f"sealed_release_status={sealed_release_status}; "
            f"blocker_reason_count={len(blocker_reason_ids)}"
        ),
    }


def machine_release_allowed_from_status_view(
    status_view: dict[str, Any],
    *,
    machine_release_not_allowed_reason_id: str = MACHINE_RELEASE_NOT_ALLOWED_REASON_ID,
) -> bool:
    blocker_reason_ids = _string_list(status_view.get("blocker_reason_ids"))
    return (
        str(status_view.get("release_authority_status", "")).strip() == "clean_pass"
        and machine_release_not_allowed_reason_id not in blocker_reason_ids
    )


def clean_required_preflight_passes(
    *,
    status: str,
    preflight_status: str,
    preflight_mode: str,
    distribution_binding_status: str,
    authority_preflight_status: str,
    expected_blocked_preflight: bool,
    clean_required_preflight: bool,
) -> bool:
    return (
        status == "pass"
        and preflight_status == "sealed_clean_pass"
        and preflight_mode == "clean_required"
        and distribution_binding_status == "pass"
        and authority_preflight_status == "clean"
        and not expected_blocked_preflight
        and clean_required_preflight
    )


def authoritative_live_rerun_not_run_count(dashboard: dict[str, Any]) -> int:
    count = 0
    for gate in _list_value(dashboard.get("gates")):
        gate_payload = _dict_value(gate)
        live_rerun_state = _dict_value(gate_payload.get("live_rerun_state"))
        if (
            bool(gate_payload.get("authoritative_for_release"))
            and str(live_rerun_state.get("status", "")).strip() == "not_run"
        ):
            count += 1
    return count


def authoritative_live_rerun_fail_count(dashboard: dict[str, Any]) -> int:
    count = 0
    for gate in _list_value(dashboard.get("gates")):
        gate_payload = _dict_value(gate)
        live_rerun_state = _dict_value(gate_payload.get("live_rerun_state"))
        if (
            bool(gate_payload.get("authoritative_for_release"))
            and str(live_rerun_state.get("status", "")).strip() == "fail"
        ):
            count += 1
    return count


def release_authority_reports_verified(
    *,
    closeout: dict[str, Any],
    dashboard: dict[str, Any],
) -> bool:
    closeout_summary = _dict_value(closeout.get("summary"))
    closeout_status_view = release_status_v2_view_with_readiness_fallback(closeout)
    release_authority_status = str(closeout_status_view["release_authority_status"])
    dashboard_summary = _dict_value(dashboard.get("summary"))
    return (
        closeout.get("status") == "pass"
        and closeout_summary.get("live_make_check_status") == "pass"
        and bool(closeout_status_view["status_v2_available"])
        and release_authority_status in RELEASE_AUTHORITY_VERIFIED_STATUSES
        and authoritative_live_rerun_fail_count(dashboard) == 0
        and authoritative_live_rerun_not_run_count(dashboard) == 0
        and _int_value(dashboard_summary.get("required_input_fail_count")) == 0
    )


def release_artifact_revision(payload: dict[str, Any]) -> str:
    for key in ("source_revision", "commit", "git_revision"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    source = payload.get("source")
    if isinstance(source, dict):
        value = source.get("source_revision") or source.get("revision")
        if isinstance(value, str):
            return value
    return ""


def release_artifact_stale_for_revision(
    payload: dict[str, Any],
    current_revision: str,
) -> bool:
    artifact_revision = release_artifact_revision(payload)
    return bool(artifact_revision and artifact_revision != current_revision)


def current_release_manifest_pass(
    vault: Path,
    rel_path: str,
    artifact_kind: str,
    *,
    source_tree_fingerprint: str | None = None,
) -> bool:
    payload = _read_json(vault / rel_path)
    current_fingerprint = source_tree_fingerprint or release_source_tree_fingerprint(vault)
    return (
        payload.get("status") == "pass"
        and payload.get("artifact_kind") == artifact_kind
        and str(payload.get("source_tree_fingerprint", "")).strip() == current_fingerprint
    )
