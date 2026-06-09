from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.generated_artifact_semantic_digest import (
    JSON_ARTIFACT_KIND_POINTER_MODE,
    JSON_TOP_LEVEL_ENVELOPE_MODE,
    MARKDOWN_GENERATED_AT_MODE,
    semantic_file_digest,
)

pytestmark = pytest.mark.public


class GeneratedArtifactSemanticDigestTests(unittest.TestCase):
    def test_top_level_envelope_churn_does_not_change_json_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.json"
            path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "sample",
                        "generated_at": "2026-05-01T00:00:00Z",
                        "input_fingerprints": {"clock": "before"},
                        "payload": {"source_tree_fingerprint": "stable"},
                    }
                ),
                encoding="utf-8",
            )
            mode, before_digest = semantic_file_digest(path)
            path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "sample",
                        "generated_at": "2026-05-02T00:00:00Z",
                        "input_fingerprints": {"clock": "after"},
                        "payload": {"source_tree_fingerprint": "stable"},
                    }
                ),
                encoding="utf-8",
            )

            after_mode, after_digest = semantic_file_digest(path)

            self.assertEqual(mode, JSON_TOP_LEVEL_ENVELOPE_MODE)
            self.assertEqual(after_mode, JSON_TOP_LEVEL_ENVELOPE_MODE)
            self.assertEqual(before_digest, after_digest)

    def test_nested_provenance_named_like_envelope_still_changes_json_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.json"
            path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "sample",
                        "payload": {"source_tree_fingerprint": "before"},
                    }
                ),
                encoding="utf-8",
            )
            _mode, before_digest = semantic_file_digest(path)
            path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "sample",
                        "payload": {"source_tree_fingerprint": "after"},
                    }
                ),
                encoding="utf-8",
            )

            _after_mode, after_digest = semantic_file_digest(path)

            self.assertNotEqual(before_digest, after_digest)

    def test_list_contained_provenance_named_like_envelope_changes_json_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.json"
            path.write_text(
                json.dumps({"items": [{"generated_at": "2026-05-01T00:00:00Z"}]}),
                encoding="utf-8",
            )
            _mode, before_digest = semantic_file_digest(path)
            path.write_text(
                json.dumps({"items": [{"generated_at": "2026-05-02T00:00:00Z"}]}),
                encoding="utf-8",
            )

            _after_mode, after_digest = semantic_file_digest(path)

            self.assertNotEqual(before_digest, after_digest)

    def test_artifact_kind_declared_clock_pointer_does_not_change_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.json"
            path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "artifact_freshness_report",
                        "artifact_records": [
                            {
                                "path": "ops/reports/example.json",
                                "generated_at": "2026-05-01T00:00:00Z",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            mode, before_digest = semantic_file_digest(path)
            path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "artifact_freshness_report",
                        "artifact_records": [
                            {
                                "path": "ops/reports/example.json",
                                "generated_at": "2026-05-02T00:00:00Z",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            after_mode, after_digest = semantic_file_digest(path)

            self.assertEqual(mode, JSON_ARTIFACT_KIND_POINTER_MODE)
            self.assertEqual(after_mode, JSON_ARTIFACT_KIND_POINTER_MODE)
            self.assertEqual(before_digest, after_digest)

    def test_artifact_kind_declared_pointer_keeps_other_nested_drift_semantic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.json"
            path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "artifact_freshness_report",
                        "artifact_records": [
                            {
                                "path": "ops/reports/example.json",
                                "currentness": {"checked_at": "before"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            _mode, before_digest = semantic_file_digest(path)
            path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "artifact_freshness_report",
                        "artifact_records": [
                            {
                                "path": "ops/reports/example.json",
                                "currentness": {"checked_at": "after"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            _after_mode, after_digest = semantic_file_digest(path)

            self.assertNotEqual(before_digest, after_digest)

    def test_artifact_freshness_self_reference_record_drift_does_not_change_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.json"
            path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "artifact_freshness_report",
                        "summary": {"stale_artifact_count": 1},
                        "artifact_records": [
                            {
                                "path": "ops/reports/release-closeout-finality-attestation.json",
                                "currentness_status": "stale",
                                "source_tree_fingerprint_status": "stale",
                            },
                            {
                                "path": "ops/reports/non-self.json",
                                "currentness_status": "current",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            _mode, before_digest = semantic_file_digest(path)
            path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "artifact_freshness_report",
                        "summary": {"stale_artifact_count": 0},
                        "artifact_records": [
                            {
                                "path": "ops/reports/release-closeout-finality-attestation.json",
                                "currentness_status": "current",
                                "source_tree_fingerprint_status": "current",
                            },
                            {
                                "path": "ops/reports/non-self.json",
                                "currentness_status": "current",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            _after_mode, after_digest = semantic_file_digest(path)

            self.assertEqual(before_digest, after_digest)

    def test_markdown_generated_at_line_churn_does_not_change_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.md"
            path.write_text("# Report\n\n- Generated at: 2026-05-01T00:00:00Z\n- Status: pass\n", encoding="utf-8")
            mode, before_digest = semantic_file_digest(path)
            path.write_text("# Report\n\n- Generated at: 2026-05-02T00:00:00Z\n- Status: pass\n", encoding="utf-8")

            after_mode, after_digest = semantic_file_digest(path)

            self.assertEqual(mode, MARKDOWN_GENERATED_AT_MODE)
            self.assertEqual(after_mode, MARKDOWN_GENERATED_AT_MODE)
            self.assertEqual(before_digest, after_digest)


if __name__ == "__main__":
    unittest.main()
