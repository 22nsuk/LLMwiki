from __future__ import annotations

import datetime as dt
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from ops.scripts.release.release_post_commit_finalizer import (
    build_report,
    main,
    write_report,
)
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public

SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-post-commit-finalization.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 23, 12, 0, tzinfo=dt.UTC),
    )


class ReleasePostCommitFinalizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy("ops/schemas/release-post-commit-finalization.schema.json")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy(self, rel_path: str) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _write_json(self, rel_path: str, payload: dict[str, Any]) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.vault, check=True, capture_output=True)

    def _init_clean_git(self) -> None:
        self._git("init")
        self._git("config", "user.email", "tests@example.invalid")
        self._git("config", "user.name", "Tests")
        self._git("add", "-A")
        self._git("commit", "-m", "seed")

    def _patch_current_repo(self) -> Any:
        return patch.multiple(
            "ops.scripts.release.release_post_commit_finalizer",
            release_source_tree_fingerprint=lambda _vault: "fp-current",
            git_commit=lambda _vault: "abc123",
        )

    def _write_authority_inputs(self, *, preflight_revision: str = "abc123") -> None:
        authority_specs = [
            (
                "build/release/release-auto-promotion-preflight.json",
                "release_auto_promotion_preflight",
                preflight_revision,
            ),
            (
                "build/release/release-run-manifest.json",
                "release_run_manifest",
                "abc123",
            ),
            (
                "build/release/release-auto-promotion-preseal.json",
                "release_auto_promotion_preflight",
                "abc123",
            ),
            (
                "build/release/release-sealed-run-manifest.json",
                "release_sealed_run_manifest",
                "abc123",
            ),
            (
                "build/release/release-auto-promotion-ready-manifest.json",
                "release_auto_promotion_ready_manifest",
                "old-revision",
            ),
        ]
        for rel_path, artifact_kind, revision in authority_specs:
            self._write_json(
                rel_path,
                {
                    "artifact_kind": artifact_kind,
                    "producer": "tests.authority",
                    "generated_at": "2026-05-23T12:00:00Z",
                    "source_revision": revision,
                    "source_tree_fingerprint": "fp-current",
                    "status": "pass",
                },
            )

    def test_revision_stale_authority_is_attention_with_owning_target(self) -> None:
        self._write_authority_inputs(preflight_revision="old-revision")
        self._init_clean_git()

        with self._patch_current_repo():
            report = build_report(self.vault, mode="verify", context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["blocker_class"], "authority_stale")
        self.assertEqual(report["owning_target"], "release-auto-promotion-preflight")
        self.assertEqual(report["minimal_next_target"], "release-auto-promotion-preflight")
        self.assertEqual(report["authority_inputs"][0]["issues"], ["source_revision_stale"])
        self.assertEqual(report["summary"]["authority_stale_count"], 1)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(write_report(self.vault, report).exists())

    def test_cli_strict_mode_fails_on_authority_attention(self) -> None:
        self._write_authority_inputs(preflight_revision="old-revision")
        self._init_clean_git()

        with self._patch_current_repo():
            default_exit_code = main(
                [
                    "--vault",
                    str(self.vault),
                    "--out",
                    "tmp/default-release-post-commit-finalization.json",
                ]
            )
        default_report_path = self.vault / "tmp/default-release-post-commit-finalization.json"
        default_report = json.loads(default_report_path.read_text(encoding="utf-8"))
        default_report_path.unlink()

        with self._patch_current_repo():
            strict_exit_code = main(
                [
                    "--vault",
                    str(self.vault),
                    "--out",
                    "tmp/strict-release-post-commit-finalization.json",
                    "--fail-on-attention",
                ]
            )

        strict_report = json.loads(
            (self.vault / "tmp/strict-release-post-commit-finalization.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(default_exit_code, 0)
        self.assertEqual(strict_exit_code, 1)
        self.assertEqual(default_report["status"], "attention")
        self.assertEqual(strict_report["status"], "attention")
        self.assertEqual(strict_report["minimal_next_target"], "release-auto-promotion-preflight")

    def test_source_tracked_drift_fails_and_returns_to_prepare(self) -> None:
        self._init_clean_git()
        (self.vault / "README.md").write_text("changed source\n", encoding="utf-8")

        with self._patch_current_repo():
            report = build_report(self.vault, mode="verify", context=fixed_context())

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["blocker_class"], "source_tree_changed")
        self.assertEqual(report["owning_target"], "release-source-ready-prepare")
        self.assertEqual(report["minimal_next_target"], "release-source-ready-prepare")
        self.assertIn("README.md", report["dirty_source_paths"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_cli_returns_nonzero_for_source_tracked_drift(self) -> None:
        self._init_clean_git()
        (self.vault / "README.md").write_text("changed source\n", encoding="utf-8")

        with self._patch_current_repo():
            exit_code = main(
                [
                    "--vault",
                    str(self.vault),
                    "--out",
                    "tmp/release-post-commit-finalization.json",
                ]
            )

        out_path = self.vault / "tmp/release-post-commit-finalization.json"
        report = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["minimal_next_target"], "release-source-ready-prepare")

    def test_clean_snapshot_identity_drift_fails_and_returns_to_prepare(self) -> None:
        self._write_authority_inputs()
        self._write_json(
            "tmp/release-post-commit-finalization.snapshot.json",
            {
                "source_revision": "old-revision",
                "source_tree_fingerprint_after": "old-fingerprint",
            },
        )
        self._init_clean_git()

        with self._patch_current_repo():
            report = build_report(
                self.vault,
                mode="verify",
                previous_path="tmp/release-post-commit-finalization.snapshot.json",
                context=fixed_context(),
            )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["blocker_class"], "source_tree_changed")
        self.assertEqual(report["dirty_source_paths"], [])
        self.assertEqual(
            report["changed_paths"],
            ["<source-revision>", "<source-tree-fingerprint>"],
        )
        self.assertTrue(report["summary"]["fingerprint_changed_since_snapshot"])
        self.assertTrue(report["summary"]["revision_changed_since_snapshot"])
        self.assertEqual(report["minimal_next_target"], "release-source-ready-prepare")

    def test_finalizer_does_not_require_final_auto_promotion_authority(self) -> None:
        self._write_authority_inputs()
        (self.vault / "build/release/release-auto-promotion-ready-manifest.json").unlink()
        self._init_clean_git()

        with self._patch_current_repo():
            report = build_report(self.vault, mode="verify", context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["blocker_class"], "none")
        self.assertNotIn(
            "release-auto-promotion-ready",
            {item["stage"] for item in report["authority_inputs"]},
        )

    def test_current_authority_status_failure_does_not_block_post_commit_currentness(
        self,
    ) -> None:
        self._write_authority_inputs()
        preflight_path = self.vault / "build/release/release-auto-promotion-preflight.json"
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        preflight["status"] = "fail"
        preflight_path.write_text(
            json.dumps(preflight, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._init_clean_git()

        with self._patch_current_repo():
            report = build_report(self.vault, mode="verify", context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["authority_inputs"][0]["status"], "fail")
        self.assertEqual(report["authority_inputs"][0]["issues"], [])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])


if __name__ == "__main__":
    unittest.main()
