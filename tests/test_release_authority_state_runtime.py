from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.release_authority_state_runtime import (
    clean_required_preflight_passes,
    current_release_manifest_pass,
    machine_release_allowed_from_status_view,
    release_artifact_revision,
    release_artifact_stale_for_revision,
    release_authority_reports_verified,
    release_status_v2_view_with_readiness_fallback,
)

pytestmark = pytest.mark.public


class ReleaseAuthorityStateRuntimeTests(unittest.TestCase):
    def test_machine_release_allowed_uses_release_authority_axis_and_blockers(self) -> None:
        clean_view = release_status_v2_view_with_readiness_fallback(
            {
                "status": "pass",
                "status_v2": {
                    "schema_version": 2,
                    "compatibility_status_value": "pass",
                    "status_axes": {
                        "release_authority_status": "clean_pass",
                        "semantic_release_status": "clean_pass",
                        "sealed_release_status": "sealed_clean_pass",
                    },
                    "blocker_reason_ids": [],
                },
            }
        )
        blocked_view = {
            **clean_view,
            "blocker_reason_ids": ["machine_release_not_allowed"],
        }

        self.assertTrue(machine_release_allowed_from_status_view(clean_view))
        self.assertFalse(machine_release_allowed_from_status_view(blocked_view))

    def test_clean_required_preflight_pass_is_shared_for_summary_and_blockers(self) -> None:
        self.assertTrue(
            clean_required_preflight_passes(
                status="pass",
                preflight_status="sealed_clean_pass",
                preflight_mode="clean_required",
                distribution_binding_status="pass",
                authority_preflight_status="clean",
                expected_blocked_preflight=False,
                clean_required_preflight=True,
            )
        )
        self.assertFalse(
            clean_required_preflight_passes(
                status="pass",
                preflight_status="sealed_clean_pass",
                preflight_mode="diagnostic",
                distribution_binding_status="pass",
                authority_preflight_status="clean",
                expected_blocked_preflight=False,
                clean_required_preflight=True,
            )
        )

    def test_release_authority_reports_verified_ignores_non_authoritative_dashboard_attention(
        self,
    ) -> None:
        closeout = {
            "status": "pass",
            "summary": {"live_make_check_status": "pass"},
            "status_v2": {
                "schema_version": 2,
                "compatibility_status_value": "pass",
                "status_axes": {
                    "release_authority_status": "conditional_pass",
                    "semantic_release_status": "conditional_pass",
                    "sealed_release_status": "unsealed_distribution_not_provided",
                },
                "blocker_reason_ids": ["machine_release_not_allowed"],
            },
        }
        dashboard = {
            "status": "attention",
            "summary": {
                "required_input_fail_count": 0,
                "live_rerun_fail_count": 1,
                "live_rerun_not_run_count": 1,
            },
            "gates": [
                {
                    "gate_id": "advisory_gate",
                    "authoritative_for_release": False,
                    "live_rerun_state": {"status": "fail"},
                }
            ],
        }

        self.assertTrue(
            release_authority_reports_verified(closeout=closeout, dashboard=dashboard)
        )

    def test_release_authority_reports_verified_blocks_authoritative_dashboard_fail(self) -> None:
        closeout = {
            "status": "pass",
            "summary": {"live_make_check_status": "pass"},
            "status_v2": {
                "schema_version": 2,
                "compatibility_status_value": "pass",
                "status_axes": {
                    "release_authority_status": "clean_pass",
                    "semantic_release_status": "clean_pass",
                    "sealed_release_status": "sealed_clean_pass",
                },
                "blocker_reason_ids": [],
            },
        }
        dashboard = {
            "summary": {"required_input_fail_count": 0},
            "gates": [
                {
                    "gate_id": "authoritative_gate",
                    "authoritative_for_release": True,
                    "live_rerun_state": {"status": "fail"},
                }
            ],
        }

        self.assertFalse(
            release_authority_reports_verified(closeout=closeout, dashboard=dashboard)
        )

    def test_release_manifest_currentness_and_revision_helpers_are_shared(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            manifest = vault / "build" / "release" / "release-run-manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                (
                    '{"artifact_kind":"release_run_manifest","status":"pass",'
                    '"source_tree_fingerprint":"fingerprint",'
                    '"source":{"revision":"current"}}\n'
                ),
                encoding="utf-8",
            )

            payload = {
                "status": "pass",
                "source": {"revision": "current"},
            }
            self.assertEqual(release_artifact_revision(payload), "current")
            self.assertFalse(release_artifact_stale_for_revision(payload, "current"))
            self.assertTrue(release_artifact_stale_for_revision(payload, "other"))
            self.assertTrue(
                current_release_manifest_pass(
                    vault,
                    "build/release/release-run-manifest.json",
                    "release_run_manifest",
                    source_tree_fingerprint="fingerprint",
                )
            )


if __name__ == "__main__":
    unittest.main()
