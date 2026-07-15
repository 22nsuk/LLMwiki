from __future__ import annotations

import unittest

import pytest

from tests.makefile_static_helpers import (
    _assert_assignment_exists,
    _makefile_text,
    _target_block,
)

pytestmark = [
    pytest.mark.public,
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
    pytest.mark.schema_static_smoke,
]


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
        "SIGSTORE_BUNDLE_REF ?=",
        "SUPPLY_CHAIN_BENCHMARK_OUT ?= ops/reports/supply-chain-benchmark.json",
        "ALLOW_FINALITY_INVALIDATION ?=",
        "UV ?= uv",
        "STRUCTURAL_COMPLEXITY_BUDGET_OUT ?= ops/reports/structural-complexity-budget.json",
        "GENERATED_ARTIFACT_INDEX_OUT ?= ops/reports/generated-artifact-index.json",
        "GENERATED_ARTIFACT_INDEX_CANDIDATE_OUT ?= tmp/generated-artifact-index.candidate.json",
        "GENERATED_ARTIFACT_INDEX_CHECK_OUT ?= tmp/generated-artifact-index-check.json",
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
        "artifact-freshness-stable-contract-debt-refresh:",
        "artifact-relocation-audit:",
        "generated-artifact-converge:",
        "generated-artifact-index:",
        "generated-artifact-index-check:",
        "generated-artifact-index-body:",
        "generated-artifact-index-body-current-check:",
        "generated-artifact-index-body-current-or-refresh:",
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
        "review-archive-clean:",
        "closure-registry-envelope:",
        "supply-chain-artifact-model:",
        "spdx-sbom:",
        "in-toto-statement:",
        "sigstore-bundle:",
        "supply-chain-benchmark:",
        "supply-chain-finality-writer-guard:",
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
            '$(PYTHON) -m ops.scripts.supply_chain_artifacts --vault "$(VAULT)" --provenance-out "$(SUPPLY_CHAIN_PROVENANCE_OUT)" --gate-out "$(SUPPLY_CHAIN_GATE_OUT)" --security-advisories-out "$(SECURITY_ADVISORIES_OUT)" --mapping-out "$(SBOM_EXPORT_MAPPING_OUT)" --readiness-out "$(SBOM_READINESS_GATE_OUT)" --model-out "$(SUPPLY_CHAIN_ARTIFACT_MODEL_OUT)" --cyclonedx-out "$(CYCLONEDX_SBOM_OUT)" --spdx-out "$(SPDX_SBOM_OUT)" --openvex-out "$(OPENVEX_DRAFT_OUT)" --in-toto-out "$(IN_TOTO_STATEMENT_OUT)" --sigstore-out "$(SIGSTORE_BUNDLE_OUT)" $(if $(SIGSTORE_BUNDLE_REF),--sigstore-bundle-ref "$(SIGSTORE_BUNDLE_REF)",)',
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
            '$(PYTHON) -m ops.scripts.sigstore_bundle --vault "$(VAULT)" --out "$(SIGSTORE_BUNDLE_OUT)" $(if $(SIGSTORE_BUNDLE_REF),--bundle-ref "$(SIGSTORE_BUNDLE_REF)",)',
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
    supply_chain_guard = _target_block(text, "supply-chain-finality-writer-guard")
    case.assertIn("ALLOW_FINALITY_INVALIDATION", supply_chain_guard)
    case.assertIn("release-closeout-finality-verify", supply_chain_guard)
    case.assertIn("release-finality-resettle-current-or-refresh", supply_chain_guard)
    case.assertIn(
        "supply-chain-artifacts-cached: supply-chain-finality-writer-guard",
        text,
    )


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
    freshness_stable_debt = _target_block(text, "artifact-freshness-stable-contract-debt-refresh")
    case.assertIn("artifact-freshness-stable-contract-debt-refresh", _target_block(text, ".PHONY"))
    case.assertIn("ops.scripts.backfill_archived_run_artifacts", freshness_stable_debt)
    case.assertIn("$(MAKE) artifact-freshness-refresh-check", freshness_stable_debt)
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
    generated_index_check = _target_block(text, "generated-artifact-index-check")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.generated_artifact_index --vault "$(VAULT)" --out "$(GENERATED_ARTIFACT_INDEX_CHECK_OUT)"',
        generated_index_check,
    )
    case.assertNotIn("ops.scripts.canonical_artifact_promote", generated_index_check)
    generated_index_current_check = _target_block(
        text, "generated-artifact-index-body-current-check"
    )
    case.assertIn(
        '$(PYTHON) -m ops.scripts.generated_artifact_index --vault "$(VAULT)" --current-check',
        generated_index_current_check,
    )
    case.assertNotIn("--out", generated_index_current_check)
    case.assertNotIn(
        "ops.scripts.canonical_artifact_promote", generated_index_current_check
    )
    generated_index_current_or_refresh = _target_block(
        text, "generated-artifact-index-body-current-or-refresh"
    )
    case.assertEqual(
        generated_index_current_or_refresh.count(
            "$(MAKE) generated-artifact-index-body-current-check"
        ),
        2,
    )
    case.assertIn(
        "$(MAKE) generated-artifact-index-body &&",
        generated_index_current_or_refresh,
    )
    case.assertNotIn(
        "ops.scripts.canonical_artifact_promote",
        generated_index_current_or_refresh,
    )
    case.assertIn(
        '$(PYTHON) -m ops.scripts.closure_registry_envelope --vault "$(VAULT)" --registry "$(CLOSURE_REGISTRY_ENVELOPE_REGISTRY)"',
        _target_block(text, "closure-registry-envelope"),
    )


def _assert_archive_and_complexity_recipes(case: unittest.TestCase, text: str) -> None:
    touched_block = _target_block(text, "complexity-budget-touched-check")
    case.assertIn('--out "$(STRUCTURAL_COMPLEXITY_BUDGET_TOUCHED_OUT)"', touched_block)
    case.assertIn('--changed-files-manifest "$(CHANGED_FILES_MANIFEST)"', touched_block)
    case.assertIn('--target "$(target)"', touched_block)
    case.assertIn('rm -f "$(STRUCTURAL_COMPLEXITY_BUDGET_TOUCHED_OUT)"', touched_block)
    case.assertIn("ratchet inactive without touched inputs", touched_block)
    case.assertIn(
        'PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m ops.scripts.release.review_archive --vault "$(VAULT)" --archive-out "$(REVIEW_ARCHIVE_OUT)" --out "$(REVIEW_ARCHIVE_REPORT_OUT)" --profile "$(REVIEW_ARCHIVE_PROFILE)"',
        _target_block(text, "review-archive"),
    )
    review_archive_clean_block = _target_block(text, "review-archive-clean")
    case.assertIn("$(MAKE) local-cache-clean", review_archive_clean_block)
    case.assertIn("$(MAKE) tmp-json-clean", review_archive_clean_block)
    case.assertIn(
        "$(MAKE) review-archive REVIEW_ARCHIVE_PROFILE=clean",
        review_archive_clean_block,
    )
    case.assertLess(
        review_archive_clean_block.index("$(MAKE) local-cache-clean"),
        review_archive_clean_block.index("$(MAKE) tmp-json-clean"),
    )
    case.assertLess(
        review_archive_clean_block.index("$(MAKE) tmp-json-clean"),
        review_archive_clean_block.index("$(MAKE) review-archive REVIEW_ARCHIVE_PROFILE=clean"),
    )
    archive_modes = (
        (
            "archive-execution-manifest-check",
            '$(PYTHON) -m ops.scripts.archive_execution_manifest --vault "$(VAULT)" --index-path "$(GENERATED_ARTIFACT_INDEX_OUT)" --out "$(ARCHIVE_EXECUTION_MANIFEST_OUT)" --mode dry_run --fail-on-attention',
        ),
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


class MakefilePublicRegistrySupplyChainGateTests(unittest.TestCase):
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
            "ops.scripts.canonical_artifact_promote",
            _target_block(text, "raw-registry-cross-environment-evidence-bundle-check"),
        )

    def test_public_check_targets_use_canonical_summary_artifact(self) -> None:
        text = _makefile_text()

        summary_block = _target_block(text, "public-check-summary")
        summary_check_block = _target_block(text, "public-check-summary-check")
        summary_current_check_block = _target_block(text, "public-check-summary-current-check")
        summary_current_or_refresh_block = _target_block(
            text,
            "public-check-summary-current-or-refresh",
        )
        summary_full_block = _target_block(text, "public-check-summary-full")
        summary_full_check_block = _target_block(text, "public-check-summary-full-check")
        summary_full_current_check_block = _target_block(
            text,
            "public-check-summary-full-current-check",
        )
        sync_check_block = _target_block(text, "sync-public-policy-check")
        _assert_assignment_exists(
            self, text, "PUBLIC_CHECK_SUMMARY_REUSE_FROM", "$(PUBLIC_CHECK_SUMMARY_OUT)"
        )
        _assert_assignment_exists(
            self, text, "PUBLIC_CHECK_SUMMARY_FULL_OUT", "ops/reports/public-check-summary-full.json"
        )
        _assert_assignment_exists(
            self,
            text,
            "PUBLIC_CHECK_SUMMARY_FULL_CANDIDATE_OUT",
            "tmp/public-check-summary-full.candidate.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "PUBLIC_CHECK_SUMMARY_FULL_CHECK_OUT",
            "tmp/public-check-summary-full-check.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "PUBLIC_CHECK_SUMMARY_FULL_REUSE_FROM",
            "$(PUBLIC_CHECK_SUMMARY_FULL_OUT)",
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
        self.assertIn(
            '--heartbeat-interval-seconds "$(PUBLIC_CHECK_HEARTBEAT_INTERVAL_SECONDS)"',
            summary_block,
        )
        self.assertIn("ops.scripts.canonical_artifact_promote", summary_block)
        self.assertIn('--out "$(PUBLIC_CHECK_SUMMARY_CHECK_OUT)"', summary_check_block)
        self.assertNotIn("ops.scripts.canonical_artifact_promote", summary_check_block)
        self.assertIn('--out "$(PUBLIC_CHECK_SUMMARY_CHECK_OUT)"', summary_current_check_block)
        self.assertIn("--reuse-if-current", summary_current_check_block)
        self.assertIn("--reuse-only", summary_current_check_block)
        self.assertIn('--reuse-from "$(PUBLIC_CHECK_SUMMARY_REUSE_FROM)"', summary_current_check_block)
        self.assertNotIn("ops.scripts.canonical_artifact_promote", summary_current_check_block)
        self.assertIn("$(MAKE) public-check-summary-current-check", summary_current_or_refresh_block)
        self.assertIn("$(MAKE) public-check-summary", summary_current_or_refresh_block)
        self.assertIn('--out "$(PUBLIC_CHECK_SUMMARY_FULL_CANDIDATE_OUT)"', summary_full_block)
        self.assertIn('--mode full', summary_full_block)
        self.assertIn('--pytest-mark-expr ""', summary_full_block)
        self.assertIn(
            '--candidate "$(PUBLIC_CHECK_SUMMARY_FULL_CANDIDATE_OUT)"', summary_full_block
        )
        self.assertIn('--out "$(PUBLIC_CHECK_SUMMARY_FULL_OUT)"', summary_full_block)
        self.assertIn('--out "$(PUBLIC_CHECK_SUMMARY_FULL_CHECK_OUT)"', summary_full_check_block)
        self.assertNotIn("ops.scripts.canonical_artifact_promote", summary_full_check_block)
        self.assertIn(
            '--out "$(PUBLIC_CHECK_SUMMARY_FULL_CHECK_OUT)"', summary_full_current_check_block
        )
        self.assertIn("--reuse-if-current", summary_full_current_check_block)
        self.assertIn("--reuse-only", summary_full_current_check_block)
        self.assertIn(
            '--reuse-from "$(PUBLIC_CHECK_SUMMARY_FULL_REUSE_FROM)"',
            summary_full_current_check_block,
        )
        self.assertNotIn(
            "ops.scripts.canonical_artifact_promote", summary_full_current_check_block
        )
        self.assertIn("--check", sync_check_block)
        self.assertIn('--gitignore "$(PUBLIC_GITIGNORE_TEMPLATE)"', sync_check_block)
        public_targets = (
            "ci-public-tier",
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
                if target == "ci-public-tier":
                    self.assertIn("public-check", block)
                elif target == "public-check-all-check":
                    self.assertIn("public-check-summary-full-current-check", block)
                elif target.startswith("public-check-all"):
                    self.assertIn("public-check-summary-full", block)
                else:
                    self.assertIn("public-check-summary", block)
        ci_public_block = _target_block(text, "ci-public-tier")
        self.assertIn("$(MAKE) public-check", ci_public_block)
        self.assertNotIn("PYTEST_PUBLIC_MARK_EXPR", ci_public_block)

    def test_supply_chain_check_targets_exist(self) -> None:
        text = _makefile_text()

        _assert_supply_chain_make_variables(self, text)
        _assert_supply_chain_target_names(self, text)
        _assert_sbom_supply_chain_recipes(self, text)
        _assert_artifact_index_and_freshness_recipes(self, text)
        _assert_archive_and_complexity_recipes(self, text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
