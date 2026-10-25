from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.test.test_execution_deselection_runtime import (
    deselection_lifecycle,
    load_deselection_policy,
    load_deselection_policy_payload,
    pytest_stdout_deselected_count,
    structured_deselected_tests,
)
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

POLICY_REL_PATH = "ops/policies/report-contract-deselections.json"


def _fixed_context(year: int) -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(year, 1, 1, tzinfo=dt.UTC),
    )


def _policy_entry() -> dict[str, object]:
    return {
        "nodeid": "tests/test_sample.py::test_two",
        "reason": "known flaky",
        "policy_ref": "ops/policies/test-deselections.json#sample",
        "risk_owner": "release",
        "expires_at": "2200-01-01T00:00:00Z",
        "release_blocking": False,
        "expected_to_pass_after_refresh": True,
    }


def _write_policy_payload(vault: Path, payload: dict[str, object]) -> None:
    policy_path = vault / "ops" / "policies" / "test-deselections.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(json.dumps(payload), encoding="utf-8")


def _write_policy(vault: Path) -> None:
    _write_policy_payload(
        vault,
        {
            "$schema": "ops/schemas/test-deselection-policy.schema.json",
            "policy_kind": "test_deselection_policy",
            "deselection_budget": {
                "max_count": 1,
                "risk_owner": "release",
                "expires_at": "2200-01-01T00:00:00Z",
                "count_increase_gate_effect": "fail",
                "expiry_gate_effect": "fail",
            },
            "deselected_tests": [_policy_entry()],
        },
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
        generated_at=_fixed_context(2026).isoformat_z(),
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
    assert "release_blocking_deselection" in codes


def test_canonical_zero_deselection_policy_is_permanent_at_future_clock() -> None:
    policy = load_deselection_policy_payload(REPO_ROOT, POLICY_REL_PATH)

    lifecycle = deselection_lifecycle(
        [],
        generated_at=_fixed_context(2200).isoformat_z(),
        policy_payload=policy,
    )

    assert "expires_at" not in policy["deselection_budget"]
    assert lifecycle["status"] == "pass"
    assert lifecycle["checked_at"] == "2200-01-01T00:00:00Z"

    legacy_zero_policy = {
        **policy,
        "deselection_budget": {
            **policy["deselection_budget"],
            "expires_at": "2000-01-01T00:00:00Z",
        },
    }
    assert (
        deselection_lifecycle(
            [],
            generated_at=_fixed_context(2200).isoformat_z(),
            policy_payload=legacy_zero_policy,
        )["status"]
        == "pass"
    )


@pytest.mark.parametrize(
    ("max_count", "policy_entries"),
    [(1, []), (0, [_policy_entry()])],
    ids=("non_zero_budget", "non_empty_policy"),
)
def test_schema_requires_budget_expiry_when_deselection_budget_is_active(
    tmp_path: Path,
    max_count: int,
    policy_entries: list[dict[str, object]],
) -> None:
    seed_minimal_vault(tmp_path)
    _write_policy_payload(
        tmp_path,
        {
            "$schema": "ops/schemas/test-deselection-policy.schema.json",
            "policy_kind": "test_deselection_policy",
            "deselection_budget": {
                "max_count": max_count,
                "risk_owner": "release",
                "count_increase_gate_effect": "fail",
                "expiry_gate_effect": "fail",
            },
            "deselected_tests": policy_entries,
        },
    )

    with pytest.raises(ValueError, match="expires_at"):
        load_deselection_policy_payload(
            tmp_path,
            "ops/policies/test-deselections.json",
        )


@pytest.mark.parametrize(
    "policy_payload",
    [
        {
            "deselection_budget": {"max_count": 1},
            "deselected_tests": [],
        },
        {
            "deselection_budget": {"max_count": 0},
            "deselected_tests": [_policy_entry()],
        },
    ],
    ids=("non_zero_budget", "non_empty_policy"),
)
def test_runtime_requires_budget_expiry_when_policy_is_active(
    policy_payload: dict[str, object],
) -> None:
    lifecycle = deselection_lifecycle(
        [],
        generated_at=_fixed_context(2100).isoformat_z(),
        policy_payload=policy_payload,
    )

    codes = {blocker["code"] for blocker in lifecycle["blockers"]}
    assert lifecycle["status"] == "fail"
    assert "missing_deselection_budget_expiry" in codes


def test_actual_deselection_activates_expiry_and_exceeds_zero_budget() -> None:
    policy = load_deselection_policy_payload(REPO_ROOT, POLICY_REL_PATH)

    lifecycle = deselection_lifecycle(
        [_policy_entry()],
        generated_at=_fixed_context(2100).isoformat_z(),
        policy_payload=policy,
    )

    codes = {blocker["code"] for blocker in lifecycle["blockers"]}
    assert lifecycle["status"] == "fail"
    assert lifecycle["over_budget"] is True
    assert "missing_deselection_budget_expiry" in codes
    assert "deselection_budget_exceeded" in codes


def test_pytest_stdout_deselected_count_reads_highest_summary_count() -> None:
    assert pytest_stdout_deselected_count("= 1 passed, 2 deselected =\n= 3 deselected =") == 3
