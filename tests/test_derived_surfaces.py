from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.derived_surfaces import (
    check_target_lines,
    currentness_output_paths,
    currentness_path_patterns,
    derived_surfaces_mk_is_current,
    load_manifest,
    render_derived_surfaces_mk,
    sync_target_lines,
    write_derived_surfaces_mk,
)
from tests.makefile_static_helpers import (
    _assert_phony_targets,
    _makefile_text,
    _recipe_lines,
    _target_block,
)
from tests.minimal_vault_runtime import REPO_ROOT

pytestmark = [
    pytest.mark.public,
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
    pytest.mark.schema_static_smoke,
    pytest.mark.default_test_boundary,
]


class DerivedSurfacesTests(unittest.TestCase):
    def test_manifest_renders_sync_derived_internal_targets(self) -> None:
        manifest = load_manifest(REPO_ROOT)
        text = _makefile_text()
        aggregate = manifest["aggregate"]

        self.assertEqual(
            _recipe_lines(text, str(aggregate["internal_sync_target"])),
            sync_target_lines(manifest),
        )
        self.assertEqual(
            _recipe_lines(text, str(aggregate["internal_check_target"])),
            check_target_lines(manifest),
        )
        self.assertNotIn(
            "generated-artifact-converge",
            _target_block(text, str(aggregate["internal_check_target"])),
        )

    def test_sync_derived_wrappers_call_generator_then_manifest_internal_targets(self) -> None:
        manifest = load_manifest(REPO_ROOT)
        text = _makefile_text()
        aggregate = manifest["aggregate"]

        self.assertEqual(
            _recipe_lines(text, str(aggregate["sync_target"])),
            [
                "$(MAKE) derived-surfaces-sync",
                f"$(MAKE) {aggregate['internal_sync_target']}",
            ],
        )
        self.assertEqual(
            _recipe_lines(text, str(aggregate["check_target"])),
            [
                "$(MAKE) derived-surfaces-sync-check",
                f"$(MAKE) {aggregate['internal_check_target']}",
            ],
        )

    def test_makefile_includes_generated_derived_surface_fragment(self) -> None:
        self.assertIn("-include $(DERIVED_SURFACES_MK_OUT)", _makefile_text())

    def test_derived_surface_aggregate_targets_are_phony(self) -> None:
        manifest = load_manifest(REPO_ROOT)
        text = _makefile_text()
        aggregate = manifest["aggregate"]

        _assert_phony_targets(
            self,
            text,
            (
                "derived-surfaces-sync",
                "derived-surfaces-sync-check",
                str(aggregate["sync_target"]),
                str(aggregate["check_target"]),
                str(aggregate["internal_sync_target"]),
                str(aggregate["internal_check_target"]),
            ),
        )

    def test_declared_targets_exist_and_are_phony(self) -> None:
        manifest = load_manifest(REPO_ROOT)
        text = _makefile_text()
        phony_block = _target_block(text, ".PHONY")

        for surface in manifest["surfaces"]:
            if not surface["include_in_sync_derived"]:
                continue
            for role in ("sync_target", "check_target"):
                target = str(surface[role])
                with self.subTest(surface=surface["surface_id"], target=target):
                    _target_block(text, target)
                    self.assertIn(target, phony_block)

    def test_generated_make_fragment_matches_manifest(self) -> None:
        manifest = load_manifest(REPO_ROOT)
        expected = render_derived_surfaces_mk(manifest)
        actual = (REPO_ROOT / "mk" / "derived-surfaces.generated.mk").read_text(
            encoding="utf-8"
        )

        self.assertEqual(actual, expected)

    def test_makefile_defaults_match_manifest_paths(self) -> None:
        manifest = load_manifest(REPO_ROOT)
        text = _makefile_text()

        self.assertIn("DERIVED_SURFACES_MANIFEST ?= ops/policies/derived-surfaces.json", text)
        self.assertIn(
            f"DERIVED_SURFACES_MK_OUT ?= {manifest['generated_make_fragment']['path']}",
            text,
        )

    def test_currentness_output_paths_are_derived_from_manifest_outputs(self) -> None:
        manifest = load_manifest(REPO_ROOT)
        expected_paths = [str(manifest["generated_make_fragment"]["path"])]
        for surface in manifest["surfaces"]:
            if not surface["include_in_sync_derived"]:
                continue
            expected_paths.extend(
                str(output_path)
                for output_path in surface["tracked_outputs"]
                if not any(char in str(output_path) for char in "*?[")
            )

        self.assertEqual(
            currentness_output_paths(manifest),
            list(dict.fromkeys(expected_paths)),
        )

    def test_currentness_output_paths_skip_globs_and_dedupe(self) -> None:
        manifest = {
            "generated_make_fragment": {"path": "mk/derived-surfaces.generated.mk"},
            "surfaces": [
                {
                    "include_in_sync_derived": True,
                    "tracked_outputs": [
                        "pytest.ini",
                        ".github/workflows/*.yml",
                        "pytest.ini",
                        "docs/release?.md",
                    ],
                },
                {
                    "include_in_sync_derived": False,
                    "tracked_outputs": ["ignored-by-aggregate.txt"],
                },
                {
                    "include_in_sync_derived": True,
                    "tracked_outputs": [
                        "ops/script-output-surfaces.json",
                        "mk/derived-surfaces.generated.mk",
                    ],
                },
            ],
        }

        self.assertEqual(
            currentness_output_paths(manifest),
            [
                "mk/derived-surfaces.generated.mk",
                "pytest.ini",
                "ops/script-output-surfaces.json",
            ],
        )

    def test_currentness_path_patterns_include_sources_and_tracked_output_globs(
        self,
    ) -> None:
        manifest = {
            "generated_make_fragment": {"path": "mk/derived-surfaces.generated.mk"},
            "surfaces": [
                {
                    "include_in_sync_derived": True,
                    "source_paths": [
                        "ops/test-lane-registry.json",
                        "ops/scripts/**/*.py",
                    ],
                    "tracked_outputs": [
                        "pytest.ini",
                        ".github/workflows/*.yml",
                    ],
                },
                {
                    "include_in_sync_derived": False,
                    "source_paths": ["ignored-source.json"],
                    "tracked_outputs": ["ignored-output.json"],
                },
                {
                    "include_in_sync_derived": True,
                    "source_paths": ["ops/test-lane-registry.json"],
                    "tracked_outputs": ["mk/derived-surfaces.generated.mk"],
                },
            ],
        }

        self.assertEqual(
            currentness_path_patterns(manifest),
            [
                "mk/derived-surfaces.generated.mk",
                "ops/test-lane-registry.json",
                "ops/scripts/**/*.py",
                "pytest.ini",
                ".github/workflows/*.yml",
            ],
        )

    def test_write_and_check_detect_stale_generated_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            manifest_path = vault / "ops" / "policies" / "derived-surfaces.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(
                (REPO_ROOT / "ops" / "policies" / "derived-surfaces.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            out_path = vault / "mk" / "derived-surfaces.generated.mk"
            out_path.parent.mkdir(parents=True)
            out_path.write_text("# stale\n", encoding="utf-8")

            self.assertFalse(derived_surfaces_mk_is_current(vault))
            self.assertEqual(write_derived_surfaces_mk(vault), out_path)
            self.assertTrue(derived_surfaces_mk_is_current(vault))

    def test_manifest_rejects_duplicate_surface_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            manifest_path = vault / "ops" / "policies" / "derived-surfaces.json"
            manifest_path.parent.mkdir(parents=True)
            manifest = copy.deepcopy(load_manifest(REPO_ROOT))
            manifest["surfaces"][1]["surface_id"] = manifest["surfaces"][0]["surface_id"]
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "duplicate derived surface id"):
                load_manifest(vault)

    def test_manifest_rejects_cross_role_target_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            manifest_path = vault / "ops" / "policies" / "derived-surfaces.json"
            manifest_path.parent.mkdir(parents=True)
            manifest = copy.deepcopy(load_manifest(REPO_ROOT))
            manifest["surfaces"][1]["check_target"] = manifest["surfaces"][0][
                "sync_target"
            ]
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "duplicate derived surface target"):
                load_manifest(vault)

    def test_manifest_rejects_invalid_paths_and_empty_source_or_output_contracts(
        self,
    ) -> None:
        cases = [
            ("source_paths", ["/tmp/private-source.py"], None),
            ("source_paths", ["ops\\..\\private-source.py"], None),
            ("source_paths", [], None),
            ("tracked_outputs", [], []),
        ]
        for field, value, local_outputs in cases:
            with (
                self.subTest(field=field, value=value),
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                vault = Path(temp_dir)
                manifest_path = vault / "ops" / "policies" / "derived-surfaces.json"
                manifest_path.parent.mkdir(parents=True)
                manifest = copy.deepcopy(load_manifest(REPO_ROOT))
                manifest["surfaces"][0][field] = value
                if local_outputs is not None:
                    manifest["surfaces"][0]["local_outputs"] = local_outputs
                manifest_path.write_text(
                    json.dumps(manifest, indent=2) + "\n",
                    encoding="utf-8",
                )

                with self.assertRaises(ValueError):
                    load_manifest(vault)

    def test_manifest_rejects_generator_module_not_owned_by_make_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            manifest_path = vault / "ops" / "policies" / "derived-surfaces.json"
            manifest_path.parent.mkdir(parents=True)
            manifest = copy.deepcopy(load_manifest(REPO_ROOT))
            manifest["surfaces"] = [
                {
                    "surface_id": "sample",
                    "description": "Sample generated fixture.",
                    "kind": "tracked_json",
                    "sync_target": "sample-sync",
                    "check_target": "sample-sync-check",
                    "generator_module": "ops.scripts.bad_generator",
                    "source_paths": ["ops/policies/sample.json"],
                    "tracked_outputs": ["ops/sample.json"],
                    "local_outputs": [],
                    "include_in_sync_derived": True,
                }
            ]
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            (vault / "Makefile").write_text(
                ".PHONY: derived-surfaces-sync derived-surfaces-sync-check "
                "sample-sync sample-sync-check\n"
                "derived-surfaces-sync:\n"
                "\t$(PYTHON) -m ops.scripts.core.derived_surfaces\n"
                "derived-surfaces-sync-check:\n"
                "\t$(PYTHON) -m ops.scripts.core.derived_surfaces --check\n"
                "sample-sync:\n"
                "\t$(PYTHON) -m ops.scripts.good_generator --out ops/sample.json\n"
                "sample-sync-check:\n"
                "\t$(PYTHON) -m ops.scripts.good_generator --check\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "sample.generator_module ops.scripts.bad_generator is not owned",
            ):
                load_manifest(vault)


if __name__ == "__main__":
    unittest.main()
