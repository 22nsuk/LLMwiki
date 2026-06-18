from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.generated_artifact_converge_summary import (
    build_report,
    write_report,
)

pytestmark = pytest.mark.public


class GeneratedArtifactConvergeSummaryTests(unittest.TestCase):
    def test_after_summary_distinguishes_semantic_changes_from_envelope_churn(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            freshness = vault / "ops" / "reports" / "artifact-freshness-report.json"
            freshness.parent.mkdir(parents=True)
            freshness.write_text(
                json.dumps(
                    {
                        "artifact_kind": "artifact_freshness_report",
                        "generated_at": "2026-05-01T00:00:00Z",
                        "summary": {"schema_invalid_artifact_count": 0},
                        "artifact_records": [
                            {
                                "path": "ops/reports/example.json",
                                "currentness_status": "current",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            before = build_report(vault, phase="before")
            write_report(vault, before, "tmp/generated-artifact-converge-summary.before.json")
            freshness.write_text(
                json.dumps(
                    {
                        "artifact_kind": "artifact_freshness_report",
                        "generated_at": "2026-05-02T00:00:00Z",
                        "summary": {"schema_invalid_artifact_count": 1},
                        "artifact_records": [
                            {
                                "path": "ops/reports/example.json",
                                "currentness_status": "stale",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            after = build_report(vault, phase="after")
            by_target = {item["target"]: item for item in after["target_summaries"]}

            self.assertEqual(by_target["artifact-freshness"]["status"], "changed")
            self.assertEqual(
                by_target["artifact-freshness"]["semantic_changed_paths"],
                ["ops/reports/artifact-freshness-report.json"],
            )

    def test_generated_markdown_timestamp_churn_is_not_semantic_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            matrix = vault / "ops" / "reports" / "release-risk-taxonomy-matrix.md"
            matrix.parent.mkdir(parents=True)
            matrix.write_text(
                "# Release Risk Taxonomy Matrix\n\n"
                "- Generated at: 2026-05-01T00:00:00Z\n"
                "- Taxonomy: ops/policies/release-risk-taxonomy.json\n",
                encoding="utf-8",
            )

            before = build_report(vault, phase="before")
            write_report(vault, before, "tmp/generated-artifact-converge-summary.before.json")
            matrix.write_text(
                "# Release Risk Taxonomy Matrix\n\n"
                "- Generated at: 2026-05-02T00:00:00Z\n"
                "- Taxonomy: ops/policies/release-risk-taxonomy.json\n",
                encoding="utf-8",
            )

            after = build_report(vault, phase="after")
            by_target = {item["target"]: item for item in after["target_summaries"]}

            self.assertEqual(by_target["generated-artifact-index"]["status"], "noop")
            self.assertEqual(
                by_target["generated-artifact-index"]["change_classification"],
                "envelope_or_raw_only_changed",
            )
            self.assertEqual(by_target["generated-artifact-index"]["semantic_changed_paths"], [])
            self.assertEqual(
                by_target["generated-artifact-index"]["raw_changed_paths"],
                ["ops/reports/release-risk-taxonomy-matrix.md"],
            )
            matrix_digest = next(
                item
                for item in by_target["generated-artifact-index"]["path_digests"]
                if item["path"] == "ops/reports/release-risk-taxonomy-matrix.md"
            )
            self.assertEqual(matrix_digest["semantic_mode"], "markdown_without_generated_at")

    def test_nested_json_provenance_drift_is_semantic_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            freshness = vault / "ops" / "reports" / "artifact-freshness-report.json"
            freshness.parent.mkdir(parents=True)
            freshness.write_text(
                json.dumps(
                    {
                        "artifact_kind": "artifact_freshness_report",
                        "details": {"input_fingerprints": {"source": "before"}},
                    }
                ),
                encoding="utf-8",
            )

            before = build_report(vault, phase="before")
            write_report(vault, before, "tmp/generated-artifact-converge-summary.before.json")
            freshness.write_text(
                json.dumps(
                    {
                        "artifact_kind": "artifact_freshness_report",
                        "details": {"input_fingerprints": {"source": "after"}},
                    }
                ),
                encoding="utf-8",
            )

            after = build_report(vault, phase="after")
            by_target = {item["target"]: item for item in after["target_summaries"]}

            self.assertEqual(by_target["artifact-freshness"]["status"], "changed")
            self.assertEqual(
                by_target["artifact-freshness"]["semantic_changed_paths"],
                ["ops/reports/artifact-freshness-report.json"],
            )


if __name__ == "__main__":
    unittest.main()
