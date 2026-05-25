"""Advisory accepted-risk lifecycle helpers."""
from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Any

from .release_risk_taxonomy_runtime import ADVISORY_REVIEW_BACKLOG

ADVISORY_LIFECYCLE_ACTIVE = "active"
ADVISORY_LIFECYCLE_EXPIRED = "expired"
ADVISORY_LIFECYCLE_METADATA_MISSING = "metadata_missing"
ADVISORY_LIFECYCLE_NOT_APPLICABLE = "not_applicable"


def _parse_iso_z(value: str) -> dt.datetime | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def advisory_lifecycle_assessment(
    risk: Mapping[str, Any],
    *,
    generated_at: str,
) -> dict[str, Any]:
    """Return machine lifecycle state for an advisory accepted risk."""
    if str(risk.get("advisory_lifecycle_effect", "")).strip() != ADVISORY_REVIEW_BACKLOG:
        return {
            "lifecycle_status": ADVISORY_LIFECYCLE_NOT_APPLICABLE,
            "lifecycle_issues": [],
            "seconds_until_expiry": None,
        }

    acceptance = risk.get("risk_acceptance")
    acceptance = acceptance if isinstance(acceptance, Mapping) else {}
    metadata = {
        "risk_owner": str(acceptance.get("risk_owner", "")).strip(),
        "expires_at": str(acceptance.get("expires_at", "")).strip(),
        "closure_action": str(acceptance.get("revalidation_condition", "")).strip(),
        "rollback_trigger": str(acceptance.get("rollback_trigger", "")).strip(),
    }
    issues = [
        f"missing_{field}"
        for field, value in metadata.items()
        if not value
    ]
    generated_at_dt = _parse_iso_z(generated_at)
    expires_at_dt = _parse_iso_z(metadata["expires_at"])
    if metadata["expires_at"] and expires_at_dt is None:
        issues.append("invalid_expires_at")
    if generated_at_dt is None:
        issues.append("invalid_generated_at")

    seconds_until_expiry = (
        int((expires_at_dt - generated_at_dt).total_seconds())
        if expires_at_dt is not None and generated_at_dt is not None
        else None
    )
    if issues:
        lifecycle_status = ADVISORY_LIFECYCLE_METADATA_MISSING
    elif seconds_until_expiry is not None and seconds_until_expiry <= 0:
        lifecycle_status = ADVISORY_LIFECYCLE_EXPIRED
    else:
        lifecycle_status = ADVISORY_LIFECYCLE_ACTIVE

    return {
        "lifecycle_status": lifecycle_status,
        "lifecycle_issues": issues,
        "seconds_until_expiry": seconds_until_expiry,
    }


def advisory_lifecycle_summary(entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    expired_count = sum(
        1
        for entry in entries
        if str(entry.get("lifecycle_status", "")) == ADVISORY_LIFECYCLE_EXPIRED
    )
    missing_count = sum(
        1
        for entry in entries
        if str(entry.get("lifecycle_status", "")) == ADVISORY_LIFECYCLE_METADATA_MISSING
    )
    active_count = sum(
        1
        for entry in entries
        if str(entry.get("lifecycle_status", "")) == ADVISORY_LIFECYCLE_ACTIVE
    )
    if expired_count:
        status = ADVISORY_LIFECYCLE_EXPIRED
    elif missing_count:
        status = ADVISORY_LIFECYCLE_METADATA_MISSING
    elif active_count:
        status = ADVISORY_LIFECYCLE_ACTIVE
    else:
        status = "clear"
    return {
        "advisory_backlog_status": status,
        "advisory_backlog_active_count": active_count,
        "advisory_backlog_expired_count": expired_count,
        "advisory_backlog_missing_lifecycle_count": missing_count,
    }
