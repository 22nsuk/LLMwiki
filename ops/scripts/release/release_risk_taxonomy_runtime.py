from __future__ import annotations

from pathlib import Path
from typing import Any

from ops.scripts.artifact_io_runtime import load_optional_json_object_with_diagnostics
from ops.scripts.schema_runtime import load_schema_with_vault_override, validate_or_raise


RELEASE_RISK_TAXONOMY_PATH = "ops/policies/release-risk-taxonomy.json"
RELEASE_RISK_TAXONOMY_SCHEMA_PATH = "ops/schemas/release-risk-taxonomy.schema.json"

CLEAN_LANE_BLOCKS = "blocks_clean_lane"
CLEAN_LANE_DOES_NOT_BLOCK = "does_not_block_clean_lane"
CONDITIONAL_OPERATOR_REVIEW = "operator_review_required"
CONDITIONAL_NOT_APPLICABLE = "not_applicable"
LEARNING_BLOCKS_CLAIM = "blocks_learning_claim"
LEARNING_NOT_APPLICABLE = "not_applicable"
ADVISORY_REVIEW_BACKLOG = "review_backlog"
ADVISORY_NOT_APPLICABLE = "not_applicable"

EFFECT_FIELDS = (
    "clean_lane_effect",
    "conditional_lane_effect",
    "learning_lane_effect",
    "advisory_lifecycle_effect",
)


def release_risk_is_registered(taxonomy: dict[str, Any], risk_code: str) -> bool:
    risks = taxonomy.get("risks")
    return isinstance(risks, dict) and str(risk_code).strip() in risks


def unregistered_release_risk_codes(
    taxonomy: dict[str, Any],
    risks: list[dict[str, Any]],
) -> list[str]:
    codes = {
        str(risk.get("code", "")).strip()
        for risk in risks
        if isinstance(risk, dict) and str(risk.get("code", "")).strip()
    }
    return sorted(code for code in codes if not release_risk_is_registered(taxonomy, code))


def load_release_risk_taxonomy(vault: Path) -> dict[str, Any]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(vault / RELEASE_RISK_TAXONOMY_PATH)
    if diagnostics.get("status") != "ok":
        raise ValueError(
            f"{RELEASE_RISK_TAXONOMY_PATH} could not be loaded: "
            f"{diagnostics.get('message', diagnostics.get('status', 'unknown'))}"
        )
    schema = load_schema_with_vault_override(vault, RELEASE_RISK_TAXONOMY_SCHEMA_PATH)
    validate_or_raise(
        payload,
        schema,
        context=f"{RELEASE_RISK_TAXONOMY_PATH} schema validation failed",
    )
    return payload


def release_risk_effects(taxonomy: dict[str, Any], risk_code: str) -> dict[str, str]:
    risks = taxonomy.get("risks")
    entry = risks.get(risk_code) if isinstance(risks, dict) else None
    if isinstance(entry, dict):
        effects = entry.get("effects")
        if isinstance(effects, dict):
            return {field: str(effects.get(field, "")) for field in EFFECT_FIELDS}
    defaults = taxonomy.get("defaults")
    fallback = defaults.get("unknown_release_risk") if isinstance(defaults, dict) else {}
    if not isinstance(fallback, dict):
        fallback = {}
    return {
        "clean_lane_effect": str(fallback.get("clean_lane_effect", CLEAN_LANE_BLOCKS)),
        "conditional_lane_effect": str(fallback.get("conditional_lane_effect", CONDITIONAL_OPERATOR_REVIEW)),
        "learning_lane_effect": str(fallback.get("learning_lane_effect", LEARNING_NOT_APPLICABLE)),
        "advisory_lifecycle_effect": str(fallback.get("advisory_lifecycle_effect", ADVISORY_NOT_APPLICABLE)),
    }


def annotate_release_risk(issue: dict[str, Any], taxonomy: dict[str, Any]) -> dict[str, Any]:
    annotated = dict(issue)
    effects = release_risk_effects(taxonomy, str(issue.get("code", "")).strip())
    annotated.update(effects)
    return annotated


def clean_lane_blocks_release(risk: dict[str, Any], taxonomy: dict[str, Any] | None = None) -> bool:
    effect = str(risk.get("clean_lane_effect", "")).strip()
    if effect:
        return effect == CLEAN_LANE_BLOCKS
    if taxonomy is None:
        return True
    return release_risk_effects(taxonomy, str(risk.get("code", "")).strip())["clean_lane_effect"] == CLEAN_LANE_BLOCKS
