from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.mechanism import (
    auto_improve_runtime,
    auto_improve_session_report_runtime,
)
from tests.run_mechanism_experiment_test_utils import seed_wrapper_vault


class AutoImproveSessionReportRuntimeTests(unittest.TestCase):
    def test_auto_improve_runtime_report_exports_point_to_helper(self) -> None:
        self.assertIs(
            auto_improve_runtime._write_session_report,
            auto_improve_session_report_runtime._write_session_report,
        )
        self.assertIs(
            auto_improve_runtime._load_session_report,
            auto_improve_session_report_runtime._load_session_report,
        )
        self.assertIs(
            auto_improve_runtime.refresh_auto_improve_session_report,
            auto_improve_session_report_runtime.refresh_auto_improve_session_report,
        )

    def test_write_session_report_generated_at_covers_next_run_decision_observed_at(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            policy, resolved_policy_path = load_policy(vault)
            context = RuntimeContext(
                display_timezone=dt.UTC,
                clock=lambda: dt.datetime(2026, 4, 15, 0, 0, 1, tzinfo=dt.UTC),
            )
            session = auto_improve_runtime._new_auto_improve_session(
                vault,
                policy["auto_improve_policy"],
                policy,
                resolved_policy_path,
                session_id="auto-session-clock-skew",
                max_proposals=1,
                max_minutes=90,
                max_consecutive_failures=1,
                requested_executor="codex_exec",
                context=context,
            )
            session["next_run_decisions"] = [
                {
                    "decision_id": "next-run-decision:run-a:clock-skew",
                    "observed_at": "2026-04-15T00:00:02Z",
                    "session_id": "auto-session-clock-skew",
                    "iteration": 1,
                    "source_run_id": "run-a",
                    "proposal_id": "proposal-a",
                    "source_candidate_id": "candidate-a",
                    "target_proposal_id": "next_run_failure_repair__example__review-blocked",
                    "proposal_family": "contract_regression_signals",
                    "proposal_tier": "supporting",
                    "failure_taxonomy": "review_blocked",
                    "blocking_role": "reviewer",
                    "decision": "carry_forward",
                    "next_run_action": "repair_failure",
                    "status": "open",
                    "reason": "clock-skew regression fixture",
                    "quarantined_source_proposal": True,
                    "primary_targets": ["ops/scripts/example.py"],
                    "supporting_targets": [],
                    "must_change_tests": ["tests/test_example.py"],
                    "evidence_paths": ["runs/run-a/run-telemetry.json"],
                }
            ]

            with mock.patch(
                "ops.scripts.mechanism.auto_improve_session_report_runtime."
                "build_canonical_report_envelope",
                wraps=auto_improve_session_report_runtime.build_canonical_report_envelope,
            ) as build_envelope:
                destination = auto_improve_session_report_runtime._write_session_report(
                    vault,
                    session,
                    context=context,
                )

            persisted = json.loads(destination.read_text(encoding="utf-8"))
            embedded_envelope = json.loads(
                next(
                    item["value"]
                    for item in persisted["metadata"]["properties"]
                    if item["name"] == "urn:openai:artifact-envelope"
                )
            )
            self.assertEqual(persisted["generated_at"], "2026-04-15T00:00:02Z")
            self.assertEqual(embedded_envelope["generated_at"], "2026-04-15T00:00:02Z")
            self.assertEqual(
                embedded_envelope["currentness"]["checked_at"],
                "2026-04-15T00:00:02Z",
            )
            self.assertEqual(embedded_envelope["$schema"], "ops/schemas/auto-improve-session.schema.json")
            self.assertEqual(embedded_envelope["artifact_kind"], "auto_improve_session")
            self.assertEqual(embedded_envelope["producer"], "ops.scripts.auto_improve_runtime")
            self.assertEqual(
                embedded_envelope["source_command"],
                "python -m ops.scripts.mechanism.auto_improve_runtime",
            )
            self.assertIn("source_paths", embedded_envelope["input_fingerprints"])
            source_paths = build_envelope.call_args.kwargs["source_paths"]
            self.assertIn("ops/scripts/mechanism/auto_improve_runtime.py", source_paths)
            self.assertIn(
                "ops/scripts/mechanism/auto_improve_learning_preflight_runtime.py",
                source_paths,
            )
            self.assertIn(
                "ops/scripts/mechanism/auto_improve_maintenance_decision_runtime.py",
                source_paths,
            )
            self.assertIn(
                "ops/scripts/mechanism/auto_improve_promotion_stop_runtime.py",
                source_paths,
            )
            self.assertIn(
                "ops/scripts/mechanism/auto_improve_session_report_runtime.py",
                source_paths,
            )
            self.assertIn(
                "ops/scripts/mechanism/auto_improve_session_start_runtime.py",
                source_paths,
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
