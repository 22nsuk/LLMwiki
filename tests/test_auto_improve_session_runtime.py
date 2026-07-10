from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.mechanism.auto_improve_session_runtime import (
    build_learning_summary,
    build_outcome_metrics_rollup,
    build_session_rollups,
    load_optional_json,
    normalize_session_report,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class AutoImproveSessionRuntimeTests(unittest.TestCase):
    def test_build_session_rollups_summarizes_run_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            run_id = "auto-session-run-01"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)

            _write_json(
                run_dir / "subagent-routing.worker.json",
                {
                    "role": "worker",
                    "routing_decision": {
                        "selected_rung": 3,
                        "score_band": "low",
                        "sandbox_mode": "workspace-write",
                        "model": "gpt-5.6-sol",
                        "reasoning_effort": "high",
                    },
                    "complexity_profile": {"risk_flags": ["runtime_touch", "runtime_touch", ""]},
                },
            )
            _write_json(
                run_dir / "subagent-routing.validator.json",
                {
                    "role": "validator",
                    "routing_decision": {
                        "selected_rung": 2,
                        "score_band": "low",
                        "sandbox_mode": "read-only",
                        "model": "gpt-5.6-sol",
                        "reasoning_effort": "xhigh",
                    },
                    "complexity_profile": {"risk_flags": ["contract_touch"]},
                },
            )
            (run_dir / "subagent-routing.invalid.json").write_text("{", encoding="utf-8")
            _write_json(
                run_dir / "worker-executor-report.json",
                {
                    "role": "worker",
                    "status": "pass",
                    "result": {"returncode": 0},
                },
            )
            _write_json(
                run_dir / "validator-executor-report.json",
                {
                    "role": "validator",
                    "status": "fail",
                    "result": {"returncode": 1},
                },
            )
            _write_json(run_dir / "reviewer-executor-report.json", ["not", "a", "report"])
            _write_json(
                run_dir / "run-telemetry.json",
                {
                    "failure_taxonomy": "validation_blocked",
                    "phase_durations": {
                        "routing": 1.1114,
                        "execution": "2.5",
                        "ignored": "not-a-number",
                    },
                },
            )
            session = {
                "session_id": "auto-session",
                "run_ids": [run_id],
                "quarantined_proposal_ids": ["proposal-a"],
                "iterations": [
                    {
                        "status": "completed",
                        "proposal_id": "proposal-a",
                        "run_id": run_id,
                        "decision": "DISCARD",
                        "outcome": "validation_blocked",
                    }
                ],
            }

            normalized = normalize_session_report(vault, session)
            rollups = build_session_rollups(vault, session)

            self.assertEqual(
                normalized["iterations"][0]["routing_reports"],
                [
                    f"runs/{run_id}/subagent-routing.validator.json",
                    f"runs/{run_id}/subagent-routing.worker.json",
                ],
            )
            self.assertEqual(
                normalized["iterations"][0]["executor_reports"],
                [
                    f"runs/{run_id}/validator-executor-report.json",
                    f"runs/{run_id}/worker-executor-report.json",
                ],
            )
            self.assertEqual(normalized["iterations"][0]["run_telemetry"], f"runs/{run_id}/run-telemetry.json")
            self.assertEqual(normalized["iterations"][0]["promotion_report"], "")
            self.assertEqual(normalized["iterations"][0]["primary_targets"], [])
            self.assertTrue(normalized["iterations"][0]["quarantined"])
            self.assertEqual(
                normalized["learning_summary"],
                {
                    "attempt_count": 1,
                    "rework_count": 0,
                    "rollback_signal_count": 0,
                    "defect_escape_pair_count": 0,
                    "session_context_status": "session_context_available",
                    "evidence_gaps": [],
                },
            )
            self.assertEqual(
                rollups["iterations"],
                {
                    "count": 1,
                    "outcome_counts": {"validation_blocked": 1},
                    "decision_counts": {"DISCARD": 1},
                    "status_counts": {"completed": 1},
                    "quarantined_proposal_count": 1,
                },
            )
            self.assertEqual(rollups["routing"]["report_count"], 2)
            self.assertEqual(rollups["routing"]["role_counts"], {"validator": 1, "worker": 1})
            self.assertEqual(rollups["routing"]["selected_rung_counts"], {"2": 1, "3": 1})
            self.assertEqual(rollups["routing"]["score_band_counts"], {"low": 2})
            self.assertEqual(
                rollups["routing"]["sandbox_mode_counts"],
                {"read-only": 1, "workspace-write": 1},
            )
            self.assertEqual(rollups["routing"]["model_counts"], {"gpt-5.6-sol": 2})
            self.assertEqual(rollups["routing"]["reasoning_effort_counts"], {"high": 1, "xhigh": 1})
            self.assertEqual(
                rollups["routing"]["risk_flag_counts"],
                {"contract_touch": 1, "runtime_touch": 2},
            )
            self.assertEqual(rollups["executor"]["report_count"], 2)
            self.assertEqual(rollups["executor"]["status_counts"], {"fail": 1, "pass": 1})
            self.assertEqual(rollups["executor"]["returncode_counts"], {"0": 1, "1": 1})
            self.assertEqual(rollups["executor"]["blocking_role_counts"], {"validator": 1})
            self.assertEqual(rollups["telemetry"]["report_count"], 1)
            self.assertEqual(
                rollups["telemetry"]["failure_taxonomy_counts"],
                {"validation_blocked": 1},
            )
            self.assertEqual(rollups["telemetry"]["phase_totals_seconds"], {"execution": 2.5, "routing": 1.111})
            self.assertEqual(rollups["telemetry"]["phase_max_seconds"], {"execution": 2.5, "routing": 1.111})
            self.assertEqual(rollups["outcome_metrics"]["attempt_count"], 1)
            self.assertEqual(rollups["outcome_metrics"]["moving_averages"]["discard"], 1.0)
            self.assertEqual(rollups["outcome_metrics"]["operator_effort_proxy"]["executor_report_count"], 2)
            self.assertEqual(rollups["outcome_metrics"]["operator_effort_proxy"]["validator_dispatch_count"], 1)

    def test_build_outcome_metrics_rollup_tracks_rework_rollback_and_defect_escape_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            target = "ops/scripts/example.py"
            promote_run = "run-promote"
            hold_run = "run-hold"
            _write_json(
                vault / "runs" / promote_run / "run-telemetry.json",
                {
                    "generated_at": "2026-04-15T01:00:00Z",
                    "proposal_id": "proposal-a",
                    "primary_targets": [target],
                    "phase_durations": {"experiment": 10.0},
                    "executor_reports": [f"runs/{promote_run}/worker-executor-report.json"],
                    "decision": "PROMOTE",
                },
            )
            _write_json(
                vault / "runs" / promote_run / "worker-executor-report.json",
                {"role": "worker", "status": "pass", "result": {"returncode": 0}},
            )
            _write_json(
                vault / "runs" / hold_run / "run-telemetry.json",
                {
                    "generated_at": "2026-04-15T02:00:00Z",
                    "proposal_id": "proposal-a",
                    "primary_targets": [target],
                    "phase_durations": {"experiment": 5.0},
                    "executor_reports": [
                        f"runs/{hold_run}/reviewer-executor-report.json",
                        f"runs/{hold_run}/validator-executor-report.json",
                    ],
                    "rollback_rehearsal_report": f"runs/{hold_run}/rollback-rehearsal-report.json",
                    "decision": "HOLD",
                },
            )
            _write_json(
                vault / "runs" / hold_run / "reviewer-executor-report.json",
                {"role": "reviewer", "status": "pass", "result": {"returncode": 0}},
            )
            _write_json(
                vault / "runs" / hold_run / "validator-executor-report.json",
                {"role": "validator", "status": "fail", "result": {"returncode": 1}},
            )
            _write_json(
                vault / "runs" / hold_run / "rollback-rehearsal-report.json",
                {"status": "fail"},
            )
            session = {
                "session_id": "auto-session",
                "iterations": [
                    {
                        "index": 1,
                        "proposal_id": "proposal-a",
                        "run_id": promote_run,
                        "status": "complete",
                        "outcome": "promoted",
                        "decision": "PROMOTE",
                    },
                    {
                        "index": 2,
                        "proposal_id": "proposal-a",
                        "run_id": hold_run,
                        "status": "blocked",
                        "outcome": "hold",
                        "decision": "HOLD",
                    },
                ],
            }

            metrics = build_outcome_metrics_rollup(vault, session)
            learning_summary = build_learning_summary(vault, session)

            self.assertEqual(metrics["attempt_count"], 2)
            self.assertEqual(metrics["rework_count"], 1)
            self.assertEqual(metrics["rework_keys"][0]["key"], "proposal:proposal-a")
            self.assertEqual(metrics["moving_averages"]["hold"], 0.5)
            self.assertEqual(metrics["moving_averages"]["rollback_signal"], 0.5)
            self.assertEqual(metrics["rollback_signal_count"], 1)
            self.assertEqual(metrics["rollback_rehearsal_coverage_count"], 1)
            self.assertEqual(metrics["operator_effort_proxy"]["phase_totals_seconds"], {"experiment": 15.0})
            self.assertEqual(metrics["operator_effort_proxy"]["executor_report_count"], 3)
            self.assertEqual(metrics["operator_effort_proxy"]["reviewer_dispatch_count"], 1)
            self.assertEqual(metrics["operator_effort_proxy"]["validator_dispatch_count"], 1)
            self.assertEqual(metrics["operator_effort_proxy"]["hold_count"], 1)
            self.assertEqual(metrics["defect_escape_proxy"]["count"], 1)
            self.assertEqual(metrics["defect_escape_proxy"]["pairs"][0]["target"], target)
            self.assertEqual(learning_summary["attempt_count"], 2)
            self.assertEqual(learning_summary["rework_count"], 1)
            self.assertEqual(learning_summary["rollback_signal_count"], 1)
            self.assertEqual(learning_summary["defect_escape_pair_count"], 1)
            self.assertEqual(learning_summary["session_context_status"], "no_run_ids")

    def test_build_session_rollups_ignores_malformed_iteration_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            session = {
                "quarantined_proposal_ids": [],
                "run_ids": [],
                "iterations": [
                    ["not", "an", "iteration"],
                    {
                        "status": "complete",
                        "decision": "PROMOTE",
                        "outcome": "promoted",
                    },
                ],
            }

            rollups = build_session_rollups(vault, session)
            learning_summary = build_learning_summary(vault, session)

            self.assertEqual(rollups["iterations"]["count"], 1)
            self.assertEqual(rollups["iterations"]["decision_counts"], {"PROMOTE": 1})
            self.assertEqual(rollups["outcome_metrics"]["attempt_count"], 0)
            self.assertEqual(learning_summary["session_context_status"], "no_run_ids")

    def test_load_optional_json_returns_none_for_missing_or_malformed_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            malformed = root / "bad.json"
            malformed.write_text("{", encoding="utf-8")

            self.assertIsNone(load_optional_json(root / "missing.json"))
            self.assertIsNone(load_optional_json(malformed))


if __name__ == "__main__":
    unittest.main()
