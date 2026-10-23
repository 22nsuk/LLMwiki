from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.python_function_budget_runtime import (
    python_function_budget_candidates,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class PythonFunctionBudgetRuntimeTest(unittest.TestCase):
    def test_candidates_emit_for_runtime_and_tests_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            runtime_path = vault / "ops" / "scripts" / "runtime_sample.py"
            test_path = vault / "tests" / "test_runtime_sample.py"
            runtime_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.parent.mkdir(parents=True, exist_ok=True)

            runtime_path.write_text(
                "def oversized_runtime(a, b, c):\n"
                "    if a:\n"
                "        if b:\n"
                "            return c\n"
                "    return a\n",
                encoding="utf-8",
            )
            test_path.write_text(
                "def test_oversized_case(value):\n"
                "    if value:\n"
                "        return True\n"
                "    return False\n",
                encoding="utf-8",
            )

            candidates = python_function_budget_candidates(
                vault,
                {
                    "profiles": {
                        "runtime": {
                            "include_prefixes": ["ops/", "tools/"],
                            "lines": 3,
                            "params": 2,
                            "branches": 1,
                        },
                        "tests": {
                            "include_prefixes": ["tests/"],
                            "lines": 3,
                            "params": 0,
                            "branches": 0,
                        },
                    }
                },
            )

            self.assertEqual(len(candidates), 2)
            self.assertEqual(
                candidates,
                [
                    {
                        "type": "python_function_budget_candidate",
                        "page": "ops/scripts/runtime_sample.py",
                        "symbol": "oversized_runtime",
                        "line": 1,
                        "profile": "runtime",
                        "triggered_budgets": [
                            "function_lines",
                            "parameter_count",
                            "branch_node_count",
                        ],
                        "value": {
                            "function_lines": 5,
                            "parameter_count": 3,
                            "branch_node_count": 2,
                        },
                        "threshold": {
                            "function_lines": 3,
                            "parameter_count": 2,
                            "branch_node_count": 1,
                        },
                        "suggested_action": "review_for_function_split_or_interface_object",
                    },
                    {
                        "type": "python_function_budget_candidate",
                        "page": "tests/test_runtime_sample.py",
                        "symbol": "test_oversized_case",
                        "line": 1,
                        "profile": "tests",
                        "triggered_budgets": [
                            "function_lines",
                            "parameter_count",
                            "branch_node_count",
                        ],
                        "value": {
                            "function_lines": 4,
                            "parameter_count": 1,
                            "branch_node_count": 1,
                        },
                        "threshold": {
                            "function_lines": 3,
                            "parameter_count": 0,
                            "branch_node_count": 0,
                        },
                        "suggested_action": "review_for_function_split_or_interface_object",
                    },
                ],
            )

    def test_nested_functions_are_counted_independently(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            target = vault / "tools" / "nested_sample.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                "class Worker:\n"
                "    def outer(self, value):\n"
                "        if value:\n"
                "            return value\n"
                "\n"
                "        def inner(flag):\n"
                "            if flag:\n"
                "                return True\n"
                "            return False\n"
                "\n"
                "        return inner(value)\n",
                encoding="utf-8",
            )

            candidates = python_function_budget_candidates(
                vault,
                {
                    "profiles": {
                        "runtime": {
                            "include_prefixes": ["ops/", "tools/"],
                            "lines": 1,
                            "params": 1,
                            "branches": 0,
                        },
                        "tests": {
                            "include_prefixes": ["tests/"],
                            "lines": 100,
                            "params": 100,
                            "branches": 100,
                        },
                    }
                },
            )

            symbols = [candidate["symbol"] for candidate in candidates]
            self.assertEqual(symbols, ["Worker.outer", "Worker.outer.inner"])
            outer = candidates[0]
            inner = candidates[1]
            self.assertEqual(outer["value"]["branch_node_count"], 1)
            self.assertEqual(inner["value"]["branch_node_count"], 1)

    def test_methods_exclude_self_and_decorators_extend_line_span(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            target = vault / "ops" / "scripts" / "method_sample.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                "class Worker:\n"
                "    @classmethod\n"
                "    def build(cls, first, second):\n"
                "        return first + second\n",
                encoding="utf-8",
            )

            candidates = python_function_budget_candidates(
                vault,
                {
                    "profiles": {
                        "runtime": {
                            "include_prefixes": ["ops/"],
                            "lines": 2,
                            "params": 2,
                            "branches": 10,
                        },
                        "tests": {
                            "include_prefixes": ["tests/"],
                            "lines": 100,
                            "params": 100,
                            "branches": 100,
                        },
                    }
                },
            )

            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["line"], 2)
            self.assertEqual(candidates[0]["triggered_budgets"], ["function_lines"])
            self.assertEqual(candidates[0]["value"]["function_lines"], 3)
            self.assertEqual(candidates[0]["value"]["parameter_count"], 2)

    def test_syntax_error_file_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            target = vault / "ops" / "scripts" / "broken.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("def broken(:\n    pass\n", encoding="utf-8")

            candidates = python_function_budget_candidates(
                vault,
                {
                    "profiles": {
                        "runtime": {
                            "include_prefixes": ["ops/", "tools/"],
                            "lines": 1,
                            "params": 0,
                            "branches": 0,
                        },
                        "tests": {
                            "include_prefixes": ["tests/"],
                            "lines": 1,
                            "params": 0,
                            "branches": 0,
                        },
                    }
                },
            )

            self.assertEqual(candidates, [])

    def test_runtime_hardening_targets_stay_under_function_budget(self) -> None:
        policy, _ = load_policy(REPO_ROOT)
        runtime_profile = policy["system_refactor_policy"]["python_function_review"]["profiles"]["runtime"]

        candidates = python_function_budget_candidates(
            REPO_ROOT,
            {
                "profiles": {
                    "runtime": {
                        **runtime_profile,
                        "include_prefixes": [
                            "ops/scripts/core/codex_exec_executor.py",
                            "ops/scripts/mechanism/auto_improve_readiness_runtime.py",
                        ],
                    }
                }
            },
        )
        symbols = {str(candidate["symbol"]) for candidate in candidates}

        self.assertNotIn("_build_executor_report", symbols)
        self.assertNotIn("_materialize_prompt", symbols)
        self.assertNotIn("load_readiness_inputs", symbols)


@pytest.mark.parametrize("path_kind", [
    "absolute_file", "parent_file", "absolute_directory", "parent_directory",
    "file_link", "directory_link", "nested_file_link",
])
def test_function_budget_rejects_external_sources(tmp_path: Path, path_kind: str) -> None:
    vault = tmp_path / "candidate"
    vault.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "synthetic.py"
    secret.write_text("def synthetic_private_symbol(value):\n    return value\n", encoding="utf-8")
    prefixes = {
        "absolute_file": str(secret), "parent_file": "../outside/synthetic.py",
        "absolute_directory": str(outside), "parent_directory": "../outside",
    }
    if path_kind not in prefixes:
        source = vault / "sources"
        source.mkdir()
        link = source / "alias.py"
        target = outside if path_kind == "directory_link" else secret
        try:
            link.symlink_to(target, target_is_directory=target.is_dir())
        except OSError as exc:
            pytest.skip(f"symlink setup unavailable: {exc}")
        prefixes[path_kind] = "sources" if path_kind == "nested_file_link" else "sources/alias.py"
    config = {"profiles": {"runtime": {
        "include_prefixes": [prefixes[path_kind]], "lines": 1, "params": 0, "branches": 0,
    }}}
    reads = []
    read_text = Path.read_text

    def record_read(path: Path, *args: object, **kwargs: object) -> str:
        if path.resolve() == secret:
            reads.append(path)
        return read_text(path, *args, **kwargs)

    try:
        with mock.patch.object(Path, "read_text", record_read), pytest.raises(ValueError, match="stay under vault"):
            python_function_budget_candidates(vault, config)
    finally:
        assert reads == [], "diagnostics read the synthetic host file"


def test_function_budget_preserves_contained_prefixes(tmp_path: Path) -> None:
    source = tmp_path / "sources" / "valid.py"
    source.parent.mkdir()
    source.write_text("def ordinary(value):\n    return value\n", encoding="utf-8")
    config = {"profiles": {"runtime": {
        "include_prefixes": ["sources", str(source), "sources/../sources/valid.py", "missing"],
        "lines": 1, "params": 0, "branches": 0,
    }}}
    candidates = python_function_budget_candidates(tmp_path, config)
    assert [(item["page"], item["symbol"]) for item in candidates] == [("sources/valid.py", "ordinary")]


def test_function_budget_preserves_internal_aliases(tmp_path: Path) -> None:
    source = tmp_path / "sources" / "module.txt"
    source.parent.mkdir()
    source.write_text("def ordinary(value):\n    return value\n", encoding="utf-8")
    try:
        (tmp_path / "alias.py").symlink_to(source)
        (tmp_path / "source_alias").symlink_to(source.parent, target_is_directory=True)
        (source.parent / "entry.py").symlink_to(source)
    except OSError as exc:
        pytest.skip(f"symlink setup unavailable: {exc}")
    config = {"profiles": {"runtime": {
        "include_prefixes": ["alias.py", "source_alias"],
        "lines": 1, "params": 0, "branches": 0,
    }}}
    candidates = python_function_budget_candidates(tmp_path, config)
    assert [(item["page"], item["symbol"]) for item in candidates] == [("sources/module.txt", "ordinary")]


if __name__ == "__main__":
    unittest.main()
