from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.eval.wiki_eval import evaluate
from tests.minimal_vault_runtime import seed_minimal_vault


def _fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.UTC),
    )


def _page_results(report: dict, page_path: Path) -> dict[str, bool]:
    page_report = next(item for item in report["pages"] if item["page"] == page_path.as_posix())
    return {result["eval"]: result["pass"] for result in page_report["results"]}


class WikiEvalRuntimeTest(unittest.TestCase):
    def test_evaluate_passes_on_minimal_vault_and_reports_page_specific_evals(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            report = evaluate(vault, context=_fixed_context())

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(report["total_score"], report["max_score"])

            source_results = _page_results(report, vault / "wiki" / "source--fake.md")
            synthesis_results = _page_results(report, vault / "wiki" / "synthesis--fake.md")

            self.assertTrue(source_results["frontmatter_contract"])
            self.assertTrue(source_results["source_page_substance"])
            self.assertTrue(synthesis_results["decisionability"])

    def test_evaluate_flags_missing_decisionability_on_synthesis_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            synthesis_path = vault / "wiki" / "synthesis--fake.md"
            synthesis_path.write_text(
                synthesis_path.read_text(encoding="utf-8").replace("## Decision / takeaway\n- x\n", ""),
                encoding="utf-8",
            )

            report = evaluate(vault)

            self.assertEqual(report["status"], "fail")
            synthesis_results = _page_results(report, synthesis_path)
            self.assertFalse(synthesis_results["decisionability"])

    def test_evaluate_short_circuits_on_duplicate_stems(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            duplicate_path = vault / "system" / "source--fake.md"
            duplicate_path.write_text(
                """---
title: "Duplicate"
page_type: "source"
corpus: "system"
aliases:
  - "source--fake"
tags:
  - "corpus/system"
  - "type/source"
---

# Duplicate
""",
                encoding="utf-8",
            )

            report = evaluate(vault, context=_fixed_context())

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(report["max_score"], 0)
            self.assertEqual(report["pages"], [])
            self.assertEqual(report["errors"][0]["type"], "duplicate_page_stem")
            self.assertIn("source--fake", report["errors"][0]["detail"])


if __name__ == "__main__":
    unittest.main()
