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
SCRIPT_MODULE_SURFACES = Path("ops/script-module-surfaces.json")
SCRIPT_MODULE_SURFACES_SCHEMA = Path("ops/schemas/script-module-surfaces.schema.json")
CONSOLE_SCRIPT_PREFIX = "llm-wiki-"


def _load_contract() -> dict:
    return json.loads(SCRIPT_MODULE_SURFACES.read_text(encoding="utf-8"))


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


def _console_command_for_direct_script(path: str) -> str:
    stem = Path(path).stem.removesuffix("_runtime")
    return f"{CONSOLE_SCRIPT_PREFIX}{stem.replace('_', '-')}"


def _console_target_for_direct_script(path: str) -> str:
    return f"{path.removesuffix('.py').replace('/', '.')}:main"


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

    def test_project_scripts_are_canonical_cli_for_direct_wrappers(self) -> None:
        entrypoints = _fallback_eligible_paths()
        expected = {
            _console_command_for_direct_script(path): _console_target_for_direct_script(path)
            for path in entrypoints
        }

        self.assertEqual(_project_scripts(), expected)

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
