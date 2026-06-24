from __future__ import annotations

import unittest

import pytest

from ops.scripts.core.codex_exec_dependency_preflight_runtime import (
    dependency_preflight_module_payloads,
    parse_dependency_preflight_probe,
    project_dependency_check_script,
)
from ops.scripts.core.make_target_operator_surface_runtime import (
    INTERNAL_TARGET_PREFIX,
    internal_make_targets,
    validate_operator_inventory_surface,
)

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


class MakeTargetOperatorSurfaceTests(unittest.TestCase):
    def test_internal_targets_use_reserved_prefix(self) -> None:
        targets = internal_make_targets({"help", "_internal-runtime-hotspot-goldens-check"})
        self.assertEqual(targets, ["_internal-runtime-hotspot-goldens-check"])
        self.assertTrue(INTERNAL_TARGET_PREFIX.startswith("_internal-"))

    def test_operator_inventory_rejects_internal_targets(self) -> None:
        violations = validate_operator_inventory_surface(
            {
                "operator_entrypoints": [
                    {
                        "target": "_internal-runtime-hotspot-goldens-check",
                        "purpose": "hidden",
                        "replacement": "make _internal-runtime-hotspot-goldens-check",
                    }
                ]
            },
            makefile_targets={"_internal-runtime-hotspot-goldens-check"},
        )
        self.assertEqual(len(violations), 1)
        self.assertIn("must not list internal target", violations[0]["message"])


class CodexExecDependencyPreflightRuntimeTests(unittest.TestCase):
    def test_project_dependency_check_script_is_executable_python(self) -> None:
        script = project_dependency_check_script()
        self.assertIn("importlib.import_module", script)
        self.assertIn("json.dumps(payload", script)

    def test_parse_dependency_preflight_probe_rejects_invalid_json(self) -> None:
        self.assertEqual(parse_dependency_preflight_probe("not-json"), {})

    def test_dependency_preflight_module_payloads_marks_missing_modules(self) -> None:
        payloads = dependency_preflight_module_payloads(
            probe={"python": {"executable": "/usr/bin/python3", "version": "3.12.0"}, "modules": []},
            completed_returncode=1,
            stdout='{"python":{"executable":"/usr/bin/python3","version":"3.12.0"},"modules":[]}',
            stderr="",
            roots=[],
        )
        self.assertEqual(len(payloads), 3)
        self.assertEqual(payloads[0]["status"], "missing")
