from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.eval.wiki_lint import lint
from tests.minimal_vault_runtime import seed_minimal_vault


class WikiLintRawMarkdownDiagnosticsTest(unittest.TestCase):
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
