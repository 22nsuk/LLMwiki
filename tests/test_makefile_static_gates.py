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
    pack_ci_entrypoint,
    pack_ci_steps,
    pack_deselection_policy,
    pack_deselects,
    pack_selectors,
    pack_summary_suite,
    pack_by_id,
    selection_by_make_target,
)

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


MAKEFILE = Path("Makefile")
README = Path("README.md")
CONFTEST = Path("tests/conftest.py")
MYPY_ALLOWLIST = Path("ops/mypy-allowlist.txt")
MYPY_STRICT_PREVIEW_ALLOWLIST = Path("ops/mypy-strict-preview-allowlist.txt")
PYTEST_INI = Path("pytest.ini")
RUFF_STRICT_PREVIEW_ALLOWLIST = Path("ops/ruff-strict-preview-allowlist.txt")
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


def _allowlist_lines(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


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


def _release_evidence_closeout_expanded_recipe_lines(text: str) -> list[str]:
    return [
        *_recipe_lines(text, "release-evidence-closeout-phase-1"),
        *_recipe_lines(text, "release-evidence-closeout-phase-2"),
        *_recipe_lines(text, "release-evidence-closeout-phase-3"),
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
        "RELEASE_CLOSEOUT_FIXED_POINT_MAX_ITERATIONS ?= 5",
        "RELEASE_CLOSEOUT_FINALITY_ATTESTATION_OUT ?= ops/reports/release-closeout-finality-attestation.json",
        "RELEASE_CLOSEOUT_FINALITY_ATTESTATION_CANDIDATE_OUT ?= tmp/release-closeout-finality-attestation.candidate.json",
        "RELEASE_DISTRIBUTION_ZIP_OUT ?= build/release/LLMwiki-source.zip",
        "RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT ?= tmp/release-distribution-zip-smoke.json",
        "RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP ?=",
        "RELEASE_CLOSEOUT_SEALED_ZIP_METADATA ?=",
        "RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_CANONICAL_OUT ?= ops/reports/release-closeout-sealed-rehearsal-check.json",
        "RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_RELEASE_OUT ?= build/release/release-closeout-sealed-rehearsal-check.json",
        "RELEASE_AUDIT_PACK_OUT ?= tmp/release-audit-pack.zip",
        "RELEASE_AUDIT_PACK_INCLUDE_OPTIONAL_PAYLOADS ?=",
        "RELEASE_POST_SEAL_ATTESTATION_OUT ?= build/release/release-post-seal-attestation.json",
        "RELEASE_POST_SEAL_ATTESTATION_SOURCE_ZIP ?= $(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)",
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
            "$(MAKE) external-report-action-matrix",
            "$(MAKE) generated-artifact-index",
            "$(MAKE) artifact-freshness",
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
        "release-evidence-closeout-sealed-check",
        "release-evidence-closeout-sealed-dry-run",
        "release-evidence-closeout-sealed-dry-run-check",
        "release-authority-sealed-preflight",
        "release-post-seal-attestation",
    ):
        case.assertIn(target, phony)
    case.assertIn(
        "RELEASE_CLOSEOUT_SEALED_DRY_RUN_ROOT ?= tmp/release-closeout-sealed-dry-run",
        text,
    )
    case.assertIn("RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_FLAGS ?= --no-fail", text)
    case.assertIn(
        '$(PYTHON) -m ops.scripts.release_smoke --vault "$(VAULT)" --profile fast --archive-out "$(RELEASE_DISTRIBUTION_ZIP_OUT)" --out "$(RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT)"',
        _target_block(text, "release-distribution-zip"),
    )
    sealed_block = _target_block(text, "release-evidence-closeout-sealed")
    for needle in (
        '$(MAKE) release-distribution-zip RELEASE_DISTRIBUTION_ZIP_OUT="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
        '$(MAKE) external-report-reference-manifest-strict EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
        '$(MAKE) release-evidence-closeout RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA="$(RELEASE_CLOSEOUT_SEALED_ZIP_METADATA)" EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
        "$(MAKE) operator-release-summary",
        '$(MAKE) release-post-seal-attestation RELEASE_POST_SEAL_ATTESTATION_SOURCE_ZIP="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
        '$(MAKE) release-evidence-closeout-sealed-check RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_OUT="$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_RELEASE_OUT)"',
    ):
        case.assertIn(needle, sealed_block)
    case.assertIn(
        "ops.scripts.release_closeout_sealed_rehearsal_check",
        _target_block(text, "release-evidence-closeout-sealed-check"),
    )
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
        '$(PYTHON) -m ops.scripts.release_post_seal_attestation build --vault "$(VAULT)" --out "$(RELEASE_POST_SEAL_ATTESTATION_OUT)" $(if $(RELEASE_POST_SEAL_ATTESTATION_SOURCE_ZIP),--source-zip-path "$(RELEASE_POST_SEAL_ATTESTATION_SOURCE_ZIP)",)',
        _target_block(text, "release-post-seal-attestation"),
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
        "STRUCTURAL_COMPLEXITY_BUDGET_OUT ?= ops/reports/structural-complexity-budget.json",
        "GENERATED_ARTIFACT_INDEX_OUT ?= ops/reports/generated-artifact-index.json",
        "GENERATED_ARTIFACT_INDEX_CANDIDATE_OUT ?= tmp/generated-artifact-index.candidate.json",
        "ARTIFACT_FRESHNESS_OUT ?= ops/reports/artifact-freshness-report.json",
        "ARTIFACT_FRESHNESS_CANDIDATE_OUT ?= tmp/artifact-freshness-report.candidate.json",
        "ARTIFACT_FRESHNESS_CHECK_OUT ?= tmp/artifact-freshness-report-check.json",
        "ARTIFACT_FRESHNESS_MTIME_SOURCE ?= embedded_currentness",
        "ARTIFACT_FRESHNESS_ZIP_METADATA ?=",
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
        "REVIEW_ARCHIVE_OUT ?= tmp/llm-wiki-vnext-review.zip",
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
        "artifact-relocation-audit:",
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
        "supply-chain-check: supply-chain-provenance",
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
        '$(PYTHON) -m ops.scripts.artifact_freshness_runtime --vault "$(VAULT)" --out "$(ARTIFACT_FRESHNESS_CHECK_OUT)" --mtime-source "$(ARTIFACT_FRESHNESS_MTIME_SOURCE)" $(if $(ARTIFACT_FRESHNESS_ZIP_METADATA),--zip-metadata "$(ARTIFACT_FRESHNESS_ZIP_METADATA)",) --fail-on-fail',
        freshness_check,
    )
    case.assertNotIn("ops.scripts.canonical_artifact_promote", freshness_check)
    freshness = _target_block(text, "artifact-freshness")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.artifact_freshness_runtime --vault "$(VAULT)" --out "$(ARTIFACT_FRESHNESS_CANDIDATE_OUT)" --mtime-source "$(ARTIFACT_FRESHNESS_MTIME_SOURCE)" $(if $(ARTIFACT_FRESHNESS_ZIP_METADATA),--zip-metadata "$(ARTIFACT_FRESHNESS_ZIP_METADATA)",)',
        freshness,
    )
    case.assertIn("ops.scripts.canonical_artifact_promote", freshness)
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
        "refresh-generated-core: registry-preflight raw-registry-export manifest script-output-surfaces routing-provenance-aggregate outcome-metrics mechanism-review mutation-proposal",
        text,
    )
    case.assertIn(
        "refresh-generated-observability: artifact-relocation-audit release-risk-taxonomy-matrix generated-artifact-index artifact-freshness make-target-inventory workflow-dependency-planner release-workflow-order-guard function-budget-refactor-proposals outcome-provenance-gate-policy external-report-action-matrix",
        text,
    )
    case.assertIn("refresh-generated: refresh-generated-core refresh-generated-observability", text)
    for phony_target in (
        "refresh-generated-core",
        "refresh-generated-observability",
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
        "CLEAN_FIXTURE_REGENERATION_ALLOW_DIRTY_REPORTS ?=",
        "MAKE_TARGET_INVENTORY_OUT ?= tmp/make-target-inventory.json",
        "WORKFLOW_DEPENDENCY_PLANNER_OUT ?= tmp/workflow-dependency-planner.json",
        "WORKFLOW_DEPENDENCY_PLANNER_CANDIDATE_OUT ?= tmp/workflow-dependency-planner.candidate.json",
        "WORKFLOW_DEPENDENCY_PLANNER_CHECK_OUT ?= tmp/workflow-dependency-planner-check.json",
        "RELEASE_WORKFLOW_ORDER_GUARD_OUT ?= tmp/release-workflow-order-guard.json",
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
    case.assertNotIn("$(MAKE) workflow-dependency-planner", _target_block(text, "release-evidence-closeout"))
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
    case.assertNotIn("$(MAKE) release-workflow-order-guard", _target_block(text, "release-evidence-closeout"))
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

    def test_check_targets_include_static_gate(self) -> None:
        text = _makefile_text()

        for target in ("check", "check-serial", "check-all", "check-all-serial"):
            with self.subTest(target=target):
                target_line = _target_block(text, target).splitlines()[0]
                self.assertRegex(target_line, rf"^{target}: static(?:\s|$)")

    def test_strict_targets_include_warning_budget_gate(self) -> None:
        text = _makefile_text()

        self.assertIn(
            "check-strict: check warning-budget complexity-budget-touched-check", text
        )
        self.assertIn("check-conditional: check", text)
        self.assertIn(
            "check-clean: check-clean-lane-guard check-conditional warning-budget test-artifact-finalization release-evidence-cohort-check",
            text,
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target check-clean',
            _target_block(text, "check-clean-lane-guard"),
        )
        self.assertIn(
            "test-artifact-finalization: test-artifact-finalization-lane-guard",
            text,
        )
        self.assertIn(
            "test-artifact-finalization-lane-guard", _target_block(text, ".PHONY")
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target test-artifact-finalization',
            _target_block(text, "test-artifact-finalization-lane-guard"),
        )
        self.assertIn("release-evidence-closeout-lane-guard", _target_block(text, ".PHONY"))
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-evidence-closeout',
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
            "release-clean: release-check warning-budget release-evidence-closeout release-evidence-cohort-check",
            text,
        )
        self.assertIn(
            "release-provenance-clean: release-clean supply-chain-check", text
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.warning_budget --vault "$(VAULT)"',
            _target_block(text, "warning-budget"),
        )

    def test_static_gate_runs_ruff_and_mypy_allowlist(self) -> None:
        text = _makefile_text()

        self.assertIn("RUFF_TARGETS ?= ops/scripts tests tools", text)
        self.assertIn("MYPY_TARGETS ?= @ops/mypy-allowlist.txt", text)
        self.assertIn("static: ruff typecheck", text)
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
            "test-report-contract": "PYTEST_REPORT_CONTRACT_MARK_EXPR",
            "test-artifact-finalization": "PYTEST_ARTIFACT_FINALIZATION_MARK_EXPR",
            "test-release-sealing": "PYTEST_RELEASE_SEALING_MARK_EXPR",
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
        self.assertNotIn('"finalization: checked-in generated artifact self-checks', pyproject_text)

    def test_readme_and_pytest_ini_pin_supported_pytest_entrypoints(self) -> None:
        registry = _test_lane_registry()
        readme_text = README.read_text(encoding="utf-8")
        conftest_text = CONFTEST.read_text(encoding="utf-8")
        pytest_ini_text = PYTEST_INI.read_text(encoding="utf-8")

        self.assertIn(
            "공식 pytest 진입점은 `make test*`, `make check*`, `make public-check*` 또는 `.venv/bin/python -m pytest`다.",
            readme_text,
        )
        self.assertIn(
            "문서, CI, 재현 절차 예시도 bare `pytest`가 아니라 `python -m pytest`",
            readme_text,
        )
        self.assertIn("plain `pytest` is not a supported entrypoint", conftest_text)
        self.assertIn("BARE_PYTEST_GUIDANCE", conftest_text)
        self.assertNotRegex(pytest_ini_text, r"(?im)^pythonpath\s*=")
        for entrypoint in compatibility_names(registry, "documented_entrypoint"):
            with self.subTest(entrypoint=entrypoint):
                self.assertIn(entrypoint, readme_text)

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
        readme_text = README.read_text(encoding="utf-8")
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
            "tests/test_generated_report_contracts.py",
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
            readme_text,
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
            "test-artifact-finalization",
            "test-release-sealing",
            "test-subprocess",
            "test-source-package",
            "release-source-package-check",
            "release-builder-full",
        ):
            with self.subTest(target=target):
                self.assertIn(target, _target_block(text, ".PHONY"))

        self.assertIn(
            "PYTEST_REPORT_CONTRACT_MARK_EXPR ?= report_contract and not artifact_finalization",
            text,
        )
        self.assertIn(
            "PYTEST_ARTIFACT_FINALIZATION_MARK_EXPR ?= artifact_finalization", text
        )
        self.assertIn("PYTEST_RELEASE_SEALING_MARK_EXPR ?= release_sealing", text)
        self.assertIn("PYTEST_SUBPROCESS_MARK_EXPR ?= subprocess", text)
        self.assertIn("not report_contract and not artifact_finalization", text)
        self.assertIn("RELEASE_SEALING_TESTS ?=", text)
        self.assertIn("SUBPROCESS_TESTS ?=", text)
        self.assertIn(
            '$(PYTHON) -m pytest -m "$(PYTEST_FAST_MARK_EXPR)" $(PYTEST_FLAGS)',
            _target_block(text, "test-fast"),
        )
        self.assertIn("test: test-fast", text)
        self.assertIn("unit-tests: test-fast", text)
        self.assertIn("report-contract-finalization: test-artifact-finalization", text)
        self.assertIn(
            "release-builder-full: release-builder-full-lane-guard bootstrap-preflight static release-evidence-closeout",
            text,
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(RELEASE_SEALING_TESTS) $(PYTEST_SERIAL_FLAGS)",
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

    def test_source_package_targets_pin_clean_extract_test_lane(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()

        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_TEST_SUMMARY_OUT",
            "tmp/test-source-package-summary.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_TEST_DESELECT_POLICY",
            pack_deselection_policy(registry, "source_package"),
        )
        _assert_assignment_exists(
            self, text, "SOURCE_PACKAGE_CHECK_ROOT", "tmp/source-package-check"
        )
        _assert_assignment_not_exists(self, text, "SOURCE_PACKAGE_ARCHIVE_ROOT_NAME")
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_EXTRACT_PARENT",
            "$(SOURCE_PACKAGE_CHECK_ROOT)/extract",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_TEST_MARK_EXPR",
            "not artifact_finalization and not release_sealing",
        )
        _assert_assignment_exists(self, text, "SOURCE_PACKAGE_PYTHON", "$(PUBLIC_PYTHON)")
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_CLEAN_EXTRACT_OUT",
            "ops/reports/source-package-clean-extract.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_CLEAN_EXTRACT_CANDIDATE_OUT",
            "tmp/source-package-clean-extract.candidate.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_HEARTBEAT_INTERVAL_SECONDS",
            "30",
        )
        self.assertEqual(
            _makefile_assignment_items(text, "SOURCE_PACKAGE_TEST_DESELECTS"),
            pack_deselects(registry, "source_package"),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-source-package",
            (
                "ops.scripts.test_execution_summary",
                "--collect-nodeids",
                f'--suite {pack_summary_suite(registry, "source_package")["suite_id"]}',
                '--deselection-policy "$(SOURCE_PACKAGE_TEST_DESELECT_POLICY)"',
                '$(PYTHON) -m pytest -m "$(SOURCE_PACKAGE_TEST_MARK_EXPR)"',
                "$(SOURCE_PACKAGE_TEST_DESELECTS)",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "release-source-package-check",
            (
                "release-distribution-zip",
                "ops.scripts.source_package_clean_extract",
                '--source-zip "$(SOURCE_PACKAGE_ZIP_OUT)"',
                '--extract-parent "$(SOURCE_PACKAGE_EXTRACT_PARENT)"',
                '--source-python "$(SOURCE_PACKAGE_PYTHON)"',
                '--zip-smoke-report "$(SOURCE_PACKAGE_ZIP_SMOKE_OUT)"',
                '--heartbeat-interval-seconds "$(SOURCE_PACKAGE_HEARTBEAT_INTERVAL_SECONDS)"',
                '--deselects="$(SOURCE_PACKAGE_TEST_DESELECTS)"',
                '--pytest-flags="$(PYTEST_SERIAL_FLAGS)"',
                "ops.scripts.canonical_artifact_promote",
                "--schema ops/schemas/source-package-clean-extract.schema.json",
            ),
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
        readme_text = README.read_text(encoding="utf-8")

        self.assertIn(
            "`.github/workflows/ci.yml`은 test tier를 `fast`, `report-contract`, `release-closeout-regression`, `artifact-finalization`, `release-sealing`, `subprocess`, `slow`, `integration`, `integration-heavy`, `public`으로 나눠 병렬 job으로 실행하고, 별도 Windows/raw-registry/supply-chain job도 유지한다.",
            readme_text,
        )
        for entrypoint in compatibility_names(registry, "documented_entrypoint"):
            with self.subTest(entrypoint=entrypoint):
                self.assertIn(entrypoint, readme_text)

    def test_registry_documents_authority_boundary_for_lane_contract(self) -> None:
        registry = _test_lane_registry()

        self.assertEqual(
            documentation_authority(registry),
            ("README.md", "ops/README.md", ".github/workflows/ci.yml"),
        )
        self.assertEqual(
            documentation_out_of_scope(registry),
            ("ARCHITECTURE.md", ".github/workflows/release.yml"),
        )

    def test_architecture_public_surface_includes_github_workflows(self) -> None:
        architecture_text = Path("ARCHITECTURE.md").read_text(encoding="utf-8")

        self.assertIn("- `.github/`", architecture_text)

    def test_release_smoke_targets_expose_fast_and_full_profiles(self) -> None:
        text = _makefile_text()
        readme_text = README.read_text(encoding="utf-8")

        self.assertIn("release-smoke-fast", _target_block(text, ".PHONY"))
        self.assertIn("release-smoke-full", _target_block(text, ".PHONY"))
        self.assertIn("release-smoke-full-reuse", _target_block(text, ".PHONY"))
        self.assertIn(
            "RELEASE_SMOKE_OUT ?= ops/reports/release-smoke-report.json", text
        )
        self.assertIn(
            "RELEASE_SMOKE_FAST_OUT ?= ops/reports/release-smoke-report-fast.json", text
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
        self.assertIn(
            '$(PYTHON) -m ops.scripts.release_smoke --vault "$(VAULT)" --profile fast --out "$(RELEASE_SMOKE_FAST_OUT)"',
            _target_block(text, "release-smoke-fast"),
        )
        self.assertIn("release-check: check-all release-smoke", text)
        self.assertIn(
            "developer/package precheck이며 canonical release evidence로 쓰지 않는다",
            readme_text,
        )
        self.assertIn(
            "canonical release evidence는 이 full 단일 report인 `ops/reports/release-smoke-report.json`이다",
            readme_text,
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
            "LEARNING_READINESS_SIGNOFF_REVALIDATION_COMMAND ?= make release-evidence-closeout PYTHON=.venv/bin/python",
            text,
        )
        self.assertIn(
            "LEARNING_READINESS_SIGNOFF_REVALIDATION_ENVIRONMENT ?= .venv clean release-builder",
            text,
        )
        self.assertIn("LEARNING_READINESS_SIGNOFF_ACCEPTED_BY ?=", text)
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

    def test_report_contracts_target_collects_schema_and_generated_artifact_checks(
        self,
    ) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()
        block = _target_block(text, "report-contracts")
        extended_block = _target_block(text, "report-contracts-extended")
        expected_core_tests = pack_selectors(registry, "report_contract_core")
        expected_extended_tests = pack_selectors(registry, "report_contract_extended")

        self.assertIn("report-contracts", _target_block(text, ".PHONY"))
        self.assertIn("report-contracts-extended", _target_block(text, ".PHONY"))
        self.assertIn("REPORT_CONTRACT_CORE_TESTS ?=", text)
        self.assertIn("REPORT_CONTRACT_EXTENDED_TESTS ?=", text)
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
            block,
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(REPORT_CONTRACT_EXTENDED_TESTS) $(PYTEST_SERIAL_FLAGS)",
            extended_block,
        )

    def test_report_contract_summary_moves_self_referential_artifact_checks_to_artifact_finalization_lane(
        self,
    ) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()
        block = _target_block(text, "test-report-contract")
        finalization_block = _target_block(text, "test-artifact-finalization")
        finalization_selectors = pack_selectors(registry, "artifact_finalization_checks")

        self.assertIn("test-report-contract", _target_block(text, ".PHONY"))
        self.assertIn("test-artifact-finalization", _target_block(text, ".PHONY"))
        self.assertIn("report-contract-summary", _target_block(text, ".PHONY"))
        self.assertIn("report-contract-finalization", _target_block(text, ".PHONY"))
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
        self.assertEqual(
            _makefile_assignment_items(text, "REPORT_CONTRACT_FINALIZATION_TESTS"),
            finalization_selectors,
        )
        self.assertIn(
            "tests/test_writer_output_paths.py::WriterOutputPathsTest::test_script_output_surface_registry_matches_current_ast_inventory",
            finalization_selectors,
        )
        self.assertNotIn("--deselect=tests/test_generated_report_contracts.py::", text)
        self.assertIn(
            "$(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_SERIAL_FLAGS)",
            block,
        )
        self.assertIn("report-contract-summary: test-report-contract", text)
        self.assertIn(
            "$(PYTHON) -m pytest $(REPORT_CONTRACT_FINALIZATION_TESTS) $(PYTEST_SERIAL_FLAGS)",
            finalization_block,
        )
        self.assertIn("report-contract-finalization: test-artifact-finalization", text)

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
        self.assertEqual(block.count("$(MAKE) generated-artifact-index"), 2)
        self.assertEqual(block.count("$(MAKE) archive-execution-manifest-report"), 0)
        self.assertNotIn("$(MAKE) archive-execution-manifest\n", block)
        self.assertEqual(block.count("$(MAKE) artifact-freshness"), 2)
        self.assertEqual(block.count("$(MAKE) release-closeout-summary-report"), 2)
        self.assertIn("$(MAKE) release-evidence-cohort", block)
        self.assertIn("$(MAKE) auto-improve-readiness-report-body", block)
        self.assertIn("$(MAKE) test-artifact-finalization", block)
        self.assertLess(
            block.index("$(MAKE) auto-improve-readiness-report-body"),
            block.index("$(MAKE) test-artifact-finalization"),
        )
        self.assertNotIn("$(PYTHON) -m pytest", block)
        self.assertIn("finalization self-checks", block)
        self.assertLess(
            block.index("$(MAKE) report-contract-closeout-precheck"),
            block.index("$(MAKE) test-execution-summary"),
        )

    def test_report_contract_closeout_precheck_policy_and_runtime_stay_in_sync(self) -> None:
        text = _makefile_text()
        policy = json.loads(REPORT_CONTRACT_CLOSEOUT_POLICY.read_text(encoding="utf-8"))
        expected_targets = [
            "script-output-surfaces",
            "generated-artifact-index",
            "auto-improve-readiness-report",
            "artifact-freshness",
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

    def test_release_evidence_closeout_enforces_strict_recipe_order(self) -> None:
        text = _makefile_text()
        block = _target_block(text, "release-evidence-closeout")
        recipe_lines = _release_evidence_closeout_expanded_recipe_lines(text)

        self.assertIn("release-evidence-closeout", _target_block(text, ".PHONY"))
        self.assertIn("release-evidence-closeout-phase-1", _target_block(text, ".PHONY"))
        self.assertIn("release-evidence-closeout-phase-2", _target_block(text, ".PHONY"))
        self.assertIn("release-evidence-closeout-phase-3", _target_block(text, ".PHONY"))
        self.assertEqual(block.splitlines()[0], "release-evidence-closeout: release-evidence-closeout-phase-3")
        self.assertEqual(
            _target_block(text, "release-evidence-closeout-phase-2").splitlines()[0],
            "release-evidence-closeout-phase-2: release-evidence-closeout-phase-1",
        )
        self.assertEqual(
            _target_block(text, "release-evidence-closeout-phase-3").splitlines()[0],
            "release-evidence-closeout-phase-3: release-evidence-closeout-phase-2",
        )
        self.assertEqual(
            recipe_lines,
            [
                "$(MAKE) release-evidence-closeout-lane-guard",
                "$(MAKE) refresh-generated-core",
                "$(MAKE) bootstrap-preflight",
                "$(MAKE) registry-preflight",
                "$(MAKE) static",
                "$(MAKE) report-schema-samples-check",
                "$(MAKE) external-report-reference-manifest-settle",
                "$(MAKE) release-smoke-full",
                "$(MAKE) release-source-package-check",
                "$(MAKE) generated-artifact-index",
                "$(MAKE) artifact-freshness",
                "$(MAKE) test-execution-summary-report-contract-refresh",
                "$(MAKE) generated-artifact-index",
                "$(MAKE) artifact-freshness",
                "$(MAKE) release-closeout-summary-report",
                "$(MAKE) auto-improve-readiness-report-body",
                "$(MAKE) generated-artifact-index",
                "$(MAKE) artifact-freshness",
                "$(MAKE) release-closeout-summary-report",
                "$(MAKE) auto-improve-readiness-report-body",
                "$(MAKE) tmp-json-clean",
                "$(MAKE) test-execution-summary-full-refresh",
                "$(MAKE) test-execution-summary",
                "$(MAKE) function-budget-refactor-proposals",
                "$(MAKE) outcome-provenance-gate-policy",
                "$(MAKE) auto-improve-readiness-report-body",
                "$(MAKE) external-report-action-matrix",
                "$(MAKE) generated-artifact-index",
                "$(MAKE) artifact-freshness",
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
                "$(MAKE) generated-artifact-index",
                "$(MAKE) artifact-freshness",
                "$(MAKE) test-artifact-finalization",
                "$(MAKE) release-closeout-post-check-finalizer-dry-run",
                "$(MAKE) release-closeout-fixed-point",
                "$(MAKE) tmp-json-clean",
                "$(MAKE) release-closeout-finality-verify",
            ],
        )

    def test_release_evidence_closeout_uses_fixed_point_finalizer(self) -> None:
        text = _makefile_text()
        recipe_lines = _release_evidence_closeout_expanded_recipe_lines(text)

        self.assertTrue(recipe_lines, "release-evidence-closeout has no recipe lines")

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
            recipe_lines[fixed_point_index + 1], "$(MAKE) tmp-json-clean"
        )
        self.assertEqual(
            recipe_lines[fixed_point_index + 2],
            "$(MAKE) release-closeout-finality-verify",
        )
        self.assertNotIn(
            "$(MAKE) release-closeout-batch-manifest-promote", recipe_lines
        )
        self.assertNotIn("$(MAKE) release-evidence-closeout-self-check", recipe_lines)

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
                "$(MAKE) external-report-action-matrix",
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
                "$(MAKE) script-output-surfaces",
                "$(MAKE) generated-artifact-index",
                "$(MAKE) artifact-freshness",
                "$(MAKE) release-closeout-post-check-finalizer-dry-run",
                "$(MAKE) release-closeout-fixed-point",
                "$(MAKE) tmp-json-clean",
                "$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required",
            ],
        )

    def test_release_evidence_closeout_canonical_writers_are_ordered_with_fixed_point_last(
        self,
    ) -> None:
        text = _makefile_text()
        closeout_block = _target_block(text, "release-evidence-closeout")
        self.assertEqual(closeout_block.splitlines()[0], "release-evidence-closeout: release-evidence-closeout-phase-3")
        closeout_lines = _release_evidence_closeout_expanded_recipe_lines(text)

        # Identify canonical writer targets (those using canonical_artifact_promote)
        canonical_writers: set[str] = set()
        for match in re.finditer(
            r"^(?P<target>[a-zA-Z0-9_-]+):(?P<deps>[^\n]*)(?P<body>(?:\n\t[^\n]*)*)",
            text,
            flags=re.MULTILINE,
        ):
            if "ops.scripts.canonical_artifact_promote" in match.group("body"):
                canonical_writers.add(match.group("target"))

        # Find all canonical writer occurrences in the closeout recipe
        occurrences: list[tuple[str, int]] = []
        for i, line in enumerate(closeout_lines):
            for writer in canonical_writers:
                invocation = f"$(MAKE) {writer}"
                if line == invocation or line.startswith(f"{invocation} "):
                    occurrences.append((writer, i))
                    break

        self.assertTrue(
            occurrences, "no canonical writers found in release-evidence-closeout"
        )

        late_operator_refresh_writers = {"auto-improve-readiness-report-body"}
        sealing_occurrences = [
            (writer, index)
            for writer, index in occurrences
            if writer not in late_operator_refresh_writers
        ]
        self.assertTrue(
            sealing_occurrences,
            "no sealing-inventory canonical writers found in release-evidence-closeout",
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
                    (
                        f"sealing-inventory canonical writer {writer} at index {index} "
                        "appears after release-closeout-fixed-point"
                    )
                )
        self.assertLessEqual(
            last_index,
            len(closeout_lines) - 1,
            "batch manifest index out of range",
        )

        # release-closeout-fixed-point must appear exactly once
        fixed_point_count = sum(
            1 for w, _ in occurrences if w == "release-closeout-fixed-point"
        )
        self.assertEqual(
            fixed_point_count,
            1,
            "release-closeout-fixed-point must appear exactly once in release-evidence-closeout",
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
                "$(MAKE) artifact-freshness",
                "$(MAKE) test-execution-summary-reuse",
                "$(MAKE) learning-readiness-signoff-revalidation",
                "$(MAKE) generated-artifact-index",
                "$(MAKE) tmp-json-clean",
                "$(MAKE) artifact-freshness",
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
            "test-execution-summary-report-contract",
            "test-execution-summary-report-contract-refresh",
            "test-execution-summary-full",
            "test-execution-summary-full-refresh",
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
            self, text, "TEST_EXECUTION_SUMMARY_FAST_OUT", "ops/reports/test-execution-summary-fast.json"
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FAST_CANDIDATE_OUT",
            "tmp/test-execution-summary-fast.candidate.json",
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
                "$(MAKE) refresh-generated-core",
                "$(MAKE) auto-improve-readiness-report-body",
                "$(MAKE) release-smoke-full",
            ),
        )
        self.assertEqual(refresh_block.count("$(MAKE) generated-artifact-index"), 2)
        self.assertEqual(refresh_block.count("$(MAKE) archive-execution-manifest-report"), 0)
        self.assertEqual(refresh_block.count("$(MAKE) artifact-freshness"), 2)
        self.assertIn(
            "strict test-execution-summary will rerun later in closeout", refresh_block
        )
        self.assertIn(
            "test-execution-summary: test-execution-summary-report-contract", text
        )
        full_block = _target_block(text, "test-execution-summary-full")
        self.assertNotIn("$(MAKE) refresh-generated-core", full_block)
        self.assertNotIn("$(MAKE) auto-improve-readiness-report-body", full_block)
        self.assertNotIn("$(MAKE) release-smoke-full", full_block)
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-full",
            (
                'rm -rf "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)"',
                'mkdir -p "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)"',
                "$(MAKE) test-execution-summary-report-contract-refresh",
                "ops.scripts.test_execution_summary",
                "--collect-nodeids",
                "--junit-xml-path",
                "--execution-log-out",
                "--failed-nodeids-out",
                "--aggregate",
                "--aggregate-dir",
                "ops.scripts.canonical_artifact_promote",
                "$(MAKE) generated-artifact-index",
                "$(MAKE) artifact-freshness",
            ),
        )
        self.assertEqual(full_block.count("$(MAKE) generated-artifact-index"), 1)
        self.assertLess(
            full_block.index("$(MAKE) test-execution-summary-report-contract-refresh"),
            full_block.index('rm -rf "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)"'),
        )
        self.assertLess(
            full_block.index("$(MAKE) test-execution-summary-report-contract-refresh"),
            full_block.rindex("ops.scripts.test_execution_summary"),
        )
        self.assertGreater(
            full_block.rindex("$(MAKE) artifact-freshness"),
            full_block.index("ops.scripts.canonical_artifact_promote"),
        )
        full_refresh_block = _target_block(text, "test-execution-summary-full-refresh")
        _assert_target_depends_on(self, text, "test-execution-summary-full-refresh", "test-execution-summary-full")
        self.assertIn(
            "full-suite evidence refreshed; collect-only nodeid digest and count recorded in $(TEST_EXECUTION_SUMMARY_FULL_OUT)",
            full_refresh_block,
        )
        self.assertNotIn("node count $$actual does not match expected", full_refresh_block)
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

        self.assertIn("registry-preflight", _target_block(text, ".PHONY"))
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
            '$(PYTHON) -m ops.scripts.raw_registry_preflight --vault "$(VAULT)" --out "$(RAW_REGISTRY_PREFLIGHT_OUT)" --reproducibility-out "$(RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_OUT)"',
            block,
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.raw_registry_cross_environment_matrix --vault "$(VAULT)" --stored-report "$(RAW_REGISTRY_PREFLIGHT_OUT)" --out "$(RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_OUT)" --require-live',
            block,
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

    def test_auto_improve_readiness_target_wraps_core_refresh_generated(self) -> None:
        text = _makefile_text()

        self.assertIn(
            "AUTO_IMPROVE_READINESS_OUT ?= ops/reports/auto-improve-readiness.json",
            text,
        )
        self.assertIn(
            "AUTO_IMPROVE_READINESS_CANDIDATE_OUT ?= tmp/auto-improve-readiness.candidate.json",
            text,
        )
        self.assertIn(
            "auto-improve-readiness: refresh-generated-core auto-improve-readiness-worktree-guard",
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
        self.assertIn("auto-improve-readiness-report: refresh-generated-core", text)
        self.assertIn(
            "auto-improve-readiness-report-body: auto-improve-readiness-worktree-guard",
            text,
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "auto-improve-readiness-worktree-guard",
            (
                "ops.scripts.goal_worktree_guard",
                "--requested-mode \"$(GOAL_WORKTREE_MODE)\"",
                "--out \"$(GOAL_WORKTREE_GUARD_OUT)\"",
                "$(if $(GOAL_WORKTREE_ALLOW_DIRTY),--allow-dirty,)",
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
            ("GOAL_WORKTREE_GUARD_OUT", "tmp/goal-worktree-guard.json"),
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
            ("GOAL_PROFILE_VERIFICATION_OUT", "ops/reports/goal-profile-verification.json"),
            (
                "GOAL_PROFILE_VERIFICATION_CANDIDATE_OUT",
                "tmp/goal-profile-verification.candidate.json",
            ),
            ("GOAL_RUNTIME_CLEAN_TRANSIENT_OUT", "tmp/goal-runtime-clean-transient.json"),
            ("GOAL_RUNTIME_CLEAN_TRANSIENT_APPLY", "1"),
            (
                "GOAL_RUNTIME_CLEAN_TRANSIENT_STATUS_REPORT",
                "$(GOAL_RUN_STATUS_OUT)",
            ),
            (
                "GOAL_RUNTIME_FIXED_POINT_CHECK_OUT",
                "tmp/goal-runtime-fixed-point-check.json",
            ),
            (
                "GOAL_SESSION_RESULT_OUT",
                "$(GOAL_ACTIVE_STATE_DIR)/auto-improve-goal-session-result.json",
            ),
            ("GOAL_RUN_STATUS", "blocked"),
            ("GOAL_RUN_PROFILE", "30m_trial"),
            ("GOAL_MAX_UNATTENDED_SECONDS", "1800"),
            ("GOAL_RUNNER_TIMEOUT_SECONDS", "1860"),
            ("GOAL_MAX_MINUTES", "30"),
            ("GOAL_MAX_PROPOSALS", "1"),
            ("GOAL_MAX_CONSECUTIVE_FAILURES", "1"),
            ("GOAL_MAINTAIN_UNTIL_BUDGET", "1"),
            ("GOAL_MAINTENANCE_INTERVAL_SECONDS", "300"),
            ("GOAL_EXECUTOR", "codex_exec"),
            ("GOAL_ARTIFACT_CLASS", "system_mechanism"),
            ("GOAL_FINAL_STATUS", "stopped"),
            ("GOAL_LADDER_PROFILES", "30m_trial 6h_ramp 2d_candidate 5d_sustained"),
            ("GOAL_RUN_LOG_DIR", "build/goal-runs"),
            ("GOAL_LADDER_CONTRACT_RUN_ID", "$(GOAL_LADDER_RUN_ID)"),
        ):
            _assert_assignment_exists(self, text, variable, expected)
        for variable in (
            "GOAL_WORKTREE_ALLOW_DIRTY",
            "GOAL_WORKTREE_STRICT",
            "GOAL_ALLOW_LEARNING_UNCERTAIN",
            "GOAL_PROFILE_VERIFICATION_PROFILE",
            "GOAL_PROFILE_VERIFICATION_APPLY",
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
        phony = _target_block(text, ".PHONY")
        for target in (
            "codex-goal-contract",
            "codex-goal-prompt",
            "codex-goal-client",
            "auto-improve-readiness-worktree-guard",
            "auto-improve-goal-contract",
            "goal-runtime-refresh",
            "goal-runtime-publish-snapshot",
            "goal-runtime-reconcile",
            "goal-runtime-clean-transient",
            "goal-runtime-fixed-point-check",
            "long-run-preflight-clean",
            "auto-improve-goal-preflight",
            "auto-improve-goal-run",
            "auto-improve-goal-status",
            "auto-improve-goal-resume",
            "auto-improve-goal-finalize",
            "auto-improve-goal-run-artifacts",
            "auto-improve-goal-ladder-run",
            "auto-improve-goal-ladder-start",
            "goal-profile-verification",
            "goal-worktree-guard",
        ):
            self.assertIn(target, phony)
        codex_contract_header = _target_block(text, "codex-goal-contract").splitlines()[0]
        self.assertNotIn("auto-improve-goal-contract", codex_contract_header)
        _assert_target_depends_on(self, text, "codex-goal-prompt", "codex-goal-contract")
        _assert_target_depends_on(self, text, "goal-runtime-refresh", "auto-improve-goal-status")
        _assert_target_depends_on(self, text, "long-run-preflight-clean", "goal-runtime-clean-transient")
        _assert_target_depends_on(self, text, "long-run-preflight-clean", "goal-runtime-fixed-point-check")
        _assert_target_depends_on(self, text, "long-run-preflight-clean", "auto-improve-goal-preflight")
        _assert_target_depends_on(self, text, "auto-improve-goal-run", "auto-improve-goal-preflight")
        _assert_target_depends_on(self, text, "auto-improve-goal-run", "auto-improve-goal-contract")
        _assert_target_depends_on(self, text, "auto-improve-goal-status", "auto-improve-goal-contract")
        _assert_target_depends_on(self, text, "auto-improve-goal-resume", "auto-improve-goal-preflight")
        _assert_target_depends_on(self, text, "auto-improve-goal-resume", "auto-improve-goal-contract")
        _assert_target_depends_on(self, text, "auto-improve-goal-finalize", "auto-improve-goal-contract")
        _assert_target_depends_on(self, text, "auto-improve-goal-run-artifacts", "auto-improve-goal-status")
        _assert_target_depends_on(self, text, "auto-improve-goal-ladder-run", "auto-improve-goal-preflight")
        _assert_target_depends_on(self, text, "auto-improve-goal-ladder-start", "auto-improve-goal-preflight")
        _assert_target_depends_on(self, text, "goal-profile-verification", "auto-improve-goal-contract")
        _assert_target_depends_on(self, text, "goal-worktree-guard", "auto-improve-goal-preflight")
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
                "--current-profile \"$(GOAL_RUN_PROFILE)\"",
                "--max-unattended-seconds \"$(GOAL_MAX_UNATTENDED_SECONDS)\"",
                "--max-proposals \"$(GOAL_MAX_PROPOSALS)\"",
                "--max-consecutive-failures \"$(GOAL_MAX_CONSECUTIVE_FAILURES)\"",
                "--goal-status-path \"$(GOAL_ACTIVE_RUN_STATUS_OUT)\"",
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
            "auto-improve-goal-preflight",
            (
                "ops.scripts.goal_worktree_guard",
                "--requested-mode \"$(GOAL_WORKTREE_MODE)\"",
                "--out \"$(GOAL_WORKTREE_GUARD_OUT)\"",
                "$(if $(GOAL_WORKTREE_ALLOW_DIRTY),--allow-dirty,)",
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
        reconcile_block = _target_block(text, "goal-runtime-reconcile")
        self.assertEqual(reconcile_block.count("$(MAKE) goal-runtime-refresh"), 2)
        self.assertEqual(reconcile_block.count("$(MAKE) goal-runtime-publish-snapshot"), 2)
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-reconcile",
            (
                "$(MAKE) goal-runtime-clean-transient",
                "$(MAKE) session-synopsis",
                "$(MAKE) remediation-backlog",
                "$(MAKE) auto-improve-readiness-report-body",
                "$(MAKE) goal-runtime-fixed-point-check",
                "$(MAKE) external-report-action-matrix",
                "$(MAKE) generated-artifact-index",
                "$(MAKE) artifact-freshness",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "auto-improve-goal-run",
            (
                "ops.scripts.goal_runtime_runner",
                "--goal-contract \"$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)\"",
                "--run-id \"$(GOAL_RUN_ID)\"",
                "--status-report-path \"$(GOAL_ACTIVE_RUN_STATUS_OUT)\"",
                "--result-out \"$(GOAL_SESSION_RESULT_OUT)\"",
                "--heartbeat-interval-seconds \"$(GOAL_HEARTBEAT_INTERVAL_SECONDS)\"",
                "--checkpoint-interval-seconds \"$(GOAL_CHECKPOINT_INTERVAL_SECONDS)\"",
                "--timeout-seconds \"$(GOAL_RUNNER_TIMEOUT_SECONDS)\"",
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
                "-- $(GOAL_RESUME_COMMAND)",
            ),
        )
        self.assertNotIn("$(MAKE)", _target_block(text, "auto-improve-goal-run"))
        self.assertNotIn("$(MAKE)", _target_block(text, "auto-improve-goal-resume"))
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
            "goal-profile-verification",
            (
                "ops.scripts.goal_profile_verification",
                "--goal-contract \"$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)\"",
                "--status-report \"$(GOAL_ACTIVE_RUN_STATUS_OUT)\"",
                "--out \"$(GOAL_PROFILE_VERIFICATION_CANDIDATE_OUT)\"",
                "$(if $(GOAL_PROFILE_VERIFICATION_PROFILE),--profile \"$(GOAL_PROFILE_VERIFICATION_PROFILE)\",)",
                "$(if $(GOAL_PROFILE_VERIFICATION_APPLY),--apply,)",
                "ops/schemas/goal-profile-verification.schema.json",
                "--expected-artifact-kind goal_profile_verification",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "auto-improve-goal-ladder-run",
            (
                "30m_trial) profile_seconds=1800; profile_minutes=30; runner_timeout=1860; profile_proposals=1; profile_failures=1",
                "6h_ramp) profile_seconds=21600; profile_minutes=360; runner_timeout=21660; profile_proposals=6; profile_failures=2",
                "2d_candidate) profile_seconds=172800; profile_minutes=2880; runner_timeout=172860; profile_proposals=24; profile_failures=3",
                "5d_sustained) profile_seconds=432000; profile_minutes=7200; runner_timeout=432060; profile_proposals=60; profile_failures=3",
                "GOAL_CONTRACT_RUN_ID=\"$(GOAL_CONTRACT_RUN_ID)\"",
                "GOAL_RUN_ID=\"$(GOAL_RUN_ID)-$$profile\"",
                "GOAL_RUN_PROFILE=\"$$profile\"",
                "GOAL_MAX_PROPOSALS=\"$$profile_proposals\"",
                "GOAL_MAX_CONSECUTIVE_FAILURES=\"$$profile_failures\"",
                "$(MAKE) goal-runtime-reconcile",
                "GOAL_PROFILE_VERIFICATION_APPLY=1",
                "GOAL_PROFILE_VERIFICATION_OUT",
                "contract_update",
                "verification_status",
                "raise SystemExit(0 if ok else 1)",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "auto-improve-goal-ladder-start",
            (
                "GOAL_RUN_ID=\"$(GOAL_LADDER_RUN_ID)\"",
                "GOAL_CONTRACT_RUN_ID=\"$(GOAL_LADDER_CONTRACT_RUN_ID)\"",
                "CODEX_GOAL_CONTRACT_ID=\"$(CODEX_GOAL_CONTRACT_ID)\"",
                "GOAL_ALLOW_LEARNING_UNCERTAIN=\"$(GOAL_ALLOW_LEARNING_UNCERTAIN)\"",
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

    def test_ruff_strict_preview_target_is_opt_in_and_scoped(self) -> None:
        text = _makefile_text()

        self.assertIn("RUFF_STRICT_PREVIEW_RULES ?= B,SIM,UP,I", text)
        self.assertIn(
            "RUFF_STRICT_PREVIEW_ALLOWLIST ?= ops/ruff-strict-preview-allowlist.txt",
            text,
        )
        self.assertEqual(
            _allowlist_lines(RUFF_STRICT_PREVIEW_ALLOWLIST),
            {
                "ops/scripts/mechanism/auto_improve_execute_runtime.py",
                "ops/scripts/mechanism/auto_improve_execution_runtime.py",
                "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py",
                "ops/scripts/mechanism/mechanism_review_session_calibration_runtime.py",
                "ops/scripts/mechanism/mechanism_review_outcome_metrics_calibration_runtime.py",
                "ops/scripts/mechanism/promotion_gate_mechanism_finalize_runtime.py",
                "ops/scripts/mechanism/promotion_gate_mechanism_rule_registry_runtime.py",
                "ops/scripts/mechanism/promotion_gate_mechanism_state_runtime.py",
                "ops/scripts/mechanism/promotion_gate_mechanism_report_runtime.py",
                "ops/scripts/eval/structural_complexity_budget_runtime.py",
            },
        )
        self.assertIn(
            '$(PYTHON) tools/ruff_strict_preview.py --vault "$(VAULT)" --allowlist "$(RUFF_STRICT_PREVIEW_ALLOWLIST)" --select "$(RUFF_STRICT_PREVIEW_RULES)"',
            _target_block(text, "ruff-strict-preview"),
        )

    def test_mypy_allowlist_tracks_ops_scripts_surface(self) -> None:
        allowlist = {
            line.strip()
            for line in MYPY_ALLOWLIST.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        script_files = {
            path.as_posix()
            for path in Path("ops/scripts").rglob("*.py")
            if path.is_file() and not path.name.startswith("_") and path.name != "__init__.py"
        }

        self.assertEqual(script_files, allowlist)

    def test_mypy_strict_preview_target_is_opt_in_and_scoped(self) -> None:
        text = _makefile_text()

        self.assertIn(
            "MYPY_STRICT_PREVIEW_FLAGS ?= --check-untyped-defs --disallow-untyped-defs --disallow-incomplete-defs",
            text,
        )
        self.assertIn(
            "MYPY_STRICT_PREVIEW_TARGETS ?= @ops/mypy-strict-preview-allowlist.txt",
            text,
        )
        self.assertEqual(
            _allowlist_lines(MYPY_STRICT_PREVIEW_ALLOWLIST),
            {
                "ops/scripts/mechanism/auto_improve_execute_runtime.py",
                "ops/scripts/mechanism/auto_improve_execution_runtime.py",
                "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py",
                "ops/scripts/mechanism/mechanism_review_session_calibration_runtime.py",
                "ops/scripts/mechanism/mechanism_review_outcome_metrics_calibration_runtime.py",
                "ops/scripts/mechanism/promotion_gate_mechanism_finalize_runtime.py",
                "ops/scripts/mechanism/promotion_gate_mechanism_rule_registry_runtime.py",
                "ops/scripts/mechanism/promotion_gate_mechanism_state_runtime.py",
                "ops/scripts/mechanism/promotion_gate_mechanism_report_runtime.py",
                "ops/scripts/eval/structural_complexity_budget_runtime.py",
            },
        )
        self.assertIn(
            "$(PYTHON) -m mypy --config-file pyproject.toml $(MYPY_STRICT_PREVIEW_FLAGS) $(MYPY_STRICT_PREVIEW_TARGETS)",
            _target_block(text, "mypy-strict-preview"),
        )

    def test_strict_preview_allowlists_reference_existing_paths(self) -> None:
        for allowlist in (RUFF_STRICT_PREVIEW_ALLOWLIST, MYPY_STRICT_PREVIEW_ALLOWLIST):
            with self.subTest(allowlist=allowlist.as_posix()):
                missing = [
                    line
                    for line in _allowlist_lines(allowlist)
                    if not Path(line).exists()
                ]

                self.assertEqual(missing, [])

    def test_public_check_targets_use_canonical_summary_artifact(self) -> None:
        text = _makefile_text()

        summary_block = _target_block(text, "public-check-summary")
        self.assertIn('--public-out "$(PUBLIC_OUT)"', summary_block)
        self.assertIn('--public-python "$(PUBLIC_PYTHON)"', summary_block)
        self.assertIn('--ruff-targets "$(RUFF_TARGETS)"', summary_block)
        self.assertIn('--mypy-targets "$(MYPY_TARGETS)"', summary_block)
        self.assertIn('--pytest-mark-expr "$(PYTEST_PUBLIC_MARK_EXPR)"', summary_block)
        self.assertIn('--pytest-flags "$(PYTEST_FLAGS)"', summary_block)
        self.assertIn("ops.scripts.canonical_artifact_promote", summary_block)
        public_targets = (
            "public-check",
            "public-check-serial",
            "public-check-parallel",
            "public-check-all",
            "public-check-all-serial",
            "public-check-all-parallel",
        )
        for target in public_targets:
            with self.subTest(target=target):
                block = _target_block(text, target)
                self.assertIn("public-check-summary", block)

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
