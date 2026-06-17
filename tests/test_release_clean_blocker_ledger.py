from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.release.release_clean_blocker_ledger import (
    build_report,
    main,
    write_report,
)
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-clean-blocker-ledger.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 3, 9, 0, tzinfo=dt.UTC),
    )


class ReleaseCleanBlockerLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_report(self, rel_path: str, payload: dict[str, Any]) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_inputs(
        self,
        *,
        accepted_risks: list[dict[str, Any]] | None = None,
        clean_lane_blocking_family_count: int | None = None,
    ) -> None:
        risks = accepted_risks or []
        blocking_count = len(risks) if clean_lane_blocking_family_count is None else clean_lane_blocking_family_count
        self._write_report(
            "ops/reports/release-closeout-summary.json",
            {
                "release_readiness_state": "conditional_pass" if blocking_count else "clean_pass",
                "accepted_risks": risks,
            },
        )
        self._write_report(
            "ops/reports/release-evidence-cohort.json",
            {
                "clean_lane_contract": {
                    "status": "fail" if blocking_count else "pass",
                    "failed_conditions": ["zero_accepted_risk_family"] if blocking_count else [],
                }
            },
        )
        self._write_report(
            "ops/reports/release-lane-summary.json",
            {
                "lane_summary": {
                    "clean_lane_status": "fail" if blocking_count else "pass",
                    "conditional_lane_status": "pass",
                    "auto_improve_lane_status": "pass",
                    "machine_release_status": "blocked" if blocking_count else "allowed",
                    "operator_release_status": "allowed",
                    "accepted_risk_family_count": len(risks),
                    "accepted_risk_instance_count": len(risks),
                    "clean_lane_blocking_family_count": blocking_count,
                }
            },
        )
        self._write_report(
            "ops/reports/learning-delta-scoreboard.json",
            {
                "status": "pass",
                "summary": {
                    "claims_learning_improved": False,
                    "learning_claim_allowed": False,
                    "telemetry_coverage_ratio": 0.75,
                    "same_eval_run_count": 4,
                    "same_eval_reason_coverage_ratio": 0.0,
                    "strict_secondary_improvement_coverage_ratio": 0.0,
                    "behavior_delta_digest_coverage_ratio": 0.0,
                    "placeholder_count": 0,
                    "evidence_scope_count": 6,
                },
                "learning_claim_guard": {
                    "status": "pass",
                    "reason": "learning claims are not being made in this release snapshot",
                    "required_conditions": [],
                },
                "external_report_placeholder_audit": {
                    "status": "pass",
                    "placeholder_count": 0,
                    "placeholders": [],
                },
            },
        )

    def test_ledger_lists_accepted_risks_as_clean_lane_blockers(self) -> None:
        self._write_inputs(
            accepted_risks=[
                {
                    "source": "artifact_freshness",
                    "source_path": "ops/reports/artifact-freshness-report.json",
                    "code": "artifact_freshness_attention",
                    "severity": "warn",
                    "gate_effect": "advisory",
                    "message": "artifact freshness has attention-level debt",
                    "required_evidence": ["rerun artifact-freshness"],
                    "risk_acceptance": {
                        "accepted_by": "release_closeout_policy",
                        "accepted_at": "2026-05-03T09:00:00Z",
                        "risk_owner": "runtime-maintainer",
                        "expires_at": "2026-05-10T00:00:00Z",
                        "acceptance_source": "ops/scripts/release_closeout_summary.py",
                        "revalidation_condition": "rerun artifact-freshness",
                        "rollback_trigger": "treat as blocker if expired",
                    },
                }
            ]
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["summary"]["blocker_count"], 1)
        self.assertEqual(report["summary"]["source_clean_blocker_count"], 1)
        self.assertEqual(report["summary"]["auto_improve_blocker_count"], 0)
        self.assertEqual(report["summary"]["learning_claim_guard_status"], "pass")
        self.assertEqual(report["summary"]["advisory_backlog_status"], "clear")
        self.assertEqual(report["blockers"][0]["clean_lane_effect"], "blocks_clean_lane")
        self.assertEqual(report["blockers"][0]["lifecycle_status"], "not_applicable")
        self.assertEqual(report["blockers"][0]["conditional_lane_effect"], "operator_review_required")
        self.assertEqual(report["blockers"][0]["learning_lane_effect"], "not_applicable")
        self.assertEqual(report["advisory_backlog"], [])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_ledger_lists_archive_advisory_as_backlog_not_clean_blocker(self) -> None:
        self._write_inputs(
            accepted_risks=[
                {
                    "source": "generated_index",
                    "source_path": "ops/reports/generated-artifact-index.json",
                    "code": "generated_index_archive_advisory",
                    "severity": "warn",
                    "gate_effect": "advisory",
                    "message": "generated artifact index reports archive candidates as advisory release risk",
                    "required_evidence": ["rerun generated-artifact-index"],
                    "risk_acceptance": {
                        "accepted_by": "release_closeout_policy",
                        "accepted_at": "2026-05-03T09:00:00Z",
                        "risk_owner": "runtime-maintainer",
                        "expires_at": "2026-05-10T00:00:00Z",
                        "acceptance_source": "ops/scripts/release_closeout_summary.py",
                        "revalidation_condition": "archive or defer generated index candidates",
                        "rollback_trigger": "treat as blocker if current artifacts go missing",
                    },
                }
            ],
            clean_lane_blocking_family_count=0,
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["blocker_count"], 0)
        self.assertEqual(report["summary"]["advisory_lifecycle_family_count"], 1)
        self.assertEqual(report["summary"]["advisory_backlog_status"], "active")
        self.assertEqual(report["summary"]["advisory_backlog_active_count"], 1)
        self.assertEqual(report["summary"]["advisory_backlog_expired_count"], 0)
        self.assertEqual(report["summary"]["advisory_backlog_missing_lifecycle_count"], 0)
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["source_clean_blockers"], [])
        self.assertEqual(report["auto_improve_blockers"], [])
        self.assertEqual(report["advisory_backlog"][0]["code"], "generated_index_archive_advisory")
        self.assertEqual(report["advisory_backlog"][0]["clean_lane_effect"], "does_not_block_clean_lane")
        self.assertEqual(report["advisory_backlog"][0]["advisory_lifecycle_effect"], "review_backlog")
        self.assertEqual(report["advisory_backlog"][0]["lifecycle_status"], "active")
        self.assertEqual(report["advisory_backlog"][0]["lifecycle_issues"], [])
        self.assertGreater(report["advisory_backlog"][0]["seconds_until_expiry"], 0)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_ledger_marks_expired_advisory_backlog_for_operator_attention(self) -> None:
        self._write_inputs(
            accepted_risks=[
                {
                    "source": "generated_index",
                    "source_path": "ops/reports/generated-artifact-index.json",
                    "code": "generated_index_archive_advisory",
                    "severity": "warn",
                    "gate_effect": "advisory",
                    "message": "generated artifact index reports archive candidates as advisory release risk",
                    "required_evidence": ["rerun generated-artifact-index"],
                    "risk_acceptance": {
                        "accepted_by": "release_closeout_policy",
                        "accepted_at": "2026-05-01T09:00:00Z",
                        "risk_owner": "runtime-maintainer",
                        "expires_at": "2026-05-02T00:00:00Z",
                        "acceptance_source": "ops/scripts/release_closeout_summary.py",
                        "revalidation_condition": "archive or defer generated index candidates",
                        "rollback_trigger": "treat as blocker if current artifacts go missing",
                    },
                }
            ],
            clean_lane_blocking_family_count=0,
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["summary"]["blocker_count"], 0)
        self.assertEqual(report["summary"]["advisory_backlog_status"], "expired")
        self.assertEqual(report["summary"]["advisory_backlog_expired_count"], 1)
        self.assertEqual(report["advisory_backlog"][0]["lifecycle_status"], "expired")
        self.assertLessEqual(report["advisory_backlog"][0]["seconds_until_expiry"], 0)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_ledger_marks_advisory_backlog_missing_lifecycle_metadata(self) -> None:
        self._write_inputs(
            accepted_risks=[
                {
                    "source": "external_report_reference_manifest",
                    "source_path": "external-reports/report-reference-manifest.json",
                    "code": "external_report_strict_unavailable",
                    "severity": "warn",
                    "gate_effect": "advisory",
                    "message": "strict external report release check is unavailable",
                    "required_evidence": ["run sealed external report release check"],
                    "risk_acceptance": {
                        "accepted_by": "release_closeout_policy",
                        "accepted_at": "2026-05-03T09:00:00Z",
                        "acceptance_source": "ops/scripts/release_closeout_summary.py",
                    },
                }
            ],
            clean_lane_blocking_family_count=0,
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["summary"]["blocker_count"], 0)
        self.assertEqual(report["summary"]["advisory_backlog_status"], "metadata_missing")
        self.assertEqual(report["summary"]["advisory_backlog_missing_lifecycle_count"], 1)
        self.assertEqual(report["advisory_backlog"][0]["lifecycle_status"], "metadata_missing")
        self.assertEqual(
            set(report["advisory_backlog"][0]["lifecycle_issues"]),
            {
                "missing_risk_owner",
                "missing_expires_at",
                "missing_closure_action",
                "missing_rollback_trigger",
            },
        )
        self.assertIsNone(report["advisory_backlog"][0]["seconds_until_expiry"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_ledger_excludes_learning_signoff_risk_from_clean_lane_blockers(self) -> None:
        self._write_inputs(
            accepted_risks=[
                {
                    "source": "auto_improve_readiness",
                    "source_path": "ops/reports/auto-improve-readiness.json",
                    "code": "learning_blocked_by_review_required",
                    "severity": "warn",
                    "gate_effect": "advisory",
                    "message": "learning readiness still needs operator review",
                    "required_evidence": ["signoff"],
                    "risk_acceptance": {
                        "accepted_by": "operator@example.test",
                        "accepted_at": "2026-05-03T08:00:00Z",
                        "risk_owner": "runtime-maintainer",
                        "expires_at": "2026-05-10T00:00:00Z",
                        "acceptance_source": "ops/reports/learning-readiness-signoff.json",
                        "revalidation_condition": "rerun learning readiness",
                        "rollback_trigger": "treat as blocker if expired",
                    },
                }
            ],
            clean_lane_blocking_family_count=0,
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["blocker_count"], 0)
        self.assertEqual(report["summary"]["accepted_risk_family_count"], 1)
        self.assertEqual(report["summary"]["clean_lane_blocking_family_count"], 0)
        self.assertEqual(report["summary"]["learning_claim_blocking_family_count"], 1)
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["source_clean_blockers"], [])
        self.assertEqual(report["advisory_backlog"], [])
        self.assertEqual(report["learning_claim_blockers"][0]["code"], "learning_blocked_by_review_required")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_ledger_separates_auto_improve_and_learning_blockers_from_source_clean_blockers(self) -> None:
        self._write_inputs()
        closeout_path = self.vault / "ops" / "reports" / "release-closeout-summary.json"
        closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
        closeout["blockers"] = [
            {
                "source": "auto_improve_readiness",
                "source_path": "ops/reports/auto-improve-readiness.json",
                "code": "learning_blocked_by_execution_not_runnable",
                "severity": "blocker",
                "gate_effect": "blocks_execution",
                "message": "no runnable proposal is available",
                "required_evidence": ["restore runnable proposal queue"],
                "clean_lane_effect": "does_not_block_clean_lane",
                "conditional_lane_effect": "not_applicable",
                "learning_lane_effect": "blocks_learning_claim",
                "advisory_lifecycle_effect": "not_applicable",
            }
        ]
        closeout_path.write_text(json.dumps(closeout, ensure_ascii=False, indent=2), encoding="utf-8")
        lane_path = self.vault / "ops" / "reports" / "release-lane-summary.json"
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        lane["lane_summary"]["auto_improve_lane_status"] = "blocked"
        lane["lane_summary"]["learning_claim_blocking_family_count"] = 1
        lane_path.write_text(json.dumps(lane, ensure_ascii=False, indent=2), encoding="utf-8")

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["summary"]["blocker_count"], 0)
        self.assertEqual(report["summary"]["source_clean_blocker_count"], 0)
        self.assertEqual(report["summary"]["auto_improve_blocker_count"], 1)
        self.assertEqual(report["summary"]["auto_improve_lane_status"], "blocked")
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["source_clean_blockers"], [])
        self.assertEqual(report["auto_improve_blockers"][0]["code"], "learning_blocked_by_execution_not_runnable")
        self.assertEqual(report["learning_claim_blockers"][0]["learning_lane_effect"], "blocks_learning_claim")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_ledger_passes_when_no_clean_lane_blockers_remain(self) -> None:
        self._write_inputs()

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["blocker_count"], 0)
        self.assertEqual(report["summary"]["source_clean_blocker_count"], 0)
        self.assertEqual(report["summary"]["auto_improve_blocker_count"], 0)
        self.assertEqual(report["summary"]["learning_claim_guard_status"], "pass")
        self.assertEqual(report["summary"]["advisory_backlog_status"], "clear")
        self.assertEqual(report["summary"]["same_eval_reason_coverage_status"], "none")
        self.assertEqual(report["summary"]["strict_secondary_improvement_coverage_status"], "none")
        self.assertEqual(report["learning_claim_guard"]["placeholder_audit_status"], "pass")
        self.assertEqual(report["blockers"], [])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_ledger_attention_when_learning_claim_guard_is_blocked(self) -> None:
        self._write_inputs()
        scoreboard_path = self.vault / "ops" / "reports" / "learning-delta-scoreboard.json"
        scoreboard = json.loads(scoreboard_path.read_text(encoding="utf-8"))
        scoreboard["summary"]["claims_learning_improved"] = True
        scoreboard["learning_claim_guard"]["status"] = "blocked"
        scoreboard["learning_claim_guard"]["reason"] = "same-eval reason and digest coverage are incomplete"
        scoreboard_path.write_text(json.dumps(scoreboard, ensure_ascii=False, indent=2), encoding="utf-8")

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["summary"]["blocker_count"], 0)
        self.assertEqual(report["summary"]["learning_claim_guard_status"], "blocked")
        self.assertEqual(report["learning_claim_guard"]["claims_learning_improved"], True)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_main_writes_schema_valid_report(self) -> None:
        self._write_inputs()

        exit_code = main(["--vault", self.vault.as_posix(), "--out", "ops/reports/test-clean-blocker-ledger.json"])

        self.assertEqual(exit_code, 0)
        destination = self.vault / "ops" / "reports" / "test-clean-blocker-ledger.json"
        self.assertTrue(destination.exists())
        payload = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(validate_with_schema(payload, load_schema(SCHEMA_PATH)), [])

    def test_write_report_validates_schema(self) -> None:
        self._write_inputs()
        report = build_report(self.vault, context=fixed_context())

        destination = write_report(self.vault, report, "ops/reports/test-clean-blocker-ledger.json")

        self.assertTrue(destination.exists())


if __name__ == "__main__":
    unittest.main()
