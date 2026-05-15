from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from ops.scripts.learning_claim_evidence_bundle import (
    build_report,
    validate_learning_claim_evidence_bundle,
    write_report,
)
from ops.scripts.learning_confirmed_legacy_reconstruction import build_report as build_legacy_reconstruction
from ops.scripts.learning_confirmed_legacy_reconstruction import write_report as write_legacy_reconstruction
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "learning-claim-evidence-bundle.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 8, 9, 0, tzinfo=dt.timezone.utc),
    )


def seed_bundle_inputs(vault: Path, *, digest: str = "a") -> None:
    (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
    (vault / "external-reports").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
        json.dumps({"learning_readiness": {"status": "learning_likely"}}),
        encoding="utf-8",
    )
    (vault / "ops" / "reports" / "outcome-metrics.json").write_text("{}", encoding="utf-8")
    (vault / "ops" / "reports" / "public-check-summary.json").write_text(
        json.dumps({"status": "pass"}),
        encoding="utf-8",
    )
    (vault / "ops" / "reports" / "mutation-proposals.json").write_text(
        json.dumps(
            {
                "proposals": [
                    {
                        "family": "contract_regression_signals",
                        "failure_mode": "repeated_same_eval_or_discard",
                        "primary_targets": ["ops/scripts/example.py"],
                        "supporting_targets": [],
                        "run_ids": ["run-a"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (vault / "ops" / "reports" / "mechanism-review-candidates.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "family": "contract_regression_signals",
                        "primary_targets": ["ops/scripts/example.py"],
                        "supporting_targets": [],
                        "run_ids": ["run-a"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (vault / "external-reports" / "report-reference-manifest.json").write_text(
        json.dumps({"status": "pass"}),
        encoding="utf-8",
    )
    (vault / "runs" / "run-a").mkdir(parents=True, exist_ok=True)
    (vault / "runs" / "run-a" / "baseline-mechanism-assessment.json").write_text(
        json.dumps({"artifact_kind": "baseline_mechanism_assessment", "run_id": "run-a"}),
        encoding="utf-8",
    )
    (vault / "runs" / "run-a" / "candidate-mechanism-assessment.json").write_text(
        json.dumps({"artifact_kind": "candidate_mechanism_assessment", "run_id": "run-a"}),
        encoding="utf-8",
    )
    (vault / "runs" / "run-a" / "promotion-report.json").write_text(
        json.dumps({"decision": "PROMOTE", "run_id": "run-a"}),
        encoding="utf-8",
    )
    (vault / "runs" / "run-a" / "run-telemetry.json").write_text(
        json.dumps(
            {
                "decision": "PROMOTE",
                "same_eval_reason_code": "telemetry_discoverability_improved",
                "strict_secondary_improvement_present": True,
                "secondary_improvement_axes": ["complexity"],
                "behavior_delta_digest": digest * 64,
            }
        ),
        encoding="utf-8",
    )
    write_legacy_reconstruction(vault, build_legacy_reconstruction(vault, context=fixed_context()))


class LearningClaimEvidenceBundleTests(unittest.TestCase):
    def test_bundle_happy_path_validates_and_readback_is_active(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_bundle_inputs(vault)

            report = build_report(vault, context=fixed_context())
            destination = write_report(vault, report)
            validation = validate_learning_claim_evidence_bundle(vault, context=fixed_context())

            self.assertTrue(destination.exists())
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["revocation_status"], "active")
            self.assertEqual(report["behavior_delta_digest_readback"]["status"], "pass")
            self.assertEqual(report["behavior_delta_artifact_readback"]["status"], "not_available")
            self.assertEqual(report["summary"]["confirmed_run_artifact_missing_count"], 0)
            self.assertEqual(report["confirmed_run_artifacts"][0]["status"], "pass")
            self.assertRegex(report["bundle_identity"]["evidence_bundle_digest"], r"^[a-f0-9]{64}$")
            self.assertEqual(validation["revocation_status"], "active")
            self.assertEqual(validation["bundle_fingerprint_match_status"], "match")
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_bundle_validation_stales_when_bound_evidence_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_bundle_inputs(vault)
            write_report(vault, build_report(vault, context=fixed_context()))

            readiness_path = vault / "ops" / "reports" / "auto-improve-readiness.json"
            payload: dict[str, Any] = json.loads(readiness_path.read_text(encoding="utf-8"))
            payload["queue"] = {"runnable_proposal_count": 2}
            readiness_path.write_text(json.dumps(payload), encoding="utf-8")

            validation = validate_learning_claim_evidence_bundle(vault, context=fixed_context())

            self.assertEqual(validation["revocation_status"], "stale")
            self.assertEqual(validation["bundle_fingerprint_match_status"], "mismatch")

    def test_bundle_validation_stales_when_confirmed_promotion_report_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_bundle_inputs(vault)
            write_report(vault, build_report(vault, context=fixed_context()))

            promotion_path = vault / "runs" / "run-a" / "promotion-report.json"
            promotion_path.write_text(
                json.dumps({"decision": "PROMOTE", "run_id": "run-a", "later": True}),
                encoding="utf-8",
            )

            validation = validate_learning_claim_evidence_bundle(vault, context=fixed_context())

            self.assertEqual(validation["revocation_status"], "stale")
            self.assertEqual(validation["bundle_fingerprint_match_status"], "mismatch")

    def test_bundle_validation_revokes_when_behavior_delta_digest_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_bundle_inputs(vault)
            write_report(vault, build_report(vault, context=fixed_context()))

            telemetry_path = vault / "runs" / "run-a" / "run-telemetry.json"
            telemetry = json.loads(telemetry_path.read_text(encoding="utf-8"))
            telemetry.pop("behavior_delta_digest")
            telemetry_path.write_text(json.dumps(telemetry), encoding="utf-8")

            validation = validate_learning_claim_evidence_bundle(vault, context=fixed_context())

            self.assertEqual(validation["revocation_status"], "revoked")
            self.assertIn("behavior_delta_digest missing", "; ".join(validation["reasons"]))

    def test_confirmed_legacy_digest_fallback_uses_reconstruction_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_bundle_inputs(vault)
            (vault / "ops" / "reports" / "mutation-proposals.json").write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "family": "contract_regression_signals",
                                "failure_mode": "repeated_same_eval_or_discard",
                                "primary_targets": ["ops/scripts/example.py"],
                                "supporting_targets": [],
                                "run_ids": ["discard-a"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (vault / "runs" / "discard-a").mkdir(parents=True, exist_ok=True)
            (vault / "runs" / "discard-a" / "run-telemetry.json").write_text(
                json.dumps(
                    {
                        "decision": "DISCARD",
                        "same_eval_reason_code": "telemetry_discoverability_improved",
                        "strict_secondary_improvement_present": True,
                        "secondary_improvement_axes": ["complexity"],
                        "behavior_delta_digest": "b" * 64,
                    }
                ),
                encoding="utf-8",
            )
            behavior_delta_path = vault / "runs" / "run-a" / "behavior-delta.json"
            behavior_delta = {"artifact_kind": "behavior_delta", "run_id": "run-a", "summary": {"delta_count": 1}}
            behavior_delta_text = json.dumps(behavior_delta, sort_keys=True)
            behavior_delta_path.write_text(behavior_delta_text, encoding="utf-8")
            telemetry_path = vault / "runs" / "run-a" / "run-telemetry.json"
            telemetry = json.loads(telemetry_path.read_text(encoding="utf-8"))
            telemetry["behavior_delta"] = "runs/run-a/behavior-delta.json"
            telemetry.pop("behavior_delta_digest")
            telemetry.pop("strict_secondary_improvement_present")
            telemetry.pop("secondary_improvement_axes")
            telemetry_path.write_text(json.dumps(telemetry), encoding="utf-8")
            promotion_path = vault / "runs" / "run-a" / "promotion-report.json"
            promotion_path.write_text(
                json.dumps(
                    {
                        "decision": "PROMOTE",
                        "run_id": "run-a",
                        "inputs": {"behavior_delta": "runs/run-a/behavior-delta.json"},
                        "checks": [
                            {
                                "id": "equal_score_secondary_eligibility",
                                "status": "PASS",
                                "detail": (
                                    "allowed=true, score_equal=true, selected_axes=['complexity'], "
                                    "selected_non_regression=true, selected_any_improvement=true"
                                ),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            write_legacy_reconstruction(vault, build_legacy_reconstruction(vault, context=fixed_context()))

            report = build_report(vault, context=fixed_context())
            confirmed = report["confirmed_telemetry_evidence"][0]

            self.assertEqual(report["summary"]["revocation_status"], "active")
            self.assertEqual(confirmed["behavior_delta_digest_source"], "legacy_reconstruction_artifact")
            self.assertEqual(confirmed["legacy_reconstruction_status"], "reconstructed")
            self.assertEqual(confirmed["secondary_improvement_axes"], ["complexity"])

    def test_bundle_validation_stales_when_public_check_summary_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_bundle_inputs(vault)
            write_report(vault, build_report(vault, context=fixed_context()))

            public_check_path = vault / "ops" / "reports" / "public-check-summary.json"
            public_check_path.write_text(json.dumps({"status": "pass", "run_id": "later"}), encoding="utf-8")

            validation = validate_learning_claim_evidence_bundle(vault, context=fixed_context())

            self.assertEqual(validation["revocation_status"], "stale")
            self.assertEqual(validation["bundle_fingerprint_match_status"], "mismatch")

    def test_bundle_validation_stales_when_public_check_summary_status_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_bundle_inputs(vault)
            write_report(vault, build_report(vault, context=fixed_context()))

            public_check_path = vault / "ops" / "reports" / "public-check-summary.json"
            public_check_path.write_text(
                json.dumps({"status": "fail", "failed_gate": "public-check"}),
                encoding="utf-8",
            )

            validation = validate_learning_claim_evidence_bundle(vault, context=fixed_context())

            self.assertEqual(validation["revocation_status"], "stale")
            self.assertEqual(validation["bundle_fingerprint_match_status"], "mismatch")

    def test_bundle_validation_revokes_when_behavior_delta_artifact_digest_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_bundle_inputs(vault)
            behavior_delta_path = vault / "runs" / "run-a" / "behavior-delta.json"
            behavior_delta = {"artifact_kind": "behavior_delta", "run_id": "run-a", "summary": {"delta_count": 1}}
            behavior_delta_text = json.dumps(behavior_delta, sort_keys=True)
            behavior_delta_path.write_text(behavior_delta_text, encoding="utf-8")
            telemetry_path = vault / "runs" / "run-a" / "run-telemetry.json"
            telemetry = json.loads(telemetry_path.read_text(encoding="utf-8"))
            telemetry["behavior_delta"] = "runs/run-a/behavior-delta.json"
            telemetry["behavior_delta_digest"] = hashlib.sha256(
                behavior_delta_text.encode("utf-8")
            ).hexdigest()
            telemetry_path.write_text(json.dumps(telemetry), encoding="utf-8")
            write_report(vault, build_report(vault, context=fixed_context()))

            behavior_delta_path.write_text(
                json.dumps({"artifact_kind": "behavior_delta", "run_id": "run-a", "summary": {"delta_count": 2}}),
                encoding="utf-8",
            )

            validation = validate_learning_claim_evidence_bundle(vault, context=fixed_context())

            self.assertEqual(validation["revocation_status"], "revoked")
            self.assertIn("behavior_delta artifact digest mismatch", "; ".join(validation["reasons"]))

    def test_bundle_validation_stales_when_run_set_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_bundle_inputs(vault)
            write_report(vault, build_report(vault, context=fixed_context()))

            mutation_path = vault / "ops" / "reports" / "mutation-proposals.json"
            mutation_path.write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "failure_mode": "repeated_same_eval_or_discard",
                                "run_ids": ["run-a", "run-b"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (vault / "runs" / "run-b").mkdir(parents=True)
            (vault / "runs" / "run-b" / "run-telemetry.json").write_text(
                json.dumps(
                    {
                        "decision": "PROMOTE",
                        "same_eval_reason_code": "telemetry_discoverability_improved",
                        "strict_secondary_improvement_present": True,
                        "secondary_improvement_axes": ["complexity"],
                        "behavior_delta_digest": "b" * 64,
                    }
                ),
                encoding="utf-8",
            )

            validation = validate_learning_claim_evidence_bundle(vault, context=fixed_context())

            self.assertEqual(validation["revocation_status"], "stale")
            self.assertEqual(validation["bundle_fingerprint_match_status"], "mismatch")


if __name__ == "__main__":
    unittest.main()
