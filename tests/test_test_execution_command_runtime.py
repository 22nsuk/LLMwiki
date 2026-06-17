from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.command_runtime import TimedProcessResult
from ops.scripts.test.test_execution_command_runtime import (
    classify_interpreter_path,
    classify_status,
    parse_pytest_counts,
    semantic_command,
)


class TestExecutionCommandRuntimeTests(unittest.TestCase):
    def test_semantic_command_ignores_executable_path_before_pytest_module(self) -> None:
        self.assertEqual(
            semantic_command(["/tmp/venv/bin/python", "-m", "pytest", "-q", "tests"]),
            ["-m", "pytest", "-q", "tests"],
        )
        self.assertEqual(
            semantic_command([".venv/bin/pytest", "-q", "tests"]),
            [".venv/bin/pytest", "-q", "tests"],
        )

    def test_interpreter_path_classifies_repo_and_external_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            self.assertEqual(classify_interpreter_path(vault, "python"), "path_lookup")
            self.assertEqual(classify_interpreter_path(vault, ".venv/bin/python"), "repo_virtualenv")
            self.assertEqual(
                classify_interpreter_path(vault, (vault / "tools" / "python").as_posix()),
                "repo_absolute",
            )

    def test_parse_counts_and_status_share_pytest_outcome_semantics(self) -> None:
        counts = parse_pytest_counts("3 passed, 1 failed, 1 subtest passed, 5 subtests passed, 2 warnings")

        self.assertEqual(counts["passed"], 3)
        self.assertEqual(counts["failed"], 1)
        self.assertEqual(counts["subtests_passed"], 5)
        self.assertEqual(counts["warnings"], 2)
        self.assertEqual(
            classify_status(
                TimedProcessResult(
                    args=["python", "-m", "pytest"],
                    returncode=1,
                    stdout="",
                    stderr="",
                    timed_out=False,
                    timeout_seconds=60,
                    termination_reason="exited",
                ),
                counts,
            ),
            "partial-pass",
        )


if __name__ == "__main__":
    unittest.main()
