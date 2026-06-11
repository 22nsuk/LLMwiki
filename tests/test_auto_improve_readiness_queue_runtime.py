from __future__ import annotations

import json
import unittest

from ops.scripts.auto_improve_readiness_queue_runtime import (
    readiness_execution_fields,
    readiness_queue_payloads,
    readiness_queue_state,
)
from ops.scripts.auto_improve_readiness_runtime import (
    build_readiness_report,
    load_readiness_inputs,
    readiness_can_run,
    readiness_exit_code,
    write_readiness_report,
)
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.auto_improve_readiness_test_runtime import (
    ENVELOPE_SCHEMA_PATH,
    AutoImproveReadinessRuntimeFixture,
    fixed_context,
)


class AutoImproveReadinessQueueRuntimeTests(
    AutoImproveReadinessRuntimeFixture, unittest.TestCase
):
    def test_readiness_queue_state_owns_queue_derivation(self) -> None:
        reports = {
            "outcome_metrics": {
                "summary": {
                    "attempts_considered": 7,
                    "session_reports_considered": 0,
                }
            },
            "mechanism_review": {
                "status": "attention",
                "summary": {"candidates_emitted": 1},
                "diagnostics": {"bootstrap": {"status": "needs_history"}},
            },
            "mutation_proposal": {
                "status": "attention",
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 1,
                    "queue_pressure_summary": "1 proposal, 1 blocked",
                },
                "diagnostics": {
                    "evidence_gaps": ["candidate evidence gap"],
                    "queue_selection": {
                        "blocked_available_count": 1,
                        "blocked_reason_counts": [
                            {"reason": "recent_log_overlap", "count": 1}
                        ],
                    },
                },
                "proposals": [
                    {
                        "proposal_id": "proposal-blocked",
                        "blocked_by": ["recent_log_overlap"],
                    }
                ],
            },
        }

        state = readiness_queue_state(self.vault, reports)

        self.assertFalse(state.queue_ready)
        self.assertEqual(state.proposals_emitted, 1)
        self.assertEqual(state.runnable_proposal_ids, [])
        self.assertEqual(state.blocked_proposal_count, 1)
        self.assertEqual(state.blocked_reason_counts, {"recent_log_overlap": 1})
        self.assertEqual(
            state.blocked_proposal_ids,
            {"recent_log_overlap": ["proposal-blocked"]},
        )
        self.assertEqual(state.blocked_reasons, ["recent_log_overlap"])
        self.assertEqual(state.seed_runs, [])
        self.assertEqual(state.history_requirement, 0)
        self.assertIn(
            "mechanism_review.status=attention",
            state.queue_evidence_gaps[0],
        )
        self.assertIn(
            "mutation_proposal.status=attention",
            state.queue_evidence_gaps[1],
        )
        self.assertIn("candidate evidence gap", state.queue_evidence_gaps)
        self.assertIn(
            "proposal blockers active: recent_log_overlap",
            state.queue_evidence_gaps,
        )

        execution = readiness_execution_fields(state)

        self.assertEqual(execution.status, "warn")
        self.assertEqual(execution.gate_effect, "blocks_execution")
        self.assertFalse(execution.can_run)
        self.assertEqual(execution.runnable_proposal_count, 0)
        self.assertEqual(execution.blocked_proposal_count, 1)
        self.assertEqual(execution.reasons[0], "no runnable proposal is available")
        self.assertIn(
            "proposal blockers active: recent_log_overlap",
            execution.reasons,
        )
        self.assertIn("none are runnable yet", execution.recommended_next_step)
        self.assertEqual(execution.to_wire()["reasons"], execution.reasons)

        payloads = readiness_queue_payloads(
            queue_state=state,
            reports_present=True,
            mechanism_review_report=reports["mechanism_review"],
        )

        self.assertFalse(payloads.queue.ready)
        self.assertEqual(payloads.queue.runnable_proposal_count, 0)
        self.assertEqual(payloads.queue.blocked_proposal_count, 1)
        self.assertEqual(
            payloads.queue.blocked_reason_counts,
            [{"reason": "recent_log_overlap", "count": 1}],
        )
        self.assertEqual(payloads.fallback["status"], "blocked_queue")
        checks = {check["id"]: check for check in payloads.checks}
        self.assertFalse(checks["proposal_queue_nonempty"]["pass"])
        self.assertEqual(len(payloads.remediations), 1)
        self.assertEqual(payloads.remediations[0]["blocker"], "recent_log_overlap")

    def test_build_readiness_report_passes_when_queue_is_nonempty(self) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 2,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"}
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "proposal-ready",
                        "blocked_by": [],
                        "priority": 55,
                    }
                ],
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())
        inputs = load_readiness_inputs(self.vault, context=fixed_context())
        execution = readiness_execution_fields(inputs.queue_state)
        payloads = readiness_queue_payloads(
            queue_state=inputs.queue_state,
            reports_present=inputs.reports_present,
            mechanism_review_report=inputs.active_mechanism_review,
        )
        destination = write_readiness_report(self.vault, report)
        persisted = json.loads(destination.read_text(encoding="utf-8"))
        envelope_schema = load_schema(ENVELOPE_SCHEMA_PATH)

        self.assertEqual(validate_with_schema(persisted, envelope_schema), [])
        self.assertEqual(report["execution_readiness"], execution.to_wire())
        self.assertEqual(persisted["execution_readiness"]["status"], "pass")
        self.assertTrue(persisted["execution_readiness"]["can_run"])
        self.assertEqual(persisted["execution_status"], "pass")
        self.assertEqual(persisted["promotion_status"], "pass")
        self.assertTrue(persisted["can_execute_trial"])
        self.assertTrue(persisted["can_promote_result"])
        self.assertEqual(
            persisted["promotion_readiness"],
            {
                "status": "pass",
                "can_promote_result": True,
                "blocker_count": 0,
                "blocker_ids": [],
                "blocking_scopes": [],
                "gate_effects": [],
            },
        )
        self.assertTrue(readiness_can_run(persisted))
        self.assertEqual(readiness_exit_code(persisted), 0)
        self.assertTrue(persisted["queue"]["ready"])
        self.assertEqual(persisted["queue"]["runnable_proposal_count"], 1)
        self.assertEqual(persisted["queue"]["blocked_proposal_count"], 0)
        self.assertEqual(persisted["fallback"]["status"], "not_needed")
        self.assertEqual(persisted["fallback"]["seed_run_count"], 0)
        self.assertEqual(report["queue"], payloads.queue.to_wire())
        self.assertEqual(report["fallback"], payloads.fallback)
        self.assertEqual(report["checks"], payloads.checks)
        self.assertEqual(report["remediations"], payloads.remediations)
        self.assertEqual(
            persisted["diagnostics"]["loop_health_summary"]["status"], "missing"
        )
        self.assertEqual(
            persisted["diagnostics"]["loop_health_summary"]["gate_effect"], "none"
        )
        self.assertEqual(persisted["learning_readiness"]["status"], "learning_likely")
        self.assertEqual(persisted["learning_readiness"]["gate_effect"], "none")
        self.assertTrue(persisted["learning_readiness"]["can_run"])
        self.assertTrue(persisted["learning_readiness"]["likely_to_learn"])
        self.assertEqual(persisted["learning_readiness"]["signals"], [])
        self.assertEqual(persisted["execution_blockers"], [])
        self.assertEqual(persisted["learning_claim_blockers"], [])
        self.assertEqual(persisted["promotion_blockers"], [])
        self.assertEqual(persisted["clean_release_blockers"], [])
        self.assertEqual(
            persisted["diagnostics"]["artifact_freshness_summary"]["status"],
            "pass",
        )
        self.assertEqual(
            persisted["diagnostics"]["selected_contract_summary"]["status"],
            "pass",
        )
        self.assertEqual(
            persisted["diagnostics"]["source_package_clean_extract_summary"]["status"],
            "pass",
        )
        self.assertEqual(
            persisted["inputs"]["selected_contract_summary_report"],
            "ops/reports/test-execution-summary.json",
        )
        self.assertEqual(
            persisted["inputs"]["source_package_clean_extract_report"],
            "ops/reports/source-package-clean-extract.json",
        )
        self.assertEqual(
            persisted["inputs"]["goal_worktree_guard_report"],
            "ops/reports/goal-worktree-guard.json",
        )
        self.assertEqual(
            persisted["inputs"]["remediation_backlog_report"],
            "ops/reports/remediation-backlog.json",
        )
        self.assertEqual(
            persisted["diagnostics"]["goal_worktree_guard_summary"]["status"],
            "pass",
        )
        self.assertEqual(
            persisted["diagnostics"]["remediation_backlog_summary"]["status"],
            "pass",
        )
        self.assertEqual(
            persisted["inputs"]["release_evidence_cohort_report"],
            "ops/reports/release-evidence-cohort.json",
        )
        self.assertEqual(persisted["remediations"], [])
        self.assertEqual(
            persisted["fallback"]["auto_improve_command"], "make auto-improve-goal-run"
        )
        self.assertIn("auto-improve-goal-run", persisted["next_action"])
        self.assertNotIn("auto_improve_loop", persisted["next_action"])
        self.assertNotIn("status", persisted)
        self.assertNotIn("combined_state", persisted)
        self.assertNotIn("learnability_shadow_gate", persisted["diagnostics"])
        self.assertEqual(
            persisted["diagnostics"]["release_evidence_cohort_summary"]["status"],
            "pass",
        )

    def test_build_readiness_report_recommends_seed_run_when_queue_is_empty(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 3,
                    "recent_window": 20,
                    "recent_attempt_count": 3,
                    "session_reports_considered": 0,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 0},
                "diagnostics": {
                    "bootstrap": {
                        "summary": "fallback family needs more comparable runs",
                        "target_groups_under_min_history": [
                            {
                                "primary_targets": [
                                    "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"
                                ],
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
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 0,
                    "proposals_emitted": 0,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "no proposals emitted",
                },
                "diagnostics": {
                    "evidence_gaps": [
                        "mechanism review emitted zero candidates",
                        "outcome_metrics: attempts_considered=3 is below min_attempts_considered=10",
                    ]
                },
                "proposals": [],
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertEqual(report["execution_readiness"]["status"], "warn")
        self.assertEqual(report["execution_status"], "blocked")
        self.assertFalse(report["can_execute_trial"])
        self.assertFalse(report["can_promote_result"])
        self.assertEqual(report["promotion_readiness"]["status"], "blocked")
        self.assertEqual(report["promotion_readiness"]["blocking_scopes"], ["learning_readiness"])
        self.assertEqual(report["promotion_readiness"]["gate_effects"], ["blocks_execution"])
        self.assertTrue(
            any(
                item["scope"] == "execution_readiness"
                for item in report["execution_blockers"]
            )
        )
        self.assertFalse(
            any(
                item["scope"] == "execution_readiness"
                for item in report["promotion_blockers"]
            )
        )
        self.assertFalse(readiness_can_run(report))
        self.assertEqual(readiness_exit_code(report), 1)
        self.assertFalse(report["queue"]["ready"])
        self.assertEqual(
            report["diagnostics"]["loop_health_summary"]["status"], "missing"
        )
        self.assertEqual(report["fallback"]["status"], "seed_recommended")
        self.assertEqual(report["fallback"]["seed_run_count"], 0)
        self.assertEqual(report["fallback"]["history_requirement"], 2)
        self.assertEqual(report["fallback"]["additional_runs_needed"], 1)
        self.assertEqual(
            report["remediations"][0]["blocker"], "fallback_target_history_missing"
        )
        self.assertEqual(
            report["remediations"][0]["remediation_code"], "seed_fallback_target_family"
        )
        self.assertEqual(report["remediations"][0]["blocker_kind"], "history_gap")
        self.assertEqual(
            report["remediations"][0]["unblock_action_type"], "manual_seed_run"
        )
        self.assertIn("Finalize one narrow manual", report["next_action"])

    def test_build_readiness_report_tracks_seeded_fallback_family_history(self) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 3,
                    "recent_window": 20,
                    "recent_attempt_count": 3,
                    "session_reports_considered": 0,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 0},
                "diagnostics": {
                    "bootstrap": {
                        "summary": "fallback family still below the comparable-run floor",
                        "target_groups_under_min_history": [
                            {
                                "primary_targets": [
                                    "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"
                                ],
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
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 0,
                    "proposals_emitted": 0,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "no proposals emitted",
                },
                "diagnostics": {
                    "evidence_gaps": [
                        "mechanism review emitted zero candidates",
                    ]
                },
                "proposals": [],
            },
        )
        self._write_report(
            "runs/run-fallback-seed/run-telemetry.json",
            {
                "$schema": "ops/schemas/run-telemetry.schema.json",
                "run_id": "run-fallback-seed",
                "generated_at": "2026-04-22T00:00:00Z",
                "proposal_snapshot": "",
                "scope_freeze": "",
                "routing_reports": [],
                "executor_reports": [],
                "decision": "PROMOTE",
                "finalized": True,
                "finalize_result": {"run_id": "run-fallback-seed"},
                "primary_targets": [
                    "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"
                ],
                "supporting_targets": ["ops/schemas/run-telemetry.schema.json"],
                "test_files": ["tests/test_auto_improve_iteration_runtime.py"],
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertEqual(report["learning_readiness"]["status"], "not_runnable")
        self.assertEqual(report["execution_status"], "blocked")
        self.assertFalse(report["can_execute_trial"])
        self.assertFalse(report["can_promote_result"])
        self.assertEqual(len(report["learning_claim_blockers"]), 1)
        self.assertEqual(
            report["learning_claim_blockers"][0]["id"],
            "learning_blocked_by_execution_not_runnable",
        )
        self.assertEqual(
            report["learning_claim_blockers"][0]["gate_effect"],
            "blocks_execution",
        )
        self.assertEqual(
            report["learning_claim_blockers"][0]["source_status"], "not_runnable"
        )
        self.assertIn(
            "learning-readiness signoff cannot accept",
            report["learning_claim_blockers"][0]["required_evidence"][1],
        )
        self.assertNotIn(
            "operator must record accepted risk",
            " ".join(report["learning_claim_blockers"][0]["required_evidence"]),
        )
        self.assertTrue(
            any(
                item["id"] == "execution_blocked_by_no_runnable_proposal"
                for item in report["execution_blockers"]
            )
        )
        self.assertFalse(
            any(
                item["id"] == "execution_blocked_by_no_runnable_proposal"
                for item in report["promotion_blockers"]
            )
        )
        self.assertFalse(readiness_can_run(report))
        self.assertEqual(report["fallback"]["status"], "history_seeded")
        self.assertEqual(report["fallback"]["seed_run_count"], 1)
        self.assertEqual(report["fallback"]["seed_runs"], ["run-fallback-seed"])
        self.assertEqual(
            report["remediations"][0]["blocker"], "fallback_target_history_depth"
        )
        self.assertEqual(
            report["remediations"][0]["remediation_code"],
            "add_comparable_fallback_history",
        )
        self.assertIn("add another comparable narrow run", report["next_action"])

    def test_build_readiness_report_warns_when_only_blocked_proposals_exist(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 7,
                    "recent_window": 20,
                    "recent_attempt_count": 7,
                    "session_reports_considered": 0,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"}
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 1,
                    "queue_pressure_summary": "1 proposal, 1 blocked",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "proposal-blocked",
                        "blocked_by": ["recent_log_overlap"],
                        "priority": 55,
                    }
                ],
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertFalse(readiness_can_run(report))
        self.assertFalse(report["execution_readiness"]["can_run"])
        self.assertFalse(report["queue"]["ready"])
        self.assertEqual(report["queue"]["runnable_proposal_count"], 0)
        self.assertEqual(report["queue"]["runnable_proposal_ids"], [])
        self.assertEqual(report["queue"]["blocked_proposal_count"], 1)
        self.assertEqual(
            report["queue"]["blocked_reason_counts"],
            [{"reason": "recent_log_overlap", "count": 1}],
        )
        self.assertEqual(report["fallback"]["status"], "blocked_queue")
        self.assertEqual(len(report["remediations"]), 1)
        remediation = report["remediations"][0]
        self.assertEqual(remediation["blocker"], "recent_log_overlap")
        self.assertEqual(
            remediation["remediation_code"], "wait_for_recent_log_overlap_to_clear"
        )
        self.assertEqual(remediation["blocker_kind"], "hard")
        self.assertEqual(
            remediation["unblock_action_type"],
            "chronology_advance_or_target_rotation",
        )
        self.assertEqual(remediation["affected_proposal_count"], 1)
        self.assertEqual(remediation["proposal_ids"], ["proposal-blocked"])
        self.assertTrue(
            any(
                "runnable_proposal_count" in item
                for item in remediation["minimum_evidence"]
            )
        )
        self.assertTrue(
            any(
                "recent_log_overlap_queue_blocked__ target-rotation" in item
                for item in remediation["minimum_evidence"]
            )
        )
        self.assertIn("make auto-improve-readiness", remediation["retry_condition"])
        self.assertIn("queue_unblock target-rotation", remediation["retry_condition"])
        self.assertIn("none are runnable yet", report["next_action"])
        self.assertIn("recent_log_overlap", report["next_action"])
        checks = {check["id"]: check for check in report["checks"]}
        self.assertIn(
            "blocked_proposal_count=1", checks["proposal_queue_nonempty"]["detail"]
        )
        self.assertIn(
            "recent_log_overlap=1", checks["proposal_queue_nonempty"]["detail"]
        )
        self.assertTrue(checks["fallback_target_history_requirement_met"]["pass"])
        self.assertIn(
            "fallback history depth is not needed",
            checks["fallback_target_history_requirement_met"]["detail"],
        )

    def test_build_readiness_report_surfaces_recent_outcome_rework_remediation(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 7,
                    "recent_window": 20,
                    "recent_attempt_count": 7,
                    "session_reports_considered": 0,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"}
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 1,
                    "queue_pressure_summary": "queue_unblock 1 proposal, 1 blocked",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "recent_log_overlap_queue_blocked__mutation-proposal-runtime",
                        "blocked_by": ["recent_outcome_rework"],
                        "priority": 91,
                    }
                ],
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertFalse(readiness_can_run(report))
        self.assertEqual(report["queue"]["runnable_proposal_count"], 0)
        self.assertEqual(
            report["queue"]["blocked_reason_counts"],
            [{"reason": "recent_outcome_rework", "count": 1}],
        )
        self.assertEqual(len(report["remediations"]), 1)
        remediation = report["remediations"][0]
        self.assertEqual(remediation["blocker"], "recent_outcome_rework")
        self.assertEqual(
            remediation["remediation_code"],
            "stop_repeating_unresolved_queue_rotation",
        )
        self.assertEqual(
            remediation["unblock_action_type"],
            "outcome_rework_repair_or_successful_supersession",
        )
        self.assertIn(
            "Do not rerun the same queue-unblock proposal",
            remediation["retry_condition"],
        )
        self.assertTrue(
            any("outcome-metrics" in item for item in remediation["minimum_evidence"])
        )

    def test_build_readiness_report_surfaces_empty_queue_blockers_as_blocked_seeds(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 7,
                    "recent_window": 20,
                    "recent_attempt_count": 7,
                    "session_reports_considered": 0,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "status": "attention",
                "summary": {"candidates_emitted": 0},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue blocker is available"}
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "status": "attention",
                "summary": {
                    "source_candidates_read": 0,
                    "proposals_emitted": 0,
                    "blocked_proposals": 2,
                    "queue_pressure_summary": "no proposals emitted",
                },
                "diagnostics": {
                    "evidence_gaps": [],
                    "empty_queue_blockers": [
                        {
                            "blocker_type": "schema",
                            "reason": "run_artifact_invalid",
                            "detail": "schema validation failed for runs/run-a/baseline-eval.json",
                            "source": "mechanism_review.candidate_blockers",
                        },
                        {
                            "blocker_type": "schema",
                            "reason": "run_artifact_invalid",
                            "detail": "schema validation failed for runs/run-b/baseline-eval.json",
                            "source": "mechanism_review.candidate_blockers",
                        },
                    ],
                },
                "proposals": [],
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertFalse(readiness_can_run(report))
        self.assertEqual(report["queue"]["blocked_proposal_count"], 2)
        self.assertEqual(
            report["queue"]["blocked_reason_counts"],
            [{"reason": "run_artifact_invalid", "count": 2}],
        )
        self.assertEqual(report["fallback"]["status"], "blocked_queue")
        self.assertEqual(report["remediations"][0]["blocker"], "run_artifact_invalid")
        self.assertEqual(report["remediations"][0]["affected_proposal_count"], 2)
        self.assertIn(
            "diagnostics.empty_queue_blockers",
            report["remediations"][0]["minimum_evidence"][0],
        )
        self.assertIn("blocked queue seed", report["next_action"])
        self.assertIn("run_artifact_invalid", report["next_action"])

    def test_build_readiness_report_passes_when_blocked_and_runnable_proposals_coexist(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 1,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 2},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"}
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 2,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "selected one ready; one blocked available",
                },
                "diagnostics": {
                    "evidence_gaps": [],
                    "queue_selection": {
                        "available_proposal_count": 2,
                        "selected_proposal_count": 1,
                        "runnable_available_count": 1,
                        "blocked_available_count": 1,
                        "selected_runnable_count": 1,
                        "selected_blocked_count": 0,
                        "blocked_reason_counts": [
                            {"reason": "recent_log_overlap", "count": 1}
                        ],
                    },
                },
                "proposals": [
                    {
                        "proposal_id": "recent_log_overlap_queue_blocked__auto-improve-readiness-constants-runtime",
                        "failure_mode": "recent_log_overlap_queue_blocked",
                        "blocked_by": [],
                        "priority": 40,
                    },
                ],
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(readiness_can_run(report))
        self.assertEqual(report["execution_readiness"]["runnable_proposal_count"], 1)
        self.assertTrue(report["queue"]["ready"])
        self.assertEqual(report["queue"]["runnable_proposal_count"], 1)
        self.assertEqual(
            report["queue"]["runnable_proposal_ids"],
            [
                "recent_log_overlap_queue_blocked__auto-improve-readiness-constants-runtime"
            ],
        )
        self.assertEqual(report["queue"]["blocked_proposal_count"], 1)
        self.assertEqual(
            report["queue"]["blocked_reason_counts"],
            [{"reason": "recent_log_overlap", "count": 1}],
        )
        self.assertEqual(report["queue"]["evidence_gaps"], [])
        self.assertEqual(report["remediations"], [])
        self.assertNotIn(
            "learning_blocked_by_execution_not_runnable",
            {blocker["id"] for blocker in report["learning_claim_blockers"]},
        )
        self.assertIn("Queue is non-empty", report["next_action"])
        self.assertIn(
            "Run proposal `recent_log_overlap_queue_blocked__auto-improve-readiness-constants-runtime` next.",
            report["next_action"],
        )
        checks = {check["id"]: check for check in report["checks"]}
        self.assertTrue(checks["fallback_target_history_requirement_met"]["pass"])
        self.assertIn(
            "fallback history depth is not needed",
            checks["fallback_target_history_requirement_met"]["detail"],
        )
