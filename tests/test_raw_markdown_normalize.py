from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import (
    RAW_MARKDOWN_NORMALIZATION_REPORT_SCHEMA_PATH,
)
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.registry.raw_markdown_normalize import build_report
from ops.scripts.registry.raw_markdown_runtime import normalize_raw_markdown_file

REPO_ROOT = Path(__file__).resolve().parents[1]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.UTC),
    )


class RawMarkdownNormalizeTest(unittest.TestCase):
    def test_normalizer_adds_frontmatter_and_required_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            raw_dir = vault / "raw"
            raw_dir.mkdir()
            path = raw_dir / "sample.md"
            path.write_text(
                """Title: Example Story

URL Source: https://example.com/2026/04/10/example-story

Markdown Content:
# Example Story

Body text.
""",
                encoding="utf-8",
            )

            result = normalize_raw_markdown_file(vault, path)

            self.assertTrue(result.changed)
            self.assertEqual(
                result.metadata,
                {
                    "title": "Example Story",
                    "source": "https://example.com/2026/04/10/example-story",
                    "published": "2026-04-10",
                    "created": "unknown",
                },
            )
            self.assertNotIn("Markdown Content:", result.text)
            self.assertTrue(result.text.startswith("---\n"))

    def test_normalizer_uses_unknown_when_dates_are_not_extractable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            raw_dir = vault / "raw"
            raw_dir.mkdir()
            path = raw_dir / "snapshot.md"
            path.write_text(
                """# Snapshot: Demo
- URL: https://github.com/example/demo/blob/main/README.md

## Key excerpts
- one
""",
                encoding="utf-8",
            )

            result = normalize_raw_markdown_file(vault, path)

            self.assertEqual(result.metadata["title"], "Snapshot: Demo")
            self.assertEqual(result.metadata["source"], "https://github.com/example/demo/blob/main/README.md")
            self.assertEqual(result.metadata["published"], "unknown")
            self.assertEqual(result.metadata["created"], "unknown")

    def test_normalizer_removes_transport_cookie_and_blob_noise(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            raw_dir = vault / "raw"
            raw_dir.mkdir()
            path = raw_dir / "iren.md"
            path.write_text(
                """Title: IREN Signs $9.7 Billion Agreement with Microsoft to Deploy AI Cloud Infrastructure

URL Source: https://iren.com/resources/blog/iren-signs97-billion-agreement-with-microsoft-to-deploy-ai-cloud-infrastructure

Markdown Content:
# IREN Signs $9.7 Billion Agreement with Microsoft to Deploy AI Cloud Infrastructure

[](https://www.cookiebot.com/en/what-is-behind-powered-by-cookiebot/)

This website uses cookies

Allow all Customize Allow selection Deny

1.   [Resources](https://iren.com/resources)

5.   IREN Signs $9.7 Billion Agreement with Microsoft to Deploy AI Cloud Infrastructure

# IREN Signs $9.7 Billion Agreement with Microsoft to Deploy AI Cloud Infrastructure

IREN - 11/3/2025

![Image](blob:http://localhost/123)

Body text.
""",
                encoding="utf-8",
            )

            result = normalize_raw_markdown_file(vault, path)

            self.assertEqual(
                result.removed_noise_classes,
                ["transport_header", "cookie_banner", "blob_localhost"],
            )
            self.assertNotIn("cookiebot.com", result.text)
            self.assertNotIn("blob:http://localhost", result.text)
            self.assertNotIn("Allow all Customize Allow selection Deny", result.text)
            self.assertIn("Body text.", result.text)

    def test_normalizer_leaves_compliant_file_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            raw_dir = vault / "raw"
            raw_dir.mkdir()
            path = raw_dir / "clean.md"
            text = """---
title: "Already Clean"
source: "https://example.com/clean"
published: "unknown"
created: "unknown"
---

# Already Clean

Body text.
"""
            path.write_text(text, encoding="utf-8")

            result = normalize_raw_markdown_file(vault, path)

            self.assertFalse(result.changed)
            self.assertEqual(result.text, text)

    def test_normalizer_flags_replacement_char_for_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            raw_dir = vault / "raw"
            raw_dir.mkdir()
            path = raw_dir / "replacement.md"
            path.write_text(
                """---
title: "World Oil Transit Chokepoints"
source: "https://www.eia.gov/international/content/analysis/special_topics/World_Oil_Transit_Chokepoints/"
published:
created: "2026-04-13"
---

**Last Updated:** March 3, 2026 | [Notes](#endnotes) |

bad � text
""",
                encoding="utf-8",
            )

            result = normalize_raw_markdown_file(vault, path)

            self.assertTrue(result.manual_review_required)
            self.assertEqual(result.manual_review_reasons, ["replacement_char"])
            self.assertIn("�", result.text)
            self.assertEqual(result.metadata["published"], "2026-03-03")

    def test_build_report_in_write_mode_writes_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            (vault / "ops" / "policies").mkdir(parents=True)
            (vault / "ops" / "schemas").mkdir(parents=True)
            (vault / "raw").mkdir()
            repo_root = Path(__file__).resolve().parents[1]
            (vault / "ops" / "policies" / "wiki-maintainer-policy.yaml").write_text(
                (repo_root / "ops" / "policies" / "wiki-maintainer-policy.yaml").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            (vault / "ops" / "schemas" / "wiki-maintainer-policy.schema.json").write_text(
                (repo_root / "ops" / "schemas" / "wiki-maintainer-policy.schema.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            target = vault / "raw" / "sample.md"
            target.write_text(
                "# Snapshot: Demo\n- URL: https://github.com/example/demo/blob/main/README.md\n",
                encoding="utf-8",
            )

            report = build_report(vault, vault / "raw", write=True, context=fixed_context())

            self.assertEqual(report["stats"]["file_count"], 1)
            self.assertEqual(report["stats"]["changed_count"], 1)
            self.assertEqual(report["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(report["$schema"], RAW_MARKDOWN_NORMALIZATION_REPORT_SCHEMA_PATH)
            schema = load_schema(REPO_ROOT / RAW_MARKDOWN_NORMALIZATION_REPORT_SCHEMA_PATH)
            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertTrue(target.read_text(encoding="utf-8").startswith("---\n"))


if __name__ == "__main__":
    unittest.main()
