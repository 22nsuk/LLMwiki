from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ops.scripts.core.policy_runtime import load_policy, required_sections_from_policy
from ops.scripts.eval.wiki_page_runtime import (
    discover_pages,
    open_question_severity_counts,
    required_sections_for_page,
    section_body,
    source_trace_item_count,
)
from ops.scripts.eval.wiki_quality_runtime import (
    broken_wikilinks,
    has_placeholder,
    missing_required_sections,
    open_question_budget_status,
    resolved_wikilink_targets,
    source_trace_targets_missing,
)
from ops.scripts.eval.wiki_snapshot_runtime import build_wiki_runtime_snapshot
from ops.scripts.eval.wikilink_runtime import build_page_lookup
from tests import minimal_vault_runtime
from tests.minimal_vault_runtime import seed_minimal_vault


class WikiRuntimeHelpersTest(unittest.TestCase):
    def test_live_policy_reuses_parsed_policy_until_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            policy_path = Path(temp_dir) / "wiki-maintainer-policy.yaml"
            policy_path.write_text(
                minimal_vault_runtime.POLICY_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            parse_calls = 0
            original_safe_load = minimal_vault_runtime.yaml.safe_load

            def counted_safe_load(text: str) -> object:
                nonlocal parse_calls
                parse_calls += 1
                return original_safe_load(text)

            with (
                mock.patch.object(minimal_vault_runtime, "POLICY_PATH", policy_path),
                mock.patch.object(
                    minimal_vault_runtime.yaml,
                    "safe_load",
                    side_effect=counted_safe_load,
                ),
            ):
                minimal_vault_runtime.clear_live_policy_cache()
                try:
                    vault = Path(temp_dir) / "vault"
                    vault.mkdir()
                    seed_minimal_vault(vault)
                    self.assertEqual(parse_calls, 1)

                    first_policy = minimal_vault_runtime.live_policy()
                    second_policy = minimal_vault_runtime.live_policy()
                    self.assertEqual(first_policy, second_policy)
                    self.assertEqual(parse_calls, 1)

                    policy_path.write_text(
                        policy_path.read_text(encoding="utf-8") + "\n# cache invalidation\n",
                        encoding="utf-8",
                    )

                    minimal_vault_runtime.live_policy()
                    self.assertEqual(parse_calls, 2)
                finally:
                    minimal_vault_runtime.clear_live_policy_cache()

    def test_discover_pages_collects_duplicates_by_stem(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            duplicate_text = (
                "---\n"
                "title: \"Duplicate\"\n"
                "page_type: \"source\"\n"
                "corpus: \"wiki\"\n"
                "aliases:\n"
                "  - \"duplicate\"\n"
                "tags:\n"
                "  - \"corpus/wiki\"\n"
                "---\n\n"
                "# duplicate\n"
            )
            (vault / "wiki" / "source--dup.md").write_text(duplicate_text, encoding="utf-8")
            (vault / "system" / "source--dup.md").write_text(
                duplicate_text.replace('corpus: "wiki"', 'corpus: "system"'),
                encoding="utf-8",
            )

            pages, duplicate_stems = discover_pages(vault)

            self.assertIn("source--dup", pages)
            self.assertIn("source--dup", duplicate_stems)
            self.assertEqual(
                sorted(path.relative_to(vault).as_posix() for path in duplicate_stems["source--dup"]),
                ["system/source--dup.md", "wiki/source--dup.md"],
            )

    def test_required_sections_for_page_uses_special_page_and_prefix_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, _ = load_policy(vault)
            required_sections = required_sections_from_policy(policy)

            system_log_sections = required_sections_for_page(
                vault,
                vault / "system" / "system-log.md",
                "system-log",
                required_sections,
            )
            source_sections = required_sections_for_page(
                vault,
                vault / "wiki" / "source--fake.md",
                "source--fake",
                required_sections,
            )

            self.assertEqual(system_log_sections, ["Related pages", "Source trace"])
            self.assertIn("Key points", source_sections)
            self.assertIn("Limitations / caveats", source_sections)

    def test_section_body_and_source_trace_item_count_cover_both_trace_shapes(self) -> None:
        text = (
            "## Summary\n"
            "- x\n"
            "## Source trace\n"
            "- `raw/one.pdf`\n"
            "- `raw/two.pdf`\n"
            "## Related pages\n"
            "- [[index]]\n"
        )

        self.assertEqual(section_body(text, "Source trace"), "\n- `raw/one.pdf`\n- `raw/two.pdf`\n")
        self.assertIsNone(section_body(text, "Missing"))
        self.assertEqual(source_trace_item_count(section_body(text, "Source trace")), 2)
        self.assertEqual(source_trace_item_count("- raw one\n- raw two"), 2)

    def test_open_question_helpers_count_only_tagged_high_and_medium_items(self) -> None:
        open_questions = (
            "\n"
            "- [high] unresolved contradiction\n"
            "- [medium] needs more evidence\n"
            "- [HIGH] another blocker\n"
            "- untagged note stays advisory only\n"
        )

        self.assertEqual(
            open_question_severity_counts(open_questions),
            {
                "high": 2,
                "medium": 1,
            },
        )
        self.assertEqual(
            open_question_budget_status(
                open_questions,
                {
                    "max_high_severity_open_questions": 1,
                    "max_medium_severity_open_questions": 0,
                    "allow_warn_for_medium_question_overflow": True,
                },
            ),
            {
                "counts": {
                    "high": 2,
                    "medium": 1,
                },
                "high_overflow": True,
                "medium_overflow": True,
                "high_max": 1,
                "medium_max": 0,
                "medium_overflow_severity": "warn",
            },
        )

    def test_open_question_budget_status_uses_policy_toggle_for_medium_overflow(self) -> None:
        open_questions = (
            "\n"
            "- [medium] question one\n"
            "- [medium] question two\n"
            "- [medium] question three\n"
            "- [medium] question four\n"
        )

        self.assertEqual(
            open_question_budget_status(
                open_questions,
                {
                    "max_high_severity_open_questions": 0,
                    "max_medium_severity_open_questions": 3,
                    "allow_warn_for_medium_question_overflow": True,
                },
            ),
            {
                "counts": {
                    "high": 0,
                    "medium": 4,
                },
                "high_overflow": False,
                "medium_overflow": True,
                "high_max": 0,
                "medium_max": 3,
                "medium_overflow_severity": "warn",
            },
        )
        self.assertEqual(
            open_question_budget_status(
                open_questions,
                {
                    "max_high_severity_open_questions": 0,
                    "max_medium_severity_open_questions": 3,
                    "allow_warn_for_medium_question_overflow": False,
                },
            ),
            {
                "counts": {
                    "high": 0,
                    "medium": 4,
                },
                "high_overflow": False,
                "medium_overflow": True,
                "high_max": 0,
                "medium_max": 3,
                "medium_overflow_severity": "fail",
            },
        )

    def test_wikilink_and_placeholder_quality_helpers_share_page_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            pages, _ = discover_pages(vault)
            page_lookup = build_page_lookup(vault, pages)
            text = (
                "## Related pages\n"
                "- [[source--fake]]\n"
                "- [[AGENTS]]\n"
                "- [[missing-page]]\n"
                "TODO fill later\n"
            )

            self.assertEqual(
                resolved_wikilink_targets(text, page_lookup),
                {"source--fake"},
            )
            self.assertEqual(
                broken_wikilinks(text, page_lookup, {"AGENTS"}),
                ["missing-page"],
            )
            self.assertTrue(has_placeholder(text))
            self.assertEqual(
                missing_required_sections("## Summary\n- ok\n", ["Summary", "Related pages"]),
                ["Related pages"],
            )

    def test_source_trace_targets_missing_uses_shared_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            self.assertEqual(
                source_trace_targets_missing(
                    vault,
                    "- `raw/fake.pdf`\n- `raw/missing.pdf`\n",
                ),
                [
                    {
                        "ref": "raw/missing.pdf",
                        "resolved_path": "raw/missing.pdf",
                    }
                ],
            )

    def test_runtime_snapshot_reuses_page_text_frontmatter_links_and_resolution_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, _ = load_policy(vault)

            snapshot = build_wiki_runtime_snapshot(
                vault,
                registry_contract=policy["registry_contract"],
            )

            self.assertIn("source--fake", snapshot.pages)
            self.assertIn("source--fake", snapshot.texts)
            self.assertEqual(snapshot.frontmatter_errors, {})
            self.assertEqual(snapshot.frontmatters["source--fake"]["title"], "Fake Source")
            self.assertIn("index", snapshot.related_links["source--fake"])
            self.assertEqual(snapshot.source_trace_resolution_map["raw/fake.pdf"][0], "raw/fake.pdf")


if __name__ == "__main__":
    unittest.main()
