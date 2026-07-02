from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.core.script_module_surfaces import (
    build_contract as build_script_module_surface_contract,
    direct_script_entrypoint_paths,
    literal_all_exports,
)

pytestmark = [pytest.mark.public, pytest.mark.fast_smoke]


SCRIPTS_DIR = Path("ops/scripts")
SCRIPT_OUTPUT_SURFACES = Path("ops/script-output-surfaces.json")
PYPROJECT = Path("pyproject.toml")
SCRIPT_LIFECYCLE_POLICY = Path("ops/script-lifecycle-policy.json")
SCRIPT_LIFECYCLE_POLICY_SCHEMA = Path("ops/schemas/script-lifecycle-policy.schema.json")
SCRIPT_MODULE_SURFACES = Path("ops/script-module-surfaces.json")
SCRIPT_MODULE_SURFACES_SCHEMA = Path("ops/schemas/script-module-surfaces.schema.json")
MAKE_FILES = [Path("Makefile"), *sorted(Path("mk").glob("*.mk"))]
CONSOLE_SCRIPT_PREFIX = "llm-wiki-"
INSTALLED_POLICY_STATES = {"public_cli", "transitional_installed"}
PUBLIC_CLI_COMMANDS = {
    "llm-wiki-finalize-run",
    "llm-wiki-improvement-observations",
    "llm-wiki-planning-gate-validate",
    "llm-wiki-run-mechanism-experiment",
    "llm-wiki-status",
}
REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_contract() -> dict:
    return json.loads(SCRIPT_MODULE_SURFACES.read_text(encoding="utf-8"))


def _load_lifecycle_policy() -> dict:
    return json.loads(SCRIPT_LIFECYCLE_POLICY.read_text(encoding="utf-8"))


def _fallback_eligible_paths() -> set[str]:
    return direct_script_entrypoint_paths(REPO_ROOT)


def _project_scripts() -> dict[str, str]:
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    scripts = pyproject.get("project", {}).get("scripts", {})
    return {str(name): str(target) for name, target in scripts.items()}


def _make_targets() -> set[str]:
    text = "\n".join(path.read_text(encoding="utf-8") for path in MAKE_FILES)
    return set(re.findall(r"^([A-Za-z0-9_.%/@-]+):", text, flags=re.MULTILINE))


def _policy_project_scripts() -> dict[str, str]:
    expected: dict[str, str] = {}
    for module in _load_lifecycle_policy()["modules"]:
        if module["install_state"] not in INSTALLED_POLICY_STATES:
            continue
        target = f"{module['canonical_module']}:main"
        for command in module["console_scripts"]:
            expected[command] = target
    return expected


def _script_files() -> set[str]:
    return {
        path.as_posix()
        for path in SCRIPTS_DIR.rglob("*.py")
        if path.name != "__init__.py"
    }


def _path_from_canonical_module(canonical_module: str) -> str:
    return f"{canonical_module.replace('.', '/')}.py"


def _module_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())


def _literal_all(path: Path) -> list[str] | None:
    return literal_all_exports(path.resolve(), vault=REPO_ROOT)


def _top_level_bindings(path: Path) -> set[str]:
    bindings: set[str] = set()
    for node in ast.walk(_module_tree(path)):
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            bindings.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bindings.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            bindings.add(node.target.id)
        elif isinstance(node, ast.TypeAlias) and isinstance(node.name, ast.Name):
            bindings.add(node.name.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bindings.add(alias.asname or alias.name.partition(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                bindings.add(alias.asname or alias.name)
    return bindings


def _run_script_module_surfaces_check(stored: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "ops.scripts.script_module_surfaces",
            "--vault",
            ".",
            "--stored",
            stored.as_posix(),
            "--check",
        ],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


class ScriptModuleSurfaceContractTests(unittest.TestCase):
    def test_contract_schema_validates(self) -> None:
        contract = _load_contract()
        schema = load_schema(SCRIPT_MODULE_SURFACES_SCHEMA)

        self.assertEqual(validate_with_schema(contract, schema), [])

    def test_contract_matches_live_source_derived_module_surfaces(self) -> None:
        contract = _load_contract()
        expected = build_script_module_surface_contract(
            REPO_ROOT, stored_contract=contract
        )

        self.maxDiff = None
        self.assertEqual(contract, expected)

    def test_contract_check_passes_for_current_registry_without_writing(self) -> None:
        before = SCRIPT_MODULE_SURFACES.read_bytes()

        result = _run_script_module_surfaces_check(SCRIPT_MODULE_SURFACES)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ops/script-module-surfaces.json is current", result.stdout)
        self.assertEqual(SCRIPT_MODULE_SURFACES.read_bytes(), before)

    def test_contract_check_fails_on_stale_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stored = Path(temp_dir) / "script-module-surfaces.json"
            payload = _load_contract()
            surface = next(
                item
                for item in payload["stable_import_surfaces"]
                if len(item["exports"]) > 1
            )
            surface["exports"] = list(reversed(surface["exports"]))
            stored.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            result = _run_script_module_surfaces_check(stored)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("script-module-surfaces contract is stale", result.stderr)
        self.assertIn(surface["path"], result.stderr)

    def test_contract_check_fails_on_stale_direct_entrypoint_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stored = Path(temp_dir) / "script-module-surfaces.json"
            payload = _load_contract()
            surface = next(
                item
                for item in payload["stable_import_surfaces"]
                if item["direct_script_entrypoint"]
            )
            surface["direct_script_entrypoint"] = False
            stored.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            result = _run_script_module_surfaces_check(stored)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("script-module-surfaces contract is stale", result.stderr)
        self.assertIn(surface["path"], result.stderr)

    def test_source_derived_contract_requires_manually_curated_role_for_new_stable_surface(
        self,
    ) -> None:
        contract = _load_contract()
        removed = contract["stable_import_surfaces"][0]["path"]
        contract["stable_import_surfaces"] = [
            item
            for item in contract["stable_import_surfaces"]
            if item["path"] != removed
        ]

        with self.assertRaisesRegex(ValueError, "missing manually curated roles"):
            build_script_module_surface_contract(REPO_ROOT, stored_contract=contract)

    def test_lifecycle_policy_schema_validates(self) -> None:
        policy = _load_lifecycle_policy()
        schema = load_schema(SCRIPT_LIFECYCLE_POLICY_SCHEMA)

        self.assertEqual(validate_with_schema(policy, schema), [])

    def test_lifecycle_policy_modules_are_unique_and_paths_are_derived(self) -> None:
        policy = _load_lifecycle_policy()
        modules = [module["canonical_module"] for module in policy["modules"]]
        paths = [
            _path_from_canonical_module(module["canonical_module"])
            for module in policy["modules"]
        ]

        self.assertEqual(len(modules), len(set(modules)))
        self.assertEqual(len(paths), len(set(paths)))
        for module in policy["modules"]:
            with self.subTest(module=module["canonical_module"]):
                self.assertNotIn("path", module)
                path = _path_from_canonical_module(module["canonical_module"])
                self.assertTrue(path.startswith("ops/scripts/"))
                self.assertTrue(Path(path).is_file())

    def test_lifecycle_policy_install_states_match_console_script_exposure(
        self,
    ) -> None:
        for module in _load_lifecycle_policy()["modules"]:
            with self.subTest(module=module["canonical_module"]):
                if module["install_state"] in INSTALLED_POLICY_STATES:
                    self.assertTrue(module["console_scripts"])
                else:
                    self.assertEqual(module["console_scripts"], [])

    def test_lifecycle_policy_installed_surface_is_public_cli_allowlist(self) -> None:
        policy = _load_lifecycle_policy()
        public_commands = {
            command
            for module in policy["modules"]
            if module["install_state"] == "public_cli"
            for command in module["console_scripts"]
        }
        transitional_modules = [
            module["canonical_module"]
            for module in policy["modules"]
            if module["install_state"] == "transitional_installed"
        ]

        self.assertEqual(public_commands, PUBLIC_CLI_COMMANDS)
        self.assertEqual(transitional_modules, [])
        self.assertEqual(set(_project_scripts()), PUBLIC_CLI_COMMANDS)

    def test_not_installed_lifecycle_entries_have_replacement_paths(self) -> None:
        for module in _load_lifecycle_policy()["modules"]:
            if module["install_state"] != "not_installed":
                continue
            with self.subTest(module=module["canonical_module"]):
                self.assertTrue(module["replacement"])

    def test_make_lifecycle_replacements_point_to_existing_targets(self) -> None:
        targets = _make_targets()
        for module in _load_lifecycle_policy()["modules"]:
            replacement = str(module.get("replacement", ""))
            if not replacement.startswith("make "):
                continue
            command_parts = replacement.split()
            if len(command_parts) < 2 or "=" in command_parts[1]:
                continue
            with self.subTest(module=module["canonical_module"]):
                self.assertIn(command_parts[1], targets)

    def test_lifecycle_policy_is_packaged_with_ops_control_files(self) -> None:
        pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        package_data = pyproject["tool"]["setuptools"]["package-data"]["ops"]

        self.assertIn("script-lifecycle-policy.json", package_data)

    def test_stable_import_surfaces_match_literal_all_exports(self) -> None:
        contract = _load_contract()

        for surface in contract["stable_import_surfaces"]:
            path = Path(surface["path"])
            with self.subTest(path=surface["path"]):
                self.assertTrue(path.is_file())
                self.assertEqual(_literal_all(path), surface["exports"])

    def test_all_literal_all_modules_are_declared_stable_surfaces(self) -> None:
        contract = _load_contract()
        declared = {surface["path"] for surface in contract["stable_import_surfaces"]}
        actual = {
            path.as_posix()
            for path in SCRIPTS_DIR.rglob("*.py")
            if _literal_all(path) is not None
        }

        self.assertEqual(actual, declared)

    def test_stable_export_names_resolve_to_module_bindings(self) -> None:
        contract = _load_contract()

        for surface in contract["stable_import_surfaces"]:
            path = Path(surface["path"])
            bindings = _top_level_bindings(path)
            missing = sorted(set(surface["exports"]) - bindings)
            with self.subTest(path=surface["path"]):
                self.assertEqual(missing, [])

    def test_direct_entrypoint_flags_match_direct_script_contract(self) -> None:
        contract = _load_contract()
        entrypoints = _fallback_eligible_paths()

        for surface in contract["stable_import_surfaces"]:
            path = surface["path"]
            with self.subTest(path=path):
                self.assertEqual(
                    surface["direct_script_entrypoint"], path in entrypoints
                )
                if path in entrypoints:
                    self.assertEqual(surface["role"], "cli_facade")

    def test_project_scripts_match_lifecycle_installed_console_scripts(self) -> None:
        self.assertEqual(_project_scripts(), _policy_project_scripts())

    def test_project_script_targets_resolve_to_main_bindings(self) -> None:
        for command, target in sorted(_project_scripts().items()):
            module, _, function = target.partition(":")
            path = Path(f"{module.replace('.', '/')}.py")
            with self.subTest(command=command, target=target):
                self.assertTrue(command.startswith(CONSOLE_SCRIPT_PREFIX))
                self.assertEqual(function, "main")
                self.assertTrue(path.is_file())
                self.assertIn(function, _top_level_bindings(path))

    def test_script_files_have_one_derived_module_layer(self) -> None:
        contract = _load_contract()
        stable = {surface["path"] for surface in contract["stable_import_surfaces"]}
        entrypoints = _fallback_eligible_paths()
        scripts = _script_files()

        self.assertTrue(stable <= scripts)
        self.assertTrue(entrypoints <= scripts)
        self.assertTrue(scripts - stable - entrypoints)
        for path in scripts:
            with self.subTest(path=path):
                if path in stable:
                    self.assertIsNotNone(_literal_all(Path(path)))
                elif path in entrypoints:
                    self.assertIn(
                        "direct script fallback", Path(path).read_text(encoding="utf-8")
                    )
                else:
                    self.assertIsNone(_literal_all(Path(path)))
