from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.mechanism.mutation_proposal_runtime import build_report
from tests.minimal_vault_runtime import (
    seed_minimal_vault as seed_minimal_raw_registry_vault,
)
from tests.mutation_proposal_test_runtime import (
    auto_improve_session_envelope,
    fixed_context,
    mechanism_review_report,
    seed_vault,
    write_json,
    write_json_exact,
)


class MutationProposalPromotionTest(unittest.TestCase):
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
            source_run_id = "auto-session-a-run-01-example-runtime"
            run_dir = vault / "runs" / source_run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(run_dir / "run-telemetry.json", {"status": "blocked"})
            write_json(run_dir / "reviewer-executor-report.json", {"status": "fail"})
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
                            "source_run_id": source_run_id,
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
                                f"runs/{source_run_id}/run-telemetry.json",
                                (
                                    f"runs/{source_run_id}/"
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
            self.assertEqual(repair["run_ids"], [source_run_id])
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
    def test_over_budget_next_run_repair_is_not_selected_as_runnable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            target = "ops/scripts/mechanism/oversized_runtime.py"
            test_target = "tests/test_oversized_runtime.py"
            (vault / target).parent.mkdir(parents=True, exist_ok=True)
            (vault / target).write_text(
                "\n".join(f"VALUE_{index} = {index}" for index in range(950)) + "\n",
                encoding="utf-8",
            )
            (vault / test_target).write_text(
                "def test_oversized_runtime():\n    assert True\n",
                encoding="utf-8",
            )
            source_run_id = "auto-session-a-run-01-oversized-runtime"
            run_dir = vault / "runs" / source_run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(run_dir / "run-telemetry.json", {"status": "blocked"})
            write_json(run_dir / "repo-health.json", {"status": "fail"})
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
                            "proposal_id": "original-proposal",
                            "source_candidate_id": "original-candidate",
                            "target_proposal_id": (
                                "next_run_failure_repair__oversized-runtime__repo-health-blocked"
                            ),
                            "proposal_family": "contract_regression_signals",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "repo_health_blocked",
                            "blocking_role": "repo_health",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "repo-health failure should become next-run repair work",
                            "quarantined_source_proposal": True,
                            "primary_targets": [target],
                            "supporting_targets": ["ops/script-output-surfaces.json"],
                            "must_change_tests": [test_target],
                            "evidence_paths": [
                                f"runs/{source_run_id}/run-telemetry.json",
                                f"runs/{source_run_id}/repo-health.json",
                            ],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            repair = proposal_report["proposals"][0]

            self.assertEqual(proposal_report["status"], "attention")
            self.assertEqual(repair["failure_mode"], "next_run_failure_repair")
            self.assertEqual(repair["blocked_by"], ["structural_complexity_budget"])
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"]["selected_runnable_count"],
                0,
            )
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"]["selected_blocked_count"],
                1,
            )
            structural_blockers = [
                item
                for item in proposal_report["diagnostics"]["queue_selection"][
                    "blocked_reason_counts"
                ]
                if item["reason"] == "structural_complexity_budget"
            ]
            self.assertEqual(len(structural_blockers), 1)
            self.assertGreaterEqual(structural_blockers[0]["count"], 1)

    def test_generated_report_support_does_not_block_single_source_next_run_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            target = "ops/scripts/mechanism/auto_improve_loop.py"
            test_target = "tests/test_goal_auto_improve_runtime.py"
            support_target = "ops/reports/large-generated-support.json"
            (vault / target).parent.mkdir(parents=True, exist_ok=True)
            (vault / target).write_text(
                "def run_loop() -> None:\n    return None\n",
                encoding="utf-8",
            )
            (vault / test_target).write_text(
                "def test_goal_auto_improve_runtime():\n    assert True\n",
                encoding="utf-8",
            )
            (vault / support_target).parent.mkdir(parents=True, exist_ok=True)
            (vault / support_target).write_text(
                "\n".join(f'  "item_{index}": true,' for index in range(950)) + "\n",
                encoding="utf-8",
            )
            source_run_id = "auto-session-a-run-01-auto-improve-loop"
            run_dir = vault / "runs" / source_run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(run_dir / "run-telemetry.json", {"status": "blocked"})
            write_json(
                vault / "ops" / "reports" / "mechanism-review-candidates.json",
                mechanism_review_report(),
            )
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
                            "proposal_id": "recent_log_overlap_queue_blocked__auto-improve-loop",
                            "source_candidate_id": "recent-log-overlap",
                            "target_proposal_id": (
                                "next_run_failure_repair__auto-improve-loop__repo-health-blocked"
                            ),
                            "proposal_family": "queue_unblock",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "repo_health_blocked",
                            "blocking_role": "repo_health",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "repo-health failure should become next-run repair work",
                            "quarantined_source_proposal": True,
                            "primary_targets": [target],
                            "supporting_targets": [support_target],
                            "must_change_tests": [test_target],
                            "evidence_paths": [
                                f"runs/{source_run_id}/run-telemetry.json",
                            ],
                        }
                    ]
                },
            )
            (vault / "system" / "system-log.md").write_text("# System Log\n", encoding="utf-8")

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path, context=fixed_context(policy))
            repair = proposal_report["proposals"][0]

            self.assertEqual(
                repair["proposal_id"],
                "next_run_failure_repair__auto-improve-loop__repo-health-blocked",
            )
            self.assertEqual(repair["primary_targets"], [target])
            self.assertIn(support_target, repair["supporting_targets"])
            self.assertEqual(repair["blocked_by"], [])
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"]["selected_runnable_count"],
                1,
            )
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"]["selected_blocked_count"],
                0,
            )
    def test_next_run_decision_why_now_omits_missing_leaf_evidence_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            target = "ops/scripts/mechanism/example_runtime.py"
            test_target = "tests/test_example_runtime.py"
            (vault / target).parent.mkdir(parents=True, exist_ok=True)
            (vault / target).write_text("VALUE = 1\n", encoding="utf-8")
            (vault / test_target).write_text(
                "def test_example_runtime():\n    assert True\n",
                encoding="utf-8",
            )
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            source_run_id = "partial-run"
            run_dir = vault / "runs" / source_run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(run_dir / "run-telemetry.json", {"status": "blocked"})
            present_evidence = f"runs/{source_run_id}/run-telemetry.json"
            missing_evidence = f"runs/{source_run_id}/reviewer-executor-report.json"
            session_report = "ops/reports/auto-improve-sessions/session-a.json"
            write_json(
                vault / session_report,
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:missing-run:review",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": source_run_id,
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
                            "primary_targets": [target],
                            "supporting_targets": ["ops/script-output-surfaces.json"],
                            "must_change_tests": [test_target],
                            "evidence_paths": [present_evidence, missing_evidence],
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

            self.assertIn(present_evidence, repair["why_now"])
            self.assertIn(session_report, repair["why_now"])
            self.assertIn("1 missing leaf evidence path omitted", repair["why_now"])
            self.assertNotIn(missing_evidence, repair["why_now"])
    def test_next_run_decision_with_all_missing_leaf_evidence_does_not_emit_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            target = "ops/scripts/mechanism/example_runtime.py"
            test_target = "tests/test_example_runtime.py"
            (vault / target).parent.mkdir(parents=True, exist_ok=True)
            (vault / target).write_text("VALUE = 1\n", encoding="utf-8")
            (vault / test_target).write_text(
                "def test_example_runtime():\n    assert True\n",
                encoding="utf-8",
            )
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:missing-run:review",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 1,
                            "source_run_id": "missing-run",
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
                            "primary_targets": [target],
                            "supporting_targets": ["ops/script-output-surfaces.json"],
                            "must_change_tests": [test_target],
                            "evidence_paths": [
                                "runs/missing-run/run-telemetry.json",
                                "runs/missing-run/reviewer-executor-report.json",
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
            self.assertFalse(
                any(
                    proposal["failure_mode"] == "next_run_failure_repair"
                    for proposal in proposal_report["proposals"]
                )
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
                "\n".join(f'  "sample_{index}": true,' for index in range(1000)) + "\n",
                encoding="utf-8",
            )
            source_run_id = "auto-session-a-run-03-example-runtime"
            run_dir = vault / "runs" / source_run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(run_dir / "run-telemetry.json", {"status": "blocked"})
            write_json(run_dir / "validator-executor-report.json", {"status": "fail"})
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
                            "source_run_id": source_run_id,
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
                                f"runs/{source_run_id}/run-telemetry.json",
                                (
                                    f"runs/{source_run_id}/"
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
            self.assertEqual(repair["blocked_by"], [])
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
            write_json(run_dir / "run-telemetry.json", {"status": "blocked"})
            write_json(run_dir / "promotion-report.json", {"decision": "HOLD"})
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
                            "decision_id": "next-run-decision:run-a:review",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 3,
                            "source_run_id": source_run_id,
                            "proposal_id": "next_run_failure_repair__example-runtime__validation-blocked",
                            "source_candidate_id": "next-run-decision:prior:validation",
                            "target_proposal_id": "next_run_failure_repair__example-runtime__review-blocked",
                            "proposal_family": "next_run_failure_repair",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "review_blocked",
                            "blocking_role": "reviewer",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": "review repair should remain bounded to exact source evidence",
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
    def test_resolved_structural_next_run_decision_does_not_emit_repair_proposal(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            primary_target = "ops/scripts/mechanism/auto_improve_readiness_runtime.py"
            (vault / primary_target).write_text(
                "def ready() -> bool:\n    return True\n",
                encoding="utf-8",
            )
            (vault / "tests" / "test_auto_improve_readiness_runtime.py").write_text(
                "def test_ready():\n    assert True\n",
                encoding="utf-8",
            )
            write_json(vault / "ops" / "reports" / "mechanism-review-candidates.json", mechanism_review_report())
            write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "session-a.json",
                {
                    "next_run_decisions": [
                        {
                            "decision_id": "next-run-decision:run-a:structural",
                            "observed_at": "2026-04-14T02:00:00Z",
                            "session_id": "auto-session-a",
                            "iteration": 3,
                            "source_run_id": (
                                "auto-session-a-run-03-auto-improve-readiness-runtime"
                            ),
                            "proposal_id": (
                                "next_run_failure_repair__auto-improve-readiness-runtime__"
                                "repo-health-blocked"
                            ),
                            "source_candidate_id": "next-run-decision:prior:repo-health",
                            "target_proposal_id": (
                                "next_run_failure_repair__auto-improve-readiness-runtime__"
                                "structural-complexity-non-regression"
                            ),
                            "proposal_family": "next_run_failure_repair",
                            "proposal_tier": "supporting",
                            "failure_taxonomy": "structural_complexity_non_regression",
                            "blocking_role": "promotion_gate",
                            "decision": "carry_forward",
                            "next_run_action": "repair_failure",
                            "status": "open",
                            "reason": (
                                "structural non-regression is already resolved in the "
                                "current target"
                            ),
                            "quarantined_source_proposal": False,
                            "primary_targets": [primary_target],
                            "supporting_targets": ["ops/script-output-surfaces.json"],
                            "must_change_tests": [
                                "tests/test_auto_improve_readiness_runtime.py"
                            ],
                            "evidence_paths": [
                                (
                                    "runs/auto-session-a-run-03-auto-improve-readiness-runtime/"
                                    "structural-complexity-budget.json"
                                )
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
                proposal_report["diagnostics"]["next_run_decision_queue"],
                {
                    "session_reports_scanned": 1,
                    "decisions_considered": 1,
                    "open_carry_forward_decisions": 0,
                    "repair_proposals_emitted": 0,
                    "decision_counts": {"carry_forward": 1},
                    "action_counts": {"repair_failure": 1},
                    "selected_target_proposal_ids": [],
                },
            )
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
            source_run_id = "auto-session-a-run-01-example-runtime"
            run_dir = vault / "runs" / source_run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(run_dir / "run-telemetry.json", {"status": "blocked"})
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
                            "source_run_id": source_run_id,
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
                                f"runs/{source_run_id}/run-telemetry.json"
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

            from ops.scripts.registry.raw_registry_export import (
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

            from ops.scripts.registry.raw_registry_export import (
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

            from ops.scripts.registry.raw_registry_export import (
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

            from ops.scripts.registry.raw_registry_export import (
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

            from ops.scripts.registry.raw_registry_export import (
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

            from ops.scripts.registry.raw_registry_export import (
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



if __name__ == "__main__":
    unittest.main()
