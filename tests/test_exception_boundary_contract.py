from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BROAD_EXCEPTION_MARKER = re.compile(r"broad-exception:\s*([a-z_]+)")
ALLOWED_BOUNDARY_CLASSES = frozenset(
    {
        "cli_boundary",
        "cli_policy_load_boundary",
        "platform_cleanup_boundary",
        "tolerant_parse_boundary",
    }
)
EXPECTED_BROAD_EXCEPTION_BOUNDARIES = {
    "ops/scripts/mechanism/auto_improve_loop.py": ["cli_boundary"],
    "ops/scripts/core/executor_runtime.py": ["cli_boundary"],
    "ops/scripts/core/filesystem_runtime.py": ["platform_cleanup_boundary"],
    "ops/scripts/mechanism/finalize_run.py": ["cli_boundary"],
    "ops/scripts/mechanism/mechanism_review.py": ["cli_policy_load_boundary", "cli_boundary"],
    "ops/scripts/mechanism/mutation_proposal.py": ["cli_policy_load_boundary", "cli_boundary"],
    "ops/scripts/mechanism/promotion_gate.py": ["cli_boundary"],
    "ops/scripts/registry/raw_markdown_runtime.py": ["tolerant_parse_boundary"],
    "ops/scripts/release/release_evidence_closeout_self_check.py": ["cli_boundary"],
    "ops/scripts/release/release_smoke.py": ["platform_cleanup_boundary", "cli_boundary"],
    "ops/scripts/mechanism/run_mechanism_experiment.py": ["cli_boundary"],
    "ops/scripts/mechanism/set_mechanism_run_history.py": ["cli_boundary"],
}


def _ops_script_files() -> list[str]:
    return sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "ops" / "scripts").rglob("*.py")
        if not path.name.startswith("_")
    )


def _catches_broad_exception(node: ast.ExceptHandler) -> bool:
    if isinstance(node.type, ast.Name):
        return node.type.id == "Exception"
    if isinstance(node.type, ast.Tuple):
        return any(isinstance(item, ast.Name) and item.id == "Exception" for item in node.type.elts)
    return False


def _boundary_classifications(rel_path: str) -> list[str]:
    path = REPO_ROOT / rel_path
    lines = path.read_text(encoding="utf-8").splitlines()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel_path)
    classifications = []
    broad_handlers = [
        node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler) and _catches_broad_exception(node)
    ]
    for handler in sorted(broad_handlers, key=lambda node: node.lineno):
        match = BROAD_EXCEPTION_MARKER.search(lines[handler.lineno - 1])
        classifications.append(match.group(1) if match else "")
    return classifications


class ExceptionBoundaryContractTest(unittest.TestCase):
    def test_broad_exception_boundaries_are_classified_and_pinned(self) -> None:
        actual = {
            rel_path: classifications
            for rel_path in _ops_script_files()
            if (classifications := _boundary_classifications(rel_path))
        }

        self.assertEqual(actual, EXPECTED_BROAD_EXCEPTION_BOUNDARIES)
        for classifications in actual.values():
            self.assertTrue(set(classifications) <= ALLOWED_BOUNDARY_CLASSES)


if __name__ == "__main__":
    unittest.main()
