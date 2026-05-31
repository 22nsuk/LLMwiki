from __future__ import annotations

from typing import Any

ATTACHMENT_STATUS_ATTACHED = "attached"
ATTACHMENT_STATUS_FAILED = "failed"
ATTACHMENT_STATUS_NOT_ATTEMPTED = "not_attempted"
ERROR_KIND_SERVICE = "service"
ERROR_KIND_CONFIGURATION = "configuration"
ERROR_KIND_UNKNOWN = "unknown"

_ERROR_KINDS = {ERROR_KIND_SERVICE, ERROR_KIND_CONFIGURATION, ERROR_KIND_UNKNOWN}


def _error_kind(value: str) -> str:
    normalized = value.strip().lower()
    return normalized if normalized in _ERROR_KINDS else ERROR_KIND_UNKNOWN


def workflow_attachment_result(
    *,
    workflow_run_attached: bool = False,
    combined_status_check_attached: bool = False,
    error_kind: str = "",
    error_message: str = "",
) -> dict[str, Any]:
    """Describe GitHub workflow/status attachment without changing push status."""
    has_error = bool(error_kind.strip() or error_message.strip())
    status = (
        ATTACHMENT_STATUS_FAILED
        if has_error
        else (
            ATTACHMENT_STATUS_ATTACHED
            if workflow_run_attached and combined_status_check_attached
            else ATTACHMENT_STATUS_NOT_ATTEMPTED
        )
    )
    result: dict[str, Any] = {
        "status": status,
        "workflow_run_attached": bool(workflow_run_attached),
        "combined_status_check_attached": bool(combined_status_check_attached),
        "sync_continues": True,
    }
    if has_error:
        result["workflow_attachment_error"] = {
            "kind": _error_kind(error_kind),
            "message": error_message.strip() or "workflow/status attachment failed",
        }
    return result


def remote_sync_governance_record(
    remote_sync_signal: dict[str, Any],
    *,
    workflow_attachment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = dict(remote_sync_signal)
    if workflow_attachment is not None:
        record["workflow_attachment"] = dict(workflow_attachment)
    return record
