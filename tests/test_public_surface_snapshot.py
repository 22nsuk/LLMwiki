from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.public.public_surface_policy import (
    PUBLIC_INCLUDE_FILES,
    PUBLIC_INCLUDE_PREFIXES,
)
from ops.scripts.public.public_surface_snapshot import build_report

pytestmark = [pytest.mark.public, pytest.mark.report_contract, pytest.mark.report_contract_core]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 25, 12, 0, tzinfo=dt.UTC),
    )


class PublicSurfaceSnapshotTests(unittest.TestCase):
    def test_snapshot_counts_public_policy_include_surface_without_requiring_private_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            for rel_path in PUBLIC_INCLUDE_FILES:
                path = vault / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x\n", encoding="utf-8")
            for prefix in PUBLIC_INCLUDE_PREFIXES:
                root = vault / prefix
                root.mkdir(parents=True, exist_ok=True)
                (root / "sample.txt").write_text("x\n", encoding="utf-8")
            (vault / "external-reports").mkdir()
            (vault / "raw").mkdir()

            report = build_report(vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["missing_include_file_count"], 0)
        self.assertEqual(report["summary"]["missing_include_prefix_count"], 0)
        self.assertIn(
            {"prefix": "external-reports/", "present": True},
            report["excluded_prefixes"],
        )
        self.assertEqual(
            validate_with_schema(
                report,
                load_schema("ops/schemas/public-surface-snapshot.schema.json"),
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
