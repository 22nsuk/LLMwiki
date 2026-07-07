from __future__ import annotations

import unittest

import pytest

from tests.makefile_static_helpers import (
    MakeTargetContract,
    _assert_assignment_values,
    _assert_make_target_contracts,
    _assert_phony_targets,
    _makefile_text,
    _target_block,
    _target_dependencies,
)

pytestmark = [
    pytest.mark.public,
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
    pytest.mark.schema_static_smoke,
    pytest.mark.default_test_boundary,
]


_LEARNING_READINESS_SIGNOFF_PHONY_TARGETS = (
    "learning-readiness-signoff",
    "learning-readiness-signoff-refresh",
    "learning-readiness-signoff-check",
    "learning-readiness-signoff-revalidation",
    "learning-readiness-signoff-revalidation-check",
    "learning-readiness-signoff-template",
)

_LEARNING_READINESS_SIGNOFF_ASSIGNMENTS = (
    (
        "LEARNING_READINESS_SIGNOFF_OUT",
        "ops/reports/learning-readiness-signoff.json",
    ),
    (
        "LEARNING_READINESS_SIGNOFF_REUSE_FROM",
        "$(LEARNING_READINESS_SIGNOFF_OUT)",
    ),
    (
        "LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT",
        "ops/reports/learning-readiness-signoff-revalidation.json",
    ),
    (
        "LEARNING_READINESS_SIGNOFF_REVALIDATION_CHECK_OUT",
        "tmp/learning-readiness-signoff-revalidation-check.json",
    ),
    ("LEARNING_READINESS_SIGNOFF_REVALIDATION_WINDOW_DAYS", "7"),
    (
        "LEARNING_READINESS_SIGNOFF_REVALIDATION_COMMAND",
        "make release-evidence-converge PYTHON=.venv/bin/python",
    ),
    (
        "LEARNING_READINESS_SIGNOFF_REVALIDATION_ENVIRONMENT",
        ".venv clean release-builder",
    ),
    ("LEARNING_READINESS_SIGNOFF_ACCEPTED_BY", ""),
    ("LEARNING_READINESS_SIGNOFF_EXPIRY_DAYS", "14"),
)


_LEARNING_READINESS_SIGNOFF_TARGET_CONTRACTS = (
    MakeTargetContract(
        "learning-readiness-signoff",
        required_tokens=(
            "ops.scripts.learning_readiness_signoff",
            '--accepted-by "$(LEARNING_READINESS_SIGNOFF_ACCEPTED_BY)"',
            '--expiry-days "$(LEARNING_READINESS_SIGNOFF_EXPIRY_DAYS)"',
            '--risk-owner "$(LEARNING_READINESS_SIGNOFF_RISK_OWNER)"',
            '--revalidation-condition "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_CONDITION)"',
            '--rollback-trigger "$(LEARNING_READINESS_SIGNOFF_ROLLBACK_TRIGGER)"',
        ),
    ),
    MakeTargetContract(
        "learning-readiness-signoff-refresh",
        required_tokens=(
            "ops.scripts.learning_readiness_signoff_refresh",
            '--reuse-from "$(LEARNING_READINESS_SIGNOFF_REUSE_FROM)"',
            '--out "$(LEARNING_READINESS_SIGNOFF_OUT)"',
        ),
    ),
    MakeTargetContract(
        "learning-readiness-signoff-check",
        required_tokens=(
            "tmp/learning-readiness-signoff-check-release-closeout-summary.json",
        ),
    ),
    MakeTargetContract(
        "learning-readiness-signoff-revalidation",
        required_tokens=(
            "ops.scripts.learning_readiness_signoff_revalidation",
            '--window-days "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_WINDOW_DAYS)"',
            '--required-command "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_COMMAND)"',
            '--required-environment "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_ENVIRONMENT)"',
        ),
    ),
    MakeTargetContract(
        "learning-readiness-signoff-revalidation-check",
        required_tokens=(
            "--fail-on-due",
            '--out "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_CHECK_OUT)"',
        ),
    ),
    MakeTargetContract(
        "learning-readiness-signoff-template",
        required_tokens=(
            "$(PYTHON) -m json.tool ops/templates/learning-readiness-signoff.json",
        ),
    ),
)

_LEARNING_PIPELINE_PHONY_TARGETS = (
    "learning-claim-evidence-bundle",
    "learning-confirmed-legacy-reconstruction",
    "learning-confirmed-evidence-cohort",
    "learning-claim-unlock-review",
    "learning-delta-scoreboard",
    "learning-claim-activation-report",
    "session-synopsis",
    "self-improvement-negative-lessons",
    "remediation-backlog",
    "public-check-summary",
    "tmp-clean",
)


_LEARNING_PIPELINE_ASSIGNMENTS = (
    ("PUBLIC_CHECK_SUMMARY_OUT", "ops/reports/public-check-summary.json"),
    (
        "LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT",
        "ops/reports/learning-claim-evidence-bundle.json",
    ),
    (
        "LEARNING_CONFIRMED_LEGACY_RECONSTRUCTION_OUT",
        "ops/reports/learning-confirmed-legacy-reconstruction.json",
    ),
    (
        "LEARNING_CONFIRMED_EVIDENCE_COHORT_OUT",
        "ops/reports/learning-confirmed-evidence-cohort.json",
    ),
    (
        "LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY",
        "ops/policies/learning-claim-confirmed-improvement.json",
    ),
    (
        "LEARNING_DELTA_SCOREBOARD_OUT",
        "ops/reports/learning-delta-scoreboard.json",
    ),
    (
        "LEARNING_CLAIM_ACTIVATION_REPORT_OUT",
        "ops/reports/learning_claim_activation_report.json",
    ),
    ("SESSION_SYNOPSIS_OUT", "ops/reports/session-synopsis.json"),
    (
        "SELF_IMPROVEMENT_NEGATIVE_LESSONS_OUT",
        "ops/reports/self-improvement-negative-lessons.json",
    ),
    ("REMEDIATION_BACKLOG_OUT", "ops/reports/remediation-backlog.json"),
)


def _promoted_target_contract(
    target: str,
    producer: str,
    schema: str,
    *,
    required_tokens: tuple[str, ...] = (),
    forbidden_tokens: tuple[str, ...] = (),
) -> MakeTargetContract:
    return MakeTargetContract(
        target,
        required_tokens=(
            producer,
            "ops.scripts.canonical_artifact_promote",
            schema,
            *required_tokens,
        ),
        forbidden_tokens=forbidden_tokens,
    )


_LEARNING_PIPELINE_TARGET_CONTRACTS = (
    _promoted_target_contract(
        "learning-confirmed-legacy-reconstruction",
        "ops.scripts.learning_confirmed_legacy_reconstruction",
        "ops/schemas/learning-confirmed-legacy-reconstruction.schema.json",
    ),
    _promoted_target_contract(
        "learning-claim-evidence-bundle",
        "ops.scripts.learning_claim_evidence_bundle",
        "ops/schemas/learning-claim-evidence-bundle.schema.json",
    ),
    _promoted_target_contract(
        "learning-confirmed-evidence-cohort",
        "ops.scripts.learning_confirmed_evidence_cohort",
        "ops/schemas/learning-confirmed-evidence-cohort.schema.json",
        required_tokens=(
            '--evidence-bundle "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT)"',
            '--confirmed-policy "$(LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY)"',
        ),
    ),
    _promoted_target_contract(
        "public-check-summary",
        "ops.scripts.public_check_summary",
        "ops/schemas/public-check-summary.schema.json",
    ),
    _promoted_target_contract(
        "learning-claim-unlock-review",
        "ops.scripts.learning_claim_unlock_review",
        "ops/schemas/learning-claim-unlock-review.schema.json",
        required_tokens=(
            '--evidence-bundle "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT)"',
            '--confirmed-policy "$(LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY)"',
        ),
    ),
    _promoted_target_contract(
        "learning-delta-scoreboard",
        "ops.scripts.learning_delta_scoreboard",
        "ops/schemas/learning-delta-scoreboard.schema.json",
    ),
    _promoted_target_contract(
        "learning-claim-activation-report",
        "ops.scripts.learning_claim_activation_report",
        "ops/schemas/learning-claim-activation-report.schema.json",
    ),
    _promoted_target_contract(
        "session-synopsis",
        "ops.scripts.session_synopsis",
        "ops/schemas/session-synopsis.schema.json",
    ),
    _promoted_target_contract(
        "self-improvement-negative-lessons",
        "ops.scripts.self_improvement_negative_lessons",
        "ops/schemas/self-improvement-negative-lessons.schema.json",
    ),
    _promoted_target_contract(
        "remediation-backlog",
        "ops.scripts.remediation_backlog",
        "ops/schemas/remediation-backlog.schema.json",
    ),
)

_LEARNING_PIPELINE_DEPENDENCIES = (
    ("learning-claim-evidence-bundle", ("learning-confirmed-legacy-reconstruction",)),
    ("learning-confirmed-evidence-cohort", ("learning-claim-evidence-bundle",)),
    ("public-check-summary", ("script-output-surfaces-check",)),
    ("learning-claim-unlock-review", ("learning-confirmed-evidence-cohort",)),
    ("learning-delta-scoreboard", ("learning-claim-unlock-review",)),
    ("learning-claim-activation-report", ("learning-delta-scoreboard",)),
    ("session-synopsis", ("learning-claim-activation-report",)),
    ("self-improvement-negative-lessons", ("session-synopsis",)),
    ("remediation-backlog", ("self-improvement-negative-lessons", "session-synopsis")),
    ("tmp-clean", ("tmp-json-clean",)),
)


def _assert_target_dependencies(
    case: unittest.TestCase,
    text: str,
    dependencies: tuple[tuple[str, tuple[str, ...]], ...],
) -> None:
    for target, expected_dependencies in dependencies:
        with case.subTest(target=target, surface="dependencies"):
            case.assertEqual(_target_dependencies(text, target), expected_dependencies)


class MakefileLearningStaticGateTests(unittest.TestCase):
    def test_learning_readiness_signoff_make_targets_are_explicit_operator_ux(
        self,
    ) -> None:
        text = _makefile_text()

        _assert_phony_targets(self, text, _LEARNING_READINESS_SIGNOFF_PHONY_TARGETS)
        _assert_assignment_values(self, text, _LEARNING_READINESS_SIGNOFF_ASSIGNMENTS)
        _assert_make_target_contracts(
            self,
            text,
            _LEARNING_READINESS_SIGNOFF_TARGET_CONTRACTS,
        )
        refresh_block = _target_block(text, "learning-readiness-signoff-refresh")
        self.assertNotIn("--accepted-by", refresh_block)

    def test_learning_claim_bundle_delta_scoreboard_and_tmp_clean_alias_are_explicit(
        self,
    ) -> None:
        text = _makefile_text()

        _assert_phony_targets(self, text, _LEARNING_PIPELINE_PHONY_TARGETS)
        _assert_assignment_values(self, text, _LEARNING_PIPELINE_ASSIGNMENTS)
        _assert_make_target_contracts(
            self,
            text,
            _LEARNING_PIPELINE_TARGET_CONTRACTS,
        )
        _assert_target_dependencies(self, text, _LEARNING_PIPELINE_DEPENDENCIES)
        bundle_block = _target_block(text, "learning-claim-evidence-bundle")
        self.assertNotIn(
            "$(MAKE) learning-confirmed-legacy-reconstruction", bundle_block
        )
        tmp_json_clean_block = _target_block(text, "tmp-json-clean")
        self.assertIn("find tmp -mindepth 1 -delete", tmp_json_clean_block)
        self.assertNotIn("goal-worktree-guard.json", tmp_json_clean_block)
