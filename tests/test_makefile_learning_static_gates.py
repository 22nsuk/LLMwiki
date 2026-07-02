from __future__ import annotations

import unittest

import pytest

from tests.makefile_static_helpers import _makefile_text, _target_block

pytestmark = [
    pytest.mark.public,
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
    pytest.mark.schema_static_smoke,
    pytest.mark.default_test_boundary,
]


class MakefileLearningStaticGateTests(unittest.TestCase):
    def test_learning_readiness_signoff_make_targets_are_explicit_operator_ux(
        self,
    ) -> None:
        text = _makefile_text()

        self.assertIn("learning-readiness-signoff", _target_block(text, ".PHONY"))
        self.assertIn(
            "learning-readiness-signoff-refresh", _target_block(text, ".PHONY")
        )
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
            "LEARNING_READINESS_SIGNOFF_REUSE_FROM ?= $(LEARNING_READINESS_SIGNOFF_OUT)",
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
        refresh_block = _target_block(text, "learning-readiness-signoff-refresh")
        self.assertIn("ops.scripts.learning_readiness_signoff_refresh", refresh_block)
        self.assertIn(
            '--reuse-from "$(LEARNING_READINESS_SIGNOFF_REUSE_FROM)"',
            refresh_block,
        )
        self.assertIn('--out "$(LEARNING_READINESS_SIGNOFF_OUT)"', refresh_block)
        self.assertNotIn("--accepted-by", refresh_block)
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
        negative_lessons_block = _target_block(
            text, "self-improvement-negative-lessons"
        )
        self.assertEqual(
            negative_lessons_block.splitlines()[0],
            "self-improvement-negative-lessons: session-synopsis",
        )
        self.assertIn(
            "ops.scripts.self_improvement_negative_lessons", negative_lessons_block
        )
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
