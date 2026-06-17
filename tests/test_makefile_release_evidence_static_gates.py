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
    _makefile_text,
    _recipe_lines,
    _target_block,
)

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


REPORT_CONTRACT_CLOSEOUT_POLICY = Path("ops/policies/report-contract-closeout.json")
REPO_ROOT = Path(__file__).resolve().parents[1]


def _assert_ordered_subsequence(
    case: unittest.TestCase,
    observed: list[str],
    expected: list[str],
) -> None:
    cursor = 0
    for expected_line in expected:
        try:
            cursor = observed.index(expected_line, cursor) + 1
        except ValueError:
            case.fail(f"missing or out-of-order recipe line: {expected_line}")


def _release_evidence_converge_expanded_recipe_lines(text: str) -> list[str]:
    return [
        *_recipe_lines(text, "release-evidence-converge-phase-1"),
        *_recipe_lines(text, "release-evidence-converge-phase-2"),
        *_recipe_lines(text, "release-evidence-converge-phase-3"),
    ]


def _assert_release_closeout_manifest_phony_and_vars(case: unittest.TestCase, text: str) -> None:
    phony = _target_block(text, ".PHONY")
    for target in (
        "release-closeout-batch-manifest-promote",
        "release-closeout-batch-manifest-verify",
        "release-closeout-batch-manifest-replay-verify",
        "release-closeout-finality-attestation",
        "release-closeout-finality-verify",
        "release-evidence-closeout-self-check",
        "release-closeout-post-check-finalizer-dry-run",
        "release-closeout-post-check-finalizer-ci-artifact",
        "release-closeout-fixed-point",
    ):
        case.assertIn(target, phony)
    for assignment in (
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
        "RELEASE_CLOSEOUT_FIXED_POINT_MAX_ITERATIONS ?= 10",
        "RELEASE_CLOSEOUT_FIXED_POINT_INITIAL_TARGETS ?=",
        "OPERATOR_EVIDENCE_FINALITY_INITIAL_TARGETS ?= generated-artifact-index-body artifact-freshness external-report-action-matrix release-closeout-summary-report learning-readiness-signoff-revalidation release-evidence-cohort release-evidence-dashboard-report release-lane-summary release-clean-blocker-ledger release-closeout-batch-manifest-promote release-evidence-closeout-self-check",
        "OPERATOR_EVIDENCE_ARTIFACT_FRESHNESS_PROGRESS ?= jsonl-stable",
        "RELEASE_CLOSEOUT_FINALITY_ATTESTATION_OUT ?= ops/reports/release-closeout-finality-attestation.json",
        "RELEASE_CLOSEOUT_FINALITY_ATTESTATION_CANDIDATE_OUT ?= tmp/release-closeout-finality-attestation.candidate.json",
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
    ):
        case.assertIn(assignment, text)


def _assert_external_report_release_basis_targets(case: unittest.TestCase, text: str) -> None:
    phony = _target_block(text, ".PHONY")
    for target in (
        "external-report-reference-manifest-strict",
        "external-report-reference-manifest-release-check",
        "external-report-reference-manifest-settle",
        "external-report-action-matrix",
        "github-governance-live-drift",
        "github-governance-live-drift-check",
        "collaboration-governance",
        "external-report-lifecycle-refresh",
    ):
        case.assertIn(target, phony)
    for assignment in (
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
    ):
        case.assertIn(assignment, text)
    case.assertNotIn(
        "0a547950871ebd749bf6523cbc1d1a33a58a793168f3b6514b26a8b796869c93", text
    )
    case.assertNotIn(
        "EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_ENTRY_COUNT = $(if $(EXTERNAL_REPORT_REVIEW_BASIS_ZIP_ENTRY_COUNT),$(EXTERNAL_REPORT_REVIEW_BASIS_ZIP_ENTRY_COUNT),$(if $(EXTERNAL_REPORT_BASIS_ZIP_ENTRY_COUNT),$(EXTERNAL_REPORT_BASIS_ZIP_ENTRY_COUNT),1819))",
        text,
    )
    case.assertIn(
        '$(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_NAME),--basis-zip-name "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_NAME)",)',
        _target_block(text, "external-report-reference-manifest"),
    )
    strict_block = _target_block(text, "external-report-reference-manifest-strict")
    for needle in (
        '--basis-zip-path "$(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_PATH),$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_PATH),$(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH))"',
        "--mode strict_review_release",
        '$(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_NAME),--basis-zip-name "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_NAME)",)',
        '$(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_SHA256),--basis-zip-sha256 "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_SHA256)",)',
        '$(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_ENTRY_COUNT),--basis-zip-entry-count "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_ENTRY_COUNT)",)',
        '--current-distribution-zip-path "$(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH)"',
    ):
        case.assertIn(needle, strict_block)
    release_check_block = _target_block(text, "external-report-reference-manifest-release-check")
    case.assertIn("external-report-reference-manifest-strict", release_check_block)
    case.assertIn("EXTERNAL_REPORT_REFERENCE_MANIFEST_MODE=advisory", release_check_block)
    settle_block = _target_block(text, "external-report-reference-manifest-settle")
    case.assertIn("RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP", settle_block)
    case.assertIn(
        'EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"',
        settle_block,
    )
    case.assertIn(
        'EXTERNAL_REPORT_REVIEW_BASIS_ZIP_PATH="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"',
        settle_block,
    )
    case.assertGreaterEqual(
        settle_block.count("external-report-reference-manifest-release-check"),
        2,
    )
    case.assertIn(
        '$(PYTHON) -m ops.scripts.external_report_action_matrix --vault "$(VAULT)" --out "$(EXTERNAL_REPORT_ACTION_MATRIX_OUT)"',
        _target_block(text, "external-report-action-matrix"),
    )
    case.assertIn(
        'PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m ops.scripts.release.github_governance_live_drift --vault "$(VAULT)" --live-input "$(GITHUB_GOVERNANCE_LIVE_INPUT)" --out "$(GITHUB_GOVERNANCE_LIVE_DRIFT_OUT)"',
        _target_block(text, "github-governance-live-drift"),
    )
    case.assertIn(
        'PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m ops.scripts.release.github_governance_live_drift --vault "$(VAULT)" --live-input "$(GITHUB_GOVERNANCE_LIVE_INPUT)" --out "$(GITHUB_GOVERNANCE_LIVE_DRIFT_CHECK_OUT)"',
        _target_block(text, "github-governance-live-drift-check"),
    )
    case.assertIn("collaboration-governance: github-governance-live-drift", text)
    case.assertEqual(
        _recipe_lines(text, "external-report-lifecycle-refresh"),
        [
            "$(MAKE) external-report-reference-manifest-settle",
            "$(MAKE) generated-artifact-converge",
            "$(MAKE) release-closeout-summary-report",
            "$(MAKE) release-evidence-cohort",
            "$(MAKE) release-evidence-dashboard-report",
        ],
    )


def _assert_sealed_release_closeout_targets(case: unittest.TestCase, text: str) -> None:
    phony = _target_block(text, ".PHONY")
    for target in (
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
    ):
        case.assertIn(target, phony)
    case.assertIn(
        "RELEASE_CLOSEOUT_SEALED_DRY_RUN_ROOT ?= build/release/release-closeout-sealed-dry-run",
        text,
    )
    case.assertIn("RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_FLAGS ?= --no-fail", text)
    for assignment in (
        "RELEASE_CLOSEOUT_SEALED_EXTERNAL_MANIFEST_OUT ?= build/release/external-report-reference-manifest.json",
        "RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT ?= build/release/release-closeout-batch-manifest.json",
        "RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT ?= build/release/release-evidence-closeout-self-check.json",
        "RELEASE_CLOSEOUT_SEALED_OPERATOR_SUMMARY_OUT ?= build/release/operator-release-summary.json",
        "RELEASE_AUTO_PROMOTION_OPERATOR_SUMMARY_OUT ?= $(RELEASE_CLOSEOUT_SEALED_OPERATOR_SUMMARY_OUT)",
        "RELEASE_SEALED_POST_SEAL_ATTESTATION_OUT ?= build/release/release-sealed-post-seal-attestation.json",
        "RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_BATCH_MANIFEST ?= build/release/release-closeout-batch-manifest.json",
        "RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_EXTERNAL_MANIFEST ?= build/release/external-report-reference-manifest.json",
    ):
        case.assertIn(assignment, text)
    case.assertIn(
        '$(PYTHON) -m ops.scripts.release.release_smoke --vault "$(VAULT)" --profile fast --archive-out "$(RELEASE_DISTRIBUTION_ZIP_OUT)" --out "$(RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT)"',
        _target_block(text, "release-distribution-zip"),
    )
    sealed_block = _target_block(text, "release-evidence-closeout-sealed")
    for needle in (
        "$(MAKE) release-worktree-clean-check",
        "$(MAKE) release-package-current",
        "$(MAKE) release-seal-current",
    ):
        case.assertIn(needle, sealed_block)
    case.assertNotIn("$(MAKE) release-evidence-converge", sealed_block)
    case.assertNotIn("release-sealed-verify", sealed_block)
    sealed_core_sidecars_block = _target_block(text, "release-evidence-closeout-sealed-core-sidecars")
    for needle in (
        '--out "$(RELEASE_CLOSEOUT_SEALED_EXTERNAL_MANIFEST_OUT)"',
        "--mode strict_review_release",
        '--current-distribution-zip-path "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
        '--out "$(RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT)"',
        '--zip-metadata "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
        "ops.scripts.release_evidence_closeout_self_check",
        '--out "$(RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT)"',
        "$(MAKE) tmp-json-clean",
    ):
        case.assertIn(needle, sealed_core_sidecars_block)
    sealed_sidecars_block = _target_block(text, "release-evidence-closeout-sealed-sidecars")
    for needle in (
        "$(MAKE) release-evidence-closeout-sealed-core-sidecars",
        "ops.scripts.operator_release_summary",
        '--out "$(RELEASE_CLOSEOUT_SEALED_OPERATOR_SUMMARY_OUT)"',
        '--batch-manifest "$(RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT)"',
        '--self-check "$(RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT)"',
    ):
        case.assertIn(needle, sealed_sidecars_block)
    sealed_attestation_block = _target_block(text, "release-sealed-post-seal-attestation")
    case.assertIn("ops.scripts.release_sealed_post_seal_attestation", sealed_attestation_block)
    case.assertIn('--out "$(RELEASE_SEALED_POST_SEAL_ATTESTATION_OUT)"', sealed_attestation_block)
    case.assertIn('--run-manifest "$(RELEASE_RUN_MANIFEST_OUT)"', sealed_attestation_block)
    sealed_verify_block = _target_block(text, "release-sealed-verify")
    case.assertIn("$(MAKE) release-verify-current", sealed_verify_block)
    case.assertIn("$(MAKE) release-evidence-closeout-sealed-check", sealed_verify_block)
    sealed_check_block = _target_block(text, "release-evidence-closeout-sealed-check")
    case.assertIn("ops.scripts.release_closeout_sealed_rehearsal_check", sealed_check_block)
    case.assertIn('--batch-manifest "$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_BATCH_MANIFEST)"', sealed_check_block)
    case.assertIn('--external-manifest "$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_EXTERNAL_MANIFEST)"', sealed_check_block)
    sealed_dry_run = _target_block(text, "release-evidence-closeout-sealed-dry-run")
    for needle in (
        'RELEASE_DISTRIBUTION_ZIP_OUT="$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_DISTRIBUTION_ZIP)"',
        '--out "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_EXTERNAL_MANIFEST_OUT)"',
        "--mode strict_review_release",
        '--out "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_BATCH_MANIFEST_OUT)"',
        '--batch-manifest "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_BATCH_MANIFEST_OUT)"',
        '--external-manifest "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_EXTERNAL_MANIFEST_OUT)"',
        "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_FLAGS)",
    ):
        case.assertIn(needle, sealed_dry_run)
    case.assertIn(
        "RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_FLAGS=",
        _target_block(text, "release-evidence-closeout-sealed-dry-run-check"),
    )
    case.assertIn(
        "RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_FLAGS=--allow-blocked-preflight",
        _target_block(text, "release-authority-sealed-preflight"),
    )
    case.assertIn(
        "--candidate \"$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_OUT)\" --out \"$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_CANONICAL_OUT)\"",
        _target_block(text, "release-authority-sealed-preflight"),
    )


def _assert_batch_manifest_closeout_recipe_targets(case: unittest.TestCase, text: str) -> None:
    batch_promote = _target_block(text, "release-closeout-batch-manifest-promote")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.release_closeout_batch_manifest --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_CANDIDATE_OUT)" $(if $(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA),--zip-metadata "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA)" --zip-timestamp-timezone "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE)",) $(if $(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP),--distribution-zip "$(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP)",)',
        batch_promote,
    )
    case.assertIn("ops.scripts.canonical_artifact_promote", batch_promote)
    case.assertIn(
        '$(PYTHON) -m ops.scripts.release_closeout_batch_manifest --vault "$(VAULT)" --check $(if $(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA),--zip-metadata "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA)" --zip-timestamp-timezone "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE)",) $(if $(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP),--distribution-zip "$(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP)",)',
        _target_block(text, "release-closeout-batch-manifest-replay-verify"),
    )
    fixed_point = _target_block(text, "release-closeout-fixed-point")
    for needle in (
        '$(PYTHON) -m ops.scripts.release_closeout_fixed_point --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_FIXED_POINT_CANDIDATE_OUT)" --max-iterations "$(RELEASE_CLOSEOUT_FIXED_POINT_MAX_ITERATIONS)"',
        "--schema ops/schemas/release-closeout-fixed-point.schema.json",
        "--bootstrap-post-promote",
        '--initial-target "$(target)"',
        "--baseline-before-first-iteration",
        "$(MAKE) external-report-action-matrix",
        "$(MAKE) release-closeout-finality-attestation",
    ):
        case.assertIn(needle, fixed_point)
    fixed_point_lines = _recipe_lines(text, "release-closeout-fixed-point")
    bootstrap_index = next(
        index
        for index, line in enumerate(fixed_point_lines)
        if "--bootstrap-post-promote" in line
    )
    matrix_index = fixed_point_lines.index("$(MAKE) external-report-action-matrix")
    attestation_index = fixed_point_lines.index(
        "$(MAKE) release-closeout-finality-attestation"
    )
    case.assertLess(bootstrap_index, matrix_index)
    case.assertLess(matrix_index, attestation_index)
    post_check_dry_run = _target_block(text, "release-closeout-post-check-finalizer-dry-run")
    case.assertIn('--dry-run --out "$(RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_OUT)"', post_check_dry_run)
    case.assertIn("$(RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS)", post_check_dry_run)
    post_check_artifact = _target_block(text, "release-closeout-post-check-finalizer-ci-artifact")
    case.assertIn("--recommended-targets-out", post_check_artifact)
    case.assertIn("--plan-out", post_check_artifact)
    finality = _target_block(text, "release-closeout-finality-attestation")
    case.assertIn("ops.scripts.release_closeout_finality_attestation", finality)
    case.assertIn("--schema ops/schemas/release-closeout-finality-attestation.schema.json", finality)
    case.assertIn("--verify", _target_block(text, "release-closeout-finality-verify"))
    self_check = _target_block(text, "release-evidence-closeout-self-check")
    for needle in (
        "$(PYTHON) -m ops.scripts.release_evidence_closeout_self_check",
        '--batch-manifest "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_OUT)"',
        '--out "$(RELEASE_EVIDENCE_CLOSEOUT_SELF_CHECK_OUT)"',
    ):
        case.assertIn(needle, self_check)


def _assert_release_audit_and_post_seal_targets(case: unittest.TestCase, text: str) -> None:
    phony = _target_block(text, ".PHONY")
    case.assertIn("release-audit-pack", phony)
    audit_pack = _target_block(text, "release-audit-pack")
    case.assertIn("ops.scripts.release_audit_pack", audit_pack)
    case.assertIn(
        "$(if $(RELEASE_AUDIT_PACK_INCLUDE_OPTIONAL_PAYLOADS),--include-optional-payloads,)",
        audit_pack,
    )
    case.assertIn(
        '$(PYTHON) -m ops.scripts.release_post_seal_attestation build --vault "$(VAULT)" --out "$(RELEASE_POST_SEAL_ATTESTATION_OUT)" $(if $(RELEASE_POST_SEAL_ATTESTATION_SOURCE_ZIP),--source-zip-path "$(RELEASE_POST_SEAL_ATTESTATION_SOURCE_ZIP)",) $(if $(RELEASE_POST_SEAL_ATTESTATION_BATCH_MANIFEST),--batch-manifest-path "$(RELEASE_POST_SEAL_ATTESTATION_BATCH_MANIFEST)",) $(if $(RELEASE_POST_SEAL_ATTESTATION_SELF_CHECK),--self-check-path "$(RELEASE_POST_SEAL_ATTESTATION_SELF_CHECK)",) $(if $(RELEASE_POST_SEAL_ATTESTATION_OPERATOR_SUMMARY),--operator-summary-path "$(RELEASE_POST_SEAL_ATTESTATION_OPERATOR_SUMMARY)",)',
        _target_block(text, "release-post-seal-attestation"),
    )
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

        self.assertIn("release-closeout-summary", _target_block(text, ".PHONY"))
        self.assertIn(
            "RELEASE_CLOSEOUT_SUMMARY_OUT ?= ops/reports/release-closeout-summary.json",
            text,
        )
        self.assertIn(
            "RELEASE_CLOSEOUT_SUMMARY_CANDIDATE_OUT ?= tmp/release-closeout-summary.candidate.json",
            text,
        )
        self.assertIn("RELEASE_CLOSEOUT_PROFILE ?= base", text)
        self.assertIn(
            '$(PYTHON) -m ops.scripts.release_closeout_summary --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_SUMMARY_CANDIDATE_OUT)" --profile "$(RELEASE_CLOSEOUT_PROFILE)"',
            _target_block(text, "release-closeout-summary"),
        )
        self.assertIn(
            "ops.scripts.canonical_artifact_promote",
            _target_block(text, "release-closeout-summary"),
        )

    def test_head_aligned_evidence_converge_aliases_post_commit_check_only_finalizer(
        self,
    ) -> None:
        text = _makefile_text()

        self.assertIn("head-aligned-evidence-converge", _target_block(text, ".PHONY"))
        alias_block = _target_block(text, "head-aligned-evidence-converge")
        self.assertTrue(
            alias_block.startswith(
                "head-aligned-evidence-converge: release-post-commit-finalize"
            )
        )
        self.assertEqual(
            _recipe_lines(text, "head-aligned-evidence-converge"),
            [
                '@echo "head-aligned-evidence-converge is a compatibility alias; prefer release-post-commit-finalize."',
            ],
        )
        finalizer_lines = _recipe_lines(text, "release-post-commit-finalize")
        _assert_ordered_subsequence(
            self,
            finalizer_lines,
            [
                '$(PYTHON) -m ops.scripts.release.release_post_commit_finalizer --vault "$(VAULT)" --mode snapshot --out "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"',
                "$(MAKE) script-output-surfaces-check",
                "$(MAKE) release-smoke-fast-current-check",
                "$(MAKE) test-execution-summary-current-check",
                "$(MAKE) test-execution-summary-full-current-check",
                "$(MAKE) sync-public-policy-check",
                "$(MAKE) public-check-summary-current-check",
                "$(MAKE) artifact-freshness-check",
                '$(PYTHON) -m ops.scripts.release.release_post_commit_finalizer --vault "$(VAULT)" --mode verify --previous "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)" --out "$(RELEASE_POST_COMMIT_FINALIZATION_OUT)" --fail-on-attention',
                "$(MAKE) release-closeout-finality-verify",
            ],
        )
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
        self.assertEqual(finalizer_lines.count("$(MAKE) release-closeout-finality-verify"), 1)
        self.assertIn("--mode verify", finalizer_lines[-2])
        self.assertEqual(finalizer_lines[-1], "$(MAKE) release-closeout-finality-verify")

    def test_release_closeout_summary_report_target_is_write_only(self) -> None:
        text = _makefile_text()

        self.assertIn("release-closeout-summary-report", _target_block(text, ".PHONY"))
        self.assertIn(
            "release-closeout-summary-conditional", _target_block(text, ".PHONY")
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.release_closeout_summary --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_SUMMARY_CANDIDATE_OUT)" --profile "$(RELEASE_CLOSEOUT_PROFILE)" --no-fail',
            _target_block(text, "release-closeout-summary-report"),
        )
        self.assertIn(
            "ops.scripts.canonical_artifact_promote",
            _target_block(text, "release-closeout-summary-report"),
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.release_closeout_summary --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_SUMMARY_CANDIDATE_OUT)" --profile "$(RELEASE_CLOSEOUT_PROFILE)" --allow-conditional',
            _target_block(text, "release-closeout-summary-conditional"),
        )
        self.assertIn(
            "ops.scripts.canonical_artifact_promote",
            _target_block(text, "release-closeout-summary-conditional"),
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
        phony = _target_block(text, ".PHONY")
        target_block = _target_block(text, "freshness-source-identity-converge")

        self.assertIn("freshness-source-identity-converge", phony)
        self.assertEqual(
            _recipe_lines(text, "freshness-source-identity-converge"),
            [
                "$(MAKE) artifact-freshness-refresh-check",
                "$(MAKE) generated-artifact-index",
                "$(MAKE) artifact-freshness-refresh-check",
                "$(MAKE) release-finality-resettle-current-or-refresh",
            ],
        )
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
                '$(MAKE) generated-artifact-finality-suffix ARTIFACT_FRESHNESS_PROGRESS="$(OPERATOR_EVIDENCE_ARTIFACT_FRESHNESS_PROGRESS)"',
                "$(MAKE) release-closeout-summary-report",
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

        self.assertIn("release-clean-lane-evidence-review", _target_block(text, ".PHONY"))
        self.assertIn(
            "RELEASE_CLEAN_LANE_EVIDENCE_REVIEW_OUT ?= tmp/release-clean-lane-evidence-review.json",
            text,
        )
        block = _target_block(text, "release-clean-lane-evidence-review")
        self.assertIn("ops.scripts.release_clean_lane_evidence_review", block)
        self.assertIn('--closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)"', block)
        self.assertIn('--out "$(RELEASE_CLEAN_LANE_EVIDENCE_REVIEW_OUT)"', block)

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
        self.assertEqual(recipe_lines[0], "$(MAKE) release-evidence-converge-lane-guard")
        _assert_ordered_subsequence(
            self,
            recipe_lines,
            [
                "$(MAKE) release-evidence-converge-lane-guard",
                "$(MAKE) refresh-generated-core",
                "$(MAKE) bootstrap-preflight",
                "$(MAKE) registry-preflight",
                "$(MAKE) static",
                "$(MAKE) report-schema-samples-check",
                "$(MAKE) release-smoke-full",
                "$(MAKE) release-source-package-check",
                "$(MAKE) test-execution-summary-report-contract-refresh",
                "$(MAKE) test-execution-summary-full-refresh",
                "$(MAKE) test-execution-summary-current-or-refresh",
                "$(MAKE) release-freshness-sensitive-evidence-refresh",
                "$(MAKE) public-check-summary",
                "$(MAKE) remediation-backlog",
                "$(MAKE) learning-readiness-signoff-revalidation",
                "$(MAKE) release-evidence-cohort-report RELEASE_EVIDENCE_COHORT_POLICY=strict_same_fingerprint",
                "$(MAKE) release-evidence-dashboard-report",
                "$(MAKE) release-lane-summary",
                "$(MAKE) release-clean-blocker-ledger",
                "$(MAKE) release-closeout-post-check-finalizer-dry-run",
                "$(MAKE) release-closeout-fixed-point",
                "$(MAKE) tmp-json-clean",
                "$(MAKE) release-closeout-finality-verify",
            ],
        )
        self.assertEqual(recipe_lines.count("$(MAKE) test-execution-summary-full-refresh"), 1)
        self.assertGreaterEqual(recipe_lines.count("$(MAKE) generated-artifact-converge"), 2)
        self.assertEqual(recipe_lines[-1], "$(MAKE) release-closeout-finality-verify")
        self.assertNotIn("$(MAKE) release-closeout-batch-manifest-promote", recipe_lines)
        self.assertNotIn("$(MAKE) release-evidence-closeout-self-check", recipe_lines)

    def test_release_evidence_converge_uses_fixed_point_finalizer(self) -> None:
        text = _makefile_text()
        recipe_lines = _release_evidence_converge_expanded_recipe_lines(text)

        self.assertTrue(recipe_lines, "release-evidence-converge has no recipe lines")

        fixed_point_index = next(
            (
                i
                for i, line in enumerate(recipe_lines)
                if line == "$(MAKE) release-closeout-fixed-point"
            ),
            None,
        )
        self.assertIsNotNone(fixed_point_index)
        assert fixed_point_index is not None
        self.assertEqual(
            recipe_lines[fixed_point_index + 1], "$(MAKE) operator-release-summary"
        )
        self.assertEqual(
            recipe_lines[fixed_point_index + 2], "$(MAKE) generated-artifact-converge"
        )
        self.assertEqual(
            recipe_lines[fixed_point_index + 3], "$(MAKE) release-closeout-fixed-point"
        )
        self.assertEqual(
            recipe_lines[fixed_point_index + 4],
            "$(MAKE) tmp-json-clean",
        )
        self.assertEqual(
            recipe_lines[fixed_point_index + 5],
            "$(MAKE) release-closeout-finality-verify",
        )
        self.assertNotIn(
            "$(MAKE) release-closeout-batch-manifest-promote", recipe_lines
        )
        self.assertNotIn("$(MAKE) release-evidence-closeout-self-check", recipe_lines)

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
        self.assertIn("release-finality-resettle-current-or-refresh", _target_block(text, ".PHONY"))
        self.assertIn("release-terminal-finality", _target_block(text, ".PHONY"))
        self.assertEqual(
            recipe_lines,
            [
                "$(MAKE) workflow-dependency-planner",
                "$(MAKE) release-authority-sealed-preflight",
                "$(MAKE) release-terminal-finality",
            ],
        )
        self.assertEqual(
            terminal_lines,
            [
                "$(MAKE) generated-artifact-finality-suffix",
                "$(MAKE) release-closeout-summary-report",
                "$(MAKE) release-closeout-fixed-point",
                "$(MAKE) tmp-json-clean",
                "$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required",
                "$(MAKE) tmp-json-clean",
                "$(MAKE) release-closeout-finality-verify",
            ],
        )
        self.assertEqual(
            _recipe_lines(text, "release-finality-resettle-current-check"),
            [
                "$(MAKE) tmp-json-clean",
                "$(MAKE) release-closeout-batch-manifest-replay-verify",
                "$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required",
                "$(MAKE) tmp-json-clean",
                "$(MAKE) release-closeout-finality-verify",
            ],
        )
        current_or_refresh_block = _target_block(
            text,
            "release-finality-resettle-current-or-refresh",
        )
        self.assertIn("$(MAKE) release-finality-resettle-current-check", current_or_refresh_block)
        self.assertIn("$(MAKE) release-finality-resettle", current_or_refresh_block)
        self.assertNotIn("$(MAKE) release-evidence-converge", recipe_lines)
        self.assertEqual(terminal_lines[-1], "$(MAKE) release-closeout-finality-verify")

    def test_check_finalized_runs_post_check_dry_run_before_mutating_finalizer(self) -> None:
        text = _makefile_text()
        block = _target_block(text, "check-finalized")
        recipe_lines = [
            line.strip() for line in block.splitlines()[1:] if line.startswith("\t")
        ]

        self.assertIn("check-finalized", _target_block(text, ".PHONY"))
        self.assertEqual(block.splitlines()[0], "check-finalized:")
        self.assertEqual(
            recipe_lines,
            [
                "$(MAKE) auto-improve-readiness-report",
                "$(MAKE) check",
                "$(MAKE) auto-improve-readiness-report-body",
                "$(MAKE) generated-artifact-converge",
                "$(MAKE) release-closeout-post-check-finalizer-dry-run",
                "$(MAKE) release-closeout-fixed-point",
                "$(MAKE) tmp-json-clean",
                "$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required",
                "$(MAKE) release-closeout-finality-verify",
            ],
        )

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

        # Fixed-point owns iteration internally; Make should keep any extra
        # fixed-point calls bounded instead of hand-rolling an outer loop.
        fixed_point_count = sum(
            1 for w, _ in occurrences if w == "release-closeout-fixed-point"
        )
        self.assertGreaterEqual(fixed_point_count, 1)
        self.assertLessEqual(fixed_point_count, 2)

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
                "$(MAKE) test-execution-summary-reuse",
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

    def test_release_evidence_cohort_targets_exist(self) -> None:
        text = _makefile_text()

        self.assertIn("release-evidence-cohort", _target_block(text, ".PHONY"))
        self.assertIn("release-evidence-cohort-report", _target_block(text, ".PHONY"))
        self.assertIn("release-evidence-cohort-preseal-refresh", _target_block(text, ".PHONY"))
        self.assertIn("release-evidence-dashboard", _target_block(text, ".PHONY"))
        self.assertIn(
            "release-evidence-dashboard-report", _target_block(text, ".PHONY")
        )
        self.assertIn("release-lane-summary", _target_block(text, ".PHONY"))
        self.assertIn("release-clean-blocker-ledger", _target_block(text, ".PHONY"))
        self.assertIn("release-risk-taxonomy-matrix", _target_block(text, ".PHONY"))
        self.assertIn(
            "RELEASE_EVIDENCE_DASHBOARD_OUT ?= ops/reports/release-evidence-dashboard.json",
            text,
        )
        self.assertIn(
            "RELEASE_EVIDENCE_DASHBOARD_CANDIDATE_OUT ?= tmp/release-evidence-dashboard.candidate.json",
            text,
        )
        self.assertIn(
            "RELEASE_LANE_SUMMARY_OUT ?= ops/reports/release-lane-summary.json", text
        )
        self.assertIn(
            "RELEASE_LANE_SUMMARY_CANDIDATE_OUT ?= tmp/release-lane-summary.candidate.json",
            text,
        )
        self.assertIn(
            "RELEASE_CLEAN_BLOCKER_LEDGER_OUT ?= ops/reports/release-clean-blocker-ledger.json",
            text,
        )
        self.assertIn(
            "RELEASE_CLEAN_BLOCKER_LEDGER_CANDIDATE_OUT ?= tmp/release-clean-blocker-ledger.candidate.json",
            text,
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.release_evidence_dashboard --vault "$(VAULT)" --out "$(RELEASE_EVIDENCE_DASHBOARD_CANDIDATE_OUT)"',
            _target_block(text, "release-evidence-dashboard"),
        )
        self.assertIn(
            "ops.scripts.canonical_artifact_promote",
            _target_block(text, "release-evidence-dashboard"),
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.release_evidence_dashboard --vault "$(VAULT)" --out "$(RELEASE_EVIDENCE_DASHBOARD_CANDIDATE_OUT)" --no-fail',
            _target_block(text, "release-evidence-dashboard-report"),
        )
        self.assertIn(
            "ops.scripts.canonical_artifact_promote",
            _target_block(text, "release-evidence-dashboard-report"),
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.release_lane_summary --vault "$(VAULT)" --out "$(RELEASE_LANE_SUMMARY_CANDIDATE_OUT)"',
            _target_block(text, "release-lane-summary"),
        )
        self.assertIn(
            "ops.scripts.canonical_artifact_promote",
            _target_block(text, "release-lane-summary"),
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.release_clean_blocker_ledger --vault "$(VAULT)" --out "$(RELEASE_CLEAN_BLOCKER_LEDGER_CANDIDATE_OUT)"',
            _target_block(text, "release-clean-blocker-ledger"),
        )
        self.assertIn(
            "ops.scripts.canonical_artifact_promote",
            _target_block(text, "release-clean-blocker-ledger"),
        )
        self.assertIn(
            "RELEASE_RISK_TAXONOMY_MATRIX_OUT ?= ops/reports/release-risk-taxonomy-matrix.json",
            text,
        )
        self.assertIn(
            "RELEASE_RISK_TAXONOMY_MATRIX_MD_OUT ?= ops/reports/release-risk-taxonomy-matrix.md",
            text,
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.release_risk_taxonomy_matrix --vault "$(VAULT)"',
            _target_block(text, "release-risk-taxonomy-matrix"),
        )
        self.assertIn(
            "ops.scripts.canonical_artifact_promote",
            _target_block(text, "release-risk-taxonomy-matrix"),
        )
        self.assertIn(
            "RELEASE_EVIDENCE_COHORT_OUT ?= ops/reports/release-evidence-cohort.json",
            text,
        )
        self.assertIn(
            "RELEASE_EVIDENCE_COHORT_STAGING_OUT ?= tmp/release-evidence-cohort.candidate.json",
            text,
        )
        self.assertIn(
            "RELEASE_EVIDENCE_COHORT_DIAGNOSTIC_OUT ?= tmp/release-evidence-cohort-check.json",
            text,
        )
        self.assertIn(
            "RELEASE_EVIDENCE_COHORT_POLICY ?= allowed_divergence_with_explicit_risk",
            text,
        )
        self.assertIn(
            "RELEASE_EVIDENCE_COHORT_PROVENANCE_MODE ?= embedded_currentness",
            text,
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.release_evidence_cohort --vault "$(VAULT)" --out "$(RELEASE_EVIDENCE_COHORT_STAGING_OUT)" --profile "$(RELEASE_CLOSEOUT_PROFILE)" --cohort-policy "$(RELEASE_EVIDENCE_COHORT_POLICY)" --provenance-mode "$(RELEASE_EVIDENCE_COHORT_PROVENANCE_MODE)"',
            _target_block(text, "release-evidence-cohort"),
        )
        self.assertIn(
            "ops.scripts.canonical_artifact_promote",
            _target_block(text, "release-evidence-cohort"),
        )
        cohort_report_block = _target_block(text, "release-evidence-cohort-report")
        self.assertIn(
            '$(PYTHON) -m ops.scripts.release_evidence_cohort --vault "$(VAULT)" --out "$(RELEASE_EVIDENCE_COHORT_STAGING_OUT)" --profile "$(RELEASE_CLOSEOUT_PROFILE)" --cohort-policy "$(RELEASE_EVIDENCE_COHORT_POLICY)" --provenance-mode "$(RELEASE_EVIDENCE_COHORT_PROVENANCE_MODE)"',
            cohort_report_block,
        )
        self.assertIn("ops.scripts.canonical_artifact_promote", cohort_report_block)
        self.assertNotIn("--require-clean-lane", cohort_report_block)
        self.assertNotIn("--fail-on-attention", cohort_report_block)
        preseal_refresh_block = _target_block(text, "release-evidence-cohort-preseal-refresh")
        self.assertIn(
            '--cohort-policy strict_same_fingerprint',
            preseal_refresh_block,
        )
        self.assertIn(
            "ops.scripts.canonical_artifact_promote",
            preseal_refresh_block,
        )
        self.assertNotIn("--require-clean-lane", preseal_refresh_block)
        self.assertNotIn("--fail-on-attention", preseal_refresh_block)
        self.assertNotIn("cp ", _target_block(text, "release-evidence-cohort"))
        self.assertIn(
            '$(PYTHON) -m ops.scripts.release_evidence_cohort --vault "$(VAULT)" --out "$(RELEASE_EVIDENCE_COHORT_DIAGNOSTIC_OUT)" --profile "$(RELEASE_CLOSEOUT_PROFILE)" --cohort-policy strict_same_fingerprint --provenance-mode "$(RELEASE_EVIDENCE_COHORT_PROVENANCE_MODE)"',
            _target_block(text, "release-evidence-cohort-check"),
        )
        self.assertIn(
            "--require-clean-lane", _target_block(text, "release-evidence-cohort-check")
        )
        self.assertNotIn(
            "$(RELEASE_EVIDENCE_COHORT_OUT)",
            _target_block(text, "release-evidence-cohort-check"),
        )
