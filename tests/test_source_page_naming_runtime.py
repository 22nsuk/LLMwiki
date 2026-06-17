from __future__ import annotations

import unittest

from ops.scripts.core.source_page_naming_runtime import (
    source_slug_validation_detail,
    source_stem_slug_and_date,
)


class SourcePageNamingRuntimeTest(unittest.TestCase):
    def test_source_stem_slug_and_date_splits_date_suffix(self) -> None:
        self.assertEqual(
            source_stem_slug_and_date("source--white-house-anthropic-mythos-response-2026-04-21"),
            ("white-house-anthropic-mythos-response", "2026-04-21"),
        )
        self.assertEqual(
            source_stem_slug_and_date("source--meta-harness"),
            ("meta-harness", None),
        )

    def test_source_slug_validation_accepts_ascii_summary_slug(self) -> None:
        detail = source_slug_validation_detail(
            "source--white-house-anthropic-mythos-response-2026-04-21",
            {
                "ascii_summary_slug_pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$",
                "disallowed_slug_substrings": ["intake-w-"],
            },
        )
        self.assertIsNone(detail)

    def test_source_slug_validation_rejects_registry_first_slug(self) -> None:
        detail = source_slug_validation_detail(
            "source--middle-east-energy-intake-w-225-2026-04-21",
            {
                "ascii_summary_slug_pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$",
                "disallowed_slug_substrings": ["intake-w-"],
            },
        )
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertIn("slug_contains_disallowed_substring", detail["violations"])


if __name__ == "__main__":
    unittest.main()
