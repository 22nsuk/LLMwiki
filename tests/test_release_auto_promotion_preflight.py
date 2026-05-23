from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from ops.scripts.release.release_auto_promotion_preflight import build_manifest, write_manifest
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public


SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-auto-promotion-preflight.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 23, 12, 0, tzinfo=dt.timezone.utc),
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
            "ops/reports/auto-improve-readiness.json",
            {
                "artifact_kind": "auto_improve_readiness_report",
                "producer": "tests.auto_improve",
                "generated_at": "2026-05-23T12:00:00Z",
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
                "source_tree_fingerprint": "fp-current",
                "status": "pass",
                "cohort": {
                    "strict_same_fingerprint": True,
                    "component_fingerprint_count": 5,
                },
                "summary": {"clean_lane_contract_status": "pass"},
            },
        )

    def _patch_current_repo(self):
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
        self.assertTrue(manifest["checks"]["auto_improve_stage3_promotion_blockers_clear"])
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(
            write_manifest(
                self.vault,
                manifest,
                "build/release/release-auto-promotion-preflight.json",
            ).exists()
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
        self._write_json("ops/reports/release-closeout-summary.json", closeout)

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, phase="preseal", context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertFalse(manifest["checks"]["closeout_accepted_risk_clean"])
        self.assertIn("closeout_accepted_risk_not_clean", manifest["failures"])

        closeout["summary"]["accepted_risk_instance_count"] = 0
        closeout["summary"]["gate_attention_count"] = 1
        self._write_json("ops/reports/release-closeout-summary.json", closeout)

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, phase="preseal", context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertTrue(manifest["checks"]["closeout_accepted_risk_clean"])
        self.assertFalse(manifest["checks"]["closeout_gate_attention_clean"])
        self.assertNotIn("closeout_accepted_risk_not_clean", manifest["failures"])
        self.assertIn("closeout_gate_attention_not_clean", manifest["failures"])

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
