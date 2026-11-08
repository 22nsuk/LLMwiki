from __future__ import annotations

import shutil
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


@pytest.mark.parametrize("action", ["codeql", "checkout"])
def test_bot_workflow_update_needs_no_second_pin_source(tmp_path: Path, action: str) -> None:
    shutil.copytree(REPO_ROOT / ".github", tmp_path / ".github")
    old = PINNED_CI_CHECKOUT_ACTION.split("@")[1] if action == "checkout" else next(
        line.split("@")[1].split()[0]
        for line in (tmp_path / ".github/workflows/codeql.yml").read_text().splitlines()
        if "github/codeql-action/init@" in line
    )
    for path in (tmp_path / ".github").rglob("*.yml"):
        path.write_text(path.read_text().replace(old, "1" * 40))
    before = {p: p.read_bytes() for p in (tmp_path / ".github").rglob("*.yml")}
    assert validate_workflow_action_pins(tmp_path) == []
    assert validate_workflow_action_pins(tmp_path, write=True) == []
    assert {p: p.read_bytes() for p in before} == before


@pytest.mark.parametrize("mutation", ["split", "tag", "comment", "uncovered", "flow"])
def test_invalid_workflow_pins_fail_without_rewriting(tmp_path: Path, mutation: str) -> None:
    shutil.copytree(REPO_ROOT / ".github", tmp_path / ".github")
    path = tmp_path / ".github/workflows/codeql.yml"
    original = path.read_text()
    line = next(line for line in original.splitlines() if "github/codeql-action/init@" in line)
    if mutation == "split":
        replacement = line.split("@")[0] + "@" + "2" * 40 + " # v99.0.0"
    elif mutation == "tag":
        replacement = line.split("@")[0] + "@v4 # v4"
    elif mutation == "comment":
        replacement = line.split("#")[0]
    elif mutation == "uncovered":
        replacement = line.replace("github/codeql-action/init", "unregistered/action")
    else:
        replacement = '      - {uses: "unregistered/action@v1"}'
    path.write_text(original.replace(line, replacement))
    before = path.read_bytes()
    assert validate_workflow_action_pins(tmp_path)
    assert validate_workflow_action_pins(tmp_path, write=True)
    assert path.read_bytes() == before


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
