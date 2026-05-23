from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from ops.scripts.release.release_evidence_planner import build_plan, write_plan
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public


SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-evidence-plan.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 23, 12, 0, tzinfo=dt.timezone.utc),
    )


class ReleaseEvidencePlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy("ops/schemas/release-evidence-plan.schema.json")

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

    def _write_authorities(self) -> None:
        self._write_json(
            "build/release/release-run-manifest.json",
            {
                "artifact_kind": "release_run_manifest",
                "producer": "tests.run",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_tree_fingerprint": "fp-current",
                "input_fingerprints": {"tests": "pass"},
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
                "input_fingerprints": {"run_manifest": "abc"},
                "status": "pass",
            },
        )
        self._write_json(
            "build/release/operator-release-summary.json",
            {
                "artifact_kind": "operator_release_summary",
                "producer": "tests.operator",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_tree_fingerprint": "fp-current",
                "input_fingerprints": {"sealed_run_manifest": "def"},
                "status": "attention",
            },
        )
        self._write_json(
            "ops/reports/auto-improve-readiness.json",
            {
                "artifact_kind": "auto_improve_readiness_report",
                "producer": "tests.auto",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_tree_fingerprint": "fp-current",
                "input_fingerprints": {"auto_improve": "ghi"},
                "can_promote_result": False,
            },
        )

    def _patch_current_repo(self):
        return patch.multiple(
            "ops.scripts.release.release_evidence_planner",
            release_source_tree_fingerprint=lambda _vault: "fp-current",
            git_commit=lambda _vault: "abc123",
        )

    def test_auto_promotion_plan_reuses_lower_authorities_without_cascade(self) -> None:
        self._write_authorities()

        with self._patch_current_repo():
            plan = build_plan(self.vault, stage="auto-promotion-ready", context=fixed_context())

        self.assertEqual(plan["plan_status"], "ready")
        self.assertEqual(plan["blockers"], [])
        self.assertTrue(plan["nodes"]["run_manifest"]["can_reuse"])
        self.assertTrue(plan["nodes"]["sealed_run_manifest"]["can_reuse"])
        self.assertTrue(plan["nodes"]["run_manifest"]["dependency_fingerprint"])
        planned_targets = {action["target"] for action in plan["planned_actions"]}
        self.assertEqual(planned_targets, {"release-auto-promotion-operator-summary"})
        self.assertNotIn("release-run-ready", planned_targets)
        self.assertNotIn("release-sealed-run-ready", planned_targets)
        self.assertEqual(validate_with_schema(plan, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(write_plan(self.vault, plan, "build/release/release-evidence-plan.json").exists())

    def test_auto_promotion_plan_blocks_stale_sealed_authority_with_next_action(self) -> None:
        self._write_authorities()
        sealed = json.loads((self.vault / "build/release/release-sealed-run-manifest.json").read_text())
        sealed["source_tree_fingerprint"] = "fp-old"
        self._write_json("build/release/release-sealed-run-manifest.json", sealed)

        with self._patch_current_repo():
            plan = build_plan(self.vault, stage="auto-promotion-ready", context=fixed_context())

        self.assertEqual(plan["plan_status"], "blocked")
        self.assertIn("sealed_run_manifest_not_reusable", plan["failures"])
        self.assertEqual(plan["planned_actions"], [])
        self.assertIn("make release-sealed-run-ready", plan["blockers"][0]["recommended_next_step"])

    def test_auto_promotion_plan_reports_pre_seal_diagnostic_refresh_without_cascade(self) -> None:
        self._write_authorities()
        auto = json.loads((self.vault / "ops/reports/auto-improve-readiness.json").read_text())
        auto["source_tree_fingerprint"] = "fp-old"
        self._write_json("ops/reports/auto-improve-readiness.json", auto)

        with self._patch_current_repo():
            plan = build_plan(self.vault, stage="auto-promotion-ready", context=fixed_context())

        self.assertEqual(plan["plan_status"], "ready")
        planned_actions = {action["target"]: action for action in plan["planned_actions"]}
        self.assertEqual(
            set(planned_actions),
            {"release-auto-promotion-operator-summary", "auto-improve-readiness-report-body"},
        )
        self.assertEqual(
            planned_actions["auto-improve-readiness-report-body"]["action_type"],
            "pre_seal_diagnostic_refresh_required",
        )
        self.assertNotIn("release-run-ready", planned_actions)
        self.assertNotIn("release-sealed-run-ready", planned_actions)

    def test_sealed_plan_blocks_stale_run_authority_without_running_stage_one(self) -> None:
        self._write_authorities()
        run = json.loads((self.vault / "build/release/release-run-manifest.json").read_text())
        run["status"] = "fail"
        self._write_json("build/release/release-run-manifest.json", run)

        with self._patch_current_repo():
            plan = build_plan(self.vault, stage="sealed-run-ready", context=fixed_context())

        self.assertEqual(plan["plan_status"], "blocked")
        self.assertIn("run_manifest_not_reusable", plan["failures"])
        self.assertEqual(plan["planned_actions"], [])


if __name__ == "__main__":
    unittest.main()
