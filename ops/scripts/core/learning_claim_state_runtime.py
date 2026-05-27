from __future__ import annotations

from typing import Any

from ops.scripts.learning.learning_claim_model import (
    normalize_evidence_cohort_summary,
)


def confirmed_evidence_summary(
    value: object,
    *,
    blocking_predicate_ids: list[str] | None = None,
) -> dict[str, Any]:
    return normalize_evidence_cohort_summary(
        value,
        blocking_predicate_ids=blocking_predicate_ids,
    )


def confirmed_predicate_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in payload.get("confirmed_predicate_results", [])
        if isinstance(item, dict)
    ]


def confirmed_blocking_predicate_ids(
    predicate_results: list[dict[str, Any]],
    *,
    summary: dict[str, Any] | None = None,
) -> list[str]:
    summary = summary or {}
    explicit_ids = [
        str(item).strip()
        for item in summary.get("confirmed_blocking_predicate_ids", [])
        if str(item).strip()
    ]
    if explicit_ids:
        return explicit_ids
    return [
        str(item.get("id", "")).strip()
        for item in predicate_results
        if str(item.get("id", "")).strip()
        and str(item.get("status", "")).strip() != "pass"
    ]


def improvement_claim_status(summary: dict[str, Any]) -> str:
    return (
        str(
            summary.get(
                "improvement_claim_status",
                summary.get("confirmed_learning_improvement_status", "not_ready"),
            )
        ).strip()
        or "not_ready"
    )


def evidence_cohort_status(
    summary: dict[str, Any],
    confirmed_summary: dict[str, Any],
) -> str:
    return (
        str(
            summary.get(
                "evidence_cohort_status",
                confirmed_summary.get("evidence_cohort_status", "not_ready"),
            )
        ).strip()
        or "not_ready"
    )


def learning_claim_bundle_status(summary: dict[str, Any]) -> str:
    return (
        str(summary.get("learning_claim_evidence_bundle_status", "not_evaluated")).strip()
        or "not_evaluated"
    )


def confirmed_wording_allowed(
    *,
    summary: dict[str, Any],
    claim_level: str,
    confirmed_status: str,
    evidence_cohort_status: str,
    bundle_status: str,
    blocking_predicate_ids: list[str],
) -> bool:
    if "claim_wording_allowed" in summary:
        return bool(summary.get("claim_wording_allowed"))
    return (
        claim_level == "confirmed_learning_improvement"
        and bool(summary.get("confirmed_learning_improvement_allowed"))
        and confirmed_status == "auto_confirmed"
        and evidence_cohort_status == "auto_confirmed"
        and bundle_status == "active"
        and not blocking_predicate_ids
    )
