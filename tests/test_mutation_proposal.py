from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.mutation_proposal import main as mutation_proposal_main
from ops.scripts.mutation_proposal_runtime import build_report
from ops.scripts.policy_runtime import load_policy
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.cli_test_runtime import invoke_cli_main
from tests.minimal_vault_runtime import (
    seed_minimal_vault as seed_minimal_raw_registry_vault,
)
from tests.mutation_proposal_test_runtime import (
    ENVELOPE_SCHEMA_PATH,
    auto_improve_session_envelope,
    fixed_context,
    mechanism_review_report,
    seed_vault,
    shadow_priority_diagnostics,
    write_json,
    write_json_exact,
)


class MutationProposalTest(unittest.TestCase):
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

    def test_closed_repeated_discard_remediation_falls_through_to_open_same_eval_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "remediation-backlog.json",
                {
                    "status": "attention",
                    "summary": {"open_total_count": 0},
                    "items": [
                        {
                            "item_id": "negative_lesson_discard_equal_score_secondary_eligibility",
                            "blocker_id": "discard_equal_score_secondary_eligibility",
                            "status": "open",
                            "severity": "blocks_repeat",
                            "repair_target": "Open items alone should not suppress proposals.",
                            "next_action": "Keep working.",
                        },
                        {
                            "item_id": "negative_lesson_discard_equal_score_secondary_eligibility",
                            "blocker_id": "discard_equal_score_secondary_eligibility",
                            "status": "closed",
                            "severity": "blocks_repeat",
                            "repair_target": (
                                "Change the mechanism or evidence predicate before rerunning "
                                "another DISCARD attempt with same_eval_reason_code="
                                "equal_score_secondary_eligibility."
                            ),
                            "next_action": "Closed by predicate repair evidence.",
                        },
                    ],
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            schema = load_schema(vault / "ops" / "schemas" / "mutation-proposals.schema.json")

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["proposals_emitted"], 3)
            proposals_by_source = {proposal["source_candidate_type"]: proposal for proposal in report["proposals"]}
            stagnation = proposals_by_source["mechanism_eval_stagnation_candidate"]
            self.assertEqual(stagnation["failure_mode"], "repeated_same_eval_after_promote")
            self.assertEqual(stagnation["supporting_targets"], [])
            self.assertEqual(stagnation["metrics_triggered"], ["stage1_same_eval_rate"])
            self.assertEqual(stagnation["run_ids"], ["run-a", "run-b", "run-c"])
            self.assertEqual(
                stagnation["must_change_budget_signal"],
                {
                    "signal": "strict_secondary_improvement_present",
                    "expected_change": "true_for_equal_score_promotion",
                },
            )
            self.assertNotIn(
                "repeated_discard_runs",
                {proposal["failure_mode"] for proposal in report["proposals"]},
            )
            self.assertEqual(
                report["diagnostics"]["skipped_candidates"],
                [
                    {
                        "candidate_id": "mechanism_eval_stagnation_candidate__promotion-gate",
                        "reason": "closed_remediation_backlog_resolution",
                        "detail": (
                            "closed remediation backlog item(s): "
                            "negative_lesson_discard_equal_score_secondary_eligibility"
                        ),
                    }
                ],
            )

    def test_closed_repeated_discard_alternate_survives_when_original_mode_disallowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "remediation-backlog.json",
                {
                    "status": "attention",
                    "summary": {"open_total_count": 0},
                    "items": [
                        {
                            "item_id": "negative_lesson_discard_equal_score_secondary_eligibility",
                            "blocker_id": "discard_equal_score_secondary_eligibility",
                            "status": "closed",
                            "severity": "blocks_repeat",
                            "repair_target": (
                                "Change the mechanism or evidence predicate before rerunning "
                                "another DISCARD attempt with same_eval_reason_code="
                                "equal_score_secondary_eligibility."
                            ),
                            "next_action": "Closed by predicate repair evidence.",
                        },
                    ],
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")
            policy_path = vault / "ops" / "policies" / "wiki-maintainer-policy.yaml"
            policy_path.write_text(
                policy_path.read_text(encoding="utf-8").replace(
                    "  allowed_failure_modes:\n"
                    "    - branch_growth_without_test_growth\n"
                    "    - high_complexity_low_test_pressure\n"
                    "    - schema_change_without_test_guardrails\n"
                    "    - policy_surface_growth_without_eval_gain\n"
                    "    - repeated_same_eval_or_discard\n"
                    "    - repeated_same_eval_after_promote\n"
                    "    - repeated_discard_runs\n"
                    "    - bootstrap_history_insufficient\n"
                    "    - recent_log_overlap_queue_blocked\n"
                    "    - next_run_failure_repair\n",
                    "  allowed_failure_modes:\n"
                    "    - branch_growth_without_test_growth\n"
                    "    - high_complexity_low_test_pressure\n"
                    "    - schema_change_without_test_guardrails\n"
                    "    - policy_surface_growth_without_eval_gain\n"
                    "    - repeated_same_eval_or_discard\n"
                    "    - repeated_same_eval_after_promote\n"
                    "    - bootstrap_history_insufficient\n"
                    "    - recent_log_overlap_queue_blocked\n"
                    "    - next_run_failure_repair\n",
                    1,
                ),
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            schema = load_schema(vault / "ops" / "schemas" / "mutation-proposals.schema.json")

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["proposals_emitted"], 3)
            proposals_by_source = {proposal["source_candidate_type"]: proposal for proposal in report["proposals"]}
            stagnation = proposals_by_source["mechanism_eval_stagnation_candidate"]
            self.assertEqual(stagnation["failure_mode"], "repeated_same_eval_after_promote")
            self.assertEqual(stagnation["metrics_triggered"], ["stage1_same_eval_rate"])
            self.assertNotIn(
                "repeated_discard_runs",
                {proposal["failure_mode"] for proposal in report["proposals"]},
            )
            self.assertEqual(
                report["diagnostics"]["skipped_candidates"],
                [
                    {
                        "candidate_id": "mechanism_eval_stagnation_candidate__promotion-gate",
                        "reason": "closed_remediation_backlog_resolution",
                        "detail": (
                            "closed remediation backlog item(s): "
                            "negative_lesson_discard_equal_score_secondary_eligibility"
                        ),
                    }
                ],
            )

    def test_closed_repeated_discard_remediation_stays_terminal_without_other_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            report = mechanism_review_report()
            candidate = dict(report["candidates"][0])
            candidate["metrics_triggered"] = ["repeated_discard_runs"]
            candidate["signal_run_ids"] = {"repeated_discard_runs": ["run-a", "run-b"]}
            report["summary"]["candidates_emitted"] = 1
            report["candidates"] = [candidate]
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            write_json(
                vault / "ops" / "reports" / "remediation-backlog.json",
                {
                    "status": "attention",
                    "summary": {"open_total_count": 0},
                    "items": [
                        {
                            "item_id": "negative_lesson_discard_equal_score_secondary_eligibility",
                            "blocker_id": "discard_equal_score_secondary_eligibility",
                            "status": "closed",
                            "severity": "blocks_repeat",
                            "repair_target": "Closed discard-only repeat remediation.",
                            "next_action": "No new independent signal is available.",
                        },
                    ],
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            schema = load_schema(vault / "ops" / "schemas" / "mutation-proposals.schema.json")

            self.assertEqual(validate_with_schema(proposal_report, schema), [])
            self.assertEqual(proposal_report["status"], "attention")
            self.assertEqual(proposal_report["summary"]["proposals_emitted"], 0)
            self.assertEqual(proposal_report["summary"]["blocked_proposals"], 1)
            self.assertEqual(proposal_report["proposals"], [])
            self.assertEqual(
                proposal_report["diagnostics"]["empty_queue_blockers"],
                [
                    {
                        "blocker_type": "source",
                        "reason": "closed_remediation_backlog_resolution",
                        "detail": (
                            "closed remediation backlog item(s): "
                            "negative_lesson_discard_equal_score_secondary_eligibility"
                        ),
                        "source": "skipped_candidates",
                        "candidate_id": "mechanism_eval_stagnation_candidate__promotion-gate",
                    }
                ],
            )

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

    def test_promoted_next_run_repair_closes_queue_unblock_rework(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "outcome-metrics.json",
                {
                    "recent_attempts": [
                        {
                            "run_id": "auto-improve-trial-10-run-01-mechanism-run-validation-runtime",
                            "proposal_id": (
                                "next_run_failure_repair__mechanism-run-validation-runtime__"
                                "equal-score-secondary-eligibility"
                            ),
                            "source_candidate_id": (
                                "next-run-decision:"
                                "auto-improve-trial-9-run-01-mechanism-run-validation-runtime:"
                                "af4b86e34efb67d5"
                            ),
                            "outcome": "promoted",
                            "decision": "PROMOTE",
                            "primary_targets": [
                                "ops/scripts/mechanism/mechanism_run_validation_runtime.py"
                            ],
                        },
                        {
                            "run_id": "auto-improve-trial-9-run-01-mechanism-run-validation-runtime",
                            "proposal_id": (
                                "recent_log_overlap_queue_blocked__"
                                "mechanism-run-validation-runtime"
                            ),
                            "outcome": "discarded",
                            "decision": "DISCARD",
                            "primary_targets": [
                                "ops/scripts/mechanism/mechanism_run_validation_runtime.py"
                            ],
                        },
                        {
                            "run_id": "auto-improve-trial-8-run-01-mutation-proposal-runtime",
                            "proposal_id": (
                                "recent_log_overlap_queue_blocked__mutation-proposal-runtime"
                            ),
                            "outcome": "mutation_failed",
                            "decision": "HOLD",
                            "primary_targets": [
                                "ops/scripts/mechanism/mutation_proposal_runtime.py"
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
                "- `ops/scripts/mechanism/mutation_proposal_runtime.py`\n",
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
            self.assertEqual(rotation["failure_mode"], "recent_log_overlap_queue_blocked")
            self.assertEqual(
                rotation["proposal_id"],
                "recent_log_overlap_queue_blocked__mechanism-run-validation-runtime",
            )
            self.assertEqual(rotation["blocked_by"], [])

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
                    "ops/script-output-surfaces.json",
                ],
            )

    def test_repeated_discard_proposal_keeps_mutation_scope_to_primary_target(self) -> None:
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
            broad_supporting_targets = [
                "ops/schemas/run-telemetry.schema.json",
                "ops/script-output-surfaces.json",
                "tests/fixtures/report_schema_samples.json",
                "ops/scripts/core/artifact_freshness_runtime.py",
            ]
            for rel_path in broad_supporting_targets:
                path = vault / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
            (vault / "tests" / "test_auto_improve_iteration_runtime.py").write_text(
                (
                    "from ops.scripts.mechanism.auto_improve_iteration_persistence_runtime "
                    "import persist_iteration_state\n\n"
                    "def test_placeholder() -> None:\n"
                    "    assert persist_iteration_state is not None\n"
                ),
                encoding="utf-8",
            )
            (vault / "tests" / "test_report_schema_sample_regeneration.py").write_text(
                "def test_placeholder() -> None:\n    assert True\n",
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
                    "supporting_targets": broad_supporting_targets,
                    "metrics_triggered": ["repeated_discard_runs"],
                    "run_ids": ["run-1", "run-2"],
                    "evidence": {"runs_examined": 2, "same_eval_runs": 0, "discard_runs": 2},
                    "rationale": "fixture",
                    "suggested_experiments": [f"try one mechanism-only experiment on {target}"],
                }
            ]
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", report)
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path)

            proposal = proposal_report["proposals"][0]
            self.assertEqual(proposal["failure_mode"], "repeated_discard_runs")
            self.assertEqual(proposal["primary_targets"], [target])
            self.assertEqual(proposal["supporting_targets"], [])
            self.assertEqual(
                proposal["must_change_tests"],
                ["tests/test_auto_improve_iteration_runtime.py"],
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
            self.assertEqual(
                proposal_report["proposals"][0]["source_candidate_type"],
                "mechanism_bootstrap_history_candidate",
            )
            self.assertEqual(
                proposal_report["proposals"][0]["blocked_by"],
                ["bootstrap_history_insufficient"],
            )
            self.assertEqual(
                proposal_report["proposals"][0]["primary_targets"],
                ["ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"],
            )
            self.assertEqual(
                proposal_report["proposals"][0]["must_change_tests"],
                ["tests/test_auto_improve_iteration_runtime.py"],
            )
            self.assertEqual(
                proposal_report["proposals"][0]["run_ids"],
                ["run-1"],
            )

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
            self.assertEqual(
                proposal_report["proposals"][0]["supporting_targets"],
                ["ops/schemas/run-telemetry.schema.json"],
            )
            self.assertEqual(
                proposal_report["proposals"][0]["must_change_tests"],
                ["tests/test_auto_improve_iteration_runtime.py"],
            )
            self.assertEqual(
                proposal_report["proposals"][0]["blocked_by"],
                ["no_history"],
            )
            self.assertEqual(
                proposal_report["proposals"][0]["run_ids"],
                ["bootstrap-no-history"],
            )

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

    def test_open_next_run_decision_emits_priority_repair_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            (vault / "ops" / "scripts" / "mechanism" / "example_runtime.py").parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            (vault / "ops" / "scripts" / "mechanism" / "example_runtime.py").write_text(
                "VALUE = 1\n",
                encoding="utf-8",
            )
            (vault / "tests" / "test_example_runtime.py").write_text(
                "def test_example_runtime():\n    assert True\n",
                encoding="utf-8",
            )
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:review",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": "auto-session-a-run-01-example-runtime",
                            "proposal_id": "original-proposal",
                            "source_candidate_id": "original-candidate",
                            "target_proposal_id": (
                                "next_run_failure_repair__example-runtime__review-blocked"
                            ),
                            "proposal_family": "contract_regression_signals",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "review_blocked",
                            "blocking_role": "reviewer",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "review failure should become next-run repair work",
                            "quarantined_source_proposal": True,
                            "primary_targets": [
                                "ops/scripts/mechanism/example_runtime.py"
                            ],
                            "supporting_targets": ["ops/script-output-surfaces.json"],
                            "must_change_tests": ["tests/test_example_runtime.py"],
                            "evidence_paths": [
                                "runs/auto-session-a-run-01-example-runtime/run-telemetry.json",
                                (
                                    "runs/auto-session-a-run-01-example-runtime/"
                                    "reviewer-executor-report.json"
                                ),
                            ],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            repair_proposals = [
                proposal
                for proposal in proposal_report["proposals"]
                if proposal["failure_mode"] == "next_run_failure_repair"
            ]

            self.assertEqual(len(repair_proposals), 1)
            repair = repair_proposals[0]
            self.assertEqual(
                repair["proposal_id"],
                "next_run_failure_repair__example-runtime__review-blocked",
            )
            self.assertEqual(repair["priority"], 100)
            self.assertEqual(
                repair["source_candidate_type"],
                "auto_improve_next_run_decision_candidate",
            )
            self.assertEqual(repair["run_ids"], ["auto-session-a-run-01-example-runtime"])
            self.assertIn(
                "ops/reports/auto-improve-sessions/session-a.json",
                repair["supporting_targets"],
            )
            self.assertEqual(repair["blocked_by"], [])
            self.assertEqual(proposal_report["summary"]["next_run_repair_proposals"], 1)
            self.assertEqual(
                [proposal["failure_mode"] for proposal in proposal_report["proposals"]],
                ["next_run_failure_repair"],
            )
            self.assertEqual(proposal_report["summary"]["proposals_emitted"], 1)
            self.assertGreater(
                proposal_report["diagnostics"]["queue_selection"][
                    "available_proposal_count"
                ],
                1,
            )
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"][
                    "selected_proposal_count"
                ],
                1,
            )
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"]["selection_mode"],
                "carry_forward_repair_only",
            )
            self.assertGreater(
                proposal_report["diagnostics"]["queue_selection"][
                    "repair_priority_suppressed_count"
                ],
                0,
            )
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"],
                {
                    "session_reports_scanned": 1,
                    "decisions_considered": 1,
                    "open_carry_forward_decisions": 1,
                    "repair_proposals_emitted": 1,
                    "decision_counts": {"carry_forward": 1},
                    "action_counts": {"repair_failure": 1},
                    "selected_target_proposal_ids": [
                        "next_run_failure_repair__example-runtime__review-blocked"
                    ],
                },
            )

    def test_next_run_decision_adds_schema_sample_regeneration_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            script_target = "ops/scripts/mechanism/example_runtime.py"
            schema_target = "ops/schemas/example-report.schema.json"
            (vault / script_target).parent.mkdir(parents=True, exist_ok=True)
            (vault / script_target).write_text("VALUE = 1\n", encoding="utf-8")
            (vault / schema_target).write_text('{"type": "object"}\n', encoding="utf-8")
            (vault / "ops" / "script-output-surfaces.json").write_text("{}\n", encoding="utf-8")
            (vault / "tests" / "test_example_runtime.py").write_text(
                "def test_example_runtime():\n    assert True\n",
                encoding="utf-8",
            )
            (vault / "tests" / "test_report_schema_sample_regeneration.py").write_text(
                "def test_report_schema_sample_regeneration():\n    assert True\n",
                encoding="utf-8",
            )
            (vault / "tests" / "fixtures").mkdir(parents=True, exist_ok=True)
            (vault / "tests" / "fixtures" / "report_schema_samples.json").write_text(
                "{}\n",
                encoding="utf-8",
            )
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:validation",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 3,
                            "source_run_id": "auto-session-a-run-03-example-runtime",
                            "proposal_id": "original-proposal",
                            "source_candidate_id": "original-candidate",
                            "target_proposal_id": (
                                "next_run_failure_repair__example-runtime__validation-blocked"
                            ),
                            "proposal_family": "contract_regression_signals",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "validation_blocked",
                            "blocking_role": "validator",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "schema sample freshness should become next-run repair work",
                            "quarantined_source_proposal": True,
                            "primary_targets": [script_target],
                            "supporting_targets": [schema_target],
                            "must_change_tests": ["tests/test_example_runtime.py"],
                            "evidence_paths": [
                                "runs/auto-session-a-run-03-example-runtime/run-telemetry.json",
                                (
                                    "runs/auto-session-a-run-03-example-runtime/"
                                    "validator-executor-report.json"
                                ),
                            ],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            repair = next(
                proposal
                for proposal in proposal_report["proposals"]
                if proposal["failure_mode"] == "next_run_failure_repair"
            )

            self.assertEqual(
                repair["proposal_id"],
                "next_run_failure_repair__example-runtime__validation-blocked",
            )
            self.assertEqual(
                repair["supporting_targets"],
                [
                    schema_target,
                    "ops/script-output-surfaces.json",
                    "tests/fixtures/report_schema_samples.json",
                    "ops/reports/auto-improve-sessions/session-a.json",
                ],
            )
            self.assertEqual(
                repair["must_change_tests"],
                [
                    "tests/test_example_runtime.py",
                    "tests/test_report_schema_sample_regeneration.py",
                ],
            )
            self.assertTrue(repair["must_not_expand_apply_roots"])

    def test_next_run_decision_adds_changed_files_scope_from_source_run_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            script_target = "ops/scripts/mechanism/example_runtime.py"
            declared_test = "tests/test_example_runtime.py"
            extra_test = "tests/test_report_schemas.py"
            (vault / script_target).parent.mkdir(parents=True, exist_ok=True)
            (vault / script_target).write_text("VALUE = 1\n", encoding="utf-8")
            (vault / declared_test).write_text(
                "def test_example_runtime():\n    assert True\n",
                encoding="utf-8",
            )
            (vault / extra_test).write_text(
                "def test_report_schema_scope():\n    assert True\n",
                encoding="utf-8",
            )
            source_run_id = "auto-session-a-run-01-example-runtime"
            run_dir = vault / "runs" / source_run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(
                run_dir / "changed-files-manifest.json",
                {
                    "declared_targets": {
                        "primary_targets": [script_target],
                        "supporting_targets": ["ops/script-output-surfaces.json"],
                        "test_files": [declared_test],
                    },
                    "files": [
                        {"path": script_target, "change_type": "modified"},
                        {"path": declared_test, "change_type": "modified"},
                        {"path": extra_test, "change_type": "modified"},
                    ],
                },
            )
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:changed-files",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": source_run_id,
                            "proposal_id": "original-proposal",
                            "source_candidate_id": "original-candidate",
                            "target_proposal_id": (
                                "next_run_failure_repair__example-runtime__changed-files-manifest-scope"
                            ),
                            "proposal_family": "next_run_failure_repair",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "changed_files_manifest_scope",
                            "blocking_role": "promotion_gate",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "changed-files scope should become bounded repair work",
                            "quarantined_source_proposal": False,
                            "primary_targets": [script_target],
                            "supporting_targets": ["ops/script-output-surfaces.json"],
                            "must_change_tests": [declared_test],
                            "evidence_paths": [
                                f"runs/{source_run_id}/run-telemetry.json",
                                f"runs/{source_run_id}/promotion-report.json",
                            ],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            repair = next(
                proposal
                for proposal in proposal_report["proposals"]
                if proposal["failure_mode"] == "next_run_failure_repair"
            )

            self.assertEqual(
                repair["proposal_id"],
                "next_run_failure_repair__example-runtime__changed-files-manifest-scope",
            )
            self.assertEqual(repair["must_change_tests"], [declared_test, extra_test])

    def test_next_run_decision_adds_reviewer_diagnostic_paths_to_repair_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            primary_target = "ops/scripts/mechanism/example_runtime.py"
            diagnostic_target = "ops/scripts/mechanism/example_outcome_runtime.py"
            diagnostic_test = "tests/test_example_outcome_runtime.py"
            for path, content in (
                (primary_target, "VALUE = 1\n"),
                (diagnostic_target, "VALUE = 2\n"),
                (diagnostic_test, "def test_example_outcome_runtime():\n    assert True\n"),
            ):
                file_path = vault / path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")
            source_run_id = "auto-session-a-run-02-example-runtime"
            run_dir = vault / "runs" / source_run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(
                run_dir / "reviewer-executor-report.json",
                {
                    "status": "fail",
                    "diagnostics": {
                        "notes": [
                            (
                                "Finding P1: repair also needs "
                                f"{diagnostic_target}:42 and {diagnostic_test}:7."
                            )
                        ]
                    },
                },
            )
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:review",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 2,
                            "source_run_id": source_run_id,
                            "proposal_id": "original-proposal",
                            "source_candidate_id": "original-candidate",
                            "target_proposal_id": (
                                "next_run_failure_repair__example-runtime__review-blocked"
                            ),
                            "proposal_family": "next_run_failure_repair",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "review_blocked",
                            "blocking_role": "reviewer",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "review failure should become bounded repair work",
                            "quarantined_source_proposal": True,
                            "primary_targets": [primary_target],
                            "supporting_targets": ["ops/script-output-surfaces.json"],
                            "must_change_tests": ["tests/test_example_runtime.py"],
                            "evidence_paths": [
                                f"runs/{source_run_id}/reviewer-executor-report.json",
                            ],
                        }
                    ]
                },
            )
            (vault / "tests" / "test_example_runtime.py").write_text(
                "def test_example_runtime():\n    assert True\n",
                encoding="utf-8",
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            repair = next(
                proposal
                for proposal in proposal_report["proposals"]
                if proposal["failure_mode"] == "next_run_failure_repair"
            )

            self.assertIn(diagnostic_target, repair["supporting_targets"])
            self.assertIn(diagnostic_test, repair["must_change_tests"])

    def test_next_run_decision_keeps_source_session_report_with_diagnostic_ancestry(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            primary_target = "ops/scripts/mechanism/example_runtime.py"
            diagnostic_session = "ops/reports/auto-improve-sessions/prior-session.json"
            source_session = "ops/reports/auto-improve-sessions/session-a.json"
            (vault / primary_target).parent.mkdir(parents=True, exist_ok=True)
            (vault / primary_target).write_text("VALUE = 1\n", encoding="utf-8")
            (vault / "tests" / "test_example_runtime.py").write_text(
                "def test_example_runtime():\n    assert True\n",
                encoding="utf-8",
            )
            write_json(vault / diagnostic_session, {"next_run_decisions": []})
            source_run_id = "auto-session-a-run-03-example-runtime"
            provenance_report = vault / "runs" / source_run_id / "provenance-auditor-executor-report.json"
            write_json(
                provenance_report,
                {
                    "status": "fail",
                    "diagnostics": {
                        "notes": [
                            f"Prior ancestry is recorded in `{diagnostic_session}`."
                        ]
                    },
                },
            )
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / source_session,
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:structural",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 3,
                            "source_run_id": source_run_id,
                            "proposal_id": "next_run_failure_repair__example-runtime__validation-blocked",
                            "source_candidate_id": "next-run-decision:prior:validation",
                            "target_proposal_id": (
                                "next_run_failure_repair__example-runtime__structural-complexity-non-regression"
                            ),
                            "proposal_family": "next_run_failure_repair",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "structural_complexity_non_regression",
                            "blocking_role": "promotion_gate",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "structural non-regression should remain bounded to exact source evidence",
                            "quarantined_source_proposal": False,
                            "primary_targets": [primary_target],
                            "supporting_targets": ["ops/script-output-surfaces.json"],
                            "must_change_tests": ["tests/test_example_runtime.py"],
                            "evidence_paths": [
                                f"runs/{source_run_id}/provenance-auditor-executor-report.json"
                            ],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            repair = next(
                proposal
                for proposal in proposal_report["proposals"]
                if proposal["failure_mode"] == "next_run_failure_repair"
            )

            self.assertIn(source_session, repair["supporting_targets"])
            self.assertIn(diagnostic_session, repair["supporting_targets"])

    def test_consumed_next_run_decision_does_not_emit_repair_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            decision_id = "next-run-decision:run-a:review"
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": decision_id,
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": "auto-session-a-run-01-example-runtime",
                            "proposal_id": "original-proposal",
                            "source_candidate_id": "original-candidate",
                            "target_proposal_id": (
                                "next_run_failure_repair__example-runtime__review-blocked"
                            ),
                            "proposal_family": "contract_regression_signals",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "review_blocked",
                            "blocking_role": "reviewer",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "review failure should become next-run repair work",
                            "quarantined_source_proposal": True,
                            "primary_targets": [
                                "ops/scripts/mechanism/example_runtime.py"
                            ],
                            "supporting_targets": ["ops/script-output-surfaces.json"],
                            "must_change_tests": ["tests/test_example_runtime.py"],
                            "evidence_paths": [
                                "runs/auto-session-a-run-01-example-runtime/run-telemetry.json"
                            ],
                        }
                    ]
                },
            )
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-b.json",
                {
                    "iterations": [
                        {
                            "index": 1,
                            "proposal_id": "next_run_failure_repair__example-runtime__review-blocked",
                            "source_candidate_id": decision_id,
                            "run_id": "auto-session-b-run-01-example-runtime",
                            "status": "blocked",
                            "outcome": "mutation_failed",
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))

            self.assertEqual(proposal_report["summary"]["next_run_repair_proposals"], 0)
            self.assertFalse(
                any(
                    proposal["failure_mode"] == "next_run_failure_repair"
                    for proposal in proposal_report["proposals"]
                )
            )
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"],
                {
                    "session_reports_scanned": 2,
                    "decisions_considered": 1,
                    "open_carry_forward_decisions": 0,
                    "repair_proposals_emitted": 0,
                    "decision_counts": {"carry_forward": 1},
                    "action_counts": {"repair_failure": 1},
                    "selected_target_proposal_ids": [],
                },
            )

    def test_consumed_newer_next_run_decision_suppresses_older_same_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            older_decision_id = "next-run-decision:run-a:review"
            newer_decision_id = "next-run-decision:run-b:review"
            target_proposal_id = "next_run_failure_repair__example-runtime__review-blocked"
            decision_template = {
                "session_id": "auto-session-a",
                "iteration": 1,
                "proposal_id": "original-proposal",
                "source_candidate_id": "original-candidate",
                "target_proposal_id": target_proposal_id,
                "proposal_family": "contract_regression_signals",
                "proposal_tier": "supporting",
                "failure_taxonomy": "review_blocked",
                "blocking_role": "reviewer",
                "decision": "carry_forward",
                "next_run_action": "repair_failure",
                "status": "open",
                "reason": "review failure should become next-run repair work",
                "quarantined_source_proposal": True,
                "primary_targets": ["ops/scripts/mechanism/example_runtime.py"],
                "supporting_targets": ["ops/script-output-surfaces.json"],
                "must_change_tests": ["tests/test_example_runtime.py"],
                "evidence_paths": ["runs/auto-session-a-run-01-example-runtime/run-telemetry.json"],
            }
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            **decision_template,
                            "decision_id": older_decision_id,
                            "observed_at": "2026-04-14T02:00:00Z",
                            "source_run_id": "auto-session-a-run-01-example-runtime",
                        }
                    ]
                },
            )
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-b.json",
                {
                    "next_run_decisions": [
                        {
                            **decision_template,
                            "decision_id": newer_decision_id,
                            "observed_at": "2026-04-14T03:00:00Z",
                            "source_run_id": "auto-session-b-run-01-example-runtime",
                        }
                    ]
                },
            )
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-c.json",
                {
                    "iterations": [
                        {
                            "index": 1,
                            "proposal_id": target_proposal_id,
                            "source_candidate_id": newer_decision_id,
                            "run_id": "auto-session-c-run-01-example-runtime",
                            "status": "blocked",
                            "outcome": "discarded",
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))

            self.assertEqual(proposal_report["summary"]["next_run_repair_proposals"], 0)
            self.assertFalse(
                any(
                    proposal["failure_mode"] == "next_run_failure_repair"
                    for proposal in proposal_report["proposals"]
                )
            )
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"],
                {
                    "session_reports_scanned": 3,
                    "decisions_considered": 2,
                    "open_carry_forward_decisions": 0,
                    "repair_proposals_emitted": 0,
                    "decision_counts": {"carry_forward": 2},
                    "action_counts": {"repair_failure": 2},
                    "selected_target_proposal_ids": [],
                },
            )

    def test_stale_session_decision_does_not_emit_next_run_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json_exact(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    **auto_improve_session_envelope("2026-04-14T01:00:00Z"),
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:review",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": "auto-session-a-run-01-example-runtime",
                            "proposal_id": "original-proposal",
                            "source_candidate_id": "original-candidate",
                            "target_proposal_id": (
                                "next_run_failure_repair__example-runtime__review-blocked"
                            ),
                            "proposal_family": "contract_regression_signals",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "review_blocked",
                            "blocking_role": "reviewer",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "stale decision should not become next-run repair work",
                            "quarantined_source_proposal": True,
                            "primary_targets": [
                                "ops/scripts/mechanism/example_runtime.py"
                            ],
                            "supporting_targets": ["ops/script-output-surfaces.json"],
                            "must_change_tests": ["tests/test_example_runtime.py"],
                            "evidence_paths": [
                                "runs/auto-session-a-run-01-example-runtime/run-telemetry.json"
                            ],
                        }
                    ],
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))

            self.assertEqual(proposal_report["summary"]["next_run_repair_proposals"], 0)
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"]["decisions_considered"],
                0,
            )
            self.assertFalse(
                any(
                    proposal["failure_mode"] == "next_run_failure_repair"
                    for proposal in proposal_report["proposals"]
                )
            )

    def test_stale_consumed_iteration_does_not_close_fresh_next_run_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            decision_id = "next-run-decision:run-a:review"
            write_json_exact(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    **auto_improve_session_envelope("2026-04-14T02:05:00Z"),
                    "next_run_decisions": [
                        {
                            "decision_id": decision_id,
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": "auto-session-a-run-01-example-runtime",
                            "proposal_id": "original-proposal",
                            "source_candidate_id": "original-candidate",
                            "target_proposal_id": (
                                "next_run_failure_repair__example-runtime__review-blocked"
                            ),
                            "proposal_family": "contract_regression_signals",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "review_blocked",
                            "blocking_role": "reviewer",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "fresh decision should become next-run repair work",
                            "quarantined_source_proposal": True,
                            "primary_targets": [
                                "ops/scripts/mechanism/example_runtime.py"
                            ],
                            "supporting_targets": ["ops/script-output-surfaces.json"],
                            "must_change_tests": ["tests/test_example_runtime.py"],
                            "evidence_paths": [
                                "runs/auto-session-a-run-01-example-runtime/run-telemetry.json"
                            ],
                        }
                    ],
                },
            )
            write_json_exact(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-b.json",
                {
                    **auto_improve_session_envelope("2026-04-14T01:30:00Z"),
                    "iterations": [
                        {
                            "index": 1,
                            "proposal_id": (
                                "next_run_failure_repair__example-runtime__review-blocked"
                            ),
                            "source_candidate_id": decision_id,
                            "run_id": "auto-session-b-run-01-example-runtime",
                            "status": "blocked",
                            "outcome": "mutation_failed",
                        }
                    ],
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            repair_proposals = [
                proposal
                for proposal in proposal_report["proposals"]
                if proposal["failure_mode"] == "next_run_failure_repair"
            ]

            self.assertEqual(len(repair_proposals), 1)
            self.assertEqual(
                repair_proposals[0]["proposal_id"],
                "next_run_failure_repair__example-runtime__review-blocked",
            )
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"],
                {
                    "session_reports_scanned": 2,
                    "decisions_considered": 1,
                    "open_carry_forward_decisions": 1,
                    "repair_proposals_emitted": 1,
                    "decision_counts": {"carry_forward": 1},
                    "action_counts": {"repair_failure": 1},
                    "selected_target_proposal_ids": [
                        "next_run_failure_repair__example-runtime__review-blocked"
                    ],
                },
            )

    def test_noop_queue_unblock_mutation_failure_does_not_emit_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            primary_target = "ops/scripts/mechanism/example_runtime.py"
            (vault / primary_target).parent.mkdir(parents=True, exist_ok=True)
            (vault / primary_target).write_text("VALUE = 1\n", encoding="utf-8")
            (vault / "tests" / "test_example_runtime.py").write_text(
                "def test_example_runtime():\n    assert True\n",
                encoding="utf-8",
            )
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            source_run_id = "auto-session-a-run-01-example-runtime"
            run_dir = vault / "runs" / source_run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "mutation-command.stderr.txt").write_text(
                (
                    "worker reported pass without modifying any declared primary target; "
                    f"primary_targets=[{primary_target}]\n"
                ),
                encoding="utf-8",
            )
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:queue-unblock",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": source_run_id,
                            "proposal_id": "recent_log_overlap_queue_blocked__example-runtime",
                            "source_candidate_id": "recent_log_overlap_queue_unblock__example-runtime",
                            "target_proposal_id": (
                                "next_run_failure_repair__example-runtime__mutation-failed"
                            ),
                            "proposal_family": "queue_unblock",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "mutation_failed",
                            "blocking_role": "worker",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "queue unblock no-op should not cycle as next-run repair work",
                            "quarantined_source_proposal": True,
                            "primary_targets": [primary_target],
                            "supporting_targets": ["ops/script-output-surfaces.json"],
                            "must_change_tests": ["tests/test_example_runtime.py"],
                            "evidence_paths": [
                                f"runs/{source_run_id}/run-telemetry.json",
                                f"runs/{source_run_id}/worker-executor-report.json",
                            ],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            repair_proposals = [
                proposal
                for proposal in proposal_report["proposals"]
                if proposal["failure_mode"] == "next_run_failure_repair"
            ]

            self.assertEqual(len(repair_proposals), 0)
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"][
                    "open_carry_forward_decisions"
                ],
                0,
            )
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"][
                    "selected_target_proposal_ids"
                ],
                [],
            )

    def test_resolved_repo_health_schema_debt_does_not_emit_repair_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            primary_target = "ops/scripts/mechanism/example_runtime.py"
            schema_path = "ops/schemas/generated-report.schema.json"
            report_path = "ops/reports/generated-report.json"
            (vault / primary_target).parent.mkdir(parents=True, exist_ok=True)
            (vault / primary_target).write_text("VALUE = 1\n", encoding="utf-8")
            write_json(
                vault / schema_path,
                {
                    "type": "object",
                    "required": ["$schema", "status"],
                    "properties": {
                        "$schema": {"type": "string"},
                        "status": {"const": "pass"},
                    },
                    "additionalProperties": True,
                },
            )
            write_json(
                vault / report_path,
                {
                    "$schema": schema_path,
                    "status": "pass",
                },
            )
            source_run_id = "auto-session-a-run-01-example-runtime"
            source_run = vault / "runs" / source_run_id
            source_run.mkdir(parents=True, exist_ok=True)
            write_json(
                source_run / "repo-health-artifact-freshness-report-check.json",
                {
                    "status": "fail",
                    "recommended_next_action": "regenerate_schema_invalid_artifacts",
                    "top_debt_files": [
                        {
                            "path": report_path,
                            "primary_issue": "schema_validation_failed",
                            "issues": ["schema_validation_failed"],
                        }
                    ],
                },
            )
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:repo-health",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": source_run_id,
                            "proposal_id": "next_run_failure_repair__example-runtime__review-blocked",
                            "source_candidate_id": "next-run-decision:prior-review",
                            "target_proposal_id": (
                                "next_run_failure_repair__example-runtime__repo-health-blocked"
                            ),
                            "proposal_family": "next_run_failure_repair",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "repo_health_blocked",
                            "blocking_role": "repo_health",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "artifact freshness failure should be repaired only while it still reproduces",
                            "quarantined_source_proposal": True,
                            "primary_targets": [primary_target],
                            "supporting_targets": [report_path],
                            "must_change_tests": ["tests/test_example_runtime.py"],
                            "evidence_paths": [
                                f"runs/{source_run_id}/repo-health-artifact-freshness-report-check.json"
                            ],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))

            self.assertEqual(proposal_report["summary"]["next_run_repair_proposals"], 0)
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"][
                    "open_carry_forward_decisions"
                ],
                0,
            )
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"][
                    "selected_target_proposal_ids"
                ],
                [],
            )

    def test_resolved_artifact_freshness_schema_debt_does_not_emit_repair_proposal(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            primary_target = "ops/scripts/mechanism/example_runtime.py"
            schema_path = "ops/schemas/generated-report.schema.json"
            report_path = "ops/reports/generated-report.json"
            (vault / primary_target).parent.mkdir(parents=True, exist_ok=True)
            (vault / primary_target).write_text("VALUE = 1\n", encoding="utf-8")
            write_json(
                vault / schema_path,
                {
                    "type": "object",
                    "required": ["$schema", "status"],
                    "properties": {
                        "$schema": {"type": "string"},
                        "status": {"const": "pass"},
                    },
                    "additionalProperties": True,
                },
            )
            write_json(
                vault / report_path,
                {
                    "$schema": schema_path,
                    "status": "pass",
                },
            )
            source_run_id = "auto-session-a-run-01-example-runtime"
            source_run = vault / "runs" / source_run_id
            source_run.mkdir(parents=True, exist_ok=True)
            write_json(
                source_run / "repo-health-artifact-freshness-report-check.json",
                {
                    "status": "fail",
                    "recommended_next_action": "regenerate_schema_invalid_artifacts",
                    "top_debt_files": [
                        {
                            "path": report_path,
                            "primary_issue": "schema_validation_failed",
                            "issues": ["schema_validation_failed"],
                        }
                    ],
                },
            )
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:repo-health",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": source_run_id,
                            "proposal_id": "next_run_failure_repair__example-runtime__review-blocked",
                            "source_candidate_id": "next-run-decision:prior-review",
                            "target_proposal_id": (
                                "next_run_failure_repair__example-runtime__"
                                "artifact-freshness-schema-validation-failed"
                            ),
                            "proposal_family": "next_run_failure_repair",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "artifact_freshness_schema_validation_failed",
                            "blocking_role": "repo_health",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "clean artifact freshness failures should not stay queued",
                            "quarantined_source_proposal": True,
                            "primary_targets": [primary_target],
                            "supporting_targets": [report_path],
                            "must_change_tests": ["tests/test_example_runtime.py"],
                            "evidence_paths": [
                                f"runs/{source_run_id}/repo-health-artifact-freshness-report-check.json"
                            ],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))

            self.assertEqual(proposal_report["summary"]["next_run_repair_proposals"], 0)
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"][
                    "open_carry_forward_decisions"
                ],
                0,
            )
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"][
                    "selected_target_proposal_ids"
                ],
                [],
            )

    def test_clean_raw_registry_export_suppresses_stale_next_run_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_raw_registry_vault(vault)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())

            from ops.scripts.raw_registry_export import (
                build_current_raw_registry_export,
            )

            export, destination = build_current_raw_registry_export(vault)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(export, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            source_run_id = "auto-session-a-run-01-raw-registry"
            run_dir = vault / "runs" / source_run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(
                run_dir / "validator-last-message.json",
                {
                    "diagnostics": {
                        "notes": [
                            "raw_registry_content_sha256_mismatch was observed in `ops/raw-registry.json`."
                        ]
                    }
                },
            )
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:raw-registry",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": source_run_id,
                            "proposal_id": "next_run_failure_repair__registry-runtime__validation-blocked",
                            "source_candidate_id": "next-run-decision:prior-validation",
                            "target_proposal_id": (
                                "next_run_failure_repair__registry-runtime__validation-blocked"
                            ),
                            "proposal_family": "next_run_failure_repair",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "validation_blocked",
                            "blocking_role": "validator",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "raw-registry stale export should be repaired only while it still reproduces",
                            "quarantined_source_proposal": True,
                            "primary_targets": [
                                "ops/scripts/registry/raw_registry_runtime.py"
                            ],
                            "supporting_targets": [
                                "ops/raw-registry.json",
                                "ops/reports/raw-registry-preflight-report.json",
                            ],
                            "must_change_tests": ["tests/test_raw_registry_runtime.py"],
                            "evidence_paths": [
                                f"runs/{source_run_id}/validator-last-message.json"
                            ],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))

            self.assertEqual(proposal_report["summary"]["next_run_repair_proposals"], 0)
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"][
                    "open_carry_forward_decisions"
                ],
                0,
            )

    def test_clean_raw_registry_evidence_suppresses_review_blocked_preflight_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_raw_registry_vault(vault)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())

            from ops.scripts.raw_registry_export import (
                build_current_raw_registry_export,
            )

            export, destination = build_current_raw_registry_export(vault)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(export, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            source_run_id = "auto-session-a-run-01-generated-preflight"
            run_dir = vault / "runs" / source_run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(
                run_dir / "reviewer-last-message.json",
                {
                    "diagnostics": {
                        "notes": [
                            "Finding HIGH: `ops/reports/raw-registry-preflight-report.json` "
                            "was stale after the worker patch, but live raw-registry export "
                            "and preflight both passed."
                        ]
                    }
                },
            )
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:generated-preflight",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": source_run_id,
                            "proposal_id": "next_run_failure_repair__runtime__validation-blocked",
                            "source_candidate_id": "next-run-decision:prior-validation",
                            "target_proposal_id": (
                                "next_run_failure_repair__runtime__review-blocked"
                            ),
                            "proposal_family": "next_run_failure_repair",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "review_blocked",
                            "blocking_role": "reviewer",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "generated raw-registry preflight evidence was stale",
                            "quarantined_source_proposal": True,
                            "primary_targets": [
                                "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"
                            ],
                            "supporting_targets": [
                                "ops/reports/raw-registry-preflight-report.json",
                                "ops/scripts/registry/raw_registry_preflight.py",
                            ],
                            "must_change_tests": ["tests/test_raw_registry_preflight.py"],
                            "evidence_paths": [
                                f"runs/{source_run_id}/reviewer-last-message.json"
                            ],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))

            self.assertEqual(proposal_report["summary"]["next_run_repair_proposals"], 0)
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"][
                    "open_carry_forward_decisions"
                ],
                0,
            )

    def test_clean_raw_registry_evidence_does_not_suppress_unrelated_review_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_raw_registry_vault(vault)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())

            from ops.scripts.raw_registry_export import (
                build_current_raw_registry_export,
            )

            export, destination = build_current_raw_registry_export(vault)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(export, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            target = vault / "ops" / "scripts" / "mechanism" / "example_runtime.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("def subject():\n    return 'review'\n", encoding="utf-8")

            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:generic-review",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": "auto-session-a-run-01-generic-review",
                            "proposal_id": "next_run_failure_repair__example-runtime__review-blocked",
                            "source_candidate_id": "next-run-decision:prior-review",
                            "target_proposal_id": (
                                "next_run_failure_repair__example-runtime__review-blocked"
                            ),
                            "proposal_family": "next_run_failure_repair",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "review_blocked",
                            "blocking_role": "reviewer",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "reviewer found an unrelated runtime behavior regression",
                            "quarantined_source_proposal": True,
                            "primary_targets": [
                                "ops/scripts/mechanism/example_runtime.py"
                            ],
                            "supporting_targets": [],
                            "must_change_tests": ["tests/test_example.py"],
                            "evidence_paths": [],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            repair_proposals = [
                proposal
                for proposal in proposal_report["proposals"]
                if proposal["failure_mode"] == "next_run_failure_repair"
            ]

            self.assertEqual(proposal_report["summary"]["next_run_repair_proposals"], 1)
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"][
                    "open_carry_forward_decisions"
                ],
                1,
            )
            self.assertEqual(len(repair_proposals), 1)
            self.assertEqual(
                repair_proposals[0]["proposal_id"],
                "next_run_failure_repair__example-runtime__review-blocked",
            )

    def test_clean_export_with_unclean_live_raw_registry_preflight_keeps_repair_open(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_raw_registry_vault(vault)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())

            from ops.scripts.raw_registry_export import (
                build_current_raw_registry_export,
            )

            export, destination = build_current_raw_registry_export(vault)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(export, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (vault / "raw" / "unregistered.md").write_text("not registered\n", encoding="utf-8")

            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:preflight-unclean",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": "auto-session-a-run-01-preflight-unclean",
                            "proposal_id": "next_run_failure_repair__registry-runtime__review-blocked",
                            "source_candidate_id": "next-run-decision:prior-review",
                            "target_proposal_id": (
                                "next_run_failure_repair__registry-runtime__review-blocked"
                            ),
                            "proposal_family": "next_run_failure_repair",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "review_blocked",
                            "blocking_role": "reviewer",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "raw-registry preflight report remains stale",
                            "quarantined_source_proposal": True,
                            "primary_targets": [
                                "ops/scripts/registry/raw_registry_preflight.py"
                            ],
                            "supporting_targets": [
                                "ops/reports/raw-registry-preflight-report.json"
                            ],
                            "must_change_tests": ["tests/test_raw_registry_preflight.py"],
                            "evidence_paths": [],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))

            self.assertEqual(proposal_report["summary"]["next_run_repair_proposals"], 1)
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"][
                    "open_carry_forward_decisions"
                ],
                1,
            )

    def test_stale_raw_registry_export_keeps_next_run_repair_open(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_raw_registry_vault(vault)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())

            from ops.scripts.raw_registry_export import (
                build_current_raw_registry_export,
            )

            export, destination = build_current_raw_registry_export(vault)
            export["entries"][0]["content_sha256"] = "0" * 64
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(export, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            source_run_id = "auto-session-a-run-01-raw-registry"
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:raw-registry",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": source_run_id,
                            "proposal_id": "next_run_failure_repair__registry-runtime__validation-blocked",
                            "source_candidate_id": "next-run-decision:prior-validation",
                            "target_proposal_id": (
                                "next_run_failure_repair__registry-runtime__validation-blocked"
                            ),
                            "proposal_family": "next_run_failure_repair",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "validation_blocked",
                            "blocking_role": "validator",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "raw-registry stale export should remain repairable",
                            "quarantined_source_proposal": True,
                            "primary_targets": [
                                "ops/scripts/registry/raw_registry_runtime.py"
                            ],
                            "supporting_targets": ["ops/raw-registry.json"],
                            "must_change_tests": ["tests/test_raw_registry_runtime.py"],
                            "evidence_paths": [],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            repair_proposals = [
                proposal
                for proposal in proposal_report["proposals"]
                if proposal["failure_mode"] == "next_run_failure_repair"
            ]

            self.assertEqual(len(repair_proposals), 1)
            self.assertEqual(
                repair_proposals[0]["proposal_id"],
                "next_run_failure_repair__registry-runtime__validation-blocked",
            )
            self.assertNotIn(
                "ops/raw-registry.json",
                repair_proposals[0]["supporting_targets"],
            )

    def test_raw_registry_export_repair_demotes_local_cache_primary_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_raw_registry_vault(vault)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())

            from ops.scripts.raw_registry_export import (
                build_current_raw_registry_export,
            )

            export, destination = build_current_raw_registry_export(vault)
            export["entries"][0]["content_sha256"] = "0" * 64
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(export, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:raw-registry-cache",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": "auto-session-a-run-01-raw-registry",
                            "proposal_id": "next_run_failure_repair__raw-registry__validation-blocked",
                            "source_candidate_id": "next-run-decision:prior-validation",
                            "target_proposal_id": (
                                "next_run_failure_repair__raw-registry__validation-blocked"
                            ),
                            "proposal_family": "next_run_failure_repair",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "validation_blocked",
                            "blocking_role": "validator",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "raw-registry stale export should repair the producer, not the cache",
                            "quarantined_source_proposal": True,
                            "primary_targets": ["ops/raw-registry.json"],
                            "supporting_targets": [
                                "ops/raw-registry.json",
                                "ops/reports/raw-registry-preflight-report.json",
                            ],
                            "must_change_tests": [],
                            "evidence_paths": [],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            repair_proposals = [
                proposal
                for proposal in proposal_report["proposals"]
                if proposal["failure_mode"] == "next_run_failure_repair"
            ]

            self.assertEqual(len(repair_proposals), 1)
            repair = repair_proposals[0]
            self.assertEqual(
                repair["primary_targets"],
                ["ops/scripts/registry/raw_registry_export.py"],
            )
            self.assertNotIn("ops/raw-registry.json", repair["primary_targets"])
            self.assertNotIn("ops/raw-registry.json", repair["supporting_targets"])
            self.assertIn(
                "ops/scripts/registry/raw_registry_preflight.py",
                repair["supporting_targets"],
            )
            self.assertIn(
                "tests/test_raw_registry_preflight.py",
                repair["must_change_tests"],
            )

    def test_candidate_fingerprint_repo_health_schema_debt_stays_open(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            primary_target = "ops/scripts/mechanism/example_runtime.py"
            schema_path = "ops/schemas/generated-report.schema.json"
            report_path = "ops/reports/generated-report.json"
            (vault / primary_target).parent.mkdir(parents=True, exist_ok=True)
            (vault / primary_target).write_text("VALUE = 1\n", encoding="utf-8")
            write_json(
                vault / schema_path,
                {
                    "type": "object",
                    "required": ["$schema", "status"],
                    "properties": {
                        "$schema": {"type": "string"},
                        "status": {"const": "pass"},
                    },
                    "additionalProperties": True,
                },
            )
            write_json(
                vault / report_path,
                {
                    "$schema": schema_path,
                    "status": "pass",
                },
            )
            source_run_id = "auto-session-a-run-01-example-runtime"
            source_run = vault / "runs" / source_run_id
            source_run.mkdir(parents=True, exist_ok=True)
            write_json(
                source_run / "repo-health-artifact-freshness-report-check.json",
                {
                    "status": "fail",
                    "source_tree_fingerprint": "candidate-workspace-fingerprint",
                    "recommended_next_action": "regenerate_schema_invalid_artifacts",
                    "top_debt_files": [
                        {
                            "path": report_path,
                            "primary_issue": "schema_validation_failed",
                            "issues": ["schema_validation_failed"],
                        }
                    ],
                },
            )
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:repo-health",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": source_run_id,
                            "proposal_id": "next_run_failure_repair__example-runtime__review-blocked",
                            "source_candidate_id": "next-run-decision:prior-review",
                            "target_proposal_id": (
                                "next_run_failure_repair__example-runtime__repo-health-blocked"
                            ),
                            "proposal_family": "next_run_failure_repair",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "repo_health_blocked",
                            "blocking_role": "repo_health",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "candidate-fingerprint artifact freshness failure should remain repairable",
                            "quarantined_source_proposal": True,
                            "primary_targets": [primary_target],
                            "supporting_targets": [report_path],
                            "must_change_tests": ["tests/test_example_runtime.py"],
                            "evidence_paths": [
                                f"runs/{source_run_id}/repo-health-artifact-freshness-report-check.json"
                            ],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            repair_proposals = [
                proposal
                for proposal in proposal_report["proposals"]
                if proposal["failure_mode"] == "next_run_failure_repair"
            ]

            self.assertEqual(len(repair_proposals), 1)
            self.assertEqual(
                repair_proposals[0]["proposal_id"],
                "next_run_failure_repair__example-runtime__repo-health-blocked",
            )
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"][
                    "open_carry_forward_decisions"
                ],
                1,
            )

    def test_noop_repair_mutation_failure_does_not_emit_followup_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            source_run_id = "auto-session-a-run-01-example-runtime"
            run_dir = vault / "runs" / source_run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "mutation-command.stderr.txt").write_text(
                (
                    "worker reported pass without modifying any declared primary target; "
                    "primary_targets=[ops/scripts/mechanism/example_runtime.py]\n"
                ),
                encoding="utf-8",
            )
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:mutation",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": source_run_id,
                            "proposal_id": (
                                "next_run_failure_repair__example-runtime__validation-blocked"
                            ),
                            "source_candidate_id": "next-run-decision:prior-validation",
                            "target_proposal_id": (
                                "next_run_failure_repair__example-runtime__mutation-failed"
                            ),
                            "proposal_family": "next_run_failure_repair",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "mutation_failed",
                            "blocking_role": "worker",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "noop repair should close instead of cycling",
                            "quarantined_source_proposal": True,
                            "primary_targets": [
                                "ops/scripts/mechanism/example_runtime.py"
                            ],
                            "supporting_targets": ["ops/script-output-surfaces.json"],
                            "must_change_tests": ["tests/test_example_runtime.py"],
                            "evidence_paths": [
                                f"runs/{source_run_id}/run-telemetry.json",
                                f"runs/{source_run_id}/worker-executor-report.json",
                            ],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))

            self.assertEqual(proposal_report["summary"]["next_run_repair_proposals"], 0)
            self.assertFalse(
                any(
                    proposal["failure_mode"] == "next_run_failure_repair"
                    for proposal in proposal_report["proposals"]
                )
            )
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"]["open_carry_forward_decisions"],
                0,
            )

    def test_original_noop_mutation_failure_does_not_emit_followup_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            source_run_id = "auto-session-a-run-01-example-runtime"
            run_dir = vault / "runs" / source_run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "mutation-command.stderr.txt").write_text(
                (
                    "worker reported pass without modifying any declared primary target; "
                    "primary_targets=[ops/scripts/mechanism/example_runtime.py]\n"
                ),
                encoding="utf-8",
            )
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:original-noop",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": source_run_id,
                            "proposal_id": "repeated_discard_runs__example-runtime",
                            "source_candidate_id": "mechanism_eval_stagnation_candidate__example-runtime",
                            "target_proposal_id": (
                                "next_run_failure_repair__example-runtime__mutation-failed"
                            ),
                            "proposal_family": "contract_regression_signals",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "mutation_failed",
                            "blocking_role": "worker",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "original no-op mutation should close instead of cycling",
                            "quarantined_source_proposal": True,
                            "primary_targets": [
                                "ops/scripts/mechanism/example_runtime.py"
                            ],
                            "supporting_targets": ["ops/script-output-surfaces.json"],
                            "must_change_tests": ["tests/test_example_runtime.py"],
                            "evidence_paths": [
                                f"runs/{source_run_id}/run-telemetry.json",
                                f"runs/{source_run_id}/worker-executor-report.json",
                            ],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))

            self.assertEqual(proposal_report["summary"]["next_run_repair_proposals"], 0)
            self.assertFalse(
                any(
                    proposal["failure_mode"] == "next_run_failure_repair"
                    for proposal in proposal_report["proposals"]
                )
            )
            self.assertEqual(
                proposal_report["diagnostics"]["next_run_decision_queue"]["open_carry_forward_decisions"],
                0,
            )

    def test_closed_next_run_decision_does_not_emit_repair_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:capacity",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": "auto-session-a-run-01-example-runtime",
                            "proposal_id": "original-proposal",
                            "source_candidate_id": "original-candidate",
                            "target_proposal_id": "",
                            "proposal_family": "contract_regression_signals",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "executor_usage_limited",
                            "blocking_role": "",
                            "decision": "ignore_retryable",
                            "next_run_action": "wait_for_executor_capacity",
                            "status": "closed",
                            "reason": "capacity issue should not become repair work",
                            "quarantined_source_proposal": False,
                            "primary_targets": [
                                "ops/scripts/mechanism/example_runtime.py"
                            ],
                            "supporting_targets": [],
                            "must_change_tests": [],
                            "evidence_paths": [
                                "runs/auto-session-a-run-01-example-runtime/run-telemetry.json"
                            ],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))

            self.assertEqual(proposal_report["summary"]["next_run_repair_proposals"], 0)
            self.assertFalse(
                any(
                    proposal["failure_mode"] == "next_run_failure_repair"
                    for proposal in proposal_report["proposals"]
                )
            )

    def test_disallowed_failure_mode_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy_path = vault / "ops" / "policies" / "wiki-maintainer-policy.yaml"
            policy_text = policy_path.read_text(encoding="utf-8")
            policy_text = policy_text.replace(
                "  allowed_failure_modes:\n"
                "    - branch_growth_without_test_growth\n"
                "    - high_complexity_low_test_pressure\n"
                "    - schema_change_without_test_guardrails\n"
                "    - policy_surface_growth_without_eval_gain\n"
                "    - repeated_same_eval_or_discard\n"
                "    - repeated_same_eval_after_promote\n"
                "    - repeated_discard_runs\n"
                "    - bootstrap_history_insufficient\n",
                "  allowed_failure_modes:\n"
                "    - branch_growth_without_test_growth\n"
                "    - repeated_same_eval_or_discard\n",
                1,
            )
            policy_path.write_text(policy_text, encoding="utf-8")

            policy, resolved_policy_path = load_policy(vault)
            report = build_report(vault, policy, resolved_policy_path)

            self.assertEqual(report["summary"]["proposals_emitted"], 1)
            self.assertEqual(
                report["diagnostics"]["skipped_candidates"][0]["reason"],
                "failure_mode_not_allowed",
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
