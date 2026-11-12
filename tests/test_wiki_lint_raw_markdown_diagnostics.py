from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.eval.wiki_lint import lint
from ops.scripts.eval.wiki_lint_review_classification import classify_review_candidates
from tests.minimal_vault_runtime import seed_minimal_vault


class WikiLintRawMarkdownDiagnosticsTest(unittest.TestCase):
    def test_capture_review_is_advisory_even_without_a_source_page(self) -> None:
        from tests.test_raw_capture_review_runtime import SUMMARY, TITLE

        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            (vault / "raw" / "capture.md").write_text(
                f'---\ntitle: "{TITLE}"\nsource: "https://example.com/story"\n'
                'published: "unknown"\ncreated: "unknown"\n---\n\n' + SUMMARY,
            )
            report = lint(vault)
            candidates = [item for item in report["review_candidates"] if item["type"] == "raw_snapshot_capture_review"]
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["page"], "raw/capture.md")
            self.assertEqual(candidates[0]["detail"]["reasons"], ["raw_capture_summary_only"])
            self.assertFalse(any(item["type"] == "raw_snapshot_capture_review" for item in report["errors"] + report["warnings"]))
            classified = classify_review_candidates(candidates)[0]
            self.assertEqual(classified["primary_bucket"], "documentation_candidate")
            self.assertFalse(classified["refactor_candidate"])
            self.assertEqual(classified["suggested_action"], "review_source_capture_preserve_raw")

    def test_lint_surfaces_missing_raw_markdown_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "raw" / "snapshot.md").write_text(
                "# Snapshot: Demo\n- URL: https://example.com/demo\n",
                encoding="utf-8",
            )

            report = lint(vault)
            error_types = {issue["type"] for issue in report["errors"]}

            self.assertEqual(report["status"], "fail")
            self.assertIn("raw_markdown_missing_frontmatter", error_types)

    def test_lint_warns_for_replacement_char_in_raw_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "raw" / "snapshot.md").write_text(
                """---
title: "Demo"
source: "https://example.com/demo"
published: "unknown"
created: "unknown"
---

bad � text
""",
                encoding="utf-8",
            )

            report = lint(vault)
            warning_types = {issue["type"] for issue in report["warnings"]}

            self.assertIn("raw_markdown_replacement_char", warning_types)


if __name__ == "__main__":
    unittest.main()
