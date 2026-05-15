from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.sbom_readiness_gate_runtime import build_gate_report, write_gate_report
from tests.minimal_vault_runtime import seed_minimal_vault


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 4, 15, 12, 0, tzinfo=dt.timezone.utc),
    )


class SbomReadinessGateRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_mapping(self, payload: dict) -> None:
        (self.vault / "ops" / "reports" / "sbom-export-mapping.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def test_gate_passes_when_mapping_is_ready(self) -> None:
        self._write_mapping(
            {
                "status": "pass",
                "provenance_summary": {
                    "locked_package_count": 2,
                    "locked_dependency_edge_count": 1,
                },
                "sbom_readiness": {"full_mapping_ready": True},
                "surface_summary": {"public_subset_of_release": True},
            }
        )

        report = build_gate_report(self.vault, context=fixed_context())
        destination = write_gate_report(self.vault, report)
        persisted = json.loads(destination.read_text(encoding="utf-8"))

        self.assertEqual(persisted["status"], "pass")
        self.assertTrue(next(c["pass"] for c in persisted["checks"] if c["rule"] == "locked_dependency_graph_observed"))

    def test_gate_fails_when_mapping_status_is_not_pass(self) -> None:
        self._write_mapping(
            {
                "status": "warn",
                "sbom_readiness": {"full_mapping_ready": True},
                "surface_summary": {"public_subset_of_release": True},
            }
        )

        report = build_gate_report(self.vault, context=fixed_context())
        self.assertEqual(report["status"], "fail")
        self.assertFalse(next(c["pass"] for c in report["checks"] if c["rule"] == "mapping_report_status_pass"))

    def test_gate_fails_when_full_mapping_ready_is_false(self) -> None:
        self._write_mapping(
            {
                "status": "pass",
                "sbom_readiness": {"full_mapping_ready": False},
                "surface_summary": {"public_subset_of_release": True},
            }
        )

        report = build_gate_report(self.vault, context=fixed_context())
        self.assertEqual(report["status"], "fail")
        self.assertFalse(next(c["pass"] for c in report["checks"] if c["rule"] == "full_mapping_ready"))

    def test_gate_fails_when_public_export_is_not_release_subset(self) -> None:
        self._write_mapping(
            {
                "status": "pass",
                "sbom_readiness": {"full_mapping_ready": True},
                "surface_summary": {"public_subset_of_release": False},
            }
        )

        report = build_gate_report(self.vault, context=fixed_context())
        self.assertEqual(report["status"], "fail")
        self.assertFalse(
            next(
                c["pass"]
                for c in report["checks"]
                if c["rule"] == "public_export_subset_of_release_manifest"
            )
        )

    def test_gate_fails_when_mapping_report_is_missing(self) -> None:
        report = build_gate_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "fail")
        self.assertFalse(next(c["pass"] for c in report["checks"] if c["rule"] == "sbom_mapping_report_exists"))


if __name__ == "__main__":
    unittest.main()
