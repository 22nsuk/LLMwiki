from __future__ import annotations

import unittest

import pytest

from ops.scripts.auto_improve_readiness_release_authority_runtime import (
    _artifact_contract_promotion_blockers,
    _release_gate_promotion_blockers,
    _release_gate_summaries,
)

pytestmark = pytest.mark.public


def _pass_release_reports() -> dict[str, dict]:
    return {
        "artifact_freshness": {
            "status": "pass",
            "summary": {
                "schema_invalid_artifact_count": 0,
                "stable_contract_debt_issue_count": 0,
            },
            "artifact_records": [],
        },
        "selected_contract": {
            "artifact_kind": "test_execution_summary",
            "status": "pass",
            "currentness": {"status": "current", "checked_at": "2026-05-17T00:00:00Z"},
        },
        "source_package": {
            "artifact_kind": "source_package_clean_extract",
            "status": "pass",
        },
        "release_closeout": {
            "artifact_kind": "release_closeout_summary",
            "status": "pass",
            "clean_release_ready": True,
            "machine_release_allowed": True,
            "release_authority_status": "clean_pass",
            "sealed_release_status": "sealed_clean_pass",
        },
        "release_batch_manifest": {
            "artifact_kind": "release_closeout_batch_manifest",
            "status": "pass",
            "release_authority_status": "clean_pass",
            "sealed_release_status": "sealed_clean_pass",
            "batch_integrity_status": "pass",
            "machine_release_status": "allowed",
            "distribution_package": {"status": "materialized"},
        },
        "release_finality": {
            "artifact_kind": "release_closeout_finality_attestation",
            "status": "pass",
            "finality_status": "pass",
            "finality_failures": [],
        },
        "release_evidence_cohort": {
            "artifact_kind": "release_evidence_cohort",
            "status": "pass",
            "summary": {"clean_lane_contract_status": "pass"},
            "cohort": {
                "strict_same_fingerprint": True,
                "component_fingerprint_count": 1,
            },
        },
        "artifact_finalization": {
            "artifact_kind": "release_closeout_post_check_finalizer",
            "status": "pass",
            "refresh_required": False,
            "affected_path_count": 0,
        },
        "release_authority_preflight": {
            "artifact_kind": "release_closeout_sealed_rehearsal_check",
            "status": "pass",
            "preflight_status": "sealed_clean_pass",
            "distribution_binding_status": "pass",
            "authority_preflight_status": "clean",
            "failures": [],
            "blocking_reason_ids": [],
        },
    }


def _release_gate_blockers(summaries: dict[str, dict]) -> list[dict]:
    return _release_gate_promotion_blockers(
        summaries["selected_contract"],
        summaries["source_package"],
        summaries["release_closeout"],
        summaries["release_batch_manifest"],
        summaries["release_finality"],
        summaries["release_evidence_cohort"],
        summaries["artifact_finalization"],
    )


class AutoImproveReadinessReleaseAuthorityRuntimeTests(unittest.TestCase):
    def test_selected_contract_currentness_blocks_promotion_even_when_artifact_freshness_passes(
        self,
    ) -> None:
        reports = _pass_release_reports()
        reports["selected_contract"] = {
            "artifact_kind": "test_execution_summary",
            "status": "fail",
        }

        summaries = _release_gate_summaries(reports)
        release_gate_blockers = _release_gate_blockers(summaries)
        artifact_contract_blockers = _artifact_contract_promotion_blockers(
            summaries["artifact_freshness"],
            reports["artifact_freshness"],
        )

        self.assertEqual(artifact_contract_blockers, [])
        self.assertEqual(summaries["artifact_freshness"]["status"], "pass")
        self.assertEqual(summaries["selected_contract"]["status"], "fail")
        self.assertEqual(len(release_gate_blockers), 1)
        blocker = release_gate_blockers[0]
        self.assertEqual(blocker["id"], "promotion_blocked_by_selected_contract_failure")
        self.assertEqual(blocker["signal_ids"], ["selected_contract_status_not_pass"])
        self.assertIn("selected_contract release gate is not pass", blocker["reason"])

    def test_selected_contract_operational_currentness_drift_is_a_release_gate_blocker(self) -> None:
        reports = _pass_release_reports()
        reports["artifact_freshness"]["artifact_records"] = [
            {
                "path": "ops/reports/test-execution-summary.json",
                "issues": ["test_target_fingerprint_mismatch: selected contract currentness drift"],
                "schema_validation_status": "pass",
            }
        ]

        summaries = _release_gate_summaries(reports)
        release_gate_blockers = _release_gate_blockers(summaries)
        artifact_contract_blockers = _artifact_contract_promotion_blockers(
            summaries["artifact_freshness"],
            reports["artifact_freshness"],
        )

        self.assertEqual(artifact_contract_blockers, [])
        self.assertEqual(len(release_gate_blockers), 1)
        blocker = release_gate_blockers[0]
        self.assertEqual(blocker["id"], "promotion_blocked_by_selected_contract_failure")
        self.assertEqual(blocker["signal_ids"], ["selected_contract_currentness_not_current"])
        self.assertIn("operational_attention=", blocker["reason"])

    def test_release_closeout_gate_prefers_status_v2_axes_over_legacy_machine_booleans(
        self,
    ) -> None:
        reports = _pass_release_reports()
        reports["release_closeout"]["machine_release_allowed"] = True
        reports["release_closeout"]["clean_release_ready"] = True
        reports["release_closeout"]["status_v2"] = {
            "schema_version": 2,
            "compatibility_status_value": "pass",
            "status_axes": {
                "release_authority_status": "conditional_pass",
                "sealed_release_status": "unsealed_distribution_not_provided",
            },
            "blocker_reason_ids": ["machine_release_not_allowed"],
        }

        summaries = _release_gate_summaries(reports)

        self.assertEqual(summaries["release_closeout"]["status"], "fail")
        self.assertEqual(
            summaries["release_closeout"]["signal_ids"],
            ["machine_release_not_allowed"],
        )


if __name__ == "__main__":
    unittest.main()
