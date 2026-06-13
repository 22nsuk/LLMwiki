from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.mechanism.goal_runtime_json_loader_runtime import (
    load_json_object_from_path,
    load_json_object_from_vault,
)


class GoalRuntimeJsonLoaderTests(unittest.TestCase):
    def test_load_json_object_from_path_returns_empty_dict_for_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payload = load_json_object_from_path(Path(temp_dir) / "missing.json")
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
