from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.mechanism import mechanism_review_runtime
from ops.scripts.mechanism.mechanism_review import main as mechanism_review_main
from ops.scripts.mechanism.mechanism_review_runtime import build_report
from tests.cli_test_runtime import invoke_cli_main
from tests.mechanism_review_test_utils import (
    eval_report,
    mechanism_report,
    outcome_metrics_report,
    promotion_report,
    seed_review_vault,
    write_json,
    write_run_session_context,
    write_session_report,
)
from tests.minimal_vault_runtime import mutate_policy

pytestmark = pytest.mark.fast_smoke


class MechanismReviewTest(unittest.TestCase):
    def test_build_report_emits_core_and_supporting_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)

            primary_targets = ["ops/scripts/promotion_gate.py"]
            runs = [
                ("run-20260414-a", 18, 26, 2, 10, "DISCARD"),
                ("run-20260414-b", 24, 28, 2, 10, "DISCARD"),
                ("run-20260414-c", 30, 30, 2, 10, "HOLD"),
            ]
            baseline_branch = 24
            baseline_nonempty = 14
            for run_id, candidate_nonempty, candidate_branch, test_cases, eval_score, decision in runs:
                run_dir = vault / "runs" / run_id
                baseline_eval_path = f"runs/{run_id}/baseline-eval.json"
                candidate_eval_path = f"runs/{run_id}/candidate-eval.json"
                baseline_mechanism_path = f"runs/{run_id}/baseline-mechanism.json"
                candidate_mechanism_path = f"runs/{run_id}/candidate-mechanism.json"

                write_json(vault / baseline_eval_path, eval_report(vault, eval_score))
                write_json(vault / candidate_eval_path, eval_report(vault, eval_score))
                write_json(
                    vault / baseline_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=baseline_nonempty,
                        functions=4,
                        branches=baseline_branch,
                        test_file_count=1,
                        test_case_count=test_cases,
                        complexity_score=60,
                    ),
                )
                write_json(
                    vault / candidate_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=candidate_nonempty,
                        functions=4,
                        branches=candidate_branch,
                        test_file_count=1,
                        test_case_count=test_cases,
                        complexity_score=85 if run_id == "run-20260414-c" else 75,
                    ),
                )
                write_json(
                    run_dir / "promotion-report.json",
                    promotion_report(
                        run_id,
                        primary_targets=primary_targets,
                        decision=decision,
                        baseline_eval_path=baseline_eval_path,
                        candidate_eval_path=candidate_eval_path,
                        baseline_mechanism_path=baseline_mechanism_path,
                        candidate_mechanism_path=candidate_mechanism_path,
                    ),
                )
                baseline_branch = candidate_branch
                baseline_nonempty = candidate_nonempty

            policy, policy_path = load_policy(vault)
            report = build_report(vault, policy, policy_path)
            schema = load_schema(vault / "ops" / "schemas" / "mechanism-review-candidates.schema.json")

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["runs_discovered"], 3)
            self.assertEqual(report["summary"]["runs_considered"], 3)
            self.assertEqual(report["diagnostics"]["bootstrap"]["status"], "ready")
            self.assertEqual(
                report["diagnostics"]["session_calibration"],
                {
                    "enabled": True,
                    "status": "no_session_context",
                    "candidate_count": 3,
                    "candidates_with_session_context": 0,
                    "candidates_with_rollups": 0,
                    "candidates_without_session_context": 3,
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
                    "unchanged_candidates": 3,
                    "by_family": [
                        {
                            "family": "contract_regression_signals",
                            "candidates_with_session_context": 0,
                            "candidates_with_rollups": 0,
                            "candidates_without_session_context": 1,
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
                            "unchanged_candidates": 1,
                        },
                        {
                            "family": "self_mod_stability",
                            "candidates_with_session_context": 0,
                            "candidates_with_rollups": 0,
                            "candidates_without_session_context": 2,
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
                            "unchanged_candidates": 2,
                        },
                    ],
                },
            )
            candidate_types = {candidate["candidate_type"] for candidate in report["candidates"]}
            self.assertEqual(
                candidate_types,
                {
                    "mechanism_branch_growth_without_test_growth_candidate",
                    "mechanism_high_complexity_low_test_pressure_candidate",
                    "mechanism_eval_stagnation_candidate",
                },
            )
            family_by_type = {candidate["candidate_type"]: candidate["family"] for candidate in report["candidates"]}
            self.assertEqual(family_by_type["mechanism_eval_stagnation_candidate"], "contract_regression_signals")
            self.assertEqual(family_by_type["mechanism_high_complexity_low_test_pressure_candidate"], "self_mod_stability")
            stagnation_candidate = next(
                candidate
                for candidate in report["candidates"]
                if candidate["candidate_type"] == "mechanism_eval_stagnation_candidate"
            )
            self.assertEqual(
                stagnation_candidate["signal_run_ids"],
                {
                    "repeated_discard_runs": ["run-20260414-a", "run-20260414-b"],
                    "repeated_same_eval_after_promote": [
                        "run-20260414-a",
                        "run-20260414-b",
                        "run-20260414-c",
                    ],
                },
            )
            priorities = [candidate["priority"] for candidate in report["candidates"]]
            self.assertEqual(priorities, sorted(priorities, reverse=True))

    def test_outcome_metrics_calibration_preview_reports_signals_without_priority_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)

            primary_targets = ["ops/scripts/promotion_gate.py"]
            runs = [
                ("run-20260414-a", 18, 26, 2, 10, "DISCARD"),
                ("run-20260414-b", 24, 28, 2, 10, "DISCARD"),
                ("run-20260414-c", 30, 30, 2, 10, "HOLD"),
            ]
            baseline_branch = 24
            baseline_nonempty = 14
            for run_id, candidate_nonempty, candidate_branch, test_cases, eval_score, decision in runs:
                run_dir = vault / "runs" / run_id
                baseline_eval_path = f"runs/{run_id}/baseline-eval.json"
                candidate_eval_path = f"runs/{run_id}/candidate-eval.json"
                baseline_mechanism_path = f"runs/{run_id}/baseline-mechanism.json"
                candidate_mechanism_path = f"runs/{run_id}/candidate-mechanism.json"

                write_json(vault / baseline_eval_path, eval_report(vault, eval_score))
                write_json(vault / candidate_eval_path, eval_report(vault, eval_score))
                write_json(
                    vault / baseline_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=baseline_nonempty,
                        functions=4,
                        branches=baseline_branch,
                        test_file_count=1,
                        test_case_count=test_cases,
                        complexity_score=60,
                    ),
                )
                write_json(
                    vault / candidate_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=candidate_nonempty,
                        functions=4,
                        branches=candidate_branch,
                        test_file_count=1,
                        test_case_count=test_cases,
                        complexity_score=85 if run_id == "run-20260414-c" else 75,
                    ),
                )
                write_json(
                    run_dir / "promotion-report.json",
                    promotion_report(
                        run_id,
                        primary_targets=primary_targets,
                        decision=decision,
                        baseline_eval_path=baseline_eval_path,
                        candidate_eval_path=candidate_eval_path,
                        baseline_mechanism_path=baseline_mechanism_path,
                        candidate_mechanism_path=candidate_mechanism_path,
                    ),
                )
                baseline_branch = candidate_branch
                baseline_nonempty = candidate_nonempty

            policy, policy_path = load_policy(vault)
            baseline_report = build_report(vault, policy, policy_path)
            baseline_priorities = {
                candidate["candidate_id"]: candidate["priority"]
                for candidate in baseline_report["candidates"]
            }

            write_json(
                vault / "ops" / "reports" / "outcome-metrics.json",
                outcome_metrics_report(vault, primary_targets=primary_targets),
            )
            report = build_report(vault, policy, policy_path)
            schema = load_schema(vault / "ops" / "schemas" / "mechanism-review-candidates.schema.json")

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(
                {candidate["candidate_id"]: candidate["priority"] for candidate in report["candidates"]},
                baseline_priorities,
            )
            diagnostics = report["diagnostics"]["outcome_metrics_calibration"]
            self.assertTrue(diagnostics["enabled"])
            self.assertEqual(diagnostics["status"], "active")
            self.assertEqual(diagnostics["mode"], "audit_only")
            self.assertEqual(diagnostics["gate_effect"], "none")
            self.assertEqual(diagnostics["candidates_with_outcome_context"], 3)
            self.assertEqual(diagnostics["global_signals"]["rework_count"], 2)
            self.assertEqual(diagnostics["global_signals"]["moving_averages"]["discard"], 0.6667)

            target_signal = diagnostics["target_signals"][0]
            self.assertEqual(target_signal["primary_targets"], primary_targets)
            self.assertEqual(target_signal["rework_count"], 2)
            self.assertEqual(target_signal["defect_escape_pair_count"], 1)
            self.assertEqual(
                target_signal["preview_flags"],
                [
                    "high_rework",
                    "recent_hold_moving_average",
                    "recent_discard_moving_average",
                    "rollback_signal_ratio",
                    "defect_escape_proxy",
                ],
            )
            self.assertEqual(
                target_signal["candidate_count_by_family"],
                {"contract_regression_signals": 1, "self_mod_stability": 2},
            )
            family_by_name = {
                item["family"]: item for item in diagnostics["family_signals"]
            }
            self.assertEqual(family_by_name["self_mod_stability"]["candidate_count"], 2)
            self.assertEqual(family_by_name["contract_regression_signals"]["rework_count"], 2)
            self.assertEqual(
                diagnostics["high_rework_targets"],
                [
                    {
                        "primary_targets": primary_targets,
                        "families": ["contract_regression_signals", "self_mod_stability"],
                        "rework_count": 2,
                        "source_run_ids": [
                            "run-20260414-a",
                            "run-20260414-b",
                            "run-20260414-c",
                        ],
                    }
                ],
            )
            self.assertEqual(diagnostics["defect_escape_pairs"][0]["target"], primary_targets[0])
            self.assertEqual(diagnostics["shadow_priority"]["status"], "disabled")
            self.assertEqual(diagnostics["shadow_priority"]["gate_effect"], "none")
            self.assertEqual(diagnostics["shadow_priority"]["ordering_deltas"], [])
            self.assertEqual(
                diagnostics["evidence_gaps"],
                [
                    "attempts_considered=3 is below min_attempts_considered=10",
                ],
            )

            shadow_policy = json.loads(json.dumps(policy))
            shadow_policy["mechanism_review"]["calibration"]["outcome_metrics_preview"].update(
                {
                    "mode": "shadow_priority",
                    "min_attempts_considered": 3,
                    "min_target_attempts": 1,
                    "shadow_priority_max_delta": 10,
                }
            )
            shadow_report = build_report(vault, shadow_policy, policy_path)
            self.assertEqual(validate_with_schema(shadow_report, schema), [])
            self.assertEqual(
                {candidate["candidate_id"]: candidate["priority"] for candidate in shadow_report["candidates"]},
                baseline_priorities,
            )
            shadow = shadow_report["diagnostics"]["outcome_metrics_calibration"]["shadow_priority"]
            self.assertEqual(shadow["status"], "active")
            self.assertEqual(shadow["gate_effect"], "none")
            self.assertEqual(shadow["attempts_considered"], 3)
            self.assertEqual(len(shadow["ordering_deltas"]), 3)
            self.assertTrue(any(item["priority_delta"] > 0 for item in shadow["ordering_deltas"]))
            self.assertTrue(all(item["priority_delta"] <= 10 for item in shadow["ordering_deltas"]))
            self.assertEqual(
                shadow_report["diagnostics"]["outcome_metrics_calibration"]["evidence_gaps"],
                [],
            )

    def test_session_calibration_reuses_run_telemetry_reads_across_candidate_types(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)

            primary_targets = ["ops/scripts/promotion_gate.py"]
            runs = [
                ("run-20260414-a", 18, 26, 2, 10, "DISCARD"),
                ("run-20260414-b", 24, 28, 2, 10, "DISCARD"),
                ("run-20260414-c", 30, 30, 2, 10, "HOLD"),
            ]
            baseline_branch = 24
            baseline_nonempty = 14
            for run_id, candidate_nonempty, candidate_branch, test_cases, eval_score, decision in runs:
                run_dir = vault / "runs" / run_id
                baseline_eval_path = f"runs/{run_id}/baseline-eval.json"
                candidate_eval_path = f"runs/{run_id}/candidate-eval.json"
                baseline_mechanism_path = f"runs/{run_id}/baseline-mechanism.json"
                candidate_mechanism_path = f"runs/{run_id}/candidate-mechanism.json"

                write_json(vault / baseline_eval_path, eval_report(vault, eval_score))
                write_json(vault / candidate_eval_path, eval_report(vault, eval_score))
                write_json(
                    vault / baseline_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=baseline_nonempty,
                        functions=4,
                        branches=baseline_branch,
                        test_file_count=1,
                        test_case_count=test_cases,
                        complexity_score=60,
                    ),
                )
                write_json(
                    vault / candidate_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=candidate_nonempty,
                        functions=4,
                        branches=candidate_branch,
                        test_file_count=1,
                        test_case_count=test_cases,
                        complexity_score=85 if run_id == "run-20260414-c" else 75,
                    ),
                )
                write_json(
                    run_dir / "promotion-report.json",
                    promotion_report(
                        run_id,
                        primary_targets=primary_targets,
                        decision=decision,
                        baseline_eval_path=baseline_eval_path,
                        candidate_eval_path=candidate_eval_path,
                        baseline_mechanism_path=baseline_mechanism_path,
                        candidate_mechanism_path=candidate_mechanism_path,
                    ),
                )
                write_run_session_context(vault, run_id, session_id="auto-session-shared")
                baseline_branch = candidate_branch
                baseline_nonempty = candidate_nonempty

            write_session_report(
                vault,
                "auto-session-shared",
                failure_taxonomy_counts={"validation_blocked": 1},
                executor_role_counts={"validator": 1},
            )

            policy, policy_path = load_policy(vault)
            original_load_optional_json = mechanism_review_runtime._load_optional_json
            telemetry_read_counts: dict[str, int] = {}

            def counting_load_optional_json(path: Path) -> dict | None:
                if path.name == "run-telemetry.json":
                    key = report_path(vault, path)
                    telemetry_read_counts[key] = telemetry_read_counts.get(key, 0) + 1
                return original_load_optional_json(path)

            with mock.patch.object(
                mechanism_review_runtime,
                "_load_optional_json",
                side_effect=counting_load_optional_json,
            ):
                report = build_report(vault, policy, policy_path)

            self.assertEqual(len(report["candidates"]), 3)
            self.assertEqual(
                telemetry_read_counts,
                {
                    "runs/run-20260414-a/run-telemetry.json": 1,
                    "runs/run-20260414-b/run-telemetry.json": 1,
                    "runs/run-20260414-c/run-telemetry.json": 1,
                },
            )

    def test_disabled_session_calibration_emits_disabled_diagnostics_and_omits_candidate_block(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)

            primary_targets = ["ops/scripts/promotion_gate.py"]
            runs = [
                ("run-20260414-a", 18, 26, 2, 10, "DISCARD"),
                ("run-20260414-b", 24, 28, 2, 10, "DISCARD"),
                ("run-20260414-c", 30, 30, 2, 10, "HOLD"),
            ]
            baseline_branch = 24
            baseline_nonempty = 14
            for run_id, candidate_nonempty, candidate_branch, test_cases, eval_score, decision in runs:
                run_dir = vault / "runs" / run_id
                baseline_eval_path = f"runs/{run_id}/baseline-eval.json"
                candidate_eval_path = f"runs/{run_id}/candidate-eval.json"
                baseline_mechanism_path = f"runs/{run_id}/baseline-mechanism.json"
                candidate_mechanism_path = f"runs/{run_id}/candidate-mechanism.json"

                write_json(vault / baseline_eval_path, eval_report(vault, eval_score))
                write_json(vault / candidate_eval_path, eval_report(vault, eval_score))
                write_json(
                    vault / baseline_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=baseline_nonempty,
                        functions=4,
                        branches=baseline_branch,
                        test_file_count=1,
                        test_case_count=test_cases,
                        complexity_score=60,
                    ),
                )
                write_json(
                    vault / candidate_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=candidate_nonempty,
                        functions=4,
                        branches=candidate_branch,
                        test_file_count=1,
                        test_case_count=test_cases,
                        complexity_score=85 if run_id == "run-20260414-c" else 75,
                    ),
                )
                write_json(
                    run_dir / "promotion-report.json",
                    promotion_report(
                        run_id,
                        primary_targets=primary_targets,
                        decision=decision,
                        baseline_eval_path=baseline_eval_path,
                        candidate_eval_path=candidate_eval_path,
                        baseline_mechanism_path=baseline_mechanism_path,
                        candidate_mechanism_path=candidate_mechanism_path,
                    ),
                )
                write_run_session_context(vault, run_id, session_id="auto-session-shared")
                baseline_branch = candidate_branch
                baseline_nonempty = candidate_nonempty

            write_session_report(
                vault,
                "auto-session-shared",
                failure_taxonomy_counts={"validation_blocked": 1},
                executor_role_counts={"validator": 1},
            )

            policy, policy_path = load_policy(vault)
            policy["mechanism_review"]["calibration"]["enabled"] = False
            report = build_report(vault, policy, policy_path)

            self.assertEqual(len(report["candidates"]), 3)
            self.assertTrue(all("session_calibration" not in candidate for candidate in report["candidates"]))
            self.assertEqual(
                report["diagnostics"]["session_calibration"],
                {
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
                },
            )

    def test_historical_calibration_is_family_aware_within_same_target_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)

            primary_targets = ["ops/scripts/promotion_gate.py"]
            runs = [
                ("run-20260414-h1", 18, 26, 10, 10, "HOLD"),
                ("run-20260414-h2", 24, 28, 10, 10, "PROMOTE"),
                ("run-20260414-h3", 30, 30, 10, 10, "DISCARD"),
                ("run-20260414-h4", 36, 32, 10, 10, "HOLD"),
            ]
            baseline_branch = 24
            baseline_nonempty = 14
            for run_id, candidate_nonempty, candidate_branch, baseline_score, candidate_score, decision in runs:
                run_dir = vault / "runs" / run_id
                baseline_eval_path = f"runs/{run_id}/baseline-eval.json"
                candidate_eval_path = f"runs/{run_id}/candidate-eval.json"
                baseline_mechanism_path = f"runs/{run_id}/baseline-mechanism.json"
                candidate_mechanism_path = f"runs/{run_id}/candidate-mechanism.json"

                write_json(vault / baseline_eval_path, eval_report(vault, baseline_score))
                write_json(vault / candidate_eval_path, eval_report(vault, candidate_score))
                write_json(
                    vault / baseline_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=baseline_nonempty,
                        functions=4,
                        branches=baseline_branch,
                        test_file_count=1,
                        test_case_count=2,
                        complexity_score=60,
                    ),
                )
                write_json(
                    vault / candidate_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=candidate_nonempty,
                        functions=4,
                        branches=candidate_branch,
                        test_file_count=1,
                        test_case_count=2,
                        complexity_score=75,
                    ),
                )
                write_json(
                    run_dir / "promotion-report.json",
                    promotion_report(
                        run_id,
                        primary_targets=primary_targets,
                        decision=decision,
                        baseline_eval_path=baseline_eval_path,
                        candidate_eval_path=candidate_eval_path,
                        baseline_mechanism_path=baseline_mechanism_path,
                        candidate_mechanism_path=candidate_mechanism_path,
                    ),
                )
                baseline_branch = candidate_branch
                baseline_nonempty = candidate_nonempty

            policy, policy_path = load_policy(vault)
            report = build_report(vault, policy, policy_path)

            candidates_by_type = {
                candidate["candidate_type"]: candidate for candidate in report["candidates"]
            }
            branch_candidate = candidates_by_type["mechanism_branch_growth_without_test_growth_candidate"]
            stagnation_candidate = candidates_by_type["mechanism_eval_stagnation_candidate"]

            self.assertEqual(
                branch_candidate["historical_calibration"],
                {
                    "lookback_runs": 6,
                    "history_window_runs": 4,
                    "unstable_followup_window": 2,
                    "historical_promote_count": 1,
                    "promoted_then_regressed_count": 1,
                    "repeated_same_eval_after_promote_count": 1,
                    "durable_promote_count": 0,
                    "priority_before_calibration": 80,
                    "priority_delta": 20,
                    "priority_after_calibration": 100,
                },
            )
            self.assertEqual(branch_candidate["priority"], 100)
            self.assertEqual(
                stagnation_candidate["historical_calibration"]["historical_promote_count"],
                0,
            )
            self.assertEqual(
                stagnation_candidate["historical_calibration"]["priority_delta"],
                0,
            )

    def test_historical_calibration_lowers_priority_for_durable_promote_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)

            primary_targets = ["ops/scripts/mechanism_assess.py"]
            runs = [
                ("run-20260414-d1", 18, 26, 10, 10, "HOLD"),
                ("run-20260414-d2", 24, 28, 10, 11, "PROMOTE"),
                ("run-20260414-d3", 30, 30, 10, 11, "HOLD"),
                ("run-20260414-d4", 36, 32, 10, 11, "HOLD"),
            ]
            baseline_branch = 24
            baseline_nonempty = 14
            for run_id, candidate_nonempty, candidate_branch, baseline_score, candidate_score, decision in runs:
                run_dir = vault / "runs" / run_id
                baseline_eval_path = f"runs/{run_id}/baseline-eval.json"
                candidate_eval_path = f"runs/{run_id}/candidate-eval.json"
                baseline_mechanism_path = f"runs/{run_id}/baseline-mechanism.json"
                candidate_mechanism_path = f"runs/{run_id}/candidate-mechanism.json"

                write_json(vault / baseline_eval_path, eval_report(vault, baseline_score))
                write_json(vault / candidate_eval_path, eval_report(vault, candidate_score))
                write_json(
                    vault / baseline_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=baseline_nonempty,
                        functions=4,
                        branches=baseline_branch,
                        test_file_count=1,
                        test_case_count=2,
                        complexity_score=60,
                    ),
                )
                write_json(
                    vault / candidate_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=candidate_nonempty,
                        functions=4,
                        branches=candidate_branch,
                        test_file_count=1,
                        test_case_count=2,
                        complexity_score=75,
                    ),
                )
                write_json(
                    run_dir / "promotion-report.json",
                    promotion_report(
                        run_id,
                        primary_targets=primary_targets,
                        decision=decision,
                        baseline_eval_path=baseline_eval_path,
                        candidate_eval_path=candidate_eval_path,
                        baseline_mechanism_path=baseline_mechanism_path,
                        candidate_mechanism_path=candidate_mechanism_path,
                    ),
                )
                baseline_branch = candidate_branch
                baseline_nonempty = candidate_nonempty

            policy, policy_path = load_policy(vault)
            report = build_report(vault, policy, policy_path)

            self.assertEqual(len(report["candidates"]), 1)
            candidate = report["candidates"][0]
            self.assertEqual(
                candidate["historical_calibration"],
                {
                    "lookback_runs": 6,
                    "history_window_runs": 4,
                    "unstable_followup_window": 2,
                    "historical_promote_count": 1,
                    "promoted_then_regressed_count": 0,
                    "repeated_same_eval_after_promote_count": 0,
                    "durable_promote_count": 1,
                    "priority_before_calibration": 80,
                    "priority_delta": -10,
                    "priority_after_calibration": 70,
                },
            )
            self.assertEqual(candidate["priority"], 70)

    def test_schema_drift_candidate_emits_and_uses_historical_calibration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)

            primary_targets = ["ops/schemas/wiki.schema.json"]
            runs = [
                ("run-20260414-s1", 10, 10, 2, 2, "HOLD", []),
                ("run-20260414-s2", 10, 11, 2, 2, "PROMOTE", ["schema_change"]),
                ("run-20260414-s3", 10, 11, 2, 2, "HOLD", ["schema_change"]),
                ("run-20260414-s4", 10, 11, 2, 2, "PROMOTE", ["schema_change"]),
                ("run-20260414-s5", 10, 10, 2, 2, "HOLD", ["schema_change"]),
            ]
            for run_id, baseline_score, candidate_score, baseline_tests, candidate_tests, decision, risk_flags in runs:
                run_dir = vault / "runs" / run_id
                baseline_eval_path = f"runs/{run_id}/baseline-eval.json"
                candidate_eval_path = f"runs/{run_id}/candidate-eval.json"
                baseline_mechanism_path = f"runs/{run_id}/baseline-mechanism.json"
                candidate_mechanism_path = f"runs/{run_id}/candidate-mechanism.json"

                write_json(vault / baseline_eval_path, eval_report(vault, baseline_score))
                write_json(vault / candidate_eval_path, eval_report(vault, candidate_score))
                write_json(
                    vault / baseline_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=12,
                        functions=2,
                        branches=4,
                        test_file_count=1,
                        test_case_count=baseline_tests,
                        complexity_score=50,
                    ),
                )
                write_json(
                    vault / candidate_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=12,
                        functions=2,
                        branches=4,
                        test_file_count=1,
                        test_case_count=candidate_tests,
                        complexity_score=55,
                        risk_flags=risk_flags,
                    ),
                )
                write_json(
                    run_dir / "promotion-report.json",
                    promotion_report(
                        run_id,
                        primary_targets=primary_targets,
                        decision=decision,
                        baseline_eval_path=baseline_eval_path,
                        candidate_eval_path=candidate_eval_path,
                        baseline_mechanism_path=baseline_mechanism_path,
                        candidate_mechanism_path=candidate_mechanism_path,
                    ),
                )

            policy, policy_path = load_policy(vault)
            report = build_report(vault, policy, policy_path)

            schema_candidate = next(
                candidate
                for candidate in report["candidates"]
                if candidate["candidate_type"] == "mechanism_schema_drift_candidate"
            )
            self.assertEqual(schema_candidate["family"], "schema_drift")
            self.assertEqual(
                schema_candidate["metrics_triggered"],
                [
                    "schema_change_without_test_growth",
                    "promoted_schema_change_without_guardrails",
                    "latest_schema_change_still_uncovered",
                ],
            )
            self.assertEqual(
                schema_candidate["evidence"]["schema_change_without_test_growth_promotions"],
                2,
            )
            self.assertEqual(
                schema_candidate["historical_calibration"],
                {
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
            )
            self.assertEqual(schema_candidate["priority"], 75)

    def test_session_calibration_raises_schema_drift_priority_from_session_rollups(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)

            primary_targets = ["ops/schemas/wiki.schema.json"]
            runs = [
                ("run-20260414-sc1", 10, 10, 2, 2, "HOLD", []),
                ("run-20260414-sc2", 10, 11, 2, 2, "PROMOTE", ["schema_change"]),
                ("run-20260414-sc3", 10, 11, 2, 2, "HOLD", ["schema_change"]),
                ("run-20260414-sc4", 10, 11, 2, 2, "PROMOTE", ["schema_change"]),
            ]
            for run_id, baseline_score, candidate_score, baseline_tests, candidate_tests, decision, risk_flags in runs:
                run_dir = vault / "runs" / run_id
                baseline_eval_path = f"runs/{run_id}/baseline-eval.json"
                candidate_eval_path = f"runs/{run_id}/candidate-eval.json"
                baseline_mechanism_path = f"runs/{run_id}/baseline-mechanism.json"
                candidate_mechanism_path = f"runs/{run_id}/candidate-mechanism.json"

                write_json(vault / baseline_eval_path, eval_report(vault, baseline_score))
                write_json(vault / candidate_eval_path, eval_report(vault, candidate_score))
                write_json(
                    vault / baseline_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=12,
                        functions=2,
                        branches=4,
                        test_file_count=1,
                        test_case_count=baseline_tests,
                        complexity_score=50,
                    ),
                )
                write_json(
                    vault / candidate_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=12,
                        functions=2,
                        branches=4,
                        test_file_count=1,
                        test_case_count=candidate_tests,
                        complexity_score=55,
                        risk_flags=risk_flags,
                    ),
                )
                write_json(
                    run_dir / "promotion-report.json",
                    promotion_report(
                        run_id,
                        primary_targets=primary_targets,
                        decision=decision,
                        baseline_eval_path=baseline_eval_path,
                        candidate_eval_path=candidate_eval_path,
                        baseline_mechanism_path=baseline_mechanism_path,
                        candidate_mechanism_path=candidate_mechanism_path,
                    ),
                )

            write_run_session_context(vault, "run-20260414-sc2", session_id="auto-session-schema-1")
            write_run_session_context(vault, "run-20260414-sc4", session_id="auto-session-schema-2")
            write_session_report(
                vault,
                "auto-session-schema-1",
                failure_taxonomy_counts={"validation_blocked": 1},
                executor_role_counts={"validator": 1},
                routing_extras={
                    "model_counts": {"gpt-5.6-sol": 99},
                    "reasoning_effort_counts": {"xhigh": 99},
                },
                telemetry_extras={
                    "phase_totals_seconds": {"routing": 999.0},
                    "phase_max_seconds": {"routing": 999.0},
                },
            )

            policy, policy_path = load_policy(vault)
            report = build_report(vault, policy, policy_path)

            schema_candidate = next(
                candidate
                for candidate in report["candidates"]
                if candidate["candidate_type"] == "mechanism_schema_drift_candidate"
            )
            self.assertEqual(
                schema_candidate["session_calibration"],
                {
                    "runs_with_session_context": 2,
                    "sessions_considered": 2,
                    "sessions_with_rollups": 1,
                    "validation_blocked_sessions": 1,
                    "review_blocked_sessions": 0,
                    "mutation_failed_sessions": 0,
                    "validator_dispatch_sessions": 1,
                    "reviewer_dispatch_sessions": 0,
                    "high_risk_routing_sessions": 0,
                    "priority_before_calibration": 70,
                    "priority_delta": 8,
                    "priority_after_calibration": 78,
                },
            )
            self.assertEqual(schema_candidate["priority"], 78)
            self.assertEqual(
                report["diagnostics"]["session_calibration"],
                {
                    "enabled": True,
                    "status": "active",
                    "candidate_count": 1,
                    "candidates_with_session_context": 1,
                    "candidates_with_rollups": 1,
                    "candidates_without_session_context": 0,
                    "runs_with_session_context": 2,
                    "sessions_considered": 2,
                    "sessions_with_rollups": 1,
                    "validation_blocked_sessions": 1,
                    "review_blocked_sessions": 0,
                    "mutation_failed_sessions": 0,
                    "validator_dispatch_sessions": 1,
                    "reviewer_dispatch_sessions": 0,
                    "high_risk_routing_sessions": 0,
                    "total_priority_delta": 8,
                    "boosted_candidates": 1,
                    "lowered_candidates": 0,
                    "unchanged_candidates": 0,
                    "by_family": [
                        {
                            "family": "schema_drift",
                            "candidates_with_session_context": 1,
                            "candidates_with_rollups": 1,
                            "candidates_without_session_context": 0,
                            "runs_with_session_context": 2,
                            "sessions_considered": 2,
                            "sessions_with_rollups": 1,
                            "validation_blocked_sessions": 1,
                            "review_blocked_sessions": 0,
                            "mutation_failed_sessions": 0,
                            "validator_dispatch_sessions": 1,
                            "reviewer_dispatch_sessions": 0,
                            "high_risk_routing_sessions": 0,
                            "total_priority_delta": 8,
                            "boosted_candidates": 1,
                            "lowered_candidates": 0,
                            "unchanged_candidates": 0,
                        }
                    ],
                },
            )

    def test_policy_complexity_growth_candidate_emits_and_uses_historical_calibration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)

            primary_targets = ["ops/policies/wiki-maintainer-policy.yaml"]
            supporting_targets = ["ops/scripts/promotion_gate_mechanism_runtime.py"]
            runs = [
                ("run-20260414-p1", 18, 30, 60, 68, 10, 10, "HOLD"),
                ("run-20260414-p2", 30, 40, 68, 75, 10, 10, "PROMOTE"),
                ("run-20260414-p3", 40, 50, 75, 81, 10, 10, "HOLD"),
            ]
            for (
                run_id,
                baseline_nonempty,
                candidate_nonempty,
                baseline_complexity,
                candidate_complexity,
                baseline_score,
                candidate_score,
                decision,
            ) in runs:
                run_dir = vault / "runs" / run_id
                baseline_eval_path = f"runs/{run_id}/baseline-eval.json"
                candidate_eval_path = f"runs/{run_id}/candidate-eval.json"
                baseline_mechanism_path = f"runs/{run_id}/baseline-mechanism.json"
                candidate_mechanism_path = f"runs/{run_id}/candidate-mechanism.json"

                write_json(vault / baseline_eval_path, eval_report(vault, baseline_score))
                write_json(vault / candidate_eval_path, eval_report(vault, candidate_score))
                write_json(
                    vault / baseline_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=baseline_nonempty,
                        functions=2,
                        branches=4,
                        test_file_count=1,
                        test_case_count=8,
                        complexity_score=baseline_complexity,
                    ),
                )
                candidate_mechanism = mechanism_report(
                    vault,
                    primary_targets=primary_targets,
                    nonempty=candidate_nonempty,
                    functions=2,
                    branches=4,
                    test_file_count=1,
                    test_case_count=8,
                    complexity_score=candidate_complexity,
                )
                candidate_mechanism["supporting_targets"] = supporting_targets
                candidate_mechanism["complexity_profile"]["supporting_targets"] = supporting_targets
                write_json(vault / candidate_mechanism_path, candidate_mechanism)
                write_json(
                    run_dir / "promotion-report.json",
                    promotion_report(
                        run_id,
                        primary_targets=primary_targets,
                        decision=decision,
                        baseline_eval_path=baseline_eval_path,
                        candidate_eval_path=candidate_eval_path,
                        baseline_mechanism_path=baseline_mechanism_path,
                        candidate_mechanism_path=candidate_mechanism_path,
                    ),
                )

            policy, policy_path = load_policy(vault)
            report = build_report(vault, policy, policy_path)

            policy_candidate = next(
                candidate
                for candidate in report["candidates"]
                if candidate["candidate_type"] == "mechanism_policy_complexity_growth_candidate"
            )
            self.assertEqual(policy_candidate["family"], "policy_complexity_growth")
            self.assertEqual(
                policy_candidate["metrics_triggered"],
                [
                    "policy_surface_growth_without_eval_gain",
                    "policy_complexity_score_growth",
                    "policy_nonempty_growth",
                ],
            )
            self.assertEqual(
                policy_candidate["evidence"]["policy_surface_growth_without_eval_gain_runs"],
                3,
            )
            self.assertEqual(
                policy_candidate["evidence"]["policy_pruning_positive_signal_runs"],
                0,
            )
            self.assertFalse(
                policy_candidate["evidence"]["latest_policy_pruning_positive_signal"]
            )
            self.assertEqual(
                policy_candidate["evidence"]["policy_targets_summary"],
                "ops/policies/wiki-maintainer-policy.yaml",
            )
            self.assertEqual(
                policy_candidate["historical_calibration"],
                {
                    "lookback_runs": 6,
                    "history_window_runs": 3,
                    "unstable_followup_window": 2,
                    "historical_promote_count": 1,
                    "promoted_then_regressed_count": 0,
                    "repeated_same_eval_after_promote_count": 1,
                    "durable_promote_count": 0,
                    "priority_before_calibration": 70,
                    "priority_delta": 10,
                    "priority_after_calibration": 80,
                },
            )
            self.assertEqual(policy_candidate["priority"], 80)

    def test_policy_complexity_growth_candidate_records_pruning_positive_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)

            primary_targets = ["ops/policies/wiki-maintainer-policy.yaml"]
            supporting_targets = ["ops/scripts/promotion_gate_mechanism_runtime.py"]
            runs = [
                ("run-20260414-pg1", 20, 30, 60, 68, 10, 10),
                ("run-20260414-pg2", 30, 40, 68, 75, 10, 10),
                ("run-20260414-prune", 40, 30, 75, 68, 10, 10),
            ]
            for (
                run_id,
                baseline_nonempty,
                candidate_nonempty,
                baseline_complexity,
                candidate_complexity,
                baseline_score,
                candidate_score,
            ) in runs:
                run_dir = vault / "runs" / run_id
                baseline_eval_path = f"runs/{run_id}/baseline-eval.json"
                candidate_eval_path = f"runs/{run_id}/candidate-eval.json"
                baseline_mechanism_path = f"runs/{run_id}/baseline-mechanism.json"
                candidate_mechanism_path = f"runs/{run_id}/candidate-mechanism.json"

                write_json(vault / baseline_eval_path, eval_report(vault, baseline_score))
                write_json(vault / candidate_eval_path, eval_report(vault, candidate_score))
                write_json(
                    vault / baseline_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=baseline_nonempty,
                        functions=2,
                        branches=4,
                        test_file_count=1,
                        test_case_count=8,
                        complexity_score=baseline_complexity,
                    ),
                )
                candidate_mechanism = mechanism_report(
                    vault,
                    primary_targets=primary_targets,
                    nonempty=candidate_nonempty,
                    functions=2,
                    branches=4,
                    test_file_count=1,
                    test_case_count=8,
                    complexity_score=candidate_complexity,
                )
                candidate_mechanism["supporting_targets"] = supporting_targets
                candidate_mechanism["complexity_profile"]["supporting_targets"] = (
                    supporting_targets
                )
                write_json(vault / candidate_mechanism_path, candidate_mechanism)
                write_json(
                    run_dir / "promotion-report.json",
                    promotion_report(
                        run_id,
                        primary_targets=primary_targets,
                        decision="HOLD",
                        baseline_eval_path=baseline_eval_path,
                        candidate_eval_path=candidate_eval_path,
                        baseline_mechanism_path=baseline_mechanism_path,
                        candidate_mechanism_path=candidate_mechanism_path,
                    ),
                )

            policy, policy_path = load_policy(vault)
            report = build_report(vault, policy, policy_path)

            policy_candidate = next(
                candidate
                for candidate in report["candidates"]
                if candidate["candidate_type"] == "mechanism_policy_complexity_growth_candidate"
            )

            self.assertIn(
                "policy_pruning_positive_signal",
                policy_candidate["metrics_triggered"],
            )
            self.assertEqual(
                policy_candidate["evidence"]["policy_surface_growth_without_eval_gain_runs"],
                2,
            )
            self.assertEqual(
                policy_candidate["evidence"]["policy_pruning_positive_signal_runs"],
                1,
            )
            self.assertEqual(
                policy_candidate["evidence"]["policy_pruning_positive_signal_run_ids"],
                "run-20260414-prune",
            )
            self.assertTrue(
                policy_candidate["evidence"]["latest_policy_pruning_positive_signal"]
            )
            self.assertEqual(
                policy_candidate["evidence"]["policy_pruning_priority_credit"],
                5,
            )

    def test_session_calibration_lowers_policy_complexity_priority_for_failure_heavy_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)

            primary_targets = ["ops/policies/wiki-maintainer-policy.yaml"]
            supporting_targets = ["ops/scripts/promotion_gate_mechanism_runtime.py"]
            runs = [
                ("run-20260414-pc1", 18, 30, 60, 68, 10, 10, "HOLD"),
                ("run-20260414-pc2", 30, 40, 68, 75, 10, 10, "PROMOTE"),
                ("run-20260414-pc3", 40, 50, 75, 81, 10, 10, "HOLD"),
            ]
            for (
                run_id,
                baseline_nonempty,
                candidate_nonempty,
                baseline_complexity,
                candidate_complexity,
                baseline_score,
                candidate_score,
                decision,
            ) in runs:
                run_dir = vault / "runs" / run_id
                baseline_eval_path = f"runs/{run_id}/baseline-eval.json"
                candidate_eval_path = f"runs/{run_id}/candidate-eval.json"
                baseline_mechanism_path = f"runs/{run_id}/baseline-mechanism.json"
                candidate_mechanism_path = f"runs/{run_id}/candidate-mechanism.json"

                write_json(vault / baseline_eval_path, eval_report(vault, baseline_score))
                write_json(vault / candidate_eval_path, eval_report(vault, candidate_score))
                write_json(
                    vault / baseline_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=baseline_nonempty,
                        functions=2,
                        branches=4,
                        test_file_count=1,
                        test_case_count=8,
                        complexity_score=baseline_complexity,
                    ),
                )
                candidate_mechanism = mechanism_report(
                    vault,
                    primary_targets=primary_targets,
                    nonempty=candidate_nonempty,
                    functions=2,
                    branches=4,
                    test_file_count=1,
                    test_case_count=8,
                    complexity_score=candidate_complexity,
                )
                candidate_mechanism["supporting_targets"] = supporting_targets
                candidate_mechanism["complexity_profile"]["supporting_targets"] = supporting_targets
                write_json(vault / candidate_mechanism_path, candidate_mechanism)
                write_json(
                    run_dir / "promotion-report.json",
                    promotion_report(
                        run_id,
                        primary_targets=primary_targets,
                        decision=decision,
                        baseline_eval_path=baseline_eval_path,
                        candidate_eval_path=candidate_eval_path,
                        baseline_mechanism_path=baseline_mechanism_path,
                        candidate_mechanism_path=candidate_mechanism_path,
                    ),
                )

            write_run_session_context(vault, "run-20260414-pc1", session_id="auto-session-policy-1")
            write_run_session_context(vault, "run-20260414-pc2", session_id="auto-session-policy-2")
            write_run_session_context(vault, "run-20260414-pc3", session_id="auto-session-policy-2")
            write_session_report(
                vault,
                "auto-session-policy-1",
                failure_taxonomy_counts={"mutation_failed": 1},
                risk_flag_counts={"destructive_command": 1},
            )
            write_session_report(
                vault,
                "auto-session-policy-2",
                failure_taxonomy_counts={"mutation_failed": 2},
                risk_flag_counts={"policy_surface": 1},
            )

            policy, policy_path = load_policy(vault)
            policy["mechanism_review"]["calibration"]["priority_adjustments"] = {
                "promoted_then_regressed": 0,
                "repeated_same_eval_after_promote": 0,
                "durable_promote": 0,
            }
            report = build_report(vault, policy, policy_path)

            policy_candidate = next(
                candidate
                for candidate in report["candidates"]
                if candidate["candidate_type"] == "mechanism_policy_complexity_growth_candidate"
            )
            self.assertEqual(
                policy_candidate["session_calibration"],
                {
                    "runs_with_session_context": 3,
                    "sessions_considered": 2,
                    "sessions_with_rollups": 2,
                    "validation_blocked_sessions": 0,
                    "review_blocked_sessions": 0,
                    "mutation_failed_sessions": 2,
                    "validator_dispatch_sessions": 0,
                    "reviewer_dispatch_sessions": 0,
                    "high_risk_routing_sessions": 2,
                    "priority_before_calibration": 70,
                    "priority_delta": -12,
                    "priority_after_calibration": 58,
                },
            )
            self.assertEqual(policy_candidate["priority"], 58)
            self.assertEqual(report["diagnostics"]["session_calibration"]["status"], "active")
            self.assertTrue(report["diagnostics"]["session_calibration"]["enabled"])
            family_summary = next(
                item
                for item in report["diagnostics"]["session_calibration"]["by_family"]
                if item["family"] == "policy_complexity_growth"
            )
            self.assertEqual(
                family_summary,
                {
                    "family": "policy_complexity_growth",
                    "candidates_with_session_context": 1,
                    "candidates_with_rollups": 1,
                    "candidates_without_session_context": 0,
                    "runs_with_session_context": 3,
                    "sessions_considered": 2,
                    "sessions_with_rollups": 2,
                    "validation_blocked_sessions": 0,
                    "review_blocked_sessions": 0,
                    "mutation_failed_sessions": 2,
                    "validator_dispatch_sessions": 0,
                    "reviewer_dispatch_sessions": 0,
                    "high_risk_routing_sessions": 2,
                    "total_priority_delta": -12,
                    "boosted_candidates": 0,
                    "lowered_candidates": 1,
                    "unchanged_candidates": 0,
                },
            )

    def test_invalid_run_artifacts_are_reported_as_skipped_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)

            run_id = "run-20260414-bad"
            run_dir = vault / "runs" / run_id
            baseline_eval_path = f"runs/{run_id}/baseline-eval.json"
            candidate_eval_path = f"runs/{run_id}/candidate-eval.json"
            baseline_mechanism_path = f"runs/{run_id}/baseline-mechanism.json"
            candidate_mechanism_path = f"runs/{run_id}/candidate-mechanism.json"

            write_json(vault / baseline_eval_path, eval_report(vault, 10))
            write_json(vault / candidate_eval_path, eval_report(vault, 10))
            write_json(
                vault / baseline_mechanism_path,
                mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=10,
                    functions=2,
                    branches=5,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=50,
                ),
            )
            write_json(
                run_dir / "promotion-report.json",
                promotion_report(
                    run_id,
                    primary_targets=["ops/scripts/example.py"],
                    decision="DISCARD",
                    baseline_eval_path=baseline_eval_path,
                    candidate_eval_path=candidate_eval_path,
                    baseline_mechanism_path=baseline_mechanism_path,
                    candidate_mechanism_path=candidate_mechanism_path,
                ),
            )

            policy, policy_path = load_policy(vault)
            report = build_report(vault, policy, policy_path)

            self.assertEqual(report["summary"]["runs_discovered"], 1)
            self.assertEqual(report["summary"]["runs_considered"], 0)
            self.assertEqual(report["summary"]["runs_skipped"], 1)
            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["candidates"], [])
            self.assertEqual(report["diagnostics"]["bootstrap"]["status"], "no_history")
            blocker_types = {
                item["blocker_type"] for item in report["diagnostics"]["candidate_blockers"]
            }
            self.assertEqual(blocker_types, {"history", "schema", "session", "outcome"})
            self.assertIn(
                "run_artifact_invalid",
                {item["reason"] for item in report["diagnostics"]["candidate_blockers"]},
            )
            self.assertEqual(
                report["diagnostics"]["session_calibration"],
                {
                    "enabled": True,
                    "status": "no_candidates",
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
                },
            )
            self.assertEqual(
                report["diagnostics"]["skipped_runs"][0]["run_id"],
                run_id,
            )
            self.assertEqual(
                report["diagnostics"]["skipped_runs"][0]["triage"]["recommended_action"],
                "restore_missing_artifact_or_archive_run_history",
            )

    def test_single_valid_run_emits_bootstrap_history_insufficient_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)

            run_id = "run-20260414-single"
            primary_targets = ["ops/scripts/planning_gate_validate.py"]
            baseline_eval_path = f"runs/{run_id}/baseline-eval.json"
            candidate_eval_path = f"runs/{run_id}/candidate-eval.json"
            baseline_mechanism_path = f"runs/{run_id}/baseline-mechanism.json"
            candidate_mechanism_path = f"runs/{run_id}/candidate-mechanism.json"

            write_json(vault / baseline_eval_path, eval_report(vault, 10))
            write_json(vault / candidate_eval_path, eval_report(vault, 10))
            write_json(
                vault / baseline_mechanism_path,
                mechanism_report(
                    vault,
                    primary_targets=primary_targets,
                    nonempty=24,
                    functions=3,
                    branches=6,
                    test_file_count=1,
                    test_case_count=2,
                    complexity_score=40,
                ),
            )
            write_json(
                vault / candidate_mechanism_path,
                mechanism_report(
                    vault,
                    primary_targets=primary_targets,
                    nonempty=25,
                    functions=3,
                    branches=7,
                    test_file_count=1,
                    test_case_count=2,
                    complexity_score=45,
                ),
            )
            write_json(
                vault / "runs" / run_id / "promotion-report.json",
                promotion_report(
                    run_id,
                    primary_targets=primary_targets,
                    decision="PROMOTE",
                    baseline_eval_path=baseline_eval_path,
                    candidate_eval_path=candidate_eval_path,
                    baseline_mechanism_path=baseline_mechanism_path,
                    candidate_mechanism_path=candidate_mechanism_path,
                ),
            )

            policy, policy_path = load_policy(vault)
            report = build_report(vault, policy, policy_path)

            self.assertEqual(report["summary"]["runs_discovered"], 1)
            self.assertEqual(report["summary"]["runs_considered"], 1)
            self.assertEqual(report["summary"]["candidates_emitted"], 0)
            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["diagnostics"]["bootstrap"]["status"], "bootstrap_history_insufficient")
            self.assertTrue(
                any(
                    item["blocker_type"] == "history"
                    and item["reason"] == "bootstrap_history_insufficient"
                    and item.get("candidate_type") == "mechanism_eval_stagnation_candidate"
                    for item in report["diagnostics"]["candidate_blockers"]
                )
            )
            self.assertEqual(
                report["diagnostics"]["bootstrap"]["target_groups_under_min_history"][0]["primary_targets"],
                primary_targets,
            )
            self.assertEqual(
                report["diagnostics"]["bootstrap"]["target_groups_under_min_history"][0]["latest_run_id"],
                run_id,
            )
            blocked_types = {
                item["candidate_type"]
                for item in report["diagnostics"]["bootstrap"]["target_groups_under_min_history"][0][
                    "blocked_candidate_types"
                ]
            }
            self.assertEqual(
                blocked_types,
                {
                    "mechanism_branch_growth_without_test_growth_candidate",
                    "mechanism_schema_drift_candidate",
                    "mechanism_policy_complexity_growth_candidate",
                    "mechanism_eval_stagnation_candidate",
                },
            )

    def test_build_report_rewrites_flat_script_aliases_in_live_history_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)

            legacy_target = "ops/scripts/auto_improve_iteration_persistence_runtime.py"
            current_target = "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"
            (vault / "ops" / "scripts" / "mechanism").mkdir(parents=True, exist_ok=True)
            (vault / current_target).write_text(
                "def persist_iteration_state() -> None:\n"
                "    return None\n",
                encoding="utf-8",
            )

            run_id = "run-20260414-flat-alias"
            baseline_eval_path = f"runs/{run_id}/baseline-eval.json"
            candidate_eval_path = f"runs/{run_id}/candidate-eval.json"
            baseline_mechanism_path = f"runs/{run_id}/baseline-mechanism.json"
            candidate_mechanism_path = f"runs/{run_id}/candidate-mechanism.json"

            write_json(vault / baseline_eval_path, eval_report(vault, 10))
            write_json(vault / candidate_eval_path, eval_report(vault, 10))
            write_json(
                vault / baseline_mechanism_path,
                mechanism_report(
                    vault,
                    primary_targets=[legacy_target],
                    nonempty=24,
                    functions=3,
                    branches=6,
                    test_file_count=1,
                    test_case_count=2,
                    complexity_score=40,
                ),
            )
            write_json(
                vault / candidate_mechanism_path,
                mechanism_report(
                    vault,
                    primary_targets=[legacy_target],
                    nonempty=25,
                    functions=3,
                    branches=7,
                    test_file_count=1,
                    test_case_count=2,
                    complexity_score=45,
                ),
            )
            write_json(
                vault / "runs" / run_id / "promotion-report.json",
                promotion_report(
                    run_id,
                    primary_targets=[legacy_target],
                    decision="PROMOTE",
                    baseline_eval_path=baseline_eval_path,
                    candidate_eval_path=candidate_eval_path,
                    baseline_mechanism_path=baseline_mechanism_path,
                    candidate_mechanism_path=candidate_mechanism_path,
                ),
            )

            policy, policy_path = load_policy(vault)
            report = build_report(vault, policy, policy_path)

            group = report["diagnostics"]["bootstrap"]["target_groups_under_min_history"][0]
            self.assertEqual(group["primary_targets"], [current_target])
            self.assertNotIn(legacy_target, json.dumps(group, ensure_ascii=False))

    def test_ready_without_candidates_emits_non_trigger_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)

            primary_targets = ["ops/scripts/planning_gate_validate.py"]
            runs = [
                ("run-20260414-ready-a", 10, 10, 24, 24, 2, 2, 10, 11, "PROMOTE"),
                ("run-20260414-ready-b", 10, 10, 24, 24, 2, 2, 11, 12, "PROMOTE"),
            ]

            for (
                run_id,
                baseline_score,
                candidate_score,
                baseline_nonempty,
                candidate_nonempty,
                baseline_branches,
                candidate_branches,
                baseline_tests,
                candidate_tests,
                decision,
            ) in runs:
                baseline_eval_path = f"runs/{run_id}/baseline-eval.json"
                candidate_eval_path = f"runs/{run_id}/candidate-eval.json"
                baseline_mechanism_path = f"runs/{run_id}/baseline-mechanism.json"
                candidate_mechanism_path = f"runs/{run_id}/candidate-mechanism.json"

                write_json(vault / baseline_eval_path, eval_report(vault, baseline_score))
                write_json(vault / candidate_eval_path, eval_report(vault, candidate_score))
                write_json(
                    vault / baseline_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=baseline_nonempty,
                        functions=2,
                        branches=baseline_branches,
                        test_file_count=2,
                        test_case_count=baseline_tests,
                        complexity_score=40,
                    ),
                )
                write_json(
                    vault / candidate_mechanism_path,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=candidate_nonempty,
                        functions=2,
                        branches=candidate_branches,
                        test_file_count=2,
                        test_case_count=candidate_tests,
                        complexity_score=40,
                    ),
                )
                write_json(
                    vault / "runs" / run_id / "promotion-report.json",
                    promotion_report(
                        run_id,
                        primary_targets=primary_targets,
                        decision=decision,
                        baseline_eval_path=baseline_eval_path,
                        candidate_eval_path=candidate_eval_path,
                        baseline_mechanism_path=baseline_mechanism_path,
                        candidate_mechanism_path=candidate_mechanism_path,
                    ),
                )

            policy, policy_path = load_policy(vault)
            report = build_report(vault, policy, policy_path)

            self.assertEqual(report["diagnostics"]["bootstrap"]["status"], "ready")
            self.assertEqual(report["summary"]["candidates_emitted"], 0)
            self.assertEqual(report["status"], "attention")
            self.assertIn(
                "threshold",
                {item["blocker_type"] for item in report["diagnostics"]["candidate_blockers"]},
            )
            self.assertEqual(len(report["diagnostics"]["bootstrap"]["non_trigger_diagnostics"]), 1)

            group = report["diagnostics"]["bootstrap"]["non_trigger_diagnostics"][0]
            self.assertEqual(group["primary_targets"], primary_targets)
            self.assertEqual(group["latest_run_id"], "run-20260414-ready-b")
            details_by_type = {
                item["candidate_type"]: item["detail"] for item in group["candidate_diagnostics"]
            }
            self.assertIn(
                "same_eval_runs=2/3",
                details_by_type["mechanism_eval_stagnation_candidate"],
            )
            self.assertIn(
                "latest_complexity=40/80",
                details_by_type["mechanism_high_complexity_low_test_pressure_candidate"],
            )
            self.assertIn(
                "latest_schema_flags=[]",
                details_by_type["mechanism_schema_drift_candidate"],
            )

    def test_unknown_candidate_type_in_policy_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)

            mutate_policy(
                vault,
                lambda policy: policy["mechanism_review"].__setitem__(
                    "candidate_types",
                    [
                        "mechanism_branch_growth_without_test_growth_candidate",
                        "mechanism_unknown_test_sentinel_candidate",
                        "mechanism_eval_stagnation_candidate",
                    ],
                ),
            )

            policy, resolved_policy_path = load_policy(vault)
            with self.assertRaisesRegex(
                ValueError,
                "mechanism review candidate registry references unknown candidate type",
            ):
                build_report(vault, policy, resolved_policy_path)

    def test_cli_writes_default_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)

            completed = invoke_cli_main(
                mechanism_review_main,
                ["--vault", str(vault)],
                cwd=vault,
            )
            self.assertEqual(completed.exit_code, 0, msg=completed.stderr or completed.stdout)

            report_path = vault / "ops" / "reports" / "mechanism-review-candidates.json"
            self.assertTrue(report_path.exists())
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "attention")
            self.assertEqual(payload["summary"]["runs_discovered"], 0)
            self.assertEqual(payload["candidates"], [])
            self.assertEqual(payload["diagnostics"]["bootstrap"]["status"], "no_history")


if __name__ == "__main__":
    unittest.main()
