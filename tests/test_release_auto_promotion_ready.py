from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from ops.scripts.release.release_auto_promotion_ready import build_manifest, write_manifest
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public


SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-auto-promotion-ready-manifest.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 23, 12, 0, tzinfo=dt.timezone.utc),
    )


class ReleaseAutoPromotionReadyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy("ops/schemas/release-auto-promotion-ready-manifest.schema.json")

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

    def _operator_summary(self, **overrides) -> dict:
        payload = {
            "artifact_kind": "operator_release_summary",
            "producer": "tests.operator",
            "generated_at": "2026-05-23T12:00:00Z",
            "source_tree_fingerprint": "fp-current",
            "status": "pass",
            "source_zip_policy_status": "match",
            "tmp_json_policy_status": "clean",
            "artifact_digest_policy_status": "match",
            "batch_verify": {"status": "pass"},
            "test_evidence": {"full_suite_status": "pass"},
            "learning_readiness": {"revalidation_status": "current"},
            "accepted_risk": {
                "accepted_risk_count": 0,
                "release_accepted_risk_count": 0,
                "accepted_learning_risk_count": 0,
                "clean_lane_blocking_accepted_risk_family_count": 0,
                "gate_attention_count": 0,
                "learning_claim_blocking_family_count": 0,
            },
        }
        payload.update(overrides)
        return payload

    def _write_inputs(self) -> None:
        self._write_json(
            "build/release/release-run-manifest.json",
            {
                "artifact_kind": "release_run_manifest",
                "producer": "tests.run",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_tree_fingerprint": "fp-current",
                "status": "pass",
            },
        )
        self._write_json(
            "build/release/release-sealed-run-manifest.json",
            {
                "artifact_kind": "release_sealed_run_manifest",
                "producer": "tests.sealed",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_tree_fingerprint": "fp-current",
                "status": "pass",
            },
        )
        self._write_json("build/release/operator-release-summary.json", self._operator_summary())
        self._write_json(
            "ops/reports/auto-improve-readiness.json",
            {
                "artifact_kind": "auto_improve_readiness_report",
                "producer": "tests.auto_improve",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_tree_fingerprint": "fp-current",
                "status": "pass",
                "can_execute_trial": True,
                "can_promote_result": True,
                "learning_claim_blockers": [],
                "promotion_blockers": [],
                "clean_release_blockers": [],
            },
        )

    def _patch_current_repo(self):
        return patch.multiple(
            "ops.scripts.release.release_auto_promotion_ready",
            release_source_tree_fingerprint=lambda _vault: "fp-current",
            git_commit=lambda _vault: "abc123",
        )

    def test_manifest_passes_when_all_low_cost_inputs_are_clean(self) -> None:
        self._write_inputs()

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, context=fixed_context())

        self.assertEqual(manifest["status"], "pass")
        self.assertTrue(manifest["unattended_promotion_allowed"])
        self.assertEqual(manifest["blockers"], [])
        self.assertNotIn("payload_status", json.dumps(manifest, ensure_ascii=False))
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(
            write_manifest(
                self.vault,
                manifest,
                "build/release/release-auto-promotion-ready-manifest.json",
            ).exists()
        )

    def test_operator_attention_blocks_auto_promotion(self) -> None:
        self._write_inputs()
        self._write_json(
            "build/release/operator-release-summary.json",
            self._operator_summary(status="attention"),
        )

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("operator_attention_open", manifest["failures"])

    def test_operator_summary_load_and_kind_are_explicit_blockers(self) -> None:
        self._write_inputs()
        operator_path = self.vault / "build/release/operator-release-summary.json"
        operator_path.write_text("{not-json", encoding="utf-8")

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("operator_summary_not_loadable", manifest["failures"])

        self._write_json(
            "build/release/operator-release-summary.json",
            self._operator_summary(artifact_kind="legacy_operator_summary"),
        )

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("operator_summary_artifact_kind_invalid", manifest["failures"])

    def test_stale_run_and_sealed_manifests_block_auto_promotion(self) -> None:
        self._write_inputs()
        self._write_json(
            "build/release/release-run-manifest.json",
            {
                "artifact_kind": "release_run_manifest",
                "producer": "tests.run",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_tree_fingerprint": "fp-old",
                "status": "pass",
            },
        )
        self._write_json(
            "build/release/release-sealed-run-manifest.json",
            {
                "artifact_kind": "release_sealed_run_manifest",
                "producer": "tests.sealed",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_tree_fingerprint": "fp-old",
                "status": "pass",
            },
        )

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("run_manifest_stale", manifest["failures"])
        self.assertIn("sealed_run_manifest_stale", manifest["failures"])

    def test_learning_revalidation_due_blocks_auto_promotion(self) -> None:
        self._write_inputs()
        operator = self._operator_summary(learning_readiness={"revalidation_status": "due"})
        self._write_json("build/release/operator-release-summary.json", operator)

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("learning_revalidation_not_current", manifest["failures"])

    def test_auto_improve_promotion_blocker_blocks_auto_promotion(self) -> None:
        self._write_inputs()
        self._write_json(
            "ops/reports/auto-improve-readiness.json",
            {
                "artifact_kind": "auto_improve_readiness_report",
                "producer": "tests.auto_improve",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_tree_fingerprint": "fp-current",
                "can_execute_trial": True,
                "can_promote_result": False,
                "learning_claim_blockers": [],
                "promotion_blockers": [{"id": "blocked"}],
                "clean_release_blockers": [],
            },
        )

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("auto_improve_result_not_promotable", manifest["failures"])
        self.assertIn("auto_improve_blockers_open", manifest["failures"])

    def test_auto_improve_readiness_load_and_kind_are_explicit_blockers(self) -> None:
        self._write_inputs()
        readiness_path = self.vault / "ops/reports/auto-improve-readiness.json"
        readiness_path.write_text("{not-json", encoding="utf-8")

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("auto_improve_readiness_not_loadable", manifest["failures"])

        self._write_json(
            "ops/reports/auto-improve-readiness.json",
            {
                "artifact_kind": "legacy_auto_improve_readiness",
                "producer": "tests.auto_improve",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_tree_fingerprint": "fp-current",
                "can_execute_trial": True,
                "can_promote_result": True,
                "learning_claim_blockers": [],
                "promotion_blockers": [],
                "clean_release_blockers": [],
            },
        )

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("auto_improve_readiness_artifact_kind_invalid", manifest["failures"])

    def test_accepted_risk_blocks_auto_promotion(self) -> None:
        self._write_inputs()
        operator = self._operator_summary()
        operator["accepted_risk"]["accepted_risk_count"] = 1
        self._write_json("build/release/operator-release-summary.json", operator)

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("accepted_risk_count_not_zero", manifest["failures"])


if __name__ == "__main__":
    unittest.main()
