from __future__ import annotations

import json
from pathlib import Path

from ops.scripts.test.test_execution_deselection_runtime import (
    deselection_lifecycle,
    load_deselection_policy,
    pytest_stdout_deselected_count,
    structured_deselected_tests,
)
from tests.minimal_vault_runtime import seed_minimal_vault


def _write_policy(vault: Path) -> None:
    policy_path = vault / "ops" / "policies" / "test-deselections.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/test-deselection-policy.schema.json",
                "policy_kind": "test_deselection_policy",
                "deselection_budget": {
                    "max_count": 1,
                    "risk_owner": "release",
                    "expires_at": "2026-12-31T00:00:00Z",
                    "count_increase_gate_effect": "fail",
                    "expiry_gate_effect": "fail",
                },
                "deselected_tests": [
                    {
                        "nodeid": "tests/test_sample.py::test_two",
                        "reason": "known flaky",
                        "policy_ref": "ops/policies/test-deselections.json#sample",
                        "risk_owner": "release",
                        "expires_at": "2026-12-31T00:00:00Z",
                        "release_blocking": False,
                        "expected_to_pass_after_refresh": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_structured_deselected_tests_loads_policy_entries(tmp_path: Path) -> None:
    seed_minimal_vault(tmp_path)
    _write_policy(tmp_path)

    entries = structured_deselected_tests(
        ["python", "-m", "pytest", "--deselect=tests/test_sample.py::test_two"],
        vault=tmp_path,
        deselection_policy_path="ops/policies/test-deselections.json",
    )

    assert set(load_deselection_policy(tmp_path, "ops/policies/test-deselections.json")) == {
        "tests/test_sample.py::test_two"
    }
    assert entries[0]["policy_ref"] == "ops/policies/test-deselections.json#sample"
    assert entries[0]["release_blocking"] is False


def test_deselection_lifecycle_blocks_expired_or_over_budget_entries() -> None:
    lifecycle = deselection_lifecycle(
        [
            {
                "nodeid": "tests/test_sample.py::test_two",
                "risk_owner": "release",
                "expires_at": "2026-01-01T00:00:00Z",
                "release_blocking": False,
            },
            {
                "nodeid": "tests/test_sample.py::test_three",
                "risk_owner": "",
                "expires_at": "",
                "release_blocking": True,
            },
        ],
        generated_at="2026-04-29T00:00:00Z",
        policy_payload={
            "deselection_budget": {
                "max_count": 1,
                "expires_at": "2026-01-01T00:00:00Z",
            },
            "deselected_tests": [{"nodeid": "tests/test_sample.py::test_two"}],
        },
    )

    codes = {blocker["code"] for blocker in lifecycle["blockers"]}
    assert lifecycle["status"] == "fail"
    assert "expired_deselection" in codes
    assert "expired_deselection_budget" in codes
    assert "deselection_budget_exceeded" in codes
    assert "missing_deselection_lifecycle" in codes


def test_pytest_stdout_deselected_count_reads_highest_summary_count() -> None:
    assert pytest_stdout_deselected_count("= 1 passed, 2 deselected =\n= 3 deselected =") == 3
