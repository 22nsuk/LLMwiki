from __future__ import annotations

import configparser
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

import pytest
from ops.scripts.test_lane_registry_runtime import (
    authoritative_markers,
    compatibility_map,
    compatibility_names,
    documentation_authority,
    documentation_out_of_scope,
    lane_ci_entrypoint,
    lane_ci_steps,
    load_registry,
    marker_semantics,
    pack_by_id,
    pack_ci_entrypoint,
    pack_ci_steps,
    pack_mark_expr,
    pack_selectors,
    pack_summary_suite,
    selection_by_make_target,
)

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


MAKEFILE = Path("Makefile")
README = Path("README.md")
DOCS_DEVELOPMENT = Path("docs/development.md")
DOCS_CBM = Path("docs/codebase-memory-mcp.md")
DOCS_RELEASE = Path("docs/release.md")
CONFTEST = Path("tests/conftest.py")
PYTEST_INI = Path("pytest.ini")
CI_WORKFLOW = Path(".github/workflows/ci.yml")
REPORT_CONTRACT_CLOSEOUT_POLICY = Path("ops/policies/report-contract-closeout.json")
REPO_ROOT = Path(__file__).resolve().parents[1]


def _test_lane_registry() -> dict[str, object]:
    return load_registry(REPO_ROOT)


def _makefile_text() -> str:
    text = MAKEFILE.read_text(encoding="utf-8")
    for mk_file in sorted(REPO_ROOT.glob("mk/*.mk")):
        text += "\n" + mk_file.read_text(encoding="utf-8")
    return text


def _target_block(text: str, target: str) -> str:
    if target == ".PHONY":
        matches = list(re.finditer(
            rf"^{re.escape(target)}:(?P<deps>[^\n]*)(?P<body>(?:\n\t[^\n]*)*)",
            text,
            flags=re.MULTILINE,
        ))
        if not matches:
            raise AssertionError(f"missing Makefile target: {target}")
        return "\n".join(m.group(0) for m in matches)
    match = re.search(
        rf"^{re.escape(target)}:(?P<deps>[^\n]*)(?P<body>(?:\n\t[^\n]*)*)",
        text,
        flags=re.MULTILINE,
    )
    if match is None:
        raise AssertionError(f"missing Makefile target: {target}")
    return match.group(0)


def _recipe_lines(text: str, target: str) -> list[str]:
    block = _target_block(text, target)
    return [line.strip() for line in block.splitlines()[1:] if line.startswith("\t")]


def _target_dependencies(text: str, target: str) -> tuple[str, ...]:
    header = _target_block(text, target).splitlines()[0]
    _, _, raw_deps = header.partition(":")
    return tuple(raw_deps.split())


def _assert_target_depends_on(case: unittest.TestCase, text: str, target: str, dependency: str) -> None:
    case.assertIn(dependency, _target_dependencies(text, target))


def _assert_assignment_exists(
    case: unittest.TestCase,
    text: str,
    variable: str,
    expected_value: str | None = None,
) -> str:
    value = _makefile_assignment_value(text, variable)
    if expected_value is not None:
        case.assertEqual(value, expected_value)
    return value


def _assert_assignment_not_exists(case: unittest.TestCase, text: str, variable: str) -> None:
    with case.assertRaises(AssertionError):
        _makefile_assignment_value(text, variable)


def _assert_recipe_contains_tokens(
    case: unittest.TestCase,
    text: str,
    target: str,
    required_tokens: tuple[str, ...],
) -> None:
    block = _target_block(text, target)
    missing = [token for token in required_tokens if token not in block]
    case.assertEqual(missing, [], f"{target} recipe missing required tokens")


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
    case.assertEqual(
        _recipe_lines(text, "external-report-reference-manifest-settle"),
        [
            "$(MAKE) external-report-reference-manifest-release-check",
            "$(MAKE) external-report-reference-manifest-release-check",
        ],
    )
    case.assertIn(
        '$(PYTHON) -m ops.scripts.external_report_action_matrix --vault "$(VAULT)" --out "$(EXTERNAL_REPORT_ACTION_MATRIX_OUT)"',
        _target_block(text, "external-report-action-matrix"),
    )
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
        '$(PYTHON) -m ops.scripts.release_smoke --vault "$(VAULT)" --profile fast --archive-out "$(RELEASE_DISTRIBUTION_ZIP_OUT)" --out "$(RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT)"',
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
        "$(MAKE) release-closeout-finality-attestation",
    ):
        case.assertIn(needle, fixed_point)
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


def _assert_supply_chain_make_variables(case: unittest.TestCase, text: str) -> None:
    for assignment in (
        "SUPPLY_CHAIN_GATE_OUT ?= ops/reports/supply-chain-gate-report.json",
        "SECURITY_ADVISORIES_OUT ?= ops/reports/security-advisories.json",
        "SBOM_EXPORT_MAPPING_OUT ?= ops/reports/sbom-export-mapping.json",
        "SBOM_READINESS_GATE_OUT ?= ops/reports/sbom-readiness-gate-report.json",
        "SUPPLY_CHAIN_ARTIFACT_MODEL_OUT ?= ops/reports/supply-chain-artifact-model.json",
        "CYCLONEDX_SBOM_OUT ?= ops/reports/cyclonedx-bom.json",
        "SPDX_SBOM_OUT ?= ops/reports/spdx-sbom.json",
        "OPENVEX_DRAFT_OUT ?= ops/reports/openvex-draft.json",
        "IN_TOTO_STATEMENT_OUT ?= ops/reports/in-toto-statement.json",
        "SIGSTORE_BUNDLE_OUT ?= ops/reports/sigstore-bundle-verification.json",
        "SUPPLY_CHAIN_BENCHMARK_OUT ?= ops/reports/supply-chain-benchmark.json",
        "UV ?= uv",
        "STRUCTURAL_COMPLEXITY_BUDGET_OUT ?= ops/reports/structural-complexity-budget.json",
        "GENERATED_ARTIFACT_INDEX_OUT ?= ops/reports/generated-artifact-index.json",
        "GENERATED_ARTIFACT_INDEX_CANDIDATE_OUT ?= tmp/generated-artifact-index.candidate.json",
        "ARTIFACT_FRESHNESS_OUT ?= ops/reports/artifact-freshness-report.json",
        "ARTIFACT_FRESHNESS_CANDIDATE_OUT ?= tmp/artifact-freshness-report.candidate.json",
        "ARTIFACT_FRESHNESS_CHECK_OUT ?= tmp/artifact-freshness-report-check.json",
        "ARTIFACT_FRESHNESS_MTIME_SOURCE ?= embedded_currentness",
        "ARTIFACT_FRESHNESS_ZIP_METADATA ?=",
        "ARTIFACT_FRESHNESS_PROGRESS ?= none",
        "ARTIFACT_RELOCATION_AUDIT_OUT ?= ops/operator/artifact-relocation-audit.json",
        "ARTIFACT_RELOCATION_AUDIT_CANDIDATE_OUT ?= tmp/artifact-relocation-audit.candidate.json",
        "ARCHIVE_EXECUTION_MANIFEST_OUT ?= tmp/archive-execution-manifest.json",
        "ARCHIVE_EXECUTION_MANIFEST_SOURCE ?= tmp/archive-execution-manifest.json",
        "ARCHIVE_EXECUTION_OPERATOR_CONFIRMATION ?=",
        "RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_OUT ?= ops/reports/raw-registry-cross-environment-matrix.json",
        "RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_LINUX_OUT ?= ops/reports/raw-registry-cross-environment-matrix-linux-c-utf8.json",
        "RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_WINDOWS_OUT ?= ops/reports/raw-registry-cross-environment-matrix-windows-utf8.json",
        "RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_MACOS_OUT ?= ops/reports/raw-registry-cross-environment-matrix-macos-utf8.json",
        "RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_OUT ?= ops/reports/raw-registry-cross-environment-evidence-bundle.json",
        "STRUCTURAL_COMPLEXITY_BUDGET_TOUCHED_OUT ?= ops/reports/structural-complexity-budget-touched.json",
        "CHANGED_FILES_MANIFEST ?=",
        "STRUCTURAL_COMPLEXITY_BUDGET_TARGETS ?=",
        "REVIEW_ARCHIVE_OUT ?= build/review/llm-wiki-vnext-review.zip",
        "REVIEW_ARCHIVE_REPORT_OUT ?= ops/reports/review-archive-report.json",
        "REVIEW_ARCHIVE_PROFILE ?= clean",
        "CLOSURE_REGISTRY_ENVELOPE_REGISTRY ?= all",
    ):
        case.assertIn(assignment, text)


def _assert_supply_chain_target_names(case: unittest.TestCase, text: str) -> None:
    for target in (
        "security-advisories:",
        "complexity-budget:",
        "complexity-budget-check:",
        "complexity-budget-touched-check:",
        "artifact-freshness:",
        "artifact-freshness-check:",
        "artifact-freshness-refresh-check:",
        "artifact-relocation-audit:",
        "generated-artifact-converge:",
        "generated-artifact-index:",
        "generated-artifact-index-body:",
        "archive-execution-manifest:",
        "archive-execution-manifest-report:",
        "archive-execution-manifest-apply:",
        "archive-execution-manifest-defer:",
        "archive-execution-manifest-rollback:",
        "raw-registry-cross-environment-matrix:",
        "raw-registry-cross-environment-profile-matrices:",
        "raw-registry-cross-environment-evidence-bundle:",
        "raw-registry-cross-environment-evidence-bundle-check:",
        "review-archive:",
        "closure-registry-envelope:",
        "supply-chain-artifact-model:",
        "spdx-sbom:",
        "in-toto-statement:",
        "sigstore-bundle:",
        "supply-chain-benchmark:",
        "sbom-export-mapping:",
        "supply-chain-artifacts-cached:",
        "uv-lock-check:",
    ):
        case.assertIn(target, text)
    case.assertIn(
        "generated-artifact-index: artifact-relocation-audit closure-registry-envelope manual-mutate-defect-registry release-risk-taxonomy-matrix generated-artifact-index-body",
        text,
    )
    profile_matrix_block = _target_block(text, "raw-registry-cross-environment-profile-matrices")
    for needle in (
        '$(PYTHON) -m ops.scripts.raw_registry_cross_environment_matrix --vault "$(VAULT)" --stored-report "$(RAW_REGISTRY_PREFLIGHT_OUT)" --profile linux-c-utf8 --out "$(RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_LINUX_OUT)"',
        '$(PYTHON) -m ops.scripts.raw_registry_cross_environment_matrix --vault "$(VAULT)" --stored-report "$(RAW_REGISTRY_PREFLIGHT_OUT)" --profile windows-utf8 --out "$(RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_WINDOWS_OUT)"',
        '$(PYTHON) -m ops.scripts.raw_registry_cross_environment_matrix --vault "$(VAULT)" --stored-report "$(RAW_REGISTRY_PREFLIGHT_OUT)" --profile macos-utf8 --out "$(RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_MACOS_OUT)"',
    ):
        case.assertIn(needle, profile_matrix_block)
    case.assertIn(
        "raw-registry-cross-environment-evidence-bundle: raw-registry-cross-environment-profile-matrices",
        text,
    )


def _assert_sbom_supply_chain_recipes(case: unittest.TestCase, text: str) -> None:
    case.assertIn(
        '$(PYTHON) -m ops.scripts.sbom_export_mapping --vault "$(VAULT)" --out "$(SBOM_EXPORT_MAPPING_OUT)"',
        _target_block(text, "sbom-export-mapping"),
    )
    for dependency in (
        "sbom-readiness-check: sbom-export-mapping",
        "cyclonedx-sbom: sbom-readiness-check",
        "openvex-draft: cyclonedx-sbom",
        "release-sbom-clean: release-provenance-clean sbom-readiness-check",
        "openvex-draft-cached: supply-chain-artifacts-cached",
        "supply-chain-check: uv-lock-check supply-chain-provenance",
        "provenance-check: supply-chain-check",
    ):
        case.assertIn(dependency, text)
    recipe_expectations = (
        (
            "sbom-readiness-check",
            '$(PYTHON) -m ops.scripts.sbom_readiness_gate_runtime --vault "$(VAULT)"',
        ),
        (
            "cyclonedx-sbom",
            '$(PYTHON) -m ops.scripts.cyclonedx_sbom --vault "$(VAULT)" --out "$(CYCLONEDX_SBOM_OUT)"',
        ),
        (
            "openvex-draft",
            '$(PYTHON) -m ops.scripts.openvex_draft --vault "$(VAULT)" --out "$(OPENVEX_DRAFT_OUT)"',
        ),
        (
            "supply-chain-artifacts-cached",
            '$(PYTHON) -m ops.scripts.supply_chain_artifacts --vault "$(VAULT)" --provenance-out "$(SUPPLY_CHAIN_PROVENANCE_OUT)" --gate-out "$(SUPPLY_CHAIN_GATE_OUT)" --security-advisories-out "$(SECURITY_ADVISORIES_OUT)" --mapping-out "$(SBOM_EXPORT_MAPPING_OUT)" --readiness-out "$(SBOM_READINESS_GATE_OUT)" --model-out "$(SUPPLY_CHAIN_ARTIFACT_MODEL_OUT)" --cyclonedx-out "$(CYCLONEDX_SBOM_OUT)" --spdx-out "$(SPDX_SBOM_OUT)" --openvex-out "$(OPENVEX_DRAFT_OUT)" --in-toto-out "$(IN_TOTO_STATEMENT_OUT)" --sigstore-out "$(SIGSTORE_BUNDLE_OUT)"',
        ),
        (
            "security-advisories",
            '$(PYTHON) -m ops.scripts.security_advisories --vault "$(VAULT)" --out "$(SECURITY_ADVISORIES_OUT)"',
        ),
        (
            "supply-chain-artifact-model",
            '$(PYTHON) -m ops.scripts.supply_chain_artifact_model --vault "$(VAULT)" --out "$(SUPPLY_CHAIN_ARTIFACT_MODEL_OUT)"',
        ),
        (
            "spdx-sbom",
            '$(PYTHON) -m ops.scripts.spdx_sbom --vault "$(VAULT)" --out "$(SPDX_SBOM_OUT)"',
        ),
        (
            "in-toto-statement",
            '$(PYTHON) -m ops.scripts.in_toto_statement --vault "$(VAULT)" --out "$(IN_TOTO_STATEMENT_OUT)"',
        ),
        (
            "sigstore-bundle",
            '$(PYTHON) -m ops.scripts.sigstore_bundle --vault "$(VAULT)" --out "$(SIGSTORE_BUNDLE_OUT)"',
        ),
        (
            "supply-chain-benchmark",
            '$(PYTHON) -m ops.scripts.supply_chain_benchmark --vault "$(VAULT)" --out "$(SUPPLY_CHAIN_BENCHMARK_OUT)"',
        ),
        (
            "supply-chain-check",
            '$(PYTHON) -m ops.scripts.supply_chain_gate_runtime --vault "$(VAULT)"',
        ),
    )
    for target, needle in recipe_expectations:
        case.assertIn(needle, _target_block(text, target))


def _assert_artifact_index_and_freshness_recipes(case: unittest.TestCase, text: str) -> None:
    case.assertIn(
        '$(PYTHON) -m ops.scripts.structural_complexity_budget --vault "$(VAULT)" --out "$(STRUCTURAL_COMPLEXITY_BUDGET_OUT)"',
        _target_block(text, "complexity-budget"),
    )
    case.assertIn(
        '$(PYTHON) -m ops.scripts.structural_complexity_budget --vault "$(VAULT)" --out "$(STRUCTURAL_COMPLEXITY_BUDGET_OUT)" --fail-on-attention',
        _target_block(text, "complexity-budget-check"),
    )
    freshness_check = _target_block(text, "artifact-freshness-check")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.artifact_freshness_runtime --vault "$(VAULT)" --out "$(ARTIFACT_FRESHNESS_CHECK_OUT)" --mtime-source "$(ARTIFACT_FRESHNESS_MTIME_SOURCE)" --progress "$(ARTIFACT_FRESHNESS_PROGRESS)" $(if $(ARTIFACT_FRESHNESS_ZIP_METADATA),--zip-metadata "$(ARTIFACT_FRESHNESS_ZIP_METADATA)",) --fail-on-fail',
        freshness_check,
    )
    case.assertNotIn("ops.scripts.canonical_artifact_promote", freshness_check)
    freshness = _target_block(text, "artifact-freshness")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.artifact_freshness_runtime --vault "$(VAULT)" --out "$(ARTIFACT_FRESHNESS_CANDIDATE_OUT)" --mtime-source "$(ARTIFACT_FRESHNESS_MTIME_SOURCE)" --progress "$(ARTIFACT_FRESHNESS_PROGRESS)" $(if $(ARTIFACT_FRESHNESS_ZIP_METADATA),--zip-metadata "$(ARTIFACT_FRESHNESS_ZIP_METADATA)",)',
        freshness,
    )
    case.assertIn("ops.scripts.canonical_artifact_promote", freshness)
    freshness_refresh_check = _target_block(text, "artifact-freshness-refresh-check")
    case.assertIn('--out "$(ARTIFACT_FRESHNESS_CANDIDATE_OUT)"', freshness_refresh_check)
    case.assertIn("--fail-on-fail", freshness_refresh_check)
    case.assertIn("ops.scripts.canonical_artifact_promote", freshness_refresh_check)
    case.assertIn("|| status=$$?; exit $$status", freshness_refresh_check)
    case.assertIn("exit $$status", freshness_refresh_check)
    relocation_audit = _target_block(text, "artifact-relocation-audit")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.artifact_relocation_audit --vault "$(VAULT)" --out "$(ARTIFACT_RELOCATION_AUDIT_CANDIDATE_OUT)" --fail-on-fail',
        relocation_audit,
    )
    case.assertIn("--schema ops/schemas/artifact-relocation-audit.schema.json", relocation_audit)
    generated_index = _target_block(text, "generated-artifact-index-body")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.generated_artifact_index --vault "$(VAULT)" --out "$(GENERATED_ARTIFACT_INDEX_CANDIDATE_OUT)"',
        generated_index,
    )
    case.assertIn("ops.scripts.canonical_artifact_promote", generated_index)
    case.assertIn(
        '$(PYTHON) -m ops.scripts.closure_registry_envelope --vault "$(VAULT)" --registry "$(CLOSURE_REGISTRY_ENVELOPE_REGISTRY)"',
        _target_block(text, "closure-registry-envelope"),
    )


def _assert_archive_and_complexity_recipes(case: unittest.TestCase, text: str) -> None:
    touched_block = _target_block(text, "complexity-budget-touched-check")
    case.assertIn('--out "$(STRUCTURAL_COMPLEXITY_BUDGET_TOUCHED_OUT)"', touched_block)
    case.assertIn('--changed-files-manifest "$(CHANGED_FILES_MANIFEST)"', touched_block)
    case.assertIn('--target "$(target)"', touched_block)
    case.assertIn(
        'PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m ops.scripts.review_archive --vault "$(VAULT)" --archive-out "$(REVIEW_ARCHIVE_OUT)" --out "$(REVIEW_ARCHIVE_REPORT_OUT)" --profile "$(REVIEW_ARCHIVE_PROFILE)"',
        _target_block(text, "review-archive"),
    )
    archive_modes = (
        (
            "archive-execution-manifest-apply",
            '$(PYTHON) -m ops.scripts.archive_execution_manifest --vault "$(VAULT)" --index-path "$(GENERATED_ARTIFACT_INDEX_OUT)" --out "$(ARCHIVE_EXECUTION_MANIFEST_OUT)" --mode applied --operator-confirmation "$(ARCHIVE_EXECUTION_OPERATOR_CONFIRMATION)"',
        ),
        (
            "archive-execution-manifest-defer",
            '$(PYTHON) -m ops.scripts.archive_execution_manifest --vault "$(VAULT)" --index-path "$(GENERATED_ARTIFACT_INDEX_OUT)" --out "$(ARCHIVE_EXECUTION_MANIFEST_OUT)" --mode deferred',
        ),
        (
            "archive-execution-manifest-rollback",
            '$(PYTHON) -m ops.scripts.archive_execution_manifest --vault "$(VAULT)" --manifest-path "$(ARCHIVE_EXECUTION_MANIFEST_SOURCE)" --out "$(ARCHIVE_EXECUTION_MANIFEST_OUT)" --mode rollback --operator-confirmation "$(ARCHIVE_EXECUTION_OPERATOR_CONFIRMATION)"',
        ),
    )
    for target, needle in archive_modes:
        case.assertIn(needle, _target_block(text, target))


def _makefile_assignment_items(text: str, variable: str) -> tuple[str, ...]:
    prefix = f"{variable} ?="
    lines = text.splitlines()
    collecting = False
    items: list[str] = []
    for line in lines:
        if not collecting:
            if not line.startswith(prefix):
                continue
            collecting = True
            remainder = line[len(prefix) :].strip()
        else:
            if not line.startswith(("\t", " ")):
                break
            remainder = line.strip()

        continued = remainder.endswith("\\")
        remainder = remainder[:-1].strip() if continued else remainder
        if remainder:
            items.extend(remainder.split())
        if collecting and not continued:
            break

    if not collecting:
        raise AssertionError(f"missing Makefile assignment: {variable}")
    return tuple(items)


def _makefile_assignment_value(text: str, variable: str) -> str:
    prefix = f"{variable} ?="
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    raise AssertionError(f"missing Makefile assignment: {variable}")


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _shell_join(items: tuple[str, ...]) -> str:
    return " ".join(items)


def _pytest_ini_marker_docs() -> dict[str, str]:
    parser = configparser.ConfigParser()
    parser.read_string(PYTEST_INI.read_text(encoding="utf-8"))
    markers_value = parser["pytest"]["markers"]
    marker_docs: dict[str, str] = {}
    for line in markers_value.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        marker, separator, description = stripped.partition(":")
        if not separator:
            raise AssertionError(f"invalid pytest.ini marker declaration: {stripped}")
        marker_docs[marker.strip()] = description.strip()
    return marker_docs


def _assert_refresh_generated_split_targets(case: unittest.TestCase, text: str) -> None:
    case.assertIn(
        "refresh-generated-core: registry-preflight raw-registry-export manifest script-output-surfaces routing-provenance-aggregate outcome-metrics promotion-decision-trends mechanism-review mutation-proposal",
        text,
    )
    case.assertEqual(
        _recipe_lines(text, "refresh-generated-observability"),
        [
            "$(MAKE) make-target-inventory",
            "$(MAKE) workflow-dependency-planner",
            "$(MAKE) release-workflow-order-guard",
            "$(MAKE) function-budget-refactor-proposals",
            "$(MAKE) outcome-provenance-gate-policy",
            "$(MAKE) generated-artifact-converge",
        ],
    )
    case.assertIn("refresh-generated: refresh-generated-core refresh-generated-observability", text)
    case.assertEqual(
        _recipe_lines(text, "generated-artifact-converge"),
        [
            '$(PYTHON) -m ops.scripts.generated_artifact_converge_summary --vault "$(VAULT)" --phase before --out "$(GENERATED_ARTIFACT_CONVERGE_SUMMARY_BEFORE_OUT)"',
            "$(MAKE) script-output-surfaces",
            "$(MAKE) external-report-action-matrix",
            "$(MAKE) generated-artifact-index",
            "$(MAKE) artifact-freshness",
            '$(PYTHON) -m ops.scripts.generated_artifact_converge_summary --vault "$(VAULT)" --phase after --before "$(GENERATED_ARTIFACT_CONVERGE_SUMMARY_BEFORE_OUT)" --out "$(GENERATED_ARTIFACT_CONVERGE_SUMMARY_OUT)"',
        ],
    )
    case.assertIn(
        "GENERATED_ARTIFACT_CONVERGE_SUMMARY_OUT ?= tmp/generated-artifact-converge-summary.json",
        text,
    )
    case.assertIn(
        "GENERATED_ARTIFACT_CONVERGE_SUMMARY_BEFORE_OUT ?= tmp/generated-artifact-converge-summary.before.json",
        text,
    )
    for phony_target in (
        "refresh-generated-core",
        "refresh-generated-observability",
        "generated-artifact-converge",
        "script-output-surfaces",
        "function-budget-refactor-proposals",
        "outcome-provenance-gate-policy",
        "external-report-action-matrix",
        "artifact-relocation-audit",
    ):
        with case.subTest(phony_target=phony_target):
            case.assertIn(phony_target, _target_block(text, ".PHONY"))


def _assert_observability_output_variables(case: unittest.TestCase, text: str) -> None:
    expected_variables = (
        "FUNCTION_BUDGET_REFACTOR_PROPOSALS_OUT ?= ops/reports/function-budget-refactor-proposals.json",
        "FUNCTION_BUDGET_REFACTOR_PROPOSALS_CANDIDATE_OUT ?= tmp/function-budget-refactor-proposals.candidate.json",
        "OUTCOME_PROVENANCE_GATE_POLICY_OUT ?= ops/reports/outcome-provenance-gate-policy.json",
        "OUTCOME_PROVENANCE_GATE_POLICY_CANDIDATE_OUT ?= tmp/outcome-provenance-gate-policy.candidate.json",
        "EXTERNAL_REPORT_ACTION_MATRIX_OUT ?= ops/reports/external-report-action-matrix.json",
        "SCRIPT_OUTPUT_SURFACES_OUT ?= ops/script-output-surfaces.json",
        "SCRIPT_OUTPUT_SURFACES_CANDIDATE_OUT ?= tmp/script-output-surfaces.candidate.json",
        "CLEAN_FIXTURE_REGENERATION_GUARD_OUT ?= tmp/clean-fixture-regeneration-guard.json",
        "MAKE_TARGET_INVENTORY_OUT ?= tmp/make-target-inventory.json",
        "WORKFLOW_DEPENDENCY_PLANNER_OUT ?= ops/reports/workflow-dependency-planner.json",
        "WORKFLOW_DEPENDENCY_PLANNER_CANDIDATE_OUT ?= tmp/workflow-dependency-planner.candidate.json",
        "WORKFLOW_DEPENDENCY_PLANNER_CHECK_OUT ?= tmp/workflow-dependency-planner-check.json",
        "RELEASE_WORKFLOW_ORDER_GUARD_OUT ?= ops/reports/release-workflow-order-guard.json",
        "RELEASE_WORKFLOW_ORDER_GUARD_CANDIDATE_OUT ?= tmp/release-workflow-order-guard.candidate.json",
    )
    for variable in expected_variables:
        with case.subTest(variable=variable):
            case.assertIn(variable, text)


def _assert_script_surface_and_inventory_targets(case: unittest.TestCase, text: str) -> None:
    script_output_block = _target_block(text, "script-output-surfaces")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.script_output_surfaces --vault "$(VAULT)" --out "$(SCRIPT_OUTPUT_SURFACES_CANDIDATE_OUT)"',
        script_output_block,
    )
    case.assertIn("ops.scripts.canonical_artifact_promote", script_output_block)
    guard_block = _target_block(text, "clean-fixture-regeneration-guard")
    case.assertIn("clean-fixture-regeneration-guard", _target_block(text, ".PHONY"))
    case.assertIn(
        '$(PYTHON) -m ops.scripts.clean_fixture_regeneration_guard --vault "$(VAULT)" --out "$(CLEAN_FIXTURE_REGENERATION_GUARD_OUT)"',
        guard_block,
    )
    case.assertIn(
        "script-output-surfaces-clean-regenerate: clean-fixture-regeneration-guard script-output-surfaces",
        text,
    )
    case.assertIn("make-target-inventory", _target_block(text, ".PHONY"))
    case.assertIn(
        '$(PYTHON) -m ops.scripts.make_target_inventory --vault "$(VAULT)" --out "$(MAKE_TARGET_INVENTORY_OUT)"',
        _target_block(text, "make-target-inventory"),
    )


def _assert_workflow_dependency_planner_target(case: unittest.TestCase, text: str) -> None:
    case.assertIn("workflow-dependency-planner", _target_block(text, ".PHONY"))
    case.assertIn("workflow-dependency-planner-check", _target_block(text, ".PHONY"))
    planner_block = _target_block(text, "workflow-dependency-planner")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.workflow_dependency_planner --vault "$(VAULT)" --out "$(WORKFLOW_DEPENDENCY_PLANNER_CANDIDATE_OUT)"',
        planner_block,
    )
    case.assertIn("ops.scripts.canonical_artifact_promote", planner_block)
    case.assertIn("--schema ops/schemas/workflow-dependency-planner.schema.json", planner_block)
    case.assertIn("--expected-artifact-kind workflow_dependency_planner", planner_block)
    case.assertIn("--expected-producer ops.scripts.workflow_dependency_planner", planner_block)
    planner_check_block = _target_block(text, "workflow-dependency-planner-check")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.workflow_dependency_planner --vault "$(VAULT)" --out "$(WORKFLOW_DEPENDENCY_PLANNER_CHECK_OUT)"',
        planner_check_block,
    )
    case.assertNotIn("canonical_artifact_promote", planner_check_block)
    for target in ("static", "check", "check-all", "release-check", "release-clean"):
        with case.subTest(target=target):
            case.assertNotIn("workflow-dependency-planner", _target_block(text, target))
    case.assertNotIn("$(MAKE) workflow-dependency-planner", _target_block(text, "release-evidence-converge"))
    case.assertNotIn("$(MAKE) workflow-dependency-planner", _target_block(text, "check-finalized"))


def _assert_release_workflow_order_guard_target(case: unittest.TestCase, text: str) -> None:
    case.assertIn("release-workflow-order-guard", _target_block(text, ".PHONY"))
    order_guard_block = _target_block(text, "release-workflow-order-guard")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.release_workflow_order_guard --vault "$(VAULT)" --out "$(RELEASE_WORKFLOW_ORDER_GUARD_CANDIDATE_OUT)"',
        order_guard_block,
    )
    case.assertIn("ops.scripts.canonical_artifact_promote", order_guard_block)
    case.assertIn("--schema ops/schemas/release-workflow-order-guard.schema.json", order_guard_block)
    case.assertIn("--expected-artifact-kind release_workflow_order_guard", order_guard_block)
    case.assertIn("--expected-producer ops.scripts.release_workflow_order_guard", order_guard_block)
    case.assertNotIn("$(MAKE) release-workflow-order-guard", _target_block(text, "release-evidence-converge"))
    case.assertNotIn("$(MAKE) release-workflow-order-guard", _target_block(text, "check-finalized"))


def _assert_function_budget_and_outcome_targets(case: unittest.TestCase, text: str) -> None:
    proposal_block = _target_block(text, "function-budget-refactor-proposals")
    case.assertIn("function-budget-refactor-proposals: wiki-lint-review-classification", text)
    case.assertIn(
        '$(PYTHON) -m ops.scripts.function_budget_refactor_proposals --vault "$(VAULT)" --classification "$(WIKI_LINT_REVIEW_CLASSIFICATION_OUT)" --out "$(FUNCTION_BUDGET_REFACTOR_PROPOSALS_CANDIDATE_OUT)"',
        proposal_block,
    )
    case.assertIn("--schema ops/schemas/function-budget-refactor-proposals.schema.json", proposal_block)

    outcome_policy_block = _target_block(text, "outcome-provenance-gate-policy")
    case.assertIn("outcome-provenance-gate-policy: outcome-metrics routing-provenance-aggregate", text)
    case.assertIn(
        '$(PYTHON) -m ops.scripts.outcome_provenance_gate_policy --vault "$(VAULT)" --out "$(OUTCOME_PROVENANCE_GATE_POLICY_CANDIDATE_OUT)"',
        outcome_policy_block,
    )
    case.assertIn("--schema ops/schemas/outcome-provenance-gate-policy.schema.json", outcome_policy_block)
    case.assertIn("--expected-artifact-kind outcome_provenance_gate_policy", outcome_policy_block)
    case.assertIn("--expected-producer ops.scripts.outcome_provenance_gate_policy", outcome_policy_block)

    promotion_trends_block = _target_block(text, "promotion-decision-trends")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.promotion_decision_trends --vault "$(VAULT)" --recent-window "$(PROMOTION_DECISION_TRENDS_RECENT_WINDOW)"',
        promotion_trends_block,
    )


def _assert_external_report_action_matrix_target(case: unittest.TestCase, text: str) -> None:
    external_action_block = _target_block(text, "external-report-action-matrix")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.external_report_action_matrix --vault "$(VAULT)" --out "$(EXTERNAL_REPORT_ACTION_MATRIX_OUT)"',
        external_action_block,
    )
    case.assertIn("compatibility aggregate", _target_block(text, "refresh-generated"))


class MakefileStaticGateTests(unittest.TestCase):
    def test_root_makefile_keeps_only_common_variables_and_aggregate_aliases(self) -> None:
        root_text = MAKEFILE.read_text(encoding="utf-8")
        allowed_assignments = {
            "VENV_DIR",
            "VENV_PYTHON",
            "PYTHON",
            "BOOTSTRAP_PYTHON",
            "VAULT",
            "EXECUTION_LANE_POLICY",
        }
        assignment_names = {
            match.group(1)
            for match in re.finditer(r"^([A-Z0-9_]+)\s*(?:\?|:)?=", root_text, flags=re.MULTILINE)
        }

        self.assertEqual(assignment_names, allowed_assignments)
        for mk_file in (
            "mk/core.mk",
            "mk/static.mk",
            "mk/test.mk",
            "mk/eval.mk",
            "mk/artifact.mk",
            "mk/registry.mk",
            "mk/mechanism.mk",
            "mk/release.mk",
            "mk/public.mk",
            "mk/supply_chain.mk",
        ):
            with self.subTest(mk_file=mk_file):
                self.assertIn(f"include {mk_file}", root_text)
                self.assertLess(root_text.index(f"include {mk_file}"), root_text.index(".PHONY: check"))
        self.assertLess(root_text.index("include mk/test.mk"), root_text.index("export PYTEST_DISABLE_PLUGIN_AUTOLOAD"))

    def test_help_target_indexes_operator_entrypoints(self) -> None:
        text = _makefile_text()
        block = _target_block(text, "help")

        self.assertIn("help", _target_block(text, ".PHONY"))
        for heading in (
            "Setup:",
            "Source checks:",
            "Report contracts:",
            "Public mirror:",
            "Mechanism:",
            "Release:",
        ):
            self.assertIn(heading, block)
        for target in (
            "make dev-install",
            "make static",
            "make strict-preview-audit",
            "make report-contracts-core",
            "make external-report-lifecycle-refresh",
            "make sync-public-policy",
            "make goal-runtime-run-admission",
            "make release-auto-promotion-ready",
        ):
            self.assertIn(target, block)

    def test_check_targets_include_static_gate(self) -> None:
        text = _makefile_text()

        for target in ("check", "check-serial", "check-all", "check-all-serial"):
            with self.subTest(target=target):
                dependencies = _target_dependencies(text, target)
                self.assertEqual(dependencies[:2], ("uv-lock-check", "static"))
                self.assertIn("registry-preflight-check", dependencies)
                self.assertNotIn("registry-preflight", dependencies)
        self.assertEqual(_target_dependencies(text, "static"), ("uv-lock-check", "ruff", "typecheck"))
        self.assertEqual(_recipe_lines(text, "uv-lock-check"), ["$(UV) lock --check"])
        self.assertIn("uv-lock-check", _target_block(text, ".PHONY"))

    def test_strict_targets_include_warning_budget_gate(self) -> None:
        text = _makefile_text()

        self.assertIn(
            "check-strict: check warning-budget complexity-budget-touched-check", text
        )
        self.assertIn("check-conditional: check", text)
        self.assertIn(
            "check-clean: check-clean-lane-guard check-conditional warning-budget release-evidence-cohort-check",
            text,
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target check-clean',
            _target_block(text, "check-clean-lane-guard"),
        )
        self.assertIn("release-evidence-converge-lane-guard", _target_block(text, ".PHONY"))
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-evidence-converge',
            _target_block(text, "release-evidence-converge-lane-guard"),
        )
        self.assertIn("release-evidence-closeout-lane-guard", _target_block(text, ".PHONY"))
        self.assertIn(
            "release-evidence-closeout-lane-guard is a compatibility alias",
            _target_block(text, "release-evidence-closeout-lane-guard"),
        )
        self.assertIn("release-builder-full-lane-guard", _target_block(text, ".PHONY"))
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-builder-full',
            _target_block(text, "release-builder-full-lane-guard"),
        )
        self.assertIn("release-smoke-lane-guard", _target_block(text, ".PHONY"))
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-smoke',
            _target_block(text, "release-smoke-lane-guard"),
        )
        self.assertIn(
            "release-distribution-zip: release-distribution-zip-lane-guard",
            text,
        )
        self.assertIn(
            "release-distribution-zip-lane-guard", _target_block(text, ".PHONY")
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-distribution-zip',
            _target_block(text, "release-distribution-zip-lane-guard"),
        )
        self.assertIn("release-conditional: release-evidence-refresh-fast", text)
        self.assertIn(
            "release-clean: release-check warning-budget release-evidence-converge release-evidence-cohort-check",
            text,
        )
        self.assertIn(
            "release-provenance-clean: release-clean supply-chain-check", text
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.warning_budget --vault "$(VAULT)"',
            _target_block(text, "warning-budget"),
        )

    def test_static_gate_runs_ruff_and_full_ops_mypy_target(self) -> None:
        text = _makefile_text()

        self.assertIn("RUFF_TARGETS ?= ops/scripts tests tools", text)
        self.assertIn("MYPY_TARGETS ?= ops/scripts", text)
        self.assertIn("static: uv-lock-check ruff typecheck", text)
        self.assertIn("$(UV) lock --check", _target_block(text, "uv-lock-check"))
        self.assertIn(
            "$(PYTHON) -m ruff check $(RUFF_TARGETS)", _target_block(text, "ruff")
        )
        self.assertIn(
            "$(PYTHON) -m mypy $(MYPY_TARGETS)", _target_block(text, "typecheck")
        )

    def test_pytest_entrypoints_disable_third_party_plugin_autoload(self) -> None:
        text = _makefile_text()

        self.assertIn("PYTEST_DISABLE_PLUGIN_AUTOLOAD ?= 1", text)
        self.assertIn("export PYTEST_DISABLE_PLUGIN_AUTOLOAD", text)
        self.assertIn(
            "PYTEST_PARALLEL_FLAGS ?= -p xdist.plugin -n auto --dist=loadfile", text
        )

    def test_pytest_ini_declares_lane_markers(self) -> None:
        registry = _test_lane_registry()
        pytest_ini_text = PYTEST_INI.read_text(encoding="utf-8")
        marker_docs = _pytest_ini_marker_docs()

        self.assertEqual(set(marker_docs), authoritative_markers(registry))
        self.assertEqual(marker_docs, marker_semantics(registry))
        self.assertNotIn(
            "deprecated compatibility alias for artifact_finalization", pytest_ini_text
        )

    def test_registry_make_target_marker_expressions_match_makefile_variables(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()
        variable_by_target = {
            "test-slow": "PYTEST_SLOW_MARK_EXPR",
            "test-integration": "PYTEST_INTEGRATION_MARK_EXPR",
            "test-integration-heavy": "PYTEST_INTEGRATION_HEAVY_MARK_EXPR",
            "test-public": "PYTEST_PUBLIC_MARK_EXPR",
            "test-report-contract-all": "PYTEST_REPORT_CONTRACT_MARK_EXPR",
            "test-release-sealing-all": "PYTEST_RELEASE_SEALING_MARK_EXPR",
            "test-subprocess": "PYTEST_SUBPROCESS_MARK_EXPR",
        }

        for target, variable in variable_by_target.items():
            with self.subTest(target=target, variable=variable):
                self.assertEqual(
                    _normalize_whitespace(_makefile_assignment_value(text, variable)),
                    _normalize_whitespace(selection_by_make_target(registry)[target]),
                )

    def test_registry_make_target_compatibility_entries_exist_in_makefile(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()

        for target in compatibility_names(registry, "make_target"):
            with self.subTest(target=target):
                _target_block(text, target)

    def test_pyproject_does_not_define_conflicting_pytest_marker_block(self) -> None:
        pyproject_text = Path("pyproject.toml").read_text(encoding="utf-8")

        self.assertNotIn("[tool.pytest.ini_options]", pyproject_text)
        self.assertNotIn('"finalization: local artifact self-checks', pyproject_text)

    def test_readme_and_pytest_ini_pin_supported_pytest_entrypoints(self) -> None:
        registry = _test_lane_registry()
        readme_text = README.read_text(encoding="utf-8")
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")
        conftest_text = CONFTEST.read_text(encoding="utf-8")
        pytest_ini_text = PYTEST_INI.read_text(encoding="utf-8")

        self.assertIn("docs/development.md", readme_text)
        self.assertIn("make help", readme_text)
        self.assertIn("make help", development_text)
        self.assertIn("uv lock --check", development_text)
        self.assertIn("uv.lock", development_text)
        self.assertIn(
            "공식 pytest 진입점은 `make test*`, `make check*`, `make public-check*` 또는 `.venv/bin/python -m pytest`다.",
            development_text,
        )
        self.assertIn(
            "문서, CI, 재현 절차 예시도 bare `pytest`가 아니라 `python -m pytest` 또는 Make target을 사용한다.",
            development_text,
        )
        self.assertIn("plain `pytest` is not a supported entrypoint", conftest_text)
        self.assertIn("BARE_PYTEST_GUIDANCE", conftest_text)
        self.assertNotRegex(pytest_ini_text, r"(?im)^pythonpath\s*=")
        for entrypoint in compatibility_names(registry, "documented_entrypoint"):
            with self.subTest(entrypoint=entrypoint):
                self.assertIn(entrypoint, development_text)

    def test_python_command_allows_interpreter_flags(self) -> None:
        text = _makefile_text()

        self.assertNotIn('"$(PYTHON)"', text)
        self.assertIn("PUBLIC_PYTHON ?= $(if $(wildcard $(firstword $(PYTHON)))", text)
        self.assertIn(
            "$(PYTHON) -m ruff check $(RUFF_TARGETS)", _target_block(text, "ruff")
        )

    def test_repo_virtualenv_is_canonical_make_default(self) -> None:
        text = _makefile_text()

        self.assertIn("VENV_DIR ?= .venv", text)
        self.assertIn("VENV_PYTHON ?= $(VENV_DIR)/bin/python", text)
        self.assertIn(
            "PYTHON ?= $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),python3)",
            text,
        )

    def test_fast_smoke_is_curated_developer_feedback_loop(self) -> None:
        text = _makefile_text()
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")
        block = _target_block(text, "fast-smoke")
        expected_tests = (
            "tests/test_import_fallback_contract.py",
            "tests/test_script_module_surface_contract.py",
            "tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_eval_report_validates_and_requires_policy_identity",
            "tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_lint_report_validates_and_requires_policy_identity",
            "tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_warning_budget_report_validates_and_requires_policy_identity",
            "tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_structural_complexity_budget_report_validates_and_requires_policy_identity",
            "tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_eval_coverage_report_validates_and_requires_policy_identity",
            "tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_stage2_eval_report_validates_and_requires_policy_identity",
            "tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_auto_improve_readiness_report_validates_and_requires_queue_block",
            "tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_proposal_scope_report_validates_and_requires_apply_guardrails",
            "tests/test_artifact_io_runtime.py",
            "tests/test_mechanism_review.py",
            "tests/test_mechanism_review_candidate_runtime.py",
            "tests/test_mechanism_review_history_runtime.py",
            "tests/test_mutation_proposal.py::MutationProposalTest::test_missing_artifact_envelope_fails_fast_for_primary_evidence",
            "tests/test_mutation_proposal.py::MutationProposalTest::test_unknown_currentness_fails_fast_for_primary_evidence",
            "tests/test_auto_improve_readiness_runtime.py",
            "tests/test_artifact_freshness_runtime.py::test_no_root_ephemeral_test_artifacts",
            "tests/test_artifact_freshness_runtime.py::ArtifactFreshnessRuntimeTests::test_report_accepts_enveloped_current_json_artifact",
            "tests/test_release_smoke.py::ReleaseSmokeTest::test_build_smoke_commands_match_release_gate_profiles",
            "tests/test_release_smoke.py::ReleaseSmokeTest::test_run_smoke_commands_captures_returncodes_and_tails",
            "tests/test_release_smoke.py::ReleaseSmokeTest::test_build_report_uses_runtime_context_and_sanitizes_ephemeral_paths",
            "tests/test_release_smoke.py::ReleaseSmokeTest::test_main_exits_with_report_status_and_prints_written_destination",
        )

        self.assertIn("fast-smoke", _target_block(text, ".PHONY"))
        self.assertIn(
            "PYTEST_FAST_SMOKE_MARK_EXPR ?= not slow and not integration_heavy", text
        )
        self.assertIn("FAST_SMOKE_TESTS ?=", text)
        self.assertIn(
            "`make fast-smoke`는 Subagent/developer precheck 전용 curated pytest slice다.",
            development_text,
        )
        for test_path in expected_tests:
            with self.subTest(test_path=test_path):
                self.assertIn(test_path, text)
        self.assertIn(
            '$(PYTHON) -m pytest -m "$(PYTEST_FAST_SMOKE_MARK_EXPR)" $(FAST_SMOKE_TESTS) $(PYTEST_SERIAL_FLAGS)',
            block,
        )
        self.assertNotIn("lint", block)
        self.assertNotIn("eval", block)
        self.assertNotIn("stage2-eval", block)
        self.assertNotIn("release-smoke", block)
        self.assertNotIn("tests/test_report_generation_smoke.py", block)
        self.assertNotIn("tests/test_mutation_proposal.py \\", block)
        self.assertNotIn("tests/test_artifact_freshness_runtime.py \\", block)
        self.assertNotIn("tests/test_release_smoke.py \\", block)

    def test_fast_smoke_selectors_collect_via_supported_pytest_entrypoint(self) -> None:
        text = _makefile_text()
        selectors = _makefile_assignment_items(text, "FAST_SMOKE_TESTS")
        env = os.environ.copy()
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", *selectors],
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
            msg=(
                "FAST_SMOKE_TESTS contains an uncollectable pytest selector.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            ),
        )

    def test_makefile_exposes_lane_targets_and_compatibility_aliases(self) -> None:
        text = _makefile_text()

        for target in (
            "test-fast",
            "test-report-contract",
            "test-report-contract-core",
            "test-report-contract-all",
            "test-release-sealing",
            "test-release-sealing-core",
            "test-release-sealing-all",
            "test-subprocess",
            "release-source-package-smoke",
            "release-source-package-check",
            "release-run-ready",
            "release-run-ready-check",
            "release-sealed-run-ready",
            "release-sealed-run-ready-plan",
            "release-sealed-run-ready-check",
            "release-auto-promotion-goal-run-id-guard",
            "release-auto-promotion-preflight",
            "release-auto-promotion-preflight-check",
            "release-auto-promotion-safe-cleanup",
            "release-auto-promotion-preseal",
            "release-auto-promotion-preseal-check",
            "release-auto-promotion-ready",
            "release-auto-promotion-ready-plan",
            "release-auto-promotion-operator-summary",
            "release-auto-promotion-ready-check",
            "release-builder-full",
        ):
            with self.subTest(target=target):
                self.assertIn(target, _target_block(text, ".PHONY"))

        self.assertIn(
            "PYTEST_REPORT_CONTRACT_MARK_EXPR ?= report_contract",
            text,
        )
        self.assertIn(
            "PYTEST_RELEASE_CHECK_MARK_EXPR ?= not report_contract",
            text,
        )
        self.assertIn("PYTEST_RELEASE_SEALING_MARK_EXPR ?= release_sealing", text)
        self.assertIn("PYTEST_SUBPROCESS_MARK_EXPR ?= subprocess", text)
        self.assertIn("RELEASE_SEALING_CORE_TESTS ?=", text)
        self.assertIn("tests/test_release_auto_promotion_preflight.py", text)
        self.assertIn("RELEASE_SEALING_TESTS ?= $(RELEASE_SEALING_CORE_TESTS)", text)
        self.assertIn("SUBPROCESS_TESTS ?=", text)
        self.assertIn(
            '$(PYTHON) -m pytest -m "$(PYTEST_FAST_MARK_EXPR)" $(PYTEST_FLAGS)',
            _target_block(text, "test-fast"),
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(PYTEST_FLAGS)",
            _target_block(text, "unit-tests-all"),
        )
        self.assertIn(
            '$(PYTHON) -m pytest -m "$(PYTEST_RELEASE_CHECK_MARK_EXPR)" $(PYTEST_FLAGS)',
            _target_block(text, "unit-tests-release-check"),
        )
        self.assertIn("test: test-fast", text)
        self.assertIn("unit-tests: test-fast", text)
        self.assertIn(
            "release-builder-full: release-builder-full-lane-guard bootstrap-preflight static release-evidence-converge",
            text,
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(RELEASE_SEALING_TESTS) $(PYTEST_SERIAL_FLAGS)",
            _target_block(text, "test-release-sealing-core"),
        )
        self.assertIn(
            '$(PYTHON) -m pytest -m "$(PYTEST_RELEASE_SEALING_MARK_EXPR)" $(PYTEST_SERIAL_FLAGS)',
            _target_block(text, "test-release-sealing-all"),
        )
        self.assertIn(
            "test-release-sealing is a compatibility alias",
            _target_block(text, "test-release-sealing"),
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(SUBPROCESS_TESTS) $(PYTEST_SERIAL_FLAGS)",
            _target_block(text, "test-subprocess"),
        )
        self.assertIn("RELEASE_CLOSEOUT_REGRESSION_TESTS ?=", text)
        self.assertIn(
            "RELEASE_CLOSEOUT_REGRESSION_FRESHNESS_CHECK_OUT ?= tmp/release-closeout-regression-artifact-freshness-check.json",
            text,
        )
        self.assertIn(
            "RELEASE_CLOSEOUT_COST_EVIDENCE_CI_OUT ?= tmp/release-closeout-fixed-point-cost-trend-ci.json",
            text,
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(RELEASE_CLOSEOUT_REGRESSION_TESTS) $(PYTEST_SERIAL_FLAGS)",
            _target_block(text, "test-release-closeout-regression-pack"),
        )
        self.assertIn(
            "release-closeout-regression-dry-run",
            _target_block(text, ".PHONY"),
        )
        self.assertIn(
            "release-closeout-cost-evidence-ci-artifact",
            _target_block(text, ".PHONY"),
        )
        self.assertIn(
            "release-closeout-post-check-finalizer-ci-artifact",
            _target_block(text, ".PHONY"),
        )
        regression_dry_run = _target_block(text, "release-closeout-regression-dry-run")
        self.assertIn("release-closeout-regression-dry-run: tmp-json-clean", text)
        self.assertIn(
            "$(MAKE) test-release-closeout-regression-pack", regression_dry_run
        )
        self.assertIn(
            '--out "$(RELEASE_CLOSEOUT_REGRESSION_FRESHNESS_CHECK_OUT)"',
            regression_dry_run,
        )
        self.assertIn("--fail-on-fail", regression_dry_run)
        self.assertIn("--verify", regression_dry_run)
        cost_artifact = _target_block(
            text, "release-closeout-cost-evidence-ci-artifact"
        )
        self.assertIn(
            "ops.scripts.release_closeout_fixed_point_cost_trend", cost_artifact
        )
        self.assertIn('--out "$(RELEASE_CLOSEOUT_COST_EVIDENCE_CI_OUT)"', cost_artifact)
        self.assertIn("--no-fail", cost_artifact)
        post_check_artifact = _target_block(
            text, "release-closeout-post-check-finalizer-ci-artifact"
        )
        self.assertIn("--recommended-targets-out", post_check_artifact)
        self.assertIn(
            '"$(RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_RECOMMENDED_TARGETS_OUT)"',
            post_check_artifact,
        )
        self.assertIn("--no-fail", post_check_artifact)

    def test_developer_full_suite_runs_full_pytest_without_marker_filter(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()
        release_check_expr = pack_mark_expr(registry, "release_check_unit_complement")

        _assert_assignment_exists(
            self,
            text,
            "PYTEST_RELEASE_CHECK_MARK_EXPR",
            release_check_expr,
        )
        self.assertEqual(release_check_expr, "not report_contract")
        for target, flags in (
            ("unit-tests-all", "$(PYTEST_FLAGS)"),
            ("unit-tests-all-serial", "$(PYTEST_SERIAL_FLAGS)"),
            ("unit-tests-all-parallel", "$(PYTEST_PARALLEL_FLAGS)"),
        ):
            with self.subTest(target=target):
                self.assertIn(
                    f"$(PYTHON) -m pytest {flags}",
                    _target_block(text, target),
                )
        self.assertIn(
            '$(PYTHON) -m pytest -m "$(PYTEST_RELEASE_CHECK_MARK_EXPR)" $(PYTEST_FLAGS)',
            _target_block(text, "unit-tests-release-check"),
        )

    def test_source_package_targets_pin_clean_extract_smoke_lane(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()

        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_SMOKE_ROOT",
            "build/source-package-smoke",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_SMOKE_OUT",
            "$(SOURCE_PACKAGE_SMOKE_ROOT)/source-package-smoke.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_SMOKE_EXTRACT_PARENT",
            "$(SOURCE_PACKAGE_SMOKE_ROOT)/extract",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_SMOKE_PYTHON",
            "$(PUBLIC_PYTHON)",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_CLEAN_EXTRACT_OUT",
            "ops/reports/source-package-clean-extract.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_CLEAN_EXTRACT_ROOT",
            "tmp/source-package-clean-extract",
        )
        self.assertIn("release-source-package-clean-extract", _target_block(text, ".PHONY"))
        _assert_recipe_contains_tokens(
            self,
            text,
            "release-source-package-smoke",
            (
                "ops.scripts.source_package_smoke",
                '--source-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
                '--extract-parent "$(SOURCE_PACKAGE_SMOKE_EXTRACT_PARENT)"',
                '--source-python "$(SOURCE_PACKAGE_SMOKE_PYTHON)"',
                '--out "$(SOURCE_PACKAGE_SMOKE_OUT)"',
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "release-source-package-clean-extract",
            (
                "ops.scripts.source_package_clean_extract",
                '--source-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
                '--extract-parent "$(SOURCE_PACKAGE_CLEAN_EXTRACT_EXTRACT_PARENT)"',
                '--source-python "$(SOURCE_PACKAGE_SMOKE_PYTHON)"',
                '--test-summary-out "$(SOURCE_PACKAGE_CLEAN_EXTRACT_TEST_SUMMARY_OUT)"',
                '--pytest-flags="$(SOURCE_PACKAGE_CLEAN_EXTRACT_PYTEST_FLAGS)"',
                '--zip-smoke-report "$(RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT)"',
                '--out "$(SOURCE_PACKAGE_CLEAN_EXTRACT_OUT)"',
            ),
        )
        self.assertEqual(pack_selectors(registry, "source_package"), ("release-source-package-smoke",))
        self.assertEqual(
            pack_summary_suite(registry, "source_package")["summary_target"],
            "build/source-package-smoke/source-package-smoke.json",
        )
        self.assertIn("$(MAKE) release-package-current", _target_block(text, "release-source-package-check"))
        self.assertIn("$(MAKE) release-source-package-smoke", _target_block(text, "release-source-package-check"))
        self.assertIn(
            "$(MAKE) release-source-package-clean-extract",
            _target_block(text, "release-source-package-check"),
        )

    def test_ci_matrix_runs_named_lane_targets(self) -> None:
        registry = _test_lane_registry()
        workflow_text = CI_WORKFLOW.read_text(encoding="utf-8")
        ci_map = compatibility_map(registry, "ci_tier")

        for tier, mapped_id in ci_map.items():
            with self.subTest(tier=tier, mapped_id=mapped_id):
                self.assertIn(f"- {tier}", workflow_text)
                if mapped_id in pack_by_id(registry):
                    expected_steps = pack_ci_steps(registry, mapped_id)
                    expected_entrypoint = pack_ci_entrypoint(registry, mapped_id)
                else:
                    expected_steps = lane_ci_steps(registry, mapped_id)
                    expected_entrypoint = lane_ci_entrypoint(registry, mapped_id)
                self.assertTrue(expected_steps)
                self.assertTrue(expected_entrypoint)
                self.assertIn(f"make {expected_entrypoint}", workflow_text)
                for step in expected_steps:
                    self.assertIn(step, workflow_text)
        self.assertIn("make release-authority-sealed-preflight", workflow_text)
        self.assertIn("make test-fast", workflow_text)

    def test_readme_ci_tier_summary_matches_current_workflow_shape(self) -> None:
        registry = _test_lane_registry()
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")

        self.assertIn(
            "`.github/workflows/ci.yml`은 test tier를 `fast`, `report-contract`, `release-closeout-regression`, `release-sealing`, `subprocess`, `slow`, `integration`, `integration-heavy`, `public`으로 나눠 병렬 job으로 실행하고, 별도 Windows/raw-registry/supply-chain job도 유지한다.",
            development_text,
        )
        for entrypoint in compatibility_names(registry, "documented_entrypoint"):
            with self.subTest(entrypoint=entrypoint):
                self.assertIn(entrypoint, development_text)

    def test_registry_documents_authority_boundary_for_lane_contract(self) -> None:
        registry = _test_lane_registry()

        self.assertEqual(
            documentation_authority(registry),
            ("README.md", "docs/development.md", "ops/README.md", ".github/workflows/ci.yml"),
        )
        self.assertEqual(
            documentation_out_of_scope(registry),
            ("ARCHITECTURE.md", ".github/workflows/release.yml"),
        )

    def test_architecture_public_surface_includes_github_workflows(self) -> None:
        architecture_text = Path("ARCHITECTURE.md").read_text(encoding="utf-8")

        self.assertIn("- `.github/`", architecture_text)
        self.assertIn("- `docs/`", architecture_text)

    def test_release_smoke_targets_expose_fast_and_full_profiles(self) -> None:
        text = _makefile_text()
        release_doc_text = DOCS_RELEASE.read_text(encoding="utf-8")

        self.assertIn("release-smoke-fast", _target_block(text, ".PHONY"))
        self.assertIn("release-smoke-full", _target_block(text, ".PHONY"))
        self.assertIn("release-smoke-full-reuse", _target_block(text, ".PHONY"))
        self.assertIn("release-smoke-full-current-check", _target_block(text, ".PHONY"))
        self.assertIn("release-smoke-fast-current-check", _target_block(text, ".PHONY"))
        self.assertIn("release-smoke-fast-refresh-check", _target_block(text, ".PHONY"))
        self.assertIn(
            "RELEASE_SMOKE_OUT ?= ops/reports/release-smoke-report.json", text
        )
        self.assertIn(
            "RELEASE_SMOKE_FAST_OUT ?= ops/reports/release-smoke-report-fast.json", text
        )
        self.assertIn(
            "RELEASE_SMOKE_FAST_CURRENT_CHECK_OUT ?= tmp/release-smoke-report-fast-current-check.json",
            text,
        )
        self.assertIn("RELEASE_SMOKE_REUSE_FROM ?= $(RELEASE_SMOKE_OUT)", text)
        self.assertIn(
            '$(PYTHON) -m ops.scripts.release_smoke --vault "$(VAULT)" --profile full --out "$(RELEASE_SMOKE_OUT)"',
            _target_block(text, "release-smoke"),
        )
        self.assertIn("release-smoke-full: release-smoke", text)
        reuse_block = _target_block(text, "release-smoke-full-reuse")
        self.assertIn("--reuse-if-current", reuse_block)
        self.assertIn('--reuse-from "$(RELEASE_SMOKE_REUSE_FROM)"', reuse_block)
        current_check_block = _target_block(text, "release-smoke-full-current-check")
        self.assertIn("--reuse-if-current", current_check_block)
        self.assertIn("--reuse-only", current_check_block)
        self.assertIn('--out "$(RELEASE_SMOKE_CURRENT_CHECK_OUT)"', current_check_block)
        self.assertIn(
            '$(PYTHON) -m ops.scripts.release_smoke --vault "$(VAULT)" --profile fast --out "$(RELEASE_SMOKE_FAST_OUT)"',
            _target_block(text, "release-smoke-fast"),
        )
        fast_current_check_block = _target_block(text, "release-smoke-fast-current-check")
        self.assertIn("--reuse-if-current", fast_current_check_block)
        self.assertIn("--reuse-only", fast_current_check_block)
        self.assertIn('--reuse-from "$(RELEASE_SMOKE_FAST_OUT)"', fast_current_check_block)
        self.assertIn('--out "$(RELEASE_SMOKE_FAST_CURRENT_CHECK_OUT)"', fast_current_check_block)
        self.assertEqual(
            _recipe_lines(text, "release-smoke-fast-refresh-check"),
            [
                '@if $(MAKE) release-smoke-fast-current-check; then \\',
                'echo "fast release smoke evidence is current; reused $(RELEASE_SMOKE_FAST_OUT)"; \\',
                "else \\",
                "$(MAKE) release-smoke-fast; \\",
                "$(MAKE) release-smoke-fast-current-check; \\",
                "fi",
            ],
        )
        converge_block = _target_block(text, "release-converge")
        converge_all_block = _target_block(text, "release-converge-all-surfaces")
        ready_snapshot_block = _target_block(text, "release-source-ready-snapshot")
        ready_commit_block = _target_block(text, "release-source-ready-commit")
        ready_post_verify_block = _target_block(text, "release-source-ready-post-verify")
        ready_block = _target_block(text, "release-source-ready")
        preflight_block = _target_block(text, "release-check-preflight-converge")
        core_block = _target_block(text, "release-check-core")
        release_check_block = _target_block(text, "release-check")
        all_surfaces_block = _target_block(text, "release-check-all-surfaces")
        post_check_block = _target_block(text, "release-check-post-check")
        post_block = _target_block(text, "release-check-post-converge")
        self.assertIn("release-worktree-clean-check", _target_block(text, ".PHONY"))
        self.assertIn("release-converge", _target_block(text, ".PHONY"))
        self.assertIn("release-converge-all-surfaces", _target_block(text, ".PHONY"))
        phony_targets = _target_block(text, ".PHONY").replace(".PHONY:", "").split()
        self.assertIn("release-source-ready-snapshot", _target_block(text, ".PHONY"))
        self.assertIn("release-source-ready-prepare", _target_block(text, ".PHONY"))
        self.assertIn("release-source-ready-commit", _target_block(text, ".PHONY"))
        self.assertIn("release-source-ready-post-verify", _target_block(text, ".PHONY"))
        self.assertNotIn("release-source-ready-post-commit", phony_targets)
        self.assertNotIn("release-source-ready-post-commit-converge", phony_targets)
        self.assertNotIn("release-source-ready-amend", phony_targets)
        self.assertNotIn("release-source-ready-final-guard-amend", phony_targets)
        self.assertIn("release-source-ready", _target_block(text, ".PHONY"))
        self.assertIn("release-run-ready", _target_block(text, ".PHONY"))
        self.assertIn("release-run-ready-check", _target_block(text, ".PHONY"))
        self.assertNotIn("release-run-ready-ensure", phony_targets)
        self.assertIn("release-sealed-run-ready-plan", _target_block(text, ".PHONY"))
        self.assertNotIn("release-sealed-run-ready-ensure", phony_targets)
        self.assertIn("release-auto-promotion-goal-run-id-guard", _target_block(text, ".PHONY"))
        self.assertIn("release-auto-promotion-preflight", _target_block(text, ".PHONY"))
        self.assertIn("release-auto-promotion-preflight-check", _target_block(text, ".PHONY"))
        self.assertIn("release-auto-promotion-safe-cleanup", _target_block(text, ".PHONY"))
        self.assertIn("release-auto-promotion-preseal", _target_block(text, ".PHONY"))
        self.assertIn("release-auto-promotion-preseal-check", _target_block(text, ".PHONY"))
        self.assertIn("release-auto-promotion-ready-plan", _target_block(text, ".PHONY"))
        self.assertIn("release-auto-promotion-operator-summary", _target_block(text, ".PHONY"))
        self.assertNotIn("release-converge-artifact-commit", _target_block(text, ".PHONY"))
        self.assertIn("release-check-preflight-converge", _target_block(text, ".PHONY"))
        self.assertIn("release-check-core", _target_block(text, ".PHONY"))
        self.assertIn("release-check-post-check", _target_block(text, ".PHONY"))
        self.assertIn("release-check-post-converge", _target_block(text, ".PHONY"))
        self.assertIn("release-check-all-surfaces", _target_block(text, ".PHONY"))
        self.assertIn("release-check-preflight-converge: release-converge-preflight", preflight_block)
        self.assertIn("release-check-post-converge: release-converge-post", post_block)
        self.assertIn("mutating compatibility alias", preflight_block)
        self.assertIn("mutating compatibility alias", post_block)
        self.assertEqual(
            _recipe_lines(text, "release-converge-preflight"),
            [
                "$(MAKE) report-schema-samples-regenerate",
                "$(MAKE) goal-runtime-local-evidence-refresh",
                "$(MAKE) test-execution-summary-report-contract-refresh-no-smoke",
            ],
        )
        self.assertNotIn("$(MAKE) test-execution-summary-report-contract-refresh\n", preflight_block)
        self.assertIn("$(MAKE) release-converge-preflight", converge_block)
        self.assertIn("$(MAKE) registry-preflight", converge_block)
        self.assertIn("$(MAKE) release-smoke-full-reuse", converge_block)
        self.assertIn("$(MAKE) release-converge-post", converge_block)
        self.assertIn("$(MAKE) release-converge", converge_all_block)
        self.assertIn("$(MAKE) sync-public-policy", converge_all_block)
        self.assertIn("$(MAKE) public-check-all", converge_all_block)
        self.assertIn("$(MAKE) release-converge-post", converge_all_block)
        self.assertIn(
            "RELEASE_SOURCE_READY_COMMIT_MESSAGE ?= release: converge source-ready surfaces",
            text,
        )
        self.assertIn("RELEASE_SOURCE_READY_PRE_STATUS_OUT ?= tmp/release-source-ready-pre-status.json", text)
        self.assertIn("RELEASE_SOURCE_READY_COMMIT_OUT ?= tmp/release-source-ready-commit.json", text)
        self.assertNotIn("RELEASE_SOURCE_READY_AMEND_OUT", text)
        self.assertNotIn("RELEASE_SOURCE_READY_FINAL_GUARD_AMEND_OUT", text)
        self.assertIn("RELEASE_SOURCE_READY_STATUS_OUT ?= tmp/release-source-ready-status.json", text)
        self.assertIn("RELEASE_WORKTREE_CLEAN_CHECK_OUT ?= tmp/release-worktree-clean-check.json", text)
        worktree_clean_block = _target_block(text, "release-worktree-clean-check")
        self.assertIn('ops.scripts.goal_worktree_guard', worktree_clean_block)
        self.assertIn('--out "$(RELEASE_WORKTREE_CLEAN_CHECK_OUT)"', worktree_clean_block)
        self.assertNotIn('--out "$(GOAL_WORKTREE_GUARD_OUT)"', worktree_clean_block)
        self.assertIn("ops.scripts.release_source_ready_commit", ready_snapshot_block)
        self.assertIn("--snapshot-only", ready_snapshot_block)
        self.assertEqual(
            _recipe_lines(text, "release-source-ready-prepare"),
            [
                "$(MAKE) release-source-ready-snapshot",
                "$(MAKE) release-converge-all-surfaces",
                "$(MAKE) test-execution-summary-full-current-or-refresh",
            ],
        )
        self.assertIn("ops.scripts.release_source_ready_commit", ready_commit_block)
        self.assertIn('--pre-status "$(RELEASE_SOURCE_READY_PRE_STATUS_OUT)"', ready_commit_block)
        self.assertIn('--message "$(RELEASE_SOURCE_READY_COMMIT_MESSAGE)"', ready_commit_block)
        self.assertEqual(
            _recipe_lines(text, "release-source-ready-post-verify"),
            [
                "$(MAKE) release-check-all-surfaces",
                "$(MAKE) release-source-ready-status",
            ],
        )
        for writer in (
            "$(MAKE) auto-improve-readiness-worktree-guard",
            "$(MAKE) goal-runtime-local-evidence-refresh",
            "$(MAKE) generated-artifact-converge",
            "$(MAKE) remediation-backlog",
            "$(MAKE) release-closeout-fixed-point",
            "$(MAKE) release-source-ready-amend",
            "$(MAKE) release-source-ready-final-guard-amend",
        ):
            self.assertNotIn(writer, ready_post_verify_block)
        self.assertIn("$(MAKE) release-source-ready-prepare", ready_block)
        self.assertIn("$(MAKE) release-source-ready-commit", ready_block)
        self.assertIn("$(MAKE) release-source-ready-post-verify", ready_block)
        status_block = _target_block(text, "release-source-ready-status")
        self.assertIn("ops.scripts.release_source_ready_status", status_block)
        self.assertIn('--out "$(RELEASE_SOURCE_READY_STATUS_OUT)"', status_block)
        self.assertEqual(
            _recipe_lines(text, "release-source-ready"),
            [
                "$(MAKE) release-source-ready-prepare",
                "$(MAKE) release-source-ready-commit",
                "$(MAKE) release-source-ready-post-verify",
            ],
        )
        self.assertIn("ops.scripts.release_run_ready", _target_block(text, "release-run-ready"))
        self.assertIn("ops.scripts.release_run_manifest", _target_block(text, "release-run-ready-check"))
        release_test_current_lines = _recipe_lines(text, "release-test-current")
        self.assertEqual(
            release_test_current_lines,
            [
                "$(MAKE) static",
                "$(MAKE) report-schema-samples-check",
                "$(MAKE) test-execution-summary-report-contract",
                "$(MAKE) test-execution-summary-full-current-or-refresh",
            ],
        )
        release_test_current_block = _target_block(text, "release-test-current")
        self.assertNotIn("$(PYTHON) -m pytest $(PYTEST_SERIAL_FLAGS)", release_test_current_block)
        self.assertNotIn("$(MAKE) generated-artifact-converge", release_test_current_block)
        self.assertIn("ops.scripts.release_evidence_planner", _target_block(text, "release-sealed-run-ready-plan"))
        self.assertIn("--stage sealed-run-ready", _target_block(text, "release-sealed-run-ready-plan"))
        sealed_run_ready_block = _target_block(text, "release-sealed-run-ready")
        self.assertIn("$(MAKE) release-sealed-run-ready-plan", sealed_run_ready_block)
        self.assertIn("$(MAKE) release-evidence-closeout-sealed-sidecars", sealed_run_ready_block)
        self.assertNotIn("release-run-ready-ensure", sealed_run_ready_block)
        self.assertNotIn(
            "$(MAKE) release-evidence-closeout-sealed-core-sidecars",
            sealed_run_ready_block,
        )
        self.assertIn("ops.scripts.release_sealed_run_manifest", sealed_run_ready_block)
        auto_promotion_goal_identity_block = _target_block(
            text, "release-auto-promotion-goal-run-id-guard"
        )
        auto_promotion_preflight_block = _target_block(text, "release-auto-promotion-preflight")
        auto_promotion_preflight_resolved_block = _target_block(
            text, "release-auto-promotion-preflight-resolved"
        )
        auto_promotion_preseal_block = _target_block(text, "release-auto-promotion-preseal")
        auto_promotion_preseal_resolved_block = _target_block(
            text, "release-auto-promotion-preseal-resolved"
        )
        self.assertIn(
            "ops.scripts.release_goal_run_identity_guard",
            auto_promotion_goal_identity_block,
        )
        self.assertIn('--goal-run-id "$(GOAL_RUN_ID)"', auto_promotion_goal_identity_block)
        self.assertIn('--goal-run-id-origin "$(origin GOAL_RUN_ID)"', auto_promotion_goal_identity_block)
        self.assertIn("$(MAKE) release-auto-promotion-goal-run-id-guard", auto_promotion_preflight_block)
        self.assertIn("$(MAKE) release-auto-promotion-goal-run-id-guard", auto_promotion_preseal_block)
        self.assertIn("--print-effective-run-id-from-report", auto_promotion_preflight_block)
        self.assertIn("--print-effective-run-id-from-report", auto_promotion_preseal_block)
        self.assertIn("auto-inferred-goal-run-id", auto_promotion_preflight_block)
        self.assertIn("auto-inferred-goal-run-id", auto_promotion_preseal_block)
        self.assertIn(
            '$(MAKE) release-auto-promotion-preflight-resolved GOAL_RUN_ID="$$effective_goal_run_id"',
            auto_promotion_preflight_block,
        )
        self.assertIn(
            '$(MAKE) release-auto-promotion-preseal-resolved GOAL_RUN_ID="$$effective_goal_run_id"',
            auto_promotion_preseal_block,
        )
        self.assertIn(
            "ops.scripts.release_auto_promotion_preflight",
            auto_promotion_preflight_resolved_block,
        )
        self.assertIn("--phase preflight", auto_promotion_preflight_resolved_block)
        self.assertIn("$(MAKE) remediation-backlog", auto_promotion_preflight_resolved_block)
        self.assertIn(
            "$(MAKE) learning-readiness-signoff-revalidation",
            auto_promotion_preflight_resolved_block,
        )
        self.assertIn(
            "$(MAKE) auto-improve-readiness-report-body AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH=1",
            auto_promotion_preflight_resolved_block,
        )
        self.assertEqual(
            _recipe_lines(text, "release-auto-promotion-preseal"),
            [
                "$(MAKE) release-auto-promotion-goal-run-id-guard",
                'if [ -n "$(findstring n,$(firstword $(MAKEFLAGS)))" ]; then if [ "$(origin GOAL_RUN_ID)" = "file" ]; then effective_goal_run_id="auto-inferred-goal-run-id"; else effective_goal_run_id="$(GOAL_RUN_ID)"; fi; else effective_goal_run_id="$$( $(PYTHON) -m ops.scripts.release_goal_run_identity_guard --vault "$(VAULT)" --print-effective-run-id-from-report "$(RELEASE_AUTO_PROMOTION_GOAL_RUN_IDENTITY_OUT)" )"; fi && $(MAKE) release-auto-promotion-preseal-resolved GOAL_RUN_ID="$$effective_goal_run_id"',
            ],
        )
        self.assertEqual(
            _recipe_lines(text, "release-auto-promotion-preseal-resolved")[:10],
            [
                "$(MAKE) release-run-ready-check",
                "$(MAKE) bootstrap-preflight",
                "$(MAKE) registry-preflight",
                "$(MAKE) release-smoke-full-current-check",
                "$(MAKE) release-smoke-fast-refresh-check",
                "$(MAKE) goal-runtime-local-evidence-converge",
                "$(MAKE) release-auto-promotion-safe-cleanup",
                "$(MAKE) learning-readiness-signoff-revalidation",
                '$(MAKE) release-evidence-cohort-preseal-refresh RELEASE_EVIDENCE_COHORT_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)"',
                "$(MAKE) release-closeout-summary-report",
            ],
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "release-auto-promotion-safe-cleanup",
            (
                "$(MAKE) goal-runtime-clean-transient",
                "$(MAKE) tmp-json-clean",
                "ops.scripts.backfill_archived_run_artifacts",
                "$(MAKE) generated-artifact-index",
                "$(MAKE) artifact-freshness-refresh-check",
                "$(MAKE) external-report-reference-manifest-release-check",
                "$(MAKE) release-closeout-batch-manifest-promote",
                "$(MAKE) release-closeout-fixed-point",
                "$(MAKE) release-closeout-summary-report",
            ),
        )
        for expensive_writer in (
            "$(MAKE) test-execution-summary-full-refresh",
            "$(MAKE) test-execution-summary-full-body",
            "$(PYTHON) -m pytest",
            "$(MAKE) generated-artifact-converge",
        ):
            self.assertNotIn(expensive_writer, auto_promotion_preseal_resolved_block)
        self.assertEqual(
            _recipe_lines(text, "release-auto-promotion-preflight"),
            [
                "$(MAKE) release-auto-promotion-goal-run-id-guard",
                'if [ -n "$(findstring n,$(firstword $(MAKEFLAGS)))" ]; then if [ "$(origin GOAL_RUN_ID)" = "file" ]; then effective_goal_run_id="auto-inferred-goal-run-id"; else effective_goal_run_id="$(GOAL_RUN_ID)"; fi; else effective_goal_run_id="$$( $(PYTHON) -m ops.scripts.release_goal_run_identity_guard --vault "$(VAULT)" --print-effective-run-id-from-report "$(RELEASE_AUTO_PROMOTION_GOAL_RUN_IDENTITY_OUT)" )"; fi && $(MAKE) release-auto-promotion-preflight-resolved GOAL_RUN_ID="$$effective_goal_run_id"',
            ],
        )
        self.assertEqual(
            _recipe_lines(text, "release-auto-promotion-preflight-resolved")[:8],
            [
                "$(MAKE) release-smoke-fast-refresh-check",
                "$(MAKE) goal-runtime-local-evidence-converge",
                "$(MAKE) test-execution-summary-report-contract",
                "$(MAKE) artifact-freshness-refresh-check",
                "$(MAKE) auto-improve-readiness-report-body AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH=1",
                "$(MAKE) learning-readiness-signoff-revalidation",
                "$(MAKE) remediation-backlog",
                "$(MAKE) auto-improve-readiness-report-body",
            ],
        )
        self.assertIn(
            '--remediation-backlog "$(REMEDIATION_BACKLOG_OUT)"',
            auto_promotion_preflight_resolved_block,
        )
        self.assertIn(
            '--learning-revalidation "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT)"',
            auto_promotion_preflight_resolved_block,
        )
        self.assertIn(
            '--closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)"',
            auto_promotion_preflight_resolved_block,
        )
        self.assertIn(
            '--evidence-cohort "$(RELEASE_EVIDENCE_COHORT_OUT)"',
            auto_promotion_preflight_resolved_block,
        )
        self.assertIn("ops.scripts.release_auto_promotion_preflight", auto_promotion_preseal_resolved_block)
        self.assertIn("--phase preseal", auto_promotion_preseal_resolved_block)
        self.assertIn("$(MAKE) release-run-ready-check", auto_promotion_preseal_resolved_block)
        self.assertIn("$(MAKE) release-closeout-summary-report", auto_promotion_preseal_resolved_block)
        self.assertIn(
            "$(MAKE) release-evidence-cohort-preseal-refresh",
            auto_promotion_preseal_resolved_block,
        )
        self.assertIn(
            "$(MAKE) release-evidence-cohort RELEASE_EVIDENCE_COHORT_POLICY=strict_same_fingerprint",
            auto_promotion_preseal_resolved_block,
        )
        preseal_recipe = _recipe_lines(text, "release-auto-promotion-preseal-resolved")
        self.assertEqual(preseal_recipe.count("$(MAKE) release-closeout-summary-report"), 1)
        preseal_refresh_line = (
            '$(MAKE) release-evidence-cohort-preseal-refresh '
            'RELEASE_EVIDENCE_COHORT_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)"'
        )
        strict_cohort_line = (
            "$(MAKE) release-evidence-cohort RELEASE_EVIDENCE_COHORT_POLICY=strict_same_fingerprint "
            'RELEASE_EVIDENCE_COHORT_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)"'
        )
        self.assertLess(
            preseal_recipe.index(preseal_refresh_line),
            preseal_recipe.index(strict_cohort_line),
        )
        self.assertLess(
            preseal_recipe.index("$(MAKE) release-clean-blocker-ledger"),
            preseal_recipe.index("$(MAKE) remediation-backlog"),
        )
        self.assertLess(
            preseal_recipe.index(
                "$(MAKE) auto-improve-readiness-report-body AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH=1"
            ),
            preseal_recipe.index("$(MAKE) remediation-backlog"),
        )
        self.assertIn(
            '--remediation-backlog "$(REMEDIATION_BACKLOG_OUT)"',
            auto_promotion_preseal_resolved_block,
        )
        self.assertIn(
            '--learning-revalidation "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT)"',
            auto_promotion_preseal_resolved_block,
        )
        self.assertIn(
            '--closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)"',
            auto_promotion_preseal_resolved_block,
        )
        self.assertIn(
            '--evidence-cohort "$(RELEASE_EVIDENCE_COHORT_OUT)"',
            auto_promotion_preseal_resolved_block,
        )
        self.assertIn("ops.scripts.release_auto_promotion_ready", _target_block(text, "release-auto-promotion-ready"))
        auto_promotion_block = _target_block(text, "release-auto-promotion-ready")
        self.assertIn("$(MAKE) release-auto-promotion-ready-plan", auto_promotion_block)
        self.assertNotIn("$(MAKE) release-auto-promotion-operator-summary", auto_promotion_block)
        self.assertIn('--run-manifest "$(RELEASE_RUN_MANIFEST_OUT)"', auto_promotion_block)
        self.assertIn('--sealed-run-manifest "$(RELEASE_SEALED_RUN_MANIFEST_OUT)"', auto_promotion_block)
        self.assertIn(
            '--auto-promotion-preflight "$(RELEASE_AUTO_PROMOTION_PREFLIGHT_OUT)"',
            auto_promotion_block,
        )
        self.assertIn(
            '--auto-promotion-preseal "$(RELEASE_AUTO_PROMOTION_PRESEAL_OUT)"',
            auto_promotion_block,
        )
        self.assertNotIn("release-sealed-run-ready-ensure", auto_promotion_block)
        self.assertNotIn("learning-readiness-signoff-revalidation", auto_promotion_block)
        self.assertNotIn("auto-improve-readiness-report-body", auto_promotion_block)
        self.assertNotIn("$(MAKE) release-auto-promotion-preflight", auto_promotion_block)
        self.assertNotIn("$(MAKE) release-auto-promotion-preseal", auto_promotion_block)
        self.assertNotIn("$(MAKE) release-sealed-run-ready-check", auto_promotion_block)
        auto_promotion_plan_block = _target_block(text, "release-auto-promotion-ready-plan")
        self.assertIn("ops.scripts.release_evidence_planner", auto_promotion_plan_block)
        self.assertIn("--stage auto-promotion-ready", auto_promotion_plan_block)
        self.assertIn('--run-manifest "$(RELEASE_RUN_MANIFEST_OUT)"', auto_promotion_plan_block)
        self.assertIn(
            '--sealed-run-manifest "$(RELEASE_SEALED_RUN_MANIFEST_OUT)"',
            auto_promotion_plan_block,
        )
        self.assertIn(
            '--auto-promotion-preflight "$(RELEASE_AUTO_PROMOTION_PREFLIGHT_OUT)"',
            auto_promotion_plan_block,
        )
        self.assertIn(
            '--auto-promotion-preseal "$(RELEASE_AUTO_PROMOTION_PRESEAL_OUT)"',
            auto_promotion_plan_block,
        )
        self.assertIn('--self-check "$(RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT)"', _target_block(text, "release-auto-promotion-operator-summary"))
        self.assertIn("$(MAKE) release-worktree-clean-check", core_block)
        self.assertIn("$(MAKE) test-execution-summary-current-check", core_block)
        self.assertIn("$(MAKE) test-execution-summary-full-current-check", core_block)
        self.assertNotIn("$(MAKE) test-report-contract-all", core_block)
        self.assertIn("$(MAKE) static", core_block)
        self.assertIn("$(MAKE) artifact-freshness-check", core_block)
        self.assertIn("$(MAKE) registry-preflight-check", core_block)
        self.assertNotIn("$(MAKE) registry-preflight\n", core_block)
        self.assertIn("$(MAKE) lint", core_block)
        self.assertIn("$(MAKE) eval", core_block)
        self.assertIn("$(MAKE) stage2-eval", core_block)
        self.assertIn("$(MAKE) planning-gate", core_block)
        self.assertNotIn("$(MAKE) unit-tests-release-check", core_block)
        self.assertIn("$(MAKE) release-smoke-full-current-check", core_block)
        self.assertNotIn("$(MAKE) release-smoke-full-reuse", core_block)
        self.assertNotIn("$(MAKE) release-check-post-converge", core_block)
        self.assertIn("$(MAKE) release-check-core", release_check_block)
        self.assertIn("$(MAKE) release-check-post-check", release_check_block)
        self.assertNotIn("$(MAKE) check-all", core_block)
        self.assertNotIn("$(MAKE) unit-tests-all", core_block)
        release_converge_post_block = _target_block(text, "release-converge-post")
        self.assertIn("$(MAKE) generated-artifact-converge", release_converge_post_block)
        self.assertIn("$(MAKE) remediation-backlog", release_converge_post_block)
        self.assertIn("$(MAKE) release-closeout-fixed-point", release_converge_post_block)
        self.assertIn("$(MAKE) operator-release-summary", release_converge_post_block)
        self.assertIn(
            "$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required",
            release_converge_post_block,
        )
        self.assertGreater(
            release_converge_post_block.index("$(MAKE) operator-release-summary"),
            release_converge_post_block.index("$(MAKE) release-closeout-fixed-point"),
        )
        self.assertGreater(
            release_converge_post_block.rindex("$(MAKE) release-closeout-fixed-point"),
            release_converge_post_block.rindex("$(MAKE) generated-artifact-converge"),
        )
        self.assertGreaterEqual(release_converge_post_block.count("$(MAKE) generated-artifact-converge"), 2)
        self.assertGreaterEqual(release_converge_post_block.count("$(MAKE) release-closeout-fixed-point"), 2)
        self.assertNotIn("$(MAKE) generated-artifact-index", _target_block(text, "release-converge-post"))
        self.assertNotIn("$(MAKE) artifact-freshness", _target_block(text, "release-converge-post"))
        self.assertIn("$(MAKE) release-worktree-clean-check", post_check_block)
        self.assertNotIn("$(MAKE) generated-artifact-converge", post_check_block)
        self.assertLess(
            core_block.index("$(MAKE) release-worktree-clean-check"),
            core_block.index("$(MAKE) test-execution-summary-current-check"),
        )
        self.assertLess(
            core_block.index("$(MAKE) test-execution-summary-full-current-check"),
            core_block.index("$(MAKE) release-smoke-full-current-check"),
        )
        self.assertLess(
            release_check_block.index("$(MAKE) release-check-core"),
            release_check_block.index("$(MAKE) release-check-post-check"),
        )
        self.assertIn("$(MAKE) release-check-core", all_surfaces_block)
        self.assertIn("$(MAKE) sync-public-policy-check", all_surfaces_block)
        self.assertIn("$(MAKE) public-check-all-check", all_surfaces_block)
        self.assertIn("$(MAKE) release-check-post-check", all_surfaces_block)
        self.assertNotIn("$(MAKE) sync-public-policy\n", all_surfaces_block)
        self.assertNotIn("$(MAKE) public-check-all\n", all_surfaces_block)
        self.assertNotIn("$(MAKE) release-check\n", all_surfaces_block)
        self.assertLess(
            all_surfaces_block.index("$(MAKE) release-check-core"),
            all_surfaces_block.index("$(MAKE) sync-public-policy-check"),
        )
        self.assertLess(
            all_surfaces_block.index("$(MAKE) sync-public-policy-check"),
            all_surfaces_block.index("$(MAKE) public-check-all-check"),
        )
        self.assertLess(
            all_surfaces_block.index("$(MAKE) public-check-all-check"),
            all_surfaces_block.index("$(MAKE) release-check-post-check"),
        )
        finalized_block = _target_block(text, "release-check-finalized")
        self.assertIn("release-check-finalized", _target_block(text, ".PHONY"))
        self.assertTrue(finalized_block.startswith("release-check-finalized: release-check"))
        self.assertIn("release-check is check-only", finalized_block)
        self.assertIn(
            "developer/package precheck이며 canonical release evidence로 쓰지 않는다",
            release_doc_text,
        )
        self.assertIn(
            "canonical release evidence는 이 full 단일 report인 `ops/reports/release-smoke-report.json`이다",
            release_doc_text,
        )

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

    def test_learning_readiness_signoff_make_targets_are_explicit_operator_ux(
        self,
    ) -> None:
        text = _makefile_text()

        self.assertIn("learning-readiness-signoff", _target_block(text, ".PHONY"))
        self.assertIn("learning-readiness-signoff-check", _target_block(text, ".PHONY"))
        self.assertIn(
            "learning-readiness-signoff-revalidation", _target_block(text, ".PHONY")
        )
        self.assertIn(
            "learning-readiness-signoff-revalidation-check",
            _target_block(text, ".PHONY"),
        )
        self.assertIn(
            "learning-readiness-signoff-template", _target_block(text, ".PHONY")
        )
        self.assertIn(
            "LEARNING_READINESS_SIGNOFF_OUT ?= ops/reports/learning-readiness-signoff.json",
            text,
        )
        self.assertIn(
            "LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT ?= ops/reports/learning-readiness-signoff-revalidation.json",
            text,
        )
        self.assertIn(
            "LEARNING_READINESS_SIGNOFF_REVALIDATION_CHECK_OUT ?= tmp/learning-readiness-signoff-revalidation-check.json",
            text,
        )
        self.assertIn("LEARNING_READINESS_SIGNOFF_REVALIDATION_WINDOW_DAYS ?= 7", text)
        self.assertIn(
            "LEARNING_READINESS_SIGNOFF_REVALIDATION_COMMAND ?= make release-evidence-converge PYTHON=.venv/bin/python",
            text,
        )
        self.assertIn(
            "LEARNING_READINESS_SIGNOFF_REVALIDATION_ENVIRONMENT ?= .venv clean release-builder",
            text,
        )
        self.assertIn("LEARNING_READINESS_SIGNOFF_ACCEPTED_BY ?=", text)
        self.assertIn("LEARNING_READINESS_SIGNOFF_EXPIRY_DAYS ?= 14", text)
        block = _target_block(text, "learning-readiness-signoff")
        self.assertIn("ops.scripts.learning_readiness_signoff", block)
        self.assertIn(
            '--accepted-by "$(LEARNING_READINESS_SIGNOFF_ACCEPTED_BY)"', block
        )
        self.assertIn(
            '--expiry-days "$(LEARNING_READINESS_SIGNOFF_EXPIRY_DAYS)"', block
        )
        self.assertIn('--risk-owner "$(LEARNING_READINESS_SIGNOFF_RISK_OWNER)"', block)
        self.assertIn(
            '--revalidation-condition "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_CONDITION)"',
            block,
        )
        self.assertIn(
            '--rollback-trigger "$(LEARNING_READINESS_SIGNOFF_ROLLBACK_TRIGGER)"', block
        )
        self.assertIn(
            "tmp/learning-readiness-signoff-check-release-closeout-summary.json",
            _target_block(text, "learning-readiness-signoff-check"),
        )
        revalidation_block = _target_block(
            text, "learning-readiness-signoff-revalidation"
        )
        self.assertIn(
            "ops.scripts.learning_readiness_signoff_revalidation", revalidation_block
        )
        self.assertIn(
            '--window-days "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_WINDOW_DAYS)"',
            revalidation_block,
        )
        self.assertIn(
            '--required-command "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_COMMAND)"',
            revalidation_block,
        )
        self.assertIn(
            '--required-environment "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_ENVIRONMENT)"',
            revalidation_block,
        )
        self.assertIn(
            "--fail-on-due",
            _target_block(text, "learning-readiness-signoff-revalidation-check"),
        )
        self.assertIn(
            '--out "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_CHECK_OUT)"',
            _target_block(text, "learning-readiness-signoff-revalidation-check"),
        )
        self.assertIn(
            "$(PYTHON) -m json.tool ops/templates/learning-readiness-signoff.json",
            _target_block(text, "learning-readiness-signoff-template"),
        )

    def test_learning_claim_bundle_delta_scoreboard_and_tmp_clean_alias_are_explicit(
        self,
    ) -> None:
        text = _makefile_text()

        self.assertIn("learning-claim-evidence-bundle", _target_block(text, ".PHONY"))
        self.assertIn(
            "learning-confirmed-legacy-reconstruction", _target_block(text, ".PHONY")
        )
        self.assertIn("public-check-summary", _target_block(text, ".PHONY"))
        self.assertIn(
            "PUBLIC_CHECK_SUMMARY_OUT ?= ops/reports/public-check-summary.json", text
        )
        self.assertIn(
            "LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT ?= ops/reports/learning-claim-evidence-bundle.json",
            text,
        )
        self.assertIn(
            "LEARNING_CONFIRMED_LEGACY_RECONSTRUCTION_OUT ?= ops/reports/learning-confirmed-legacy-reconstruction.json",
            text,
        )
        self.assertIn(
            "LEARNING_CONFIRMED_EVIDENCE_COHORT_OUT ?= ops/reports/learning-confirmed-evidence-cohort.json",
            text,
        )
        self.assertIn(
            "LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY ?= ops/policies/learning-claim-confirmed-improvement.json",
            text,
        )
        bundle_block = _target_block(text, "learning-claim-evidence-bundle")
        legacy_block = _target_block(text, "learning-confirmed-legacy-reconstruction")
        self.assertIn(
            "ops.scripts.learning_confirmed_legacy_reconstruction", legacy_block
        )
        self.assertIn(
            "ops/schemas/learning-confirmed-legacy-reconstruction.schema.json",
            legacy_block,
        )
        self.assertEqual(
            bundle_block.splitlines()[0],
            "learning-claim-evidence-bundle: learning-confirmed-legacy-reconstruction",
        )
        self.assertNotIn(
            "$(MAKE) learning-confirmed-legacy-reconstruction", bundle_block
        )
        self.assertIn("ops.scripts.learning_claim_evidence_bundle", bundle_block)
        self.assertIn(
            "ops/schemas/learning-claim-evidence-bundle.schema.json", bundle_block
        )
        cohort_block = _target_block(text, "learning-confirmed-evidence-cohort")
        self.assertEqual(
            cohort_block.splitlines()[0],
            "learning-confirmed-evidence-cohort: learning-claim-evidence-bundle",
        )
        self.assertIn("ops.scripts.learning_confirmed_evidence_cohort", cohort_block)
        self.assertIn(
            "ops/schemas/learning-confirmed-evidence-cohort.schema.json", cohort_block
        )
        self.assertIn(
            '--evidence-bundle "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT)"', cohort_block
        )
        self.assertIn(
            '--confirmed-policy "$(LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY)"',
            cohort_block,
        )
        public_check_block = _target_block(text, "public-check-summary")
        self.assertIn("ops.scripts.public_check_summary", public_check_block)
        self.assertIn(
            "ops/schemas/public-check-summary.schema.json", public_check_block
        )
        self.assertIn("ops.scripts.canonical_artifact_promote", public_check_block)
        unlock_block = _target_block(text, "learning-claim-unlock-review")
        self.assertEqual(
            unlock_block.splitlines()[0],
            "learning-claim-unlock-review: learning-confirmed-evidence-cohort",
        )
        self.assertIn(
            '--evidence-bundle "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT)"', unlock_block
        )
        self.assertIn(
            '--confirmed-policy "$(LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY)"',
            unlock_block,
        )
        self.assertIn("learning-delta-scoreboard", _target_block(text, ".PHONY"))
        self.assertIn("tmp-clean", _target_block(text, ".PHONY"))
        self.assertIn(
            "LEARNING_DELTA_SCOREBOARD_OUT ?= ops/reports/learning-delta-scoreboard.json",
            text,
        )
        self.assertIn(
            "LEARNING_CLAIM_ACTIVATION_REPORT_OUT ?= ops/reports/learning_claim_activation_report.json",
            text,
        )
        self.assertIn(
            "SESSION_SYNOPSIS_OUT ?= ops/reports/session-synopsis.json",
            text,
        )
        self.assertIn(
            "SELF_IMPROVEMENT_NEGATIVE_LESSONS_OUT ?= ops/reports/self-improvement-negative-lessons.json",
            text,
        )
        self.assertIn(
            "REMEDIATION_BACKLOG_OUT ?= ops/reports/remediation-backlog.json",
            text,
        )
        block = _target_block(text, "learning-delta-scoreboard")
        self.assertEqual(
            block.splitlines()[0],
            "learning-delta-scoreboard: learning-claim-unlock-review",
        )
        self.assertIn("ops.scripts.learning_delta_scoreboard", block)
        self.assertIn("ops/schemas/learning-delta-scoreboard.schema.json", block)
        activation_block = _target_block(text, "learning-claim-activation-report")
        self.assertEqual(
            activation_block.splitlines()[0],
            "learning-claim-activation-report: learning-delta-scoreboard",
        )
        self.assertIn("ops.scripts.learning_claim_activation_report", activation_block)
        self.assertIn(
            "ops/schemas/learning-claim-activation-report.schema.json",
            activation_block,
        )
        synopsis_block = _target_block(text, "session-synopsis")
        self.assertEqual(
            synopsis_block.splitlines()[0],
            "session-synopsis: learning-claim-activation-report",
        )
        self.assertIn("ops.scripts.session_synopsis", synopsis_block)
        self.assertIn("ops/schemas/session-synopsis.schema.json", synopsis_block)
        negative_lessons_block = _target_block(text, "self-improvement-negative-lessons")
        self.assertEqual(
            negative_lessons_block.splitlines()[0],
            "self-improvement-negative-lessons: session-synopsis",
        )
        self.assertIn("ops.scripts.self_improvement_negative_lessons", negative_lessons_block)
        self.assertIn(
            "ops/schemas/self-improvement-negative-lessons.schema.json",
            negative_lessons_block,
        )
        backlog_block = _target_block(text, "remediation-backlog")
        self.assertEqual(
            backlog_block.splitlines()[0],
            "remediation-backlog: self-improvement-negative-lessons session-synopsis",
        )
        self.assertIn("ops.scripts.remediation_backlog", backlog_block)
        self.assertIn("ops/schemas/remediation-backlog.schema.json", backlog_block)
        self.assertIn("tmp-clean: tmp-json-clean", text)
        tmp_json_clean_block = _target_block(text, "tmp-json-clean")
        self.assertIn("find tmp -mindepth 1 -delete", tmp_json_clean_block)
        self.assertNotIn("goal-worktree-guard.json", tmp_json_clean_block)

    def test_report_contracts_target_collects_schema_and_generated_artifact_checks(
        self,
    ) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()
        block = _target_block(text, "report-contracts")
        core_block = _target_block(text, "report-contracts-core")
        all_block = _target_block(text, "report-contracts-all")
        extended_block = _target_block(text, "report-contracts-extended")
        expected_core_tests = pack_selectors(registry, "report_contract_core")
        expected_extended_tests = pack_selectors(registry, "report_contract_extended")

        self.assertIn("report-contracts", _target_block(text, ".PHONY"))
        self.assertIn("report-contracts-core", _target_block(text, ".PHONY"))
        self.assertIn("report-contracts-all", _target_block(text, ".PHONY"))
        self.assertIn("report-contracts-extended", _target_block(text, ".PHONY"))
        self.assertIn("REPORT_CONTRACT_CORE_TESTS ?=", text)
        self.assertIn("REPORT_CONTRACT_EXTENDED_TESTS ?=", text)
        self.assertIn('REPORT_CONTRACT_ALL_TESTS ?= -m "$(PYTEST_REPORT_CONTRACT_MARK_EXPR)"', text)
        self.assertIn("REPORT_CONTRACT_TESTS ?=", text)
        self.assertIn("REPORT_CONTRACT_TESTS ?= $(REPORT_CONTRACT_CORE_TESTS)", text)
        core_items = _makefile_assignment_items(text, "REPORT_CONTRACT_CORE_TESTS")
        extended_items = _makefile_assignment_items(
            text, "REPORT_CONTRACT_EXTENDED_TESTS"
        )
        self.assertEqual(core_items, expected_core_tests)
        self.assertEqual(extended_items, expected_extended_tests)
        for test_path in expected_core_tests:
            with self.subTest(test_path=test_path):
                self.assertIn(test_path, core_items)
        for test_path in expected_extended_tests:
            with self.subTest(test_path=test_path):
                self.assertIn(test_path, extended_items)
                self.assertNotIn(test_path, core_items)
        self.assertIn(
            '$(PYTHON) -m pytest -m "$(PYTEST_REPORT_CONTRACT_MARK_EXPR)" $(REPORT_CONTRACT_TESTS) $(PYTEST_SERIAL_FLAGS)',
            core_block,
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(REPORT_CONTRACT_ALL_TESTS) $(PYTEST_SERIAL_FLAGS)",
            all_block,
        )
        self.assertIn(
            "report-contracts is a compatibility alias",
            block,
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(REPORT_CONTRACT_EXTENDED_TESTS) $(PYTEST_SERIAL_FLAGS)",
            extended_block,
        )

    def test_report_contract_summary_uses_current_report_contract_lane(
        self,
    ) -> None:
        text = _makefile_text()
        block = _target_block(text, "test-report-contract")
        core_block = _target_block(text, "test-report-contract-core")
        all_block = _target_block(text, "test-report-contract-all")

        self.assertIn("test-report-contract", _target_block(text, ".PHONY"))
        self.assertIn("test-report-contract-core", _target_block(text, ".PHONY"))
        self.assertIn("test-report-contract-all", _target_block(text, ".PHONY"))
        self.assertIn("report-contract-summary", _target_block(text, ".PHONY"))
        self.assertIn(
            "REPORT_CONTRACT_SUMMARY_MARK_EXPR ?= $(PYTEST_REPORT_CONTRACT_MARK_EXPR)", text
        )
        self.assertIn(
            "REPORT_CONTRACT_SUMMARY_DESELECT_POLICY ?= ops/policies/report-contract-deselections.json",
            text,
        )
        self.assertIn(
            'REPORT_CONTRACT_SUMMARY_TESTS ?= -m "$(REPORT_CONTRACT_SUMMARY_MARK_EXPR)" $(REPORT_CONTRACT_TESTS)',
            text,
        )
        self.assertNotIn("--deselect=tests/test_", text)
        self.assertIn(
            "$(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_SERIAL_FLAGS)",
            core_block,
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(REPORT_CONTRACT_ALL_TESTS) $(PYTEST_SERIAL_FLAGS)",
            all_block,
        )
        self.assertIn(
            "test-report-contract is a compatibility alias",
            block,
        )
        self.assertIn("report-contract-summary: test-report-contract-core", text)

    def test_report_contract_closeout_runs_pytest_wrapper_once_between_generated_refreshes(
        self,
    ) -> None:
        text = _makefile_text()
        block = _target_block(text, "report-contract-closeout")
        precheck_block = _target_block(text, "report-contract-closeout-precheck")

        self.assertIn("report-contract-closeout", _target_block(text, ".PHONY"))
        self.assertIn("report-contract-closeout:", text)
        self.assertIn("$(MAKE) release-smoke-full-reuse", block)
        self.assertIn("$(MAKE) report-contract-closeout-precheck", block)
        self.assertIn(
            '$(PYTHON) -m ops.scripts.report_contract_closeout_runtime --vault "$(VAULT)"',
            precheck_block,
        )
        self.assertIn("$(MAKE) test-execution-summary", block)
        self.assertNotIn("$(MAKE) script-output-surfaces", block)
        self.assertNotIn("$(MAKE) auto-improve-readiness-report\n", block)
        self.assertEqual(block.count("$(MAKE) generated-artifact-converge"), 3)
        self.assertNotIn("$(MAKE) generated-artifact-index", block)
        self.assertEqual(block.count("$(MAKE) archive-execution-manifest-report"), 0)
        self.assertNotIn("$(MAKE) archive-execution-manifest\n", block)
        self.assertNotIn("$(MAKE) artifact-freshness", block)
        self.assertEqual(block.count("$(MAKE) release-closeout-summary-report"), 2)
        self.assertIn("$(MAKE) release-evidence-cohort", block)
        self.assertIn("$(MAKE) auto-improve-readiness-report-body", block)
        self.assertNotIn("$(PYTHON) -m pytest", block)
        self.assertIn("closeout artifacts", block)
        self.assertLess(
            block.index("$(MAKE) report-contract-closeout-precheck"),
            block.index("$(MAKE) release-smoke-full-reuse"),
        )
        self.assertLess(
            block.index("$(MAKE) release-smoke-full-reuse"),
            block.index("$(MAKE) test-execution-summary"),
        )

    def test_report_contract_closeout_precheck_policy_and_runtime_stay_in_sync(self) -> None:
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
        self.assertEqual(
            recipe_lines,
            [
                "$(MAKE) release-evidence-converge-lane-guard",
                "$(MAKE) refresh-generated-core",
                "$(MAKE) bootstrap-preflight",
                "$(MAKE) registry-preflight",
                "$(MAKE) static",
                "$(MAKE) report-schema-samples-check",
                "$(MAKE) external-report-reference-manifest-settle",
                "$(MAKE) release-smoke-full",
                "$(MAKE) release-source-package-check",
                "$(MAKE) generated-artifact-converge",
                "$(MAKE) test-execution-summary-report-contract-refresh",
                "$(MAKE) generated-artifact-converge",
                "$(MAKE) release-closeout-summary-report",
                "$(MAKE) auto-improve-readiness-report-body",
                "$(MAKE) generated-artifact-converge",
                "$(MAKE) release-closeout-summary-report",
                "$(MAKE) auto-improve-readiness-report-body",
                "$(MAKE) tmp-json-clean",
                "$(MAKE) test-execution-summary-full-refresh",
                "$(MAKE) test-execution-summary",
                "$(MAKE) function-budget-refactor-proposals",
                "$(MAKE) outcome-provenance-gate-policy",
                "$(MAKE) auto-improve-readiness-report-body",
                "$(MAKE) generated-artifact-converge",
                "$(MAKE) public-check-summary",
                "$(MAKE) learning-claim-evidence-bundle",
                "$(MAKE) learning-confirmed-evidence-cohort",
                "$(MAKE) learning-claim-unlock-review",
                "$(MAKE) learning-delta-scoreboard",
                "$(MAKE) learning-claim-activation-report",
                "$(MAKE) session-synopsis",
                "$(MAKE) self-improvement-negative-lessons",
                "$(MAKE) remediation-backlog",
                "$(MAKE) release-closeout-summary",
                "$(MAKE) learning-readiness-signoff-revalidation",
                "$(MAKE) release-evidence-cohort RELEASE_EVIDENCE_COHORT_POLICY=strict_same_fingerprint",
                "$(MAKE) auto-improve-readiness-report-body",
                "$(MAKE) release-evidence-dashboard",
                "$(MAKE) release-lane-summary",
                "$(MAKE) release-clean-blocker-ledger",
                "$(MAKE) generated-artifact-converge",
                "$(MAKE) release-closeout-post-check-finalizer-dry-run",
                "$(MAKE) release-closeout-fixed-point",
                "$(MAKE) operator-release-summary",
                "$(MAKE) generated-artifact-converge",
                "$(MAKE) tmp-json-clean",
                "$(MAKE) release-closeout-finality-verify",
            ],
        )

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
            recipe_lines[fixed_point_index + 3], "$(MAKE) tmp-json-clean"
        )
        self.assertEqual(
            recipe_lines[fixed_point_index + 4],
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

        self.assertIn("release-finality-resettle", _target_block(text, ".PHONY"))
        self.assertEqual(
            recipe_lines,
            [
                "$(MAKE) workflow-dependency-planner",
                "$(MAKE) generated-artifact-converge",
                "$(MAKE) release-closeout-fixed-point",
                "$(MAKE) tmp-json-clean",
                "$(MAKE) release-closeout-finality-verify",
            ],
        )
        self.assertNotIn("$(MAKE) release-evidence-converge", recipe_lines)
        self.assertEqual(recipe_lines[-1], "$(MAKE) release-closeout-finality-verify")

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

        # release-closeout-fixed-point must appear exactly once
        fixed_point_count = sum(
            1 for w, _ in occurrences if w == "release-closeout-fixed-point"
        )
        self.assertEqual(
            fixed_point_count,
            1,
            "release-closeout-fixed-point must appear exactly once in release-evidence-converge",
        )

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

    def test_test_execution_summary_target_wraps_report_contracts(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()

        for target in (
            "test-execution-summary",
            "test-execution-summary-fast",
            "test-execution-summary-public",
            "test-execution-summary-report-contract",
            "test-execution-summary-report-contract-refresh",
            "test-execution-summary-report-contract-refresh-no-smoke",
            "test-execution-summary-current-check",
            "test-execution-summary-full-body",
            "test-execution-summary-full",
            "test-execution-summary-full-refresh",
            "test-execution-summary-full-refresh-no-converge",
            "test-execution-summary-full-current-check",
            "test-execution-summary-full-current-or-refresh",
            "test-execution-summary-reuse",
            "test-execution-summary-aggregate",
        ):
            self.assertIn(target, _target_block(text, ".PHONY"))
        _assert_assignment_exists(
            self, text, "TEST_EXECUTION_SUMMARY_OUT", "ops/reports/test-execution-summary.json"
        )
        _assert_assignment_exists(
            self, text, "TEST_EXECUTION_SUMMARY_CANDIDATE_OUT", "tmp/test-execution-summary.candidate.json"
        )
        _assert_assignment_exists(
            self, text, "TEST_EXECUTION_SUMMARY_CHECK_OUT", "tmp/test-execution-summary-check.json"
        )
        _assert_assignment_exists(
            self, text, "TEST_EXECUTION_SUMMARY_FAST_OUT", "ops/reports/test-execution-summary-fast.json"
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FAST_CANDIDATE_OUT",
            "tmp/test-execution-summary-fast.candidate.json",
        )
        _assert_assignment_exists(
            self, text, "TEST_EXECUTION_SUMMARY_PUBLIC_OUT", "ops/reports/test-execution-summary-public.json"
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_PUBLIC_CANDIDATE_OUT",
            "tmp/test-execution-summary-public.candidate.json",
        )
        _assert_assignment_exists(
            self, text, "TEST_EXECUTION_SUMMARY_FULL_OUT", "ops/reports/test-execution-summary-full.json"
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FULL_CANDIDATE_OUT",
            "tmp/test-execution-summary-full.candidate.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FULL_CHECK_OUT",
            "tmp/test-execution-summary-full-check.json",
        )
        _assert_assignment_not_exists(self, text, "TEST_EXECUTION_SUMMARY_FULL_EXPECTED_NODE_COUNT")
        _assert_assignment_exists(self, text, "RELEASE_AUDIT_PAYLOAD_STAGING_DIR", "build/release-payloads")
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FULL_JUNIT_OUT",
            "$(RELEASE_AUDIT_PAYLOAD_STAGING_DIR)/test-execution-summary-full.junit.xml",
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FULL_LOG_OUT",
            "$(RELEASE_AUDIT_PAYLOAD_STAGING_DIR)/test-execution-summary-full.log",
        )
        _assert_assignment_exists(
            self, text, "TEST_EXECUTION_SUMMARY_REUSE_FROM", "$(TEST_EXECUTION_SUMMARY_OUT)"
        )
        _assert_assignment_exists(
            self, text, "TEST_EXECUTION_SUMMARY_FULL_REUSE_FROM", "$(TEST_EXECUTION_SUMMARY_FULL_OUT)"
        )
        _assert_assignment_exists(
            self, text, "TEST_EXECUTION_SUMMARY_SHARD_DIR", "ops/reports/test-execution-summary-shards"
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR",
            "ops/reports/test-execution-summary-full-shards",
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FAST_SUITE",
            pack_summary_suite(registry, "fast")["suite_id"],
        )
        _assert_assignment_exists(self, text, "TEST_EXECUTION_SUMMARY_PUBLIC_SUITE", "public")
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_SUITE",
            pack_summary_suite(registry, "report_contract_core")["suite_id"],
        )
        _assert_assignment_exists(self, text, "TEST_EXECUTION_SUMMARY_FULL_SUITE", "full")
        _assert_assignment_exists(self, text, "TEST_EXECUTION_SUMMARY_FULL_SHARD_SUITE", "full-shard-1")
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-fast",
            (
                "ops.scripts.test_execution_summary",
                "--collect-nodeids",
                '$(PYTHON) -m pytest -m "$(PYTEST_FAST_MARK_EXPR)"',
                "ops.scripts.canonical_artifact_promote",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-public",
            (
                "ops.scripts.test_execution_summary",
                "--collect-nodeids",
                '$(PYTHON) -m pytest -m "$(PYTEST_PUBLIC_MARK_EXPR)"',
                "ops.scripts.canonical_artifact_promote",
            ),
        )
        _assert_target_depends_on(self, text, "test-public", "test-execution-summary-public")
        self.assertIn(
            '$(MAKE) test-execution-summary-public PYTEST_FLAGS="$(PYTEST_SERIAL_FLAGS)"',
            _target_block(text, "test-public-serial"),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-report-contract",
            (
                "ops.scripts.test_execution_summary",
                "--collect-nodeids",
                '--deselection-policy "$(REPORT_CONTRACT_SUMMARY_DESELECT_POLICY)"',
                "$(REPORT_CONTRACT_SUMMARY_TESTS)",
                "ops.scripts.canonical_artifact_promote",
            ),
        )
        refresh_block = _target_block(
            text, "test-execution-summary-report-contract-refresh"
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-report-contract-refresh",
            (
                "ops.scripts.test_execution_summary",
                "ops.scripts.canonical_artifact_promote",
                "$(MAKE) auto-improve-readiness-report",
                "$(MAKE) release-smoke-full-reuse",
                "$(MAKE) generated-artifact-converge",
            ),
        )
        self.assertNotIn("$(MAKE) release-smoke-full\n", refresh_block)
        self.assertEqual(refresh_block.count("$(MAKE) generated-artifact-converge"), 2)
        self.assertEqual(refresh_block.count("$(MAKE) archive-execution-manifest-report"), 0)
        self.assertNotIn("$(MAKE) artifact-freshness", refresh_block)
        self.assertNotIn("$(MAKE) generated-artifact-index", refresh_block)
        self.assertIn(
            "strict test-execution-summary will rerun later in closeout", refresh_block
        )
        no_smoke_refresh_block = _target_block(
            text, "test-execution-summary-report-contract-refresh-no-smoke"
        )
        self.assertIn("$(MAKE) auto-improve-readiness-report", no_smoke_refresh_block)
        self.assertEqual(no_smoke_refresh_block.count("$(MAKE) generated-artifact-converge"), 2)
        self.assertNotIn("$(MAKE) release-smoke-full-reuse", no_smoke_refresh_block)
        self.assertNotIn("$(MAKE) generated-artifact-index", no_smoke_refresh_block)
        self.assertNotIn("$(MAKE) artifact-freshness", no_smoke_refresh_block)
        self.assertIn(
            "test-execution-summary-report-contract-refresh-no-smoke promoted a non-pass bootstrap summary",
            no_smoke_refresh_block,
        )
        self.assertIn(
            "test-execution-summary: test-execution-summary-report-contract", text
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-current-check",
            (
                "ops.scripts.test_execution_summary",
                '--out "$(TEST_EXECUTION_SUMMARY_CHECK_OUT)"',
                "--collect-nodeids",
                "--reuse-if-current",
                "--reuse-only",
                '--reuse-from "$(TEST_EXECUTION_SUMMARY_REUSE_FROM)"',
                '--deselection-policy "$(REPORT_CONTRACT_SUMMARY_DESELECT_POLICY)"',
            ),
        )
        full_body_block = _target_block(text, "test-execution-summary-full-body")
        self.assertNotIn("$(MAKE) refresh-generated-core", full_body_block)
        self.assertNotIn("$(MAKE) auto-improve-readiness-report-body", full_body_block)
        self.assertNotIn("$(MAKE) release-smoke-full", full_body_block)
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-full-body",
            (
                'rm -rf "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)"',
                'mkdir -p "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)"',
                "ops.scripts.test_execution_summary",
                "--collect-nodeids",
                "--junit-xml-path",
                "--execution-log-out",
                "--failed-nodeids-out",
                "--aggregate",
                "--aggregate-dir",
                "ops.scripts.canonical_artifact_promote",
            ),
        )
        self.assertNotIn("$(MAKE) generated-artifact-converge", full_body_block)
        self.assertNotIn("$(MAKE) test-execution-summary-report-contract-refresh", full_body_block)
        full_block = _target_block(text, "test-execution-summary-full")
        _assert_target_depends_on(self, text, "test-execution-summary-full", "test-execution-summary-full-body")
        self.assertEqual(full_block.count("$(MAKE) generated-artifact-converge"), 1)
        self.assertNotIn("$(PYTHON) -m pytest", full_block)
        self.assertGreater(
            full_block.rindex("$(MAKE) generated-artifact-converge"),
            full_block.index("test-execution-summary-full-body"),
        )
        full_refresh_block = _target_block(text, "test-execution-summary-full-refresh")
        _assert_target_depends_on(self, text, "test-execution-summary-full-refresh", "test-execution-summary-full")
        self.assertIn(
            "full-suite evidence refreshed; collect-only nodeid digest and count recorded in $(TEST_EXECUTION_SUMMARY_FULL_OUT)",
            full_refresh_block,
        )
        self.assertNotIn("node count $$actual does not match expected", full_refresh_block)
        no_converge_full_refresh_block = _target_block(
            text, "test-execution-summary-full-refresh-no-converge"
        )
        _assert_target_depends_on(
            self,
            text,
            "test-execution-summary-full-refresh-no-converge",
            "test-execution-summary-full-body",
        )
        self.assertNotIn("$(MAKE) generated-artifact-converge", no_converge_full_refresh_block)
        self.assertIn(
            "full-suite evidence refreshed without generated artifact convergence",
            no_converge_full_refresh_block,
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-full-current-check",
            (
                "ops.scripts.test_execution_summary",
                '--out "$(TEST_EXECUTION_SUMMARY_FULL_CHECK_OUT)"',
                "--aggregate",
                "--reuse-if-current",
                "--reuse-only",
                '--reuse-from "$(TEST_EXECUTION_SUMMARY_FULL_REUSE_FROM)"',
            ),
        )
        full_current_or_refresh_block = _target_block(
            text, "test-execution-summary-full-current-or-refresh"
        )
        self.assertIn("$(MAKE) test-execution-summary-full-current-check", full_current_or_refresh_block)
        self.assertIn("$(MAKE) test-execution-summary-full-refresh-no-converge", full_current_or_refresh_block)
        self.assertIn("full-suite evidence is current", full_current_or_refresh_block)
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-reuse",
            (
                "ops.scripts.test_execution_summary",
                "--reuse-if-current",
                '--reuse-from "$(TEST_EXECUTION_SUMMARY_REUSE_FROM)"',
                '--deselection-policy "$(REPORT_CONTRACT_SUMMARY_DESELECT_POLICY)"',
                "ops.scripts.canonical_artifact_promote",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-aggregate",
            (
                "ops.scripts.test_execution_summary",
                "--aggregate",
                '--aggregate-dir "$(TEST_EXECUTION_SUMMARY_SHARD_DIR)"',
                "ops.scripts.canonical_artifact_promote",
            ),
        )

    def test_registry_preflight_writes_reproducibility_and_cross_environment_matrix(
        self,
    ) -> None:
        text = _makefile_text()
        block = _target_block(text, "registry-preflight")
        check_block = _target_block(text, "registry-preflight-check")

        self.assertIn("registry-preflight", _target_block(text, ".PHONY"))
        self.assertIn("registry-preflight-check", _target_block(text, ".PHONY"))
        self.assertIn(
            "raw-registry-cross-environment-matrix", _target_block(text, ".PHONY")
        )
        self.assertIn(
            "RAW_REGISTRY_PREFLIGHT_OUT ?= ops/reports/raw-registry-preflight-report.json",
            text,
        )
        self.assertIn(
            "RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_OUT ?= ops/reports/raw-registry-preflight-reproducibility.json",
            text,
        )
        self.assertIn(
            "RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_OUT ?= ops/reports/raw-registry-cross-environment-matrix.json",
            text,
        )
        self.assertIn(
            "RAW_REGISTRY_PREFLIGHT_CHECK_OUT ?= tmp/raw-registry-preflight-report-check.json",
            text,
        )
        self.assertIn(
            "RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_CHECK_OUT ?= tmp/raw-registry-preflight-reproducibility-check.json",
            text,
        )
        self.assertIn(
            "RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_CHECK_OUT ?= tmp/raw-registry-cross-environment-matrix-check.json",
            text,
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.raw_registry_preflight --vault "$(VAULT)" --out "$(RAW_REGISTRY_PREFLIGHT_OUT)" --reproducibility-out "$(RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_OUT)"',
            block,
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.raw_registry_cross_environment_matrix --vault "$(VAULT)" --stored-report "$(RAW_REGISTRY_PREFLIGHT_OUT)" --out "$(RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_OUT)" --require-live',
            block,
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.raw_registry_preflight --vault "$(VAULT)" --out "$(RAW_REGISTRY_PREFLIGHT_CHECK_OUT)" --reproducibility-out "$(RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_CHECK_OUT)"',
            check_block,
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.raw_registry_cross_environment_matrix --vault "$(VAULT)" --stored-report "$(RAW_REGISTRY_PREFLIGHT_CHECK_OUT)" --out "$(RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_CHECK_OUT)" --require-live',
            check_block,
        )

    def test_raw_registry_cross_environment_evidence_bundle_targets_collect_ci_reports(
        self,
    ) -> None:
        text = _makefile_text()

        self.assertIn(
            "raw-registry-cross-environment-evidence-bundle",
            _target_block(text, ".PHONY"),
        )
        self.assertIn(
            "raw-registry-cross-environment-evidence-bundle-check",
            _target_block(text, ".PHONY"),
        )
        self.assertIn(
            "RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_OUT ?= ops/reports/raw-registry-cross-environment-evidence-bundle.json",
            text,
        )
        self.assertIn(
            "RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_STAGING_OUT ?= tmp/raw-registry-cross-environment-evidence-bundle.candidate.json",
            text,
        )
        self.assertIn(
            "RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_DIAGNOSTIC_OUT ?= tmp/raw-registry-cross-environment-evidence-bundle-check.json",
            text,
        )
        self.assertIn(
            "RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_STAGING_OUT ?= tmp/raw-registry-cross-environment-evidence-bundle.candidate.json",
            text,
        )
        self.assertIn(
            "RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_DIAGNOSTIC_OUT ?= tmp/raw-registry-cross-environment-evidence-bundle-check.json",
            text,
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.raw_registry_cross_environment_evidence_bundle --vault "$(VAULT)" --reports-dir "ops/reports" --out "$(RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_STAGING_OUT)"',
            _target_block(text, "raw-registry-cross-environment-evidence-bundle"),
        )
        self.assertIn(
            "ops.scripts.canonical_artifact_promote",
            _target_block(text, "raw-registry-cross-environment-evidence-bundle"),
        )
        self.assertNotIn(
            "cp ", _target_block(text, "raw-registry-cross-environment-evidence-bundle")
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.raw_registry_cross_environment_evidence_bundle --vault "$(VAULT)" --reports-dir "ops/reports" --out "$(RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_DIAGNOSTIC_OUT)"',
            _target_block(text, "raw-registry-cross-environment-evidence-bundle-check"),
        )
        self.assertNotIn(
            "$(RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_OUT)",
            _target_block(text, "raw-registry-cross-environment-evidence-bundle-check"),
        )

    def test_dev_install_creates_editable_environment(self) -> None:
        text = _makefile_text()

        block = _target_block(text, "dev-install")
        self.assertIn('uv pip install --python "$(VENV_PYTHON)" -e .', block)
        self.assertIn('"$(VENV_PYTHON)" -m pip install -e .', block)

    def test_bootstrap_preflight_target_writes_canonical_report_with_project_python(
        self,
    ) -> None:
        text = _makefile_text()

        self.assertIn("bootstrap-preflight", _target_block(text, ".PHONY"))
        self.assertIn(
            "BOOTSTRAP_PREFLIGHT_OUT ?= ops/reports/bootstrap-preflight-report.json",
            text,
        )
        self.assertIn("BOOTSTRAP_PREFLIGHT_ENVIRONMENT_CLASS ?= developer", text)
        self.assertIn(
            '$(PYTHON) -m ops.scripts.bootstrap_preflight --vault "$(VAULT)" --dev --environment-class "$(BOOTSTRAP_PREFLIGHT_ENVIRONMENT_CLASS)" --out "$(BOOTSTRAP_PREFLIGHT_OUT)"',
            _target_block(text, "bootstrap-preflight"),
        )

    def test_refresh_generated_splits_core_outputs_from_observability_outputs(
        self,
    ) -> None:
        text = _makefile_text()

        _assert_refresh_generated_split_targets(self, text)
        _assert_observability_output_variables(self, text)
        _assert_script_surface_and_inventory_targets(self, text)
        _assert_workflow_dependency_planner_target(self, text)
        _assert_release_workflow_order_guard_target(self, text)
        _assert_function_budget_and_outcome_targets(self, text)
        _assert_external_report_action_matrix_target(self, text)

    def test_auto_improve_readiness_target_does_not_self_dirty_with_core_refresh(self) -> None:
        text = _makefile_text()

        self.assertIn(
            "AUTO_IMPROVE_READINESS_OUT ?= ops/reports/auto-improve-readiness.json",
            text,
        )
        self.assertIn(
            "AUTO_IMPROVE_READINESS_CANDIDATE_OUT ?= tmp/auto-improve-readiness.candidate.json",
            text,
        )
        self.assertIn("AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH ?= 0", text)
        self.assertIn(
            "auto-improve-readiness: auto-improve-readiness-worktree-guard",
            text,
        )
        self.assertNotIn(
            "auto-improve-readiness: refresh-generated-core",
            text,
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.auto_improve_readiness --vault "$(VAULT)" --out "$(AUTO_IMPROVE_READINESS_CANDIDATE_OUT)"',
            _target_block(text, "auto-improve-readiness"),
        )
        self.assertIn(
            "ops.scripts.canonical_artifact_promote",
            _target_block(text, "auto-improve-readiness"),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "auto-improve-readiness-report",
            (
                "$(MAKE) auto-improve-readiness-worktree-guard",
                "$(MAKE) refresh-generated-core",
                "$(MAKE) auto-improve-readiness-report-body AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH=0",
                "$(MAKE) remediation-backlog",
            ),
        )
        self.assertIn("auto-improve-readiness-report-body:", text)
        self.assertIn(
            'if [ "$(AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH)" = "1" ]; then $(MAKE) auto-improve-readiness-worktree-guard; fi',
            _target_block(text, "auto-improve-readiness-report-body"),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "auto-improve-readiness-worktree-guard",
            (
                "ops.scripts.goal_worktree_guard",
                "--requested-mode \"$(GOAL_WORKTREE_MODE)\"",
                "--out \"$(GOAL_WORKTREE_GUARD_OUT)\"",
            ),
        )

    def test_auto_improve_goal_targets_write_contract_and_status_report(self) -> None:
        text = _makefile_text()

        for variable, expected in (
            ("CODEX_GOAL_CONTRACT_OUT", "ops/reports/codex-goal-contract.json"),
            ("CODEX_GOAL_PROMPT_OUT", "ops/reports/codex-goal-prompt.json"),
            ("GOAL_RUN_ID", "auto-improve-trial"),
            ("GOAL_CONTRACT_RUN_ID", "$(GOAL_RUN_ID)"),
            ("GOAL_ACTIVE_STATE_DIR", "runs/goal-$(GOAL_CONTRACT_RUN_ID)/state"),
            (
                "CODEX_GOAL_ACTIVE_CONTRACT_OUT",
                "$(GOAL_ACTIVE_STATE_DIR)/codex-goal-contract.json",
            ),
            ("GOAL_WORKTREE_GUARD_OUT", "ops/reports/goal-worktree-guard.json"),
            ("GOAL_WORKTREE_MODE", "git"),
            ("GOAL_RUN_STATUS_OUT", "ops/reports/goal-run-status.json"),
            (
                "GOAL_ACTIVE_RUN_STATUS_OUT",
                "$(GOAL_ACTIVE_STATE_DIR)/goal-run-status.json",
            ),
            (
                "GOAL_RUN_STATUS_CANDIDATE_OUT",
                "$(GOAL_ACTIVE_STATE_DIR)/goal-run-status.candidate.json",
            ),
            (
                "GOAL_LOCAL_READINESS_OUT",
                "$(GOAL_ACTIVE_STATE_DIR)/auto-improve-readiness.json",
            ),
            (
                "GOAL_LOCAL_READINESS_CANDIDATE_OUT",
                "$(GOAL_ACTIVE_STATE_DIR)/auto-improve-readiness.candidate.json",
            ),
            (
                "GOAL_LOCAL_SESSION_SYNOPSIS_OUT",
                "$(GOAL_ACTIVE_STATE_DIR)/session-synopsis.json",
            ),
            (
                "GOAL_LOCAL_SESSION_SYNOPSIS_CANDIDATE_OUT",
                "$(GOAL_ACTIVE_STATE_DIR)/session-synopsis.candidate.json",
            ),
            (
                "GOAL_LOCAL_NEGATIVE_LESSONS_OUT",
                "$(GOAL_ACTIVE_STATE_DIR)/self-improvement-negative-lessons.json",
            ),
            (
                "GOAL_LOCAL_NEGATIVE_LESSONS_CANDIDATE_OUT",
                "$(GOAL_ACTIVE_STATE_DIR)/self-improvement-negative-lessons.candidate.json",
            ),
            (
                "GOAL_LOCAL_REMEDIATION_BACKLOG_OUT",
                "$(GOAL_ACTIVE_STATE_DIR)/remediation-backlog.json",
            ),
            (
                "GOAL_LOCAL_REMEDIATION_BACKLOG_CANDIDATE_OUT",
                "$(GOAL_ACTIVE_STATE_DIR)/remediation-backlog.candidate.json",
            ),
            ("GOAL_RUNTIME_CERTIFICATE_OUT", "ops/reports/goal-runtime-certificate.json"),
            (
                "GOAL_RUNTIME_CERTIFICATE_CANDIDATE_OUT",
                "tmp/goal-runtime-certificate.candidate.json",
            ),
            ("GOAL_RUNTIME_CLEAN_TRANSIENT_OUT", "tmp/goal-runtime-clean-transient.json"),
            ("GOAL_RUNTIME_CLEAN_TRANSIENT_APPLY", "1"),
            (
                "GOAL_RUNTIME_CLEAN_TRANSIENT_STATUS_REPORT",
                "$(GOAL_RUN_STATUS_OUT)",
            ),
            (
                "GOAL_RUNTIME_QUARANTINE_PREFLIGHT_OUT",
                "tmp/goal-runtime-quarantine-preflight.json",
            ),
            (
                "GOAL_RUNTIME_FIXED_POINT_CHECK_OUT",
                "tmp/goal-runtime-fixed-point-check.json",
            ),
            (
                "GOAL_RUNTIME_LOCAL_EVIDENCE_REFRESH_OUT",
                "tmp/goal-runtime-local-evidence-refresh.json",
            ),
            ("GOAL_RUNTIME_LOCAL_EVIDENCE_REFRESH_MAX_ITERATIONS", "6"),
            ("GOAL_RUNTIME_LOCAL_EVIDENCE_REFRESH_TIMEOUT_SECONDS", "300"),
            (
                "GOAL_RUNTIME_RUN_ADMISSION_OUT",
                "tmp/goal-runtime-run-admission.json",
            ),
            ("GOAL_RUNTIME_RUN_ADMISSION_MAINTENANCE_ACTION_PLAN", ""),
            (
                "GOAL_MAINTENANCE_ACTION_PLAN_OUT",
                "$(GOAL_ACTIVE_STATE_DIR)/maintenance-action.json",
            ),
            (
                "GOAL_RUNTIME_CLOSEOUT_PLAN_OUT",
                "tmp/goal-runtime-closeout-plan.json",
            ),
            ("GOAL_RUNTIME_CLOSEOUT_BUDGET", "cheap"),
            ("GOAL_RUNTIME_CLOSEOUT_STATE_DIR", "$(GOAL_ACTIVE_STATE_DIR)/closeout"),
            (
                "GOAL_RUNTIME_CLOSEOUT_SCRIPT_OUTPUT_SURFACES_OUT",
                "$(GOAL_RUNTIME_CLOSEOUT_STATE_DIR)/script-output-surfaces.json",
            ),
            (
                "GOAL_RUNTIME_CLOSEOUT_GENERATED_ARTIFACT_INDEX_OUT",
                "$(GOAL_RUNTIME_CLOSEOUT_STATE_DIR)/generated-artifact-index.json",
            ),
            (
                "GOAL_RUNTIME_CLOSEOUT_ARTIFACT_FRESHNESS_OUT",
                "$(GOAL_RUNTIME_CLOSEOUT_STATE_DIR)/artifact-freshness-report.json",
            ),
            ("GOAL_RUNTIME_LOCK_PATH", "$(GOAL_RUN_LOG_DIR)/goal-runtime.lock.json"),
            (
                "GOAL_RUNTIME_PYTHON_PREFLIGHT_OUT",
                "tmp/goal-runtime-python-preflight.json",
            ),
            (
                "GOAL_SESSION_RESULT_OUT",
                "$(GOAL_ACTIVE_STATE_DIR)/auto-improve-goal-session-result.json",
            ),
            ("GOAL_RUN_STATUS", "blocked"),
            ("GOAL_RUNTIME_MODE", "self_improvement_loop"),
            ("GOAL_RUNTIME_SECONDS", "21600"),
            ("GOAL_MAX_UNATTENDED_SECONDS", "$(GOAL_RUNTIME_SECONDS)"),
            ("GOAL_RUNNER_TIMEOUT_SECONDS", "28800"),
            ("GOAL_MAX_MINUTES", "360"),
            ("GOAL_MAX_PROPOSALS", "1"),
            ("GOAL_MAX_CONSECUTIVE_FAILURES", "1"),
            ("GOAL_MAINTAIN_UNTIL_BUDGET", "0"),
            ("GOAL_MAINTENANCE_INTERVAL_SECONDS", "300"),
            ("GOAL_POST_PROMOTE_MAINTENANCE_CYCLES", "1"),
            ("GOAL_EXECUTOR", "codex_exec"),
            ("GOAL_ARTIFACT_CLASS", "system_mechanism"),
            ("GOAL_FINAL_STATUS", "stopped"),
            ("GOAL_RUN_LOG_DIR", "build/goal-runs"),
        ):
            _assert_assignment_exists(self, text, variable, expected)
        for variable in (
            "GOAL_WORKTREE_STRICT",
            "GOAL_ALLOW_LEARNING_UNCERTAIN",
            "GOAL_RUNTIME_CERTIFICATE_MODE",
            "GOAL_RUNTIME_CERTIFICATE_APPLY",
        ):
            _assert_assignment_exists(self, text, variable, "")
        run_command = _assert_assignment_exists(self, text, "GOAL_RUN_COMMAND")
        self.assertIn("ops.scripts.auto_improve_loop", run_command)
        self.assertIn("--session-id \"$(GOAL_RUN_ID)\"", run_command)
        self.assertIn("--goal-contract \"$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)\"", run_command)
        self.assertIn("--executor \"$(GOAL_EXECUTOR)\"", run_command)
        self.assertIn("--class \"$(GOAL_ARTIFACT_CLASS)\"", run_command)
        self.assertIn("$(if $(GOAL_ALLOW_LEARNING_UNCERTAIN),--allow-learning-uncertain,)", run_command)
        self.assertIn("$(if $(GOAL_MAINTAIN_UNTIL_BUDGET),--maintain-until-budget,)", run_command)
        self.assertIn("--maintenance-interval-seconds \"$(GOAL_MAINTENANCE_INTERVAL_SECONDS)\"", run_command)
        self.assertIn(
            "--post-promote-maintenance-cycles \"$(GOAL_POST_PROMOTE_MAINTENANCE_CYCLES)\"",
            run_command,
        )
        resume_command = _assert_assignment_exists(self, text, "GOAL_RESUME_COMMAND")
        self.assertIn("ops.scripts.auto_improve_loop", resume_command)
        self.assertIn("--resume-session \"$(GOAL_RUN_ID)\"", resume_command)
        self.assertIn("--goal-contract \"$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)\"", resume_command)
        self.assertIn("--max-minutes \"$(GOAL_MAX_MINUTES)\"", resume_command)
        self.assertIn("--max-proposals \"$(GOAL_MAX_PROPOSALS)\"", resume_command)
        self.assertIn(
            "--max-consecutive-failures \"$(GOAL_MAX_CONSECUTIVE_FAILURES)\"",
            resume_command,
        )
        self.assertIn("$(if $(GOAL_MAINTAIN_UNTIL_BUDGET),--maintain-until-budget,)", resume_command)
        self.assertIn("--maintenance-interval-seconds \"$(GOAL_MAINTENANCE_INTERVAL_SECONDS)\"", resume_command)
        self.assertIn(
            "--post-promote-maintenance-cycles \"$(GOAL_POST_PROMOTE_MAINTENANCE_CYCLES)\"",
            resume_command,
        )
        maintenance_action_command = _assert_assignment_exists(
            self,
            text,
            "GOAL_MAINTENANCE_ACTION_NEXT_MAX_PROPOSALS",
        )
        self.assertIn("ops.scripts.auto_improve_loop", maintenance_action_command)
        self.assertIn("--resume-session \"$(GOAL_RUN_ID)\"", maintenance_action_command)
        self.assertIn(
            "--print-maintenance-action-next-max-proposals",
            maintenance_action_command,
        )
        self.assertIn(
            "--maintenance-action-plan-out \"$(GOAL_MAINTENANCE_ACTION_PLAN_OUT)\"",
            maintenance_action_command,
        )
        phony = _target_block(text, ".PHONY")
        for target in (
            "codex-goal-contract",
            "codex-goal-prompt",
            "codex-goal-client",
            "auto-improve-readiness-worktree-guard",
            "auto-improve-goal-contract",
            "goal-runtime-refresh",
            "goal-runtime-publish-snapshot",
            "goal-runtime-local-readiness",
            "goal-runtime-local-session-synopsis",
            "goal-runtime-local-negative-lessons",
            "goal-runtime-local-remediation-backlog",
            "goal-runtime-local-fixed-point-check",
            "goal-runtime-local-evidence-refresh",
            "goal-runtime-local-evidence-converge",
            "goal-runtime-publish-local-evidence",
            "goal-runtime-reconcile",
            "goal-runtime-pre-run-cleanup",
            "goal-runtime-between-run-settle",
            "goal-runtime-closeout-plan",
            "goal-runtime-closeout-candidate-script-output-surfaces",
            "goal-runtime-closeout-candidate-generated-artifact-index",
            "goal-runtime-closeout-candidate-artifact-freshness",
            "goal-runtime-closeout-candidate-converge",
            "goal-runtime-closeout-publish-script-output-surfaces",
            "goal-runtime-closeout-publish",
            "goal-runtime-closeout-finalize",
            "goal-runtime-closeout",
            "goal-runtime-closeout-full",
            "goal-runtime-clean-transient",
            "goal-runtime-quarantine-preflight",
            "goal-runtime-fixed-point-check",
            "goal-runtime-run-admission-converge",
            "goal-runtime-run-admission-local-refresh",
            "goal-runtime-run-admission",
            "goal-runtime-run-admission-resume",
            "goal-runtime-maintenance-action-plan",
            "goal-runtime-lock-check",
            "goal-runtime-lock-status",
            "goal-runtime-lock-stop",
            "goal-runtime-python-preflight",
            "long-run-preflight-clean",
            "auto-improve-goal-preflight",
            "auto-improve-goal-run",
            "auto-improve-goal-status",
            "auto-improve-goal-resume",
            "auto-improve-goal-maintenance-action",
            "auto-improve-goal-finalize",
            "auto-improve-goal-run-artifacts",
            "goal-runtime-certificate",
            "goal-worktree-guard",
        ):
            self.assertIn(target, phony)
        codex_contract_header = _target_block(text, "codex-goal-contract").splitlines()[0]
        self.assertNotIn("auto-improve-goal-contract", codex_contract_header)
        _assert_target_depends_on(self, text, "codex-goal-prompt", "codex-goal-contract")
        _assert_target_depends_on(self, text, "goal-runtime-refresh", "auto-improve-goal-status")
        _assert_target_depends_on(self, text, "goal-runtime-run-admission-converge", "goal-runtime-lock-check")
        _assert_target_depends_on(
            self,
            text,
            "goal-runtime-run-admission-converge",
            "goal-runtime-python-preflight",
        )
        _assert_target_depends_on(self, text, "goal-runtime-run-admission-local-refresh", "goal-runtime-lock-check")
        _assert_target_depends_on(
            self,
            text,
            "goal-runtime-run-admission-local-refresh",
            "goal-runtime-python-preflight",
        )
        _assert_target_depends_on(self, text, "goal-runtime-run-admission", "goal-runtime-run-admission-local-refresh")
        _assert_target_depends_on(self, text, "long-run-preflight-clean", "goal-runtime-run-admission-converge")
        _assert_target_depends_on(self, text, "auto-improve-goal-preflight", "goal-runtime-lock-check")
        _assert_target_depends_on(
            self,
            text,
            "auto-improve-goal-preflight",
            "goal-runtime-python-preflight",
        )
        _assert_target_depends_on(self, text, "auto-improve-goal-run", "goal-runtime-run-admission")
        _assert_target_depends_on(self, text, "auto-improve-goal-run", "auto-improve-goal-contract")
        _assert_target_depends_on(self, text, "auto-improve-goal-status", "auto-improve-goal-contract")
        admission_block = _target_block(text, "goal-runtime-run-admission")
        self.assertIn(
            "$(if $(GOAL_ALLOW_LEARNING_UNCERTAIN),--allow-learning-uncertain,)",
            admission_block,
        )
        _assert_target_depends_on(self, text, "goal-runtime-run-admission-resume", "goal-runtime-run-admission")
        _assert_target_depends_on(
            self,
            text,
            "goal-runtime-maintenance-action-plan",
            "goal-runtime-between-run-settle",
        )
        _assert_target_depends_on(self, text, "auto-improve-goal-resume", "goal-runtime-run-admission-resume")
        _assert_target_depends_on(self, text, "auto-improve-goal-resume", "auto-improve-goal-contract")
        _assert_target_depends_on(
            self,
            text,
            "auto-improve-goal-maintenance-action",
            "goal-runtime-maintenance-action-plan",
        )
        _assert_target_depends_on(self, text, "auto-improve-goal-finalize", "auto-improve-goal-contract")
        _assert_target_depends_on(self, text, "auto-improve-goal-run-artifacts", "auto-improve-goal-status")
        _assert_target_depends_on(self, text, "goal-runtime-certificate", "auto-improve-goal-contract")
        _assert_target_depends_on(self, text, "goal-worktree-guard", "auto-improve-goal-preflight")
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-run-admission-converge",
            (
                "$(MAKE) refresh-generated-core",
                "$(MAKE) release-smoke-fast-refresh-check",
                "$(MAKE) goal-runtime-pre-run-cleanup",
                "$(MAKE) goal-runtime-quarantine-preflight",
                "$(MAKE) goal-runtime-publish-local-evidence",
                "$(MAKE) goal-runtime-fixed-point-check",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-run-admission-local-refresh",
            (
                "$(MAKE) release-smoke-fast-refresh-check",
                "$(MAKE) goal-runtime-pre-run-cleanup",
                "$(MAKE) goal-runtime-quarantine-preflight",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-pre-run-cleanup",
            (
                "$(MAKE) tmp-json-clean",
                "$(MAKE) goal-runtime-clean-transient",
                "$(MAKE) goal-runtime-local-evidence-converge",
                "$(MAKE) artifact-freshness-refresh-check",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-between-run-settle",
            (
                "$(MAKE) refresh-generated-core",
                "$(MAKE) goal-runtime-pre-run-cleanup",
                "$(MAKE) goal-runtime-publish-local-evidence",
                "$(MAKE) goal-runtime-fixed-point-check",
            ),
        )
        for admission_target in (
            "goal-runtime-pre-run-cleanup",
        ):
            admission_recipe = _recipe_lines(text, admission_target)
            self.assertLess(
                admission_recipe.index("$(MAKE) tmp-json-clean"),
                admission_recipe.index("$(MAKE) goal-runtime-clean-transient"),
            )
            self.assertLess(
                admission_recipe.index("$(MAKE) goal-runtime-local-evidence-converge"),
                admission_recipe.index("$(MAKE) artifact-freshness-refresh-check"),
            )
        for admission_target in (
            "goal-runtime-run-admission-converge",
            "goal-runtime-run-admission-local-refresh",
        ):
            admission_recipe = _recipe_lines(text, admission_target)
            self.assertLess(
                admission_recipe.index("$(MAKE) goal-runtime-pre-run-cleanup"),
                admission_recipe.index("$(MAKE) goal-runtime-quarantine-preflight"),
            )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-run-admission",
            (
                "ops.scripts.goal_runtime_run_admission",
                "--out \"$(GOAL_RUNTIME_RUN_ADMISSION_OUT)\"",
                "--quarantine-preflight-report \"$(GOAL_RUNTIME_QUARANTINE_PREFLIGHT_OUT)\"",
                "--mutation-proposals-report \"$(MUTATION_PROPOSAL_OUT)\"",
                "--readiness-report \"$(GOAL_LOCAL_READINESS_OUT)\"",
                "--remediation-backlog-report \"$(GOAL_LOCAL_REMEDIATION_BACKLOG_OUT)\"",
                "--maintenance-action-plan \"$(GOAL_RUNTIME_RUN_ADMISSION_MAINTENANCE_ACTION_PLAN)\"",
                "--strict",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-quarantine-preflight",
            (
                "ops.scripts.goal_runtime_quarantine_preflight",
                "--out \"$(GOAL_RUNTIME_QUARANTINE_PREFLIGHT_OUT)\"",
                "--mechanism-review-report \"$(MECHANISM_REVIEW_OUT)\"",
                "--strict",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "codex-goal-client",
            (
                "tests/test_codex_goal_contract.py",
                "tests/test_codex_goal_client.py",
                "tests/test_codex_goal_prompt.py",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "auto-improve-goal-contract",
            (
                "ops.scripts.codex_goal_client",
                "--out \"$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)\"",
                "--backend-type run_local_file",
                "--runtime-mode \"$(GOAL_RUNTIME_MODE)\"",
                "--max-unattended-seconds \"$(GOAL_MAX_UNATTENDED_SECONDS)\"",
                "--max-proposals \"$(GOAL_MAX_PROPOSALS)\"",
                "--max-consecutive-failures \"$(GOAL_MAX_CONSECUTIVE_FAILURES)\"",
                "--goal-status-path \"$(GOAL_ACTIVE_RUN_STATUS_OUT)\"",
                "--readiness-report \"$(GOAL_LOCAL_READINESS_OUT)\"",
                "--worktree-guard-report \"$(GOAL_WORKTREE_GUARD_OUT)\"",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "codex-goal-contract",
            (
                "ops.scripts.codex_goal_client",
                "--out \"$(CODEX_GOAL_CONTRACT_OUT)\"",
                "--backend-type file",
                "--goal-status-path \"$(GOAL_RUN_STATUS_OUT)\"",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "codex-goal-prompt",
            (
                "ops.scripts.codex_goal_prompt",
                "--goal-contract \"$(CODEX_GOAL_CONTRACT_OUT)\"",
                "--out \"$(CODEX_GOAL_PROMPT_OUT)\"",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-lock-check",
            (
                "ops.scripts.goal_runtime_lock check",
                "--lock-path \"$(GOAL_RUNTIME_LOCK_PATH)\"",
                "--cleanup-stale",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-lock-status",
            (
                "ops.scripts.goal_runtime_lock status",
                "--lock-path \"$(GOAL_RUNTIME_LOCK_PATH)\"",
                "--json",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-lock-stop",
            (
                "ops.scripts.goal_runtime_lock stop",
                "--lock-path \"$(GOAL_RUNTIME_LOCK_PATH)\"",
                "--json",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-python-preflight",
            (
                "ops.scripts.bootstrap_preflight",
                "--dev",
                "--environment-class goal-runtime",
                "--out \"$(GOAL_RUNTIME_PYTHON_PREFLIGHT_OUT)\"",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "auto-improve-goal-preflight",
            (
                "ops.scripts.goal_worktree_guard",
                "--requested-mode \"$(GOAL_WORKTREE_MODE)\"",
                "--out \"$(GOAL_WORKTREE_GUARD_OUT)\"",
                "$(if $(GOAL_WORKTREE_STRICT),--strict,)",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "auto-improve-goal-status",
            (
                "ops.scripts.goal_run_status",
                "--goal-contract \"$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)\"",
                "--status-report-path \"$(GOAL_ACTIVE_RUN_STATUS_OUT)\"",
                "--out \"$(GOAL_RUN_STATUS_CANDIDATE_OUT)\"",
                "--write-run-artifacts",
                "ops.scripts.canonical_artifact_promote",
                "--schema ops/schemas/goal-run-status.schema.json",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-publish-snapshot",
            (
                "--candidate \"$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)\"",
                "--out \"$(CODEX_GOAL_CONTRACT_OUT)\"",
                "--candidate \"$(GOAL_ACTIVE_RUN_STATUS_OUT)\"",
                "--out \"$(GOAL_RUN_STATUS_OUT)\"",
                "--goal-contract \"$(CODEX_GOAL_CONTRACT_OUT)\"",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-clean-transient",
            (
                "ops.scripts.goal_runtime_clean_transient",
                "--out \"$(GOAL_RUNTIME_CLEAN_TRANSIENT_OUT)\"",
                "--status-report \"$(GOAL_RUNTIME_CLEAN_TRANSIENT_STATUS_REPORT)\"",
                "$(if $(GOAL_RUNTIME_CLEAN_TRANSIENT_APPLY),--apply,)",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-fixed-point-check",
            (
                "ops.scripts.goal_runtime_fixed_point_check",
                "--out \"$(GOAL_RUNTIME_FIXED_POINT_CHECK_OUT)\"",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-local-readiness",
            (
                "ops.scripts.auto_improve_readiness",
                "--out \"$(GOAL_LOCAL_READINESS_CANDIDATE_OUT)\"",
                "--remediation-backlog \"$(GOAL_LOCAL_REMEDIATION_BACKLOG_OUT)\"",
                "--out \"$(GOAL_LOCAL_READINESS_OUT)\"",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-local-session-synopsis",
            (
                "ops.scripts.session_synopsis",
                "--out \"$(GOAL_LOCAL_SESSION_SYNOPSIS_CANDIDATE_OUT)\"",
                "--auto-improve-readiness \"$(GOAL_LOCAL_READINESS_OUT)\"",
                "--goal-run-status \"$(GOAL_ACTIVE_RUN_STATUS_OUT)\"",
                "--out \"$(GOAL_LOCAL_SESSION_SYNOPSIS_OUT)\"",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-local-negative-lessons",
            (
                "ops.scripts.self_improvement_negative_lessons",
                "--out \"$(GOAL_LOCAL_NEGATIVE_LESSONS_CANDIDATE_OUT)\"",
                "--session-synopsis \"$(GOAL_LOCAL_SESSION_SYNOPSIS_OUT)\"",
                "--out \"$(GOAL_LOCAL_NEGATIVE_LESSONS_OUT)\"",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-local-remediation-backlog",
            (
                "ops.scripts.remediation_backlog",
                "--out \"$(GOAL_LOCAL_REMEDIATION_BACKLOG_CANDIDATE_OUT)\"",
                "--self-improvement-negative-lessons \"$(GOAL_LOCAL_NEGATIVE_LESSONS_OUT)\"",
                "--session-synopsis \"$(GOAL_LOCAL_SESSION_SYNOPSIS_OUT)\"",
                "--out \"$(GOAL_LOCAL_REMEDIATION_BACKLOG_OUT)\"",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-local-fixed-point-check",
            (
                "--codex-goal-contract \"$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)\"",
                "--goal-run-status \"$(GOAL_ACTIVE_RUN_STATUS_OUT)\"",
                "--auto-improve-readiness \"$(GOAL_LOCAL_READINESS_OUT)\"",
                "--session-synopsis \"$(GOAL_LOCAL_SESSION_SYNOPSIS_OUT)\"",
                "--remediation-backlog \"$(GOAL_LOCAL_REMEDIATION_BACKLOG_OUT)\"",
            ),
        )
        reconcile_block = _target_block(text, "goal-runtime-reconcile")
        self.assertNotIn("$(MAKE) goal-runtime-publish-snapshot", reconcile_block)
        self.assertNotIn("$(MAKE) session-synopsis", reconcile_block)
        self.assertNotIn("$(MAKE) remediation-backlog", reconcile_block)
        self.assertNotIn("$(MAKE) auto-improve-readiness-report-body", reconcile_block)
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-reconcile",
            (
                "$(MAKE) goal-runtime-clean-transient",
                "$(MAKE) goal-runtime-local-evidence-converge",
                "$(MAKE) goal-runtime-publish-local-evidence",
                "$(MAKE) goal-runtime-fixed-point-check",
                "$(MAKE) generated-artifact-converge",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-closeout-plan",
            (
                "ops.scripts.goal_runtime_closeout",
                "--out \"$(GOAL_RUNTIME_CLOSEOUT_PLAN_OUT)\"",
                "--budget \"$(GOAL_RUNTIME_CLOSEOUT_BUDGET)\"",
                "--candidate-root \"$(GOAL_RUNTIME_CLOSEOUT_STATE_DIR)\"",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-closeout-candidate-script-output-surfaces",
            (
                "ops.scripts.script_output_surfaces",
                "--out \"$(GOAL_RUNTIME_CLOSEOUT_SCRIPT_OUTPUT_SURFACES_OUT)\"",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-closeout-candidate-generated-artifact-index",
            (
                "ops.scripts.generated_artifact_index",
                "--out \"$(GOAL_RUNTIME_CLOSEOUT_GENERATED_ARTIFACT_INDEX_OUT)\"",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-closeout-candidate-artifact-freshness",
            (
                "ops.scripts.artifact_freshness_runtime",
                "--out \"$(GOAL_RUNTIME_CLOSEOUT_ARTIFACT_FRESHNESS_OUT)\"",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-closeout-candidate-converge",
            (
                "$(MAKE) report-schema-samples-check",
                "$(MAKE) goal-runtime-clean-transient",
                "$(MAKE) goal-runtime-local-evidence-converge",
                "$(MAKE) goal-runtime-closeout-candidate-script-output-surfaces",
                "$(MAKE) goal-runtime-closeout-candidate-generated-artifact-index",
                "$(MAKE) goal-runtime-closeout-candidate-artifact-freshness",
            ),
        )
        candidate_block = _target_block(text, "goal-runtime-closeout-candidate-converge")
        self.assertNotIn("$(MAKE) script-output-surfaces", candidate_block)
        self.assertNotIn("$(MAKE) generated-artifact-index", candidate_block)
        self.assertNotIn("$(MAKE) artifact-freshness", candidate_block)
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-closeout-publish-script-output-surfaces",
            (
                "ops.scripts.canonical_artifact_promote",
                "--candidate \"$(GOAL_RUNTIME_CLOSEOUT_SCRIPT_OUTPUT_SURFACES_OUT)\"",
                "--out \"$(SCRIPT_OUTPUT_SURFACES_OUT)\"",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-closeout-publish",
            (
                "$(MAKE) goal-runtime-closeout-publish-script-output-surfaces",
                "$(MAKE) goal-runtime-publish-local-evidence",
                "$(MAKE) goal-runtime-certificate",
                "$(MAKE) generated-artifact-converge",
            ),
        )
        self.assertEqual(
            _recipe_lines(text, "goal-runtime-closeout-publish"),
            [
                "$(MAKE) goal-runtime-closeout-publish-script-output-surfaces",
                "$(MAKE) goal-runtime-publish-local-evidence",
                "$(MAKE) goal-runtime-certificate",
                "$(MAKE) generated-artifact-converge",
            ],
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-closeout-finalize",
            (
                "$(MAKE) goal-runtime-fixed-point-check",
            ),
        )
        self.assertNotIn(
            "$(MAKE) generated-artifact-index",
            _target_block(text, "goal-runtime-closeout-finalize"),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-closeout",
            (
                "@set -e; \\",
                "--budget cheap --candidate-root \"$(GOAL_RUNTIME_CLOSEOUT_STATE_DIR)\" --format targets",
                "$(MAKE) $$target",
                "GOAL_RUNTIME_CLOSEOUT_BUDGET=cheap",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-closeout-full",
            (
                "@set -e; \\",
                "--budget full --candidate-root \"$(GOAL_RUNTIME_CLOSEOUT_STATE_DIR)\" --format targets",
                "$(MAKE) $$target",
                "GOAL_RUNTIME_CLOSEOUT_BUDGET=full",
            ),
        )
        self.assertNotIn(
            "test-execution-summary-full-refresh",
            _target_block(text, "goal-runtime-closeout"),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-local-evidence-refresh",
            (
                "ops.scripts.goal_runtime_local_evidence_refresh",
                "--out \"$(GOAL_RUNTIME_LOCAL_EVIDENCE_REFRESH_OUT)\"",
                "--max-iterations \"$(GOAL_RUNTIME_LOCAL_EVIDENCE_REFRESH_MAX_ITERATIONS)\"",
                "--timeout-seconds \"$(GOAL_RUNTIME_LOCAL_EVIDENCE_REFRESH_TIMEOUT_SECONDS)\"",
                "--codex-goal-contract \"$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)\"",
                "--goal-run-status \"$(GOAL_ACTIVE_RUN_STATUS_OUT)\"",
                "--auto-improve-readiness \"$(GOAL_LOCAL_READINESS_OUT)\"",
                "--session-synopsis \"$(GOAL_LOCAL_SESSION_SYNOPSIS_OUT)\"",
                "--negative-lessons \"$(GOAL_LOCAL_NEGATIVE_LESSONS_OUT)\"",
                "--remediation-backlog \"$(GOAL_LOCAL_REMEDIATION_BACKLOG_OUT)\"",
            ),
        )
        local_refresh_block = _target_block(text, "goal-runtime-local-evidence-refresh")
        self.assertNotIn("$(MAKE) goal-runtime-refresh", local_refresh_block)
        self.assertNotIn("$(MAKE) goal-runtime-local-readiness", local_refresh_block)
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-local-evidence-converge",
            (
                "$(MAKE) goal-runtime-local-evidence-refresh",
                "$(MAKE) goal-runtime-local-fixed-point-check",
            ),
        )
        self.assertEqual(
            _target_block(text, "goal-runtime-publish-local-evidence").count(
                "ops.scripts.canonical_artifact_promote"
            ),
            6,
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "auto-improve-goal-run",
            (
                "ops.scripts.goal_runtime_runner",
                "--goal-contract \"$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)\"",
                "--run-id \"$(GOAL_RUN_ID)\"",
                "--runtime-mode \"$(GOAL_RUNTIME_MODE)\"",
                "--status-report-path \"$(GOAL_ACTIVE_RUN_STATUS_OUT)\"",
                "--result-out \"$(GOAL_SESSION_RESULT_OUT)\"",
                "--heartbeat-interval-seconds \"$(GOAL_HEARTBEAT_INTERVAL_SECONDS)\"",
                "--checkpoint-interval-seconds \"$(GOAL_CHECKPOINT_INTERVAL_SECONDS)\"",
                "--timeout-seconds \"$(GOAL_RUNNER_TIMEOUT_SECONDS)\"",
                "--workspace-lock-path \"$(GOAL_RUNTIME_LOCK_PATH)\"",
                "-- $(GOAL_RUN_COMMAND)",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "auto-improve-goal-resume",
            (
                "ops.scripts.goal_runtime_runner",
                "--resume-from-checkpoint",
                "--result-out \"$(GOAL_SESSION_RESULT_OUT)\"",
                "--heartbeat-interval-seconds \"$(GOAL_HEARTBEAT_INTERVAL_SECONDS)\"",
                "--checkpoint-interval-seconds \"$(GOAL_CHECKPOINT_INTERVAL_SECONDS)\"",
                "--timeout-seconds \"$(GOAL_RUNNER_TIMEOUT_SECONDS)\"",
                "--workspace-lock-path \"$(GOAL_RUNTIME_LOCK_PATH)\"",
                "-- $(GOAL_RESUME_COMMAND)",
            ),
        )
        self.assertNotIn("$(MAKE)", _target_block(text, "auto-improve-goal-run"))
        self.assertNotIn("$(MAKE)", _target_block(text, "auto-improve-goal-resume"))
        _assert_recipe_contains_tokens(
            self,
            text,
            "auto-improve-goal-maintenance-action",
            (
                "GOAL_MAINTENANCE_ACTION_PLAN_OUT",
                "$(MAKE) auto-improve-goal-resume",
                "GOAL_MAX_PROPOSALS=\"$$next_max_proposals\"",
                "GOAL_RUNTIME_RUN_ADMISSION_MAINTENANCE_ACTION_PLAN=\"$(GOAL_MAINTENANCE_ACTION_PLAN_OUT)\"",
            ),
        )
        self.assertNotIn("> \"$(GOAL_SESSION_RESULT_OUT)\"", _target_block(text, "auto-improve-goal-run"))
        self.assertNotIn("> \"$(GOAL_SESSION_RESULT_OUT)\"", _target_block(text, "auto-improve-goal-resume"))
        _assert_recipe_contains_tokens(
            self,
            text,
            "auto-improve-goal-finalize",
            (
                "--status \"$(GOAL_FINAL_STATUS)\"",
                "--completed-at \"$(GOAL_COMPLETED_AT)\"",
                "--write-run-artifacts",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-certificate",
            (
                "ops.scripts.goal_runtime_certificate_report",
                "--goal-contract \"$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)\"",
                "--status-report \"$(GOAL_ACTIVE_RUN_STATUS_OUT)\"",
                "--out \"$(GOAL_RUNTIME_CERTIFICATE_CANDIDATE_OUT)\"",
                "$(if $(GOAL_RUNTIME_CERTIFICATE_MODE),--runtime-mode \"$(GOAL_RUNTIME_CERTIFICATE_MODE)\",)",
                "$(if $(GOAL_RUNTIME_CERTIFICATE_APPLY),--apply,)",
                "ops/schemas/goal-runtime-certificate.schema.json",
                "--expected-artifact-kind goal_runtime_certificate",
            ),
        )

    def test_mechanism_run_linux_tmp_target_pins_native_temp_environment(self) -> None:
        text = _makefile_text()
        block = _target_block(text, "run-mechanism-experiment-linux-tmp")

        self.assertIn("MECHANISM_RUN_ARGS ?=", text)
        self.assertIn("run-mechanism-experiment-linux-tmp", _target_block(text, ".PHONY"))
        self.assertIn(
            'TMPDIR=/tmp TEMP=/tmp TMP=/tmp $(PYTHON) -m ops.scripts.run_mechanism_experiment --vault "$(VAULT)" $(MECHANISM_RUN_ARGS)',
            block,
        )

    def test_ruff_strict_preview_target_uses_full_scope_targets(self) -> None:
        text = _makefile_text()

        self.assertIn("RUFF_STRICT_PREVIEW_RULES ?= B,SIM,UP,I", text)
        self.assertIn("RUFF_STRICT_PREVIEW_TARGETS ?= $(STRICT_PREVIEW_AUDIT_TARGETS)", text)
        self.assertIn(
            '$(PYTHON) tools/ruff_strict_preview.py --vault "$(VAULT)" --targets "$(RUFF_STRICT_PREVIEW_TARGETS)" --select "$(RUFF_STRICT_PREVIEW_RULES)"',
            _target_block(text, "ruff-strict-preview"),
        )

    def test_strict_preview_audit_target_expands_all_public_runtime_targets(self) -> None:
        text = _makefile_text()

        self.assertIn("STRICT_PREVIEW_AUDIT_TARGETS ?= ops/scripts tests tools", text)
        self.assertIn("STRICT_PREVIEW_AUDIT_OUT ?= tmp/strict-preview-audit.json", text)
        block = _target_block(text, "strict-preview-audit")
        self.assertIn("tools/strict_preview_audit.py", block)
        self.assertIn('--targets "$(STRICT_PREVIEW_AUDIT_TARGETS)"', block)
        self.assertIn('--ruff-select "$(RUFF_STRICT_PREVIEW_RULES)"', block)
        self.assertIn('--mypy-flags "$(MYPY_STRICT_PREVIEW_FLAGS)"', block)
        self.assertNotIn("--fail-on-attention", block)

    def test_mypy_strict_preview_target_uses_full_scope_targets(self) -> None:
        text = _makefile_text()

        self.assertIn(
            "MYPY_STRICT_PREVIEW_FLAGS ?= --check-untyped-defs --disallow-untyped-defs --disallow-incomplete-defs",
            text,
        )
        self.assertIn(
            "MYPY_STRICT_PREVIEW_TARGETS ?= $(STRICT_PREVIEW_AUDIT_TARGETS)",
            text,
        )
        self.assertIn(
            "$(PYTHON) -m mypy --config-file pyproject.toml $(MYPY_STRICT_PREVIEW_FLAGS) $(MYPY_STRICT_PREVIEW_TARGETS)",
            _target_block(text, "mypy-strict-preview"),
        )

    def test_public_check_targets_use_canonical_summary_artifact(self) -> None:
        text = _makefile_text()

        summary_block = _target_block(text, "public-check-summary")
        summary_check_block = _target_block(text, "public-check-summary-check")
        summary_current_check_block = _target_block(text, "public-check-summary-current-check")
        sync_check_block = _target_block(text, "sync-public-policy-check")
        _assert_assignment_exists(
            self, text, "PUBLIC_CHECK_SUMMARY_REUSE_FROM", "$(PUBLIC_CHECK_SUMMARY_OUT)"
        )
        _assert_assignment_exists(self, text, "PUBLIC_CHECK_HEARTBEAT_INTERVAL_SECONDS", "30")
        _assert_assignment_exists(
            self, text, "PUBLIC_GITIGNORE_TEMPLATE", "ops/templates/public-mirror.gitignore"
        )
        self.assertIn('--public-out "$(PUBLIC_OUT)"', summary_block)
        self.assertIn('--public-python "$(PUBLIC_PYTHON)"', summary_block)
        self.assertIn('--ruff-targets "$(RUFF_TARGETS)"', summary_block)
        self.assertIn('--mypy-targets "$(MYPY_TARGETS)"', summary_block)
        self.assertIn('--pytest-mark-expr "$(PYTEST_PUBLIC_MARK_EXPR)"', summary_block)
        self.assertIn('--pytest-flags "$(PYTEST_FLAGS)"', summary_block)
        self.assertIn('--heartbeat-interval-seconds "$(PUBLIC_CHECK_HEARTBEAT_INTERVAL_SECONDS)"', summary_block)
        self.assertIn("ops.scripts.canonical_artifact_promote", summary_block)
        self.assertIn('--out "$(PUBLIC_CHECK_SUMMARY_CHECK_OUT)"', summary_check_block)
        self.assertNotIn("ops.scripts.canonical_artifact_promote", summary_check_block)
        self.assertIn('--out "$(PUBLIC_CHECK_SUMMARY_CHECK_OUT)"', summary_current_check_block)
        self.assertIn("--reuse-if-current", summary_current_check_block)
        self.assertIn("--reuse-only", summary_current_check_block)
        self.assertIn('--reuse-from "$(PUBLIC_CHECK_SUMMARY_REUSE_FROM)"', summary_current_check_block)
        self.assertNotIn("ops.scripts.canonical_artifact_promote", summary_current_check_block)
        self.assertIn("--check", sync_check_block)
        self.assertIn('--gitignore "$(PUBLIC_GITIGNORE_TEMPLATE)"', sync_check_block)
        public_targets = (
            "public-check",
            "public-check-serial",
            "public-check-parallel",
            "public-check-all",
            "public-check-all-check",
            "public-check-all-serial",
            "public-check-all-parallel",
        )
        for target in public_targets:
            with self.subTest(target=target):
                block = _target_block(text, target)
                if target == "public-check-all-check":
                    self.assertIn("public-check-summary-current-check", block)
                else:
                    self.assertIn("public-check-summary", block)

    def test_codebase_memory_mcp_targets_are_optional_public_export_sidecar(self) -> None:
        text = _makefile_text()
        phony = _target_block(text, ".PHONY")
        for target in (
            "cbm-require-bin",
            "cbm-export-public",
            "cbm-index-public",
            "cbm-list-projects-public",
            "cbm-schema-public",
            "cbm-architecture-public",
            "cbm-reset-local",
        ):
            with self.subTest(target=target):
                self.assertIn(target, phony)

        for assignment in (
            "CBM_BIN ?= codebase-memory-mcp",
            "CBM_CACHE_ROOT ?= $(if $(XDG_CACHE_HOME),$(XDG_CACHE_HOME),$(HOME)/.cache)",
            "CBM_PUBLIC_OUT ?= $(CBM_CACHE_ROOT)/llmwiki/codebase-memory-mcp/public-surface",
            "CBM_CACHE_DIR ?= $(CBM_CACHE_ROOT)/codebase-memory-mcp/llmwiki-public",
            "CBM_IGNORE_TEMPLATE ?= ops/templates/codebase-memory-mcp.cbmignore",
            "CBM_PROJECT_NAME ?= $(subst /,-,$(patsubst /%,%,$(CBM_PUBLIC_OUT)))",
        ):
            self.assertIn(assignment, text)

        export_block = _target_block(text, "cbm-export-public")
        for token in (
            "ops.scripts.cbm_public_export",
            '--vault "$(VAULT)"',
            '--out "$(CBM_PUBLIC_OUT)"',
            '--cbmignore-template "$(CBM_IGNORE_TEMPLATE)"',
        ):
            self.assertIn(token, export_block)

        self.assertEqual(
            _target_block(text, "cbm-index-public").splitlines()[0],
            "cbm-index-public: cbm-require-bin cbm-export-public",
        )
        self.assertIn(
            '\'{"project":"$(CBM_PROJECT_NAME)"}\'',
            _target_block(text, "cbm-schema-public"),
        )
        self.assertIn(
            '\'{"project":"$(CBM_PROJECT_NAME)"}\'',
            _target_block(text, "cbm-architecture-public"),
        )
        for release_gate in ("check", "check-finalized", "release-check", "release-source-ready"):
            with self.subTest(release_gate=release_gate):
                self.assertNotIn("cbm-", _target_block(text, release_gate))

    def test_codebase_memory_mcp_onboarding_is_documented_in_public_entrypoints(self) -> None:
        agents_text = Path("AGENTS.md").read_text(encoding="utf-8")
        readme_text = README.read_text(encoding="utf-8")
        ops_readme_text = Path("ops/README.md").read_text(encoding="utf-8")
        cbm_docs_text = DOCS_CBM.read_text(encoding="utf-8")

        for token in (
            "Optional codebase-memory-mcp sidecar",
            "make cbm-index-public",
            "cbm-schema-public",
            "cbm-architecture-public",
            "make cbm-index-public`로 재색인",
            "`CBM_PUBLIC_OUT` cache 경로",
            "candidate link, not proof",
            "assistant-specific workflow requirement",
        ):
            with self.subTest(surface="AGENTS.md", token=token):
                self.assertIn(token, agents_text)

        for token in (
            "code/ops 구조 탐색",
            "make cbm-index-public",
            "make cbm-schema-public",
            "make cbm-architecture-public",
            "graph-first/file-verified",
            "기존 `rg` / file read workflow",
        ):
            with self.subTest(surface="README.md", token=token):
                self.assertIn(token, readme_text)

        for token in (
            "Optional codebase-memory-mcp quickstart",
            "make cbm-index-public",
            "make cbm-schema-public",
            "make cbm-architecture-public",
            "graph-first/file-verified",
        ):
            with self.subTest(surface="ops/README.md", token=token):
                self.assertIn(token, ops_readme_text)

        for token in (
            "CBM_BIN=/path/to/codebase-memory-mcp",
            "not a dependency",
            "assistant-specific",
            "CBM-EXPORT-MANIFEST.json",
            "ops/reports/",
            "Re-run `make cbm-index-public` after repo edits",
            "cache export paths",
            "Map them back to the same relative path in the repo",
            "candidate links, not proof",
        ):
            with self.subTest(surface="docs/codebase-memory-mcp.md", token=token):
                self.assertIn(token, cbm_docs_text)

    def test_raw_intake_and_review_classification_targets_exist(self) -> None:
        text = _makefile_text()

        self.assertIn(
            "RAW_INTAKE_ABSORPTION_MATRIX ?= runs/run-20260422-raw-intake-registration-and-promotion/absorption/raw-intake-absorption-matrix-2026-04-22.json",
            text,
        )
        self.assertIn(
            "RAW_INTAKE_ROUTE_PROPOSAL_OUT ?= tmp/raw-intake-route-proposal-report.json",
            text,
        )
        self.assertIn(
            "RAW_INTAKE_SOURCE_QUALITY_OUT ?= tmp/raw-intake-source-quality-report.json",
            text,
        )
        self.assertIn(
            "RAW_INTAKE_ABSORPTION_CLOSEOUT_OUT ?= tmp/raw-intake-absorption-closeout-report.json",
            text,
        )
        self.assertIn(
            "WIKI_LINT_REVIEW_CLASSIFICATION_OUT ?= tmp/wiki-lint-review-classification.json",
            text,
        )
        self.assertIn("raw-intake-route-proposal", _target_block(text, ".PHONY"))
        self.assertIn("raw-intake-source-quality", _target_block(text, ".PHONY"))
        self.assertIn("raw-intake-absorption-closeout", _target_block(text, ".PHONY"))
        self.assertIn(
            "wiki-lint-review-classification", _target_block(text, ".PHONY")
        )
        self.assertIn(
            "ops.scripts.raw_intake_route_proposal",
            _target_block(text, "raw-intake-route-proposal"),
        )
        self.assertIn(
            "ops.scripts.raw_intake_source_quality",
            _target_block(text, "raw-intake-source-quality"),
        )
        self.assertIn(
            "--mode absorption_closeout --fail-on-fail",
            _target_block(text, "raw-intake-absorption-closeout"),
        )
        self.assertIn(
            "ops.scripts.wiki_lint_review_classification",
            _target_block(text, "wiki-lint-review-classification"),
        )

    def test_supply_chain_check_targets_exist(self) -> None:
        text = _makefile_text()

        _assert_supply_chain_make_variables(self, text)
        _assert_supply_chain_target_names(self, text)
        _assert_sbom_supply_chain_recipes(self, text)
        _assert_artifact_index_and_freshness_recipes(self, text)
        _assert_archive_and_complexity_recipes(self, text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
