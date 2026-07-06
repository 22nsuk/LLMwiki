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
    SAMPLE_GENERATION_FIXTURE_SEED,
    SAMPLE_GENERATION_SELF_CONTAINED,
    _assert_sample_coverage_matches_payload,
    _normalize_sample_vault_text_newlines,
    _write_stable_json_file,
    build_auto_improve_readiness_schema_sample,
    build_openvex_schema_sample,
    build_release_run_ready_plan_schema_sample,
    build_supply_chain_schema_samples,
    report_schema_sample_coverage_table,
    seed_preserved_report_schema_sample_keys,
    self_contained_report_schema_sample_keys,
    self_contained_report_schema_sample_update_keys,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "report_schema_samples.json"

pytestmark = [
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
    pytest.mark.schema_static_smoke,
]


def _assert_sample_matches(
    case: unittest.TestCase, actual: object, expected: object, sample_key: str
) -> None:
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
    def test_sample_coverage_table_matches_fixture_keys(self) -> None:
        samples = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        coverage = report_schema_sample_coverage_table()

        self.assertEqual([entry.sample_key for entry in coverage], list(samples))
        self.assertEqual(
            tuple(
                entry.sample_key
                for entry in coverage
                if entry.generation == SAMPLE_GENERATION_SELF_CONTAINED
            ),
            self_contained_report_schema_sample_keys(),
        )
        self.assertEqual(
            tuple(
                entry.sample_key
                for entry in coverage
                if entry.generation == SAMPLE_GENERATION_FIXTURE_SEED
            ),
            seed_preserved_report_schema_sample_keys(),
        )
        for entry in coverage:
            if entry.generation == SAMPLE_GENERATION_SELF_CONTAINED:
                self.assertTrue(entry.builder, entry.sample_key)
            else:
                self.assertEqual(entry.generation, SAMPLE_GENERATION_FIXTURE_SEED)
                self.assertEqual(entry.builder, "")

    def test_sample_coverage_table_declares_valid_dependency_order(self) -> None:
        seen: set[str] = set()
        allowed_generation_modes = {
            SAMPLE_GENERATION_FIXTURE_SEED,
            SAMPLE_GENERATION_SELF_CONTAINED,
        }

        for entry in report_schema_sample_coverage_table():
            self.assertNotIn(entry.sample_key, seen)
            self.assertIn(entry.generation, allowed_generation_modes)
            for dependency in entry.dependencies:
                self.assertIn(dependency, seen, entry.sample_key)
            seen.add(entry.sample_key)

    def test_self_contained_update_keys_track_coverage_table(self) -> None:
        self.assertEqual(
            self_contained_report_schema_sample_update_keys(),
            self_contained_report_schema_sample_keys(),
        )
        self.assertEqual(
            self_contained_report_schema_sample_update_keys(include_openvex=False),
            tuple(
                sample_key
                for sample_key in self_contained_report_schema_sample_keys()
                if sample_key != "openvex_draft"
            ),
        )

    def test_sample_coverage_mismatch_fails_with_clear_diagnostic(self) -> None:
        samples = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        samples["unexpected_sample"] = {}

        with self.assertRaisesRegex(ValueError, "missing_from_coverage"):
            _assert_sample_coverage_matches_payload(samples)

    def test_generator_does_not_import_test_case_modules(self) -> None:
        source = (
            REPO_ROOT / "tools" / "regenerate_report_schema_samples.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("tests.test_", source)

    def test_generated_openvex_sample_matches_frozen_fixture(self) -> None:
        samples = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cyclonedx_sample = build_supply_chain_schema_samples()["cyclonedx_bom"]

        _assert_sample_matches(
            self,
            build_openvex_schema_sample(cyclonedx_sample),
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

    def test_generated_release_run_ready_plan_sample_matches_frozen_fixture(
        self,
    ) -> None:
        samples = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        _assert_sample_matches(
            self,
            build_release_run_ready_plan_schema_sample(),
            samples["release_run_ready_plan"],
            "release_run_ready_plan",
        )

    def test_generated_readiness_sample_keeps_release_clean_queue_blocked_shape(
        self,
    ) -> None:
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
            fixture.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

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

    def test_sample_vault_newline_normalizer_makes_text_fixtures_platform_stable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            path = vault / "ops" / "scripts" / "example.py"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"print('one')\r\nprint('two')\r\n")

            _normalize_sample_vault_text_newlines(vault)

            self.assertEqual(path.read_bytes(), b"print('one')\nprint('two')\n")

    def test_stable_json_writer_uses_lf_bytes_for_input_fingerprints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "sample.json"

            _write_stable_json_file(path, {"lines": ["one", "two"]})

            raw = path.read_bytes()

        self.assertIn(b'\n  "lines": [\n', raw)
        self.assertNotIn(b"\r\n", raw)


if __name__ == "__main__":
    unittest.main()
