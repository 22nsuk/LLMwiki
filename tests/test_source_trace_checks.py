from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest

from tests.minimal_vault_runtime import seed_open_question_smoke_vault
from ops.scripts.policy_runtime import load_policy
from ops.scripts.wiki_eval import evaluate
from ops.scripts.wiki_lint import lint
from ops.scripts.wiki_snapshot_runtime import build_wiki_runtime_snapshot
from tests.vault_test_runtime import lint_and_evaluate_with_shared_snapshot

pytestmark = pytest.mark.slow


class SourceTraceChecksTest(unittest.TestCase):
    def test_wiki_lint_and_eval_surface_missing_source_trace_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "vault"
            root.mkdir()
            seed_open_question_smoke_vault(root, "raw/does-not-exist.pdf")

            lint_report, eval_report = lint_and_evaluate_with_shared_snapshot(root)
            page_map = {page["page"]: page for page in eval_report["pages"]}
            source_page = page_map[(root / "wiki" / "source--fake.md").as_posix()]
            eval_results = {result["eval"]: result["pass"] for result in source_page["results"]}

            self.assertEqual(lint_report["status"], "fail")
            self.assertIn(
                "source_trace_target_missing",
                {issue["type"] for issue in lint_report["errors"]},
            )
            self.assertEqual(eval_report["status"], "fail")
            self.assertFalse(eval_results["source_trace_targets_exist"])

    def test_release_archive_profile_allows_manifest_excluded_source_trace_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "vault"
            root.mkdir()
            seed_open_question_smoke_vault(root, "runs/run-1/promotion/evidence.json")

            policy, _ = load_policy(root)
            snapshot = build_wiki_runtime_snapshot(root, registry_contract=policy["registry_contract"])
            strict_lint_report = lint(root, snapshot=snapshot)
            release_lint_report = lint(root, snapshot=snapshot, release_archive_profile=True)
            release_eval_report = evaluate(root, snapshot=snapshot, release_archive_profile=True)
            page_map = {page["page"]: page for page in release_eval_report["pages"]}
            source_page = page_map[(root / "wiki" / "source--fake.md").as_posix()]
            eval_results = {result["eval"]: result["pass"] for result in source_page["results"]}
            target_result = next(
                result
                for result in source_page["results"]
                if result["eval"] == "source_trace_targets_exist"
            )

            self.assertIn(
                "source_trace_target_missing",
                {issue["type"] for issue in strict_lint_report["errors"]},
            )
            self.assertNotIn(
                "source_trace_target_missing",
                {issue["type"] for issue in release_lint_report["errors"]},
            )
            self.assertTrue(eval_results["source_trace_targets_exist"])
            self.assertEqual(
                target_result["detail"]["classified_missing_targets"][0]["classification"],
                "missing_export_excluded_bound",
            )
            self.assertTrue(
                target_result["detail"]["classified_missing_targets"][0]["profile_allows_missing"]
            )

    def test_release_archive_profile_blocks_unbound_export_excluded_source_trace_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "vault"
            root.mkdir()
            seed_open_question_smoke_vault(root, "tmp/local-only.json")

            policy, _ = load_policy(root)
            snapshot = build_wiki_runtime_snapshot(root, registry_contract=policy["registry_contract"])
            release_lint_report = lint(root, snapshot=snapshot, release_archive_profile=True)
            release_eval_report = evaluate(root, snapshot=snapshot, release_archive_profile=True)
            page_map = {page["page"]: page for page in release_eval_report["pages"]}
            source_page = page_map[(root / "wiki" / "source--fake.md").as_posix()]
            target_result = next(
                result
                for result in source_page["results"]
                if result["eval"] == "source_trace_targets_exist"
            )

            self.assertIn(
                "source_trace_target_missing",
                {issue["type"] for issue in release_lint_report["errors"]},
            )
            self.assertFalse(target_result["pass"])
            self.assertEqual(
                target_result["detail"]["blocking_missing_targets"][0]["classification"],
                "missing_export_excluded_unbound",
            )


if __name__ == "__main__":
    unittest.main()
