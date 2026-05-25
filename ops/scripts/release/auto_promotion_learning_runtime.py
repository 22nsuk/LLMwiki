from __future__ import annotations

from typing import Any

ALLOWED_LEARNING_REVALIDATION_STATUSES = frozenset(
    {
        "current",
        "fresh",
        "metrics_close_candidate",
        "not_due",
        "not_required",
        "pass",
    }
)


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "pass", "allowed"}
    return False


def _dict(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def unaccepted_learning_claim_blockers(
    learning_claim_blockers: list[Any],
    diagnostics: Any,
) -> list[dict[str, Any]]:
    signoff_summary = _dict(_dict(diagnostics).get("learning_signoff_summary"))
    signoff_supported_blocker_id = str(signoff_summary.get("linked_blocker_id", "")).strip()
    signoff_active = bool_value(signoff_summary.get("active", False))
    return [
        blocker
        for blocker in (_dict(item) for item in learning_claim_blockers)
        if not (
            signoff_active
            and signoff_supported_blocker_id
            and str(blocker.get("id", "")).strip() == signoff_supported_blocker_id
        )
    ]
