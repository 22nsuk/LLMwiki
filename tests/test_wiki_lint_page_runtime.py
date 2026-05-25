from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.policy_runtime import load_policy, required_sections_from_policy
from ops.scripts.raw_registry_runtime import load_registry_source_trace_resolution_map
from ops.scripts.wiki_lint_page_runtime import PageLintContext, lint_page, orphan_issues
from ops.scripts.wiki_lint_registry_runtime import registry_review_exempt_paths
from ops.scripts.wiki_page_runtime import discover_pages
from ops.scripts.wikilink_runtime import build_page_lookup

from tests.minimal_vault_runtime import seed_minimal_vault


class WikiLintPageRuntimeTest(unittest.TestCase):
    def test_lint_page_reports_source_trace_and_open_question_issues(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            page = vault / "wiki" / "concept--probe.md"
            page.write_text(
                """---
title: "Probe"
page_type: "concept"
corpus: "wiki"
aliases:
  - "concept--probe"
tags:
  - "corpus/wiki"
  - "type/concept"
canonical: true
---

# Probe

## Summary
x

## Why it matters here
x

## Main body
x

## Related pages
- [[index]]

## Open questions
- [high] unresolved blocker

## Source trace
- `raw/missing*.pdf`
""",
                encoding="utf-8",
            )

            policy, _ = load_policy(vault)
            required_sections = required_sections_from_policy(policy)
            pages, _ = discover_pages(vault)
            page_lookup = build_page_lookup(vault, pages)
            context = PageLintContext(
                vault=vault,
                path=page,
                stem=page.stem,
                text=page.read_text(encoding="utf-8"),
                page_lookup=page_lookup,
                required_headings=required_sections["concept--"],
                lint_thresholds=policy["lint_thresholds"],
                readiness_gate=policy["readiness_gate"],
                frontmatter_contract=policy["frontmatter_contract"],
                schema_versioning=policy.get("schema_versioning"),
                source_trace_resolution_map=load_registry_source_trace_resolution_map(
                    vault, policy["registry_contract"]
                ),
                refactor_triggers=policy["refactor_triggers"],
                system_refactor_policy=policy["system_refactor_policy"],
                registry_review_exempt=registry_review_exempt_paths(policy["registry_contract"]),
            )

            result = lint_page(context)
            issue_types = {issue["type"] for issue, _ in result.issues}
            self.assertIn("wildcard_source_trace", issue_types)
            self.assertIn("source_trace_target_missing", issue_types)
            self.assertIn("high_severity_open_question_overflow", issue_types)
            self.assertEqual(result.frontmatter["title"], "Probe")
            self.assertIn("index", result.page_links)

    def test_orphan_issues_flags_only_unlinked_non_index_pages(self) -> None:
        pages = {
            "index": Path("wiki/index.md"),
            "concept--probe": Path("wiki/concept--probe.md"),
            "source--probe": Path("wiki/source--probe.md"),
        }
        issues = orphan_issues(
            {
                "index": 0,
                "concept--probe": 0,
                "source--probe": 1,
            },
            pages,
            "warn",
        )

        self.assertEqual(len(issues), 1)
        issue, severity = issues[0]
        self.assertEqual(severity, "warn")
        self.assertEqual(issue["type"], "orphan_page")
        self.assertEqual(issue["page"], "wiki/concept--probe.md")


if __name__ == "__main__":
    unittest.main()
