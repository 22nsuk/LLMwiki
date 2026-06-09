from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

from tools.regenerate_report_schema_samples import (
    _normalize_sample_vault_text_newlines,
    build_auto_improve_readiness_schema_sample,
    build_openvex_schema_sample,
    build_release_run_ready_plan_schema_sample,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "report_schema_samples.json"

pytestmark = pytest.mark.report_contract


def _assert_sample_matches(case: unittest.TestCase, actual: object, expected: object, sample_key: str) -> None:
    case.assertEqual(
        actual,
        expected,
        msg=(
            f"report schema sample fixture drift for {sample_key}; "
            "run `make report-schema-samples-regenerate` and review the fixture diff."
        ),
    )


def _isolated_child_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


class ReportSchemaSampleRegenerationTests(unittest.TestCase):
    def test_generated_openvex_sample_matches_frozen_fixture(self) -> None:
        samples = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        _assert_sample_matches(
            self,
            build_openvex_schema_sample(),
            samples["openvex_draft"],
            "openvex_draft",
        )

    def test_generated_readiness_sample_matches_frozen_fixture(self) -> None:
        samples = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        _assert_sample_matches(
            self,
            build_auto_improve_readiness_schema_sample(),
            samples["auto_improve_readiness_report"],
            "auto_improve_readiness_report",
        )

    def test_generated_release_run_ready_plan_sample_matches_frozen_fixture(self) -> None:
        samples = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        _assert_sample_matches(
            self,
            build_release_run_ready_plan_schema_sample(),
            samples["release_run_ready_plan"],
            "release_run_ready_plan",
        )

    def test_generated_readiness_sample_keeps_release_clean_queue_blocked_shape(self) -> None:
        sample = build_auto_improve_readiness_schema_sample()

        self.assertFalse(sample["can_execute_trial"])
        self.assertFalse(sample["can_promote_result"])
        self.assertEqual(sample["execution_readiness"]["status"], "warn")
        self.assertEqual(sample["learning_readiness"]["status"], "not_runnable")
        self.assertEqual(
            [blocker["id"] for blocker in sample["learning_claim_blockers"]],
            ["learning_blocked_by_execution_not_runnable"],
        )
        self.assertEqual(sample["clean_release_blockers"], [])
        self.assertEqual(
            [blocker["id"] for blocker in sample["execution_blockers"]],
            ["execution_blocked_by_no_runnable_proposal"],
        )
        self.assertNotIn(
            "execution_blocked_by_no_runnable_proposal",
            [blocker["id"] for blocker in sample["promotion_blockers"]],
        )

    def test_direct_script_help_runs_without_pythonpath(self) -> None:
        result = subprocess.run(
            [sys.executable, "tools/regenerate_report_schema_samples.py", "--help"],
            cwd=REPO_ROOT,
            env=_isolated_child_env(),
            check=False,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--skip-openvex", result.stdout)
        self.assertIn("--check", result.stdout)

    def test_direct_script_check_fails_on_stale_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = Path(temp_dir) / "report_schema_samples.json"
            payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
            payload["openvex_draft"]["@id"] = "urn:uuid:stale"
            fixture.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "tools/regenerate_report_schema_samples.py",
                    "--fixture",
                    fixture.as_posix(),
                    "--check",
                ],
                cwd=REPO_ROOT,
                env=_isolated_child_env(),
                check=False,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("report schema samples are stale", result.stderr)

    def test_direct_script_check_passes_for_current_fixture(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "tools/regenerate_report_schema_samples.py",
                "--check",
            ],
            cwd=REPO_ROOT,
            env=_isolated_child_env(),
            check=False,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_sample_vault_newline_normalizer_makes_text_fixtures_platform_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            path = vault / "ops" / "scripts" / "example.py"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"print('one')\r\nprint('two')\r\n")

            _normalize_sample_vault_text_newlines(vault)

            self.assertEqual(path.read_bytes(), b"print('one')\nprint('two')\n")


if __name__ == "__main__":
    unittest.main()
