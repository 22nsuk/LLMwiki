from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from ops.scripts.artifact_io_runtime import write_json_object
from ops.scripts.learning_readiness_signoff import (
    LearningReadinessSignoffRequest,
    build_signoff_report,
)
from ops.scripts.learning_readiness_signoff_revalidation import (
    AUTO_IMPROVE_READINESS_PATH,
    DEFAULT_OUT,
    RELEASE_CLOSEOUT_PATH,
    SUPPORTED_BLOCKER_ID,
    build_revalidation_report,
    write_revalidation_report,
)
from ops.scripts.learning_readiness_vocabulary import (
    LEARNING_EXECUTION_NOT_RUNNABLE_BLOCKER_ID,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import (
    LEARNING_READINESS_SIGNOFF_REVALIDATION_SCHEMA_PATH,
)
from ops.scripts.schema_runtime import (
    load_schema_with_vault_override,
    validate_with_schema,
)

from tests.minimal_vault_runtime import seed_minimal_vault


def fixed_context(timestamp: dt.datetime | None = None) -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: timestamp or dt.datetime(2026, 4, 30, 12, 0, tzinfo=dt.UTC),
    )


def envelope(
    *,
    schema_path: str,
    artifact_kind: str,
    generated_at: str = "2026-04-30T11:00:00Z",
    producer: str = "test",
) -> dict[str, Any]:
    return {
        "$schema": schema_path,
        "artifact_kind": artifact_kind,
        "generated_at": generated_at,
        "producer": producer,
        "source_command": "test",
        "source_revision": "test",
        "source_tree_fingerprint": "source-tree",
        "input_fingerprints": {"test": "fingerprint"},
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "canonical_report",
        "encoding": "utf-8",
        "currentness": {"status": "current", "checked_at": generated_at},
    }


class LearningReadinessSignoffRevalidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_signoff(self, *, expires_at: str = "2026-05-07T06:02:10Z") -> None:
        report = build_signoff_report(
            self.vault,
            LearningReadinessSignoffRequest(
                accepted_by="operator@example.test",
                accepted_at="2026-04-30T06:02:10Z",
                expires_at=expires_at,
                risk_owner="runtime-maintainer",
                revalidation_condition="rerun release evidence closeout before expiry",
                rollback_trigger="learning telemetry regresses or signoff expires",
            ),
            context=fixed_context(),
        )
        write_json_object(self.vault / "ops" / "reports" / "learning-readiness-signoff.json", report)

    def write_closeout(self, *, accepted_learning_risk: bool = True, active_blocker: bool = False) -> None:
        accepted_risks = []
        blockers = []
        if accepted_learning_risk:
            accepted_risks.append({"code": SUPPORTED_BLOCKER_ID})
        if active_blocker:
            blockers.append({"code": SUPPORTED_BLOCKER_ID})
        checked_in_release_ready = not active_blocker
        release_readiness_state = (
            "blocked"
            if active_blocker
            else ("conditional_pass" if accepted_learning_risk else "clean_pass")
        )
        report = {
            **envelope(
                schema_path="ops/schemas/release-closeout-summary.schema.json",
                artifact_kind="release_closeout_summary",
                producer="ops.scripts.release_closeout_summary",
            ),
            "checked_in_release_ready": checked_in_release_ready,
            "live_rerun_release_ready": not active_blocker and not accepted_learning_risk,
            "conditional_release_ready": checked_in_release_ready and accepted_learning_risk,
            "clean_release_ready": checked_in_release_ready and not accepted_learning_risk,
            "release_readiness_state": release_readiness_state,
            "machine_release_allowed": checked_in_release_ready and not accepted_learning_risk,
            "operator_release_allowed": checked_in_release_ready,
            "requires_accepted_risk_review": checked_in_release_ready and accepted_learning_risk,
            "status": "pass" if not active_blocker else "fail",
            "blockers": blockers,
            "accepted_risks": accepted_risks,
        }
        write_json_object(self.vault / RELEASE_CLOSEOUT_PATH, report)

    def write_readiness(
        self,
        *,
        likely_to_learn: bool = False,
        blocker_present: bool = True,
        blocker_id: str = SUPPORTED_BLOCKER_ID,
        status: str | None = None,
    ) -> None:
        learning_claim_blockers = []
        if blocker_present:
            learning_claim_blockers.append(
                {
                    "id": blocker_id,
                    "status": "open",
                }
            )
        learning_status = status or ("learning_likely" if likely_to_learn else "learning_uncertain")
        report = {
            **envelope(
                schema_path="ops/schemas/auto-improve-readiness-report.schema.json",
                artifact_kind="auto_improve_readiness_report",
                producer="ops.scripts.auto_improve_readiness",
            ),
            "learning_readiness": {
                "status": learning_status,
                "likely_to_learn": likely_to_learn,
                "metrics": {"attempts_considered": 10},
                "signals": [],
            },
            "learning_claim_blockers": learning_claim_blockers,
        }
        write_json_object(self.vault / AUTO_IMPROVE_READINESS_PATH, report)

    def test_active_signoff_due_with_open_learning_blocker_requires_clean_closeout(self) -> None:
        self.write_signoff()
        self.write_closeout()
        self.write_readiness(likely_to_learn=False, blocker_present=True)

        report = build_revalidation_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["revalidation"]["status"], "due")
        self.assertFalse(report["revalidation"]["clean_closeout_required"])
        self.assertIn("release_authority_status=conditional_pass", report["revalidation"]["status_reason"])
        self.assertIn("release_readiness_state=conditional_pass", report["revalidation"]["status_reason"])
        self.assertIn("machine_release_allowed=False", report["revalidation"]["status_reason"])
        self.assertIn("operator_release_allowed=True", report["revalidation"]["status_reason"])
        self.assertIn("requires_accepted_risk_review=True", report["revalidation"]["status_reason"])
        self.assertEqual(report["release_effect"]["clean_release_effect"], "conditional_operator_accepted")
        self.assertEqual(report["release_effect"]["release_authority_status"], "conditional_pass")
        self.assertFalse(report["release_effect"]["machine_release_allowed"])
        self.assertTrue(report["release_effect"]["operator_release_allowed"])
        self.assertIn("learning revalidation=due", report["release_effect"]["operator_summary"])
        self.assertEqual(report["signoff"]["signoff_status"], "active")
        self.assertEqual(report["required_actions"][0]["id"], "decide_learning_signoff_renewal")
        self.assertIn("make learning-readiness-signoff", report["required_actions"][0]["command"])

        schema = load_schema_with_vault_override(self.vault, LEARNING_READINESS_SIGNOFF_REVALIDATION_SCHEMA_PATH)
        self.assertEqual(validate_with_schema(report, schema), [])

    def test_closeout_status_v2_overrides_legacy_release_booleans(self) -> None:
        self.write_signoff()
        self.write_closeout(accepted_learning_risk=False)
        closeout_path = self.vault / RELEASE_CLOSEOUT_PATH
        closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
        closeout.update(
            {
                "release_readiness_state": "clean_pass",
                "machine_release_allowed": True,
                "operator_release_allowed": False,
                "requires_accepted_risk_review": False,
                "status_v2": {
                    "schema_version": 2,
                    "compatibility_status_value": "pass",
                    "status_axes": {
                        "release_authority_status": "conditional_pass",
                        "semantic_release_status": "conditional_pass",
                        "sealed_release_status": "sealed_conditional_pass",
                    },
                    "blocker_reason_ids": [
                        "release_authority_not_clean_pass",
                        "machine_release_not_allowed",
                    ],
                },
            }
        )
        write_json_object(closeout_path, closeout)
        self.write_readiness(likely_to_learn=False, blocker_present=True)

        report = build_revalidation_report(self.vault, context=fixed_context())

        self.assertEqual(report["closeout"]["release_readiness_state"], "conditional_pass")
        self.assertEqual(report["closeout"]["release_authority_status"], "conditional_pass")
        self.assertEqual(report["closeout"]["semantic_release_status"], "conditional_pass")
        self.assertEqual(report["closeout"]["sealed_release_status"], "sealed_conditional_pass")
        self.assertEqual(
            report["closeout"]["status_v2_blocker_reason_ids"],
            ["release_authority_not_clean_pass", "machine_release_not_allowed"],
        )
        self.assertEqual(report["closeout"]["status_v2_used_legacy_fallback_fields"], [])
        self.assertFalse(report["closeout"]["machine_release_allowed"])
        self.assertTrue(report["closeout"]["operator_release_allowed"])
        self.assertTrue(report["closeout"]["requires_accepted_risk_review"])
        self.assertEqual(report["release_effect"]["clean_release_effect"], "conditional_operator_accepted")
        self.assertEqual(report["release_effect"]["release_authority_status"], "conditional_pass")
        self.assertIn("release_authority_status=conditional_pass", report["revalidation"]["status_reason"])
        self.assertIn("release_authority_status=conditional_pass", report["release_effect"]["operator_summary"])

        schema = load_schema_with_vault_override(self.vault, LEARNING_READINESS_SIGNOFF_REVALIDATION_SCHEMA_PATH)
        self.assertEqual(validate_with_schema(report, schema), [])

    def test_metric_improvement_becomes_close_candidate_without_renewing_signoff(self) -> None:
        self.write_signoff()
        self.write_closeout(accepted_learning_risk=False)
        self.write_readiness(likely_to_learn=True, blocker_present=False)

        report = build_revalidation_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["revalidation"]["status"], "metrics_close_candidate")
        self.assertEqual(report["release_effect"]["clean_release_effect"], "clean_allowed")
        self.assertFalse(report["revalidation"]["clean_closeout_required"])
        close_option = report["decision_options"][0]
        self.assertEqual(close_option["id"], "close_blocker_with_metric_improvement")
        self.assertTrue(close_option["available"])

    def test_not_runnable_learning_blocker_requires_clean_closeout_not_signoff_renewal(self) -> None:
        self.write_signoff()
        self.write_closeout()
        self.write_readiness(
            likely_to_learn=False,
            blocker_present=True,
            blocker_id=LEARNING_EXECUTION_NOT_RUNNABLE_BLOCKER_ID,
            status="not_runnable",
        )

        report = build_revalidation_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["revalidation"]["status"], "missing_signoff")
        self.assertTrue(report["revalidation"]["clean_closeout_required"])
        self.assertEqual(report["learning_readiness"]["blocker_ids"], [LEARNING_EXECUTION_NOT_RUNNABLE_BLOCKER_ID])
        self.assertEqual(
            report["learning_readiness"]["signoff_unsupported_blocker_ids"],
            [LEARNING_EXECUTION_NOT_RUNNABLE_BLOCKER_ID],
        )
        self.assertIn(LEARNING_EXECUTION_NOT_RUNNABLE_BLOCKER_ID, report["revalidation"]["status_reason"])
        self.assertEqual(report["required_actions"][0]["id"], "rerun_clean_release_evidence_converge")
        decision_options = {item["id"]: item for item in report["decision_options"]}
        self.assertFalse(decision_options["renew_signoff_after_clean_closeout"]["available"])
        self.assertTrue(decision_options["restore_runnable_proposal_queue"]["available"])
        self.assertFalse(decision_options["let_signoff_expire_and_block_release"]["available"])
        self.assertIn(
            "signoff cannot accept this blocker",
            decision_options["restore_runnable_proposal_queue"]["reason"],
        )

    def test_expired_signoff_is_overdue_and_failing(self) -> None:
        self.write_signoff(expires_at="2026-04-30T11:59:59Z")
        self.write_closeout(active_blocker=True, accepted_learning_risk=False)
        self.write_readiness(likely_to_learn=False, blocker_present=True)

        report = build_revalidation_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["revalidation"]["status"], "overdue")
        self.assertTrue(report["revalidation"]["clean_closeout_required"])

    def test_writes_default_schema_valid_report(self) -> None:
        self.write_signoff()
        self.write_closeout()
        self.write_readiness(likely_to_learn=False, blocker_present=True)
        report = build_revalidation_report(self.vault, context=fixed_context())

        destination = write_revalidation_report(self.vault, report)

        self.assertEqual(destination.resolve(), (self.vault / DEFAULT_OUT).resolve())
        persisted = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(persisted["artifact_kind"], "learning_readiness_signoff_revalidation")


if __name__ == "__main__":
    unittest.main()
