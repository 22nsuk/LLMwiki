from __future__ import annotations

import re
import unittest

import pytest

from tests.makefile_static_helpers import (
    MakeTargetContract,
    _assert_assignment_values,
    _assert_make_target_contracts,
    _assert_phony_targets,
    _makefile_text,
    _phony_target_names,
    _recipe_lines,
    _target_block,
)

pytestmark = [
    pytest.mark.public,
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
    pytest.mark.schema_static_smoke,
]


_RELEASE_RUN_READY_CURRENT_TARGET_CONTRACTS = (
    MakeTargetContract(
        "release-run-ready",
        phony=True,
        required_tokens=(
            "$(MAKE) release-run-ready-plan",
            "ops.scripts.release_run_ready",
            '--distribution-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
            '--source-package-smoke "$(SOURCE_PACKAGE_SMOKE_OUT)"',
            '--closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)"',
        ),
    ),
    MakeTargetContract(
        "release-run-ready-plan",
        phony=True,
        required_tokens=(
            "--plan",
            '--plan-out "$(RELEASE_RUN_READY_PLAN_OUT)"',
            '--distribution-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
            '--source-package-smoke "$(SOURCE_PACKAGE_SMOKE_OUT)"',
            '--closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)"',
        ),
    ),
    MakeTargetContract(
        "release-run-ready-plan-check",
        phony=True,
        required_tokens=(
            "--require-ready",
            '--plan-out "$(RELEASE_RUN_READY_PLAN_CHECK_OUT)"',
            '--distribution-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
            '--source-package-smoke "$(SOURCE_PACKAGE_SMOKE_OUT)"',
            '--closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)"',
        ),
    ),
    MakeTargetContract(
        "release-run-ready-check",
        phony=True,
        required_tokens=(
            "ops.scripts.release_run_manifest",
            '--distribution-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
            '--source-package-smoke "$(SOURCE_PACKAGE_SMOKE_OUT)"',
            '--closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)"',
        ),
    ),
    MakeTargetContract(
        "release-test-current",
        exact_recipe=(
            "$(MAKE) static",
            "$(MAKE) report-schema-samples-check",
            "$(MAKE) test-execution-summary-full-current-or-refresh",
            "$(MAKE) test-execution-summary-current-or-refresh",
        ),
        forbidden_tokens=(
            "$(PYTHON) -m pytest $(PYTEST_SERIAL_FLAGS)",
            "$(MAKE) generated-artifact-converge",
        ),
    ),
    MakeTargetContract(
        "release-public-current",
        exact_recipe=("$(MAKE) public-check-summary-current-or-refresh",),
    ),
)

_RELEASE_RUN_READY_ASSIGNMENTS = (
    ("RELEASE_RUN_READY_PLAN_OUT", "build/release/release-run-ready-plan.json"),
    ("RELEASE_RUN_READY_PLAN_CHECK_OUT", "tmp/release-run-ready-plan-check.json"),
)

_RELEASE_SEALED_RUN_READY_TARGET_CONTRACTS = (
    MakeTargetContract(
        "release-sealed-run-ready-plan",
        phony=True,
        required_tokens=(
            "ops.scripts.release_evidence_planner",
            "--stage sealed-run-ready",
        ),
    ),
    MakeTargetContract(
        "release-sealed-run-ready",
        phony=True,
        required_tokens=(
            "$(MAKE) release-sealed-run-ready-plan",
            "$(MAKE) release-evidence-closeout-sealed-sidecars",
            "ops.scripts.release_sealed_run_manifest",
        ),
        forbidden_tokens=(
            "release-run-ready-ensure",
            "$(MAKE) release-evidence-closeout-sealed-core-sidecars",
        ),
    ),
    MakeTargetContract(
        "release-sealed-run-ready-check",
        phony=True,
        required_tokens=(
            "ops.scripts.release_sealed_run_manifest",
            "--check",
            '--post-seal-attestation "$(RELEASE_SEALED_POST_SEAL_ATTESTATION_OUT)"',
        ),
    ),
)

_RELEASE_CONVERGE_PHONY_TARGETS = (
    "release-worktree-clean-check",
    "release-converge",
    "release-converge-all-surfaces",
    "head-aligned-evidence-converge",
)

_RELEASE_CONVERGE_TARGET_CONTRACTS = (
    MakeTargetContract(
        "release-check-preflight-converge",
        required_tokens=(
            "release-check-preflight-converge: release-converge-preflight",
            "mutating compatibility alias",
        ),
        forbidden_tokens=("$(MAKE) test-execution-summary-report-contract-refresh\n",),
    ),
    MakeTargetContract(
        "release-check-post-converge",
        required_tokens=(
            "release-check-post-converge: release-converge-post",
            "mutating compatibility alias",
        ),
    ),
    MakeTargetContract(
        "release-converge",
        required_tokens=(
            "$(MAKE) release-converge-preflight",
            "$(MAKE) registry-preflight",
            "$(MAKE) release-smoke-full-reuse",
            "$(MAKE) release-converge-post",
        ),
    ),
    MakeTargetContract(
        "release-converge-all-surfaces",
        required_tokens=(
            "$(MAKE) release-converge",
            "$(MAKE) sync-public-policy",
            "$(MAKE) public-check-all",
            "$(MAKE) release-converge-post",
        ),
    ),
    MakeTargetContract(
        "release-converge-post",
        required_tokens=(
            "$(MAKE) generated-artifact-converge",
            "$(MAKE) remediation-backlog",
            "$(MAKE) release-closeout-fixed-point",
            "$(MAKE) operator-release-summary",
            "$(MAKE) release-closeout-post-check-finalizer-dry-run "
            "RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required",
        ),
        forbidden_tokens=(
            "$(MAKE) generated-artifact-index",
            "$(MAKE) artifact-freshness",
        ),
    ),
)

_RELEASE_SOURCE_READY_PHONY_TARGETS = (
    "release-source-ready-snapshot",
    "release-source-ready-prepare",
    "release-source-ready-commit",
    "release-source-ready-post-verify",
    "release-source-ready",
)

_RELEASE_SOURCE_READY_ABSENT_PHONY_TARGETS = (
    "release-source-ready-post-commit",
    "release-source-ready-post-commit-converge",
    "release-source-ready-amend",
    "release-source-ready-final-guard-amend",
)

_RELEASE_SOURCE_READY_ASSIGNMENTS = (
    (
        "RELEASE_SOURCE_READY_COMMIT_MESSAGE",
        "release: converge source-ready surfaces",
    ),
    ("RELEASE_SOURCE_READY_PRE_STATUS_OUT", "tmp/release-source-ready-pre-status.json"),
    ("RELEASE_SOURCE_READY_COMMIT_OUT", "tmp/release-source-ready-commit.json"),
    ("RELEASE_SOURCE_READY_STATUS_OUT", "tmp/release-source-ready-status.json"),
    ("RELEASE_WORKTREE_CLEAN_CHECK_OUT", "tmp/release-worktree-clean-check.json"),
)

_RELEASE_SOURCE_READY_ABSENT_ASSIGNMENTS = (
    "RELEASE_SOURCE_READY_AMEND_OUT",
    "RELEASE_SOURCE_READY_FINAL_GUARD_AMEND_OUT",
)

_RELEASE_SOURCE_READY_TARGET_CONTRACTS = (
    MakeTargetContract(
        "release-worktree-clean-check",
        required_tokens=(
            "ops.scripts.goal_worktree_guard",
            '--out "$(RELEASE_WORKTREE_CLEAN_CHECK_OUT)"',
        ),
        forbidden_tokens=('--out "$(GOAL_WORKTREE_GUARD_OUT)"',),
    ),
    MakeTargetContract(
        "release-source-ready-snapshot",
        required_tokens=(
            "ops.scripts.release_source_ready_commit",
            "--snapshot-only",
        ),
    ),
    MakeTargetContract(
        "release-source-ready-prepare",
        required_tokens=(
            "$(MAKE) release-source-ready-snapshot",
            "$(MAKE) release-converge-all-surfaces",
            "$(MAKE) test-execution-summary-full-current-or-refresh",
        ),
    ),
    MakeTargetContract(
        "release-source-ready-commit",
        required_tokens=(
            "ops.scripts.release_source_ready_commit",
            '--pre-status "$(RELEASE_SOURCE_READY_PRE_STATUS_OUT)"',
            '--message "$(RELEASE_SOURCE_READY_COMMIT_MESSAGE)"',
        ),
    ),
    MakeTargetContract(
        "release-source-ready-post-verify",
        required_tokens=(
            "$(MAKE) release-check-all-surfaces",
            "$(MAKE) release-source-ready-status",
        ),
        forbidden_tokens=(
            "$(MAKE) auto-improve-readiness-worktree-guard",
            "$(MAKE) goal-runtime-local-evidence-refresh",
            "$(MAKE) generated-artifact-converge",
            "$(MAKE) remediation-backlog",
            "$(MAKE) release-closeout-fixed-point",
            "$(MAKE) release-source-ready-amend",
            "$(MAKE) release-source-ready-final-guard-amend",
        ),
    ),
    MakeTargetContract(
        "release-source-ready",
        required_tokens=(
            "$(MAKE) release-source-ready-prepare",
            "$(MAKE) release-source-ready-commit",
            "$(MAKE) release-post-commit-finalize",
            "$(MAKE) release-source-ready-post-verify",
        ),
    ),
    MakeTargetContract(
        "release-source-ready-status",
        required_tokens=(
            "ops.scripts.release_source_ready_status",
            '--out "$(RELEASE_SOURCE_READY_STATUS_OUT)"',
        ),
    ),
)


_AUTO_PROMOTION_PHONY_TARGETS = (
    "release-auto-promotion-goal-run-id-guard",
    "release-auto-promotion-goal-run-id-verified-check",
    "release-auto-promotion-preflight",
    "release-auto-promotion-preflight-check",
    "release-auto-promotion-safe-cleanup",
    "release-auto-promotion-safe-cleanup-cleanup-only",
    "release-auto-promotion-safe-cleanup-finalize",
    "release-auto-promotion-preseal",
    "release-auto-promotion-preseal-check",
    "release-auto-promotion-ready-plan",
    "release-auto-promotion-operator-summary",
    "release-auto-promotion-ready-invalidate",
    "release-auto-promotion-preflight-prerequisites",
)

_AUTO_PROMOTION_INVALIDATED_BY_TARGETS = (
    "release-run-ready",
    "release-sealed-run-ready",
    "release-auto-promotion-preflight",
    "release-auto-promotion-preseal",
    "release-auto-promotion-operator-summary",
)

_AUTO_PROMOTION_REPORT_INPUT_TOKENS = (
    '--remediation-backlog "$(REMEDIATION_BACKLOG_OUT)"',
    '--learning-revalidation "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT)"',
    '--closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)"',
    '--evidence-cohort "$(RELEASE_EVIDENCE_COHORT_OUT)"',
)

_AUTO_PROMOTION_PRESEAL_EXPENSIVE_WRITERS = (
    "$(MAKE) test-execution-summary-full-refresh",
    "$(MAKE) test-execution-summary-full-body",
    "$(PYTHON) -m pytest",
    "$(MAKE) generated-artifact-converge",
)

_AUTO_PROMOTION_GOAL_IDENTITY_CONTRACTS = (
    MakeTargetContract(
        "release-auto-promotion-goal-run-id-guard",
        required_tokens=(
            "ops.scripts.release_goal_run_identity_guard",
            '--goal-run-id "$(GOAL_RUN_ID)"',
            '--goal-run-id-origin "$(origin GOAL_RUN_ID)"',
        ),
    ),
    MakeTargetContract(
        "release-auto-promotion-goal-run-id-verified-check",
        required_tokens=(
            "--check",
            "--require-verified",
        ),
    ),
)

_AUTO_PROMOTION_PREFLIGHT_PRESEAL_CONTRACTS = (
    MakeTargetContract(
        "release-auto-promotion-preflight",
        required_tokens=(
            "$(MAKE) release-auto-promotion-goal-run-id-guard",
            "ops.scripts.release_auto_promotion_preflight",
            "--phase preflight",
            "$(MAKE) remediation-backlog",
            "$(MAKE) learning-readiness-signoff-revalidation",
            "$(MAKE) auto-improve-readiness-report-body "
            "AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH=1",
            *_AUTO_PROMOTION_REPORT_INPUT_TOKENS,
        ),
    ),
    MakeTargetContract(
        "release-auto-promotion-preseal",
        required_tokens=(
            "$(MAKE) release-auto-promotion-goal-run-id-guard",
            "ops.scripts.release_auto_promotion_preflight",
            "--phase preseal",
            "release-run-ready-plan-check "
            'RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_'
            'DISTRIBUTION_ZIP)"',
            "release-run-ready-check "
            'RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_'
            'DISTRIBUTION_ZIP)"',
            "release-run-ready "
            'RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_'
            'DISTRIBUTION_ZIP)"',
            "$(MAKE) release-closeout-summary-report",
            "$(MAKE) release-evidence-cohort-preseal-refresh",
            "$(MAKE) release-evidence-cohort "
            "RELEASE_EVIDENCE_COHORT_POLICY=strict_same_fingerprint",
            *_AUTO_PROMOTION_REPORT_INPUT_TOKENS,
        ),
        forbidden_tokens=_AUTO_PROMOTION_PRESEAL_EXPENSIVE_WRITERS,
    ),
)

_AUTO_PROMOTION_SAFE_CLEANUP_CONTRACTS = (
    MakeTargetContract(
        "release-auto-promotion-safe-cleanup-cleanup-only",
        required_tokens=(
            "$(MAKE) goal-runtime-clean-transient",
            "$(MAKE) tmp-json-clean",
            "ops.scripts.backfill_archived_run_artifacts",
            "$(MAKE) generated-artifact-index",
            "$(MAKE) artifact-freshness-refresh-check",
        ),
        forbidden_tokens=("$(MAKE) release-closeout-fixed-point",),
    ),
    MakeTargetContract(
        "release-auto-promotion-safe-cleanup-finalize",
        required_tokens=(
            "$(MAKE) external-report-reference-manifest-release-check",
            "$(MAKE) release-closeout-batch-manifest-promote",
            "$(MAKE) release-closeout-fixed-point",
        ),
    ),
    MakeTargetContract(
        "release-auto-promotion-safe-cleanup",
        exact_recipe=(
            "$(MAKE) release-auto-promotion-safe-cleanup-finalize",
            "$(MAKE) tmp-json-clean",
        ),
    ),
)

_AUTO_PROMOTION_READY_AUTHORITY_PHONY_TARGETS = (
    "release-authority-post-ready-finality",
    "release-authority-post-ready-finality-current-check",
    "release-authority-post-ready-finality-current-or-refresh",
    "release-authority-archive-candidate-gate",
    "release-terminal-finality",
)

_AUTO_PROMOTION_READY_AUTHORITY_CONTRACTS = (
    MakeTargetContract(
        "release-auto-promotion-ready",
        phony=True,
        required_tokens=(
            "ops.scripts.release_auto_promotion_ready",
            "$(MAKE) release-auto-promotion-operator-summary",
            "$(MAKE) release-auto-promotion-ready-plan",
            '--run-manifest "$(RELEASE_RUN_MANIFEST_OUT)"',
            '--sealed-run-manifest "$(RELEASE_SEALED_RUN_MANIFEST_OUT)"',
            '--goal-run-status "$(GOAL_RUN_STATUS_OUT)"',
            '--goal-runtime-certificate "$(GOAL_RUNTIME_CERTIFICATE_OUT)"',
            '--auto-promotion-preflight "$(RELEASE_AUTO_PROMOTION_PREFLIGHT_OUT)"',
            '--auto-promotion-preseal "$(RELEASE_AUTO_PROMOTION_PRESEAL_OUT)"',
        ),
        forbidden_tokens=(
            "release-sealed-run-ready-ensure",
            "learning-readiness-signoff-revalidation",
            "auto-improve-readiness-report-body",
            "$(MAKE) release-auto-promotion-preflight",
            "$(MAKE) release-auto-promotion-preseal",
            "$(MAKE) release-sealed-run-ready-check",
        ),
    ),
    MakeTargetContract(
        "release-auto-promotion-ready-check",
        phony=True,
        required_tokens=(
            "ops.scripts.release_auto_promotion_ready",
            "--check",
            '--run-manifest "$(RELEASE_RUN_MANIFEST_OUT)"',
            '--sealed-run-manifest "$(RELEASE_SEALED_RUN_MANIFEST_OUT)"',
            '--operator-summary "$(RELEASE_AUTO_PROMOTION_OPERATOR_SUMMARY_OUT)"',
        ),
    ),
    MakeTargetContract(
        "release-authority-archive-candidate-gate",
        phony=True,
        required_tokens=(
            "$(MAKE) external-report-action-matrix",
            "$(MAKE) generated-artifact-index-body",
            "$(MAKE) archive-execution-manifest-check",
        ),
    ),
    MakeTargetContract(
        "release-authority-post-ready-finality",
        required_tokens=(
            "RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA="
            '"$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)"',
            "RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="
            '"$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"',
            "$(MAKE) release-closeout-post-check-finalizer-dry-run "
            "RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required",
            "$(MAKE) release-closeout-finality-verify",
        ),
    ),
    MakeTargetContract(
        "release-authority-post-ready-finality-current-check",
        required_tokens=(
            "$(MAKE) tmp-json-clean",
            "$(MAKE) release-closeout-batch-manifest-replay-verify",
            "$(MAKE) release-closeout-post-check-finalizer-dry-run "
            "RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required",
            "$(MAKE) release-closeout-finality-verify",
            "$(MAKE) release-finality-resettle-current-diagnose",
        ),
    ),
    MakeTargetContract(
        "release-authority-post-ready-finality-current-or-refresh",
        required_tokens=(
            "$(MAKE) release-authority-post-ready-finality-current-check",
            "$(MAKE) release-authority-post-ready-finality",
        ),
    ),
    MakeTargetContract(
        "release-authority-settle",
        required_tokens=(
            "@status=0; \\",
            "$(MAKE) release-auto-promotion-ready || status=$$?; \\",
            "$(MAKE) release-authority-archive-candidate-gate || exit $$?; \\",
            "if [ $$status -eq 0 ]; then \\",
            "$(MAKE) release-auto-promotion-ready-check || exit $$?; \\",
            "$(PYTHON) -m ops.scripts.release.release_post_commit_finalizer "
            '--vault "$(VAULT)" --mode verify --out '
            '"$(RELEASE_POST_COMMIT_FINALIZATION_OUT)" --fail-on-attention '
            "--fail-on-authority-attention || exit $$?; \\",
            "$(MAKE) release-authority-post-ready-finality-current-or-refresh || exit $$?; \\",
        ),
    ),
    MakeTargetContract(
        "release-auto-promotion-ready-plan",
        required_tokens=(
            "ops.scripts.release_evidence_planner",
            "--stage auto-promotion-ready",
            '--run-manifest "$(RELEASE_RUN_MANIFEST_OUT)"',
            '--sealed-run-manifest "$(RELEASE_SEALED_RUN_MANIFEST_OUT)"',
            '--auto-promotion-preflight "$(RELEASE_AUTO_PROMOTION_PREFLIGHT_OUT)"',
            '--auto-promotion-preseal "$(RELEASE_AUTO_PROMOTION_PRESEAL_OUT)"',
        ),
    ),
    MakeTargetContract(
        "release-auto-promotion-operator-summary",
        required_tokens=('--self-check "$(RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT)"',),
    ),
)

_RELEASE_CHECK_PHONY_TARGETS = (
    "release-check-preflight-converge",
    "release-check-core",
    "release-check-post-check",
    "release-check-post-converge",
    "release-check-all-surfaces",
    "release-check-finalized",
)

_RELEASE_CHECK_TARGET_CONTRACTS = (
    MakeTargetContract(
        "release-check-core",
        required_tokens=(
            "$(MAKE) release-worktree-clean-check",
            "$(MAKE) test-execution-summary-current-check",
            "$(MAKE) test-execution-summary-full-current-check",
            "$(MAKE) static",
            "$(MAKE) artifact-freshness-check",
            "$(MAKE) registry-preflight-check",
            "$(MAKE) lint",
            "$(MAKE) eval",
            "$(MAKE) stage2-eval",
            "$(MAKE) planning-gate",
            "$(MAKE) release-smoke-full-current-check",
        ),
        forbidden_tokens=(
            "$(MAKE) test-report-contract-all",
            "$(MAKE) registry-preflight\n",
            "$(MAKE) unit-tests-release-check",
            "$(MAKE) release-smoke-full-reuse",
            "$(MAKE) release-check-post-converge",
            "$(MAKE) check-all",
            "$(MAKE) unit-tests-all",
        ),
    ),
    MakeTargetContract(
        "release-check",
        required_tokens=(
            "$(MAKE) release-check-core",
            "$(MAKE) release-check-post-check",
        ),
    ),
    MakeTargetContract(
        "release-check-post-check",
        required_tokens=("$(MAKE) release-worktree-clean-check",),
        forbidden_tokens=("$(MAKE) generated-artifact-converge",),
    ),
    MakeTargetContract(
        "release-check-all-surfaces",
        required_tokens=(
            "$(MAKE) release-check-core",
            "$(MAKE) sync-public-policy-check",
            "$(MAKE) public-check-all-check",
            "$(MAKE) release-check-post-check",
        ),
        forbidden_tokens=(
            "$(MAKE) sync-public-policy\n",
            "$(MAKE) public-check-all\n",
            "$(MAKE) release-check\n",
        ),
    ),
    MakeTargetContract(
        "release-check-finalized",
        required_tokens=(
            "release-check-finalized: release-check",
            "compatibility alias",
            "release-check for check-only verification",
            "release-post-commit-finalize after committing source-ready changes",
        ),
    ),
)


def _assert_auto_promotion_phony_targets(
    test: unittest.TestCase,
    text: str,
) -> None:
    _assert_phony_targets(test, text, _AUTO_PROMOTION_PHONY_TARGETS)


def _assert_ready_manifest_invalidation_targets(
    test: unittest.TestCase,
    text: str,
) -> None:
    invalidate_block = _target_block(text, "release-auto-promotion-ready-invalidate")
    for token in (
        'rm -f "$(RELEASE_AUTO_PROMOTION_READY_MANIFEST_OUT)"',
        '"$(RELEASE_AUTO_PROMOTION_READY_PLAN_OUT)"',
        '"$(RELEASE_SEALED_RUN_READY_PLAN_OUT)"',
        '"$(RELEASE_RUN_READY_PLAN_OUT)"',
    ):
        test.assertIn(token, invalidate_block)
    for target in _AUTO_PROMOTION_INVALIDATED_BY_TARGETS:
        with test.subTest(target=target):
            test.assertIn(
                "$(MAKE) release-auto-promotion-ready-invalidate",
                _target_block(text, target),
            )


def _assert_release_targets_do_not_spawn_runtime_trials(
    test: unittest.TestCase,
    text: str,
) -> None:
    for release_target in (
        "release-auto-promotion-goal-run-id-guard",
        "release-auto-promotion-goal-run-id-verified-check",
        "release-auto-promotion-preflight",
        "release-auto-promotion-preflight-check",
        "release-auto-promotion-safe-cleanup",
        "release-auto-promotion-safe-cleanup-cleanup-only",
        "release-auto-promotion-safe-cleanup-finalize",
        "release-auto-promotion-preseal",
        "release-auto-promotion-preseal-check",
        "release-auto-promotion-ready-plan",
        "release-auto-promotion-operator-summary",
        "release-auto-promotion-ready",
        "release-auto-promotion-ready-check",
        "release-authority-settle",
        "release-authority-archive-candidate-gate",
        "release-authority-post-ready-finality-current-check",
        "release-authority-post-ready-finality-current-or-refresh",
    ):
        seen: set[str] = set()
        stack = [release_target]
        while stack:
            target = stack.pop()
            if target in seen:
                continue
            seen.add(target)
            block = _target_block(text, target)
            for forbidden in (
                "auto-improve-goal-run",
                "goal_runtime_runner",
                "$(GOAL_RUN_COMMAND)",
            ):
                test.assertNotIn(
                    forbidden,
                    block,
                    f"{release_target} must not create runtime-trial evidence via {target}",
                )
            for line in _recipe_lines(text, target):
                for match in re.finditer(r"\$\(MAKE\)\s+([A-Za-z0-9_.-]+)", line):
                    stack.append(match.group(1))


class MakefileReleaseOrchestrationStaticGateTests(unittest.TestCase):
    def test_release_converge_targets_preserve_preflight_post_and_all_surface_flow(
        self,
    ) -> None:
        text = _makefile_text()

        _assert_phony_targets(self, text, _RELEASE_CONVERGE_PHONY_TARGETS)
        self.assertNotIn("release-converge-artifact-commit", _phony_target_names(text))
        _assert_make_target_contracts(self, text, _RELEASE_CONVERGE_TARGET_CONTRACTS)

        release_converge_post_block = _target_block(text, "release-converge-post")
        self.assertGreater(
            release_converge_post_block.index("$(MAKE) operator-release-summary"),
            release_converge_post_block.index("$(MAKE) release-closeout-fixed-point"),
        )
        self.assertGreater(
            release_converge_post_block.rindex("$(MAKE) release-closeout-fixed-point"),
            release_converge_post_block.rindex("$(MAKE) generated-artifact-converge"),
        )
        self.assertGreaterEqual(
            release_converge_post_block.count("$(MAKE) generated-artifact-converge"),
            2,
        )
        self.assertGreaterEqual(
            release_converge_post_block.count("$(MAKE) release-closeout-fixed-point"),
            2,
        )

    def test_release_source_ready_targets_commit_source_and_verify_without_amends(
        self,
    ) -> None:
        text = _makefile_text()
        phony_targets = set(_phony_target_names(text))

        _assert_phony_targets(self, text, _RELEASE_SOURCE_READY_PHONY_TARGETS)
        for target in _RELEASE_SOURCE_READY_ABSENT_PHONY_TARGETS:
            with self.subTest(target=target, surface="phony"):
                self.assertNotIn(target, phony_targets)
        _assert_assignment_values(self, text, _RELEASE_SOURCE_READY_ASSIGNMENTS)
        for variable in _RELEASE_SOURCE_READY_ABSENT_ASSIGNMENTS:
            with self.subTest(variable=variable):
                self.assertNotIn(variable, text)
        _assert_make_target_contracts(
            self,
            text,
            _RELEASE_SOURCE_READY_TARGET_CONTRACTS,
        )

    def test_release_run_ready_and_current_targets_use_plans_and_current_evidence(
        self,
    ) -> None:
        text = _makefile_text()
        phony_targets = _phony_target_names(text)

        self.assertNotIn("release-run-ready-ensure", phony_targets)
        _assert_assignment_values(self, text, _RELEASE_RUN_READY_ASSIGNMENTS)
        _assert_make_target_contracts(
            self,
            text,
            _RELEASE_RUN_READY_CURRENT_TARGET_CONTRACTS,
        )

    def test_release_sealed_run_ready_targets_use_planner_and_sidecars(self) -> None:
        text = _makefile_text()
        phony_targets = _phony_target_names(text)

        self.assertNotIn("release-sealed-run-ready-ensure", phony_targets)
        _assert_make_target_contracts(
            self,
            text,
            _RELEASE_SEALED_RUN_READY_TARGET_CONTRACTS,
        )

    def test_release_auto_promotion_preflight_and_preseal_targets_preserve_ordered_gates(
        self,
    ) -> None:
        text = _makefile_text()
        _assert_auto_promotion_phony_targets(self, text)
        _assert_ready_manifest_invalidation_targets(self, text)
        _assert_make_target_contracts(
            self,
            text,
            _AUTO_PROMOTION_GOAL_IDENTITY_CONTRACTS
            + _AUTO_PROMOTION_PREFLIGHT_PRESEAL_CONTRACTS
            + _AUTO_PROMOTION_SAFE_CLEANUP_CONTRACTS,
        )

    def test_release_auto_promotion_ready_and_authority_settle_do_not_spawn_runtime_trials(
        self,
    ) -> None:
        text = _makefile_text()

        _assert_phony_targets(self, text, _AUTO_PROMOTION_READY_AUTHORITY_PHONY_TARGETS)
        _assert_make_target_contracts(
            self,
            text,
            _AUTO_PROMOTION_READY_AUTHORITY_CONTRACTS,
        )

        auto_promotion_block = _target_block(text, "release-auto-promotion-ready")
        self.assertLess(
            auto_promotion_block.index("$(MAKE) release-auto-promotion-operator-summary"),
            auto_promotion_block.index("$(MAKE) release-auto-promotion-ready-plan"),
        )
        settle_recipe = _recipe_lines(text, "release-authority-settle")
        finality_or_refresh_line = (
            "$(MAKE) release-authority-post-ready-finality-current-or-refresh || exit $$?; \\"
        )
        final_status_propagation_line = "if [ $$status -ne 0 ]; then exit $$status; fi"
        self.assertEqual(
            settle_recipe[settle_recipe.index(finality_or_refresh_line) + 1],
            final_status_propagation_line,
        )
        _assert_release_targets_do_not_spawn_runtime_trials(self, text)

    def test_release_check_targets_use_check_only_surfaces_and_finalized_alias(
        self,
    ) -> None:
        text = _makefile_text()
        _assert_phony_targets(self, text, _RELEASE_CHECK_PHONY_TARGETS)
        _assert_make_target_contracts(self, text, _RELEASE_CHECK_TARGET_CONTRACTS)

        core_block = _target_block(text, "release-check-core")
        self.assertLess(
            core_block.index("$(MAKE) release-worktree-clean-check"),
            core_block.index(
                "$(MAKE) test-execution-summary-current-check"
            ),
        )
        self.assertLess(
            core_block.index(
                "$(MAKE) test-execution-summary-full-current-check"
            ),
            core_block.index("$(MAKE) release-smoke-full-current-check"),
        )

        release_check_block = _target_block(text, "release-check")
        self.assertLess(
            release_check_block.index("$(MAKE) release-check-core"),
            release_check_block.index("$(MAKE) release-check-post-check"),
        )

        all_surfaces_block = _target_block(text, "release-check-all-surfaces")
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
