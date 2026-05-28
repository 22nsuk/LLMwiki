from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ops.scripts.gate_effect_vocabulary import (
    GATE_EFFECT_BLOCKS_PROMOTION,
    canonical_gate_effect,
)


def release_risk_identity(
    risk: dict[str, Any],
    *,
    include_linked_blocker: bool = False,
    separator: str = ":",
) -> str:
    source = str(risk.get("source", "")).strip()
    code = str(risk.get("code", "")).strip()
    parts = [source, code]
    if include_linked_blocker:
        acceptance = risk.get("risk_acceptance")
        if isinstance(acceptance, dict):
            linked = str(acceptance.get("linked_blocker_id", "")).strip()
            if linked:
                parts.append(linked)
    return separator.join(parts)


def release_risk_blocks_clean_lane(
    risk: dict[str, Any],
    *,
    learning_review_blocker_id: str,
    learning_signoff_path: str,
    policy_risk_accepted_by: str,
) -> bool:
    acceptance = risk.get("risk_acceptance")
    if not isinstance(acceptance, dict):
        return True
    code = str(risk.get("code", "")).strip()
    acceptance_source = str(acceptance.get("acceptance_source", "")).strip()
    accepted_by = str(acceptance.get("accepted_by", "")).strip()
    if code == learning_review_blocker_id and acceptance_source == learning_signoff_path:
        return False
    return accepted_by in {policy_risk_accepted_by, "test_deselection_policy"} or not accepted_by


def release_risk_with_effects(
    risk: dict[str, Any],
    effects: Mapping[str, object],
) -> dict[str, Any]:
    enriched = dict(risk)
    for field, value in effects.items():
        enriched.setdefault(field, value)
    return enriched


def release_risk_list(
    payload: dict[str, Any],
    key: str,
    effect_lookup: Callable[[dict[str, Any]], Mapping[str, object]],
) -> list[dict[str, Any]]:
    values = payload.get(key, [])
    values = values if isinstance(values, list) else []
    return [
        release_risk_with_effects(risk, effect_lookup(risk))
        for risk in values
        if isinstance(risk, dict)
    ]


def release_blocker_entry(
    risk: dict[str, Any],
    *,
    generated_at: str,
    advisory_lifecycle_assessment: Callable[..., Mapping[str, object]],
    clean_lane_effect_default: str,
) -> dict[str, Any]:
    acceptance = risk.get("risk_acceptance", {})
    if not isinstance(acceptance, dict):
        acceptance = {}
    effects = {
        "clean_lane_effect": str(risk.get("clean_lane_effect", clean_lane_effect_default)).strip()
        or clean_lane_effect_default,
        "conditional_lane_effect": str(risk.get("conditional_lane_effect", "operator_review_required")).strip()
        or "operator_review_required",
        "learning_lane_effect": str(risk.get("learning_lane_effect", "not_applicable")).strip()
        or "not_applicable",
        "advisory_lifecycle_effect": str(risk.get("advisory_lifecycle_effect", "not_applicable")).strip()
        or "not_applicable",
    }
    required_evidence = [
        str(item).strip()
        for item in risk.get("required_evidence", [])
        if str(item).strip()
    ]
    return {
        "id": release_risk_identity(risk),
        "code": str(risk.get("code", "")).strip(),
        "source": str(risk.get("source", "")).strip(),
        "source_path": str(risk.get("source_path", "")).strip(),
        "severity": str(risk.get("severity", "")).strip(),
        "gate_effect": canonical_gate_effect(
            risk.get("gate_effect"),
            active_default=GATE_EFFECT_BLOCKS_PROMOTION,
        ),
        **effects,
        "message": str(risk.get("message", "")).strip(),
        "required_evidence": required_evidence,
        "risk_owner": str(acceptance.get("risk_owner", "")).strip(),
        "expires_at": str(acceptance.get("expires_at", "")).strip(),
        "acceptance_source": str(acceptance.get("acceptance_source", "")).strip(),
        "closure_action": str(acceptance.get("revalidation_condition", "")).strip()
        or (required_evidence[0] if required_evidence else "Resolve this blocker before relying on the affected lane."),
        "rollback_trigger": str(acceptance.get("rollback_trigger", "")).strip(),
        **dict(advisory_lifecycle_assessment(risk, generated_at=generated_at)),
    }
