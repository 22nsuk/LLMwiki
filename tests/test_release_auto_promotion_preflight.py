from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from ops.scripts.release.release_auto_promotion_preflight import (
    build_manifest,
    write_manifest,
)
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public


SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-auto-promotion-preflight.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 23, 12, 0, tzinfo=dt.UTC),
    )


class ReleaseAutoPromotionPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy("ops/schemas/release-auto-promotion-preflight.schema.json")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy(self, rel_path: str) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _write_json(self, rel_path: str, payload: dict) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_common_inputs(self, *, promotion_blockers: list[dict] | None = None) -> None:
        self._write_json(
            "build/release/release-auto-promotion-goal-run-identity.json",
            {
                "artifact_kind": "release_goal_run_identity",
                "producer": "tests.goal_identity",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_revision": "abc123",
                "source_tree_fingerprint": "fp-current",
                "status": "pass",
                "binding_status": "bound",
                "verification_status": "verified",
                "requested_run_id": "auto-improve-trial",
                "effective_run_id": "promote-run",
                "inferred_run_id": "promote-run",
                "selection_mode": "inferred_from_verified_evidence",
                "goal_run_id_origin": "file",
                "observed": {
                    "requested_run_id": "auto-improve-trial",
                    "effective_run_id": "promote-run",
                    "inferred_run_id": "promote-run",
                    "selection_mode": "inferred_from_verified_evidence",
                    "goal_run_status_run_id": "promote-run",
                    "goal_runtime_certificate_run_id": "promote-run",
                },
                "verification_blockers": [],
                "failures": [],
                "verification_failures": [],
            },
        )
        self._write_json(
            "ops/reports/auto-improve-readiness.json",
            {
                "artifact_kind": "auto_improve_readiness_report",
                "producer": "tests.auto_improve",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_revision": "abc123",
                "source_tree_fingerprint": "fp-current",
                "status": "pass",
                "can_execute_trial": True,
                "can_promote_result": not promotion_blockers,
                "learning_claim_blockers": [],
                "promotion_blockers": promotion_blockers or [],
                "clean_release_blockers": [],
            },
        )
        self._write_json(
            "ops/reports/remediation-backlog.json",
            {
                "artifact_kind": "remediation_backlog",
                "producer": "tests.remediation",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_revision": "abc123",
                "source_tree_fingerprint": "fp-current",
                "status": "pass",
                "summary": {
                    "open_total_count": 0,
                    "open_promotion_count": 0,
                    "open_repeat_count": 0,
                },
            },
        )
        self._write_json(
            "ops/reports/learning-readiness-signoff-revalidation.json",
            {
                "artifact_kind": "learning_readiness_signoff_revalidation",
                "producer": "tests.learning",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_revision": "abc123",
                "source_tree_fingerprint": "fp-current",
                "status": "pass",
                "revalidation": {"status": "current", "clean_closeout_required": False},
            },
        )

    def _write_preseal_inputs(self) -> None:
        self._write_json(
            "ops/reports/release-closeout-summary.json",
            {
                "artifact_kind": "release_closeout_summary",
                "producer": "tests.closeout",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_revision": "abc123",
                "source_tree_fingerprint": "fp-current",
                "status": "pass",
                "release_authority_status": "clean_pass",
                "machine_release_allowed": True,
                "clean_release_ready": True,
                "summary": {
                    "accepted_risk_instance_count": 0,
                    "release_blocking_risk_family_count": 0,
                    "gate_attention_count": 0,
                    "source_tree_coherence_status": "pass",
                },
            },
        )
        self._write_json(
            "ops/reports/release-evidence-cohort.json",
            {
                "artifact_kind": "release_evidence_cohort",
                "producer": "tests.cohort",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_revision": "abc123",
                "source_tree_fingerprint": "fp-current",
                "status": "pass",
                "cohort": {
                    "strict_same_fingerprint": True,
                    "component_fingerprint_count": 5,
                },
                "summary": {"clean_lane_contract_status": "pass"},
            },
        )

    def _patch_current_repo(self) -> Any:
        return patch.multiple(
            "ops.scripts.release.release_auto_promotion_preflight",
            release_source_tree_fingerprint=lambda _vault: "fp-current",
            git_commit=lambda _vault: "abc123",
        )

    def test_preflight_passes_with_current_low_cost_inputs(self) -> None:
        self._write_common_inputs()

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, phase="preflight", context=fixed_context())

        self.assertEqual(manifest["status"], "pass")
        self.assertEqual(manifest["phase"], "preflight")
        self.assertEqual(manifest["blockers"], [])
        self.assertEqual(manifest["final_promotion_blockers"], [])
        self.assertTrue(manifest["checks"]["auto_improve_stage3_promotion_blockers_clear"])
        self.assertEqual(manifest["goal_run_identity"]["effective_run_id"], "promote-run")
        self.assertTrue(manifest["checks"]["goal_run_identity_pass"])
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(
            write_manifest(
                self.vault,
                manifest,
                "build/release/release-auto-promotion-preflight.json",
            ).exists()
        )

    def test_preflight_rejects_revision_stale_identity_even_when_fingerprint_matches(
        self,
    ) -> None:
        self._write_common_inputs()
        readiness = json.loads(
            (self.vault / "ops/reports/auto-improve-readiness.json").read_text(
                encoding="utf-8"
            )
        )
        readiness["source_revision"] = "old-revision"
        self._write_json("ops/reports/auto-improve-readiness.json", readiness)

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, phase="preflight", context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertFalse(manifest["checks"]["auto_improve_readiness_current"])
        self.assertIn("auto_improve_readiness_stale", manifest["failures"])
        blocker = next(
            item
            for item in manifest["blockers"]
            if item["id"] == "auto_improve_readiness_stale"
        )
        self.assertIn("source_revision=old-revision", blocker["observed"])
        self.assertIn("source_revision=abc123", blocker["expected"])

    def test_preflight_accepts_metrics_close_candidate_revalidation(self) -> None:
        self._write_common_inputs()
        learning = json.loads(
            (
                self.vault / "ops/reports/learning-readiness-signoff-revalidation.json"
            ).read_text(encoding="utf-8")
        )
        learning["revalidation"]["status"] = "metrics_close_candidate"
        self._write_json("ops/reports/learning-readiness-signoff-revalidation.json", learning)

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, phase="preflight", context=fixed_context())

        self.assertEqual(manifest["status"], "pass")
        self.assertTrue(manifest["checks"]["learning_revalidation_current"])

    def test_preflight_accepts_not_due_signoff_supported_learning_blocker(self) -> None:
        self._write_common_inputs()
        readiness = json.loads(
            (self.vault / "ops/reports/auto-improve-readiness.json").read_text(
                encoding="utf-8"
            )
        )
        readiness["learning_claim_blockers"] = [
            {
                "id": "learning_blocked_by_review_required",
                "scope": "learning_readiness",
                "status": "open",
                "accepted_risk": False,
            }
        ]
        readiness["diagnostics"] = {
            "learning_signoff_summary": {
                "active": True,
                "linked_blocker_id": "learning_blocked_by_review_required",
            }
        }
        self._write_json("ops/reports/auto-improve-readiness.json", readiness)
        learning = json.loads(
            (
                self.vault / "ops/reports/learning-readiness-signoff-revalidation.json"
            ).read_text(encoding="utf-8")
        )
        learning["revalidation"]["status"] = "not_due"
        self._write_json("ops/reports/learning-readiness-signoff-revalidation.json", learning)

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, phase="preflight", context=fixed_context())

        self.assertEqual(manifest["status"], "pass")
        self.assertTrue(manifest["checks"]["auto_improve_learning_claim_blockers_clear"])
        self.assertEqual(
            manifest["diagnostics"]["auto_improve"]["learning_claim_blocker_count"],
            1,
        )
        self.assertEqual(
            manifest["diagnostics"]["auto_improve"][
                "unaccepted_learning_claim_blocker_count"
            ],
            0,
        )

    def test_preflight_treats_release_gate_blockers_as_diagnostics(self) -> None:
        self._write_common_inputs(
            promotion_blockers=[
                {
                    "id": "promotion_blocked_by_release_batch_manifest_failure",
                    "scope": "release_gate",
                }
            ]
        )

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, phase="preflight", context=fixed_context())

        self.assertEqual(manifest["status"], "pass")
        self.assertEqual(
            manifest["diagnostics"]["auto_improve"][
                "release_gate_diagnostic_promotion_blocker_count"
            ],
            1,
        )
        self.assertEqual(
            manifest["diagnostics"]["auto_improve"]["stage3_blocking_promotion_blocker_count"],
            0,
        )

    def test_preflight_blocks_independent_promotion_blockers(self) -> None:
        self._write_common_inputs(
            promotion_blockers=[
                {
                    "id": "promotion_blocked_by_remediation_backlog_open",
                    "scope": "remediation_backlog",
                }
            ]
        )

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, phase="preflight", context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("auto_improve_independent_promotion_blockers_open", manifest["failures"])
        blocker = next(
            item
            for item in manifest["blockers"]
            if item["id"] == "auto_improve_independent_promotion_blockers_open"
        )
        self.assertEqual(blocker["gate_effect"], "blocks_promotion")

    def test_preflight_defers_unverified_goal_run_identity_to_final_promotion(self) -> None:
        self._write_common_inputs()
        identity = json.loads(
            (
                self.vault / "build/release/release-auto-promotion-goal-run-identity.json"
            ).read_text(encoding="utf-8")
        )
        identity["verification_status"] = "blocked"
        identity["verification_blockers"] = [
            {
                "id": "goal_runtime_certificate_not_verified",
                "source": "goal_runtime_certificate",
                "field_path": "$.status|$.certificate.verification_status|$.certificate.eligible",
                "observed": "status=attention;verification_status=blocked;eligible=False",
                "expected": (
                    "status=pass; verification_status in eligible,already_verified; "
                    "eligible=true"
                ),
                "gate_effect": "blocks_promotion",
                "summary": "The selected goal run does not have verified certificate evidence.",
                "recommended_next_step": (
                    "Run GOAL_RUN_ID=<completed-run-id> make goal-runtime-certificate "
                    "after the promoted run is complete."
                ),
            }
        ]
        identity["verification_failures"] = ["goal_runtime_certificate_not_verified"]
        self._write_json("build/release/release-auto-promotion-goal-run-identity.json", identity)

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, phase="preflight", context=fixed_context())

        self.assertEqual(manifest["status"], "pass")
        self.assertTrue(manifest["checks"]["goal_run_identity_pass"])
        self.assertEqual(manifest["failures"], [])
        self.assertEqual(
            manifest["diagnostics"]["goal_run_identity"]["verification_status"],
            "blocked",
        )
        self.assertEqual(
            manifest["diagnostics"]["goal_run_identity"]["verification_failure_count"],
            1,
        )
        self.assertEqual(
            [item["id"] for item in manifest["final_promotion_blockers"]],
            ["goal_runtime_certificate_not_verified"],
        )
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])

    def test_preflight_bootstraps_without_existing_promoted_goal_run(self) -> None:
        self._write_common_inputs()
        identity = json.loads(
            (
                self.vault / "build/release/release-auto-promotion-goal-run-identity.json"
            ).read_text(encoding="utf-8")
        )
        identity["binding_status"] = "unresolved"
        identity["verification_status"] = "pending"
        identity["effective_run_id"] = ""
        identity["inferred_run_id"] = ""
        identity["selection_mode"] = "unresolved"
        identity["observed"]["effective_run_id"] = ""
        identity["observed"]["inferred_run_id"] = ""
        identity["observed"]["goal_run_status_run_id"] = ""
        identity["observed"]["goal_runtime_certificate_run_id"] = ""
        identity["verification_blockers"] = [
            {
                "id": "goal_run_id_unresolved",
                "source": "make|goal_run_status|goal_runtime_certificate",
                "field_path": "GOAL_RUN_ID|$.run.run_id",
                "observed": "requested=auto-improve-trial; origin=file",
                "expected": "explicit GOAL_RUN_ID or matching verified promoted run evidence",
                "gate_effect": "blocks_promotion",
                "summary": "Release auto-promotion could not resolve the goal run id.",
                "recommended_next_step": (
                    "Rerun with GOAL_RUN_ID=<goal-run-id> or publish matching verified run evidence."
                ),
            }
        ]
        identity["verification_failures"] = ["goal_run_id_unresolved"]
        self._write_json("build/release/release-auto-promotion-goal-run-identity.json", identity)

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, phase="preflight", context=fixed_context())

        self.assertEqual(manifest["status"], "pass")
        self.assertFalse(manifest["checks"]["goal_run_identity_effective_run_id_present"])
        self.assertEqual(manifest["diagnostics"]["goal_run_identity"]["binding_status"], "unresolved")
        self.assertEqual(
            [item["id"] for item in manifest["final_promotion_blockers"]],
            ["goal_run_id_unresolved"],
        )
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])

    def test_preseal_requires_clean_closeout_and_strict_cohort(self) -> None:
        self._write_common_inputs()
        self._write_preseal_inputs()

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, phase="preseal", context=fixed_context())

        self.assertEqual(manifest["status"], "pass")
        self.assertEqual(manifest["phase"], "preseal")
        self.assertTrue(manifest["checks"]["closeout_summary_clean"])
        self.assertTrue(manifest["checks"]["evidence_cohort_strict"])
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])

        closeout = json.loads(
            (self.vault / "ops/reports/release-closeout-summary.json").read_text(
                encoding="utf-8"
            )
        )
        closeout["summary"]["accepted_risk_instance_count"] = 1
        closeout["summary"]["release_blocking_risk_family_count"] = 0
        self._write_json("ops/reports/release-closeout-summary.json", closeout)

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, phase="preseal", context=fixed_context())

        self.assertEqual(manifest["status"], "pass")
        self.assertTrue(manifest["checks"]["closeout_accepted_risk_clean"])
        self.assertNotIn("closeout_accepted_risk_not_clean", manifest["failures"])

        closeout["summary"]["release_blocking_risk_family_count"] = 1
        self._write_json("ops/reports/release-closeout-summary.json", closeout)

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, phase="preseal", context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertFalse(manifest["checks"]["closeout_accepted_risk_clean"])
        self.assertIn("closeout_accepted_risk_not_clean", manifest["failures"])
        blocker = next(
            item
            for item in manifest["blockers"]
            if item["id"] == "closeout_accepted_risk_not_clean"
        )
        self.assertEqual(blocker["gate_effect"], "operator_review_required")

        closeout["summary"]["accepted_risk_instance_count"] = 0
        closeout["summary"]["release_blocking_risk_family_count"] = 0
        closeout["summary"]["gate_attention_count"] = 1
        self._write_json("ops/reports/release-closeout-summary.json", closeout)

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, phase="preseal", context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertTrue(manifest["checks"]["closeout_accepted_risk_clean"])
        self.assertFalse(manifest["checks"]["closeout_gate_attention_clean"])
        self.assertNotIn("closeout_accepted_risk_not_clean", manifest["failures"])
        self.assertIn("closeout_gate_attention_not_clean", manifest["failures"])
        blocker = next(
            item
            for item in manifest["blockers"]
            if item["id"] == "closeout_gate_attention_not_clean"
        )
        self.assertEqual(blocker["gate_effect"], "blocks_promotion")

    def test_preseal_rejects_revision_stale_closeout_even_when_fingerprint_matches(
        self,
    ) -> None:
        self._write_common_inputs()
        self._write_preseal_inputs()
        closeout = json.loads(
            (self.vault / "ops/reports/release-closeout-summary.json").read_text(
                encoding="utf-8"
            )
        )
        closeout["source_revision"] = "old-revision"
        self._write_json("ops/reports/release-closeout-summary.json", closeout)

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, phase="preseal", context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertFalse(manifest["checks"]["closeout_summary_current"])
        self.assertIn("closeout_summary_stale", manifest["failures"])

    def test_preseal_requires_closeout_source_tree_coherence(self) -> None:
        self._write_common_inputs()
        self._write_preseal_inputs()
        closeout = json.loads(
            (self.vault / "ops/reports/release-closeout-summary.json").read_text(
                encoding="utf-8"
            )
        )
        closeout["summary"]["source_tree_coherence_status"] = "attention"
        self._write_json("ops/reports/release-closeout-summary.json", closeout)

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, phase="preseal", context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertFalse(manifest["checks"]["closeout_source_tree_coherence_clean"])
        self.assertIn("closeout_source_tree_coherence_not_clean", manifest["failures"])


if __name__ == "__main__":
    unittest.main()
