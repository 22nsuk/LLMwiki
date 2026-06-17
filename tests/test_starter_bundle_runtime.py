from __future__ import annotations

import unittest
from pathlib import Path

from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.starter_bundle_runtime import (
    DEFAULT_STARTER_BUNDLE,
    SYSTEM_MECHANISM_STARTER_BUNDLE,
    starter_bundle,
    starter_bundle_allowed_promotion_input_paths,
    starter_bundle_for_artifact_dir,
    starter_bundle_path,
    starter_bundle_registry,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class StarterBundleRuntimeTest(unittest.TestCase):
    def test_registry_exposes_canonical_bundle_contracts(self) -> None:
        policy, _ = load_policy(REPO_ROOT)

        registry = starter_bundle_registry(policy)

        self.assertEqual(set(registry), {DEFAULT_STARTER_BUNDLE, SYSTEM_MECHANISM_STARTER_BUNDLE})
        self.assertEqual(registry[DEFAULT_STARTER_BUNDLE].path, "ops/templates")
        self.assertEqual(registry[SYSTEM_MECHANISM_STARTER_BUNDLE].path, "ops/templates/mechanism-run")

    def test_bundle_lookup_and_path_resolution_follow_policy(self) -> None:
        policy, _ = load_policy(REPO_ROOT)

        planning_bundle = starter_bundle(policy, DEFAULT_STARTER_BUNDLE)
        mechanism_bundle = starter_bundle_for_artifact_dir(policy, "ops/templates/mechanism-run")

        self.assertEqual(planning_bundle.phase, "starter")
        self.assertIsNotNone(mechanism_bundle)
        self.assertEqual(mechanism_bundle.name, SYSTEM_MECHANISM_STARTER_BUNDLE)
        self.assertEqual(
            starter_bundle_path(REPO_ROOT, policy, DEFAULT_STARTER_BUNDLE),
            (REPO_ROOT / "ops" / "templates").resolve(),
        )
        self.assertIsNone(starter_bundle_for_artifact_dir(policy, "runs/run-123"))

    def test_mechanism_bundle_placeholder_inputs_extend_expected_run_local_paths(self) -> None:
        policy, _ = load_policy(REPO_ROOT)
        mechanism_bundle = starter_bundle(policy, SYSTEM_MECHANISM_STARTER_BUNDLE)

        allowed = starter_bundle_allowed_promotion_input_paths(
            mechanism_bundle,
            "run_ledger",
            expected_path="ops/templates/mechanism-run/run-ledger.json",
        )

        self.assertEqual(
            allowed,
            [
                "ops/templates/mechanism-run/run-ledger.json",
                "runs/<run-id>/run-ledger.json",
            ],
        )


if __name__ == "__main__":
    unittest.main()
