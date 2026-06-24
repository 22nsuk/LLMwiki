from __future__ import annotations

from typing import Any

from ops.scripts.core.gate_effect_vocabulary import (
    GATE_EFFECT_ADVISORY,
    GATE_EFFECT_CLAIM_BLOCKER,
    GATE_EFFECT_OPERATOR_REVIEW_REQUIRED,
)

from .external_report_release_verification_runtime import (
    ARCHIVED_REPORT_ACTION_TRACE_OBSERVATION_ID,
    REVIEW_BUNDLE_FULL_VAULT_HYGIENE_OBSERVATION_ID,
    _reason_detail,
)

ARCHIVE_RECONCILIATION_REASON_TARGETS: dict[str, tuple[str, str, list[str]]] = {
    ARCHIVED_REPORT_ACTION_TRACE_OBSERVATION_ID: (
        "external_report_reconciliation",
        "external_report_lifecycle",
        ["external-report-lifecycle-refresh", "external-report-action-matrix"],
    ),
    "status_surface_currentness_visibility_gap": (
        "operator_status_currentness",
        "status_surface",
        ["status", "artifact-freshness-refresh-check"],
    ),
    "dev_install_index_portability_gap": (
        "dependency_install_policy",
        "dependency_setup",
        ["dev-install", "uv-lock-check"],
    ),
    "github_governance_live_drift_gap": (
        "github_live_governance_verification",
        "github_live_governance",
        ["collaboration-governance"],
    ),
    REVIEW_BUNDLE_FULL_VAULT_HYGIENE_OBSERVATION_ID: (
        "review_bundle_hygiene",
        "review_archive",
        ["review-archive", "external-report-action-matrix"],
    ),
    "full_vault_archive_mtime_normalization_gap": (
        "archive_portability",
        "source_package",
        ["release-source-package-check", "release-smoke-fast"],
    ),
}
MAINTAINABILITY_REASON_TARGETS: dict[str, tuple[str, str, list[str]]] = {
    "maintainability_hotspot_report_missing": (
        "function_budget_refactor_proposals",
        "maintainability_report_evidence",
        ["function-budget-refactor-proposals"],
    ),
    "maintainability_hotspot_report_kind_mismatch": (
        "function_budget_refactor_proposals",
        "maintainability_report_evidence",
        ["function-budget-refactor-proposals"],
    ),
    "maintainability_hotspot_report_producer_mismatch": (
        "function_budget_refactor_proposals",
        "maintainability_report_evidence",
        ["function-budget-refactor-proposals"],
    ),
    "maintainability_hotspot_report_not_pass": (
        "function_budget_refactor_proposals",
        "maintainability_report_evidence",
        ["function-budget-refactor-proposals"],
    ),
    "maintainability_hotspot_candidates_remain": (
        "function_budget_candidate_closeout",
        "maintainability_candidate_backlog",
        ["function-budget-refactor-proposals"],
    ),
    "maintainability_hotspot_proposals_not_absorbed": (
        "function_budget_proposal_absorption",
        "maintainability_proposal_absorption",
        ["function-budget-refactor-proposals"],
    ),
    "maintainability_hotspot_owner_backlog_not_absorbed": (
        "function_budget_owner_backlog_absorption",
        "maintainability_owner_backlog",
        ["function-budget-refactor-proposals"],
    ),
    "maintainability_hotspot_large_main_remains": (
        "function_budget_large_main_closeout",
        "maintainability_large_main",
        ["function-budget-refactor-proposals"],
    ),
}
SIGSTORE_EXTERNAL_BUNDLE_TARGETS = [
    "sigstore-bundle SIGSTORE_BUNDLE_REF=<bundle>",
    "operator-evidence-closeout-current-or-refresh",
]

SUPPLY_CHAIN_EXTERNAL_REASON_TARGETS: dict[str, tuple[str, str, list[str]]] = {
    "supply_chain_gate_not_pass": (
        "supply_chain_external_gate",
        "supply_chain_external_verification",
        ["supply-chain-check"],
    ),
    "supply_chain_sbom_readiness_not_pass": (
        "supply_chain_external_gate",
        "supply_chain_external_verification",
        ["supply-chain-check"],
    ),
    "supply_chain_slsa_predicate_missing": (
        "supply_chain_external_gate",
        "supply_chain_external_verification",
        ["supply-chain-check"],
    ),
    "supply_chain_sigstore_local_integrity_only": (
        "supply_chain_external_bundle_verification",
        "supply_chain_external_verification",
        SIGSTORE_EXTERNAL_BUNDLE_TARGETS,
    ),
    "supply_chain_sigstore_external_bundle_not_verified": (
        "supply_chain_external_bundle_verification",
        "supply_chain_external_verification",
        SIGSTORE_EXTERNAL_BUNDLE_TARGETS,
    ),
    "supply_chain_sigstore_checks_missing": (
        "supply_chain_external_bundle_verification",
        "supply_chain_external_verification",
        SIGSTORE_EXTERNAL_BUNDLE_TARGETS,
    ),
    "supply_chain_sigstore_check_failed": (
        "supply_chain_external_bundle_verification",
        "supply_chain_external_verification",
        SIGSTORE_EXTERNAL_BUNDLE_TARGETS,
    ),
    "supply_chain_sigstore_bundle_ref_missing": (
        "supply_chain_external_bundle_verification",
        "supply_chain_external_verification",
        SIGSTORE_EXTERNAL_BUNDLE_TARGETS,
    ),
    "supply_chain_external_bundle_rule_missing": (
        "supply_chain_external_bundle_verification",
        "supply_chain_external_verification",
        SIGSTORE_EXTERNAL_BUNDLE_TARGETS,
    ),
    "supply_chain_external_bundle_not_observed": (
        "supply_chain_external_bundle_verification",
        "supply_chain_external_verification",
        SIGSTORE_EXTERNAL_BUNDLE_TARGETS,
    ),
    "supply_chain_release_attestation_missing": (
        "supply_chain_external_workflow_verification",
        "supply_chain_external_verification",
        ["supply-chain-check"],
    ),
    "supply_chain_dependency_review_missing": (
        "supply_chain_external_workflow_verification",
        "supply_chain_external_verification",
        ["supply-chain-check"],
    ),
    "supply_chain_sigstore_bundle_target_missing": (
        "supply_chain_external_workflow_verification",
        "supply_chain_external_verification",
        ["supply-chain-check"],
    ),
}
REASON_PREFIX_TARGETS: tuple[tuple[tuple[str, ...], str, str, str, tuple[str, ...]], ...] = (
    (
        ("release_run_manifest_",),
        "release_run_ready",
        "release_run",
        "",
        ("release-run-ready-plan-check", "release-run-ready"),
    ),
    (
        ("release_sealed_run_manifest_",),
        "release_sealed_run_ready",
        "sealed_release",
        "",
        ("release-sealed-run-ready-plan", "release-sealed-run-ready"),
    ),
    (
        ("release_auto_promotion_ready_manifest_",),
        "release_auto_promotion_ready",
        "unattended_promotion",
        "",
        ("release-auto-promotion-ready-plan", "release-auto-promotion-ready"),
    ),
    (
        ("release_finality_", "release_closeout_fixed_point_"),
        "release_auto_promotion_preseal",
        "release_preseal",
        "",
        (
            "release-auto-promotion-preseal",
            "release-closeout-fixed-point",
            "release-closeout-finality-verify",
        ),
    ),
    (
        ("release_dashboard_", "release_authority_", "release_closeout_"),
        "release_auto_promotion_preseal",
        "release_preseal",
        "",
        ("release-auto-promotion-preseal", "release-evidence-dashboard"),
    ),
    (
        ("source_package_",),
        "release_source_package",
        "source_package",
        "",
        ("release-source-package-check",),
    ),
    (
        ("external_report_",),
        "external_report_reference_manifest",
        "external_report_lifecycle",
        "",
        ("external-report-reference-manifest-settle",),
    ),
    (
        ("collaboration_governance_",),
        "collaboration_governance",
        "github_governance",
        GATE_EFFECT_ADVISORY,
        ("collaboration-governance", "operator-evidence-closeout-current-or-refresh"),
    ),
    (
        ("full_suite_",),
        "release_run_ready",
        "release_run",
        "",
        ("test-execution-summary-full-current-or-refresh",),
    ),
    (
        ("goal_runtime_",),
        "goal_runtime_certificate",
        "unattended_promotion",
        GATE_EFFECT_CLAIM_BLOCKER,
        (
            "GOAL_RUN_ID=<completed-run-id> make goal-runtime-certificate",
            "release-auto-promotion-goal-run-id-guard",
            "release-auto-promotion-ready-plan",
        ),
    ),
    (
        ("goal_run_status_",),
        "goal_runtime_status",
        "goal_runtime_status",
        GATE_EFFECT_CLAIM_BLOCKER,
        (
            "goal-run-status",
            "goal-runtime-reconcile",
        ),
    ),
)
REASON_EXACT_TARGETS: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "release_auto_promotion_not_allowed": (
        "release_auto_promotion_ready",
        "unattended_promotion",
        "",
        ("release-auto-promotion-ready-plan", "release-auto-promotion-ready"),
    ),
    "release_unattended_promotion_not_allowed": (
        "release_auto_promotion_ready",
        "unattended_promotion",
        "",
        ("release-auto-promotion-ready-plan", "release-auto-promotion-ready"),
    ),
}
GITHUB_LIVE_GOVERNANCE_REASON_TARGETS: dict[str, tuple[str, str, list[str]]] = {
    "github_live_governance_checklist_missing": (
        "github_live_governance_verification",
        "github_live_governance",
        ["collaboration-governance"],
    ),
    "github_live_governance_operator_evidence_missing": (
        "github_live_governance_verification",
        "github_live_governance",
        ["collaboration-governance"],
    ),
    "github_live_governance_operator_evidence_not_pass": (
        "github_live_governance_verification",
        "github_live_governance",
        ["collaboration-governance"],
    ),
}

def _target_reason_detail(
    reason_id: str,
    *,
    owning_stage: str,
    blocking_scope: str,
    recommended_targets: tuple[str, ...] | list[str],
    gate_effect: str = "",
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "owning_stage": owning_stage,
        "blocking_scope": blocking_scope,
        "recommended_targets": list(recommended_targets),
    }
    if gate_effect:
        kwargs["gate_effect"] = gate_effect
    return _reason_detail(reason_id, **kwargs)


def _prefix_reason_detail(reason_id: str) -> dict[str, Any] | None:
    if reason_id in REASON_EXACT_TARGETS:
        owning_stage, blocking_scope, gate_effect, recommended_targets = REASON_EXACT_TARGETS[
            reason_id
        ]
        return _target_reason_detail(
            reason_id,
            owning_stage=owning_stage,
            blocking_scope=blocking_scope,
            gate_effect=gate_effect,
            recommended_targets=recommended_targets,
        )
    for prefixes, owning_stage, blocking_scope, gate_effect, recommended_targets in (
        REASON_PREFIX_TARGETS
    ):
        if reason_id.startswith(prefixes):
            return _target_reason_detail(
                reason_id,
                owning_stage=owning_stage,
                blocking_scope=blocking_scope,
                gate_effect=gate_effect,
                recommended_targets=recommended_targets,
            )
    if reason_id.startswith("artifact_freshness_"):
        recommended_targets = ("artifact-freshness-refresh-check",)
        if reason_id == "artifact_freshness_source_identity_resettle":
            recommended_targets = (
                "freshness-source-identity-converge",
                "artifact-freshness-refresh-check",
            )
        if reason_id == "artifact_freshness_stable_contract_debt":
            recommended_targets = (
                "artifact-freshness-stable-contract-debt-refresh",
                "artifact-freshness-refresh-check",
            )
        return _target_reason_detail(
            reason_id,
            owning_stage="artifact_freshness",
            blocking_scope="artifact_freshness",
            gate_effect=GATE_EFFECT_ADVISORY,
            recommended_targets=recommended_targets,
        )
    return None


def _mapped_reason_detail(
    reason_id: str,
    mapping: dict[str, tuple[str, str, list[str]]],
    *,
    gate_effect: str = GATE_EFFECT_ADVISORY,
) -> dict[str, Any] | None:
    if reason_id not in mapping:
        return None
    owning_stage, blocking_scope, recommended_targets = mapping[reason_id]
    return _target_reason_detail(
        reason_id,
        owning_stage=owning_stage,
        blocking_scope=blocking_scope,
        gate_effect=gate_effect,
        recommended_targets=recommended_targets,
    )


def _action_status_reason_detail(reason_id: str, *, fallback_target: str) -> dict[str, Any]:
    prefix_detail = _prefix_reason_detail(reason_id)
    if prefix_detail is not None:
        return prefix_detail
    for mapping in (
        MAINTAINABILITY_REASON_TARGETS,
        SUPPLY_CHAIN_EXTERNAL_REASON_TARGETS,
    ):
        mapped_detail = _mapped_reason_detail(reason_id, mapping)
        if mapped_detail is not None:
            return mapped_detail
    mapped_detail = _mapped_reason_detail(
        reason_id,
        GITHUB_LIVE_GOVERNANCE_REASON_TARGETS,
        gate_effect=GATE_EFFECT_OPERATOR_REVIEW_REQUIRED,
    )
    if mapped_detail is not None:
        return mapped_detail
    if reason_id == "github_governance_live_drift_gap":
        archive_live_detail = _mapped_reason_detail(
            reason_id,
            ARCHIVE_RECONCILIATION_REASON_TARGETS,
            gate_effect=GATE_EFFECT_OPERATOR_REVIEW_REQUIRED,
        )
        if archive_live_detail is not None:
            return archive_live_detail
    archive_detail = _mapped_reason_detail(reason_id, ARCHIVE_RECONCILIATION_REASON_TARGETS)
    if archive_detail is not None:
        return archive_detail
    return _target_reason_detail(
        reason_id,
        owning_stage="action_recommended_target",
        blocking_scope="action_matrix",
        gate_effect=GATE_EFFECT_ADVISORY,
        recommended_targets=(fallback_target,),
    )


def action_status_reason_details(
    reason_ids: list[str],
    *,
    fallback_target: str,
) -> list[dict[str, Any]]:
    return [
        _action_status_reason_detail(reason_id, fallback_target=fallback_target)
        for reason_id in reason_ids
    ]

