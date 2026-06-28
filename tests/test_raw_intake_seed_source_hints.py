from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.registry.raw_intake_seed_source_hints import (
    build_report,
    main as seed_source_hints_main,
)
from tests.cli_test_runtime import invoke_cli_main
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "raw-intake-seed-source-hints-report.schema.json"


def write_seed_source(path: Path, *, include_hints: bool = False) -> None:
    hint_sections = ""
    if include_hints:
        hint_sections = """

## Why this is source-only for now
이미 설명됨.

## What future cluster would absorb this
이미 설명됨.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
title: "Lonely Source"
page_type: "source"
corpus: "wiki"
source_type: "news-snapshot"
primary_concept: "source-only"
primary_lens: "US AI regulatory federalism route가 안정화되면 승격한다."
authority_class: "source_only_seed"
route_decision: "keep_source_only_seed"
route_subtype: "us-ai-regulatory-federalism"
aliases:
  - "source--lonely"
tags:
  - "corpus/wiki"
  - "type/source"
---

# source--lonely

## Title
Lonely Source

## Source
- `raw/source.md`

## Summary
summary
{hint_sections}
## Related pages
- [[index]]

## Source trace
- `raw/source.md`
""",
        encoding="utf-8",
    )


class RawIntakeSeedSourceHintsTests(unittest.TestCase):
    def test_check_reports_missing_seed_source_hints_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            source_path = vault / "wiki" / "source--lonely.md"
            write_seed_source(source_path)

            report = build_report(vault)

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["mode"], "check")
            self.assertEqual(report["summary"]["seed_source_missing_hint_count"], 1)
            self.assertEqual(report["summary"]["written_count"], 0)
            candidate = report["candidates"][0]
            self.assertEqual(candidate["page"], "wiki/source--lonely.md")
            self.assertEqual(
                candidate["missing_sections"],
                [
                    "Why this is source-only for now",
                    "What future cluster would absorb this",
                ],
            )
            self.assertFalse(candidate["written"])
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_write_inserts_missing_sections_before_navigation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            source_path = vault / "wiki" / "source--lonely.md"
            write_seed_source(source_path)

            report = build_report(vault, write=True)
            updated = source_path.read_text(encoding="utf-8")
            followup = build_report(vault)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["mode"], "write")
            self.assertEqual(report["summary"]["seed_source_missing_hint_count"], 0)
            self.assertEqual(report["summary"]["written_count"], 1)
            self.assertIn("## Why this is source-only for now", updated)
            self.assertLess(
                updated.index("## What future cluster would absorb this"),
                updated.index("## Related pages"),
            )
            self.assertIn("[[index]]", updated)
            self.assertEqual(followup["status"], "pass")
            self.assertEqual(followup["summary"]["seed_source_missing_hint_count"], 0)
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_stable_concept_linker_skips_seed_hint_backfill(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            write_seed_source(vault / "wiki" / "source--lonely.md")
            (vault / "wiki" / "concept--linked.md").write_text(
                """---
title: "Linked"
page_type: "concept"
corpus: "wiki"
aliases:
  - "concept--linked"
tags:
  - "corpus/wiki"
  - "type/concept"
---

# concept--linked

## Summary
See [[source--lonely]].
""",
                encoding="utf-8",
            )

            report = build_report(vault)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["candidates"], [])
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_cli_writes_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)
            write_seed_source(vault / "wiki" / "source--lonely.md", include_hints=True)

            completed = invoke_cli_main(
                seed_source_hints_main,
                [
                    "--vault",
                    str(vault),
                    "--out",
                    "reports/raw-intake/seed-source-hints.json",
                ],
                cwd=launcher,
            )

            self.assertEqual(completed.exit_code, 0, msg=completed.stderr or completed.stdout)
            report_path = vault / "reports" / "raw-intake" / "seed-source-hints.json"
            self.assertTrue(report_path.exists())
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["$schema"],
                "ops/schemas/raw-intake-seed-source-hints-report.schema.json",
            )
            self.assertEqual(payload["status"], "pass")

    def test_cli_write_fail_on_missing_rechecks_after_backfill(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)
            write_seed_source(vault / "wiki" / "source--lonely.md")

            completed = invoke_cli_main(
                seed_source_hints_main,
                [
                    "--vault",
                    str(vault),
                    "--out",
                    "reports/raw-intake/seed-source-hints.json",
                    "--write",
                    "--fail-on-missing",
                ],
                cwd=launcher,
            )

            self.assertEqual(completed.exit_code, 0, msg=completed.stderr or completed.stdout)
            report_path = vault / "reports" / "raw-intake" / "seed-source-hints.json"
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["summary"]["seed_source_missing_hint_count"], 0)
            self.assertEqual(payload["summary"]["written_count"], 1)
            self.assertEqual(validate_with_schema(payload, load_schema(SCHEMA_PATH)), [])


if __name__ == "__main__":
    unittest.main()
