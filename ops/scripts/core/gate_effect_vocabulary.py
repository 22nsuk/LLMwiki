from __future__ import annotations

from collections.abc import Iterable

GATE_EFFECT_NONE = "none"
GATE_EFFECT_ADVISORY = "advisory"
GATE_EFFECT_BLOCKS_PROMOTION = "blocks_promotion"
GATE_EFFECT_BLOCKS_EXECUTION = "blocks_execution"
GATE_EFFECT_OPERATOR_REVIEW_REQUIRED = "operator_review_required"

GATE_EFFECTS = (
    GATE_EFFECT_NONE,
    GATE_EFFECT_ADVISORY,
    GATE_EFFECT_BLOCKS_PROMOTION,
    GATE_EFFECT_BLOCKS_EXECUTION,
    GATE_EFFECT_OPERATOR_REVIEW_REQUIRED,
)

_LEGACY_GATE_EFFECT_ALIASES = {
    "accepted_risk": GATE_EFFECT_ADVISORY,
    "accepted_by_cohort_policy": GATE_EFFECT_ADVISORY,
    "review_required": GATE_EFFECT_OPERATOR_REVIEW_REQUIRED,
    "shadow": GATE_EFFECT_ADVISORY,
}

_GATE_EFFECT_RANK = {
    GATE_EFFECT_NONE: 0,
    GATE_EFFECT_ADVISORY: 1,
    GATE_EFFECT_OPERATOR_REVIEW_REQUIRED: 2,
    GATE_EFFECT_BLOCKS_PROMOTION: 3,
    GATE_EFFECT_BLOCKS_EXECUTION: 4,
}


def canonical_gate_effect(effect: object, *, active_default: str = GATE_EFFECT_BLOCKS_PROMOTION) -> str:
    normalized = str(effect or "").strip()
    if normalized in GATE_EFFECTS:
        return normalized
    if normalized == "active":
        return active_default if active_default in GATE_EFFECTS else GATE_EFFECT_BLOCKS_PROMOTION
    return _LEGACY_GATE_EFFECT_ALIASES.get(normalized, active_default)


def strongest_gate_effect(effects: Iterable[str]) -> str:
    strongest = GATE_EFFECT_NONE
    strongest_rank = _GATE_EFFECT_RANK[strongest]
    for effect in effects:
        if not str(effect or "").strip():
            continue
        normalized = canonical_gate_effect(effect)
        rank = _GATE_EFFECT_RANK.get(normalized)
        if rank is None:
            continue
        if rank > strongest_rank:
            strongest = normalized
            strongest_rank = rank
    return strongest
