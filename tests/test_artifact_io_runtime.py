from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.artifact_io_runtime import (
    ReportWriterKernelRequest,
    SchemaBackedReportWriteRequest,
    describe_output_file,
    load_optional_json_object,
    load_optional_json_object_with_diagnostics,
    promote_schema_validated_json,
    read_json_object,
    serialized_json,
    write_report_with_kernel,
    write_schema_backed_report,
    write_schema_validated_json,
)


class ArtifactIoRuntimeTests(unittest.TestCase):
    def test_read_json_object_requires_object_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "payload.json"
            path.write_text('["not", "object"]', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "JSON root must be an object"):
                read_json_object(path)

    def test_load_optional_json_object_suppresses_missing_and_invalid_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            missing = root / "missing.json"
            invalid = root / "invalid.json"
            invalid.write_text("{not-json", encoding="utf-8")

            self.assertEqual(load_optional_json_object(missing), {})
            self.assertEqual(load_optional_json_object(invalid), {})

    def test_load_optional_json_object_with_diagnostics_distinguishes_failure_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            missing = root / "missing.json"
            invalid = root / "invalid.json"
            invalid.write_text("{not-json", encoding="utf-8")
            wrong_root = root / "wrong-root.json"
            wrong_root.write_text('["not", "object"]', encoding="utf-8")

            payload, diagnostics = load_optional_json_object_with_diagnostics(missing)
            self.assertEqual(payload, {})
            self.assertTrue(diagnostics["missing"])
            self.assertEqual(diagnostics["status"], "missing")

            payload, diagnostics = load_optional_json_object_with_diagnostics(invalid)
            self.assertEqual(payload, {})
            self.assertTrue(diagnostics["decode_error"])
            self.assertEqual(diagnostics["status"], "decode_error")

            payload, diagnostics = load_optional_json_object_with_diagnostics(wrong_root)
            self.assertEqual(payload, {})
            self.assertTrue(diagnostics["type_error"])
            self.assertEqual(diagnostics["status"], "type_error")

    def test_describe_output_file_reports_exists_size_and_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            existing = root / "report.json"
            existing.write_text('{"ok": true}\n', encoding="utf-8")
            missing = root / "missing.json"

            description = describe_output_file(existing)
            self.assertTrue(description["exists"])
            self.assertGreater(description["size_bytes"], 0)
            self.assertEqual(len(description["sha256"]), 64)

            self.assertEqual(
                describe_output_file(missing),
                {"exists": False, "size_bytes": 0, "sha256": ""},
            )

    def test_write_schema_validated_json_validates_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "report.json"
            schema = {
                "type": "object",
                "required": ["status"],
                "additionalProperties": False,
                "properties": {"status": {"const": "pass"}},
            }

            with self.assertRaisesRegex(ValueError, "missing required property 'status'"):
                write_schema_validated_json(
                    destination,
                    {},
                    schema,
                    context="artifact test failed",
                )

            self.assertFalse(destination.exists())
            write_schema_validated_json(
                destination,
                {"status": "pass"},
                schema,
                context="artifact test failed",
            )

            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), {"status": "pass"})

    def test_write_schema_validated_json_syncs_mtime_to_generated_at(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "report.json"
            schema = {
                "type": "object",
                "required": ["generated_at", "status"],
                "additionalProperties": False,
                "properties": {
                    "generated_at": {"type": "string"},
                    "status": {"const": "pass"},
                },
            }

            write_schema_validated_json(
                destination,
                {"generated_at": "2026-04-29T08:00:00Z", "status": "pass"},
                schema,
                context="artifact test failed",
            )

            modified_at = dt.datetime.fromtimestamp(destination.stat().st_mtime, tz=dt.UTC)
            self.assertEqual(
                modified_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "2026-04-29T08:00:00Z",
            )

    def test_write_schema_backed_report_resolves_repo_output_and_adds_newline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            schema_path = vault / "schema.json"
            schema_path.write_text(
                json.dumps(
                    {
                        "type": "object",
                        "required": ["status"],
                        "additionalProperties": False,
                        "properties": {"status": {"const": "pass"}},
                    }
                ),
                encoding="utf-8",
            )

            destination = write_schema_backed_report(
                SchemaBackedReportWriteRequest(
                    vault=vault,
                    payload={"status": "pass"},
                    schema_path="schema.json",
                    out_path=None,
                    default_relative_path="ops/reports/example.json",
                )
            )

            self.assertEqual(destination, vault / "ops" / "reports" / "example.json")
            self.assertEqual(destination.read_text(encoding="utf-8")[-1], "\n")

    def test_write_report_with_kernel_rejects_missing_canonical_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            schema_path = vault / "schema.json"
            schema_path.write_text(
                json.dumps(
                    {
                        "type": "object",
                        "required": ["status"],
                        "additionalProperties": False,
                        "properties": {"status": {"const": "pass"}},
                    }
                ),
                encoding="utf-8",
            )

            destination = vault / "ops" / "reports" / "example.json"
            with self.assertRaisesRegex(ValueError, "canonical report envelope missing fields"):
                write_report_with_kernel(
                    ReportWriterKernelRequest(
                        vault=vault,
                        payload={"status": "pass"},
                        schema_path="schema.json",
                        out_path=None,
                        default_relative_path="ops/reports/example.json",
                        artifact_kind="example_report",
                        producer="tests.example",
                    )
                )

            self.assertFalse(destination.exists())

    def test_write_report_with_kernel_validates_canonical_envelope_and_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            schema_path = vault / "schema.json"
            schema_path.write_text(
                json.dumps(
                    {
                        "type": "object",
                        "required": [
                            "$schema",
                            "artifact_kind",
                            "generated_at",
                            "producer",
                            "source_command",
                            "source_revision",
                            "source_tree_fingerprint",
                            "input_fingerprints",
                            "schema_version",
                            "artifact_status",
                            "retention_policy",
                            "encoding",
                            "currentness",
                            "status",
                        ],
                        "additionalProperties": False,
                        "properties": {
                            "$schema": {"const": "schema.json"},
                            "artifact_kind": {"const": "example_report"},
                            "generated_at": {"type": "string"},
                            "producer": {"const": "tests.example"},
                            "source_command": {"type": "string"},
                            "source_revision": {"type": "string"},
                            "source_tree_fingerprint": {"type": "string"},
                            "input_fingerprints": {"type": "object"},
                            "schema_version": {"type": "integer"},
                            "artifact_status": {"const": "current"},
                            "retention_policy": {"const": "canonical_report"},
                            "encoding": {"const": "utf-8"},
                            "currentness": {"type": "object"},
                            "status": {"const": "pass"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            payload = {
                "$schema": "schema.json",
                "artifact_kind": "example_report",
                "generated_at": "2026-04-29T08:00:00Z",
                "producer": "tests.example",
                "source_command": "pytest",
                "source_revision": "unknown",
                "source_tree_fingerprint": "source-tree",
                "input_fingerprints": {"policy": "policy-digest"},
                "schema_version": 1,
                "artifact_status": "current",
                "retention_policy": "canonical_report",
                "encoding": "utf-8",
                "currentness": {
                    "status": "current",
                    "checked_at": "2026-04-29T08:00:00Z",
                },
                "status": "pass",
            }

            destination = write_report_with_kernel(
                ReportWriterKernelRequest(
                    vault=vault,
                    payload=payload,
                    schema_path="schema.json",
                    out_path=None,
                    default_relative_path="ops/reports/example.json",
                    artifact_kind="example_report",
                    producer="tests.example",
                )
            )

            self.assertEqual(destination, vault / "ops" / "reports" / "example.json")
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), payload)
            self.assertEqual(destination.read_text(encoding="utf-8")[-1], "\n")

    def test_promote_schema_validated_json_validates_candidate_before_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            schema_path = root / "schema.json"
            schema_path.write_text(
                json.dumps(
                    {
                        "type": "object",
                        "required": ["$schema", "artifact_kind", "producer", "status"],
                        "additionalProperties": False,
                        "properties": {
                            "$schema": {"const": "schema.json"},
                            "artifact_kind": {"const": "example_report"},
                            "producer": {"const": "tests.example"},
                            "status": {"const": "pass"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            destination = root / "canonical.json"
            destination.write_text('{"status": "old"}', encoding="utf-8")
            invalid = root / "invalid.json"
            invalid.write_text(
                json.dumps(
                    {
                        "$schema": "schema.json",
                        "artifact_kind": "example_report",
                        "producer": "tests.example",
                        "status": "fail",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "expected constant 'pass'"):
                promote_schema_validated_json(
                    root,
                    candidate_path=invalid,
                    destination_path=destination,
                    context="candidate promotion failed",
                )

            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), {"status": "old"})

            valid = root / "valid.json"
            valid.write_text(
                json.dumps(
                    {
                        "$schema": "schema.json",
                        "artifact_kind": "example_report",
                        "producer": "tests.example",
                        "status": "pass",
                    }
                ),
                encoding="utf-8",
            )

            promote_schema_validated_json(
                root,
                candidate_path=valid,
                destination_path=destination,
                expected_artifact_kind="example_report",
                expected_producer="tests.example",
                context="candidate promotion failed",
            )

            self.assertEqual(json.loads(destination.read_text(encoding="utf-8"))["status"], "pass")

    def test_promote_schema_validated_json_can_preserve_semantic_noop_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            schema_path = root / "schema.json"
            schema_path.write_text(
                json.dumps(
                    {
                        "type": "object",
                        "required": [
                            "$schema",
                            "artifact_kind",
                            "producer",
                            "generated_at",
                            "source_revision",
                            "source_tree_fingerprint",
                            "input_fingerprints",
                            "currentness",
                            "surfaces",
                        ],
                        "additionalProperties": False,
                        "properties": {
                            "$schema": {"const": "schema.json"},
                            "artifact_kind": {"const": "script_output_surfaces"},
                            "producer": {"const": "ops.scripts.script_output_surfaces"},
                            "generated_at": {"type": "string"},
                            "source_revision": {"type": "string"},
                            "source_tree_fingerprint": {"type": "string"},
                            "input_fingerprints": {"type": "object"},
                            "currentness": {"type": "object"},
                            "surfaces": {"type": "array"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            destination = root / "canonical.json"
            existing = {
                "$schema": "schema.json",
                "artifact_kind": "script_output_surfaces",
                "producer": "ops.scripts.script_output_surfaces",
                "generated_at": "2026-05-28T00:00:00Z",
                "source_revision": "old",
                "source_tree_fingerprint": "old-fp",
                "input_fingerprints": {"source": "old"},
                "currentness": {"status": "current", "checked_at": "2026-05-28T00:00:00Z"},
                "surfaces": [{"path": "ops/scripts/example.py"}],
            }
            destination.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
            before_text = destination.read_text(encoding="utf-8")
            candidate = root / "candidate.json"
            candidate.write_text(
                json.dumps(
                    {
                        **existing,
                        "generated_at": "2026-05-29T00:00:00Z",
                        "source_revision": "new",
                        "source_tree_fingerprint": "new-fp",
                        "input_fingerprints": {"source": "new"},
                        "currentness": {
                            "status": "current",
                            "checked_at": "2026-05-29T00:00:00Z",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            promoted = promote_schema_validated_json(
                root,
                candidate_path=candidate,
                destination_path=destination,
                expected_artifact_kind="script_output_surfaces",
                expected_producer="ops.scripts.script_output_surfaces",
                context="candidate promotion failed",
                preserve_existing_on_semantic_match=True,
            )

            self.assertEqual(promoted, destination)
            self.assertEqual(destination.read_text(encoding="utf-8"), before_text)

    def test_promote_schema_validated_json_replaces_invalid_semantic_noop_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            schema_path = root / "schema.json"
            schema_path.write_text(
                json.dumps(
                    {
                        "type": "object",
                        "required": ["$schema", "generated_at", "surfaces"],
                        "additionalProperties": False,
                        "properties": {
                            "$schema": {"const": "schema.json"},
                            "generated_at": {"type": "string"},
                            "surfaces": {"type": "array"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            destination = root / "canonical.json"
            destination.write_text(
                json.dumps({"$schema": "schema.json", "surfaces": []}) + "\n",
                encoding="utf-8",
            )
            candidate = root / "candidate.json"
            candidate.write_text(
                json.dumps(
                    {
                        "$schema": "schema.json",
                        "generated_at": "2026-05-29T00:00:00Z",
                        "surfaces": [],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            promote_schema_validated_json(
                root,
                candidate_path=candidate,
                destination_path=destination,
                context="candidate promotion failed",
                preserve_existing_on_semantic_match=True,
            )

            self.assertEqual(
                json.loads(destination.read_text(encoding="utf-8"))["generated_at"],
                "2026-05-29T00:00:00Z",
            )

    def test_serialized_json_can_add_trailing_newline(self) -> None:
        self.assertEqual(serialized_json({"ok": True}, trailing_newline=True)[-1], "\n")


if __name__ == "__main__":
    unittest.main()
