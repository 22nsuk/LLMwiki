from __future__ import annotations

import datetime as dt
import json
import re
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.anti_slop_admission_runtime import (
    validate_operator_inventory_admission,
    validate_script_lifecycle_admission,
)
from ops.scripts.core.gate_effect_vocabulary import GATE_EFFECTS
from ops.scripts.core.make_target_inventory import build_report
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]

GATE_EFFECT_VOCABULARY_SCHEMA = REPO_ROOT / "ops/schemas/gate-effect-vocabulary.schema.json"
OPERATOR_INVENTORY_SCHEMA = REPO_ROOT / "ops/schemas/make-target-inventory-operator.schema.json"
SCRIPT_LIFECYCLE_SCHEMA = REPO_ROOT / "ops/schemas/script-lifecycle-policy.schema.json"
OPERATOR_INVENTORY = REPO_ROOT / "ops/make-target-inventory-operator.json"
SCRIPT_LIFECYCLE_POLICY = REPO_ROOT / "ops/script-lifecycle-policy.json"
INLINE_GATE_EFFECT_ENUM_RE = re.compile(
    r'"gate_effect"\s*:\s*\{[^}]*"enum"\s*:',
    re.MULTILINE,
)


def fixed_context(*, day: str = "2026-06-20") -> RuntimeContext:
    moment = dt.datetime.fromisoformat(f"{day}T12:00:00+00:00")
    return RuntimeContext(display_timezone=dt.UTC, clock=lambda: moment)


class AntiSlopAdmissionRuntimeTests(unittest.TestCase):
    def test_repo_operator_and_lifecycle_inventory_pass_admission(self) -> None:
        report = build_report(REPO_ROOT, context=fixed_context())

        self.assertEqual(report["anti_slop_admission"]["status"], "pass")
        self.assertEqual(report["anti_slop_admission"]["cli_surface_inventory"]["status"], "pass")
        self.assertEqual(
            report["anti_slop_admission"]["cli_surface_inventory"]["unclassified_module_count"],
            0,
        )
        self.assertEqual(
            report["anti_slop_admission"]["cli_surface_inventory"]["unresolved_module_count"],
            0,
        )
        self.assertEqual(report["summary"]["anti_slop_violation_count"], 0)
        self.assertIn("make-target-inventory", report["phony_targets"])
        self.assertIn("sync-derived", report["phony_targets"])
        self.assertIn("sync-derived-check", report["phony_targets"])

    def test_expired_remove_after_fails_operator_inventory(self) -> None:
        payload = {
            "operator_entrypoints": [
                {
                    "target": "alpha",
                    "category": "setup",
                    "purpose": "Test operator entrypoint.",
                    "replacement": "make alpha",
                    "deprecated_at": "2026-01-01",
                    "remove_after": "2026-01-02",
                }
            ]
        }

        violations = validate_operator_inventory_admission(
            payload,
            makefile_targets={"alpha"},
            today=dt.date(2026, 6, 20),
        )

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["field"], "remove_after")

    def test_missing_purpose_or_replacement_fail_operator_inventory(self) -> None:
        payload = {
            "operator_entrypoints": [
                {
                    "target": "alpha",
                    "category": "setup",
                    "purpose": "",
                    "replacement": "",
                    "deprecated_at": None,
                    "remove_after": None,
                }
            ]
        }

        violations = validate_operator_inventory_admission(
            payload,
            makefile_targets={"alpha"},
            today=dt.date(2026, 6, 20),
        )

        self.assertEqual({item["field"] for item in violations}, {"purpose", "replacement"})

    def test_removal_ready_requires_remove_after_in_lifecycle_admission(self) -> None:
        payload = {
            "modules": [
                {
                    "canonical_module": "ops.scripts.core.sample",
                    "rationale": "Sample module.",
                    "replacement": "make sample",
                    "lifecycle": "helper",
                    "removal_ready": True,
                }
            ]
        }

        violations = validate_script_lifecycle_admission(payload, today=dt.date(2026, 6, 20))

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["field"], "remove_after")

    def test_public_cli_lifecycle_module_allows_empty_replacement(self) -> None:
        payload = {
            "modules": [
                {
                    "canonical_module": "ops.scripts.mechanism.finalize_run",
                    "rationale": "Installed public CLI.",
                    "replacement": "",
                    "lifecycle": "public_cli",
                    "removal_ready": False,
                }
            ]
        }

        violations = validate_script_lifecycle_admission(payload, today=dt.date(2026, 6, 20))

        self.assertEqual(violations, [])

    def test_lifecycle_admission_derives_module_path_from_canonical_module(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            module_path = vault / "ops" / "scripts" / "core" / "sample.py"
            module_path.parent.mkdir(parents=True)
            module_path.write_text("def main(): pass\n", encoding="utf-8")
            payload = {
                "modules": [
                    {
                        "canonical_module": "ops.scripts.core.sample",
                        "rationale": "Sample module.",
                        "replacement": "make sample",
                        "lifecycle": "helper",
                        "removal_ready": False,
                    }
                ]
            }

            violations = validate_script_lifecycle_admission(
                payload,
                today=dt.date(2026, 6, 20),
                vault=vault,
            )

        self.assertEqual(violations, [])

    def test_lifecycle_admission_rejects_legacy_path_that_does_not_match_module(self) -> None:
        payload = {
            "modules": [
                {
                    "canonical_module": "ops.scripts.core.sample",
                    "path": "ops/scripts/release/sample.py",
                    "rationale": "Sample module.",
                    "replacement": "make sample",
                    "lifecycle": "helper",
                    "removal_ready": False,
                }
            ]
        }

        violations = validate_script_lifecycle_admission(
            payload,
            today=dt.date(2026, 6, 20),
        )

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["field"], "path")

    def test_make_inventory_fails_when_script_surface_is_missing_lifecycle_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(
                vault,
                schema_names=[
                    "make-target-inventory.schema.json",
                    "make-target-inventory-operator.schema.json",
                    "script-lifecycle-policy.schema.json",
                ],
            )
            (vault / "ops" / "schemas" / "script-lifecycle-policy.schema.json").write_text(
                SCRIPT_LIFECYCLE_SCHEMA.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            script_path = vault / "ops" / "scripts" / "core" / "missing_lifecycle.py"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text("def main(): pass\n", encoding="utf-8")
            (vault / "Makefile").write_text(
                ".PHONY: missing-lifecycle\n"
                "missing-lifecycle:\n"
                "\t$(PYTHON) -m ops.scripts.core.missing_lifecycle\n",
                encoding="utf-8",
            )
            (vault / "ops" / "script-output-surfaces.json").write_text(
                '{"surfaces":[]}\n',
                encoding="utf-8",
            )
            (vault / "ops" / "script-lifecycle-policy.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/script-lifecycle-policy.schema.json",
                        "version": 1,
                        "description": "test",
                        "lifecycle_values": [
                            "public_cli",
                            "make_only",
                            "report_generator",
                            "helper",
                            "test_only",
                            "legacy_delete",
                        ],
                        "install_state_values": [
                            "public_cli",
                            "transitional_installed",
                            "not_installed",
                        ],
                        "modules": [],
                    }
                ),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["anti_slop_admission"]["status"], "fail")
        self.assertEqual(
            report["anti_slop_admission"]["cli_surface_inventory"]["unclassified_module_count"],
            1,
        )
        self.assertEqual(
            report["anti_slop_admission"]["violations"],
            [
                {
                    "surface": (
                        "ops/script-lifecycle-policy.json#"
                        "ops.scripts.core.missing_lifecycle"
                    ),
                    "field": "canonical_module",
                    "message": (
                        "runnable script surface is missing lifecycle policy classification"
                    ),
                }
            ],
        )

    def test_gate_effect_vocabulary_schema_matches_python_constants(self) -> None:
        schema = json.loads(GATE_EFFECT_VOCABULARY_SCHEMA.read_text(encoding="utf-8"))
        enum_values = schema["$defs"]["gate_effect"]["enum"]

        self.assertEqual(tuple(enum_values), GATE_EFFECTS)

    def test_operator_inventory_schema_references_gate_effect_vocabulary(self) -> None:
        text = OPERATOR_INVENTORY_SCHEMA.read_text(encoding="utf-8")

        self.assertIn(
            '"$ref": "https://llmwiki/schemas/gate-effect-vocabulary#/$defs/gate_effect"',
            text,
        )
        self.assertIsNone(INLINE_GATE_EFFECT_ENUM_RE.search(text))

    def test_script_lifecycle_schema_has_no_inline_gate_effect_enum(self) -> None:
        text = SCRIPT_LIFECYCLE_SCHEMA.read_text(encoding="utf-8")

        self.assertNotIn("gate_effect", text)

    def test_repo_operator_inventory_validates_against_schema(self) -> None:
        from ops.scripts.core.schema_runtime import validate_with_schema

        payload = json.loads(OPERATOR_INVENTORY.read_text(encoding="utf-8"))
        self.assertEqual(
            validate_with_schema(payload, load_schema(OPERATOR_INVENTORY_SCHEMA)),
            [],
        )

    def test_repo_script_lifecycle_validates_against_updated_schema(self) -> None:
        from ops.scripts.core.schema_runtime import validate_with_schema

        payload = json.loads(SCRIPT_LIFECYCLE_POLICY.read_text(encoding="utf-8"))
        self.assertEqual(validate_with_schema(payload, load_schema(SCRIPT_LIFECYCLE_SCHEMA)), [])

    def test_make_target_inventory_fails_when_operator_target_missing_from_makefile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            (vault / "Makefile").write_text(
                ".PHONY: alpha\nalpha:\n\t@echo alpha\n",
                encoding="utf-8",
            )
            operator_dir = vault / "ops"
            operator_dir.mkdir()
            (operator_dir / "make-target-inventory-operator.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/make-target-inventory-operator.schema.json",
                        "description": "test",
                        "operator_entrypoints": [
                            {
                                "target": "missing-target",
                                "category": "setup",
                                "purpose": "Missing from makefile.",
                                "replacement": "make missing-target",
                                "deprecated_at": None,
                                "remove_after": None,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (operator_dir / "script-lifecycle-policy.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/script-lifecycle-policy.schema.json",
                        "version": 1,
                        "description": "test",
                        "lifecycle_values": ["helper"],
                        "install_state_values": ["not_installed"],
                        "modules": [],
                    }
                ),
                encoding="utf-8",
            )

            report = validate_operator_inventory_admission(
                json.loads(
                    (vault / "ops" / "make-target-inventory-operator.json").read_text(
                        encoding="utf-8"
                    )
                ),
                makefile_targets={"alpha"},
                today=dt.date(2026, 6, 20),
            )

            self.assertEqual(len(report), 1)
            self.assertEqual(report[0]["field"], "target")


if __name__ == "__main__":
    unittest.main()
