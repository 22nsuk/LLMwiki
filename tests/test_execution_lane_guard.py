from __future__ import annotations

import tempfile
import unittest
import shutil
from pathlib import Path

import pytest

from ops.scripts.execution_lane_guard import build_result, main
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault


pytestmark = pytest.mark.public


class ExecutionLaneGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        policy = self.vault / "ops" / "policies" / "execution-lanes.json"
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text(
            (REPO_ROOT / "ops" / "policies" / "execution-lanes.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_guard_fails_full_vault_target_in_source_package_extract(self) -> None:
        shutil.rmtree(self.vault / "raw", ignore_errors=True)
        shutil.rmtree(self.vault / "wiki", ignore_errors=True)
        shutil.rmtree(self.vault / "system", ignore_errors=True)
        (self.vault / "release-archive-self-description.json").write_text(
            '{"archive_root_name":"LLMwiki"}\n',
            encoding="utf-8",
        )

        result = build_result(self.vault, target="check-clean")

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["detected_lane"], "source_package_extract")
        self.assertEqual(result["required_lane"], "full_vault")
        self.assertIn("make release-source-package-smoke", result["alternatives"])

    def test_source_package_sentinel_wins_over_corpus_sentinels(self) -> None:
        (self.vault / "raw").mkdir(exist_ok=True)
        (self.vault / "wiki").mkdir(exist_ok=True)
        (self.vault / "wiki" / "index.md").write_text("# wiki\n", encoding="utf-8")
        (self.vault / "system").mkdir(exist_ok=True)
        (self.vault / "system" / "system-index.md").write_text("# system\n", encoding="utf-8")
        (self.vault / "release-archive-self-description.json").write_text(
            '{"archive_root_name":"LLMwiki"}\n',
            encoding="utf-8",
        )

        result = build_result(self.vault, target="release-distribution-zip")

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["detected_lane"], "source_package_extract")
        self.assertEqual(result["required_lane"], "full_vault")

    def test_guard_fails_release_run_ready_in_source_package_extract(self) -> None:
        shutil.rmtree(self.vault / "raw", ignore_errors=True)
        shutil.rmtree(self.vault / "wiki", ignore_errors=True)
        shutil.rmtree(self.vault / "system", ignore_errors=True)
        (self.vault / "release-archive-self-description.json").write_text(
            '{"archive_root_name":"LLMwiki"}\n',
            encoding="utf-8",
        )

        result = build_result(self.vault, target="release-run-ready")

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["detected_lane"], "source_package_extract")
        self.assertEqual(result["required_lane"], "full_vault")
        self.assertIn("make release-source-package-smoke", result["alternatives"])

    def test_guard_allows_unknown_target_in_public_or_partial_checkout(self) -> None:
        shutil.rmtree(self.vault / "raw", ignore_errors=True)
        shutil.rmtree(self.vault / "wiki", ignore_errors=True)
        shutil.rmtree(self.vault / "system", ignore_errors=True)

        result = build_result(self.vault, target="unregistered-local-target")

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["detected_lane"], "public_or_partial_checkout")

    def test_guard_fails_release_packaging_replay_in_source_package_extract(self) -> None:
        shutil.rmtree(self.vault / "raw", ignore_errors=True)
        shutil.rmtree(self.vault / "wiki", ignore_errors=True)
        shutil.rmtree(self.vault / "system", ignore_errors=True)
        (self.vault / "release-archive-self-description.json").write_text(
            '{"archive_root_name":"LLMwiki"}\n',
            encoding="utf-8",
        )

        for target in (
            "release-distribution-zip",
            "release-evidence-converge",
            "release-verify-current",
            "release-sealed-verify",
            "release-smoke",
            "release-evidence-closeout",
            "release-builder-full",
        ):
            with self.subTest(target=target):
                result = build_result(self.vault, target=target)

                self.assertEqual(result["status"], "fail")
                self.assertEqual(result["detected_lane"], "source_package_extract")
                self.assertEqual(result["required_lane"], "full_vault")
                self.assertIn("make release-source-package-smoke", result["alternatives"])

    def test_guard_passes_full_vault_target_when_full_vault_sentinels_exist(self) -> None:
        (self.vault / "raw").mkdir(exist_ok=True)
        (self.vault / "wiki").mkdir(exist_ok=True)
        (self.vault / "wiki" / "index.md").write_text("# wiki\n", encoding="utf-8")
        (self.vault / "system").mkdir(exist_ok=True)
        (self.vault / "system" / "system-index.md").write_text("# system\n", encoding="utf-8")

        result = build_result(self.vault, target="check-clean")

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["detected_lane"], "full_vault")

    def test_main_returns_distinct_failure_code_for_wrong_lane(self) -> None:
        shutil.rmtree(self.vault / "raw", ignore_errors=True)
        shutil.rmtree(self.vault / "wiki", ignore_errors=True)
        shutil.rmtree(self.vault / "system", ignore_errors=True)
        (self.vault / "release-archive-self-description.json").write_text(
            '{"archive_root_name":"LLMwiki"}\n',
            encoding="utf-8",
        )

        exit_code = main(["--vault", self.vault.as_posix(), "--target", "check-clean"])

        self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
