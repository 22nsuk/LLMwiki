from __future__ import annotations

import unittest
from pathlib import Path

import pytest

from tests.makefile_static_helpers import (
    _assert_assignment_exists,
    _assert_assignment_values,
    _assert_recipe_contains_tokens,
    _assert_target_depends_on,
    _assert_text_contains_tokens,
    _makefile_text,
    _recipe_lines,
    _target_block,
)

pytestmark = [
    pytest.mark.public,
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
    pytest.mark.schema_static_smoke,
]

DOCS_SELF_IMPROVEMENT_RUNTIME = Path("docs/self-improvement-runtime.md")


_AUTO_IMPROVE_GOAL_DEFAULT_ASSIGNMENTS = (
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
    (
        "GOAL_RUNTIME_CERTIFICATE_RUN_ID_GUARD_OUT",
        "tmp/goal-runtime-certificate-run-id-guard.json",
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
        "GOAL_RUNTIME_STALE_CLOSEOUT_OUT",
        "tmp/goal-runtime-stale-closeout.json",
    ),
    ("GOAL_RUNTIME_STALE_CLOSEOUT_APPLY", ""),
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
    ("GOAL_RUNTIME_LATEST_SUCCESSFUL_RUN_ARGS", ""),
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
    (
        "GOAL_MAINTAIN_UNTIL_BUDGET_FLAG",
        "$(if $(filter 1 true yes on,$(strip $(GOAL_MAINTAIN_UNTIL_BUDGET))),--maintain-until-budget,)",
    ),
    ("GOAL_MAINTENANCE_INTERVAL_SECONDS", "300"),
    ("GOAL_POST_PROMOTE_MAINTENANCE_CYCLES", "1"),
    ("GOAL_EXECUTOR", "codex_exec"),
    ("GOAL_ARTIFACT_CLASS", "system_mechanism"),
    ("GOAL_FINAL_STATUS", "stopped"),
    ("GOAL_RUN_LOG_DIR", "build/goal-runs"),
    ("MUTATION_MAX_PROPOSALS", ""),
)

_AUTO_IMPROVE_GOAL_EMPTY_ASSIGNMENTS = (
    "GOAL_WORKTREE_STRICT",
    "GOAL_ALLOW_LEARNING_UNCERTAIN",
    "GOAL_RUNTIME_CERTIFICATE_MODE",
    "GOAL_RUNTIME_CERTIFICATE_APPLY",
)

_AUTO_IMPROVE_GOAL_EMPTY_ASSIGNMENT_VALUES = tuple(
    (variable, "") for variable in _AUTO_IMPROVE_GOAL_EMPTY_ASSIGNMENTS
)

_AUTO_IMPROVE_LOOP_SHARED_TOKENS = (
    "ops.scripts.auto_improve_loop",
    "$(GOAL_MAINTAIN_UNTIL_BUDGET_FLAG)",
    "--maintenance-interval-seconds \"$(GOAL_MAINTENANCE_INTERVAL_SECONDS)\"",
    "--post-promote-maintenance-cycles \"$(GOAL_POST_PROMOTE_MAINTENANCE_CYCLES)\"",
)

_AUTO_IMPROVE_LOOP_LEGACY_MAINTAIN_FLAG = (
    "$(if $(GOAL_MAINTAIN_UNTIL_BUDGET),--maintain-until-budget,)"
)


def _assert_auto_improve_loop_common_tokens(
    test: unittest.TestCase,
    command: str,
) -> None:
    _assert_text_contains_tokens(
        test,
        command,
        _AUTO_IMPROVE_LOOP_SHARED_TOKENS,
        surface="auto_improve_loop_command",
    )
    test.assertNotIn(_AUTO_IMPROVE_LOOP_LEGACY_MAINTAIN_FLAG, command)


class MakefileAutoImproveGoalStaticGateTests(unittest.TestCase):
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

    def test_auto_improve_goal_variables_defaults_and_loop_commands(self) -> None:
        text = _makefile_text()

        _assert_assignment_values(self, text, _AUTO_IMPROVE_GOAL_DEFAULT_ASSIGNMENTS)
        _assert_assignment_values(self, text, _AUTO_IMPROVE_GOAL_EMPTY_ASSIGNMENT_VALUES)
        run_command = _assert_assignment_exists(self, text, "GOAL_RUN_COMMAND")
        _assert_auto_improve_loop_common_tokens(self, run_command)
        _assert_text_contains_tokens(
            self,
            run_command,
            (
                "--session-id \"$(GOAL_RUN_ID)\"",
                "--goal-contract \"$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)\"",
                "--executor \"$(GOAL_EXECUTOR)\"",
                "--class \"$(GOAL_ARTIFACT_CLASS)\"",
                "$(if $(GOAL_ALLOW_LEARNING_UNCERTAIN),--allow-learning-uncertain,)",
            ),
            surface="goal_run_command",
        )
        resume_command = _assert_assignment_exists(self, text, "GOAL_RESUME_COMMAND")
        _assert_auto_improve_loop_common_tokens(self, resume_command)
        _assert_text_contains_tokens(
            self,
            resume_command,
            (
                "--resume-session \"$(GOAL_RUN_ID)\"",
                "--goal-contract \"$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)\"",
                "--max-minutes \"$(GOAL_MAX_MINUTES)\"",
                "--max-proposals \"$(GOAL_MAX_PROPOSALS)\"",
                "--max-consecutive-failures \"$(GOAL_MAX_CONSECUTIVE_FAILURES)\"",
            ),
            surface="goal_resume_command",
        )
        maintenance_action_command = _assert_assignment_exists(
            self,
            text,
            "GOAL_MAINTENANCE_ACTION_NEXT_MAX_PROPOSALS",
        )
        _assert_text_contains_tokens(
            self,
            maintenance_action_command,
            (
                "ops.scripts.auto_improve_loop",
                "--resume-session \"$(GOAL_RUN_ID)\"",
                "--print-maintenance-action-next-max-proposals",
                "--maintenance-action-plan-out \"$(GOAL_MAINTENANCE_ACTION_PLAN_OUT)\"",
            ),
            surface="goal_maintenance_action_command",
        )
        mutation_proposal_recipe = _target_block(text, "mutation-proposal")
        self.assertIn(
            '$(if $(MUTATION_MAX_PROPOSALS),--max-proposals "$(MUTATION_MAX_PROPOSALS)",)',
            mutation_proposal_recipe,
        )

    def test_auto_improve_goal_phony_targets_and_dependencies(self) -> None:
        text = _makefile_text()

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
            "goal-runtime-stale-closeout",
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
            "goal-runtime-latest-successful-run-id",
            "goal-runtime-publish-latest-successful-evidence",
            "long-run-preflight-clean",
            "auto-improve-goal-preflight",
            "auto-improve-goal-run",
            "auto-improve-goal-status",
            "auto-improve-goal-resume",
            "auto-improve-goal-maintenance-action",
            "auto-improve-goal-finalize",
            "auto-improve-goal-run-artifacts",
            "goal-runtime-status-finalize",
            "goal-runtime-certificate-report",
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
        _assert_target_depends_on(self, text, "goal-runtime-status-finalize", "auto-improve-goal-contract")
        self.assertNotIn(
            "auto-improve-goal-contract",
            _target_block(text, "goal-runtime-certificate-report").splitlines()[0],
        )
        self.assertNotIn(
            "auto-improve-goal-contract",
            _target_block(text, "goal-runtime-certificate").splitlines()[0],
        )
        self.assertNotIn(
            "auto-improve-goal-status",
            _target_block(text, "goal-runtime-certificate").splitlines()[0],
        )
        _assert_target_depends_on(self, text, "goal-worktree-guard", "auto-improve-goal-preflight")

    def test_auto_improve_goal_admission_ordering_recipes(self) -> None:
        text = _makefile_text()

        admission_block = _target_block(text, "goal-runtime-run-admission")
        self.assertIn(
            "$(if $(GOAL_ALLOW_LEARNING_UNCERTAIN),--allow-learning-uncertain,)",
            admission_block,
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-run-admission-converge",
            (
                '$(MAKE) refresh-generated-core MUTATION_MAX_PROPOSALS="$(GOAL_MAX_PROPOSALS)"',
                "$(MAKE) release-smoke-fast-refresh-check",
                "$(MAKE) goal-runtime-pre-run-cleanup",
                "$(MAKE) mechanism-review",
                "$(MAKE) goal-runtime-quarantine-preflight",
                "$(MAKE) goal-runtime-stale-closeout",
                "$(MAKE) goal-runtime-publish-local-evidence",
                "$(MAKE) goal-runtime-fixed-point-check",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-run-admission-local-refresh",
            (
                '$(MAKE) refresh-generated-core MUTATION_MAX_PROPOSALS="$(GOAL_MAX_PROPOSALS)"',
                "$(MAKE) release-smoke-fast-refresh-check",
                "$(MAKE) goal-runtime-pre-run-cleanup",
                "$(MAKE) mechanism-review",
                "$(MAKE) goal-runtime-quarantine-preflight",
                "$(MAKE) goal-runtime-stale-closeout",
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
                '$(MAKE) refresh-generated-core MUTATION_MAX_PROPOSALS="$(GOAL_MAX_PROPOSALS)"',
                "$(MAKE) goal-runtime-quarantine-preflight",
                "$(MAKE) goal-runtime-stale-closeout",
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
        settle_recipe = _recipe_lines(text, "goal-runtime-between-run-settle")
        self.assertLess(
            settle_recipe.index(
                '$(MAKE) refresh-generated-core MUTATION_MAX_PROPOSALS="$(GOAL_MAX_PROPOSALS)"'
            ),
            settle_recipe.index("$(MAKE) goal-runtime-quarantine-preflight"),
        )
        self.assertLess(
            settle_recipe.index("$(MAKE) goal-runtime-quarantine-preflight"),
            settle_recipe.index("$(MAKE) goal-runtime-stale-closeout"),
        )
        self.assertLess(
            settle_recipe.index("$(MAKE) goal-runtime-stale-closeout"),
            settle_recipe.index("$(MAKE) goal-runtime-pre-run-cleanup"),
        )
        for admission_target in (
            "goal-runtime-run-admission-converge",
            "goal-runtime-run-admission-local-refresh",
        ):
            admission_recipe = _recipe_lines(text, admission_target)
            self.assertLess(
                admission_recipe.index(
                    '$(MAKE) refresh-generated-core MUTATION_MAX_PROPOSALS="$(GOAL_MAX_PROPOSALS)"'
                ),
                admission_recipe.index("$(MAKE) goal-runtime-pre-run-cleanup"),
            )
            self.assertLess(
                admission_recipe.index("$(MAKE) goal-runtime-pre-run-cleanup"),
                admission_recipe.index("$(MAKE) mechanism-review"),
            )
            self.assertLess(
                admission_recipe.index("$(MAKE) mechanism-review"),
                admission_recipe.index("$(MAKE) goal-runtime-quarantine-preflight"),
            )

    def test_auto_improve_goal_admission_contract_and_status_recipes(self) -> None:
        text = _makefile_text()

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

    def test_auto_improve_goal_lock_preflight_and_cleanup_recipes(self) -> None:
        text = _makefile_text()

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
                "$(MAKE) goal-runtime-certificate-run-id-guard",
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
            "goal-runtime-stale-closeout",
            (
                "ops.scripts.goal_runtime_stale_closeout",
                "--out \"$(GOAL_RUNTIME_STALE_CLOSEOUT_OUT)\"",
                "$(if $(GOAL_RUNTIME_STALE_CLOSEOUT_APPLY),--apply,)",
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

    def test_auto_improve_goal_local_evidence_report_recipes(self) -> None:
        text = _makefile_text()

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

    def test_goal_runtime_reconcile_and_closeout_candidate_recipes(self) -> None:
        text = _makefile_text()

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

    def test_goal_runtime_closeout_publish_and_dispatch_recipes(self) -> None:
        text = _makefile_text()

        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-closeout-publish-script-output-surfaces",
            (
                "ops.scripts.script_output_surfaces",
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
                "printf '%s\\n' \"$$targets\" | while IFS= read -r target; do \\",
                "[ -n \"$$target\" ] || continue; \\",
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
                "printf '%s\\n' \"$$targets\" | while IFS= read -r target; do \\",
                "[ -n \"$$target\" ] || continue; \\",
                "$(MAKE) $$target",
                "GOAL_RUNTIME_CLOSEOUT_BUDGET=full",
            ),
        )
        self.assertNotIn("for target in $$(", _target_block(text, "goal-runtime-closeout"))
        self.assertNotIn("for target in $$(", _target_block(text, "goal-runtime-closeout-full"))
        self.assertNotIn(
            "TEST_EXECUTION_SUMMARY_FULL_MODE=refresh",
            _target_block(text, "goal-runtime-closeout"),
        )

    def test_goal_runtime_local_evidence_refresh_and_publish_recipes(self) -> None:
        text = _makefile_text()

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
        self.assertIn(
            "$(MAKE) goal-runtime-certificate-run-id-guard",
            _recipe_lines(text, "goal-runtime-publish-local-evidence")[0],
        )
        self.assertIn(
            "$(MAKE) goal-runtime-local-evidence-converge",
            _recipe_lines(text, "goal-runtime-publish-local-evidence")[1],
        )

    def test_auto_improve_goal_runner_finalize_and_certificate_recipes(self) -> None:
        text = _makefile_text()

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
            "goal-runtime-status-finalize",
            (
                "$(MAKE) goal-runtime-certificate-run-id-guard",
                "$(MAKE) auto-improve-goal-status",
                "--candidate \"$(GOAL_ACTIVE_RUN_STATUS_OUT)\"",
                "--out \"$(GOAL_RUN_STATUS_OUT)\"",
                "ops/schemas/goal-run-status.schema.json",
                "--expected-artifact-kind goal_run_status",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-certificate-report",
            (
                "$(MAKE) goal-runtime-certificate-run-id-guard",
                "ops.scripts.goal_runtime_certificate_report",
                "--goal-contract \"$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)\"",
                "--status-report \"$(GOAL_ACTIVE_RUN_STATUS_OUT)\"",
                "--out \"$(GOAL_RUNTIME_CERTIFICATE_CANDIDATE_OUT)\"",
                "$(if $(GOAL_RUNTIME_CERTIFICATE_MODE),--runtime-mode \"$(GOAL_RUNTIME_CERTIFICATE_MODE)\",)",
                "$(if $(GOAL_RUNTIME_CERTIFICATE_APPLY),--apply,)",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-certificate",
            (
                "$(MAKE) goal-runtime-certificate-report",
                "--candidate \"$(GOAL_RUNTIME_CERTIFICATE_CANDIDATE_OUT)\"",
                "--out \"$(GOAL_RUNTIME_CERTIFICATE_OUT)\"",
                "ops/schemas/goal-runtime-certificate.schema.json",
                "--expected-artifact-kind goal_runtime_certificate",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-certificate-run-id-guard",
            (
                "ops.scripts.goal_runtime_certificate_run_id_guard",
                "--goal-run-id \"$(GOAL_RUN_ID)\"",
                "--goal-run-id-origin \"$(origin GOAL_RUN_ID)\"",
                "--goal-run-status \"$(GOAL_RUN_STATUS_OUT)\"",
                "--goal-runtime-certificate \"$(GOAL_RUNTIME_CERTIFICATE_OUT)\"",
                "--out \"$(GOAL_RUNTIME_CERTIFICATE_RUN_ID_GUARD_OUT)\"",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-latest-successful-run-id",
            (
                "ops.scripts.mechanism.goal_runtime_latest_successful_run",
                "--vault \"$(VAULT)\"",
                "$(GOAL_RUNTIME_LATEST_SUCCESSFUL_RUN_ARGS)",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "goal-runtime-publish-latest-successful-evidence",
            (
                "ops.scripts.mechanism.goal_runtime_latest_successful_run",
                "$(MAKE) goal-runtime-status-finalize GOAL_RUN_ID=\"$$run_id\"",
                "$(MAKE) goal-runtime-publish-local-evidence GOAL_RUN_ID=\"$$run_id\"",
                "$(MAKE) goal-runtime-certificate GOAL_RUN_ID=\"$$run_id\"",
            ),
        )
        status_finalize_recipe = _recipe_lines(text, "goal-runtime-status-finalize")
        self.assertEqual(status_finalize_recipe[0], "$(MAKE) goal-runtime-certificate-run-id-guard")
        self.assertIn("$(MAKE) auto-improve-goal-status", status_finalize_recipe[1])
        self.assertLess(
            status_finalize_recipe[1].index("$(MAKE) auto-improve-goal-status"),
            status_finalize_recipe[1].index('--candidate "$(GOAL_ACTIVE_RUN_STATUS_OUT)"'),
        )
        certificate_report_recipe = _recipe_lines(text, "goal-runtime-certificate-report")
        self.assertEqual(
            certificate_report_recipe[0],
            "$(MAKE) goal-runtime-certificate-run-id-guard",
        )
        self.assertIn("ops.scripts.goal_runtime_certificate_report", certificate_report_recipe[1])
        certificate_recipe = _recipe_lines(text, "goal-runtime-certificate")
        self.assertIn("$(MAKE) goal-runtime-certificate-report", certificate_recipe[0])
        self.assertNotIn("auto-improve-goal-status", _target_block(text, "goal-runtime-certificate"))
        self.assertNotIn("$(GOAL_RUN_STATUS_OUT)", _target_block(text, "goal-runtime-certificate"))

    def test_goal_runtime_certificate_status_write_contract_is_split_and_documented(self) -> None:
        text = _makefile_text()
        docs_text = DOCS_SELF_IMPROVEMENT_RUNTIME.read_text(encoding="utf-8")
        status_finalize_recipe = _recipe_lines(text, "goal-runtime-status-finalize")
        certificate_recipe = _recipe_lines(text, "goal-runtime-certificate")

        self.assertIn("$(MAKE) auto-improve-goal-status", status_finalize_recipe[1])
        self.assertIn('--candidate "$(GOAL_ACTIVE_RUN_STATUS_OUT)"', status_finalize_recipe[1])
        self.assertIn('--out "$(GOAL_RUN_STATUS_OUT)"', status_finalize_recipe[1])
        self.assertNotIn("auto-improve-goal-status", "\n".join(certificate_recipe))
        self.assertNotIn("$(GOAL_RUN_STATUS_OUT)", "\n".join(certificate_recipe))
        for token in (
            "goal-runtime-status-finalize",
            "goal-runtime-certificate-report",
            "auto-improve-goal-status",
            "GOAL_RUN_ID",
            "GOAL_COMPLETED_AT",
            "completed_at",
        ):
            with self.subTest(surface="docs/self-improvement-runtime.md", token=token):
                self.assertIn(token, docs_text)
