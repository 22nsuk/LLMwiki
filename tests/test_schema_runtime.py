from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.schema_constants_runtime import CYCLONEDX_16_SCHEMA_URI
from ops.scripts.core.schema_runtime import (
    load_schema,
    load_schema_with_vault_override,
    validate_or_raise,
    validate_with_schema,
)


class SchemaRuntimeTest(unittest.TestCase):
    def test_load_schema_with_vault_override_uses_bundled_schema_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            schema = load_schema_with_vault_override(
                Path(temp_dir),
                "ops/schemas/structural-complexity-budget-report.schema.json",
            )

            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(schema["title"], "LLM Wiki Structural Complexity Budget Report")

    def test_load_schema_with_vault_override_prefers_vault_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            schema_path = vault / "ops" / "schemas" / "example.schema.json"
            schema_path.parent.mkdir(parents=True)
            schema_path.write_text(
                json.dumps({"type": "object", "required": ["from_override"]}),
                encoding="utf-8",
            )

            self.assertEqual(
                load_schema_with_vault_override(vault, "ops/schemas/example.schema.json"),
                {"type": "object", "required": ["from_override"]},
            )

    def test_load_schema_with_vault_override_resolves_local_uri_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            schema_path = vault / "ops" / "schemas" / "cyclonedx-1.6.schema.json"
            schema_path.parent.mkdir(parents=True)
            schema_path.write_text(
                json.dumps({"type": "object", "required": ["from_override"]}),
                encoding="utf-8",
            )

            self.assertEqual(
                load_schema_with_vault_override(vault, CYCLONEDX_16_SCHEMA_URI),
                {"type": "object", "required": ["from_override"]},
            )

    def test_load_schema_resolves_cyclonedx_external_uri_alias(self) -> None:
        schema = load_schema(CYCLONEDX_16_SCHEMA_URI)

        self.assertEqual(schema["title"], "LLM Wiki CycloneDX 1.6 JSON SBOM Subset")

    def test_validate_with_schema_resolves_cyclonedx_ref_locally(self) -> None:
        missing_local_dependency_graph = {
            "$schema": CYCLONEDX_16_SCHEMA_URI,
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "serialNumber": "urn:uuid:00000000-0000-4000-8000-000000000001",
            "version": 1,
            "metadata": {
                "timestamp": "2026-04-20T12:00:00Z",
                "component": {
                    "type": "application",
                    "bom-ref": "pkg:generic/sample@0.1.0",
                    "name": "sample",
                    "version": "0.1.0",
                    "purl": "pkg:generic/sample@0.1.0",
                },
                "tools": {"components": []},
                "properties": [],
            },
            "components": [],
        }

        self.assertEqual(
            validate_with_schema(
                missing_local_dependency_graph,
                {"$ref": CYCLONEDX_16_SCHEMA_URI},
            ),
            ["$: missing required property 'dependencies'"],
        )

    def test_load_schema_with_vault_override_does_not_fallback_from_invalid_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            schema_path = vault / "ops" / "schemas" / "structural-complexity-budget-report.schema.json"
            schema_path.parent.mkdir(parents=True)
            schema_path.write_text("{not-json", encoding="utf-8")

            with self.assertRaises(json.JSONDecodeError):
                load_schema_with_vault_override(
                    vault,
                    "ops/schemas/structural-complexity-budget-report.schema.json",
                )

    def test_validate_or_raise_wraps_formatted_errors_with_context(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "fixture schema validation failed: \\$: missing required property 'name'",
        ):
            validate_or_raise(
                {},
                {"type": "object", "required": ["name"]},
                context="fixture schema validation failed",
            )

    def test_validate_with_schema_reports_unexpected_properties(self) -> None:
        self.assertEqual(
            validate_with_schema(
                {"extra": True},
                {"type": "object", "additionalProperties": False},
            ),
            ["$: unexpected property 'extra'"],
        )

    def test_validate_with_schema_formats_common_json_schema_errors(self) -> None:
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "mode": {"enum": ["fast", "safe"]},
                "items": {"type": "array", "minItems": 2},
                "labels": {"type": "object", "minProperties": 1},
                "kind": {"const": "fixture"},
                "count": {"minimum": 1},
                "variant": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "number"},
                    ]
                },
            },
        }

        self.assertEqual(validate_with_schema({}, schema), ["$: missing required property 'name'"])
        self.assertEqual(validate_with_schema({"name": 1}, schema), ["$.name: expected string"])
        self.assertEqual(
            validate_with_schema({"name": "x", "mode": "slow"}, schema),
            ["$.mode: expected one of ['fast', 'safe']"],
        )
        self.assertEqual(
            validate_with_schema({"name": "x", "items": []}, schema),
            ["$.items: expected at least 2 item(s)"],
        )
        self.assertEqual(
            validate_with_schema({"name": "x", "labels": {}}, schema),
            ["$.labels: expected at least 1 propert(ies)"],
        )
        self.assertEqual(
            validate_with_schema({"name": "x", "kind": "other"}, schema),
            ["$.kind: expected constant 'fixture'"],
        )
        self.assertEqual(
            validate_with_schema({"name": "x", "count": 0}, schema),
            ["$.count: expected at least 1"],
        )
        self.assertEqual(
            validate_with_schema({"name": "x", "variant": []}, schema),
            ["$.variant: does not match any allowed schema"],
        )


if __name__ == "__main__":
    unittest.main()
