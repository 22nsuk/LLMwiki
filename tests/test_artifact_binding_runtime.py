from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.artifact_binding_runtime import (
    CONTENT_BINDING_MODE,
    MARKDOWN_CONTENT_BINDING_MODE,
    REVISION_BINDING_MODE,
    binding_file_digest,
)

pytestmark = pytest.mark.public


def _content_binding(path: Path) -> tuple[str, str]:
    return binding_file_digest(path, binding_mode=CONTENT_BINDING_MODE)


class ArtifactBindingRuntimeTests(unittest.TestCase):
    def test_top_level_envelope_churn_does_not_change_json_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.json"
            path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "sample",
                        "generated_at": "2026-05-01T00:00:00Z",
                        "source_revision": "before-revision",
                        "source_tree_fingerprint": "same-tree",
                        "input_fingerprints": {"source": "same"},
                        "payload": {"source_tree_fingerprint": "stable"},
                    }
                ),
                encoding="utf-8",
            )
            mode, before_digest = _content_binding(path)
            path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "sample",
                        "generated_at": "2026-05-02T00:00:00Z",
                        "source_revision": "after-revision",
                        "source_tree_fingerprint": "same-tree",
                        "input_fingerprints": {"source": "same"},
                        "payload": {"source_tree_fingerprint": "stable"},
                    }
                ),
                encoding="utf-8",
            )

            after_mode, after_digest = _content_binding(path)

            self.assertEqual(mode, "json_content_binding")
            self.assertEqual(after_mode, "json_content_binding")
            self.assertEqual(before_digest, after_digest)

    def test_content_binding_changes_with_source_tree_or_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.json"
            path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "sample",
                        "source_revision": "same-revision",
                        "source_tree_fingerprint": "before-tree",
                        "input_fingerprints": {"source": "before"},
                        "payload": {"status": "pass"},
                    }
                ),
                encoding="utf-8",
            )
            _mode, before_digest = binding_file_digest(
                path, binding_mode=CONTENT_BINDING_MODE
            )
            path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "sample",
                        "source_revision": "same-revision",
                        "source_tree_fingerprint": "after-tree",
                        "input_fingerprints": {"source": "after"},
                        "payload": {"status": "pass"},
                    }
                ),
                encoding="utf-8",
            )
            _mode, after_digest = binding_file_digest(
                path, binding_mode=CONTENT_BINDING_MODE
            )

            self.assertNotEqual(before_digest, after_digest)

    def test_revision_binding_changes_when_only_revision_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.json"
            path.write_text(
                json.dumps({"source_revision": "before", "payload": "same"}),
                encoding="utf-8",
            )
            _mode, before_digest = binding_file_digest(
                path, binding_mode=REVISION_BINDING_MODE
            )
            path.write_text(
                json.dumps({"source_revision": "after", "payload": "same"}),
                encoding="utf-8",
            )
            _mode, after_digest = binding_file_digest(
                path, binding_mode=REVISION_BINDING_MODE
            )

            self.assertNotEqual(before_digest, after_digest)

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
            _mode, before_digest = _content_binding(path)
            path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "sample",
                        "payload": {"source_tree_fingerprint": "after"},
                    }
                ),
                encoding="utf-8",
            )

            _after_mode, after_digest = _content_binding(path)

            self.assertNotEqual(before_digest, after_digest)

    def test_list_contained_provenance_named_like_envelope_changes_json_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.json"
            path.write_text(
                json.dumps({"items": [{"generated_at": "2026-05-01T00:00:00Z"}]}),
                encoding="utf-8",
            )
            _mode, before_digest = _content_binding(path)
            path.write_text(
                json.dumps({"items": [{"generated_at": "2026-05-02T00:00:00Z"}]}),
                encoding="utf-8",
            )

            _after_mode, after_digest = _content_binding(path)

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
            mode, before_digest = _content_binding(path)
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

            after_mode, after_digest = _content_binding(path)

            self.assertEqual(mode, "json_content_binding_and_artifact_kind_declared_clock_fields")
            self.assertEqual(after_mode, "json_content_binding_and_artifact_kind_declared_clock_fields")
            self.assertEqual(before_digest, after_digest)

    def test_artifact_kind_declared_pointer_keeps_other_nested_drift_bound(self) -> None:
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
            _mode, before_digest = _content_binding(path)
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

            _after_mode, after_digest = _content_binding(path)

            self.assertNotEqual(before_digest, after_digest)

    def test_artifact_freshness_record_drift_changes_digest_without_self_reference_exception(self) -> None:
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
            _mode, before_digest = _content_binding(path)
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

            _after_mode, after_digest = _content_binding(path)

            self.assertNotEqual(before_digest, after_digest)

    def test_markdown_generated_at_line_churn_does_not_change_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.md"
            path.write_text("# Report\n\n- Generated at: 2026-05-01T00:00:00Z\n- Status: pass\n", encoding="utf-8")
            mode, before_digest = _content_binding(path)
            path.write_text("# Report\n\n- Generated at: 2026-05-02T00:00:00Z\n- Status: pass\n", encoding="utf-8")

            after_mode, after_digest = _content_binding(path)

            self.assertEqual(mode, MARKDOWN_CONTENT_BINDING_MODE)
            self.assertEqual(after_mode, MARKDOWN_CONTENT_BINDING_MODE)
            self.assertEqual(before_digest, after_digest)


if __name__ == "__main__":
    unittest.main()
