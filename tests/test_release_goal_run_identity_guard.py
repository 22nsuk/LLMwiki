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

from ops.scripts.release.release_goal_run_identity_guard import (
    build_report,
    read_effective_run_id_from_report,
    write_report,
)
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public


SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-goal-run-identity.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 23, 12, 0, tzinfo=dt.UTC),
    )


class ReleaseGoalRunIdentityGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy("ops/schemas/release-goal-run-identity.schema.json")

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

    def _write_identity_inputs(self, *, run_id: str = "promote-run") -> None:
        self._write_json(
            "ops/reports/goal-run-status.json",
            {
                "artifact_kind": "goal_run_status",
                "producer": "tests.goal_run_status",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_tree_fingerprint": "fp-current",
                "status": "pass",
                "run": {
                    "run_id": run_id,
                    "status": "completed",
                    "runtime_mode": "self_improvement_loop",
                },
                "health": {
                    "promotion_status": "allowed",
                    "can_promote_result": True,
                },
            },
        )
        self._write_json(
            "ops/reports/goal-runtime-certificate.json",
            {
                "artifact_kind": "goal_runtime_certificate",
                "producer": "tests.goal_runtime_certificate",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_tree_fingerprint": "fp-current",
                "status": "pass",
                "certificate": {
                    "verification_status": "eligible",
                    "eligible": True,
                    "already_verified": False,
                },
                "run": {
                    "run_id": run_id,
                    "run_status": "completed",
                },
            },
        )

    def _patch_current_repo(self) -> Any:
        return patch.multiple(
            "ops.scripts.release.release_goal_run_identity_guard",
            release_source_tree_fingerprint=lambda _vault: "fp-current",
            git_commit=lambda _vault: "abc123",
        )

    def test_explicit_matching_goal_run_identity_passes(self) -> None:
        self._write_identity_inputs()

        with self._patch_current_repo():
            report = build_report(
                self.vault,
                goal_run_id="promote-run",
                goal_run_id_origin="command line",
                context=fixed_context(),
            )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["effective_run_id"], "promote-run")
        self.assertEqual(report["selection_mode"], "explicit")
        self.assertEqual(report["blockers"], [])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
        report_path = write_report(
            self.vault,
            report,
            "build/release/release-auto-promotion-goal-run-identity.json",
        )
        self.assertTrue(report_path.exists())
        effective_run_id, error = read_effective_run_id_from_report(
            self.vault,
            "build/release/release-auto-promotion-goal-run-identity.json",
        )
        self.assertEqual(error, "")
        self.assertEqual(effective_run_id, "promote-run")

    def test_makefile_default_goal_run_id_infers_verified_promoted_evidence(self) -> None:
        self._write_identity_inputs(run_id="promote-run")

        with self._patch_current_repo():
            report = build_report(
                self.vault,
                goal_run_id="auto-improve-trial",
                goal_run_id_origin="file",
                context=fixed_context(),
            )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["requested_run_id"], "auto-improve-trial")
        self.assertEqual(report["effective_run_id"], "promote-run")
        self.assertEqual(report["inferred_run_id"], "promote-run")
        self.assertEqual(report["selection_mode"], "inferred_from_verified_evidence")
        self.assertFalse(report["checks"]["goal_run_id_explicit"])
        self.assertTrue(report["checks"]["goal_run_id_inferred"])
        self.assertTrue(report["checks"]["goal_run_id_not_file_default"])

    def test_makefile_default_goal_run_id_is_blocked_before_release_lane_writes(self) -> None:
        self._write_identity_inputs(run_id="auto-improve-trial")

        with self._patch_current_repo():
            report = build_report(
                self.vault,
                goal_run_id="auto-improve-trial",
                goal_run_id_origin="file",
                context=fixed_context(),
            )

        self.assertEqual(report["status"], "fail")
        self.assertIn("goal_run_id_file_default", report["failures"])

    def test_explicit_goal_run_id_must_match_inferred_verified_evidence(self) -> None:
        self._write_identity_inputs(run_id="promote-run")

        with self._patch_current_repo():
            report = build_report(
                self.vault,
                goal_run_id="other-run",
                goal_run_id_origin="command line",
                context=fixed_context(),
            )

        self.assertEqual(report["status"], "fail")
        self.assertIn("explicit_goal_run_id_mismatch", report["failures"])
        self.assertIn("goal_run_status_run_id_mismatch", report["failures"])

    def test_mismatched_status_or_certificate_run_id_is_blocked(self) -> None:
        self._write_identity_inputs(run_id="promote-run")
        certificate = json.loads(
            (self.vault / "ops/reports/goal-runtime-certificate.json").read_text(
                encoding="utf-8"
            )
        )
        certificate["run"]["run_id"] = "other-run"
        self._write_json("ops/reports/goal-runtime-certificate.json", certificate)

        with self._patch_current_repo():
            report = build_report(
                self.vault,
                goal_run_id="promote-run",
                goal_run_id_origin="command line",
                context=fixed_context(),
            )

        self.assertEqual(report["status"], "fail")
        self.assertIn("goal_runtime_certificate_run_id_mismatch", report["failures"])


if __name__ == "__main__":
    unittest.main()
