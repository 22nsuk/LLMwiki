from __future__ import annotations

import json
import unittest
from pathlib import Path

from ops.scripts.core.schema_runtime import load_schema, validate_with_schema

REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPO_ROOT / "ops" / "policies" / "distribution-profile-matrix.json"
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "distribution-profile-matrix.schema.json"


class DistributionProfileMatrixTests(unittest.TestCase):
    def _matrix(self) -> dict:
        return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

    def test_distribution_profile_matrix_validates_schema(self) -> None:
        payload = self._matrix()

        self.assertEqual(validate_with_schema(payload, load_schema(SCHEMA_PATH)), [])

    def test_release_profiles_do_not_allow_recursive_tmp(self) -> None:
        profiles = {item["profile_id"]: item for item in self._matrix()["profiles"]}

        for profile_id in ("source_content_package", "release_evidence_bundle", "public_code_mirror"):
            self.assertFalse(profiles[profile_id]["tmp_policy"]["tmp_recursive_allowed"])
            self.assertEqual(profiles[profile_id]["tmp_policy"]["allowed_tmp_prefixes"], [])

        self.assertEqual(
            profiles["review_full_snapshot"]["tmp_policy"]["allowed_tmp_prefixes"],
            ["tmp/codex-plan-review/"],
        )

    def test_generated_reports_are_source_excluded_and_evidence_included(self) -> None:
        profiles = {item["profile_id"]: item for item in self._matrix()["profiles"]}

        self.assertIn("ops/reports/", profiles["source_content_package"]["excluded_surfaces"])
        self.assertEqual(
            profiles["source_content_package"]["generated_artifact_policy"]["source_package"],
            "exclude",
        )
        self.assertEqual(
            profiles["release_evidence_bundle"]["generated_artifact_policy"]["evidence_bundle"],
            "include",
        )

    def test_public_code_mirror_keeps_private_corpus_out_of_scope(self) -> None:
        public_profile = {item["profile_id"]: item for item in self._matrix()["profiles"]}["public_code_mirror"]

        self.assertIn("ops/", public_profile["included_surfaces"])
        self.assertIn(".agents/skills/", public_profile["included_surfaces"])
        for private_surface in ("raw/", "wiki/", "system/", "runs/", "external-reports/"):
            self.assertIn(private_surface, public_profile["excluded_surfaces"])


if __name__ == "__main__":
    unittest.main()
