#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"expected snippet not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    repo = Path.cwd()
    runtime_path = repo / "ops" / "scripts" / "auto_improve_iteration_persistence_runtime.py"
    test_path = repo / "tests" / "test_auto_improve_iteration_runtime.py"

    replace_once(
        runtime_path,
        """def _existing_run_telemetry(vault: Path, run_id: str) -> dict:
    existing_report = load_optional_json(vault / run_rel(run_id, "run-telemetry.json"))
    return existing_report if isinstance(existing_report, dict) else {}


def _load_repo_relative_json(vault: Path, rel_path: object) -> dict | None:
""",
        """def _load_repo_relative_json(vault: Path, rel_path: object) -> dict | None:
""",
    )
    replace_once(
        runtime_path,
        """    existing_report = _existing_run_telemetry(request.vault, request.run_id)
""",
        """    existing_report = load_optional_json(
        request.vault / run_rel(request.run_id, "run-telemetry.json")
    ) or {}
""",
    )
    replace_once(
        test_path,
        """            self.assertEqual(payload["source_candidate_id"], "candidate-1")
            self.assertEqual(payload["metadata"], existing_metadata)
""",
        """            self.assertEqual(payload["source_candidate_id"], "candidate-1")
            self.assertEqual(payload["metadata"], existing_metadata)
            runtime_source = (
                Path(__file__).resolve().parents[1]
                / "ops"
                / "scripts"
                / "auto_improve_iteration_persistence_runtime.py"
            ).read_text(encoding="utf-8")
            self.assertNotIn("_existing_run_telemetry", runtime_source)
""",
    )


if __name__ == "__main__":
    main()
