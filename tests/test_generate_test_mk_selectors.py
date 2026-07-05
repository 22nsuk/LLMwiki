from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from ops.scripts.test.generate_test_mk_selectors import (
    DERIVED_ALIASES,
    PACK_MARK_EXPR_MAKE_VARIABLES,
    PACK_VARIABLES,
    render_test_selectors_mk,
)
from ops.scripts.test.test_lane_registry_runtime import load_registry, pack_mark_expr

pytestmark = [
    pytest.mark.public,
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
    pytest.mark.schema_static_smoke,
    pytest.mark.default_test_boundary,
]

REPO_ROOT = Path(__file__).resolve().parents[1]


def _temp_registry_vault(temp_root: Path) -> Path:
    (temp_root / "ops" / "schemas").mkdir(parents=True)
    shutil.copy2(
        REPO_ROOT / "ops" / "test-lane-registry.json",
        temp_root / "ops" / "test-lane-registry.json",
    )
    shutil.copy2(
        REPO_ROOT / "ops" / "schemas" / "test-lane-registry.schema.json",
        temp_root / "ops" / "schemas" / "test-lane-registry.schema.json",
    )
    return temp_root


class GenerateTestMkSelectorsTests(unittest.TestCase):
    def test_rendered_selector_fragment_is_derived_from_marker_packs(self) -> None:
        registry = load_registry(REPO_ROOT)
        rendered = render_test_selectors_mk(REPO_ROOT)

        for pack_id, variable in PACK_VARIABLES.items():
            with self.subTest(pack_id=pack_id, variable=variable):
                mark_expr_variable = PACK_MARK_EXPR_MAKE_VARIABLES[pack_id]
                self.assertIn(
                    f'{variable} ?= -m "$({mark_expr_variable})"',
                    rendered,
                )
                self.assertTrue(pack_mark_expr(registry, pack_id))

        for variable, value in DERIVED_ALIASES.items():
            with self.subTest(variable=variable):
                self.assertIn(f"{variable} ?= {value}", rendered)

    def test_projection_rejects_non_marker_pack(self) -> None:
        with TemporaryDirectory() as temp_dir:
            vault = _temp_registry_vault(Path(temp_dir))
            registry_path = vault / "ops" / "test-lane-registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))

            for pack in registry["derived_packs"]:
                if pack["pack_id"] == "fast_smoke":
                    pack["selection"]["mode"] = "explicit_selectors"
                    pack["selection"]["selectors"] = []
                    break
            else:  # pragma: no cover - protected by the repository registry
                raise AssertionError("missing fast_smoke pack")

            registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "fast_smoke selector projection requires marker_expression"):
                render_test_selectors_mk(vault)
