from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.release_risk_taxonomy_matrix import build_report, render_markdown, write_markdown, write_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.public


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-risk-taxonomy-matrix.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 6, 9, 0, tzinfo=dt.timezone.utc),
    )


class ReleaseRiskTaxonomyMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _taxonomy(self) -> dict:
        return json.loads((self.vault / "ops" / "policies" / "release-risk-taxonomy.json").read_text())

    def test_matrix_report_validates_and_mirrors_taxonomy_effects(self) -> None:
        report = build_report(self.vault, context=fixed_context())
        schema = load_schema(SCHEMA_PATH)

        self.assertEqual(validate_with_schema(report, schema), [])
        self.assertEqual(report["artifact_kind"], "release_risk_taxonomy_matrix")
        self.assertEqual(report["status"], "pass")

        taxonomy = self._taxonomy()
        rows = {row["code"]: row for row in report["matrix"]}
        self.assertEqual(set(rows), set(taxonomy["risks"]))
        for code, entry in taxonomy["risks"].items():
            with self.subTest(code=code):
                self.assertEqual(rows[code]["surface"], entry["surface"])
                for field, value in entry["effects"].items():
                    self.assertEqual(rows[code][field], value)

        self.assertEqual(report["summary"]["risk_code_count"], len(taxonomy["risks"]))
        self.assertGreater(report["summary"]["clean_lane_blocking_count"], 0)
        self.assertGreater(report["summary"]["learning_claim_blocking_count"], 0)
        self.assertGreater(report["summary"]["advisory_lifecycle_backlog_count"], 0)

    def test_write_report_and_markdown_emit_auditable_matrix(self) -> None:
        report = build_report(self.vault, context=fixed_context())

        json_path = write_report(self.vault, report)
        markdown_path = write_markdown(self.vault, report)

        self.assertTrue(json_path.exists())
        self.assertTrue(markdown_path.exists())
        markdown = markdown_path.read_text(encoding="utf-8")
        self.assertIn("| Risk code | Primary lane | Clean | Conditional | Learning | Advisory | Surface |", markdown)
        self.assertIn("release_risk_taxonomy_unregistered_code", markdown)
        self.assertIn("learning_blocked_by_review_required", markdown)
        self.assertEqual(render_markdown(report), markdown)


if __name__ == "__main__":
    unittest.main()
