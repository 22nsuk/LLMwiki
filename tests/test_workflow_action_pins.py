from __future__ import annotations

import unittest
from pathlib import Path

import pytest

from ops.scripts.core.workflow_action_pins import validate_workflow_action_pins
from tests.workflow_static_helpers import (
    PINNED_CI_CHECKOUT_ACTION,
    PINNED_RELEASE_SECURITY_CHECKOUT_ACTION,
    WORKFLOW_ACTION_PIN_RULES,
    load_workflow,
    workflow_job,
    workflow_step,
)

pytestmark = [
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
    pytest.mark.schema_static_smoke,
]

REPO_ROOT = Path(__file__).resolve().parents[1]


class WorkflowActionPinsTests(unittest.TestCase):
    def test_workflow_action_pins_match_helper_catalog(self) -> None:
        self.assertEqual(validate_workflow_action_pins(REPO_ROOT), [])

    def test_checkout_pins_keep_ci_and_release_security_scopes_distinct(self) -> None:
        ci = load_workflow(REPO_ROOT / ".github/workflows/ci.yml")
        release = load_workflow(REPO_ROOT / ".github/workflows/release.yml")
        codeql = load_workflow(REPO_ROOT / ".github/workflows/codeql.yml")

        self.assertEqual(
            workflow_step(workflow_job(ci, "test-tier"), "Checkout").get("uses"),
            PINNED_CI_CHECKOUT_ACTION,
        )
        self.assertEqual(
            workflow_step(workflow_job(release, "verify-clean-release"), "Checkout").get("uses"),
            PINNED_RELEASE_SECURITY_CHECKOUT_ACTION,
        )
        self.assertEqual(
            workflow_step(workflow_job(codeql, "analyze"), "Checkout").get("uses"),
            PINNED_RELEASE_SECURITY_CHECKOUT_ACTION,
        )

    def test_pin_rules_cover_only_declared_paths(self) -> None:
        for rule in WORKFLOW_ACTION_PIN_RULES:
            with self.subTest(rule=rule["id"]):
                self.assertTrue(rule["paths"])
                for path in rule["paths"]:
                    self.assertTrue((REPO_ROOT / str(path)).is_file())
