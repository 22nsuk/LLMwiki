from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path
from unittest.mock import sentinel, patch

import pytest

pytestmark = pytest.mark.public


SCRIPTS_DIR = Path("ops/scripts")
SURFACES_REGISTRY = Path("ops/script-output-surfaces.json")
PYPROJECT = Path("pyproject.toml")
MAKE_FILES = [Path("Makefile"), *sorted(Path("mk").glob("*.mk"))]
DIRECT_SCRIPT_BRANCH = 'if __package__ in (None, ""):  # pragma: no cover - direct script fallback'
REPO_ROOT_BOOTSTRAP = 'sys.path.insert(0, str(Path(__file__).resolve().parents[3]))'
FLAT_SCRIPT_MODULE_RE = re.compile(r"-m\s+ops\.scripts\.([A-Za-z0-9_]+)\b")
DEPENDENCY_IMPORT_FAILURE_ALLOWLIST = {
    "ops/scripts/core/schema_runtime.py",
    "ops/scripts/core/yaml_runtime.py",
}


def _fallback_eligible_paths() -> set[str]:
    payload = json.loads(SURFACES_REGISTRY.read_text(encoding="utf-8"))
    surfaces = payload.get("surfaces", [])
    return {
        str(item["path"])
        for item in surfaces
        if item.get("direct_fallback_eligible")
        and "direct script fallback" in Path(item["path"]).read_text(encoding="utf-8")
    }


def _project_script_module_targets() -> set[str]:
    payload = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    scripts = payload["project"]["scripts"]
    return {str(target).split(":", maxsplit=1)[0] for target in scripts.values()}


def _makefile_flat_module_names() -> set[str]:
    names: set[str] = set()
    for path in MAKE_FILES:
        names.update(FLAT_SCRIPT_MODULE_RE.findall(path.read_text(encoding="utf-8")))
    return names


def _module_name_from_script_path(rel_path: str) -> str:
    return Path(rel_path).with_suffix("").as_posix().replace("/", ".")


class ImportFallbackContractTests(unittest.TestCase):
    def test_flat_script_reexport_aliases_resolve_to_canonical_module_objects(self) -> None:
        flat = importlib.import_module("ops.scripts.test_execution_summary")
        canonical = importlib.import_module("ops.scripts.test.test_execution_summary")

        self.assertIs(flat, canonical)
        with patch("ops.scripts.test_execution_summary.run_with_timeout", sentinel.run_with_timeout):
            self.assertIs(canonical.run_with_timeout, sentinel.run_with_timeout)

    def test_flat_script_reexport_names_are_unambiguous(self) -> None:
        modules_by_stem: dict[str, list[str]] = {}
        for path in sorted(SCRIPTS_DIR.glob("*/*.py")):
            if path.name.startswith("_"):
                continue
            modules_by_stem.setdefault(path.stem, []).append(path.as_posix())

        duplicates = {
            stem: paths
            for stem, paths in sorted(modules_by_stem.items())
            if len(paths) > 1
        }
        self.assertEqual(duplicates, {})

    def test_flat_script_reexport_supports_python_m_entrypoint(self) -> None:
        env = os.environ.copy()
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ops.scripts.test_execution_summary",
                "--help",
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout)

    def test_flat_script_reexport_specs_preserve_origin_for_runpy(self) -> None:
        spec = importlib.util.find_spec("ops.scripts.test_execution_summary")

        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertTrue(spec.origin)
        self.assertTrue(spec.has_location)
        self.assertTrue(str(spec.origin).endswith("ops/scripts/test/test_execution_summary.py"))

    def test_cli_surface_inventory_resolves_project_makefile_and_direct_fallback_entries(self) -> None:
        project_targets = _project_script_module_targets()
        flat_targets = {f"ops.scripts.{name}" for name in _makefile_flat_module_names()}
        direct_fallback_targets = {
            _module_name_from_script_path(path) for path in _fallback_eligible_paths()
        }
        all_targets = sorted(project_targets | flat_targets | direct_fallback_targets)

        self.assertEqual(len(project_targets), 69)
        self.assertTrue(flat_targets)
        self.assertTrue(direct_fallback_targets)
        for module_name in all_targets:
            with self.subTest(module_name=module_name):
                module = importlib.import_module(module_name)
                self.assertTrue(hasattr(module, "main"))

    def test_direct_script_fallback_does_not_use_importerror_control_flow(self) -> None:
        offenders: list[str] = []
        for path in sorted(SCRIPTS_DIR.rglob("*.py")):
            if path.name.startswith("_"):
                continue
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if "except ImportError" in line and "direct script fallback" in line:
                    offenders.append(f"{path.as_posix()}:{line_number}")

        self.assertEqual(offenders, [])

    def test_import_failure_catches_are_dependency_contracts_only(self) -> None:
        offenders: list[str] = []
        for path in sorted(SCRIPTS_DIR.rglob("*.py")):
            if path.name.startswith("_"):
                continue
            rel_path = path.as_posix()
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if "except ImportError" not in line and "except ModuleNotFoundError" not in line:
                    continue
                if rel_path not in DEPENDENCY_IMPORT_FAILURE_ALLOWLIST:
                    offenders.append(f"{rel_path}:{line_number}")

        self.assertEqual(offenders, [])

    def test_direct_script_entrypoint_registry_matches_fallback_files(self) -> None:
        eligible = _fallback_eligible_paths()
        fallback_files = {
            path.as_posix()
            for path in sorted(SCRIPTS_DIR.rglob("*.py"))
            if "direct script fallback" in path.read_text(encoding="utf-8")
        }

        self.assertTrue(eligible)
        self.assertEqual(fallback_files, eligible)

    def test_direct_script_entrypoints_use_package_bootstrap(self) -> None:
        for rel_path in sorted(_fallback_eligible_paths()):
            path = Path(rel_path)
            with self.subTest(path=rel_path):
                text = path.read_text(encoding="utf-8")
                self.assertIn(DIRECT_SCRIPT_BRANCH, text)
                self.assertIn(REPO_ROOT_BOOTSTRAP, text)
                self.assertIn("from ops.scripts.", text)
                self.assertIn("\nelse:\n", text)
                self.assertIn('if __name__ == "__main__"', text)

    def test_direct_script_entrypoint_registry_paths_exist_under_scripts(self) -> None:
        for rel_path in sorted(_fallback_eligible_paths()):
            with self.subTest(path=rel_path):
                self.assertTrue(rel_path.startswith("ops/scripts/"))
                self.assertTrue(Path(rel_path).is_file())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
