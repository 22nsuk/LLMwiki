from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.mechanism.goal_runtime_json_loader_runtime import (
    load_json_object_from_path,
    load_json_object_from_vault,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GOAL_RUNTIME_JSON_LOADER_MODULES = (
    "ops/scripts/mechanism/goal_runtime_run_admission.py",
    "ops/scripts/mechanism/goal_runtime_closeout.py",
    "ops/scripts/mechanism/goal_runtime_quarantine_preflight.py",
    "ops/scripts/mechanism/goal_runtime_stale_closeout.py",
    "ops/scripts/mechanism/goal_runtime_fixed_point_check.py",
    "ops/scripts/mechanism/goal_runtime_clean_transient.py",
)


class GoalRuntimeJsonLoaderTests(unittest.TestCase):
    def test_load_json_object_from_path_returns_empty_dict_for_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payload = load_json_object_from_path(Path(temp_dir) / "missing.json")
            self.assertEqual(payload, {})

    def test_load_json_object_from_path_returns_empty_dict_for_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "invalid.json"
            path.write_text("{not-json", encoding="utf-8")

            payload = load_json_object_from_path(path)

        self.assertEqual(payload, {})

    def test_load_json_object_from_path_returns_empty_dict_for_non_object_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "array.json"
            path.write_text('["not", "an", "object"]', encoding="utf-8")

            payload = load_json_object_from_path(path)

        self.assertEqual(payload, {})

    def test_load_json_object_from_path_returns_empty_dict_for_read_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payload = load_json_object_from_path(Path(temp_dir))

        self.assertEqual(payload, {})

    def test_load_json_object_from_vault_returns_dict_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            rel_path = "ops/reports/example.json"
            path = vault / rel_path
            path.parent.mkdir(parents=True)
            path.write_text('{"status": "pass"}', encoding="utf-8")

            payload = load_json_object_from_vault(vault, rel_path)
            self.assertEqual(payload, {"status": "pass"})

    def test_goal_runtime_cluster_uses_shared_json_loader(self) -> None:
        for rel_path in GOAL_RUNTIME_JSON_LOADER_MODULES:
            with self.subTest(rel_path=rel_path):
                source = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
                self.assertIn("goal_runtime_json_loader_runtime", source)
                self.assertNotIn("def _load_json_object", source)
