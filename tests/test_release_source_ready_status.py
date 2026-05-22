from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import pytest

from ops.scripts.release.release_source_ready_status import build_report


pytestmark = pytest.mark.public


class ReleaseSourceReadyStatusTests(unittest.TestCase):
    def test_status_uses_status_v2_axes_for_source_ready_without_machine_release(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            closeout = vault / "ops" / "reports" / "release-closeout-summary.json"
            closeout.parent.mkdir(parents=True)
            closeout.write_text(
                json.dumps(
                    {
                        "artifact_kind": "release_closeout_summary",
                        "status": "pass",
                        "checked_in_release_ready": True,
                        "machine_release_allowed": True,
                        "status_v2": {
                            "schema_version": 2,
                            "compatibility_status_value": "pass",
                            "status_axes": {
                                "release_authority_status": "conditional_pass",
                                "sealed_release_status": "unsealed_distribution_not_provided",
                            },
                            "blocker_reason_ids": ["machine_release_not_allowed"],
                        },
                    }
                ),
                encoding="utf-8",
            )

            report = build_report(vault)

            self.assertEqual(report["status"], "pass")
            self.assertTrue(report["source_ready"])
            self.assertFalse(report["machine_release_allowed"])
            self.assertEqual(report["release_authority_status"], "conditional_pass")
            self.assertEqual(report["sealed_release_status"], "unsealed_distribution_not_provided")
            self.assertEqual(
                report["authoritative_machine_release_target"],
                "release-evidence-closeout-sealed-check",
            )


if __name__ == "__main__":
    unittest.main()
