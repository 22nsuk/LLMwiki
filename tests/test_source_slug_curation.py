from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import (
    SOURCE_SLUG_CURATION_MANIFEST_SCHEMA_PATH,
    SOURCE_SLUG_CURATION_VALIDATION_REPORT_SCHEMA_PATH,
)
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.source_slug_curation import scaffold_manifest, validate_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]


class SourceSlugCurationTest(unittest.TestCase):
    def test_scaffold_manifest_reads_matrix_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "wiki").mkdir()
            (temp_path / "wiki" / "source--legacy-cyber-security-analysis-2026-04-12.md").write_text(
                """---
title: "Legacy Cyber Security Analysis"
page_type: "source"
corpus: "wiki"
aliases:
  - "source--legacy-cyber-security-analysis-2026-04-12"
tags:
  - "corpus/wiki"
  - "type/source"
---

# source--legacy-cyber-security-analysis-2026-04-12

## Title
Legacy Cyber Security Analysis

## Summary
Cyber security and statecraft analysis.

## Why it matters
This older source can bridge a cyber statecraft synthesis family.
""",
                encoding="utf-8",
            )
            matrix_path = temp_path / "matrix.json"
            matrix_path.write_text(
                json.dumps(
                    {
                        "matrix": [
                            {
                                "registry_id": "W-100",
                                "title": "Demo title",
                                "raw_path": "raw/demo.md",
                                "source_page": "wiki/source--demo-title-2026-04-21.md",
                                "proposed_action": "create_new_synthesis_family",
                                "target": "cyber-statecraft-and-ai-security",
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            manifest = scaffold_manifest(matrix_path, vault=temp_path)

            self.assertEqual(manifest["source_count"], 1)
            self.assertEqual(manifest["$schema"], SOURCE_SLUG_CURATION_MANIFEST_SCHEMA_PATH)
            schema = load_schema(REPO_ROOT / SOURCE_SLUG_CURATION_MANIFEST_SCHEMA_PATH)
            self.assertEqual(validate_with_schema(manifest, schema), [])
            self.assertEqual(manifest["entries"][0]["current_slug"], "demo-title")
            self.assertEqual(manifest["entries"][0]["date_suffix"], "2026-04-21")
            self.assertEqual(manifest["entries"][0]["target"], "cyber-statecraft-and-ai-security")
            self.assertEqual(
                manifest["entries"][0]["family_bridge_candidates"][0]["source_stem"],
                "source--legacy-cyber-security-analysis-2026-04-12",
            )

    def test_validate_manifest_rejects_missing_and_duplicate_curated_slugs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "registry_id": "W-100",
                                "source_page": "wiki/source--demo-title-2026-04-21.md",
                                "date_suffix": "2026-04-21",
                                "curated_english_slug": "",
                            },
                            {
                                "registry_id": "W-101",
                                "source_page": "wiki/source--other-title-2026-04-21.md",
                                "date_suffix": "2026-04-21",
                                "curated_english_slug": "same-slug",
                            },
                            {
                                "registry_id": "W-102",
                                "source_page": "wiki/source--third-title-2026-04-21.md",
                                "date_suffix": "2026-04-21",
                                "curated_english_slug": "same-slug",
                            },
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            report = validate_manifest(manifest_path)

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["$schema"], SOURCE_SLUG_CURATION_VALIDATION_REPORT_SCHEMA_PATH)
            schema = load_schema(REPO_ROOT / SOURCE_SLUG_CURATION_VALIDATION_REPORT_SCHEMA_PATH)
            self.assertEqual(validate_with_schema(report, schema), [])
            error_types = {item["type"] for item in report["errors"]}
            self.assertIn("missing_curated_english_slug", error_types)
            self.assertIn("duplicate_curated_english_slug", error_types)

    def test_scaffold_manifest_uses_runtime_context_for_generated_at(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            matrix_path = temp_path / "matrix.json"
            matrix_path.write_text(
                json.dumps(
                    {
                        "matrix": [
                            {
                                "registry_id": "W-100",
                                "title": "Demo title",
                                "raw_path": "raw/demo.md",
                                "source_page": "wiki/source--demo-title-2026-04-21.md",
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            manifest = scaffold_manifest(
                matrix_path,
                context=RuntimeContext(
                    display_timezone=dt.timezone.utc,
                    clock=lambda: dt.datetime(2026, 4, 25, 5, 6, 7, tzinfo=dt.timezone.utc),
                ),
            )

            self.assertEqual(manifest["generated_at"], "2026-04-25T05:06:07Z")


if __name__ == "__main__":
    unittest.main()
