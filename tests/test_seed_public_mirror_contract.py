from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

import pytest
from ops.scripts.schema_runtime import load_schema, validate_with_schema

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "seed.schema.json"
SEED_REPORT_DIR = REPO_ROOT / "tests" / "fixtures" / "public-seed-reports"

# Path prefixes that are excluded from the public mirror and must not appear
# in seed artifacts so that seeds remain reproducible without private corpus.
SEED_FORBIDDEN_PREFIXES = (
    "external-reports/",
    "raw/",
    "runs/",
    "system/",
    "tmp/",
    "wiki/",
)


def _find_private_path_references(obj: Any, path: str = "$") -> list[str]:
    """Recursively find string values that start with forbidden private path prefixes."""
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            found.extend(_find_private_path_references(value, f"{path}.{key}"))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            found.extend(_find_private_path_references(item, f"{path}[{idx}]"))
    elif isinstance(obj, str):
        for prefix in SEED_FORBIDDEN_PREFIXES:
            if obj.startswith(prefix):
                found.append(f"{path}: {obj!r}")
                break
    return found


class SeedPublicMirrorContractTest(unittest.TestCase):
    def test_all_seed_reports_validate_against_schema(self) -> None:
        schema = load_schema(SEED_SCHEMA_PATH)
        seeds = sorted(SEED_REPORT_DIR.glob("seed-*.json"))
        self.assertTrue(seeds, f"No seed reports found in {SEED_REPORT_DIR}")
        for seed_path in seeds:
            with self.subTest(seed=seed_path.name):
                payload = json.loads(seed_path.read_text(encoding="utf-8"))
                errors = validate_with_schema(payload, schema)
                self.assertEqual(errors, [], f"Schema validation failed for {seed_path.name}")

    def test_all_seed_reports_contain_no_private_path_references(self) -> None:
        seeds = sorted(SEED_REPORT_DIR.glob("seed-*.json"))
        self.assertTrue(seeds, f"No seed reports found in {SEED_REPORT_DIR}")
        for seed_path in seeds:
            with self.subTest(seed=seed_path.name):
                payload = json.loads(seed_path.read_text(encoding="utf-8"))
                private_refs = _find_private_path_references(payload)
                self.assertEqual(
                    private_refs,
                    [],
                    f"Private path references found in {seed_path.name}",
                )


if __name__ == "__main__":
    unittest.main()
