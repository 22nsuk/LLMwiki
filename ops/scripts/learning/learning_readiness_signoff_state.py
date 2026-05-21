from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from ops.scripts.artifact_io_runtime import load_optional_json_object

from .learning_readiness_vocabulary import LEARNING_REVIEW_REQUIRED_BLOCKER_ID


SIGNOFF_REPORT_REL_PATH = "ops/reports/learning-readiness-signoff.json"
SUPPORTED_BLOCKER_ID = LEARNING_REVIEW_REQUIRED_BLOCKER_ID


def _parse_timestamp(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).replace(microsecond=0)


def _empty_summary(*, path: str, signoff_status: str, summary: str) -> dict[str, Any]:
    return {
        "path": path,
        "signoff_status": signoff_status,
        "active": False,
        "linked_blocker_id": "",
        "accepted_by": "",
        "expires_at": "",
        "risk_owner": "",
        "summary": summary,
    }


def learning_readiness_signoff_summary(
    payload: dict[str, Any],
    *,
    generated_at: str,
    path: str = SIGNOFF_REPORT_REL_PATH,
) -> dict[str, Any]:
    if not payload:
        return _empty_summary(
            path=path,
            signoff_status="missing",
            summary=f"{path} is missing",
        )
    template_marker = str(payload.get("artifact_status", "")).strip() == "template_only" or str(
        payload.get("retention_policy", "")
    ).strip() == "template" or str(payload.get("source_revision", "")).strip() == "template"
    if template_marker:
        return _empty_summary(
            path=path,
            signoff_status="template_only",
            summary=f"{path} is template-only",
        )
    if str(payload.get("artifact_kind", "")).strip() != "learning_readiness_signoff":
        return _empty_summary(
            path=path,
            signoff_status="kind_mismatch",
            summary=f"{path} is not a learning readiness signoff",
        )
    linked_blocker_id = str(payload.get("linked_blocker_id", "")).strip()
    if linked_blocker_id != SUPPORTED_BLOCKER_ID:
        return _empty_summary(
            path=path,
            signoff_status="unsupported_blocker",
            summary=f"{path} does not support linked_blocker_id={linked_blocker_id or '<missing>'}",
        )
    accepted_by = str(payload.get("accepted_by", "")).strip()
    risk_owner = str(payload.get("risk_owner", "")).strip()
    expires_at = str(payload.get("expires_at", "")).strip()
    generated = _parse_timestamp(generated_at)
    expires = _parse_timestamp(expires_at)
    if not accepted_by or not risk_owner or generated is None or expires is None:
        return _empty_summary(
            path=path,
            signoff_status="invalid",
            summary=f"{path} is missing required operator acceptance metadata",
        )
    active = expires > generated
    signoff_status = "active" if active else "expired"
    return {
        "path": path,
        "signoff_status": signoff_status,
        "active": active,
        "linked_blocker_id": linked_blocker_id,
        "accepted_by": accepted_by,
        "expires_at": expires_at,
        "risk_owner": risk_owner,
        "summary": f"{path} {signoff_status} for linked_blocker_id={linked_blocker_id}",
    }


def load_learning_readiness_signoff_summary(
    vault: Path,
    *,
    generated_at: str,
    path: str = SIGNOFF_REPORT_REL_PATH,
) -> dict[str, Any]:
    return learning_readiness_signoff_summary(
        load_optional_json_object(vault / path),
        generated_at=generated_at,
        path=path,
    )
