from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from ops.scripts.learning_claim_activation_report import build_report, write_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "learning-claim-activation-report.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 15, 9, 0, tzinfo=dt.timezone.utc),
    )


def write_json(vault: Path, rel_path: str, payload: dict[str, Any]) -> None:
    path = vault / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def seed_activation_inputs(vault: Path) -> None:
    write_json(
        vault,
        "ops/reports/auto-improve-readiness.json",
        {
            "can_execute_trial": True,
            "can_promote_result": False,
            "learning_readiness": {
                "likely_to_learn": True,
                "metrics": {
                    "same_eval_run_count": 2,
                    "same_eval_reason_code_coverage_ratio": 1.0,
                    "strict_secondary_improvement_coverage_ratio": 1.0,
                    "behavior_delta_digest_coverage_ratio": 1.0,
                },
                "signals": [],
            },
            "queue": {
                "ready": True,
                "runnable_proposal_count": 1,
                "blocked_reason_counts": [{"reason": "recent_log_overlap", "count": 1}],
            },
            "release_blockers": [],
        },
    )
    write_json(
        vault,
        "ops/reports/learning-delta-scoreboard.json",
        {
            "status": "pass",
            "summary": {
                "claims_learning_improved": False,
                "learning_claim_allowed": False,
                "learning_likely": False,
                "bounded_learning_claim_allowed": False,
                "confirmed_learning_improvement_allowed": False,
                "claim_wording_allowed": False,
                "claim_wording_policy_status": "blocked",
                "claim_level": "none",
                "learning_claim_evidence_complete": True,
                "telemetry_coverage_status": "full",
                "same_eval_reason_coverage_status": "full",
                "strict_secondary_improvement_coverage_status": "full",
                "behavior_delta_digest_coverage_status": "full",
                "confirmed_evidence_summary": {
                    "rejected_run_diagnostics": [
                        {
                            "run_id": "run-discard",
                            "decision": "DISCARD",
                            "reasons": ["decision=DISCARD"],
                        },
                        {
                            "run_id": "run-diagnostic-only",
                            "decision": "DISCARD",
                            "reasons": [
                                "decision=DISCARD",
                                "behavior delta before/after evidence missing",
                            ],
                        }
                    ]
                },
            },
            "learning_claim_unlock_review": {
                "status": "required",
                "approved": False,
                "reason": "typed same-eval coverage is complete but unlock review is required",
            },
            "anti_slop_score": {"status": "clean", "score": 100},
        },
    )
    write_json(
        vault,
        "ops/reports/learning-claim-unlock-review.json",
        {
            "review_status": "required",
            "approved": False,
            "machine_policy_decision": {
                "decision": "requires_human",
                "claim_level": "none",
                "predicate_results": [
                    {
                        "id": "auto_improve_can_promote_result",
                        "status": "fail",
                        "source_path": "ops/reports/auto-improve-readiness.json",
                        "required_condition": "auto_improve_readiness.can_promote_result == true",
                        "observed_value": "can_promote_result=False",
                        "summary": "Auto-improve result promotion gate is clean.",
                    }
                ],
                "confirmed_predicate_results": [
                    {
                        "id": "learning_claim_blocker_absence",
                        "status": "fail",
                        "source_path": "ops/reports/release-clean-blocker-ledger.json",
                        "required_condition": "release_clean_blocker_ledger.learning_claim_blockers == []",
                        "observed_value": "learning_claim_blocker_count=2",
                        "summary": "No accepted learning risk or learning-claim blocker may remain.",
                    }
                ],
            },
        },
    )
    write_json(
        vault,
        "ops/reports/learning-claim-evidence-bundle.json",
        {
            "status": "pass",
            "summary": {
                "bundle_sha256": "a" * 64,
                "revocation_status": "active",
            },
        },
    )
    write_json(
        vault,
        "ops/reports/release-clean-blocker-ledger.json",
        {
            "status": "attention",
            "learning_claim_blockers": [{"id": "accepted_learning_risk"}],
        },
    )
    write_json(
        vault,
        "ops/reports/source-package-clean-extract.json",
        {"status": "pass"},
    )
    write_json(
        vault,
        "runs/run-hold/run-telemetry.json",
        {
            "run_id": "run-hold",
            "decision": "HOLD",
            "same_eval_reason_code": "same_eval_no_secondary_improvement",
        },
    )
    write_json(
        vault,
        "runs/run-discard/run-telemetry.json",
        {
            "run_id": "run-discard",
            "decision": "DISCARD",
            "same_eval_reason_code": "unknown",
        },
    )


class LearningClaimActivationReportTests(unittest.TestCase):
    def test_report_keeps_claim_closed_and_explains_blocked_predicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_activation_inputs(vault)

            report = build_report(vault, context=fixed_context())
            destination = write_report(vault, report)
            blocked_ids = {item["id"] for item in report["blocked_predicates"]}

            self.assertTrue(destination.exists())
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["activation_status"], "blocked")
            self.assertEqual(report["claim_candidate"]["current"]["claim_level"], "none")
            self.assertFalse(report["claim_candidate"]["current"]["claim_wording_allowed"])
            self.assertIn("auto_improve_can_promote_result", blocked_ids)
            self.assertIn("learning_claim_blocker_absence", blocked_ids)
            self.assertIn("learning_claim_unlock_review_not_approved", blocked_ids)
            self.assertIn("post_seal_learning_claim_linkage", blocked_ids)
            self.assertTrue(
                all(item["repair_target"] for item in report["blocked_predicates"])
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_report_exposes_anti_slop_axes_and_negative_learning_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_activation_inputs(vault)

            report = build_report(vault, context=fixed_context())
            axes = [item["axis"] for item in report["anti_slop_preview_ledger"]["axes"]]
            patterns = {
                item["pattern_id"]: item
                for item in report["negative_learning_ledger"]["patterns"]
            }

            self.assertEqual(
                axes,
                [
                    "claim_hygiene",
                    "evidence_density",
                    "reproducibility",
                    "scope_discipline",
                    "context_efficiency",
                    "operator_override_pressure",
                ],
            )
            self.assertEqual(report["anti_slop_preview_ledger"]["gate_effect"], "none")
            self.assertEqual(report["negative_learning_ledger"]["gate_effect"], "none")
            self.assertIn("hold_same_eval_no_secondary_improvement", patterns)
            self.assertIn("discard_unknown", patterns)
            self.assertIn("discard_behavior_delta_before_after_evidence_missing", patterns)
            self.assertNotIn("discard_decision_discard", patterns)
            self.assertIn("blocked_queue_recent_log_overlap", patterns)
            self.assertIn("BLOCKED", patterns["blocked_queue_recent_log_overlap"]["decisions"])


if __name__ == "__main__":
    unittest.main()
