from __future__ import annotations

from typing import Any

CURRENTNESS_CLASSIFICATION_CURRENT = "current"
CURRENTNESS_CLASSIFICATION_ARTIFACT_CURRENT_BUT_HEAD_STALE = (
    "artifact_current_but_head_stale"
)
CURRENTNESS_CLASSIFICATION_REUSABLE_CURRENT = "reusable_current"
CURRENTNESS_CLASSIFICATION_RELEASE_AUTHORITATIVE_CURRENT = (
    "release_authoritative_current"
)
CURRENTNESS_CLASSIFICATION_REASON_HEAD_ALIGNED_CURRENT = "head_aligned_current"
CURRENTNESS_CLASSIFICATION_REASON_SOURCE_TREE_FINGERPRINT_MISMATCH = (
    "source_tree_fingerprint_mismatch"
)
CURRENTNESS_CLASSIFICATION_REASON_SOURCE_REVISION_MISMATCH = (
    "source_revision_mismatch"
)
CURRENTNESS_CLASSIFICATION_REASON_DOMAIN_CURRENT_CHECK_FAILED = (
    "domain_current_check_failed"
)
CURRENTNESS_CLASSIFICATION_REASON_DOMAIN_REUSABLE_WITHOUT_HEAD_ALIGNMENT = (
    "domain_reusable_without_head_alignment"
)
CURRENTNESS_CLASSIFICATION_REASON_RELEASE_AUTHORITATIVE_WITHOUT_HEAD_ALIGNMENT = (
    "release_authoritative_without_head_alignment"
)
CURRENTNESS_DOMAIN_MODE_REUSABLE = "reusable"
CURRENTNESS_DOMAIN_MODE_RELEASE_AUTHORITATIVE = "release_authoritative"

_CURRENTNESS_REASON_RELATION = {
    CURRENTNESS_CLASSIFICATION_CURRENT: {
        CURRENTNESS_CLASSIFICATION_REASON_HEAD_ALIGNED_CURRENT,
    },
    CURRENTNESS_CLASSIFICATION_ARTIFACT_CURRENT_BUT_HEAD_STALE: {
        CURRENTNESS_CLASSIFICATION_REASON_SOURCE_TREE_FINGERPRINT_MISMATCH,
        CURRENTNESS_CLASSIFICATION_REASON_SOURCE_REVISION_MISMATCH,
        CURRENTNESS_CLASSIFICATION_REASON_DOMAIN_CURRENT_CHECK_FAILED,
    },
    CURRENTNESS_CLASSIFICATION_REUSABLE_CURRENT: {
        CURRENTNESS_CLASSIFICATION_REASON_DOMAIN_REUSABLE_WITHOUT_HEAD_ALIGNMENT,
    },
    CURRENTNESS_CLASSIFICATION_RELEASE_AUTHORITATIVE_CURRENT: {
        CURRENTNESS_CLASSIFICATION_REASON_RELEASE_AUTHORITATIVE_WITHOUT_HEAD_ALIGNMENT,
    },
}


def currentness_field(payload: dict[str, Any], field: str) -> str:
    currentness = payload.get("currentness")
    if not isinstance(currentness, dict):
        return ""
    return str(currentness.get(field, "")).strip()


def head_alignment(
    *,
    source_revision: str,
    head_revision: str,
    source_tree_fingerprint: str,
    current_source_tree_fingerprint: str,
    domain_current_check_passes: bool,
) -> dict[str, bool]:
    source_revision_text = source_revision.strip()
    head_revision_text = head_revision.strip()
    source_tree_fingerprint_text = source_tree_fingerprint.strip()
    current_source_tree_fingerprint_text = current_source_tree_fingerprint.strip()
    return {
        "source_revision_matches_head": bool(source_revision_text)
        and bool(head_revision_text)
        and source_revision_text == head_revision_text,
        "source_tree_fingerprint_matches": bool(source_tree_fingerprint_text)
        and bool(current_source_tree_fingerprint_text)
        and source_tree_fingerprint_text == current_source_tree_fingerprint_text,
        "domain_current_check_passes": bool(domain_current_check_passes),
    }


def currentness_relation_is_valid(
    *,
    operator_facing_classification: str,
    classification_reason: str,
) -> bool:
    return classification_reason in _CURRENTNESS_REASON_RELATION.get(
        operator_facing_classification,
        set(),
    )


def _artifact_current_but_head_stale_reason(
    *,
    source_revision_matches_head: bool,
    source_tree_fingerprint_matches: bool,
    domain_current_check_passes: bool,
) -> str:
    if not source_tree_fingerprint_matches:
        return CURRENTNESS_CLASSIFICATION_REASON_SOURCE_TREE_FINGERPRINT_MISMATCH
    if not source_revision_matches_head:
        return CURRENTNESS_CLASSIFICATION_REASON_SOURCE_REVISION_MISMATCH
    if not domain_current_check_passes:
        return CURRENTNESS_CLASSIFICATION_REASON_DOMAIN_CURRENT_CHECK_FAILED
    raise ValueError("artifact_current_but_head_stale requires at least one failed alignment predicate")


def currentness_classification_record(
    *,
    report_path: str,
    self_declared_status: str,
    source_revision: str,
    head_revision: str,
    source_tree_fingerprint: str,
    current_source_tree_fingerprint: str,
    domain_current_check_passes: bool,
    domain_mode: str = CURRENTNESS_DOMAIN_MODE_REUSABLE,
) -> dict[str, Any]:
    if domain_mode not in {
        CURRENTNESS_DOMAIN_MODE_REUSABLE,
        CURRENTNESS_DOMAIN_MODE_RELEASE_AUTHORITATIVE,
    }:
        raise ValueError(f"unsupported currentness domain mode: {domain_mode}")
    alignment = head_alignment(
        source_revision=source_revision,
        head_revision=head_revision,
        source_tree_fingerprint=source_tree_fingerprint,
        current_source_tree_fingerprint=current_source_tree_fingerprint,
        domain_current_check_passes=domain_current_check_passes,
    )
    if all(alignment.values()):
        operator_facing_classification = CURRENTNESS_CLASSIFICATION_CURRENT
        classification_reason = CURRENTNESS_CLASSIFICATION_REASON_HEAD_ALIGNED_CURRENT
    elif alignment["domain_current_check_passes"]:
        if domain_mode == CURRENTNESS_DOMAIN_MODE_REUSABLE:
            operator_facing_classification = CURRENTNESS_CLASSIFICATION_REUSABLE_CURRENT
            classification_reason = (
                CURRENTNESS_CLASSIFICATION_REASON_DOMAIN_REUSABLE_WITHOUT_HEAD_ALIGNMENT
            )
        else:
            operator_facing_classification = (
                CURRENTNESS_CLASSIFICATION_RELEASE_AUTHORITATIVE_CURRENT
            )
            classification_reason = (
                CURRENTNESS_CLASSIFICATION_REASON_RELEASE_AUTHORITATIVE_WITHOUT_HEAD_ALIGNMENT
            )
    else:
        operator_facing_classification = (
            CURRENTNESS_CLASSIFICATION_ARTIFACT_CURRENT_BUT_HEAD_STALE
        )
        classification_reason = _artifact_current_but_head_stale_reason(
            source_revision_matches_head=alignment["source_revision_matches_head"],
            source_tree_fingerprint_matches=alignment["source_tree_fingerprint_matches"],
            domain_current_check_passes=alignment["domain_current_check_passes"],
        )
    if not currentness_relation_is_valid(
        operator_facing_classification=operator_facing_classification,
        classification_reason=classification_reason,
    ):
        raise ValueError(
            "invalid currentness classification relation: "
            f"{operator_facing_classification} / {classification_reason}"
        )
    return {
        "report_path": report_path.strip(),
        "self_declared_status": self_declared_status.strip() or "unknown",
        **alignment,
        "operator_facing_classification": operator_facing_classification,
        "classification_reason": classification_reason,
    }


def live_rerun_state(
    component: dict[str, Any], *, current_fingerprint: str
) -> dict[str, str]:
    component_fingerprint = str(component.get("source_tree_fingerprint", "")).strip()
    currentness_status = str(component.get("currentness_status", "")).strip()
    if not component_fingerprint:
        return {
            "status": "not_run",
            "reason": "component has no source_tree_fingerprint",
        }
    if component_fingerprint != current_fingerprint:
        return {
            "status": "not_run",
            "reason": "component fingerprint differs from current source tree",
        }
    if currentness_status != "current":
        return {
            "status": "not_run",
            "reason": f"component currentness_status={currentness_status or 'unknown'}",
        }
    if bool(component.get("ready")):
        return {
            "status": "pass",
            "reason": "checked-in component matches current source tree",
        }
    return {
        "status": "fail",
        "reason": "checked-in component matches current source tree but is not ready",
    }


def components_match_current_source_tree(
    components: list[dict[str, Any]],
    *,
    current_source_tree_fingerprint: str,
) -> bool:
    if not components:
        return False
    for component in components:
        if component.get("load_status") != "ok":
            return False
        if str(component.get("source_tree_fingerprint", "")).strip() != current_source_tree_fingerprint:
            return False
        if str(component.get("currentness_status", "")).strip() != "current":
            return False
    return True
