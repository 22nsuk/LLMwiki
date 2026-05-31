from __future__ import annotations

import datetime as dt
from typing import Any

from ops.scripts.core.release_risk_state_runtime import release_risk_identity
from ops.scripts.gate_effect_vocabulary import (
    GATE_EFFECT_BLOCKS_PROMOTION,
    GATE_EFFECT_OPERATOR_REVIEW_REQUIRED,
    canonical_gate_effect,
)

from .release_risk_taxonomy_runtime import (
    ADVISORY_REVIEW_BACKLOG,
    CLEAN_LANE_BLOCKS,
    CONDITIONAL_OPERATOR_REVIEW,
    LEARNING_BLOCKS_CLAIM,
    RELEASE_RISK_TAXONOMY_PATH,
    annotate_release_risk,
    unregistered_release_risk_codes,
)


POLICY_RISK_ACCEPTED_BY = "release_closeout_policy"
POLICY_RISK_ACCEPTANCE_DAYS = 7
LEARNING_SIGNOFF_PATH = "ops/reports/learning-readiness-signoff.json"
TAXONOMY_COVERAGE_BLOCKER_ID = "release_risk_taxonomy_unregistered_code"
COHERENCE_SOURCE = "source_tree_coherence"

POLICY_ACCEPTED_RISK_METADATA = {
    "raw_registry_preflight_warnings": {
        "risk_owner": "runtime-maintainer",
        "revalidation_condition": "Rerun registry-preflight before the next release closeout.",
        "rollback_trigger": "Treat raw registry warnings as blockers if they become fail-level drift.",
    },
    "artifact_freshness_attention": {
        "risk_owner": "runtime-maintainer",
        "revalidation_condition": "Rerun artifact-freshness before the next release closeout.",
        "rollback_trigger": "Treat artifact freshness attention as a blocker if it becomes fail-level debt.",
    },
    "artifact_freshness_stable_contract_debt_advisory": {
        "risk_owner": "runtime-maintainer",
        "revalidation_condition": "Rerun artifact-freshness before the next release closeout.",
        "rollback_trigger": (
            "Treat stable artifact contract debt as a blocker if it becomes operational "
            "or fail-level debt."
        ),
    },
    "generated_index_archive_advisory": {
        "risk_owner": "runtime-maintainer",
        "revalidation_condition": "Rerun generated-artifact-index before the next release closeout.",
        "rollback_trigger": "Treat generated artifact index advisory debt as a blocker if current artifacts go missing.",
    },
    "source_tree_coherence_attention": {
        "risk_owner": "runtime-maintainer",
        "revalidation_condition": "Rerun release evidence in one ordered closeout chain before release signoff.",
        "rollback_trigger": "Treat source tree coherence attention as a blocker if component fingerprints are missing.",
    },
    "external_report_strict_unavailable": {
        "risk_owner": "runtime-maintainer",
        "revalidation_condition": "Rerun the sealed closeout lane with a current distribution ZIP before external review signoff.",
        "rollback_trigger": "Treat missing strict external report provenance as a blocker in sealed release lanes.",
    },
}


def _parse_iso_z(value: str) -> dt.datetime | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _format_iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _expires_after(generated_at: str, *, days: int) -> str:
    generated = _parse_iso_z(generated_at)
    if generated is None:
        return ""
    return _format_iso_z(generated + dt.timedelta(days=days))


def release_closeout_issue(
    *,
    source: str,
    source_path: str,
    code: str,
    message: str,
    severity: str = "blocker",
    gate_effect: str = GATE_EFFECT_BLOCKS_PROMOTION,
    required_evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "source_path": source_path,
        "code": code,
        "severity": severity,
        "gate_effect": canonical_gate_effect(
            gate_effect,
            active_default=GATE_EFFECT_BLOCKS_PROMOTION,
        ),
        "message": message,
        "required_evidence": required_evidence or [],
    }


def policy_risk_acceptance(issue: dict[str, Any], *, generated_at: str) -> dict[str, Any]:
    code = str(issue.get("code", "")).strip()
    metadata = POLICY_ACCEPTED_RISK_METADATA.get(
        code,
        {
            "risk_owner": str(issue.get("source", "runtime-maintainer")).strip()
            or "runtime-maintainer",
            "revalidation_condition": "Rerun the source report before the next release closeout.",
            "rollback_trigger": "Treat this accepted risk as a blocker if the source report escalates it.",
        },
    )
    return {
        "accepted_by": POLICY_RISK_ACCEPTED_BY,
        "accepted_at": generated_at,
        "expires_at": _expires_after(generated_at, days=POLICY_RISK_ACCEPTANCE_DAYS),
        "risk_owner": metadata["risk_owner"],
        "revalidation_condition": metadata["revalidation_condition"],
        "rollback_trigger": metadata["rollback_trigger"],
        "acceptance_source": "ops/scripts/release_closeout_summary.py",
        "linked_blocker_id": "",
    }


def risk_acceptance_is_active(acceptance: dict[str, Any], *, generated_at: str) -> bool:
    expires_at = _parse_iso_z(str(acceptance.get("expires_at", "")).strip())
    closeout_at = _parse_iso_z(generated_at)
    return expires_at is not None and closeout_at is not None and expires_at > closeout_at


def finalize_accepted_risks(
    accepted_risks: list[dict[str, Any]],
    *,
    generated_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blockers: list[dict[str, Any]] = []
    finalized: list[dict[str, Any]] = []
    for risk in accepted_risks:
        accepted = dict(risk)
        if "risk_acceptance" not in accepted:
            accepted["risk_acceptance"] = policy_risk_acceptance(
                accepted,
                generated_at=generated_at,
            )
        acceptance = accepted.get("risk_acceptance")
        if isinstance(acceptance, dict) and risk_acceptance_is_active(
            acceptance,
            generated_at=generated_at,
        ):
            finalized.append(accepted)
            continue
        blocker = dict(accepted)
        blocker.pop("risk_acceptance", None)
        blocker["severity"] = "blocker"
        blocker["gate_effect"] = GATE_EFFECT_OPERATOR_REVIEW_REQUIRED
        blocker["message"] = f"{blocker['message']} Accepted risk metadata is missing or expired."
        evidence = list(blocker.get("required_evidence", []))
        evidence.append("Refresh or replace the risk acceptance metadata before release closeout.")
        blocker["required_evidence"] = evidence
        blockers.append(blocker)
    return blockers, finalized


def risk_identity(risk: dict[str, Any]) -> str:
    return release_risk_identity(
        risk,
        include_linked_blocker=True,
        separator="::",
    )


def risk_delta(previous_report: dict[str, Any], accepted_risks: list[dict[str, Any]]) -> dict[str, Any]:
    previous_risks = previous_report.get("accepted_risks")
    if not isinstance(previous_risks, list):
        return {
            "status": "no_previous_report",
            "previous_report_generated_at": "",
            "added_count": len(accepted_risks),
            "removed_count": 0,
            "unchanged_count": 0,
            "added": sorted(risk_identity(risk) for risk in accepted_risks),
            "removed": [],
            "unchanged": [],
            "summary": "No previous closeout accepted-risk set was available for delta comparison.",
        }
    previous = {risk_identity(risk) for risk in previous_risks if isinstance(risk, dict)}
    current = {risk_identity(risk) for risk in accepted_risks}
    added = sorted(current - previous)
    removed = sorted(previous - current)
    unchanged = sorted(current & previous)
    status = "changed" if added or removed else "unchanged"
    return {
        "status": status,
        "previous_report_generated_at": str(previous_report.get("generated_at", "")).strip(),
        "added_count": len(added),
        "removed_count": len(removed),
        "unchanged_count": len(unchanged),
        "added": added,
        "removed": removed,
        "unchanged": unchanged,
        "summary": (
            f"accepted_risk_delta status={status}; added={len(added)}; "
            f"removed={len(removed)}; unchanged={len(unchanged)}"
        ),
    }


def accepted_risk_count_by_scope(accepted_risks: list[dict[str, Any]]) -> dict[str, int]:
    def family_count_for_effect(field: str, effect: str) -> int:
        return len(
            {
                risk_identity(risk)
                for risk in accepted_risks
                if str(risk.get(field, "")).strip() == effect
            }
        )

    counts = {
        "total": len(accepted_risks),
        "policy": 0,
        "test_deselection_policy": 0,
        "operator_signoff": 0,
        "upstream_report": 0,
        "instances": len(accepted_risks),
        "families": len({risk_identity(risk) for risk in accepted_risks}),
        "release_blocking_family_count": 0,
        "advisory_only_family_count": 0,
        "clean_lane_blocking_family_count": 0,
        "conditional_operator_review_family_count": 0,
        "learning_claim_blocking_family_count": 0,
        "advisory_lifecycle_family_count": 0,
    }
    for risk in accepted_risks:
        acceptance = risk.get("risk_acceptance")
        if not isinstance(acceptance, dict):
            counts["upstream_report"] += 1
            continue
        accepted_by = str(acceptance.get("accepted_by", "")).strip()
        acceptance_source = str(acceptance.get("acceptance_source", "")).strip()
        if acceptance_source == LEARNING_SIGNOFF_PATH:
            counts["operator_signoff"] += 1
        elif accepted_by == "test_deselection_policy":
            counts["test_deselection_policy"] += 1
        elif accepted_by == POLICY_RISK_ACCEPTED_BY:
            counts["policy"] += 1
        else:
            counts["upstream_report"] += 1
    release_blocking_family_count = family_count_for_effect("clean_lane_effect", CLEAN_LANE_BLOCKS)
    advisory_only_family_count = len(
        {
            risk_identity(risk)
            for risk in accepted_risks
            if str(risk.get("clean_lane_effect", "")).strip() != CLEAN_LANE_BLOCKS
        }
    )
    conditional_operator_review_family_count = family_count_for_effect(
        "conditional_lane_effect",
        CONDITIONAL_OPERATOR_REVIEW,
    )
    learning_claim_blocking_family_count = family_count_for_effect(
        "learning_lane_effect",
        LEARNING_BLOCKS_CLAIM,
    )
    advisory_lifecycle_family_count = family_count_for_effect(
        "advisory_lifecycle_effect",
        ADVISORY_REVIEW_BACKLOG,
    )
    counts.update(
        {
            "release_blocking_family_count": release_blocking_family_count,
            "advisory_only_family_count": advisory_only_family_count,
            "clean_lane_blocking_family_count": release_blocking_family_count,
            "conditional_operator_review_family_count": conditional_operator_review_family_count,
            "learning_claim_blocking_family_count": learning_claim_blocking_family_count,
            "advisory_lifecycle_family_count": advisory_lifecycle_family_count,
        }
    )
    return counts


def taxonomy_coverage_blockers(
    risks: list[dict[str, Any]],
    taxonomy: dict[str, Any],
    *,
    source: str = COHERENCE_SOURCE,
    source_path: str = RELEASE_RISK_TAXONOMY_PATH,
    code: str = TAXONOMY_COVERAGE_BLOCKER_ID,
) -> list[dict[str, Any]]:
    missing_codes = unregistered_release_risk_codes(taxonomy, risks)
    if not missing_codes:
        return []
    return [
        release_closeout_issue(
            source=source,
            source_path=source_path,
            code=code,
            message=(
                "release closeout emitted risk code(s) not registered in release-risk-taxonomy: "
                + ", ".join(missing_codes)
            ),
            required_evidence=[
                "Add each emitted risk code to ops/policies/release-risk-taxonomy.json "
                "before release closeout can be treated as machine-clean.",
            ],
        )
    ]


def blocks_source_clean_lane(issue: dict[str, Any]) -> bool:
    return str(issue.get("clean_lane_effect", "")).strip() == CLEAN_LANE_BLOCKS


def annotated_blocks_source_clean_lane(issue: dict[str, Any], taxonomy: dict[str, Any]) -> bool:
    return blocks_source_clean_lane(annotate_release_risk(issue, taxonomy))
