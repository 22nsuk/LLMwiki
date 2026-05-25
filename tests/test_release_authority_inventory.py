from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.release_authority_inventory import build_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 25, 12, 0, tzinfo=dt.UTC),
    )


class ReleaseAuthorityInventoryTests(unittest.TestCase):
    def test_inventory_is_not_a_release_verdict_and_marks_stale_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            (vault / "build" / "release").mkdir(parents=True)
            (vault / "build" / "release" / "release-run-manifest.json").write_text(
                '{"status":"pass","source_revision":"old-revision"}\n',
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

        self.assertEqual(report["authority_claim"], "none_inventory_only")
        self.assertEqual(report["summary"]["authority_manifest_count"], 3)
        self.assertIn("run_manifest", report["stale_artifacts"])
        self.assertEqual(report["status"], "attention")
        self.assertEqual(
            validate_with_schema(report, load_schema("ops/schemas/release-authority-inventory.schema.json")),
            [],
        )


if __name__ == "__main__":
    unittest.main()
