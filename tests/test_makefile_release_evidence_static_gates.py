from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

import pytest

from tests.makefile_static_helpers import (
    MakeTargetContract,
    _assert_assignment_values,
    _assert_make_target_contracts,
    _assert_phony_targets,
    _assert_text_contains_tokens,
    _makefile_text,
    _recipe_lines,
    _target_block,
    _target_dependencies,
)

pytestmark = [
    pytest.mark.public,
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
    pytest.mark.schema_static_smoke,
]


REPORT_CONTRACT_CLOSEOUT_POLICY = Path("ops/policies/report-contract-closeout.json")
REPO_ROOT = Path(__file__).resolve().parents[1]

_RELEASE_EVIDENCE_COHORT_ASSIGNMENTS = (
    ("RELEASE_EVIDENCE_DASHBOARD_OUT", "ops/reports/release-evidence-dashboard.json"),
    (
        "RELEASE_EVIDENCE_DASHBOARD_CANDIDATE_OUT",
        "tmp/release-evidence-dashboard.candidate.json",
    ),
    ("RELEASE_LANE_SUMMARY_OUT", "ops/reports/release-lane-summary.json"),
    (
        "RELEASE_LANE_SUMMARY_CANDIDATE_OUT",
        "tmp/release-lane-summary.candidate.json",
    ),
    (
        "RELEASE_CLEAN_BLOCKER_LEDGER_OUT",
        "ops/reports/release-clean-blocker-ledger.json",
    ),
    (
        "RELEASE_CLEAN_BLOCKER_LEDGER_CANDIDATE_OUT",
        "tmp/release-clean-blocker-ledger.candidate.json",
    ),
    (
        "RELEASE_RISK_TAXONOMY_MATRIX_OUT",
        "ops/reports/release-risk-taxonomy-matrix.json",
    ),
    (
        "RELEASE_RISK_TAXONOMY_MATRIX_MD_OUT",
        "ops/reports/release-risk-taxonomy-matrix.md",
    ),
    ("RELEASE_EVIDENCE_COHORT_OUT", "ops/reports/release-evidence-cohort.json"),
    (
        "RELEASE_EVIDENCE_COHORT_STAGING_OUT",
        "tmp/release-evidence-cohort.candidate.json",
    ),
    (
        "RELEASE_EVIDENCE_COHORT_DIAGNOSTIC_OUT",
        "tmp/release-evidence-cohort-check.json",
    ),
    ("RELEASE_EVIDENCE_COHORT_POLICY", "allowed_divergence_with_explicit_risk"),
    ("RELEASE_EVIDENCE_COHORT_PROVENANCE_MODE", "embedded_currentness"),
)

_RELEASE_EVIDENCE_COHORT_BASE_COMMAND = (
    '$(PYTHON) -m ops.scripts.release_evidence_cohort --vault "$(VAULT)" '
    '--out "$(RELEASE_EVIDENCE_COHORT_STAGING_OUT)" '
    '--profile "$(RELEASE_CLOSEOUT_PROFILE)" '
    '--cohort-policy "$(RELEASE_EVIDENCE_COHORT_POLICY)" '
    '--provenance-mode "$(RELEASE_EVIDENCE_COHORT_PROVENANCE_MODE)"'
)

_RELEASE_EVIDENCE_COHORT_CHECK_COMMAND = (
    '$(PYTHON) -m ops.scripts.release_evidence_cohort --vault "$(VAULT)" '
    '--out "$(RELEASE_EVIDENCE_COHORT_DIAGNOSTIC_OUT)" '
    '--profile "$(RELEASE_CLOSEOUT_PROFILE)" '
    "--cohort-policy strict_same_fingerprint "
    '--provenance-mode "$(RELEASE_EVIDENCE_COHORT_PROVENANCE_MODE)"'
)

_RELEASE_EVIDENCE_COHORT_TARGET_CONTRACTS = (
    MakeTargetContract(
        "release-evidence-dashboard",
        phony=True,
        required_tokens=(
            '$(PYTHON) -m ops.scripts.release_evidence_dashboard --vault "$(VAULT)" --out "$(RELEASE_EVIDENCE_DASHBOARD_CANDIDATE_OUT)"',
            "ops.scripts.canonical_artifact_promote",
        ),
    ),
    MakeTargetContract(
        "release-evidence-dashboard-report",
        phony=True,
        required_tokens=(
            '$(PYTHON) -m ops.scripts.release_evidence_dashboard --vault "$(VAULT)" --out "$(RELEASE_EVIDENCE_DASHBOARD_CANDIDATE_OUT)" --no-fail',
            "ops.scripts.canonical_artifact_promote",
        ),
    ),
    MakeTargetContract(
        "release-lane-summary",
        phony=True,
        required_tokens=(
            '$(PYTHON) -m ops.scripts.release_lane_summary --vault "$(VAULT)" --out "$(RELEASE_LANE_SUMMARY_CANDIDATE_OUT)"',
            "ops.scripts.canonical_artifact_promote",
        ),
    ),
    MakeTargetContract(
        "release-clean-blocker-ledger",
        phony=True,
        required_tokens=(
            '$(PYTHON) -m ops.scripts.release_clean_blocker_ledger --vault "$(VAULT)" --out "$(RELEASE_CLEAN_BLOCKER_LEDGER_CANDIDATE_OUT)"',
            "ops.scripts.canonical_artifact_promote",
        ),
    ),
    MakeTargetContract(
        "release-risk-taxonomy-matrix",
        phony=True,
        required_tokens=(
            '$(PYTHON) -m ops.scripts.release_risk_taxonomy_matrix --vault "$(VAULT)"',
            "ops.scripts.canonical_artifact_promote",
        ),
    ),
    MakeTargetContract(
        "release-evidence-cohort",
        phony=True,
        required_tokens=(
            _RELEASE_EVIDENCE_COHORT_BASE_COMMAND,
            "ops.scripts.canonical_artifact_promote",
        ),
        forbidden_tokens=("cp ",),
    ),
    MakeTargetContract(
        "release-evidence-cohort-report",
        phony=True,
        required_tokens=(
            _RELEASE_EVIDENCE_COHORT_BASE_COMMAND,
            "ops.scripts.canonical_artifact_promote",
        ),
        forbidden_tokens=("--require-clean-lane", "--fail-on-attention"),
    ),
    MakeTargetContract(
        "release-evidence-cohort-preseal-refresh",
        phony=True,
        required_tokens=(
            "--cohort-policy strict_same_fingerprint",
            "ops.scripts.canonical_artifact_promote",
        ),
        forbidden_tokens=("--require-clean-lane", "--fail-on-attention"),
    ),
    MakeTargetContract(
        "release-evidence-cohort-check",
        required_tokens=(
            _RELEASE_EVIDENCE_COHORT_CHECK_COMMAND,
            "--require-clean-lane",
        ),
        forbidden_tokens=('$(RELEASE_EVIDENCE_COHORT_OUT)',),
    ),
)

_RELEASE_CLOSEOUT_SUMMARY_ASSIGNMENTS = (
    (
        "RELEASE_CLOSEOUT_SUMMARY_OUT",
        "ops/reports/release-closeout-summary.json",
    ),
    (
        "RELEASE_CLOSEOUT_SUMMARY_CANDIDATE_OUT",
        "tmp/release-closeout-summary.candidate.json",
    ),
    ("RELEASE_CLOSEOUT_PROFILE", "base"),
)

_RELEASE_CLOSEOUT_SUMMARY_BASE_COMMAND = (
    '$(PYTHON) -m ops.scripts.release_closeout_summary --vault "$(VAULT)" '
    '--out "$(RELEASE_CLOSEOUT_SUMMARY_CANDIDATE_OUT)" '
    '--profile "$(RELEASE_CLOSEOUT_PROFILE)"'
)

_RELEASE_CLOSEOUT_SUMMARY_TARGET_CONTRACTS = (
    MakeTargetContract(
        "release-closeout-summary",
        phony=True,
        required_tokens=(
            _RELEASE_CLOSEOUT_SUMMARY_BASE_COMMAND,
            "ops.scripts.canonical_artifact_promote",
        ),
    ),
    MakeTargetContract(
        "release-closeout-summary-report",
        phony=True,
        required_tokens=(
            f"{_RELEASE_CLOSEOUT_SUMMARY_BASE_COMMAND} --no-fail",
            "ops.scripts.canonical_artifact_promote",
        ),
    ),
    MakeTargetContract(
        "release-closeout-summary-conditional",
        phony=True,
        required_tokens=(
            f"{_RELEASE_CLOSEOUT_SUMMARY_BASE_COMMAND} --allow-conditional",
            "ops.scripts.canonical_artifact_promote",
        ),
    ),
)

_RELEASE_CLEAN_LANE_EVIDENCE_REVIEW_ASSIGNMENTS = (
    (
        "RELEASE_CLEAN_LANE_EVIDENCE_REVIEW_OUT",
        "tmp/release-clean-lane-evidence-review.json",
    ),
)

_RELEASE_CLEAN_LANE_EVIDENCE_REVIEW_TARGET_CONTRACTS = (
    MakeTargetContract(
        "release-clean-lane-evidence-review",
        phony=True,
        required_tokens=(
            "ops.scripts.release_clean_lane_evidence_review",
            '--closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)"',
            '--out "$(RELEASE_CLEAN_LANE_EVIDENCE_REVIEW_OUT)"',
        ),
    ),
)

_RELEASE_CLOSEOUT_MANIFEST_PHONY_TARGETS = (
    "release-closeout-batch-manifest-promote",
    "release-closeout-batch-manifest-verify",
    "release-closeout-batch-manifest-replay-verify",
    "release-closeout-finality-attestation",
    "release-closeout-finality-verify",
    "release-evidence-closeout-self-check",
    "release-closeout-post-check-finalizer-dry-run",
    "release-closeout-post-check-finalizer-ci-artifact",
    "release-closeout-fixed-point",
)

_RELEASE_CLOSEOUT_BATCH_MANIFEST_ASSIGNMENTS = (
    "RELEASE_CLOSEOUT_BATCH_MANIFEST_OUT ?= ops/reports/release-closeout-batch-manifest.json",
    "RELEASE_CLOSEOUT_BATCH_MANIFEST_CANDIDATE_OUT ?= tmp/release-closeout-batch-manifest.candidate.json",
    "RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA ?=",
    "RELEASE_CLOSEOUT_DISTRIBUTION_ZIP ?=",
    "RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE ?= UTC",
    "RELEASE_CLOSEOUT_FIXED_POINT_OUT ?= ops/reports/release-closeout-fixed-point.json",
    "RELEASE_CLOSEOUT_FIXED_POINT_CANDIDATE_OUT ?= tmp/release-closeout-fixed-point.candidate.json",
    "RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_OUT ?= tmp/release-closeout-post-check-finalizer.json",
    "RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_RECOMMENDED_TARGETS_OUT ?= tmp/release-closeout-post-check-finalizer-recommended-targets.txt",
    "RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_PLAN_OUT ?= tmp/release-closeout-post-check-finalizer-plan.json",
    "RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS ?=",
    "RELEASE_CLOSEOUT_FIXED_POINT_INITIAL_TARGETS ?=",
)

_RELEASE_CLOSEOUT_FINALITY_ASSIGNMENTS = (
    "OPERATOR_EVIDENCE_FINALITY_INITIAL_TARGETS ?= generated-artifact-index-body artifact-freshness external-report-action-matrix release-closeout-summary-report learning-readiness-signoff-revalidation release-evidence-cohort release-evidence-dashboard-report release-lane-summary release-clean-blocker-ledger release-closeout-batch-manifest-promote release-evidence-closeout-self-check",
    "OPERATOR_EVIDENCE_ARTIFACT_FRESHNESS_PROGRESS ?= jsonl-stable",
    "RELEASE_CLOSEOUT_FINALITY_ATTESTATION_OUT ?= ops/reports/release-closeout-finality-attestation.json",
    "RELEASE_CLOSEOUT_FINALITY_ATTESTATION_CANDIDATE_OUT ?= tmp/release-closeout-finality-attestation.candidate.json",
)

_RELEASE_DISTRIBUTION_ASSIGNMENTS = (
    "RELEASE_DISTRIBUTION_ZIP_OUT ?= build/release/LLMwiki-source.zip",
    "RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT ?= build/release/release-distribution-zip-smoke.json",
    "RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP ?=",
    "RELEASE_CLOSEOUT_SEALED_ZIP_METADATA ?=",
    "RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_OUT ?= build/release/release-closeout-sealed-rehearsal-check.json",
    "RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_CANONICAL_OUT ?= ops/reports/release-closeout-sealed-rehearsal-check.json",
    "RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_RELEASE_OUT ?= build/release/release-closeout-sealed-rehearsal-check.json",
    "RELEASE_AUDIT_PACK_OUT ?= build/release/release-audit-pack.zip",
    "RELEASE_AUDIT_PACK_INCLUDE_OPTIONAL_PAYLOADS ?=",
    "RELEASE_POST_SEAL_ATTESTATION_OUT ?= build/release/release-post-seal-attestation.json",
    "RELEASE_POST_SEAL_ATTESTATION_SOURCE_ZIP ?= $(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)",
    "RELEASE_POST_SEAL_ATTESTATION_SELF_CHECK ?=",
)

_RELEASE_CLOSEOUT_ASSIGNMENT_SURFACES = {
    "release_closeout_batch_manifest": _RELEASE_CLOSEOUT_BATCH_MANIFEST_ASSIGNMENTS,
    "release_closeout_finality": _RELEASE_CLOSEOUT_FINALITY_ASSIGNMENTS,
    "release_distribution": _RELEASE_DISTRIBUTION_ASSIGNMENTS,
}

_EXTERNAL_REPORT_RELEASE_BASIS_PHONY_TARGETS = (
    "external-report-reference-manifest-strict",
    "external-report-reference-manifest-release-check",
    "external-report-reference-manifest-settle",
    "external-report-action-matrix",
    "github-governance-live-drift",
    "github-governance-live-drift-check",
    "collaboration-governance",
    "external-report-lifecycle-refresh",
)

_EXTERNAL_REPORT_RELEASE_BASIS_ASSIGNMENTS = (
    "EXTERNAL_REPORT_REVIEW_BASIS_ZIP_NAME ?=",
    "EXTERNAL_REPORT_REVIEW_BASIS_ZIP_SHA256 ?=",
    "EXTERNAL_REPORT_REVIEW_BASIS_ZIP_ENTRY_COUNT ?=",
    "EXTERNAL_REPORT_REVIEW_BASIS_ZIP_PATH ?=",
    "EXTERNAL_REPORT_BASIS_ZIP_PATH ?=",
    "EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_NAME =",
    "EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_SHA256 =",
    "EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_ENTRY_COUNT =",
    "EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_PATH =",
    "EXTERNAL_REPORT_ACTION_MATRIX_OUT ?= ops/reports/external-report-action-matrix.json",
    "GITHUB_GOVERNANCE_LIVE_INPUT ?= build/release/github-governance-live-input.json",
    "GITHUB_GOVERNANCE_LIVE_DRIFT_OUT ?= ops/reports/github-governance-live-drift.json",
    "GITHUB_GOVERNANCE_LIVE_DRIFT_CHECK_OUT ?= tmp/github-governance-live-drift-check.json",
)

_EXTERNAL_REPORT_RELEASE_BASIS_TARGET_CONTRACTS = (
    MakeTargetContract(
        "external-report-reference-manifest",
        required_tokens=(
            "ops.scripts.external_report_reference_manifest",
            '--mode "$(EXTERNAL_REPORT_REFERENCE_MANIFEST_MODE)"',
            "--basis-zip-name",
            "--basis-zip-sha256",
            "--basis-zip-entry-count",
            "--basis-zip-path",
            "--current-distribution-zip-path",
        ),
    ),
    MakeTargetContract(
        "external-report-reference-manifest-strict",
        required_tokens=(
            "ops.scripts.external_report_reference_manifest",
            "--mode strict_review_release",
            "--basis-zip-path",
            "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_PATH)",
            "$(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH)",
            "--current-distribution-zip-path",
        ),
    ),
    MakeTargetContract(
        "external-report-reference-manifest-release-check",
        required_tokens=(
            "external-report-reference-manifest-strict",
            "external-report-reference-manifest EXTERNAL_REPORT_REFERENCE_MANIFEST_MODE=advisory",
        ),
    ),
    MakeTargetContract(
        "external-report-reference-manifest-settle",
        required_tokens=(
            "RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP",
            'EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"',
            'EXTERNAL_REPORT_REVIEW_BASIS_ZIP_PATH="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"',
        ),
    ),
    MakeTargetContract(
        "external-report-action-matrix",
        required_tokens=(
            "ops.scripts.external_report_action_matrix",
            '--out "$(EXTERNAL_REPORT_ACTION_MATRIX_OUT)"',
        ),
    ),
    MakeTargetContract(
        "github-governance-live-drift",
        required_tokens=(
            "ops.scripts.release.github_governance_live_drift",
            '--live-input "$(GITHUB_GOVERNANCE_LIVE_INPUT)"',
            '--out "$(GITHUB_GOVERNANCE_LIVE_DRIFT_OUT)"',
        ),
    ),
    MakeTargetContract(
        "github-governance-live-drift-check",
        required_tokens=(
            "ops.scripts.release.github_governance_live_drift",
            '--live-input "$(GITHUB_GOVERNANCE_LIVE_INPUT)"',
            '--out "$(GITHUB_GOVERNANCE_LIVE_DRIFT_CHECK_OUT)"',
        ),
    ),
    MakeTargetContract(
        "collaboration-governance",
        required_tokens=("github-governance-live-drift",),
    ),
    MakeTargetContract(
        "external-report-lifecycle-refresh",
        exact_recipe=(
            "$(MAKE) external-report-reference-manifest-settle",
            "$(MAKE) release-finality-resettle-current-or-refresh",
        ),
    ),
)

_SEALED_RELEASE_CLOSEOUT_PHONY_TARGETS = (
    "release-distribution-zip",
    "release-evidence-closeout-sealed",
    "release-evidence-closeout-sealed-core-sidecars",
    "release-evidence-closeout-sealed-sidecars",
    "release-sealed-post-seal-attestation",
    "release-evidence-closeout-sealed-check",
    "release-evidence-closeout-sealed-dry-run",
    "release-evidence-closeout-sealed-dry-run-check",
    "release-authority-sealed-preflight",
    "release-post-seal-attestation",
)

_SEALED_RELEASE_CLOSEOUT_ASSIGNMENTS = (
    "RELEASE_CLOSEOUT_SEALED_DRY_RUN_ROOT ?= build/release/release-closeout-sealed-dry-run",
    "RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_FLAGS ?= --no-fail",
    "RELEASE_CLOSEOUT_SEALED_EXTERNAL_MANIFEST_OUT ?= build/release/external-report-reference-manifest.json",
    "RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT ?= build/release/release-closeout-batch-manifest.json",
    "RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT ?= build/release/release-evidence-closeout-self-check.json",
    "RELEASE_CLOSEOUT_SEALED_OPERATOR_SUMMARY_OUT ?= build/release/operator-release-summary.json",
    "RELEASE_AUTO_PROMOTION_OPERATOR_SUMMARY_OUT ?= $(RELEASE_CLOSEOUT_SEALED_OPERATOR_SUMMARY_OUT)",
    "RELEASE_SEALED_POST_SEAL_ATTESTATION_OUT ?= build/release/release-sealed-post-seal-attestation.json",
    "RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_BATCH_MANIFEST ?= build/release/release-closeout-batch-manifest.json",
    "RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_EXTERNAL_MANIFEST ?= build/release/external-report-reference-manifest.json",
)

_SEALED_RELEASE_CLOSEOUT_TARGET_CONTRACTS = (
    MakeTargetContract(
        "release-distribution-zip",
        required_tokens=(
            "ops.scripts.release.release_smoke",
            "--profile fast",
            '--archive-out "$(RELEASE_DISTRIBUTION_ZIP_OUT)"',
            '--out "$(RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT)"',
        ),
    ),
    MakeTargetContract(
        "release-evidence-closeout-sealed",
        exact_recipe=(
            "$(MAKE) release-worktree-clean-check",
            "$(MAKE) release-package-current",
            "$(MAKE) release-seal-current",
        ),
        forbidden_tokens=("$(MAKE) release-evidence-converge", "release-sealed-verify"),
    ),
    MakeTargetContract(
        "release-evidence-closeout-sealed-core-sidecars",
        required_tokens=(
            "ops.scripts.external_report_reference_manifest",
            '--out "$(RELEASE_CLOSEOUT_SEALED_EXTERNAL_MANIFEST_OUT)"',
            "--mode strict_review_release",
            '--current-distribution-zip-path "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
            "ops.scripts.release_closeout_batch_manifest",
            '--out "$(RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT)"',
            '--zip-metadata "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
            "ops.scripts.release_evidence_closeout_self_check",
            '--out "$(RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT)"',
            "$(MAKE) tmp-json-clean",
        ),
    ),
    MakeTargetContract(
        "release-evidence-closeout-sealed-sidecars",
        required_tokens=(
            "$(MAKE) release-evidence-closeout-sealed-core-sidecars",
            "ops.scripts.operator_release_summary",
            '--out "$(RELEASE_CLOSEOUT_SEALED_OPERATOR_SUMMARY_OUT)"',
            '--batch-manifest "$(RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT)"',
            '--self-check "$(RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT)"',
        ),
    ),
    MakeTargetContract(
        "release-sealed-post-seal-attestation",
        required_tokens=(
            "ops.scripts.release_sealed_post_seal_attestation",
            '--out "$(RELEASE_SEALED_POST_SEAL_ATTESTATION_OUT)"',
            '--run-manifest "$(RELEASE_RUN_MANIFEST_OUT)"',
            '--batch-manifest "$(RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT)"',
            '--external-manifest "$(RELEASE_CLOSEOUT_SEALED_EXTERNAL_MANIFEST_OUT)"',
            '--self-check "$(RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT)"',
        ),
    ),
    MakeTargetContract(
        "release-evidence-closeout-sealed-check",
        required_tokens=(
            "ops.scripts.release_closeout_sealed_rehearsal_check",
            '--batch-manifest "$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_BATCH_MANIFEST)"',
            '--external-manifest "$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_EXTERNAL_MANIFEST)"',
            '--out "$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_OUT)"',
        ),
    ),
    MakeTargetContract(
        "release-evidence-closeout-sealed-dry-run",
        required_tokens=(
            'RELEASE_DISTRIBUTION_ZIP_OUT="$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_DISTRIBUTION_ZIP)"',
            "ops.scripts.external_report_reference_manifest",
            '--out "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_EXTERNAL_MANIFEST_OUT)"',
            "--mode strict_review_release",
            "ops.scripts.release_closeout_batch_manifest",
            '--out "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_BATCH_MANIFEST_OUT)"',
            "ops.scripts.release_closeout_sealed_rehearsal_check",
            '--batch-manifest "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_BATCH_MANIFEST_OUT)"',
            '--external-manifest "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_EXTERNAL_MANIFEST_OUT)"',
            "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_FLAGS)",
        ),
    ),
    MakeTargetContract(
        "release-evidence-closeout-sealed-dry-run-check",
        required_tokens=("RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_FLAGS=",),
    ),
    MakeTargetContract(
        "release-authority-sealed-preflight",
        required_tokens=(
            "RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_FLAGS=--allow-blocked-preflight",
            "ops.scripts.canonical_artifact_promote",
            '--candidate "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_OUT)"',
            '--out "$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_CANONICAL_OUT)"',
        ),
    ),
)

_BATCH_MANIFEST_CLOSEOUT_TARGET_CONTRACTS = (
    MakeTargetContract(
        "release-closeout-batch-manifest-promote",
        required_tokens=(
            "ops.scripts.release_closeout_batch_manifest",
            '--out "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_CANDIDATE_OUT)"',
            '--zip-metadata "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA)"',
            '--distribution-zip "$(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP)"',
            "ops.scripts.canonical_artifact_promote",
            "--binding-mode revision",
        ),
    ),
    MakeTargetContract(
        "release-closeout-batch-manifest-replay-verify",
        required_tokens=(
            "release-closeout-batch-manifest-replay-verify requires a clean tmp workspace",
            "find tmp -mindepth 1 -type f",
            "ops.scripts.release_closeout_batch_manifest",
            "--check",
            '--zip-metadata "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA)"',
            '--distribution-zip "$(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP)"',
        ),
    ),
    MakeTargetContract(
        "release-closeout-fixed-point",
        required_tokens=(
            "ops.scripts.release_closeout_fixed_point",
            '--out "$(RELEASE_CLOSEOUT_FIXED_POINT_CANDIDATE_OUT)"',
            "--schema ops/schemas/release-closeout-fixed-point.schema.json",
            '--initial-target "$(target)"',
            "--binding-mode revision",
            "$(MAKE) release-closeout-finality-attestation",
        ),
    ),
    MakeTargetContract(
        "release-closeout-post-check-finalizer-dry-run",
        required_tokens=(
            '--dry-run --out "$(RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_OUT)"',
            "$(RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS)",
        ),
    ),
    MakeTargetContract(
        "release-closeout-post-check-finalizer-ci-artifact",
        required_tokens=("--recommended-targets-out", "--plan-out"),
    ),
    MakeTargetContract(
        "release-closeout-finality-attestation",
        required_tokens=(
            "ops.scripts.release_closeout_finality_attestation",
            "--schema ops/schemas/release-closeout-finality-attestation.schema.json",
            "--binding-mode revision",
        ),
    ),
    MakeTargetContract(
        "release-closeout-finality-verify",
        required_tokens=("--verify",),
    ),
    MakeTargetContract(
        "release-evidence-closeout-self-check",
        required_tokens=(
            "ops.scripts.release_evidence_closeout_self_check",
            '--batch-manifest "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_OUT)"',
            '--out "$(RELEASE_EVIDENCE_CLOSEOUT_SELF_CHECK_OUT)"',
        ),
    ),
)

_RELEASE_AUDIT_AND_POST_SEAL_TARGET_CONTRACTS = (
    MakeTargetContract(
        "release-audit-pack",
        phony=True,
        required_tokens=(
            "ops.scripts.release_audit_pack",
            '--batch-manifest "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_OUT)"',
            '--out "$(RELEASE_AUDIT_PACK_OUT)"',
            "--include-optional-payloads",
        ),
    ),
    MakeTargetContract(
        "release-post-seal-attestation",
        required_tokens=(
            "ops.scripts.release_post_seal_attestation build",
            '--out "$(RELEASE_POST_SEAL_ATTESTATION_OUT)"',
            "--source-zip-path",
            "--batch-manifest-path",
            "--self-check-path",
            "--operator-summary-path",
        ),
    ),
)


def _release_evidence_converge_expanded_recipe_lines(text: str) -> list[str]:
    return [
        *_recipe_lines(text, "release-evidence-converge-phase-1"),
        *_recipe_lines(text, "release-evidence-converge-phase-2"),
        *_recipe_lines(text, "release-evidence-converge-phase-3"),
    ]


def _assert_surface_tokens(
    case: unittest.TestCase,
    text: str,
    surfaces: dict[str, tuple[str, ...]],
) -> None:
    for surface, tokens in surfaces.items():
        _assert_text_contains_tokens(case, text, tokens, surface=surface)


def _assert_release_closeout_manifest_phony_and_vars(case: unittest.TestCase, text: str) -> None:
    _assert_phony_targets(case, text, _RELEASE_CLOSEOUT_MANIFEST_PHONY_TARGETS)
    _assert_surface_tokens(case, text, _RELEASE_CLOSEOUT_ASSIGNMENT_SURFACES)


def _assert_external_report_release_basis_targets(case: unittest.TestCase, text: str) -> None:
    _assert_phony_targets(case, text, _EXTERNAL_REPORT_RELEASE_BASIS_PHONY_TARGETS)
    _assert_text_contains_tokens(
        case,
        text,
        _EXTERNAL_REPORT_RELEASE_BASIS_ASSIGNMENTS,
        surface="external_report_release_basis",
    )
    case.assertNotIn(
        "0a547950871ebd749bf6523cbc1d1a33a58a793168f3b6514b26a8b796869c93", text
    )
    case.assertNotIn(
        "EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_ENTRY_COUNT = $(if $(EXTERNAL_REPORT_REVIEW_BASIS_ZIP_ENTRY_COUNT),$(EXTERNAL_REPORT_REVIEW_BASIS_ZIP_ENTRY_COUNT),$(if $(EXTERNAL_REPORT_BASIS_ZIP_ENTRY_COUNT),$(EXTERNAL_REPORT_BASIS_ZIP_ENTRY_COUNT),1819))",
        text,
    )
    _assert_make_target_contracts(
        case,
        text,
        _EXTERNAL_REPORT_RELEASE_BASIS_TARGET_CONTRACTS,
    )
    settle_block = _target_block(text, "external-report-reference-manifest-settle")
    case.assertEqual(
        settle_block.count("external-report-reference-manifest-release-check"),
        1,
    )


def _assert_sealed_release_closeout_targets(case: unittest.TestCase, text: str) -> None:
    _assert_phony_targets(case, text, _SEALED_RELEASE_CLOSEOUT_PHONY_TARGETS)
    _assert_text_contains_tokens(
        case,
        text,
        _SEALED_RELEASE_CLOSEOUT_ASSIGNMENTS,
        surface="sealed_release_closeout",
    )
    _assert_make_target_contracts(case, text, _SEALED_RELEASE_CLOSEOUT_TARGET_CONTRACTS)


def _assert_batch_manifest_closeout_recipe_targets(case: unittest.TestCase, text: str) -> None:
    _assert_make_target_contracts(case, text, _BATCH_MANIFEST_CLOSEOUT_TARGET_CONTRACTS)
    fixed_point_lines = _recipe_lines(text, "release-closeout-fixed-point")
    promotion_index = next(
        index
        for index, line in enumerate(fixed_point_lines)
        if "ops.scripts.canonical_artifact_promote" in line
    )
    attestation_index = fixed_point_lines.index(
        "$(MAKE) release-closeout-finality-attestation"
    )
    case.assertLess(promotion_index, attestation_index)
    case.assertNotIn("$(MAKE) external-report-action-matrix", fixed_point_lines)
    case.assertFalse(any("--bootstrap-post-promote" in line for line in fixed_point_lines))


def _assert_release_audit_and_post_seal_targets(case: unittest.TestCase, text: str) -> None:
    _assert_make_target_contracts(case, text, _RELEASE_AUDIT_AND_POST_SEAL_TARGET_CONTRACTS)
    case.assertEqual(
        _target_block(text, "release-post-seal-attestation").splitlines()[0],
        "release-post-seal-attestation:",
    )
    replay_verify = _target_block(text, "release-closeout-batch-manifest-replay-verify")
    case.assertIn("release-closeout-batch-manifest-replay-verify requires a clean tmp workspace", replay_verify)
    case.assertIn("find tmp -mindepth 1 -type f", replay_verify)
    case.assertEqual(
        _target_block(text, "release-closeout-batch-manifest-verify").splitlines()[0],
        "release-closeout-batch-manifest-verify: release-closeout-batch-manifest-replay-verify",
    )



class MakefileReleaseEvidenceStaticGateTests(unittest.TestCase):
    def test_release_closeout_summary_target_aggregates_existing_release_reports(
        self,
    ) -> None:
        text = _makefile_text()

        _assert_assignment_values(self, text, _RELEASE_CLOSEOUT_SUMMARY_ASSIGNMENTS)
        _assert_make_target_contracts(
            self,
            text,
            (_RELEASE_CLOSEOUT_SUMMARY_TARGET_CONTRACTS[0],),
        )

    def test_head_aligned_evidence_converge_aliases_post_commit_check_only_finalizer(
        self,
    ) -> None:
        text = _makefile_text()

        _assert_make_target_contracts(
            self,
            text,
            (
                MakeTargetContract(
                    "head-aligned-evidence-converge",
                    phony=True,
                    required_tokens=(
                        "compatibility alias",
                        "release-post-commit-finalize",
                    ),
                ),
            ),
        )
        self.assertEqual(
            _target_dependencies(text, "head-aligned-evidence-converge"),
            ("release-post-commit-finalize",),
        )
        alias_lines = _recipe_lines(text, "head-aligned-evidence-converge")
        self.assertEqual(len(alias_lines), 1)
        self.assertTrue(alias_lines[0].startswith("@echo "))
        finalizer_lines = _recipe_lines(text, "release-post-commit-finalize")
        forbidden_default_refreshes = {
            "$(MAKE) release-evidence-converge",
            "$(MAKE) test-execution-summary-full-current-or-refresh",
            "$(MAKE) test-execution-summary-full-refresh",
            "$(MAKE) test-execution-summary-current-or-refresh",
            "$(MAKE) release-auto-promotion-ready-invalidate",
            "$(MAKE) release-authority-sealed-preflight",
            "$(MAKE) release-evidence-dashboard-report",
            "$(MAKE) release-clean-blocker-ledger",
            "$(MAKE) generated-artifact-converge",
            "$(MAKE) release-finality-resettle",
        }
        self.assertEqual(forbidden_default_refreshes & set(finalizer_lines), set())

    def test_release_closeout_summary_report_target_is_write_only(self) -> None:
        text = _makefile_text()

        _assert_make_target_contracts(
            self,
            text,
            _RELEASE_CLOSEOUT_SUMMARY_TARGET_CONTRACTS[1:],
        )

    def test_release_freshness_sensitive_evidence_refresh_avoids_goal_status_publish(
        self,
    ) -> None:
        text = _makefile_text()
        self.assertIn(
            "release-freshness-sensitive-evidence-refresh",
            _target_block(text, ".PHONY"),
        )
        self.assertEqual(
            _recipe_lines(text, "release-freshness-sensitive-evidence-refresh"),
            [
                "$(MAKE) supply-chain-artifacts-cached",
                "$(MAKE) lint-uplift-plan",
                "$(MAKE) type-uplift-plan",
                "$(MAKE) complexity-budget",
            ],
        )
        target_block = _target_block(text, "release-freshness-sensitive-evidence-refresh")
        self.assertNotIn("$(MAKE) codex-goal-contract", target_block)
        self.assertNotIn("$(MAKE) codex-goal-prompt", target_block)
        self.assertNotIn("$(MAKE) auto-improve-goal-status", target_block)
        self.assertNotIn("$(MAKE) goal-runtime-publish-snapshot", target_block)
        self.assertNotIn("$(MAKE) goal-runtime-publish-local-evidence", target_block)
        self.assertNotIn("$(MAKE) goal-runtime-certificate-run-id-guard", target_block)

        converge_lines = _release_evidence_converge_expanded_recipe_lines(text)
        phase_2_refresh_index = converge_lines.index(
            "$(MAKE) release-freshness-sensitive-evidence-refresh"
        )
        self.assertLess(
            phase_2_refresh_index,
            converge_lines.index(
                "$(MAKE) auto-improve-readiness-report-body",
                phase_2_refresh_index,
            ),
        )
        self.assertLess(
            phase_2_refresh_index,
            converge_lines.index(
                "$(MAKE) generated-artifact-converge",
                phase_2_refresh_index,
            ),
        )

    def test_freshness_source_identity_converge_stays_narrow(self) -> None:
        text = _makefile_text()
        target_block = _target_block(text, "freshness-source-identity-converge")
        owner_target_block = _target_block(text, "freshness-owner-route-converge")

        _assert_make_target_contracts(
            self,
            text,
            (
                MakeTargetContract(
                    "freshness-owner-route-converge",
                    phony=True,
                    required_tokens=(
                        "ops.scripts.release.freshness_owner_route_converge",
                        '--vault "$(VAULT)"',
                        '--make "$(MAKE)"',
                        "--python $(PYTHON)",
                        '--plan-out "$(FRESHNESS_OWNER_ROUTE_CONVERGE_PLAN_OUT)"',
                    ),
                ),
                MakeTargetContract(
                    "freshness-source-identity-converge",
                    phony=True,
                    required_tokens=("freshness-owner-route-converge",),
                ),
            ),
        )
        self.assertEqual(len(_recipe_lines(text, "freshness-owner-route-converge")), 1)
        self.assertEqual(
            _target_dependencies(text, "freshness-source-identity-converge"),
            ("freshness-owner-route-converge",),
        )
        self.assertEqual(_recipe_lines(text, "freshness-source-identity-converge"), [])
        for forbidden_target in (
            "$(MAKE) test-execution-summary-full-current-or-refresh",
            "$(MAKE) test-execution-summary-full-refresh",
            "$(MAKE) release-run-ready",
            "$(MAKE) release-authority-settle",
            "$(MAKE) release-evidence-converge",
            "$(MAKE) release-smoke-full",
            "$(MAKE) release-source-package-check",
            "$(MAKE) goal-runtime-publish-snapshot",
            "$(MAKE) goal-runtime-publish-local-evidence",
        ):
            with self.subTest(forbidden_target=forbidden_target):
                self.assertNotIn(forbidden_target, target_block)
                self.assertNotIn(forbidden_target, owner_target_block)

    def test_operator_evidence_closeout_stays_off_release_authority_lane(self) -> None:
        text = _makefile_text()
        phony = _target_block(text, ".PHONY")
        target_block = _target_block(text, "operator-evidence-closeout-finality-resettle")

        self.assertIn("operator-evidence-closeout-current-or-refresh", phony)
        self.assertIn("operator-evidence-closeout-finality-resettle", phony)
        self.assertEqual(
            _recipe_lines(text, "operator-evidence-closeout-finality-resettle"),
            [
                "$(MAKE) test-execution-summary-current-or-refresh",
                '$(MAKE) release-closeout-fixed-point RELEASE_CLOSEOUT_FIXED_POINT_INITIAL_TARGETS="$(OPERATOR_EVIDENCE_FINALITY_INITIAL_TARGETS)" ARTIFACT_FRESHNESS_PROGRESS="$(OPERATOR_EVIDENCE_ARTIFACT_FRESHNESS_PROGRESS)"',
                "$(MAKE) tmp-json-clean",
                "$(MAKE) release-closeout-finality-verify",
            ],
        )
        current_or_refresh = _target_block(
            text,
            "operator-evidence-closeout-current-or-refresh",
        )
        self.assertIn("$(MAKE) release-finality-resettle-current-check", current_or_refresh)
        self.assertIn("$(MAKE) operator-evidence-closeout-finality-resettle", current_or_refresh)
        for forbidden_target in (
            "$(MAKE) release-authority-sealed-preflight",
            "$(MAKE) release-run-ready",
            "$(MAKE) release-authority-settle",
            "$(MAKE) release-evidence-converge",
            "$(MAKE) release-smoke-full",
            "$(MAKE) release-source-package-check",
            "$(MAKE) test-execution-summary-full-current-or-refresh",
        ):
            with self.subTest(forbidden_target=forbidden_target):
                self.assertNotIn(forbidden_target, target_block)

    def test_release_clean_lane_evidence_review_target_exists(self) -> None:
        text = _makefile_text()

        _assert_assignment_values(
            self,
            text,
            _RELEASE_CLEAN_LANE_EVIDENCE_REVIEW_ASSIGNMENTS,
        )
        _assert_make_target_contracts(
            self,
            text,
            _RELEASE_CLEAN_LANE_EVIDENCE_REVIEW_TARGET_CONTRACTS,
        )

    def test_release_closeout_batch_manifest_target_uses_candidate_promote_pattern(
        self,
    ) -> None:
        text = _makefile_text()
        _assert_release_closeout_manifest_phony_and_vars(self, text)
        _assert_external_report_release_basis_targets(self, text)
        _assert_sealed_release_closeout_targets(self, text)
        _assert_batch_manifest_closeout_recipe_targets(self, text)
        _assert_release_audit_and_post_seal_targets(self, text)

    def test_report_contract_closeout_runs_pytest_wrapper_once_before_generated_orchestrator(
        self,
    ) -> None:
        text = _makefile_text()
        block = _target_block(text, "report-contract-closeout")
        orchestrator_block = _target_block(text, "report-contract-closeout-generated-artifacts")
        precheck_block = _target_block(text, "report-contract-closeout-precheck")

        self.assertIn("report-contract-closeout", _target_block(text, ".PHONY"))
        self.assertIn("report-contract-closeout-generated-artifacts", _target_block(text, ".PHONY"))
        self.assertIn("report-contract-closeout:", text)
        self.assertIn("$(MAKE) release-smoke-full-reuse", block)
        self.assertIn("$(MAKE) report-contract-closeout-precheck", block)
        self.assertIn(
            '$(PYTHON) -m ops.scripts.report_contract_closeout_runtime --vault "$(VAULT)"',
            precheck_block,
        )
        self.assertIn("$(MAKE) test-execution-summary-report-contract", block)
        self.assertIn("$(MAKE) report-contract-closeout-generated-artifacts", block)
        self.assertNotIn("$(MAKE) script-output-surfaces", block)
        self.assertNotIn("$(MAKE) auto-improve-readiness-report\n", block)
        self.assertNotIn("$(MAKE) generated-artifact-converge", block)
        self.assertEqual(orchestrator_block.count("$(MAKE) generated-artifact-converge"), 2)
        self.assertNotIn("$(MAKE) generated-artifact-index", block)
        self.assertEqual(block.count("$(MAKE) archive-execution-manifest-report"), 0)
        self.assertNotIn("$(MAKE) archive-execution-manifest\n", block)
        self.assertNotIn("$(MAKE) artifact-freshness", block)
        self.assertEqual(orchestrator_block.count("$(MAKE) release-closeout-summary-report"), 2)
        self.assertIn("$(MAKE) release-evidence-cohort", orchestrator_block)
        self.assertIn("$(MAKE) auto-improve-readiness-report-body", orchestrator_block)
        self.assertNotIn("$(PYTHON) -m pytest", block)
        self.assertIn("closeout artifacts", block)
        self.assertLess(
            block.index("$(MAKE) report-contract-closeout-precheck"),
            block.index("$(MAKE) release-smoke-full-reuse"),
        )
        self.assertLess(
            block.index("$(MAKE) release-smoke-full-reuse"),
            block.index("$(MAKE) test-execution-summary-report-contract"),
        )
        self.assertLess(
            block.index("$(MAKE) test-execution-summary-report-contract"),
            block.index("$(MAKE) report-contract-closeout-generated-artifacts"),
        )

    def test_report_contract_closeout_precheck_policy_and_runtime_stay_in_sync(
        self,
    ) -> None:
        text = _makefile_text()
        policy = json.loads(REPORT_CONTRACT_CLOSEOUT_POLICY.read_text(encoding="utf-8"))
        expected_targets = [
            "generated-artifact-converge",
            "auto-improve-readiness-report",
            "generated-artifact-converge",
        ]

        self.assertEqual(policy.get("version"), 1)
        self.assertEqual(policy.get("pre_refresh_targets"), expected_targets)
        precheck_block = _target_block(text, "report-contract-closeout-precheck")
        self.assertIn(
            '@for target in $$($(PYTHON) -m ops.scripts.report_contract_closeout_runtime --vault "$(VAULT)"); do \\',
            precheck_block,
        )
        self.assertIn("\t\t$(MAKE) $$target; \\", precheck_block)

        env = os.environ.copy()
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "ops.scripts.report_contract_closeout_runtime",
                "--vault",
                str(REPO_ROOT),
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        self.assertEqual(
            completed.returncode,
            0,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        self.assertEqual(completed.stdout.splitlines(), expected_targets)
        self.assertEqual(completed.stderr, "")

    def test_release_evidence_converge_enforces_strict_recipe_order(self) -> None:
        text = _makefile_text()
        block = _target_block(text, "release-evidence-closeout")
        converge_block = _target_block(text, "release-evidence-converge")
        recipe_lines = _release_evidence_converge_expanded_recipe_lines(text)

        self.assertIn("release-evidence-closeout", _target_block(text, ".PHONY"))
        self.assertIn("release-evidence-converge", _target_block(text, ".PHONY"))
        self.assertIn("release-evidence-converge-phase-1", _target_block(text, ".PHONY"))
        self.assertIn("release-evidence-converge-phase-2", _target_block(text, ".PHONY"))
        self.assertIn("release-evidence-converge-phase-3", _target_block(text, ".PHONY"))
        self.assertEqual(block.splitlines()[0], "release-evidence-closeout: release-evidence-converge")
        self.assertIn("compatibility alias", block)
        self.assertEqual(converge_block.splitlines()[0], "release-evidence-converge: release-evidence-converge-phase-3")
        self.assertEqual(
            _target_block(text, "release-evidence-converge-phase-2").splitlines()[0],
            "release-evidence-converge-phase-2: release-evidence-converge-phase-1",
        )
        self.assertEqual(
            _target_block(text, "release-evidence-converge-phase-3").splitlines()[0],
            "release-evidence-converge-phase-3: release-evidence-converge-phase-2",
        )
        self.assertIn("$(MAKE) release-evidence-converge-lane-guard", recipe_lines)
        self.assertIn("$(MAKE) release-closeout-post-check-finalizer-dry-run", recipe_lines)
        self.assertIn("$(MAKE) release-closeout-fixed-point", recipe_lines)
        self.assertIn("$(MAKE) tmp-json-clean", recipe_lines)
        self.assertEqual(recipe_lines.count("$(MAKE) test-execution-summary-full-refresh"), 1)
        self.assertGreaterEqual(recipe_lines.count("$(MAKE) generated-artifact-converge"), 2)
        self.assertNotIn("$(MAKE) release-closeout-batch-manifest-promote", recipe_lines)
        self.assertNotIn("$(MAKE) release-evidence-closeout-self-check", recipe_lines)

    def test_release_evidence_converge_uses_fixed_point_finalizer(self) -> None:
        text = _makefile_text()
        recipe_lines = _release_evidence_converge_expanded_recipe_lines(text)

        self.assertTrue(recipe_lines, "release-evidence-converge has no recipe lines")

        self.assertIn("$(MAKE) release-closeout-fixed-point", recipe_lines)
        self.assertNotIn("$(MAKE) operator-release-summary", recipe_lines)
        self.assertNotIn(
            "$(MAKE) release-closeout-batch-manifest-promote", recipe_lines
        )
        self.assertNotIn("$(MAKE) release-evidence-closeout-self-check", recipe_lines)

    def test_fixed_point_terminal_operator_writer_cleans_staging_first(self) -> None:
        text = _makefile_text()

        self.assertIn("operator-release-summary-terminal", _target_block(text, ".PHONY"))
        self.assertEqual(
            _recipe_lines(text, "operator-release-summary-terminal"),
            [
                "$(MAKE) tmp-json-clean",
                "$(MAKE) operator-release-summary",
            ],
        )

    def test_release_verify_current_and_sealed_verify_are_check_lanes(self) -> None:
        text = _makefile_text()
        verify_lines = _recipe_lines(text, "release-verify-current")
        sealed_lines = _recipe_lines(text, "release-sealed-verify")

        self.assertIn("release-verify-current", _target_block(text, ".PHONY"))
        self.assertIn("release-sealed-verify", _target_block(text, ".PHONY"))
        self.assertEqual(
            verify_lines,
            [
                "$(MAKE) release-check-finalized",
                "$(MAKE) release-closeout-finality-verify",
            ],
        )
        self.assertEqual(
            sealed_lines,
            [
                "$(MAKE) release-verify-current",
                "$(MAKE) release-evidence-closeout-sealed-check",
            ],
        )
        for line in verify_lines + sealed_lines:
            self.assertNotIn("release-closeout-finality-attestation", line)
            self.assertNotIn("release-evidence-converge", line)
            self.assertNotIn("release-distribution-zip", line)

    def test_release_finality_resettle_is_focused_terminal_wrapper(self) -> None:
        text = _makefile_text()
        recipe_lines = _recipe_lines(text, "release-finality-resettle")
        terminal_lines = _recipe_lines(text, "release-terminal-finality")

        self.assertIn("release-finality-resettle", _target_block(text, ".PHONY"))
        self.assertIn("release-finality-resettle-current-check", _target_block(text, ".PHONY"))
        self.assertIn("release-finality-resettle-current-diagnose", _target_block(text, ".PHONY"))
        self.assertIn("release-finality-resettle-current-or-refresh", _target_block(text, ".PHONY"))
        self.assertIn("release-terminal-finality", _target_block(text, ".PHONY"))
        for required_line in (
            "$(MAKE) workflow-dependency-planner",
            "$(MAKE) release-authority-sealed-preflight",
            "$(MAKE) release-terminal-finality",
        ):
            with self.subTest(required_line=required_line):
                self.assertIn(required_line, recipe_lines)
        for required_line in (
            "$(MAKE) release-closeout-fixed-point",
            "$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required",
        ):
            with self.subTest(required_line=required_line):
                self.assertIn(required_line, terminal_lines)
        current_check_block = _target_block(
            text,
            "release-finality-resettle-current-check",
        )
        self.assertIn("$(MAKE) release-closeout-batch-manifest-replay-verify", current_check_block)
        self.assertIn("$(MAKE) release-closeout-post-check-finalizer-dry-run", current_check_block)
        self.assertIn("$(MAKE) release-closeout-finality-verify", current_check_block)
        self.assertIn("$(MAKE) release-finality-resettle-current-diagnose", current_check_block)
        self.assertEqual(
            _recipe_lines(text, "release-finality-resettle-current-diagnose"),
            [
                '$(PYTHON) -m ops.scripts.release.release_closeout_finality_attestation --vault "$(VAULT)" --attestation "$(RELEASE_CLOSEOUT_FINALITY_ATTESTATION_OUT)" --verify --no-fail',
            ],
        )
        current_or_refresh_block = _target_block(
            text,
            "release-finality-resettle-current-or-refresh",
        )
        self.assertIn("$(MAKE) release-finality-resettle-current-check", current_or_refresh_block)
        self.assertIn("$(MAKE) release-finality-resettle", current_or_refresh_block)
        self.assertGreaterEqual(
            current_or_refresh_block.count("$(MAKE) release-finality-resettle-current-check"),
            2,
        )
        self.assertNotIn("$(MAKE) release-evidence-converge", recipe_lines)

    def test_release_converge_post_delegates_to_terminal_finality_once(self) -> None:
        recipe_lines = _recipe_lines(_makefile_text(), "release-converge-post")

        self.assertEqual(
            recipe_lines,
            [
                "$(MAKE) release-converge-post-evidence",
                "$(MAKE) release-terminal-finality",
            ],
        )
        self.assertNotIn("$(MAKE) release-closeout-fixed-point", recipe_lines)

    def test_check_finalized_runs_post_check_dry_run_before_mutating_finalizer(self) -> None:
        text = _makefile_text()
        block = _target_block(text, "check-finalized")
        recipe_lines = [
            line.strip() for line in block.splitlines()[1:] if line.startswith("\t")
        ]

        self.assertIn("check-finalized", _target_block(text, ".PHONY"))
        self.assertEqual(block.splitlines()[0], "check-finalized:")
        for required_line in (
            "$(MAKE) auto-improve-readiness-report",
            "$(MAKE) check",
            "$(MAKE) auto-improve-readiness-report-body",
            "$(MAKE) generated-artifact-converge",
            "$(MAKE) release-closeout-post-check-finalizer-dry-run",
            "$(MAKE) release-closeout-fixed-point",
            "$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required",
        ):
            with self.subTest(required_line=required_line):
                self.assertIn(required_line, recipe_lines)

    def test_canonical_parity_guard_runs_fixed_point_and_strict_finalizer_check(self) -> None:
        text = _makefile_text()
        block = _target_block(text, "canonical-parity-guard")
        recipe_lines = [
            line.strip() for line in block.splitlines()[1:] if line.startswith("\t")
        ]

        self.assertIn("canonical-parity-guard", _target_block(text, ".PHONY"))
        self.assertEqual(
            recipe_lines,
            [
                "$(MAKE) generated-artifact-converge",
                "$(MAKE) release-closeout-post-check-finalizer-dry-run",
                "$(MAKE) release-closeout-fixed-point",
                "$(MAKE) tmp-json-clean",
                "$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required",
            ],
        )

    def test_release_evidence_converge_canonical_writers_are_ordered_with_fixed_point_last(
        self,
    ) -> None:
        text = _makefile_text()
        converge_block = _target_block(text, "release-evidence-converge")
        closeout_block = _target_block(text, "release-evidence-closeout")
        self.assertEqual(converge_block.splitlines()[0], "release-evidence-converge: release-evidence-converge-phase-3")
        self.assertEqual(closeout_block.splitlines()[0], "release-evidence-closeout: release-evidence-converge")
        converge_lines = _release_evidence_converge_expanded_recipe_lines(text)

        # Identify canonical writer targets (those using canonical_artifact_promote)
        canonical_writers: set[str] = set()
        for match in re.finditer(
            r"^(?P<target>[a-zA-Z0-9_-]+):(?P<deps>[^\n]*)(?P<body>(?:\n\t[^\n]*)*)",
            text,
            flags=re.MULTILINE,
        ):
            if "ops.scripts.canonical_artifact_promote" in match.group("body"):
                canonical_writers.add(match.group("target"))

        # Find all canonical writer occurrences in the converge recipe
        occurrences: list[tuple[str, int]] = []
        for i, line in enumerate(converge_lines):
            for writer in canonical_writers:
                invocation = f"$(MAKE) {writer}"
                if line == invocation or line.startswith(f"{invocation} "):
                    occurrences.append((writer, i))
                    break

        self.assertTrue(
            occurrences, "no canonical writers found in release-evidence-converge"
        )

        late_operator_refresh_writers = {"auto-improve-readiness-report-body"}
        sealing_occurrences = [
            (writer, index)
            for writer, index in occurrences
            if writer not in late_operator_refresh_writers
        ]
        self.assertTrue(
            sealing_occurrences,
            "no sealing-inventory canonical writers found in release-evidence-converge",
        )

        # The very last sealing-inventory canonical writer must be the fixed-point finalizer.
        last_writer, last_index = sealing_occurrences[-1]
        self.assertEqual(
            last_writer,
            "release-closeout-fixed-point",
            (
                "last sealing-inventory canonical writer must be "
                f"release-closeout-fixed-point, got {last_writer}"
            ),
        )

        # Fixed-point promotion must be the last sealing-inventory canonical writer;
        # only late operator refresh writers, read-only cleanup, and verification steps may follow.
        for writer, index in occurrences:
            if index > last_index and writer not in late_operator_refresh_writers:
                self.fail(
                    f"sealing-inventory canonical writer {writer} at index {index} "
                    "appears after release-closeout-fixed-point"
                )
        self.assertLessEqual(
            last_index,
            len(converge_lines) - 1,
            "batch manifest index out of range",
        )

        # The graph owns one writer pass; Make must not add an outer settle loop.
        fixed_point_count = sum(
            1 for w, _ in occurrences if w == "release-closeout-fixed-point"
        )
        self.assertEqual(fixed_point_count, 1)

    def test_release_evidence_refresh_fast_reuses_existing_expensive_evidence(
        self,
    ) -> None:
        text = _makefile_text()
        block = _target_block(text, "release-evidence-refresh-fast")
        recipe_lines = [
            line.strip()
            for line in block.splitlines()[1:]
            if line.startswith("\t") and not line.startswith("\t@echo")
        ]

        self.assertIn("release-evidence-refresh-fast", _target_block(text, ".PHONY"))
        self.assertEqual(block.splitlines()[0], "release-evidence-refresh-fast:")
        self.assertEqual(
            recipe_lines,
            [
                "$(MAKE) bootstrap-preflight",
                "$(MAKE) release-smoke-full-reuse",
                "$(MAKE) registry-preflight",
                "$(MAKE) auto-improve-readiness-report",
                "$(MAKE) tmp-json-clean",
                "$(MAKE) generated-artifact-converge",
                "$(MAKE) test-execution-summary-revision-rebind",
                "$(MAKE) learning-readiness-signoff-revalidation",
                "$(MAKE) tmp-json-clean",
                "$(MAKE) generated-artifact-converge",
                "$(MAKE) release-closeout-summary-conditional",
                "$(MAKE) release-evidence-cohort",
                "$(MAKE) learning-readiness-signoff-revalidation",
                "$(MAKE) release-evidence-dashboard-report",
            ],
        )
        self.assertNotIn("$(MAKE) release-smoke-full\n", block)
        self.assertNotIn("$(MAKE) test-execution-summary\n", block)
        self.assertNotIn("test-execution-summary-current-or-refresh", block)
        self.assertIn("test-execution-summary-revision-rebind", block)

    def test_release_evidence_cohort_targets_exist(self) -> None:
        text = _makefile_text()

        _assert_assignment_values(self, text, _RELEASE_EVIDENCE_COHORT_ASSIGNMENTS)
        _assert_make_target_contracts(
            self,
            text,
            _RELEASE_EVIDENCE_COHORT_TARGET_CONTRACTS,
        )
