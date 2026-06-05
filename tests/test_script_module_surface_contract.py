from __future__ import annotations

import ast
import json
import tomllib
import unittest
from pathlib import Path

import pytest
from ops.scripts.schema_runtime import load_schema, validate_with_schema

pytestmark = pytest.mark.public


SCRIPTS_DIR = Path("ops/scripts")
SCRIPT_OUTPUT_SURFACES = Path("ops/script-output-surfaces.json")
PYPROJECT = Path("pyproject.toml")
SCRIPT_LIFECYCLE_POLICY = Path("ops/script-lifecycle-policy.json")
SCRIPT_LIFECYCLE_POLICY_SCHEMA = Path("ops/schemas/script-lifecycle-policy.schema.json")
SCRIPT_MODULE_SURFACES = Path("ops/script-module-surfaces.json")
SCRIPT_MODULE_SURFACES_SCHEMA = Path("ops/schemas/script-module-surfaces.schema.json")
CONSOLE_SCRIPT_PREFIX = "llm-wiki-"
INSTALLED_POLICY_STATES = {"public_cli", "transitional_installed"}
PUBLIC_CLI_COMMANDS = {
    "llm-wiki-finalize-run",
    "llm-wiki-improvement-observations",
    "llm-wiki-planning-gate-validate",
    "llm-wiki-run-mechanism-experiment",
    "llm-wiki-status",
}


def _load_contract() -> dict:
    return json.loads(SCRIPT_MODULE_SURFACES.read_text(encoding="utf-8"))


def _load_lifecycle_policy() -> dict:
    return json.loads(SCRIPT_LIFECYCLE_POLICY.read_text(encoding="utf-8"))


def _fallback_eligible_paths() -> set[str]:
    payload = json.loads(SCRIPT_OUTPUT_SURFACES.read_text(encoding="utf-8"))
    surfaces = payload.get("surfaces", [])
    return {
        str(item["path"])
        for item in surfaces
        if item.get("direct_fallback_eligible")
        and "direct script fallback" in Path(item["path"]).read_text(encoding="utf-8")
    }


def _project_scripts() -> dict[str, str]:
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    scripts = pyproject.get("project", {}).get("scripts", {})
    return {str(name): str(target) for name, target in scripts.items()}


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


def _module_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())


def _literal_all(path: Path) -> list[str] | None:
    for node in _module_tree(path).body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            continue
        value = ast.literal_eval(node.value)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise AssertionError(f"{path.as_posix()} has non-literal __all__")
        return list(value)
    return None


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


class ScriptModuleSurfaceContractTests(unittest.TestCase):
    def test_contract_schema_validates(self) -> None:
        contract = _load_contract()
        schema = load_schema(SCRIPT_MODULE_SURFACES_SCHEMA)

        self.assertEqual(validate_with_schema(contract, schema), [])

    def test_lifecycle_policy_schema_validates(self) -> None:
        policy = _load_lifecycle_policy()
        schema = load_schema(SCRIPT_LIFECYCLE_POLICY_SCHEMA)

        self.assertEqual(validate_with_schema(policy, schema), [])

    def test_lifecycle_policy_paths_exist_and_modules_are_unique(self) -> None:
        policy = _load_lifecycle_policy()
        modules = [module["canonical_module"] for module in policy["modules"]]
        paths = [module["path"] for module in policy["modules"]]

        self.assertEqual(len(modules), len(set(modules)))
        self.assertEqual(len(paths), len(set(paths)))
        for module in policy["modules"]:
            with self.subTest(module=module["canonical_module"]):
                self.assertTrue(module["path"].startswith("ops/scripts/"))
                self.assertTrue(Path(module["path"]).is_file())
                self.assertEqual(
                    Path(module["path"]).with_suffix("").as_posix().replace("/", "."),
                    module["canonical_module"],
                )

    def test_lifecycle_policy_install_states_match_console_script_exposure(self) -> None:
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
                self.assertEqual(surface["direct_script_entrypoint"], path in entrypoints)
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
                    self.assertIn("direct script fallback", Path(path).read_text(encoding="utf-8"))
                else:
                    self.assertIsNone(_literal_all(Path(path)))
