from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.core.script_lifecycle_policy import build_policy

pytestmark = [
    pytest.mark.public,
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
    pytest.mark.default_test_boundary,
]


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_LIFECYCLE_POLICY = Path("ops/script-lifecycle-policy.json")
SCRIPT_LIFECYCLE_POLICY_SCHEMA = Path("ops/schemas/script-lifecycle-policy.schema.json")
SCRIPT_LIFECYCLE_OVERRIDES = Path("ops/script-lifecycle-overrides.json")
SCRIPT_LIFECYCLE_OVERRIDES_SCHEMA = Path(
    "ops/schemas/script-lifecycle-overrides.schema.json"
)
GENERATED_ONLY_FIELDS = {"console_scripts", "install_state", "path", "rationale"}


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"{path} did not contain a JSON object")
    return payload


def _run_script_lifecycle_policy_check(stored: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "ops.scripts.core.script_lifecycle_policy",
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


class ScriptLifecyclePolicyTests(unittest.TestCase):
    def test_policy_and_overrides_schema_validate(self) -> None:
        self.assertEqual(
            validate_with_schema(
                _load_json(SCRIPT_LIFECYCLE_POLICY),
                load_schema(SCRIPT_LIFECYCLE_POLICY_SCHEMA),
            ),
            [],
        )
        self.assertEqual(
            validate_with_schema(
                _load_json(SCRIPT_LIFECYCLE_OVERRIDES),
                load_schema(SCRIPT_LIFECYCLE_OVERRIDES_SCHEMA),
            ),
            [],
        )

    def test_overrides_do_not_store_generated_inventory_fields(self) -> None:
        overrides = _load_json(SCRIPT_LIFECYCLE_OVERRIDES)

        for module in overrides["overrides"]:  # type: ignore[index]
            with self.subTest(module=module["canonical_module"]):
                self.assertFalse(GENERATED_ONLY_FIELDS & set(module))

    def test_policy_matches_live_generated_script_lifecycle_inventory(self) -> None:
        actual = _load_json(SCRIPT_LIFECYCLE_POLICY)
        expected = build_policy(REPO_ROOT)

        self.maxDiff = None
        self.assertEqual(actual, expected)

    def test_policy_check_passes_for_current_registry_without_writing(self) -> None:
        before = SCRIPT_LIFECYCLE_POLICY.read_bytes()

        result = _run_script_lifecycle_policy_check(SCRIPT_LIFECYCLE_POLICY)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ops/script-lifecycle-policy.json is current", result.stdout)
        self.assertEqual(SCRIPT_LIFECYCLE_POLICY.read_bytes(), before)

    def test_policy_check_fails_on_stale_generated_field(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stored = Path(temp_dir) / "script-lifecycle-policy.json"
            payload = _load_json(SCRIPT_LIFECYCLE_POLICY)
            module = next(
                item
                for item in payload["modules"]  # type: ignore[index]
                if item["canonical_module"] == "ops.scripts.core.script_lifecycle_policy"
            )
            module["console_scripts"] = ["llm-wiki-stale"]
            stored.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            result = _run_script_lifecycle_policy_check(stored)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("script-lifecycle-policy is stale", result.stderr)
        self.assertIn("ops.scripts.core.script_lifecycle_policy", result.stderr)

    def test_new_script_surfaces_receive_deterministic_defaults_from_live_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            (vault / "ops" / "scripts" / "core").mkdir(parents=True)
            (vault / "mk").mkdir()
            (vault / "pyproject.toml").write_text(
                "[project]\n"
                "name = 'sample'\n"
                "[project.scripts]\n"
                "llm-wiki-sample = 'ops.scripts.public_cli:main'\n",
                encoding="utf-8",
            )
            (vault / "Makefile").write_text("include mk/core.mk\n", encoding="utf-8")
            (vault / "mk" / "core.mk").write_text(
                "sample-report:\n"
                "\tpython -m ops.scripts.make_only --out tmp/sample.json\n",
                encoding="utf-8",
            )
            for name in ("public_cli", "make_only", "direct_only", "helper_only"):
                source = "def main(): pass\n"
                if name == "direct_only":
                    source = (
                        "if __package__ in (None, \"\"):  # pragma: no cover - direct script fallback\n"
                        "    pass\n"
                        "def main(): pass\n"
                        "if __name__ == \"__main__\":\n"
                        "    main()\n"
                    )
                (vault / "ops" / "scripts" / "core" / f"{name}.py").write_text(
                    source,
                    encoding="utf-8",
                )
            overrides = {
                "$schema": "ops/schemas/script-lifecycle-overrides.schema.json",
                "version": 1,
                "description": "fixture overrides",
                "overrides": [
                    {
                        "canonical_module": "ops.scripts.core.make_only",
                        "lifecycle": "report_generator",
                        "replacement": "make sample-report",
                    }
                ],
            }

            policy = build_policy(vault, overrides=overrides)

        modules = {item["canonical_module"]: item for item in policy["modules"]}
        self.assertEqual(
            set(modules),
            {
                "ops.scripts.core.direct_only",
                "ops.scripts.core.helper_only",
                "ops.scripts.core.make_only",
                "ops.scripts.core.public_cli",
            },
        )
        self.assertEqual(
            modules["ops.scripts.core.public_cli"]["console_scripts"],
            ["llm-wiki-sample"],
        )
        self.assertEqual(
            modules["ops.scripts.core.public_cli"]["install_state"],
            "public_cli",
        )
        self.assertEqual(modules["ops.scripts.core.public_cli"]["lifecycle"], "public_cli")
        self.assertEqual(
            modules["ops.scripts.core.make_only"]["lifecycle"],
            "report_generator",
        )
        self.assertEqual(
            modules["ops.scripts.core.make_only"]["replacement"],
            "make sample-report",
        )
        self.assertEqual(
            modules["ops.scripts.core.direct_only"]["replacement"],
            "python -m ops.scripts.core.direct_only",
        )
        self.assertIn(
            "direct_fallback_modules",
            modules["ops.scripts.core.direct_only"]["rationale"],
        )
        self.assertEqual(
            modules["ops.scripts.core.helper_only"]["lifecycle"],
            "helper",
        )
        self.assertEqual(
            modules["ops.scripts.core.helper_only"]["replacement"],
            "python -m ops.scripts.core.helper_only",
        )

    def test_makefile_module_scan_ignores_non_recipe_mentions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            (vault / "ops" / "scripts" / "core").mkdir(parents=True)
            (vault / "mk").mkdir()
            (vault / "pyproject.toml").write_text(
                "[project]\nname = 'sample'\n",
                encoding="utf-8",
            )
            (vault / "Makefile").write_text("include mk/core.mk\n", encoding="utf-8")
            (vault / "mk" / "core.mk").write_text(
                "# python -m ops.scripts.core.documented_only\n"
                "VARIABLE := python -m ops.scripts.core.variable_only\n"
                "USED_COMMAND ?= python -m ops.scripts.core.variable_used --flag\n"
                "ASSIGNMENT_CONTINUED ?= python \\\n"
                "    -m ops.scripts.core.assignment_continued --flag\n"
                "sample-report:\n"
                "\tpython -m ops.scripts.core.recipe_report --out tmp/sample.json\n"
                "variable-report:\n"
                "\t$(USED_COMMAND)\n"
                "assignment-continuation-report:\n"
                "\t$(ASSIGNMENT_CONTINUED)\n"
                "inline-report: ; python -m ops.scripts.core.inline_report --out tmp/inline.json\n"
                "continued-report:\n"
                "\tpython \\\n"
                "    -m ops.scripts.core.continued_report --out tmp/continued.json\n"
                "late-variable-report:\n"
                "\t$(LATE_COMMAND)\n"
                "commented-inline-report: ; # python -m ops.scripts.core.commented_only\n"
                "LATE_COMMAND ?= python -m ops.scripts.core.late_variable --flag\n",
                encoding="utf-8",
            )
            for name in (
                "documented_only",
                "variable_only",
                "recipe_report",
                "variable_used",
                "assignment_continued",
                "inline_report",
                "continued_report",
                "late_variable",
                "commented_only",
            ):
                (vault / "ops" / "scripts" / "core" / f"{name}.py").write_text(
                    "def main(): pass\n",
                    encoding="utf-8",
                )

            policy = build_policy(vault, overrides={"overrides": []})

        modules = {item["canonical_module"]: item for item in policy["modules"]}
        self.assertEqual(
            modules["ops.scripts.core.recipe_report"]["replacement"],
            "make sample-report",
        )
        self.assertEqual(modules["ops.scripts.core.recipe_report"]["lifecycle"], "make_only")
        self.assertIn(
            "makefile_module_invocations",
            modules["ops.scripts.core.recipe_report"]["rationale"],
        )
        self.assertEqual(
            modules["ops.scripts.core.variable_used"]["replacement"],
            "make variable-report",
        )
        self.assertEqual(
            modules["ops.scripts.core.assignment_continued"]["replacement"],
            "make assignment-continuation-report",
        )
        self.assertEqual(
            modules["ops.scripts.core.inline_report"]["replacement"],
            "make inline-report",
        )
        self.assertEqual(
            modules["ops.scripts.core.continued_report"]["replacement"],
            "make continued-report",
        )
        self.assertEqual(
            modules["ops.scripts.core.late_variable"]["replacement"],
            "make late-variable-report",
        )
        self.assertNotIn(
            "makefile_module_invocations",
            modules["ops.scripts.core.documented_only"]["rationale"],
        )
        self.assertNotIn(
            "makefile_module_invocations",
            modules["ops.scripts.core.variable_only"]["rationale"],
        )
        self.assertNotIn(
            "makefile_module_invocations",
            modules["ops.scripts.core.commented_only"]["rationale"],
        )


if __name__ == "__main__":
    unittest.main()
