from __future__ import annotations

import re
import unittest

import pytest

from tests.makefile_static_helpers import (
    _assert_recipe_contains_tokens,
    _makefile_text,
    _recipe_lines,
    _target_block,
)

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


def _phony_targets(text: str) -> list[str]:
    return _target_block(text, ".PHONY").replace(".PHONY:", "").split()


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


def _assert_auto_promotion_phony_targets(
    test: unittest.TestCase,
    phony_block: str,
) -> None:
    for target in _AUTO_PROMOTION_PHONY_TARGETS:
        with test.subTest(target=target):
            test.assertIn(target, phony_block)


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


def _assert_auto_promotion_report_input_tokens(
    test: unittest.TestCase,
    target_block: str,
) -> None:
    for token in _AUTO_PROMOTION_REPORT_INPUT_TOKENS:
        with test.subTest(token=token):
            test.assertIn(token, target_block)


def _assert_auto_promotion_preflight_order(test: unittest.TestCase, text: str) -> None:
    test.assertEqual(
        _recipe_lines(text, "release-auto-promotion-preflight-prerequisites"),
        [
            "$(MAKE) refresh-generated-core",
            "$(MAKE) external-report-action-matrix",
            "$(MAKE) generated-artifact-index",
        ],
    )
    test.assertEqual(
        _recipe_lines(text, "release-auto-promotion-preflight")[:8],
        [
            "$(MAKE) release-auto-promotion-ready-invalidate",
            "$(MAKE) release-auto-promotion-goal-run-id-guard",
            "$(MAKE) release-auto-promotion-preflight-prerequisites",
            "$(MAKE) release-smoke-fast-refresh-check",
            "$(MAKE) test-execution-summary-current-or-refresh",
            "$(MAKE) artifact-freshness-refresh-check",
            "$(MAKE) auto-improve-readiness-report-body AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH=1",
            "$(MAKE) learning-readiness-signoff-revalidation",
        ],
    )


def _assert_auto_promotion_preseal_order(test: unittest.TestCase, text: str) -> None:
    preseal_recipe = _recipe_lines(text, "release-auto-promotion-preseal")
    test.assertEqual(
        preseal_recipe[:14],
        [
            "$(MAKE) release-auto-promotion-ready-invalidate",
            "$(MAKE) release-auto-promotion-goal-run-id-guard",
            "$(MAKE) release-run-ready-plan-check",
            "$(MAKE) release-run-ready-check",
            "$(MAKE) bootstrap-preflight",
            "$(MAKE) registry-preflight",
            "$(MAKE) release-smoke-full-current-check",
            "$(MAKE) release-smoke-fast-refresh-check",
            "$(MAKE) release-auto-promotion-safe-cleanup-cleanup-only",
            "$(MAKE) learning-readiness-signoff-revalidation",
            "$(MAKE) auto-improve-readiness-report-body AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH=1",
            "$(MAKE) remediation-backlog",
            "$(MAKE) auto-improve-readiness-report-body",
            '$(MAKE) release-evidence-cohort-preseal-refresh RELEASE_EVIDENCE_COHORT_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)"',
        ],
    )
    preseal_refresh_line = (
        '$(MAKE) release-evidence-cohort-preseal-refresh '
        'RELEASE_EVIDENCE_COHORT_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)"'
    )
    strict_cohort_line = (
        "$(MAKE) release-evidence-cohort RELEASE_EVIDENCE_COHORT_POLICY=strict_same_fingerprint "
        'RELEASE_EVIDENCE_COHORT_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)"'
    )
    preseal_fixed_point_line = (
        "$(MAKE) release-closeout-fixed-point "
        'RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)" '
        'RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"'
    )
    test.assertEqual(preseal_recipe.count("$(MAKE) release-closeout-summary-report"), 2)
    test.assertEqual(preseal_recipe.count(preseal_fixed_point_line), 1)
    test.assertLess(preseal_recipe.index(preseal_refresh_line), preseal_recipe.index(strict_cohort_line))
    test.assertLess(
        preseal_recipe.index("$(MAKE) artifact-freshness-refresh-check"),
        preseal_recipe.index(strict_cohort_line),
    )
    preseal_freshness_index = preseal_recipe.index("$(MAKE) artifact-freshness-refresh-check")
    test.assertLess(
        preseal_freshness_index,
        preseal_recipe.index(
            "$(MAKE) release-closeout-summary-report",
            preseal_freshness_index,
        ),
    )
    test.assertLess(
        preseal_recipe.index(
            "$(MAKE) auto-improve-readiness-report-body AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH=1"
        ),
        preseal_recipe.index("$(MAKE) remediation-backlog"),
    )
    test.assertLess(
        preseal_recipe.index("$(MAKE) remediation-backlog"),
        preseal_recipe.index(strict_cohort_line),
    )
    test.assertGreater(
        preseal_recipe.index("$(MAKE) release-clean-blocker-ledger"),
        preseal_recipe.index(strict_cohort_line),
    )
    test.assertLess(
        preseal_recipe.index("$(MAKE) release-clean-blocker-ledger"),
        preseal_recipe.index(preseal_fixed_point_line),
    )
    test.assertLess(
        preseal_recipe.index(preseal_fixed_point_line),
        preseal_recipe.index("$(MAKE) tmp-json-clean"),
    )


class MakefileReleaseOrchestrationStaticGateTests(unittest.TestCase):
    def test_release_converge_targets_preserve_preflight_post_and_all_surface_flow(
        self,
    ) -> None:
        text = _makefile_text()

        phony_block = _target_block(text, ".PHONY")
        self.assertIn("release-worktree-clean-check", phony_block)
        self.assertIn("release-converge", phony_block)
        self.assertIn("release-converge-all-surfaces", phony_block)
        self.assertNotIn("release-converge-artifact-commit", phony_block)
        self.assertIn("head-aligned-evidence-converge", phony_block)

        preflight_block = _target_block(text, "release-check-preflight-converge")
        post_block = _target_block(text, "release-check-post-converge")
        self.assertIn("release-check-preflight-converge: release-converge-preflight", preflight_block)
        self.assertIn("release-check-post-converge: release-converge-post", post_block)
        self.assertIn("mutating compatibility alias", preflight_block)
        self.assertIn("mutating compatibility alias", post_block)
        self.assertEqual(
            _recipe_lines(text, "release-converge-preflight"),
            [
                "$(MAKE) generated-artifact-script-output",
                "$(MAKE) report-schema-samples-regenerate",
                "$(MAKE) goal-runtime-local-evidence-refresh",
                "$(MAKE) test-execution-summary-report-contract-refresh-no-smoke",
            ],
        )
        self.assertNotIn(
            "$(MAKE) test-execution-summary-report-contract-refresh\n",
            preflight_block,
        )

        converge_block = _target_block(text, "release-converge")
        self.assertIn("$(MAKE) release-converge-preflight", converge_block)
        self.assertIn("$(MAKE) registry-preflight", converge_block)
        self.assertIn("$(MAKE) release-smoke-full-reuse", converge_block)
        self.assertIn("$(MAKE) release-converge-post", converge_block)

        converge_all_block = _target_block(text, "release-converge-all-surfaces")
        self.assertIn("$(MAKE) release-converge", converge_all_block)
        self.assertIn("$(MAKE) sync-public-policy", converge_all_block)
        self.assertIn("$(MAKE) public-check-all", converge_all_block)
        self.assertIn("$(MAKE) release-converge-post", converge_all_block)

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
        self.assertGreaterEqual(
            release_converge_post_block.count("$(MAKE) generated-artifact-converge"),
            2,
        )
        self.assertGreaterEqual(
            release_converge_post_block.count("$(MAKE) release-closeout-fixed-point"),
            2,
        )
        self.assertNotIn("$(MAKE) generated-artifact-index", release_converge_post_block)
        self.assertNotIn("$(MAKE) artifact-freshness", release_converge_post_block)

    def test_release_source_ready_targets_commit_source_and_verify_without_amends(
        self,
    ) -> None:
        text = _makefile_text()
        phony_block = _target_block(text, ".PHONY")
        phony_targets = _phony_targets(text)

        self.assertIn("release-source-ready-snapshot", phony_block)
        self.assertIn("release-source-ready-prepare", phony_block)
        self.assertIn("release-source-ready-commit", phony_block)
        self.assertIn("release-source-ready-post-verify", phony_block)
        self.assertNotIn("release-source-ready-post-commit", phony_targets)
        self.assertNotIn("release-source-ready-post-commit-converge", phony_targets)
        self.assertNotIn("release-source-ready-amend", phony_targets)
        self.assertNotIn("release-source-ready-final-guard-amend", phony_targets)
        self.assertIn("release-source-ready", phony_block)
        self.assertIn(
            "RELEASE_SOURCE_READY_COMMIT_MESSAGE ?= release: converge source-ready surfaces",
            text,
        )
        self.assertIn(
            "RELEASE_SOURCE_READY_PRE_STATUS_OUT ?= tmp/release-source-ready-pre-status.json",
            text,
        )
        self.assertIn("RELEASE_SOURCE_READY_COMMIT_OUT ?= tmp/release-source-ready-commit.json", text)
        self.assertNotIn("RELEASE_SOURCE_READY_AMEND_OUT", text)
        self.assertNotIn("RELEASE_SOURCE_READY_FINAL_GUARD_AMEND_OUT", text)
        self.assertIn("RELEASE_SOURCE_READY_STATUS_OUT ?= tmp/release-source-ready-status.json", text)
        self.assertIn("RELEASE_WORKTREE_CLEAN_CHECK_OUT ?= tmp/release-worktree-clean-check.json", text)

        worktree_clean_block = _target_block(text, "release-worktree-clean-check")
        self.assertIn("ops.scripts.goal_worktree_guard", worktree_clean_block)
        self.assertIn('--out "$(RELEASE_WORKTREE_CLEAN_CHECK_OUT)"', worktree_clean_block)
        self.assertNotIn('--out "$(GOAL_WORKTREE_GUARD_OUT)"', worktree_clean_block)

        ready_snapshot_block = _target_block(text, "release-source-ready-snapshot")
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

        ready_commit_block = _target_block(text, "release-source-ready-commit")
        self.assertIn("ops.scripts.release_source_ready_commit", ready_commit_block)
        self.assertIn('--pre-status "$(RELEASE_SOURCE_READY_PRE_STATUS_OUT)"', ready_commit_block)
        self.assertIn('--message "$(RELEASE_SOURCE_READY_COMMIT_MESSAGE)"', ready_commit_block)

        ready_post_verify_block = _target_block(text, "release-source-ready-post-verify")
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

        ready_block = _target_block(text, "release-source-ready")
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
                "$(MAKE) release-post-commit-finalize",
                "$(MAKE) release-source-ready-post-verify",
            ],
        )

    def test_release_run_ready_and_current_targets_use_plans_and_current_evidence(
        self,
    ) -> None:
        text = _makefile_text()
        phony_block = _target_block(text, ".PHONY")
        phony_targets = _phony_targets(text)

        self.assertIn("release-run-ready", phony_block)
        self.assertIn("release-run-ready-plan", phony_block)
        self.assertIn("release-run-ready-plan-check", phony_block)
        self.assertIn("release-run-ready-check", phony_block)
        self.assertNotIn("release-run-ready-ensure", phony_targets)
        self.assertIn("RELEASE_RUN_READY_PLAN_OUT ?= build/release/release-run-ready-plan.json", text)
        self.assertIn("RELEASE_RUN_READY_PLAN_CHECK_OUT ?= tmp/release-run-ready-plan-check.json", text)

        run_ready_block = _target_block(text, "release-run-ready")
        run_ready_plan_block = _target_block(text, "release-run-ready-plan")
        run_ready_plan_check_block = _target_block(text, "release-run-ready-plan-check")
        self.assertIn("$(MAKE) release-run-ready-plan", run_ready_block)
        self.assertIn("ops.scripts.release_run_ready", run_ready_block)
        self.assertIn("--plan", run_ready_plan_block)
        self.assertIn('--plan-out "$(RELEASE_RUN_READY_PLAN_OUT)"', run_ready_plan_block)
        self.assertIn("--require-ready", run_ready_plan_check_block)
        self.assertIn('--plan-out "$(RELEASE_RUN_READY_PLAN_CHECK_OUT)"', run_ready_plan_check_block)
        self.assertIn("ops.scripts.release_run_manifest", _target_block(text, "release-run-ready-check"))

        self.assertEqual(
            _recipe_lines(text, "release-test-current"),
            [
                "$(MAKE) static",
                "$(MAKE) report-schema-samples-check",
                "$(MAKE) test-execution-summary-full-current-or-refresh",
                "$(MAKE) test-execution-summary-current-or-refresh",
            ],
        )
        self.assertEqual(
            _recipe_lines(text, "release-public-current"),
            ["$(MAKE) public-check-summary-current-or-refresh"],
        )
        release_test_current_block = _target_block(text, "release-test-current")
        self.assertNotIn("$(PYTHON) -m pytest $(PYTEST_SERIAL_FLAGS)", release_test_current_block)
        self.assertNotIn("$(MAKE) generated-artifact-converge", release_test_current_block)

    def test_release_sealed_run_ready_targets_use_planner_and_sidecars(self) -> None:
        text = _makefile_text()
        phony_targets = _phony_targets(text)

        self.assertIn("release-sealed-run-ready-plan", _target_block(text, ".PHONY"))
        self.assertNotIn("release-sealed-run-ready-ensure", phony_targets)
        sealed_plan_block = _target_block(text, "release-sealed-run-ready-plan")
        self.assertIn("ops.scripts.release_evidence_planner", sealed_plan_block)
        self.assertIn("--stage sealed-run-ready", sealed_plan_block)
        sealed_run_ready_block = _target_block(text, "release-sealed-run-ready")
        self.assertIn("$(MAKE) release-sealed-run-ready-plan", sealed_run_ready_block)
        self.assertIn("$(MAKE) release-evidence-closeout-sealed-sidecars", sealed_run_ready_block)
        self.assertNotIn("release-run-ready-ensure", sealed_run_ready_block)
        self.assertNotIn(
            "$(MAKE) release-evidence-closeout-sealed-core-sidecars",
            sealed_run_ready_block,
        )
        self.assertIn("ops.scripts.release_sealed_run_manifest", sealed_run_ready_block)

    def test_release_auto_promotion_preflight_and_preseal_targets_preserve_ordered_gates(
        self,
    ) -> None:
        text = _makefile_text()
        phony_block = _target_block(text, ".PHONY")

        _assert_auto_promotion_phony_targets(self, phony_block)
        _assert_ready_manifest_invalidation_targets(self, text)

        auto_promotion_goal_identity_block = _target_block(
            text,
            "release-auto-promotion-goal-run-id-guard",
        )
        auto_promotion_verified_goal_identity_block = _target_block(
            text,
            "release-auto-promotion-goal-run-id-verified-check",
        )
        auto_promotion_preflight_block = _target_block(text, "release-auto-promotion-preflight")
        auto_promotion_preseal_block = _target_block(text, "release-auto-promotion-preseal")
        self.assertIn(
            "ops.scripts.release_goal_run_identity_guard",
            auto_promotion_goal_identity_block,
        )
        self.assertIn('--goal-run-id "$(GOAL_RUN_ID)"', auto_promotion_goal_identity_block)
        self.assertIn('--goal-run-id-origin "$(origin GOAL_RUN_ID)"', auto_promotion_goal_identity_block)
        self.assertIn("--check", auto_promotion_verified_goal_identity_block)
        self.assertIn("--require-verified", auto_promotion_verified_goal_identity_block)
        self.assertIn("$(MAKE) release-auto-promotion-goal-run-id-guard", auto_promotion_preflight_block)
        self.assertIn("$(MAKE) release-auto-promotion-goal-run-id-guard", auto_promotion_preseal_block)
        _assert_auto_promotion_preflight_order(self, text)

        self.assertIn(
            "ops.scripts.release_auto_promotion_preflight",
            auto_promotion_preflight_block,
        )
        self.assertIn("--phase preflight", auto_promotion_preflight_block)
        self.assertIn("$(MAKE) remediation-backlog", auto_promotion_preflight_block)
        self.assertIn(
            "$(MAKE) learning-readiness-signoff-revalidation",
            auto_promotion_preflight_block,
        )
        self.assertIn(
            "$(MAKE) auto-improve-readiness-report-body AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH=1",
            auto_promotion_preflight_block,
        )
        _assert_auto_promotion_report_input_tokens(self, auto_promotion_preflight_block)

        _assert_auto_promotion_preseal_order(self, text)
        _assert_recipe_contains_tokens(
            self,
            text,
            "release-auto-promotion-safe-cleanup-cleanup-only",
            (
                "$(MAKE) goal-runtime-clean-transient",
                "$(MAKE) tmp-json-clean",
                "ops.scripts.backfill_archived_run_artifacts",
                "$(MAKE) generated-artifact-index",
                "$(MAKE) artifact-freshness-refresh-check",
            ),
        )
        self.assertNotIn(
            "$(MAKE) release-closeout-fixed-point",
            _target_block(text, "release-auto-promotion-safe-cleanup-cleanup-only"),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "release-auto-promotion-safe-cleanup-finalize",
            (
                "$(MAKE) external-report-reference-manifest-release-check",
                "$(MAKE) release-closeout-batch-manifest-promote",
                "$(MAKE) release-closeout-fixed-point",
            ),
        )
        self.assertEqual(
            _recipe_lines(text, "release-auto-promotion-safe-cleanup"),
            [
                "$(MAKE) release-auto-promotion-safe-cleanup-finalize",
                "$(MAKE) tmp-json-clean",
            ],
        )
        for expensive_writer in _AUTO_PROMOTION_PRESEAL_EXPENSIVE_WRITERS:
            self.assertNotIn(expensive_writer, auto_promotion_preseal_block)

        self.assertIn("ops.scripts.release_auto_promotion_preflight", auto_promotion_preseal_block)
        self.assertIn("--phase preseal", auto_promotion_preseal_block)
        self.assertIn("$(MAKE) release-run-ready-plan-check", auto_promotion_preseal_block)
        self.assertIn("$(MAKE) release-run-ready-check", auto_promotion_preseal_block)
        self.assertIn("$(MAKE) release-closeout-summary-report", auto_promotion_preseal_block)
        self.assertIn(
            "$(MAKE) release-evidence-cohort-preseal-refresh",
            auto_promotion_preseal_block,
        )
        self.assertIn(
            "$(MAKE) release-evidence-cohort RELEASE_EVIDENCE_COHORT_POLICY=strict_same_fingerprint",
            auto_promotion_preseal_block,
        )
        _assert_auto_promotion_report_input_tokens(self, auto_promotion_preseal_block)

    def test_release_auto_promotion_ready_and_authority_settle_do_not_spawn_runtime_trials(
        self,
    ) -> None:
        text = _makefile_text()

        phony_block = _target_block(text, ".PHONY")
        auto_promotion_block = _target_block(text, "release-auto-promotion-ready")
        self.assertIn("ops.scripts.release_auto_promotion_ready", auto_promotion_block)
        self.assertIn("$(MAKE) release-auto-promotion-ready-plan", auto_promotion_block)
        self.assertNotIn("$(MAKE) release-auto-promotion-operator-summary", auto_promotion_block)
        self.assertIn('--run-manifest "$(RELEASE_RUN_MANIFEST_OUT)"', auto_promotion_block)
        self.assertIn('--sealed-run-manifest "$(RELEASE_SEALED_RUN_MANIFEST_OUT)"', auto_promotion_block)
        self.assertIn('--goal-run-status "$(GOAL_RUN_STATUS_OUT)"', auto_promotion_block)
        self.assertIn('--goal-runtime-certificate "$(GOAL_RUNTIME_CERTIFICATE_OUT)"', auto_promotion_block)
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
        self.assertIn("release-authority-post-ready-finality", phony_block)
        self.assertIn("release-authority-post-ready-finality-current-check", phony_block)
        self.assertIn("release-authority-post-ready-finality-current-or-refresh", phony_block)
        self.assertIn("release-authority-archive-candidate-gate", phony_block)
        self.assertEqual(
            _recipe_lines(text, "release-authority-archive-candidate-gate"),
            [
                "$(MAKE) external-report-action-matrix",
                "$(MAKE) generated-artifact-index-body",
                "$(MAKE) archive-execution-manifest-check",
            ],
        )
        self.assertEqual(
            _recipe_lines(text, "release-authority-post-ready-finality"),
            [
                "$(MAKE) artifact-freshness-refresh-check",
                '$(MAKE) release-closeout-batch-manifest-promote RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)" RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"',
                '$(MAKE) release-closeout-fixed-point RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)" RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"',
                "$(MAKE) tmp-json-clean",
                '$(MAKE) release-closeout-batch-manifest-replay-verify RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)" RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"',
                "$(MAKE) release-closeout-finality-verify",
            ],
        )
        self.assertEqual(
            _recipe_lines(text, "release-authority-post-ready-finality-current-check"),
            [
                "$(MAKE) tmp-json-clean",
                '$(MAKE) release-closeout-batch-manifest-replay-verify RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)" RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"',
                "$(MAKE) release-closeout-finality-verify",
            ],
        )
        current_or_refresh_block = _target_block(
            text,
            "release-authority-post-ready-finality-current-or-refresh",
        )
        self.assertIn(
            "$(MAKE) release-authority-post-ready-finality-current-check",
            current_or_refresh_block,
        )
        self.assertIn(
            "$(MAKE) release-authority-post-ready-finality",
            current_or_refresh_block,
        )
        self.assertEqual(
            _recipe_lines(text, "release-authority-settle"),
            [
                "$(MAKE) release-finality-resettle-current-or-refresh",
                "$(MAKE) release-auto-promotion-goal-run-id-verified-check",
                "$(MAKE) release-auto-promotion-preflight",
                "$(MAKE) release-run-ready",
                "$(MAKE) release-auto-promotion-preseal",
                "$(MAKE) release-sealed-run-ready",
                "@status=0; \\",
                "$(MAKE) release-auto-promotion-ready || status=$$?; \\",
                "$(MAKE) release-authority-archive-candidate-gate || exit $$?; \\",
                "if [ $$status -eq 0 ]; then \\",
                "$(MAKE) release-auto-promotion-preflight-check || exit $$?; \\",
                "$(MAKE) release-run-ready-check || exit $$?; \\",
                "$(MAKE) release-auto-promotion-preseal-check || exit $$?; \\",
                "$(MAKE) release-sealed-run-ready-check || exit $$?; \\",
                "$(MAKE) release-auto-promotion-ready-check || exit $$?; \\",
                '$(PYTHON) -m ops.scripts.release.release_post_commit_finalizer --vault "$(VAULT)" --mode verify --out "$(RELEASE_POST_COMMIT_FINALIZATION_OUT)" --fail-on-attention --fail-on-authority-attention || exit $$?; \\',
                "fi; \\",
                "$(MAKE) release-authority-post-ready-finality-current-or-refresh || exit $$?; \\",
                "if [ $$status -ne 0 ]; then exit $$status; fi",
            ],
        )
        settle_block = _recipe_lines(text, "release-authority-settle")
        verified_goal_index = settle_block.index(
            "$(MAKE) release-auto-promotion-goal-run-id-verified-check"
        )
        run_ready_index = settle_block.index("$(MAKE) release-run-ready")
        ready_index = settle_block.index("$(MAKE) release-auto-promotion-ready || status=$$?; \\")
        archive_gate_index = settle_block.index(
            "$(MAKE) release-authority-archive-candidate-gate || exit $$?; \\"
        )
        finality_index = settle_block.index(
            "$(MAKE) release-authority-post-ready-finality-current-or-refresh || exit $$?; \\"
        )
        self.assertLess(verified_goal_index, run_ready_index)
        self.assertLess(ready_index, archive_gate_index)
        self.assertLess(archive_gate_index, finality_index)
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
                    self.assertNotIn(
                        forbidden,
                        block,
                        f"{release_target} must not create runtime-trial evidence via {target}",
                    )
                for line in _recipe_lines(text, target):
                    for match in re.finditer(r"\$\(MAKE\)\s+([A-Za-z0-9_.-]+)", line):
                        stack.append(match.group(1))

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
        self.assertIn(
            '--self-check "$(RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT)"',
            _target_block(text, "release-auto-promotion-operator-summary"),
        )

    def test_release_check_targets_use_check_only_surfaces_and_finalized_alias(
        self,
    ) -> None:
        text = _makefile_text()
        phony_block = _target_block(text, ".PHONY")

        self.assertIn("release-check-preflight-converge", phony_block)
        self.assertIn("release-check-core", phony_block)
        self.assertIn("release-check-post-check", phony_block)
        self.assertIn("release-check-post-converge", phony_block)
        self.assertIn("release-check-all-surfaces", phony_block)

        core_block = _target_block(text, "release-check-core")
        self.assertIn("$(MAKE) release-worktree-clean-check", core_block)
        self.assertIn(
            "$(MAKE) test-execution-summary-current-check",
            core_block,
        )
        self.assertIn(
            "$(MAKE) test-execution-summary-full-current-check",
            core_block,
        )
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
        self.assertNotIn("$(MAKE) check-all", core_block)
        self.assertNotIn("$(MAKE) unit-tests-all", core_block)
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
        self.assertIn("$(MAKE) release-check-core", release_check_block)
        self.assertIn("$(MAKE) release-check-post-check", release_check_block)
        self.assertLess(
            release_check_block.index("$(MAKE) release-check-core"),
            release_check_block.index("$(MAKE) release-check-post-check"),
        )

        post_check_block = _target_block(text, "release-check-post-check")
        self.assertIn("$(MAKE) release-worktree-clean-check", post_check_block)
        self.assertNotIn("$(MAKE) generated-artifact-converge", post_check_block)

        all_surfaces_block = _target_block(text, "release-check-all-surfaces")
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
        self.assertIn("release-check-finalized", phony_block)
        self.assertTrue(finalized_block.startswith("release-check-finalized: release-check"))
        self.assertIn("compatibility alias", finalized_block)
        self.assertIn("release-check for check-only verification", finalized_block)
        self.assertIn(
            "release-post-commit-finalize after committing source-ready changes",
            finalized_block,
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
