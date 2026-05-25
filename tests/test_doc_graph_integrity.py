from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.doc_graph_integrity import build_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 25, 12, 0, tzinfo=dt.UTC),
    )


class DocGraphIntegrityTests(unittest.TestCase):
    def test_doc_graph_requires_allowlisted_orphans_and_existing_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            (vault / "docs").mkdir()
            (vault / "ops").mkdir()
            (vault / "README.md").write_text("[Docs](docs/README.md)\n", encoding="utf-8")
            (vault / "docs" / "README.md").write_text("[Topic](topic.md)\n", encoding="utf-8")
            (vault / "docs" / "topic.md").write_text("topic\n", encoding="utf-8")
            (vault / "docs" / "orphan.md").write_text("orphan\n", encoding="utf-8")
            allowlist = {
                "$schema": "ops/schemas/doc-graph-integrity.schema.json",
                "allowed_orphans": [
                    {
                        "path": "docs/orphan.md",
                        "retained_reason": "standalone operator note",
                    }
                ],
            }
            (vault / "ops" / "doc-graph-orphan-allowlist.json").write_text(
                json.dumps(allowlist) + "\n",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

        schema = load_schema("ops/schemas/doc-graph-integrity.schema.json")
        self.assertEqual(validate_with_schema(allowlist, schema), [])
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["missing_link_count"], 0)
        self.assertEqual(report["summary"]["unallowed_orphan_count"], 0)
        self.assertEqual(validate_with_schema(report, schema), [])


if __name__ == "__main__":
    unittest.main()
