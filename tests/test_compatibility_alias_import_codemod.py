from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core._compatibility_alias_import_codemod import (
    rewrite_compatibility_alias_imports,
)

pytestmark = pytest.mark.public


class CompatibilityAliasImportCodemodTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        self._write("ops/scripts/__init__.py", "# _ReexportFinder\n")
        self._write(
            "ops/script-lifecycle-policy.json",
            """{
  "modules": [
    {
      "canonical_module": "ops.scripts.core.artifact_io_runtime",
      "lifecycle": "helper"
    },
    {
      "canonical_module": "ops.scripts.core.runtime_context",
      "lifecycle": "helper"
    }
  ]
}
""",
        )
        self._write(
            "ops/script-flat-import-aliases.json",
            """{
  "aliases": [
    {
      "canonical_module": "ops.scripts.core.artifact_io_runtime"
    },
    {
      "canonical_module": "ops.scripts.core.runtime_context"
    }
  ]
}
""",
        )
        self._write("ops/scripts/core/runtime_context.py", "class RuntimeContext:\n    pass\n")
        self._write(
            "ops/scripts/core/artifact_io_runtime.py",
            "def read_json_object():\n    return {}\n",
        )
        legacy_runtime_context_path = "ops/scripts/" + "runtime_context.py"
        self.target_path = self._write(
            "ops/scripts/supply_chain/example.py",
            "\n".join(
                [
                    "from ops.scripts.runtime_context import RuntimeContext",
                    "from ops.scripts.artifact_io_runtime import read_json_object",
                    "",
                    "REPORT = build_report(",
                    f"    source_paths=['{legacy_runtime_context_path}'],",
                    ")",
                    "LOGIC_PATH = 'ops/scripts/runtime_context.py'",
                    "",
                ]
            ),
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write(self, rel_path: str, text: str) -> Path:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_dry_run_reports_rewrites_without_mutating_files(self) -> None:
        report = rewrite_compatibility_alias_imports(
            self.vault,
            prefixes=("ops/scripts/supply_chain/",),
            source_path_references=True,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["mode"], "dry_run")
        self.assertEqual(report["selected_caller_count"], 2)
        self.assertEqual(report["import_rewrite_count"], 2)
        self.assertEqual(report["source_path_reference_rewrite_count"], 1)
        self.assertIn(
            "from ops.scripts.runtime_context import RuntimeContext",
            self.target_path.read_text(encoding="utf-8"),
        )

    def test_write_rewrites_imports_and_source_path_references(self) -> None:
        report = rewrite_compatibility_alias_imports(
            self.vault,
            prefixes=("ops/scripts/supply_chain/",),
            write=True,
            source_path_references=True,
        )

        self.assertEqual(report["status"], "pass")
        text = self.target_path.read_text(encoding="utf-8")
        self.assertIn(
            "from ops.scripts.core.runtime_context import RuntimeContext",
            text,
        )
        self.assertIn(
            "from ops.scripts.core.artifact_io_runtime import read_json_object",
            text,
        )
        self.assertIn("'ops/scripts/core/runtime_context.py'", text)
        self.assertIn("LOGIC_PATH = 'ops/scripts/runtime_context.py'", text)

    def test_write_rewrites_package_and_dotted_module_imports(self) -> None:
        target_path = self._write(
            "tests/test_package_imports.py",
            "\n".join(
                [
                    "from ops.scripts import runtime_context",
                    "from ops.scripts import artifact_io_runtime as io_runtime",
                    "import ops.scripts.runtime_context as runtime_context_module",
                    "from ops.scripts import (",
                    "    runtime_context as ctx_runtime,",
                    "    artifact_io_runtime,",
                    ")",
                    "",
                ]
            ),
        )

        report = rewrite_compatibility_alias_imports(
            self.vault,
            prefixes=("tests/",),
            write=True,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["selected_caller_count"], 5)
        self.assertEqual(report["import_rewrite_count"], 5)
        text = target_path.read_text(encoding="utf-8")
        self.assertIn("from ops.scripts.core import runtime_context\n", text)
        self.assertIn(
            "from ops.scripts.core import artifact_io_runtime as io_runtime\n",
            text,
        )
        self.assertIn(
            "import ops.scripts.core.runtime_context as runtime_context_module\n",
            text,
        )
        self.assertIn(
            "from ops.scripts.core import runtime_context as ctx_runtime\n",
            text,
        )
        self.assertIn("from ops.scripts.core import artifact_io_runtime\n", text)
        self.assertNotIn("from ops.scripts import", text)
