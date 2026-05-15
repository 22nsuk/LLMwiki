from __future__ import annotations

import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.mutation_proposal import main as mutation_proposal_main
from ops.scripts.mutation_proposal_runtime import build_report
from ops.scripts.policy_runtime import load_policy
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.cli_test_runtime import invoke_cli_main


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "ops" / "policies" / "wiki-maintainer-policy.yaml"
ENVELOPE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "artifact-envelope.schema.json"
LIVE_POLICY_VERSION = load_policy(REPO_ROOT)[0]["version"]
SCHEMA_NAMES = (
    "wiki-maintainer-policy.schema.json",
    "mechanism-review-candidates.schema.json",
    "mutation-proposals.schema.json",
)


def seed_vault(vault: Path) -> None:
    (vault / "ops" / "policies").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "schemas").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
    (vault / "system").mkdir(parents=True, exist_ok=True)
    (vault / "tests").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "policies" / "wiki-maintainer-policy.yaml").write_text(
        POLICY_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for name in SCHEMA_NAMES:
        source = REPO_ROOT / "ops" / "schemas" / name
        (vault / "ops" / "schemas" / name).write_text(
            source.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    for rel_path in (
        "tests/test_promotion_gate.py",
        "tests/test_wiki_lint.py",
        "tests/test_mechanism_assess.py",
        "tests/test_example.py",
    ):
        (vault / rel_path).write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    payload_to_write = copy.deepcopy(payload)
    if "generated_at" in payload_to_write:
        timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        payload_to_write["generated_at"] = timestamp
        currentness = payload_to_write.get("currentness")
        if isinstance(currentness, dict):
            currentness["checked_at"] = timestamp
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload_to_write, ensure_ascii=False, indent=2), encoding="utf-8")


def shadow_priority_diagnostics(*, attempts_considered: int = 0) -> dict:
    return {
        "status": "disabled",
        "gate_effect": "none",
        "min_attempts_considered": 10,
        "min_target_attempts": 2,
        "shadow_priority_max_delta": 10,
        "attempts_considered": attempts_considered,
        "current_order": [],
        "shadow_order": [],
        "order_changed": False,
        "ordering_deltas": [],
    }


def _mechanism_review_envelope() -> dict:
    return {
        "$schema": "ops/schemas/mechanism-review-candidates.schema.json",
        "vault": ".",
        "generated_at": "2026-04-14T00:00:00Z",
        "artifact_kind": "mechanism_review_candidates_report",
        "producer": "tests.test_mutation_proposal",
        "source_command": "pytest",
        "source_revision": "unknown",
        "source_tree_fingerprint": "fixture",
        "input_fingerprints": {
            "policy": "fixture",
            "schema": "fixture",
            "artifact_envelope_schema": "fixture"
        },
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "canonical_report",
        "encoding": "utf-8",
        "currentness": {
            "status": "current",
            "checked_at": "2026-04-14T00:00:00Z"
        },
        "policy": {
            "path": "ops/policies/wiki-maintainer-policy.yaml",
            "version": LIVE_POLICY_VERSION,
        },
        "status": "pass",
        "summary": {
            "runs_discovered": 3,
            "runs_considered": 3,
            "runs_excluded": 0,
            "runs_skipped": 0,
            "candidates_emitted": 3,
        },
    }


def _mechanism_review_bootstrap_diagnostics() -> dict:
    return {
        "status": "ready",
        "summary": "comparable mechanism run history is sufficient and candidates were emitted.",
        "recommended_next_step": "review current candidates",
        "trend_candidate_requirements": [
            {
                "candidate_type": "mechanism_branch_growth_without_test_growth_candidate",
                "evaluation_min_runs": 2,
                "full_window_runs": 2,
            },
            {
                "candidate_type": "mechanism_eval_stagnation_candidate",
                "evaluation_min_runs": 2,
                "full_window_runs": 5,
            },
        ],
        "target_groups_under_min_history": [],
    }


def _session_calibration_family(family: str, candidate_count: int) -> dict:
    return {
        "family": family,
        "candidates_with_session_context": 0,
        "candidates_with_rollups": 0,
        "candidates_without_session_context": candidate_count,
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
        "unchanged_candidates": candidate_count,
    }


def _mechanism_review_session_calibration() -> dict:
    return {
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
            _session_calibration_family("contract_regression_signals", 1),
            _session_calibration_family("self_mod_stability", 2),
        ],
    }


def _mechanism_review_outcome_metrics_calibration() -> dict:
    return {
        "enabled": True,
        "status": "missing_outcome_metrics",
        "mode": "audit_only",
        "gate_effect": "none",
        "source_report": "ops/reports/outcome-metrics.json",
        "recent_window": 20,
        "candidate_count": 3,
        "candidates_with_outcome_context": 0,
        "target_count": 0,
        "thresholds": {
            "high_rework_count": 1,
            "hold_or_discard_moving_average": 0.25,
            "rollback_signal_ratio": 0.2,
            "defect_escape_pair_count": 1,
        },
        "global_signals": {
            "attempt_count": 0,
            "recent_attempt_count": 0,
            "moving_averages": {
                "hold": 0.0,
                "discard": 0.0,
                "rollback_signal": 0.0,
            },
            "rework_count": 0,
            "rollback_signal_count": 0,
            "defect_escape_pair_count": 0,
        },
        "target_signals": [],
        "family_signals": [],
        "high_rework_targets": [],
        "defect_escape_pairs": [],
        "shadow_priority": shadow_priority_diagnostics(),
        "evidence_gaps": [],
        "notes": [
            (
                "audit-only preview: outcome metrics are reported for calibration "
                "review and do not change candidate priority."
            ),
            (
                "priority_delta and gate integration remain disabled until a later "
                "explicit policy step."
            ),
        ],
    }


def _mechanism_review_diagnostics() -> dict:
    return {
        "skipped_runs": [],
        "excluded_runs": [],
        "bootstrap": _mechanism_review_bootstrap_diagnostics(),
        "session_calibration": _mechanism_review_session_calibration(),
        "outcome_metrics_calibration": _mechanism_review_outcome_metrics_calibration(),
        "candidate_blockers": [],
    }


def _mechanism_eval_stagnation_candidate() -> dict:
    return {
        "candidate_id": "mechanism_eval_stagnation_candidate__promotion-gate",
        "candidate_type": "mechanism_eval_stagnation_candidate",
        "family": "contract_regression_signals",
        "tier": "supporting",
        "objective": "detect repeated non-improvement against current contract-eval surfaces",
        "priority": 80,
        "primary_targets": ["ops/scripts/promotion_gate.py"],
        "supporting_targets": ["ops/scripts/promotion_gate_mechanism_runtime.py"],
        "metrics_triggered": ["stage1_same_eval_rate", "repeated_discard_runs"],
        "run_ids": ["run-a", "run-b", "run-c"],
        "signal_run_ids": {
            "repeated_discard_runs": ["run-a", "run-b"],
            "repeated_same_eval_after_promote": ["run-a", "run-b", "run-c"],
        },
        "evidence": {
            "runs_examined": 3,
            "same_eval_runs": 3,
            "discard_runs": 2,
        },
        "rationale": "same eval or discard repeated",
        "suggested_experiments": [
            "try one mechanism-only experiment on ops/scripts/promotion_gate.py"
        ],
    }


def _branch_growth_without_test_growth_candidate() -> dict:
    return {
        "candidate_id": "mechanism_branch_growth_without_test_growth_candidate__wiki-lint",
        "candidate_type": "mechanism_branch_growth_without_test_growth_candidate",
        "family": "self_mod_stability",
        "tier": "core",
        "objective": "iterative self-modification degradation and structural erosion",
        "priority": 70,
        "primary_targets": ["ops/scripts/wiki_lint.py"],
        "supporting_targets": ["ops/scripts/wiki_lint_page_runtime.py"],
        "metrics_triggered": ["branch_growth_without_test_growth", "verbosity_growth"],
        "run_ids": ["run-l1", "run-l2", "run-l3"],
        "evidence": {
            "runs_examined": 3,
            "branch_growth_runs": 3,
            "branch_growth_without_test_growth_runs": 2,
        },
        "rationale": "branch growth repeated without test growth",
        "suggested_experiments": [
            "add focused regression tests for ops/scripts/wiki_lint.py"
        ],
    }


def _high_complexity_low_test_pressure_candidate() -> dict:
    return {
        "candidate_id": "mechanism_high_complexity_low_test_pressure_candidate__mechanism-assess",
        "candidate_type": "mechanism_high_complexity_low_test_pressure_candidate",
        "family": "self_mod_stability",
        "tier": "core",
        "objective": "iterative self-modification degradation and structural erosion",
        "priority": 60,
        "primary_targets": ["ops/scripts/mechanism_assess.py"],
        "supporting_targets": [],
        "metrics_triggered": ["high_complexity_low_test_pressure"],
        "run_ids": ["run-m1"],
        "evidence": {
            "runs_examined": 1,
            "latest_complexity_score": 90,
            "latest_candidate_test_case_count": 2,
        },
        "rationale": "high complexity with low tests",
        "suggested_experiments": [
            "increase mechanism-specific test coverage for ops/scripts/mechanism_assess.py"
        ],
    }


def _mechanism_review_candidates() -> list[dict]:
    return [
        _mechanism_eval_stagnation_candidate(),
        _branch_growth_without_test_growth_candidate(),
        _high_complexity_low_test_pressure_candidate(),
    ]


def mechanism_review_report() -> dict:
    report = _mechanism_review_envelope()
    report["diagnostics"] = _mechanism_review_diagnostics()
    report["candidates"] = _mechanism_review_candidates()
    return report


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
            report = build_report(vault, policy, policy_path)
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
                                "or rotate to a non-overlapping target set"
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
            proposal_report = build_report(vault, policy, policy_path, max_proposals=1)
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

    def test_all_recent_log_overlap_blocked_queue_emits_runnable_rotation_proposal(self) -> None:
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
                "- `ops/scripts/mechanism_assess.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(vault, policy, policy_path)
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
                    "runnable_available_count": 1,
                    "blocked_available_count": 3,
                    "selected_runnable_count": 1,
                    "selected_blocked_count": 3,
                    "blocked_reason_counts": [
                        {"reason": "recent_log_overlap", "count": 3}
                    ],
                },
            )
            self.assertEqual(
                proposal_report["diagnostics"]["recent_log_overlap"]["matches"][0][
                    "matched_marker"
                ],
                "ops/scripts/promotion_gate.py",
            )

            rotation = proposal_report["proposals"][0]
            self.assertEqual(rotation["failure_mode"], "recent_log_overlap_queue_blocked")
            self.assertEqual(
                rotation["source_candidate_type"],
                "mechanism_recent_log_overlap_queue_unblock_candidate",
            )
            self.assertEqual(rotation["primary_targets"], ["ops/scripts/mutation_proposal_runtime.py"])
            self.assertEqual(rotation["must_change_tests"], ["tests/test_mutation_proposal.py"])
            self.assertEqual(rotation["blocked_by"], [])
            self.assertEqual(
                rotation["must_change_budget_signal"],
                {
                    "signal": "mutation_proposal.queue_selection.runnable_available_count",
                    "expected_change": "greater_than_zero",
                },
            )

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
            proposal_report = build_report(vault, policy, policy_path, dedupe_window=1)

            self.assertEqual(proposal_report["diagnostics"]["recent_log_overlap"]["section_ordering"], "timestamp")
            self.assertEqual(
                proposal_report["diagnostics"]["recent_log_overlap"]["scanned_log_headings"],
                ["[2026-04-14 12:00] decision | newer unrelated"],
            )
            self.assertEqual(proposal_report["diagnostics"]["recent_log_overlap"]["matches"], [])
            self.assertEqual(proposal_report["proposals"][0]["blocked_by"], [])

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
                    "primary_targets": ["ops/scripts/auto_improve_iteration_persistence_runtime.py"],
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
                        "primary_targets": ["ops/scripts/auto_improve_iteration_persistence_runtime.py"],
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
                ["ops/scripts/auto_improve_iteration_persistence_runtime.py"],
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
            proposal_report = build_report(vault, policy, policy_path)

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
