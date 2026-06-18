from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.policy_runtime import load_policy, required_sections_from_policy
from ops.scripts.eval.wiki_page_runtime import (
    discover_pages,
    heading_body,
    open_question_severity_counts,
    required_sections_for_page,
    source_trace_item_count,
)
from tests.minimal_vault_runtime import seed_minimal_vault


class WikiPageRuntimeTest(unittest.TestCase):
    def test_discover_pages_reports_duplicate_stems_across_corpora(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            (vault / "wiki").mkdir(parents=True)
            (vault / "system").mkdir(parents=True)
            (vault / "wiki" / "concept--shared.md").write_text("# wiki\n", encoding="utf-8")
            (vault / "system" / "concept--shared.md").write_text("# system\n", encoding="utf-8")
            (vault / "wiki" / "source--unique.md").write_text("# source\n", encoding="utf-8")

            pages, duplicates = discover_pages(vault)

            self.assertIn("source--unique", pages)
            self.assertIn("concept--shared", duplicates)
            self.assertEqual(
                {path.as_posix() for path in duplicates["concept--shared"]},
                {
                    (vault / "wiki" / "concept--shared.md").as_posix(),
                    (vault / "system" / "concept--shared.md").as_posix(),
                },
            )

    def test_heading_body_stops_at_next_peer_heading(self) -> None:
        text = """# Page

## Summary
line one
### Detail
line two
## Related pages
- [[index]]
"""

        body = heading_body(text, "Summary")
        self.assertIsNotNone(body)
        self.assertIn("line one", body)
        self.assertIn("### Detail", body)
        self.assertNotIn("## Related pages", body)

    def test_source_trace_item_count_supports_refs_and_plain_bullets(self) -> None:
        self.assertEqual(
            source_trace_item_count("- `raw/a.pdf`\n- `raw/b.pdf`\n"),
            2,
        )
        self.assertEqual(
            source_trace_item_count("- imported from notes\n- verified manually\n"),
            2,
        )

    def test_open_question_severity_counts_only_high_and_medium(self) -> None:
        counts = open_question_severity_counts(
            "- [high] blocker\n- [medium] follow-up\n- [low] ignored\n- plain bullet\n"
        )
        self.assertEqual(counts, {"high": 1, "medium": 1})

    def test_required_sections_for_page_prefers_special_page_rules_before_prefix_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, _ = load_policy(vault)
            required_sections = required_sections_from_policy(policy)

            index_sections = required_sections_for_page(
                vault,
                vault / "wiki" / "index.md",
                "index",
                required_sections,
            )
            source_sections = required_sections_for_page(
                vault,
                vault / "wiki" / "source--fake.md",
                "source--fake",
                required_sections,
            )

            self.assertIn("How to use this wiki", index_sections)
            self.assertIn("Title", source_sections)
            self.assertNotEqual(index_sections, source_sections)


if __name__ == "__main__":
    unittest.main()
