from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.mechanism.mutation_proposal import main as mutation_proposal_main
from ops.scripts.mechanism.mutation_proposal_runtime import (
    MUTATION_PROPOSAL_SOURCE_PATHS,
    build_report,
)
from tests.cli_test_runtime import invoke_cli_main
from tests.mutation_proposal_test_runtime import (
    ENVELOPE_SCHEMA_PATH,
    fixed_context,
    mechanism_review_report,
    seed_vault,
    shadow_priority_diagnostics,
    write_json,
)


class MutationProposalBuildReportTest(unittest.TestCase):
    def test_source_paths_include_loader_dependency(self) -> None:
        self.assertEqual(
            MUTATION_PROPOSAL_SOURCE_PATHS,
            [
                "ops/scripts/mechanism/mutation_proposal_runtime.py",
                "ops/scripts/mechanism/_mutation_proposal_next_run_repair_runtime.py",
                "ops/scripts/mechanism/_mutation_proposal_render_runtime.py",
                "ops/scripts/mechanism/mutation_proposal_bootstrap_runtime.py",
                "ops/scripts/mechanism/mutation_proposal_candidate_runtime.py",
                "ops/scripts/mechanism/mutation_proposal_loader_runtime.py",
                "ops/scripts/mechanism/mutation_proposal_promotion_runtime.py",
                "ops/scripts/mechanism/mutation_proposal_queue_runtime.py",
                "ops/scripts/mechanism/mutation_proposal_recent_log_overlap_runtime.py",
                "ops/scripts/mechanism/auto_improve_next_run_decision_runtime.py",
                "ops/scripts/mechanism/current_target_path_runtime.py",
                "ops/scripts/mechanism/next_run_repair_queue_runtime.py",
                "ops/scripts/mechanism/noop_repair_classifier_runtime.py",
                "ops/scripts/mechanism/structural_complexity_scope_runtime.py",
            ],
        )
        repo_root = Path(__file__).resolve().parents[1]
        for rel_path in MUTATION_PROPOSAL_SOURCE_PATHS:
            self.assertTrue((repo_root / rel_path).is_file(), rel_path)

    def test_cli_writes_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n## [2026-04-14 00:00] decision | prior experiment\n",
                encoding="utf-8",
            )

            completed = invoke_cli_main(
                mutation_proposal_main,
                [
                    "--vault",
                    str(vault),
                    "--out",
                    "reports/mutation/proposals.json",
                ],
                cwd=launcher,
            )
            self.assertEqual(completed.exit_code, 0, msg=completed.stderr or completed.stdout)

            report_path = vault / "reports" / "mutation" / "proposals.json"
            self.assertTrue(report_path.exists())
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["$schema"], "ops/schemas/mutation-proposals.schema.json")
            self.assertEqual(payload["status"], "pass")
    def test_build_report_emits_ranked_proposals_and_respects_log_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n## [2026-04-14 00:00] decision | prior experiment\n\n### Artifacts\n- `ops/scripts/wiki_lint.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            schema = load_schema(vault / "ops" / "schemas" / "mutation-proposals.schema.json")
            envelope_schema = load_schema(ENVELOPE_SCHEMA_PATH)

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(validate_with_schema(report, envelope_schema), [])
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["source_candidates_read"], 3)
            self.assertEqual(report["summary"]["proposals_emitted"], 3)
            self.assertEqual(report["summary"]["blocked_proposals"], 1)
            self.assertEqual(
                report["summary"]["queue_pressure_summary"],
                "session unavailable | self_mod_stability 2 proposals, 1 blocked; contract_regression_signals 1 proposal",
            )
            self.assertEqual(report["diagnostics"]["skipped_candidates"], [])
            self.assertEqual(
                report["diagnostics"]["evidence_gaps"],
                [
                    "session_calibration.status=no_session_context",
                    "outcome_metrics_calibration.status=missing_outcome_metrics",
                ],
            )
            self.assertEqual(report["diagnostics"]["empty_queue_blockers"], [])
            self.assertEqual(
                report["diagnostics"]["family_session_calibration"],
                {
                    "enabled": True,
                    "status": "no_session_context",
                    "proposal_count": 3,
                    "blocked_proposal_count": 1,
                    "by_family": [
                        {
                            "family": "contract_regression_signals",
                            "proposal_count": 1,
                            "blocked_proposal_count": 0,
                            "session_priority_delta": 0,
                            "boosted_candidates": 0,
                            "lowered_candidates": 0,
                            "unchanged_candidates": 1,
                            "validation_blocked_sessions": 0,
                            "review_blocked_sessions": 0,
                            "mutation_failed_sessions": 0,
                            "validator_dispatch_sessions": 0,
                            "reviewer_dispatch_sessions": 0,
                            "high_risk_routing_sessions": 0,
                        },
                        {
                            "family": "self_mod_stability",
                            "proposal_count": 2,
                            "blocked_proposal_count": 1,
                            "session_priority_delta": 0,
                            "boosted_candidates": 0,
                            "lowered_candidates": 0,
                            "unchanged_candidates": 2,
                            "validation_blocked_sessions": 0,
                            "review_blocked_sessions": 0,
                            "mutation_failed_sessions": 0,
                            "validator_dispatch_sessions": 0,
                            "reviewer_dispatch_sessions": 0,
                            "high_risk_routing_sessions": 0,
                        },
                    ],
                },
            )
            self.assertEqual(
                report["diagnostics"]["queue_selection"],
                {
                    "available_proposal_count": 3,
                    "selected_proposal_count": 3,
                    "selection_mode": "standard",
                    "repair_priority_suppressed_count": 0,
                    "runnable_available_count": 2,
                    "blocked_available_count": 1,
                    "selected_runnable_count": 2,
                    "selected_blocked_count": 1,
                    "blocked_reason_counts": [
                        {"reason": "recent_log_overlap", "count": 1}
                    ],
                },
            )
            self.assertEqual(
                report["diagnostics"]["recent_log_overlap"],
                {
                    "dedupe_window": 5,
                    "max_age_days": 7,
                    "section_ordering": "timestamp",
                    "scanned_log_headings": [
                        "[2026-04-14 00:00] decision | prior experiment"
                    ],
                    "matches": [
                        {
                            "proposal_id": "branch_growth_without_test_growth__wiki-lint",
                            "source_candidate_id": "mechanism_branch_growth_without_test_growth_candidate__wiki-lint",
                            "matched_marker": "ops/scripts/wiki_lint.py",
                            "matched_log_heading": "[2026-04-14 00:00] decision | prior experiment",
                            "unblock_condition": (
                                "advance chronology beyond the configured dedupe window "
                                "or max age window, or rotate to a non-overlapping target set"
                            ),
                        }
                    ],
                },
            )

            proposals_by_source = {
                proposal["source_candidate_type"]: proposal for proposal in report["proposals"]
            }
            self.assertEqual(
                proposals_by_source["mechanism_eval_stagnation_candidate"]["failure_mode"],
                "repeated_discard_runs",
            )
            self.assertEqual(
                proposals_by_source["mechanism_eval_stagnation_candidate"]["metrics_triggered"],
                ["repeated_discard_runs"],
            )
            self.assertEqual(
                proposals_by_source["mechanism_eval_stagnation_candidate"]["run_ids"],
                ["run-a", "run-b"],
            )
            self.assertEqual(
                proposals_by_source["mechanism_branch_growth_without_test_growth_candidate"]["blocked_by"],
                ["recent_log_overlap"],
            )
            self.assertEqual(
                proposals_by_source["mechanism_branch_growth_without_test_growth_candidate"]["priority_breakdown"][
                    "recent_log_overlap_penalty"
                ],
                -15,
            )
            self.assertEqual(
                proposals_by_source["mechanism_high_complexity_low_test_pressure_candidate"]["failure_mode"],
                "high_complexity_low_test_pressure",
            )
            self.assertEqual(
                proposals_by_source["mechanism_eval_stagnation_candidate"]["must_change_tests"],
                ["tests/test_promotion_gate.py"],
            )
            self.assertEqual(
                proposals_by_source["mechanism_eval_stagnation_candidate"]["must_change_budget_signal"],
                {
                    "signal": "outcome_metrics.moving_averages.discard",
                    "expected_change": "decrease_after_finalized_attempt",
                },
            )
            self.assertTrue(
                proposals_by_source["mechanism_eval_stagnation_candidate"]["must_not_expand_apply_roots"]
            )
            self.assertTrue(
                proposals_by_source["mechanism_eval_stagnation_candidate"]["must_not_increase_untyped_surface"]
            )
            self.assertGreater(
                proposals_by_source["mechanism_high_complexity_low_test_pressure_candidate"][
                    "blast_radius_score"
                ],
                0,
            )
            priorities = [proposal["priority"] for proposal in report["proposals"]]
            self.assertEqual(priorities, sorted(priorities, reverse=True))
    def test_max_proposals_selects_runnable_before_blocked_proposals(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            report = mechanism_review_report()
            report["candidates"][0]["priority"] = 100
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n## [2026-04-14 00:00] decision | prior experiment\n\n### Artifacts\n- `ops/scripts/promotion_gate.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(
                vault,
                policy,
                policy_path,
                max_proposals=1,
                context=fixed_context(policy),
            )
            schema = load_schema(vault / "ops" / "schemas" / "mutation-proposals.schema.json")

            self.assertEqual(validate_with_schema(proposal_report, schema), [])
            self.assertEqual(proposal_report["status"], "pass")
            self.assertEqual(proposal_report["summary"]["proposals_emitted"], 1)
            self.assertEqual(proposal_report["summary"]["blocked_proposals"], 0)
            self.assertEqual(
                [proposal["source_candidate_type"] for proposal in proposal_report["proposals"]],
                ["mechanism_branch_growth_without_test_growth_candidate"],
            )
            self.assertEqual(proposal_report["proposals"][0]["blocked_by"], [])
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"],
                {
                    "available_proposal_count": 3,
                    "selected_proposal_count": 1,
                    "selection_mode": "standard",
                    "repair_priority_suppressed_count": 0,
                    "runnable_available_count": 2,
                    "blocked_available_count": 1,
                    "selected_runnable_count": 1,
                    "selected_blocked_count": 0,
                    "blocked_reason_counts": [
                        {"reason": "recent_log_overlap", "count": 1}
                    ],
                },
            )
            self.assertEqual(proposal_report["diagnostics"]["recent_log_overlap"]["dedupe_window"], 5)
            self.assertEqual(
                proposal_report["diagnostics"]["recent_log_overlap"]["matches"][0]["matched_marker"],
                "ops/scripts/promotion_gate.py",
            )
    def test_recent_log_overlap_rotation_blocks_after_single_unresolved_queue_unblock_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "outcome-metrics.json",
                {
                    "recent_attempts": [
                        {
                            "run_id": "auto-improve-trial-rerun-1",
                            "proposal_id": "recent_log_overlap_queue_blocked__mutation-proposal-runtime",
                            "outcome": "mutation_failed",
                            "decision": "HOLD",
                        },
                    ],
                },
            )
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n"
                "## [2026-04-14 00:00] decision | prior overlapping experiments\n\n"
                "### Artifacts\n"
                "- `ops/scripts/promotion_gate.py`\n"
                "- `ops/scripts/wiki_lint.py`\n"
                "- `ops/scripts/mechanism_assess.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            schema = load_schema(vault / "ops" / "schemas" / "mutation-proposals.schema.json")

            self.assertEqual(validate_with_schema(proposal_report, schema), [])
            self.assertEqual(proposal_report["status"], "pass")
            self.assertEqual(proposal_report["summary"]["proposals_emitted"], 4)
            self.assertEqual(proposal_report["summary"]["blocked_proposals"], 3)
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"][
                    "blocked_reason_counts"
                ],
                [
                    {"reason": "recent_log_overlap", "count": 3},
                ],
            )

            rotation = proposal_report["proposals"][0]
            self.assertEqual(rotation["failure_mode"], "recent_log_overlap_queue_blocked")
            self.assertEqual(
                rotation["proposal_id"],
                "recent_log_overlap_queue_blocked__mechanism-run-validation-runtime",
            )
            self.assertEqual(
                rotation["primary_targets"],
                ["ops/scripts/mechanism/mechanism_run_validation_runtime.py"],
            )
            self.assertEqual(rotation["blocked_by"], [])
    def test_rotated_queue_unblock_suppresses_superseded_noop_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "outcome-metrics.json",
                {
                    "recent_attempts": [
                        {
                            "run_id": "auto-improve-trial-rerun-1",
                            "proposal_id": "recent_log_overlap_queue_blocked__mutation-proposal-runtime",
                            "outcome": "mutation_failed",
                            "decision": "HOLD",
                        },
                    ],
                },
            )
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:queue-unblock-noop",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": "auto-improve-trial-rerun-1",
                            "proposal_id": "recent_log_overlap_queue_blocked__mutation-proposal-runtime",
                            "source_candidate_id": "recent_log_overlap_queue_unblock__mutation-proposal-runtime",
                            "target_proposal_id": (
                                "next_run_failure_repair__mutation-proposal-runtime__mutation-failed"
                            ),
                            "proposal_family": "queue_unblock",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "mutation_failed",
                            "blocking_role": "worker",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "old queue-unblock no-op should not outrank the current rotation target",
                            "quarantined_source_proposal": True,
                            "primary_targets": [
                                "ops/scripts/mechanism/mutation_proposal_runtime.py"
                            ],
                            "supporting_targets": ["ops/script-output-surfaces.json"],
                            "must_change_tests": [
                                "tests/test_mutation_proposal.py",
                                "tests/test_report_generation_smoke.py",
                            ],
                            "evidence_paths": [
                                "runs/auto-improve-trial-rerun-1/mutation-command.stderr.txt"
                            ],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n"
                "## [2026-04-14 00:00] decision | prior overlapping experiments\n\n"
                "### Artifacts\n"
                "- `ops/scripts/promotion_gate.py`\n"
                "- `ops/scripts/wiki_lint.py`\n"
                "- `ops/scripts/mechanism_assess.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))

            self.assertEqual(proposal_report["summary"]["next_run_repair_proposals"], 0)
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"][
                    "open_carry_forward_decisions"
                ],
                0,
            )
            rotation = proposal_report["proposals"][0]
            self.assertEqual(
                rotation["proposal_id"],
                "recent_log_overlap_queue_blocked__mechanism-run-validation-runtime",
            )
            self.assertEqual(rotation["blocked_by"], [])

    def test_blocked_queue_unblock_rotation_does_not_suppress_next_run_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "outcome-metrics.json",
                {
                    "recent_attempts": [
                        {
                            "run_id": "mutation-proposal-rerun",
                            "proposal_id": "recent_log_overlap_queue_blocked__mutation-proposal-runtime",
                            "outcome": "validation_blocked",
                            "decision": "HOLD",
                        },
                        {
                            "run_id": "mechanism-validation-rerun",
                            "proposal_id": (
                                "recent_log_overlap_queue_blocked__"
                                "mechanism-run-validation-runtime"
                            ),
                            "outcome": "validation_blocked",
                            "decision": "HOLD",
                        },
                    ],
                },
            )
            source_run_id = "mechanism-validation-rerun"
            run_dir = vault / "runs" / source_run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(run_dir / "run-telemetry.json", {"status": "blocked"})
            write_json(run_dir / "validator-executor-report.json", {"status": "fail"})
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:mechanism-validation-rerun:validation",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": source_run_id,
                            "proposal_id": (
                                "recent_log_overlap_queue_blocked__"
                                "mechanism-run-validation-runtime"
                            ),
                            "source_candidate_id": (
                                "recent_log_overlap_queue_unblock__"
                                "mechanism-run-validation-runtime"
                            ),
                            "target_proposal_id": (
                                "next_run_failure_repair__mechanism-run-validation-runtime__"
                                "validation-blocked"
                            ),
                            "proposal_family": "queue_unblock",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "validation_blocked",
                            "blocking_role": "validator",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "blocked rotation should not hide repair work",
                            "quarantined_source_proposal": True,
                            "primary_targets": [
                                "ops/scripts/mechanism/mechanism_run_validation_runtime.py"
                            ],
                            "supporting_targets": ["ops/script-output-surfaces.json"],
                            "must_change_tests": [
                                "tests/test_mechanism_run_validation_runtime.py"
                            ],
                            "evidence_paths": [
                                f"runs/{source_run_id}/run-telemetry.json",
                                f"runs/{source_run_id}/validator-executor-report.json",
                            ],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n"
                "## [2026-04-14 00:00] decision | prior overlapping experiments\n\n"
                "### Artifacts\n"
                "- `ops/scripts/promotion_gate.py`\n"
                "- `ops/scripts/wiki_lint.py`\n"
                "- `ops/scripts/mechanism_assess.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))

            self.assertEqual(proposal_report["status"], "pass")
            self.assertEqual(proposal_report["summary"]["next_run_repair_proposals"], 1)
            self.assertEqual(
                [proposal["failure_mode"] for proposal in proposal_report["proposals"]],
                ["next_run_failure_repair"],
            )
            self.assertEqual(
                proposal_report["proposals"][0]["proposal_id"],
                (
                    "next_run_failure_repair__mechanism-run-validation-runtime__"
                    "validation-blocked"
                ),
            )
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"]["selection_mode"],
                "carry_forward_repair_only",
            )
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"]["blocked_reason_counts"],
                [
                    {"reason": "recent_log_overlap", "count": 3},
                    {"reason": "recent_outcome_rework", "count": 1},
                ],
            )

    def test_recent_log_overlap_rotation_blocks_after_repeated_recent_outcome_rework(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "outcome-metrics.json",
                {
                    "recent_attempts": [
                        {
                            "run_id": "auto-improve-trial-rerun-2",
                            "proposal_id": "recent_log_overlap_queue_blocked__mutation-proposal-runtime",
                            "outcome": "validation_blocked",
                            "decision": "HOLD",
                        },
                        {
                            "run_id": "auto-improve-trial-rerun-1",
                            "proposal_id": "recent_log_overlap_queue_blocked__mutation-proposal-runtime",
                            "outcome": "discarded",
                            "decision": "DISCARD",
                        },
                        {
                            "run_id": "auto-improve-trial-rerun-3",
                            "proposal_id": "recent_log_overlap_queue_blocked__mechanism-run-validation-runtime",
                            "outcome": "mutation_failed",
                            "decision": "HOLD",
                        },
                    ],
                },
            )
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n"
                "## [2026-04-14 00:00] decision | prior overlapping experiments\n\n"
                "### Artifacts\n"
                "- `ops/scripts/promotion_gate.py`\n"
                "- `ops/scripts/wiki_lint.py`\n"
                "- `ops/scripts/mechanism_assess.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            schema = load_schema(vault / "ops" / "schemas" / "mutation-proposals.schema.json")

            self.assertEqual(validate_with_schema(proposal_report, schema), [])
            self.assertEqual(proposal_report["status"], "attention")
            self.assertEqual(proposal_report["summary"]["proposals_emitted"], 4)
            self.assertEqual(proposal_report["summary"]["blocked_proposals"], 4)
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"],
                {
                    "available_proposal_count": 4,
                    "selected_proposal_count": 4,
                    "selection_mode": "standard",
                    "repair_priority_suppressed_count": 0,
                    "runnable_available_count": 0,
                    "blocked_available_count": 4,
                    "selected_runnable_count": 0,
                    "selected_blocked_count": 4,
                    "blocked_reason_counts": [
                        {"reason": "recent_log_overlap", "count": 3},
                        {"reason": "recent_outcome_rework", "count": 1},
                    ],
                },
            )

            rotation = proposal_report["proposals"][0]
            self.assertEqual(rotation["failure_mode"], "recent_log_overlap_queue_blocked")
            self.assertEqual(rotation["blocked_by"], ["recent_outcome_rework"])
    def test_cross_target_promote_does_not_clear_queue_unblock_rework(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "outcome-metrics.json",
                {
                    "recent_attempts": [
                        {
                            "run_id": "mechanism-validation-repair",
                            "proposal_id": (
                                "next_run_failure_repair__mechanism-run-validation-runtime__"
                                "review-blocked"
                            ),
                            "source_candidate_id": (
                                "next-run-decision:"
                                "mechanism-validation-source:"
                                "abc123"
                            ),
                            "outcome": "promoted",
                            "decision": "PROMOTE",
                            "primary_targets": [
                                "ops/scripts/mechanism/mechanism_run_validation_runtime.py"
                            ],
                        },
                        {
                            "run_id": "mutation-proposal-rerun-2",
                            "proposal_id": (
                                "recent_log_overlap_queue_blocked__mutation-proposal-runtime"
                            ),
                            "outcome": "validation_blocked",
                            "decision": "HOLD",
                            "primary_targets": [
                                "ops/scripts/mechanism/mutation_proposal_runtime.py"
                            ],
                        },
                        {
                            "run_id": "mechanism-validation-rerun-2",
                            "proposal_id": (
                                "recent_log_overlap_queue_blocked__"
                                "mechanism-run-validation-runtime"
                            ),
                            "outcome": "validation_blocked",
                            "decision": "HOLD",
                            "primary_targets": [
                                "ops/scripts/mechanism/mechanism_run_validation_runtime.py"
                            ],
                        },
                    ],
                },
            )
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n"
                "## [2026-04-14 00:00] decision | prior overlapping experiments\n\n"
                "### Artifacts\n"
                "- `ops/scripts/promotion_gate.py`\n"
                "- `ops/scripts/wiki_lint.py`\n"
                "- `ops/scripts/mechanism_assess.py`\n"
                "- `ops/scripts/mechanism/mechanism_run_validation_runtime.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))

            rotation = proposal_report["proposals"][0]
            self.assertEqual(
                rotation["proposal_id"],
                "recent_log_overlap_queue_blocked__mutation-proposal-runtime",
            )
            self.assertEqual(rotation["blocked_by"], ["recent_outcome_rework"])
    def test_recent_log_overlap_rotation_scans_full_scope_when_preferred_targets_block(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            for rel_path in (
                "ops/scripts/mechanism/mutation_proposal_runtime.py",
                "ops/scripts/mechanism/mechanism_run_validation_runtime.py",
                "ops/scripts/mechanism/auto_improve_queue_runtime.py",
            ):
                (vault / rel_path).parent.mkdir(parents=True, exist_ok=True)
                (vault / rel_path).write_text("# fixture\n", encoding="utf-8")
            (vault / "tests" / "test_auto_improve_queue_runtime.py").write_text(
                "def test_placeholder():\n    assert True\n",
                encoding="utf-8",
            )
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "outcome-metrics.json",
                {
                    "recent_attempts": [
                        {
                            "run_id": "mutation-proposal-rerun-2",
                            "proposal_id": (
                                "recent_log_overlap_queue_blocked__mutation-proposal-runtime"
                            ),
                            "outcome": "validation_blocked",
                            "decision": "HOLD",
                        },
                        {
                            "run_id": "mechanism-validation-rerun-2",
                            "proposal_id": (
                                "recent_log_overlap_queue_blocked__"
                                "mechanism-run-validation-runtime"
                            ),
                            "outcome": "validation_blocked",
                            "decision": "HOLD",
                        },
                    ],
                },
            )
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n"
                "## [2026-04-14 00:00] decision | prior overlapping experiments\n\n"
                "### Artifacts\n"
                "- `ops/scripts/promotion_gate.py`\n"
                "- `ops/scripts/wiki_lint.py`\n"
                "- `ops/scripts/mechanism_assess.py`\n"
                "- `ops/scripts/mechanism/mutation_proposal_runtime.py`\n"
                "- `ops/scripts/mechanism/mechanism_run_validation_runtime.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            schema = load_schema(vault / "ops" / "schemas" / "mutation-proposals.schema.json")

            self.assertEqual(validate_with_schema(proposal_report, schema), [])
            self.assertEqual(proposal_report["status"], "pass")
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"],
                {
                    "available_proposal_count": 4,
                    "selected_proposal_count": 4,
                    "selection_mode": "standard",
                    "repair_priority_suppressed_count": 0,
                    "runnable_available_count": 1,
                    "blocked_available_count": 3,
                    "selected_runnable_count": 1,
                    "selected_blocked_count": 3,
                    "blocked_reason_counts": [
                        {"reason": "recent_log_overlap", "count": 3},
                    ],
                },
            )

            rotation = proposal_report["proposals"][0]
            self.assertEqual(
                rotation["proposal_id"],
                "recent_log_overlap_queue_blocked__auto-improve-queue-runtime",
            )
            self.assertEqual(
                rotation["primary_targets"],
                ["ops/scripts/mechanism/auto_improve_queue_runtime.py"],
            )
            self.assertEqual(
                rotation["must_change_tests"],
                ["tests/test_auto_improve_queue_runtime.py"],
            )
            self.assertEqual(rotation["blocked_by"], [])
    def test_recent_log_overlap_rotation_ignores_archived_recent_outcome_rework(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            recent_attempts = [
                {
                    "run_id": "auto-improve-trial-rerun-2-archive-suffix",
                    "proposal_id": "recent_log_overlap_queue_blocked__mutation-proposal-runtime",
                    "outcome": "validation_blocked",
                    "decision": "HOLD",
                    "promotion_report": "runs/archive/auto-improve-trial-rerun-2-archive-suffix/promotion-report.json",
                },
                {
                    "run_id": "auto-improve-trial-rerun-1",
                    "proposal_id": "recent_log_overlap_queue_blocked__mutation-proposal-runtime",
                    "outcome": "discarded",
                    "decision": "DISCARD",
                    "promotion_report": "runs/archive/auto-improve-trial-rerun-1/promotion-report.json",
                },
            ]
            for attempt, history_status in zip(recent_attempts, ("archived", "quarantined"), strict=True):
                write_json(
                    vault / attempt["promotion_report"],
                    {
                        "run_id": attempt["run_id"].replace("-archive-suffix", ""),
                        "decision": attempt["decision"],
                        "history": {
                            "status": history_status,
                            "reason": "superseded by remediation evidence",
                        },
                    },
                )
            write_json(
                vault / "ops" / "reports" / "outcome-metrics.json",
                {"recent_attempts": recent_attempts},
            )
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n"
                "## [2026-04-14 00:00] decision | prior overlapping experiments\n\n"
                "### Artifacts\n"
                "- `ops/scripts/promotion_gate.py`\n"
                "- `ops/scripts/wiki_lint.py`\n"
                "- `ops/scripts/mechanism_assess.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            schema = load_schema(vault / "ops" / "schemas" / "mutation-proposals.schema.json")

            self.assertEqual(validate_with_schema(proposal_report, schema), [])
            self.assertEqual(proposal_report["status"], "pass")
            self.assertEqual(proposal_report["summary"]["proposals_emitted"], 4)
            self.assertEqual(proposal_report["summary"]["blocked_proposals"], 3)
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"],
                {
                    "available_proposal_count": 4,
                    "selected_proposal_count": 4,
                    "selection_mode": "standard",
                    "repair_priority_suppressed_count": 0,
                    "runnable_available_count": 1,
                    "blocked_available_count": 3,
                    "selected_runnable_count": 1,
                    "selected_blocked_count": 3,
                    "blocked_reason_counts": [
                        {"reason": "recent_log_overlap", "count": 3}
                    ],
                },
            )

            rotation = proposal_report["proposals"][0]
            self.assertEqual(rotation["failure_mode"], "recent_log_overlap_queue_blocked")
            self.assertEqual(rotation["blocked_by"], [])
    def test_recent_log_overlap_rotation_treats_quarantined_noop_as_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            run_id = "auto-improve-trial-rerun-1"
            write_json(
                vault / "ops" / "reports" / "outcome-metrics.json",
                {
                    "recent_attempts": [
                        {
                            "run_id": run_id,
                            "proposal_id": "recent_log_overlap_queue_blocked__mutation-proposal-runtime",
                            "outcome": "mutation_failed",
                            "decision": "HOLD",
                            "promotion_report": f"runs/{run_id}/promotion-report.json",
                        },
                    ],
                },
            )
            write_json(
                vault / "runs" / run_id / "promotion-report.json",
                {
                    "run_id": run_id,
                    "decision": "HOLD",
                    "history": {
                        "status": "quarantined",
                        "reason": "no-op queue unblock should rotate away from this target",
                    },
                },
            )
            (vault / "runs" / run_id / "mutation-command.stderr.txt").write_text(
                (
                    "worker reported pass without modifying any declared primary target; "
                    "primary_targets=[ops/scripts/mechanism/mutation_proposal_runtime.py]\n"
                ),
                encoding="utf-8",
            )
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n"
                "## [2026-04-14 00:00] decision | prior overlapping experiments\n\n"
                "### Artifacts\n"
                "- `ops/scripts/promotion_gate.py`\n"
                "- `ops/scripts/wiki_lint.py`\n"
                "- `ops/scripts/mechanism_assess.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            schema = load_schema(vault / "ops" / "schemas" / "mutation-proposals.schema.json")

            self.assertEqual(validate_with_schema(proposal_report, schema), [])
            rotation = proposal_report["proposals"][0]
            self.assertEqual(rotation["failure_mode"], "recent_log_overlap_queue_blocked")
            self.assertEqual(
                rotation["proposal_id"],
                "recent_log_overlap_queue_blocked__mechanism-run-validation-runtime",
            )
            self.assertEqual(
                rotation["primary_targets"],
                ["ops/scripts/mechanism/mechanism_run_validation_runtime.py"],
            )
            self.assertEqual(rotation["blocked_by"], [])
    def test_recent_log_overlap_queue_rotation_does_not_self_block_when_targets_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n"
                "## [2026-04-14 00:00] decision | prior overlapping experiments\n\n"
                "### Artifacts\n"
                "- `ops/scripts/promotion_gate.py`\n"
                "- `ops/scripts/wiki_lint.py`\n"
                "- `ops/scripts/mechanism_assess.py`\n"
                "- `ops/scripts/mechanism/mutation_proposal_runtime.py`\n"
                "- `ops/scripts/mechanism/mechanism_run_validation_runtime.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            schema = load_schema(vault / "ops" / "schemas" / "mutation-proposals.schema.json")

            self.assertEqual(validate_with_schema(proposal_report, schema), [])
            self.assertEqual(proposal_report["status"], "pass")
            self.assertEqual(proposal_report["summary"]["proposals_emitted"], 4)
            self.assertEqual(proposal_report["summary"]["blocked_proposals"], 3)
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"],
                {
                    "available_proposal_count": 4,
                    "selected_proposal_count": 4,
                    "selection_mode": "standard",
                    "repair_priority_suppressed_count": 0,
                    "runnable_available_count": 1,
                    "blocked_available_count": 3,
                    "selected_runnable_count": 1,
                    "selected_blocked_count": 3,
                    "blocked_reason_counts": [
                        {"reason": "recent_log_overlap", "count": 3}
                    ],
                },
            )

            rotation = proposal_report["proposals"][0]
            self.assertEqual(rotation["failure_mode"], "recent_log_overlap_queue_blocked")
            self.assertEqual(rotation["blocked_by"], [])
            rotation_matches = [
                match
                for match in proposal_report["diagnostics"]["recent_log_overlap"]["matches"]
                if match["proposal_id"] == rotation["proposal_id"]
            ]
            self.assertEqual(len(rotation_matches), 1)
            self.assertEqual(
                rotation_matches[0]["matched_marker"],
                "mutation_proposal_runtime.py",
            )
    def test_recent_log_overlap_rotation_ignores_quarantine_log_for_secondary_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(vault / "ops" / "reports" / "outcome-metrics.json", {"recent_attempts": []})
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n"
                "## [2026-04-14 00:00] improve | active mutation proposal work\n\n"
                "### Artifacts\n"
                "- `ops/scripts/promotion_gate.py`\n"
                "- `ops/scripts/wiki_lint.py`\n"
                "- `ops/scripts/mechanism_assess.py`\n"
                "- `ops/scripts/mechanism/mutation_proposal_runtime.py`\n\n"
                "## [2026-04-14 00:01] improve | Quarantine superseded validation run\n\n"
                "### Artifacts\n"
                "- `ops/scripts/mechanism/mechanism_run_validation_runtime.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            schema = load_schema(vault / "ops" / "schemas" / "mutation-proposals.schema.json")

            self.assertEqual(validate_with_schema(proposal_report, schema), [])
            self.assertEqual(proposal_report["status"], "pass")
            rotation = next(
                proposal
                for proposal in proposal_report["proposals"]
                if proposal["failure_mode"] == "recent_log_overlap_queue_blocked"
            )
            self.assertEqual(
                rotation["proposal_id"],
                "recent_log_overlap_queue_blocked__mechanism-run-validation-runtime",
            )
            self.assertEqual(rotation["blocked_by"], [])
            rotation_matches = [
                match
                for match in proposal_report["diagnostics"]["recent_log_overlap"]["matches"]
                if match["proposal_id"] == rotation["proposal_id"]
            ]
            self.assertEqual(rotation_matches, [])
    def test_recent_log_overlap_uses_timestamp_order_before_file_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            report = mechanism_review_report()
            report["summary"]["candidates_emitted"] = 1
            report["candidates"] = [report["candidates"][0]]
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n"
                "## [2026-04-14 10:00] decision | older overlap appended late\n\n"
                "### Artifacts\n- `ops/scripts/promotion_gate.py`\n\n"
                "## [2026-04-14 12:00] decision | newer unrelated\n\n"
                "### Artifacts\n- `ops/scripts/unrelated.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(
                vault,
                policy,
                policy_path,
                dedupe_window=1,
                context=fixed_context(policy),
            )

            self.assertEqual(proposal_report["diagnostics"]["recent_log_overlap"]["section_ordering"], "timestamp")
            self.assertEqual(
                proposal_report["diagnostics"]["recent_log_overlap"]["scanned_log_headings"],
                ["[2026-04-14 12:00] decision | newer unrelated"],
            )
            self.assertEqual(proposal_report["diagnostics"]["recent_log_overlap"]["matches"], [])
            self.assertEqual(proposal_report["proposals"][0]["blocked_by"], [])
    def test_recent_log_overlap_expires_timestamped_sections_after_max_age(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n"
                "## [2026-04-14 00:00] decision | old overlap\n\n"
                "### Artifacts\n- `ops/scripts/wiki_lint.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(
                vault,
                policy,
                policy_path,
                context=fixed_context(policy, "2026-05-19T00:00:00Z"),
            )

            self.assertEqual(proposal_report["status"], "pass")
            self.assertEqual(proposal_report["summary"]["blocked_proposals"], 0)
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"]["blocked_reason_counts"],
                [],
            )
            self.assertEqual(
                proposal_report["diagnostics"]["recent_log_overlap"]["max_age_days"],
                7,
            )
            self.assertEqual(
                proposal_report["diagnostics"]["recent_log_overlap"]["scanned_log_headings"],
                [],
            )
            self.assertEqual(proposal_report["diagnostics"]["recent_log_overlap"]["matches"], [])
    def test_equal_priority_max_proposals_prefers_lower_blast_radius(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            report = mechanism_review_report()
            report["summary"]["candidates_emitted"] = 2
            report["candidates"] = [
                {
                    "candidate_id": "mechanism_eval_stagnation_candidate__example",
                    "candidate_type": "mechanism_eval_stagnation_candidate",
                    "family": "contract_regression_signals",
                    "tier": "supporting",
                    "objective": "detect repeated non-improvement against current contract-eval surfaces",
                    "priority": 80,
                    "primary_targets": ["ops/scripts/example.py"],
                    "supporting_targets": [],
                    "metrics_triggered": ["stage1_same_eval_rate"],
                    "run_ids": ["run-a", "run-b"],
                    "evidence": {"runs_examined": 2, "same_eval_runs": 2, "discard_runs": 1},
                    "rationale": "narrow script-only target",
                    "suggested_experiments": ["keep the script change isolated"],
                },
                {
                    "candidate_id": "mechanism_eval_stagnation_candidate__policy",
                    "candidate_type": "mechanism_eval_stagnation_candidate",
                    "family": "contract_regression_signals",
                    "tier": "supporting",
                    "objective": "detect repeated non-improvement against current contract-eval surfaces",
                    "priority": 80,
                    "primary_targets": ["ops/policies/wiki-maintainer-policy.yaml"],
                    "supporting_targets": ["ops/scripts/promotion_gate_mechanism_runtime.py"],
                    "metrics_triggered": ["stage1_same_eval_rate"],
                    "run_ids": ["run-p1", "run-p2"],
                    "evidence": {"runs_examined": 2, "same_eval_runs": 2, "discard_runs": 1},
                    "rationale": "broader policy touch target",
                    "suggested_experiments": ["keep the policy change isolated"],
                },
            ]
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, max_proposals=1)

            proposal = proposal_report["proposals"][0]
            self.assertEqual(proposal["source_candidate_id"], "mechanism_eval_stagnation_candidate__example")
            self.assertEqual(proposal["blast_radius_score"], 15)
    def test_build_report_falls_back_to_content_linked_tests_for_must_change_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")
            (vault / "tests" / "test_auto_improve_iteration_runtime.py").write_text(
                (
                    "from ops.scripts.auto_improve_iteration_persistence_runtime import "
                    "persist_iteration_state\n\n"
                    "def test_placeholder() -> None:\n"
                    "    assert persist_iteration_state is not None\n"
                ),
                encoding="utf-8",
            )

            report = mechanism_review_report()
            report["summary"]["candidates_emitted"] = 1
            report["candidates"] = [
                {
                    "candidate_id": "mechanism_eval_stagnation_candidate__auto-improve-iteration",
                    "candidate_type": "mechanism_eval_stagnation_candidate",
                    "family": "self_mod_stability",
                    "tier": "supporting",
                    "objective": "detect repeated non-improvement against current contract-eval surfaces",
                    "priority": 72,
                    "primary_targets": [
                        "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"
                    ],
                    "supporting_targets": [],
                    "metrics_triggered": ["stage1_same_eval_rate"],
                    "run_ids": ["run-1", "run-2"],
                    "evidence": {"runs_examined": 2, "same_eval_runs": 2, "discard_runs": 1},
                    "rationale": "fallback evidence should find the linked test import",
                    "suggested_experiments": ["keep the persistence update narrowly scoped"],
                }
            ]
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path)

            self.assertEqual(
                proposal_report["proposals"][0]["must_change_tests"],
                ["tests/test_auto_improve_iteration_runtime.py"],
            )
    def test_build_report_rewrites_flat_script_alias_to_current_target_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            current_target = "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"
            legacy_target = "ops/scripts/auto_improve_iteration_persistence_runtime.py"
            (vault / "ops" / "scripts" / "mechanism").mkdir(parents=True, exist_ok=True)
            (vault / current_target).write_text(
                "def persist_iteration_state() -> None:\n"
                "    return None\n",
                encoding="utf-8",
            )
            (vault / "tests" / "test_auto_improve_iteration_runtime.py").write_text(
                (
                    "from ops.scripts.auto_improve_iteration_persistence_runtime import "
                    "persist_iteration_state\n\n"
                    "def test_placeholder() -> None:\n"
                    "    assert persist_iteration_state is not None\n"
                ),
                encoding="utf-8",
            )

            report = mechanism_review_report()
            report["summary"]["candidates_emitted"] = 1
            report["candidates"] = [
                {
                    "candidate_id": "mechanism_eval_stagnation_candidate__auto-improve-iteration-persistence-runtime",
                    "candidate_type": "mechanism_eval_stagnation_candidate",
                    "family": "contract_regression_signals",
                    "tier": "supporting",
                    "objective": "detect repeated non-improvement against current contract-eval surfaces",
                    "priority": 85,
                    "primary_targets": [legacy_target],
                    "supporting_targets": ["ops/schemas/run-telemetry.schema.json"],
                    "metrics_triggered": ["repeated_discard_runs"],
                    "run_ids": ["run-1", "run-2"],
                    "evidence": {"runs_examined": 2, "same_eval_runs": 0, "discard_runs": 2},
                    "rationale": "legacy flat path came from historical run evidence",
                    "suggested_experiments": [f"try one mechanism-only experiment on {legacy_target}"],
                }
            ]
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path)

            proposal = proposal_report["proposals"][0]
            self.assertEqual(proposal["primary_targets"], [current_target])
            self.assertIn(current_target, proposal["single_mechanism_scope"])
            self.assertIn(current_target, proposal["change_hypothesis"])
            self.assertNotIn(legacy_target, json.dumps(proposal, ensure_ascii=False))
            self.assertEqual(
                proposal["must_change_tests"],
                ["tests/test_auto_improve_iteration_runtime.py"],
            )
    def test_build_report_adds_script_output_surface_for_ops_script_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            target = "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"
            (vault / "ops" / "scripts" / "mechanism").mkdir(parents=True, exist_ok=True)
            (vault / target).write_text(
                "def persist_iteration_state() -> None:\n"
                "    return None\n",
                encoding="utf-8",
            )
            telemetry_target = "ops/scripts/mechanism/auto_improve_iteration_telemetry_runtime.py"
            (vault / telemetry_target).write_text(
                "def iteration_same_eval_contract() -> dict:\n"
                "    return {}\n",
                encoding="utf-8",
            )
            (vault / "ops" / "script-output-surfaces.json").write_text("{}\n", encoding="utf-8")
            (vault / "tests" / "test_auto_improve_iteration_runtime.py").write_text(
                (
                    "from ops.scripts.auto_improve_iteration_persistence_runtime import "
                    "persist_iteration_state\n\n"
                    "def test_placeholder() -> None:\n"
                    "    assert persist_iteration_state is not None\n"
                ),
                encoding="utf-8",
            )

            report = mechanism_review_report()
            report["summary"]["candidates_emitted"] = 1
            report["candidates"] = [
                {
                    "candidate_id": "mechanism_eval_stagnation_candidate__auto-improve-iteration-persistence-runtime",
                    "candidate_type": "mechanism_eval_stagnation_candidate",
                    "family": "contract_regression_signals",
                    "tier": "supporting",
                    "objective": "detect repeated non-improvement against current contract-eval surfaces",
                    "priority": 85,
                    "primary_targets": [target],
                    "supporting_targets": ["ops/schemas/run-telemetry.schema.json"],
                    "metrics_triggered": ["stage1_same_eval_rate"],
                    "run_ids": ["run-1", "run-2"],
                    "evidence": {"runs_examined": 2, "same_eval_runs": 2, "discard_runs": 0},
                    "rationale": "fixture",
                    "suggested_experiments": [f"try one mechanism-only experiment on {target}"],
                }
            ]
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path)

            self.assertEqual(
                proposal_report["proposals"][0]["supporting_targets"],
                [
                    "ops/schemas/run-telemetry.schema.json",
                    telemetry_target,
                    "ops/script-output-surfaces.json",
                ],
            )
    def test_build_report_uses_bundled_schema_fallback_when_vault_schemas_are_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")
            policy, policy_path = load_policy(vault)
            (vault / "ops" / "schemas" / "mechanism-review-candidates.schema.json").unlink()
            (vault / "ops" / "schemas" / "mutation-proposals.schema.json").unlink()

            report = build_report(vault, policy, policy_path)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["proposals_emitted"], 3)
    def test_build_report_marks_empty_proposal_queue_as_attention(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            report = mechanism_review_report()
            report["summary"]["candidates_emitted"] = 0
            report["candidates"] = []
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path)

            self.assertEqual(proposal_report["status"], "attention")
            self.assertEqual(proposal_report["summary"]["proposals_emitted"], 0)
            self.assertEqual(proposal_report["summary"]["blocked_proposals"], 3)
            self.assertEqual(proposal_report["summary"]["candidate_blocker_count"], 0)
            self.assertEqual(proposal_report["summary"]["proposal_blocker_count"], 3)
            self.assertEqual(
                proposal_report["summary"]["queue_pressure_summary"],
                "no proposals emitted | mechanism review emitted zero candidates | session_calibration.status=no_session_context | outcome_metrics_calibration.status=missing_outcome_metrics",
            )
            self.assertEqual(
                {
                    item["blocker_type"]
                    for item in proposal_report["diagnostics"]["empty_queue_blockers"]
                },
                {"history", "session", "outcome"},
            )
            self.assertEqual(proposal_report["proposals"], [])
    def test_build_report_emits_blocked_bootstrap_unblock_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            (vault / "ops" / "scripts" / "auto_improve_iteration_persistence_runtime.py").write_text(
                "def persist_iteration_state() -> None:\n"
                "    return None\n",
                encoding="utf-8",
            )
            (vault / "tests" / "test_auto_improve_iteration_runtime.py").write_text(
                "from ops.scripts.auto_improve_iteration_persistence_runtime import persist_iteration_state\n\n"
                "def test_placeholder() -> None:\n"
                "    assert persist_iteration_state is not None\n",
                encoding="utf-8",
            )

            report = mechanism_review_report()
            report["summary"]["candidates_emitted"] = 0
            report["candidates"] = []
            report["status"] = "attention"
            report["diagnostics"]["bootstrap"] = {
                "status": "bootstrap_history_insufficient",
                "summary": (
                    "현재 target group들은 comparable mechanism run history가 아직 부족해 "
                    "trend-based candidate 평가 창이 열리지 않았다."
                ),
                "recommended_next_step": (
                    "run one or more additional comparable system_mechanism experiments on "
                    "the same primary target set to unlock trend-based review candidates"
                ),
                "trend_candidate_requirements": [
                    {
                        "candidate_type": "mechanism_eval_stagnation_candidate",
                        "evaluation_min_runs": 2,
                        "full_window_runs": 5,
                    }
                ],
                "target_groups_under_min_history": [
                    {
                        "primary_targets": [
                            "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"
                        ],
                        "comparable_runs": 1,
                        "latest_run_id": "run-1",
                        "blocked_candidate_types": [
                            {
                                "candidate_type": "mechanism_eval_stagnation_candidate",
                                "required_runs": 2,
                                "additional_runs_needed": 1,
                            }
                        ],
                    }
                ],
            }
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path)

            self.assertEqual(proposal_report["status"], "attention")
            self.assertEqual(proposal_report["summary"]["source_candidates_read"], 0)
            self.assertEqual(proposal_report["summary"]["proposals_emitted"], 1)
            self.assertEqual(proposal_report["summary"]["blocked_proposals"], 1)
            self.assertEqual(
                proposal_report["summary"]["queue_pressure_summary"],
                "session unavailable | bootstrap_queue_unblock 1 proposal, 1 blocked",
            )
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"]["blocked_reason_counts"],
                [{"reason": "bootstrap_history_insufficient", "count": 1}],
            )
            self.assertEqual(proposal_report["diagnostics"]["empty_queue_blockers"], [])
            proposal = proposal_report["proposals"][0]
            self.assertEqual(
                proposal["proposal_id"],
                "bootstrap_history_insufficient__auto-improve-iteration-persistence-runtime",
            )
            self.assertEqual(
                proposal["source_candidate_id"],
                "bootstrap_queue_unblock__auto_improve_iteration_persistence_runtime",
            )
            self.assertEqual(
                proposal["source_candidate_type"],
                "mechanism_bootstrap_history_candidate",
            )
            self.assertEqual(proposal["family"], "bootstrap_queue_unblock")
            self.assertEqual(proposal["failure_mode"], "bootstrap_history_insufficient")
            self.assertEqual(proposal["metrics_triggered"], ["bootstrap_history_insufficient"])
            self.assertEqual(proposal["priority"], 88)
            self.assertEqual(
                proposal["priority_breakdown"],
                {
                    "base_priority": 88,
                    "historical_calibration_delta": 0,
                    "session_calibration_delta": 0,
                    "review_candidate_priority": 88,
                    "recent_log_overlap_penalty": 0,
                    "final_priority": 88,
                },
            )
            self.assertEqual(
                proposal["must_change_budget_signal"],
                {
                    "signal": "mechanism_review.summary.candidates_emitted",
                    "expected_change": "increase",
                },
            )
            self.assertEqual(
                proposal["blocked_by"],
                ["bootstrap_history_insufficient"],
            )
            self.assertEqual(
                proposal["primary_targets"],
                ["ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"],
            )
            self.assertEqual(
                proposal["must_change_tests"],
                ["tests/test_auto_improve_iteration_runtime.py"],
            )
            self.assertEqual(
                proposal["run_ids"],
                ["run-1"],
            )
            self.assertIn(
                "one additional comparable run",
                proposal["single_mechanism_scope"],
            )
            self.assertIn("one more finalized comparable run", proposal["change_hypothesis"])
    def test_build_report_emits_blocked_seed_proposal_for_no_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            (vault / "ops" / "scripts" / "auto_improve_iteration_persistence_runtime.py").write_text(
                "def persist_iteration_state() -> None:\n"
                "    return None\n",
                encoding="utf-8",
            )
            (vault / "tests" / "test_auto_improve_iteration_runtime.py").write_text(
                "from ops.scripts.auto_improve_iteration_persistence_runtime import persist_iteration_state\n\n"
                "def test_placeholder() -> None:\n"
                "    assert persist_iteration_state is not None\n",
                encoding="utf-8",
            )
            report = mechanism_review_report()
            report["summary"]["runs_discovered"] = 0
            report["summary"]["runs_considered"] = 0
            report["summary"]["candidates_emitted"] = 0
            report["candidates"] = []
            report["status"] = "attention"
            report["diagnostics"]["bootstrap"] = {
                "status": "no_history",
                "summary": "아직 유효한 system_mechanism run history가 없어 trend-based mechanism candidate를 계산할 수 없다.",
                "recommended_next_step": (
                    "capture the first finalized system_mechanism run with baseline/candidate eval, lint, mechanism assessment, and promotion report"
                ),
                "trend_candidate_requirements": [
                    {
                        "candidate_type": "mechanism_eval_stagnation_candidate",
                        "evaluation_min_runs": 2,
                        "full_window_runs": 5,
                    }
                ],
                "target_groups_under_min_history": [],
            }
            report["diagnostics"]["session_calibration"]["status"] = "no_candidates"
            report["diagnostics"]["outcome_metrics_calibration"]["status"] = "no_candidates"
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path)

            self.assertEqual(proposal_report["status"], "attention")
            self.assertEqual(proposal_report["summary"]["source_candidates_read"], 0)
            self.assertEqual(proposal_report["summary"]["proposals_emitted"], 1)
            self.assertEqual(proposal_report["summary"]["blocked_proposals"], 1)
            self.assertEqual(
                proposal_report["summary"]["queue_pressure_summary"],
                "bootstrap_queue_unblock 1 proposal, 1 blocked",
            )
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"]["blocked_reason_counts"],
                [{"reason": "no_history", "count": 1}],
            )
            self.assertEqual(proposal_report["diagnostics"]["empty_queue_blockers"], [])
            proposal = proposal_report["proposals"][0]
            self.assertEqual(
                proposal["proposal_id"],
                "bootstrap_history_insufficient__auto-improve-iteration-persistence-runtime",
            )
            self.assertEqual(
                proposal["source_candidate_id"],
                "bootstrap_queue_unblock__fallback-seed",
            )
            self.assertEqual(
                proposal["source_candidate_type"],
                "mechanism_bootstrap_history_candidate",
            )
            self.assertEqual(proposal["family"], "bootstrap_queue_unblock")
            self.assertEqual(proposal["failure_mode"], "bootstrap_history_insufficient")
            self.assertEqual(proposal["metrics_triggered"], ["bootstrap_history_insufficient"])
            self.assertEqual(proposal["priority"], 92)
            self.assertEqual(
                proposal["priority_breakdown"],
                {
                    "base_priority": 92,
                    "historical_calibration_delta": 0,
                    "session_calibration_delta": 0,
                    "review_candidate_priority": 92,
                    "recent_log_overlap_penalty": 0,
                    "final_priority": 92,
                },
            )
            self.assertEqual(
                proposal["must_change_budget_signal"],
                {
                    "signal": "mechanism_review.summary.runs_considered",
                    "expected_change": "increase",
                },
            )
            self.assertEqual(
                proposal["primary_targets"],
                ["ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"],
            )
            self.assertEqual(
                proposal["supporting_targets"],
                ["ops/schemas/run-telemetry.schema.json"],
            )
            self.assertEqual(
                proposal["must_change_tests"],
                ["tests/test_auto_improve_iteration_runtime.py"],
            )
            self.assertEqual(
                proposal["blocked_by"],
                ["no_history"],
            )
            self.assertEqual(
                proposal["run_ids"],
                ["bootstrap-no-history"],
            )
            self.assertIn("fallback-family system_mechanism run", proposal["single_mechanism_scope"])
            self.assertIn("first finalized comparable", proposal["change_hypothesis"])
    def test_build_report_does_not_fallback_from_invalid_output_schema_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")
            policy, policy_path = load_policy(vault)
            (vault / "ops" / "schemas" / "mutation-proposals.schema.json").write_text(
                "{not-json",
                encoding="utf-8",
            )

            with self.assertRaises(json.JSONDecodeError):
                build_report(vault, policy, policy_path)
    def test_outcome_metrics_calibration_preview_is_not_a_priority_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            report = mechanism_review_report()
            report["diagnostics"]["outcome_metrics_calibration"] = {
                "enabled": True,
                "status": "active",
                "mode": "audit_only",
                "gate_effect": "none",
                "source_report": "ops/reports/outcome-metrics.json",
                "recent_window": 20,
                "candidate_count": 3,
                "candidates_with_outcome_context": 3,
                "target_count": 1,
                "thresholds": {
                    "high_rework_count": 1,
                    "hold_or_discard_moving_average": 0.25,
                    "rollback_signal_ratio": 0.2,
                    "defect_escape_pair_count": 1,
                },
                "global_signals": {
                    "attempt_count": 3,
                    "recent_attempt_count": 3,
                    "moving_averages": {
                        "hold": 0.3333,
                        "discard": 0.6667,
                        "rollback_signal": 0.3333,
                    },
                    "rework_count": 2,
                    "rollback_signal_count": 1,
                    "defect_escape_pair_count": 1,
                },
                "target_signals": [
                    {
                        "primary_targets": ["ops/scripts/promotion_gate.py"],
                        "candidate_ids": [
                            "mechanism_eval_stagnation_candidate__promotion-gate"
                        ],
                        "candidate_types": [
                            "mechanism_eval_stagnation_candidate"
                        ],
                        "families": ["contract_regression_signals"],
                        "candidate_count_by_family": {
                            "contract_regression_signals": 1
                        },
                        "current_priority_max": 80,
                        "attempt_count": 3,
                        "source_run_ids": ["run-a", "run-b", "run-c"],
                        "hold_count": 1,
                        "discard_count": 2,
                        "hold_moving_average": 0.3333,
                        "discard_moving_average": 0.6667,
                        "rollback_signal_count": 1,
                        "rollback_signal_ratio": 0.3333,
                        "rework_count": 2,
                        "defect_escape_pair_count": 1,
                        "preview_flags": [
                            "high_rework",
                            "recent_hold_moving_average",
                            "recent_discard_moving_average",
                            "rollback_signal_ratio",
                            "defect_escape_proxy",
                        ],
                    }
                ],
                "family_signals": [
                    {
                        "family": "contract_regression_signals",
                        "target_count": 1,
                        "candidate_count": 1,
                        "attempt_count": 3,
                        "hold_count": 1,
                        "discard_count": 2,
                        "rollback_signal_count": 1,
                        "rework_count": 2,
                        "defect_escape_pair_count": 1,
                        "preview_flags": [
                            "high_rework",
                            "recent_hold_moving_average",
                            "recent_discard_moving_average",
                            "rollback_signal_ratio",
                            "defect_escape_proxy",
                        ],
                        "hold_moving_average": 0.3333,
                        "discard_moving_average": 0.6667,
                        "rollback_signal_ratio": 0.3333,
                    }
                ],
                "high_rework_targets": [
                    {
                        "primary_targets": ["ops/scripts/promotion_gate.py"],
                        "families": ["contract_regression_signals"],
                        "rework_count": 2,
                        "source_run_ids": ["run-a", "run-b", "run-c"],
                    }
                ],
                "defect_escape_pairs": [
                    {
                        "target": "ops/scripts/promotion_gate.py",
                        "promoted_run_id": "run-b",
                        "escaped_run_id": "run-c",
                        "escaped_decision": "HOLD",
                        "escaped_outcome": "validation_blocked",
                    }
                ],
                "shadow_priority": shadow_priority_diagnostics(attempts_considered=3),
                "evidence_gaps": [],
                "notes": [
                    (
                        "audit-only preview: outcome metrics are reported for calibration "
                        "review and do not change candidate priority."
                    )
                ],
            }
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path)

            proposal = proposal_report["proposals"][0]
            self.assertEqual(proposal["source_candidate_type"], "mechanism_eval_stagnation_candidate")
            self.assertEqual(proposal["priority"], 80)
            self.assertEqual(
                proposal["priority_breakdown"],
                {
                    "base_priority": 80,
                    "historical_calibration_delta": 0,
                    "session_calibration_delta": 0,
                    "review_candidate_priority": 80,
                    "recent_log_overlap_penalty": 0,
                    "final_priority": 80,
                },
            )
            self.assertNotIn("outcome_metrics_calibration_delta", proposal["priority_breakdown"])
            self.assertEqual(
                proposal_report["diagnostics"]["evidence_gaps"],
                ["session_calibration.status=no_session_context"],
            )
    def test_session_calibration_contributes_to_priority_breakdown_and_final_priority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            report = mechanism_review_report()
            report["summary"]["candidates_emitted"] = 1
            report["candidates"] = [
                {
                    "candidate_id": "mechanism_eval_stagnation_candidate__promotion-gate",
                    "candidate_type": "mechanism_eval_stagnation_candidate",
                    "family": "contract_regression_signals",
                    "tier": "supporting",
                    "objective": "detect repeated non-improvement against current contract-eval surfaces",
                    "priority": 89,
                    "primary_targets": ["ops/scripts/promotion_gate.py"],
                    "supporting_targets": ["ops/scripts/promotion_gate_mechanism_runtime.py"],
                    "metrics_triggered": ["stage1_same_eval_rate", "repeated_discard_runs"],
                    "run_ids": ["run-a", "run-b", "run-c"],
                    "evidence": {
                        "runs_examined": 3,
                        "same_eval_runs": 3,
                        "discard_runs": 2,
                    },
                    "historical_calibration": {
                        "lookback_runs": 6,
                        "history_window_runs": 3,
                        "unstable_followup_window": 2,
                        "historical_promote_count": 1,
                        "promoted_then_regressed_count": 0,
                        "repeated_same_eval_after_promote_count": 1,
                        "durable_promote_count": 0,
                        "priority_before_calibration": 75,
                        "priority_delta": 10,
                        "priority_after_calibration": 85,
                    },
                    "session_calibration": {
                        "runs_with_session_context": 2,
                        "sessions_considered": 2,
                        "sessions_with_rollups": 2,
                        "validation_blocked_sessions": 1,
                        "review_blocked_sessions": 0,
                        "mutation_failed_sessions": 0,
                        "validator_dispatch_sessions": 2,
                        "reviewer_dispatch_sessions": 0,
                        "high_risk_routing_sessions": 0,
                        "priority_before_calibration": 85,
                        "priority_delta": 4,
                        "priority_after_calibration": 89,
                    },
                    "rationale": "same eval or discard repeated",
                    "suggested_experiments": [
                        "try one mechanism-only experiment on ops/scripts/promotion_gate.py"
                    ],
                }
            ]
            report["diagnostics"]["session_calibration"] = {
                "enabled": True,
                "status": "active",
                "candidate_count": 1,
                "candidates_with_session_context": 1,
                "candidates_with_rollups": 1,
                "candidates_without_session_context": 0,
                "runs_with_session_context": 2,
                "sessions_considered": 2,
                "sessions_with_rollups": 2,
                "validation_blocked_sessions": 1,
                "review_blocked_sessions": 0,
                "mutation_failed_sessions": 0,
                "validator_dispatch_sessions": 2,
                "reviewer_dispatch_sessions": 0,
                "high_risk_routing_sessions": 0,
                "total_priority_delta": 4,
                "boosted_candidates": 1,
                "lowered_candidates": 0,
                "unchanged_candidates": 0,
                "by_family": [
                    {
                        "family": "contract_regression_signals",
                        "candidates_with_session_context": 1,
                        "candidates_with_rollups": 1,
                        "candidates_without_session_context": 0,
                        "runs_with_session_context": 2,
                        "sessions_considered": 2,
                        "sessions_with_rollups": 2,
                        "validation_blocked_sessions": 1,
                        "review_blocked_sessions": 0,
                        "mutation_failed_sessions": 0,
                        "validator_dispatch_sessions": 2,
                        "reviewer_dispatch_sessions": 0,
                        "high_risk_routing_sessions": 0,
                        "total_priority_delta": 4,
                        "boosted_candidates": 1,
                        "lowered_candidates": 0,
                        "unchanged_candidates": 0,
                    }
                ],
            }
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n## [2026-04-14 00:00] decision | prior overlap\n\n### Artifacts\n- `ops/scripts/promotion_gate.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))

            self.assertEqual(proposal_report["status"], "pass")
            self.assertEqual(proposal_report["summary"]["proposals_emitted"], 2)
            self.assertEqual(proposal_report["summary"]["blocked_proposals"], 1)
            self.assertEqual(
                proposal_report["summary"]["queue_pressure_summary"],
                "contract_regression_signals 1 proposal, 1 blocked, delta +4, validator 2, validation 1; queue_unblock 1 proposal",
            )
            proposal_by_source = {
                proposal["source_candidate_type"]: proposal
                for proposal in proposal_report["proposals"]
            }
            proposal = proposal_by_source["mechanism_eval_stagnation_candidate"]
            self.assertEqual(proposal["priority"], 74)
            self.assertEqual(
                proposal["priority_breakdown"],
                {
                    "base_priority": 75,
                    "historical_calibration_delta": 10,
                    "session_calibration_delta": 4,
                    "review_candidate_priority": 89,
                    "recent_log_overlap_penalty": -15,
                    "final_priority": 74,
                },
            )
            self.assertEqual(
                proposal_report["diagnostics"]["family_session_calibration"],
                {
                    "enabled": True,
                    "status": "active",
                    "proposal_count": 2,
                    "blocked_proposal_count": 1,
                    "by_family": [
                        {
                            "family": "contract_regression_signals",
                            "proposal_count": 1,
                            "blocked_proposal_count": 1,
                            "session_priority_delta": 4,
                            "boosted_candidates": 1,
                            "lowered_candidates": 0,
                            "unchanged_candidates": 0,
                            "validation_blocked_sessions": 1,
                            "review_blocked_sessions": 0,
                            "mutation_failed_sessions": 0,
                            "validator_dispatch_sessions": 2,
                            "reviewer_dispatch_sessions": 0,
                            "high_risk_routing_sessions": 0,
                        },
                        {
                            "family": "queue_unblock",
                            "proposal_count": 1,
                            "blocked_proposal_count": 0,
                            "session_priority_delta": 0,
                            "boosted_candidates": 0,
                            "lowered_candidates": 0,
                            "unchanged_candidates": 0,
                            "validation_blocked_sessions": 0,
                            "review_blocked_sessions": 0,
                            "mutation_failed_sessions": 0,
                            "validator_dispatch_sessions": 0,
                            "reviewer_dispatch_sessions": 0,
                            "high_risk_routing_sessions": 0,
                        }
                    ],
                },
            )
    def test_disabled_session_calibration_keeps_queue_family_summary_but_marks_state_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            report = mechanism_review_report()
            report["diagnostics"]["session_calibration"] = {
                "enabled": False,
                "status": "disabled",
                "candidate_count": 0,
                "candidates_with_session_context": 0,
                "candidates_with_rollups": 0,
                "candidates_without_session_context": 0,
                "runs_with_session_context": 0,
                "sessions_considered": 0,
                "sessions_with_rollups": 0,
                "validation_blocked_sessions": 0,
                "review_blocked_sessions": 0,
                "mutation_failed_sessions": 0,
                "validator_dispatch_sessions": 0,
                "reviewer_dispatch_sessions": 0,
                "high_risk_routing_sessions": 0,
                "total_priority_delta": 0,
                "boosted_candidates": 0,
                "lowered_candidates": 0,
                "unchanged_candidates": 0,
                "by_family": [],
            }
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path)

            self.assertEqual(
                proposal_report["summary"]["queue_pressure_summary"],
                "session calibration disabled | self_mod_stability 2 proposals; contract_regression_signals 1 proposal",
            )
            self.assertEqual(
                proposal_report["diagnostics"]["family_session_calibration"],
                {
                    "enabled": False,
                    "status": "disabled",
                    "proposal_count": 3,
                    "blocked_proposal_count": 0,
                    "by_family": [
                        {
                            "family": "contract_regression_signals",
                            "proposal_count": 1,
                            "blocked_proposal_count": 0,
                            "session_priority_delta": 0,
                            "boosted_candidates": 0,
                            "lowered_candidates": 0,
                            "unchanged_candidates": 0,
                            "validation_blocked_sessions": 0,
                            "review_blocked_sessions": 0,
                            "mutation_failed_sessions": 0,
                            "validator_dispatch_sessions": 0,
                            "reviewer_dispatch_sessions": 0,
                            "high_risk_routing_sessions": 0,
                        },
                        {
                            "family": "self_mod_stability",
                            "proposal_count": 2,
                            "blocked_proposal_count": 0,
                            "session_priority_delta": 0,
                            "boosted_candidates": 0,
                            "lowered_candidates": 0,
                            "unchanged_candidates": 0,
                            "validation_blocked_sessions": 0,
                            "review_blocked_sessions": 0,
                            "mutation_failed_sessions": 0,
                            "validator_dispatch_sessions": 0,
                            "reviewer_dispatch_sessions": 0,
                            "high_risk_routing_sessions": 0,
                        },
                    ],
                },
            )
    def test_policy_identity_mismatch_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            report = mechanism_review_report()
            report["policy"]["version"] = 999
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            with self.assertRaisesRegex(
                ValueError,
                "mechanism review report policy.version does not match current policy",
            ):
                build_report(vault, policy, policy_path)
    def test_missing_artifact_envelope_fails_fast_for_primary_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            report = mechanism_review_report()
            report.pop("currentness", None)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            with self.assertRaisesRegex(
                ValueError,
                "mechanism review report is not current primary evidence: missing_artifact_envelope",
            ):
                build_report(vault, policy, policy_path)
    def test_unknown_currentness_fails_fast_for_primary_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            report = mechanism_review_report()
            report["currentness"]["status"] = "unknown"
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            with self.assertRaisesRegex(
                ValueError,
                "mechanism review report is not current primary evidence: currentness_status=unknown",
            ):
                build_report(vault, policy, policy_path)
    def test_unknown_candidate_type_in_mechanism_review_report_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            report = mechanism_review_report()
            report["candidates"][0]["candidate_type"] = "mechanism_unknown_test_sentinel_candidate"
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path)

            self.assertEqual(proposal_report["summary"]["proposals_emitted"], 2)
            self.assertEqual(
                proposal_report["diagnostics"]["skipped_candidates"][0]["reason"],
                "candidate_mapping_error",
            )
            self.assertIn(
                "unsupported mechanism review candidate type",
                proposal_report["diagnostics"]["skipped_candidates"][0]["detail"],
            )
    def test_schema_drift_candidate_maps_to_schema_guardrail_failure_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            report = mechanism_review_report()
            report["summary"]["candidates_emitted"] = 1
            report["candidates"] = [
                {
                    "candidate_id": "mechanism_schema_drift_candidate__wiki-schema",
                    "candidate_type": "mechanism_schema_drift_candidate",
                    "family": "schema_drift",
                    "tier": "core",
                    "objective": "detect schema-touching promotions that are not paired with test guardrails",
                    "priority": 75,
                    "primary_targets": ["ops/schemas/wiki.schema.json"],
                    "supporting_targets": ["ops/scripts/mechanism_assess.py"],
                    "metrics_triggered": [
                        "schema_change_without_test_growth",
                        "promoted_schema_change_without_guardrails",
                    ],
                    "run_ids": ["run-s2", "run-s4"],
                    "evidence": {
                        "runs_examined": 5,
                        "schema_change_without_test_growth_promotions": 2,
                    },
                    "historical_calibration": {
                        "lookback_runs": 6,
                        "history_window_runs": 5,
                        "unstable_followup_window": 2,
                        "historical_promote_count": 1,
                        "promoted_then_regressed_count": 0,
                        "repeated_same_eval_after_promote_count": 1,
                        "durable_promote_count": 0,
                        "priority_before_calibration": 65,
                        "priority_delta": 10,
                        "priority_after_calibration": 75,
                    },
                    "rationale": "schema change promoted without test growth",
                    "suggested_experiments": [
                        "add schema-focused regression coverage for ops/schemas/wiki.schema.json"
                    ],
                }
            ]
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path)

            self.assertEqual(proposal_report["summary"]["proposals_emitted"], 1)
            proposal = proposal_report["proposals"][0]
            self.assertEqual(
                proposal["failure_mode"],
                "schema_change_without_test_guardrails",
            )
            self.assertIn(
                "schema-specific guardrail tests",
                proposal["single_mechanism_scope"],
            )
    def test_policy_complexity_growth_candidate_maps_to_policy_surface_failure_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            report = mechanism_review_report()
            report["summary"]["candidates_emitted"] = 1
            report["candidates"] = [
                {
                    "candidate_id": "mechanism_policy_complexity_growth_candidate__wiki-maintainer-policy",
                    "candidate_type": "mechanism_policy_complexity_growth_candidate",
                    "family": "policy_complexity_growth",
                    "tier": "supporting",
                    "objective": "detect policy-surface growth that increases mechanism complexity without improving eval outcomes",
                    "priority": 70,
                    "primary_targets": ["ops/policies/wiki-maintainer-policy.yaml"],
                    "supporting_targets": ["ops/scripts/promotion_gate_mechanism_runtime.py"],
                    "metrics_triggered": [
                        "policy_surface_growth_without_eval_gain",
                        "policy_complexity_score_growth",
                        "policy_nonempty_growth",
                    ],
                    "run_ids": ["run-p1", "run-p2"],
                    "evidence": {
                        "runs_examined": 2,
                        "policy_surface_growth_without_eval_gain_runs": 2,
                        "policy_target_count": 1,
                        "policy_targets_summary": "ops/policies/wiki-maintainer-policy.yaml",
                    },
                    "historical_calibration": {
                        "lookback_runs": 6,
                        "history_window_runs": 2,
                        "unstable_followup_window": 2,
                        "historical_promote_count": 1,
                        "promoted_then_regressed_count": 0,
                        "repeated_same_eval_after_promote_count": 1,
                        "durable_promote_count": 0,
                        "priority_before_calibration": 60,
                        "priority_delta": 10,
                        "priority_after_calibration": 70,
                    },
                    "rationale": "policy surface growth repeated without eval gain",
                    "suggested_experiments": [
                        "shrink the next policy change in ops/policies/wiki-maintainer-policy.yaml to one rule or threshold and pair it with direct regression coverage"
                    ],
                }
            ]
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path)

            self.assertEqual(proposal_report["summary"]["proposals_emitted"], 1)
            proposal = proposal_report["proposals"][0]
            self.assertEqual(
                proposal["failure_mode"],
                "policy_surface_growth_without_eval_gain",
            )
            self.assertIn(
                "ops/policies/wiki-maintainer-policy.yaml",
                proposal["single_mechanism_scope"],
            )



if __name__ == "__main__":
    unittest.main()
