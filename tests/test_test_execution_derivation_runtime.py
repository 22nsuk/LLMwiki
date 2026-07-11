from __future__ import annotations

import datetime as dt
import hashlib
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from ops.scripts.core.command_runtime import TimedProcessResult
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.test.test_execution_derivation_runtime import (
    build_collection_manifest,
    collection_manifest_reference_is_current,
    derive_subset_summary,
    load_collection_manifest_digest,
    nodeids_sha256,
    parse_junit_testcases,
    serialized_report_sha256,
    subset_summary_parity,
    write_collection_manifest,
)
from ops.scripts.test.test_execution_summary import build_report
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = [pytest.mark.report_contract, pytest.mark.report_contract_core]
REPO_ROOT = Path(__file__).resolve().parents[1]
FIXED_CONTEXT = RuntimeContext(
    display_timezone=dt.UTC,
    clock=lambda: dt.datetime(2026, 7, 12, 0, 0, tzinfo=dt.UTC),
)


def _lifecycle() -> dict[str, object]:
    return {
        "status": "pass",
        "checked_at": "2026-07-12T00:00:00Z",
        "actual_deselected_count": 0,
        "max_allowed_deselected_count": 0,
        "over_budget": False,
        "expired_count": 0,
        "release_blocking_count": 0,
        "missing_lifecycle_count": 0,
        "duplicate_policy_entry_count": 0,
        "unused_policy_entry_count": 0,
        "risk_owner": "",
        "expires_at": "",
        "count_increase_gate_effect": "none",
        "expiry_gate_effect": "none",
        "next_action": "none",
        "blockers": [],
    }


def _junit_xml() -> bytes:
    return b"""<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="2">
  <testcase classname="tests.test_sample" name="test_function[value-a]" time="0.001" />
  <testcase classname="tests.test_sample.TestGroup" name="test_method[value-b]" time="0.001" />
</testsuite></testsuites>
"""


def test_xunit2_classname_name_and_parametrized_names_map_to_canonical_nodeids() -> (
    None
):
    nodeids = [
        "tests/test_sample.py::test_function[value-a]",
        "tests/test_sample.py::TestGroup::test_method[value-b]",
    ]

    evidence = parse_junit_testcases(_junit_xml(), expected_nodeids=nodeids)

    assert evidence["testcase_count"] == 2
    assert evidence["counts"]["passed"] == 2
    assert list(evidence["outcomes"]) == sorted(nodeids)


@pytest.mark.parametrize(
    ("xml", "message"),
    [
        (
            b'<testsuite><testcase classname="tests.test_sample" name="test_function[value-a]" /></testsuite>',
            "missing=",
        ),
        (
            b'<testsuite><testcase classname="tests.test_sample" name="test_function[value-a]" />'
            b'<testcase classname="tests.test_sample" name="test_function[value-a]" /></testsuite>',
            "duplicate=",
        ),
        (
            b'<testsuite><testcase classname="tests.test_sample" name="test_function[value-a]" />'
            b'<testcase classname="tests.test_other" name="test_extra" /></testsuite>',
            "unmatched_or_extra=",
        ),
        (
            b'<testsuite><testcase name="test_function[value-a]" /></testsuite>',
            "missing xunit2",
        ),
    ],
)
def test_junit_authority_fails_closed_for_missing_duplicate_unmatched_or_malformed_cases(
    xml: bytes, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_junit_testcases(
            xml,
            expected_nodeids=[
                "tests/test_sample.py::test_function[value-a]",
                "tests/test_sample.py::TestGroup::test_method[value-b]",
            ],
        )


def _derived_fixture(vault: Path) -> tuple[dict, dict, dict, dict]:
    nodeids = [
        "tests/test_sample.py::test_function[value-a]",
        "tests/test_sample.py::TestGroup::test_method[value-b]",
    ]
    full_manifest = build_collection_manifest(
        vault,
        suite="full-shard-1",
        semantic_command="-m pytest",
        nodeids=nodeids,
        selection_kind="full_suite",
        deselected_tests=[],
        deselection_lifecycle=_lifecycle(),
        context=FIXED_CONTEXT,
    )
    digest = {
        "status": "collected",
        "command": "python -m pytest --collect-only",
        "nodeid_count": 2,
        "sha256": nodeids_sha256(nodeids),
        "reason": "",
        "manifest_nodeids_sha256": nodeids_sha256(nodeids),
        "manifest_sha256": serialized_report_sha256(full_manifest),
        "source_tree_fingerprint": full_manifest["source_tree_fingerprint"],
        "source_revision": full_manifest["source_revision"],
    }
    result = TimedProcessResult(
        args=["python", "-m", "pytest"],
        returncode=0,
        stdout="2 passed in 0.01s",
        stderr="",
        timed_out=False,
        timeout_seconds=30,
        termination_reason="completed",
    )
    full_summary = build_report(
        vault,
        command=["python", "-m", "pytest"],
        result=result,
        duration_ms=10,
        suite="full-shard-1",
        collect_nodeids=True,
        collect_nodeid_digest=digest,
        context=FIXED_CONTEXT,
    )
    junit_evidence = parse_junit_testcases(_junit_xml(), expected_nodeids=nodeids)
    full_summary["evidence_artifacts"] = [
        {
            "kind": "junit_xml",
            "path": "build/release-payloads/full.junit.xml",
            "exists": True,
            "size_bytes": len(_junit_xml()),
            "sha256": hashlib.sha256(_junit_xml()).hexdigest(),
            "source": "pytest_junit_xml",
        }
    ]
    selected_manifest = build_collection_manifest(
        vault,
        suite="report-contract-summary",
        semantic_command="-m pytest -m report_contract_core -p no:cacheprovider",
        nodeids=[nodeids[0]],
        selection_kind="selector_subset",
        deselected_tests=[],
        deselection_lifecycle=_lifecycle(),
        context=FIXED_CONTEXT,
    )
    derived = derive_subset_summary(
        full_summary, junit_evidence, full_manifest, selected_manifest
    )
    return derived, full_summary, full_manifest, selected_manifest


def test_collection_manifest_and_derived_summary_are_schema_backed_and_deterministic(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)

    derived, _, full_manifest, _ = _derived_fixture(vault)

    assert (
        validate_with_schema(
            full_manifest,
            load_schema(
                REPO_ROOT / "ops/schemas/test-execution-collection-manifest.schema.json"
            ),
        )
        == []
    )
    assert (
        validate_with_schema(
            derived,
            load_schema(REPO_ROOT / "ops/schemas/test-execution-summary.schema.json"),
        )
        == []
    )
    assert derived["evidence_origin"] == "derived_full_suite"
    assert derived["counts"]["passed"] == 1
    assert derived["pytest_collect_nodeid_digest"]["nodeid_count"] == 1
    assert derived["derivation"]["full_collection_nodeid_count"] == 2
    assert derived["derivation"]["selected_collection_nodeid_count"] == 1


def test_collection_manifest_reference_rejects_input_digest_drift(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    schema_name = "test-execution-collection-manifest.schema.json"
    shutil.copyfile(
        REPO_ROOT / "ops/schemas" / schema_name,
        vault / "ops/schemas" / schema_name,
    )
    manifest = build_collection_manifest(
        vault,
        suite="full-shard-1",
        semantic_command="-m pytest",
        nodeids=["tests/test_sample.py::test_ok"],
        selection_kind="full_suite",
        deselected_tests=[],
        deselection_lifecycle=_lifecycle(),
        context=FIXED_CONTEXT,
    )
    identity = write_collection_manifest(
        vault, manifest, "build/release-payloads/full.collection.json"
    )
    digest = {
        **identity,
        "nodeid_count": 1,
        "sha256": manifest["nodeids_sha256"],
    }

    assert collection_manifest_reference_is_current(vault, digest) is True
    loaded_digest = load_collection_manifest_digest(vault, identity["manifest_path"])
    assert loaded_digest["sha256"] == manifest["nodeids_sha256"]
    assert loaded_digest["manifest_sha256"] == identity["manifest_sha256"]

    path = vault / identity["manifest_path"]
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '"nodeid_count": 1', '"nodeid_count": 2'
        ),
        encoding="utf-8",
    )
    assert collection_manifest_reference_is_current(vault, digest) is False


def test_derivation_rejects_parent_and_input_digest_drift(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    _, full_summary, full_manifest, selected_manifest = _derived_fixture(vault)
    junit_evidence = parse_junit_testcases(
        _junit_xml(), expected_nodeids=full_manifest["nodeids"]
    )

    drifted = deepcopy(selected_manifest)
    drifted["source_tree_fingerprint"] = "drifted-tree"
    with pytest.raises(ValueError, match="source_tree_fingerprint drift"):
        derive_subset_summary(full_summary, junit_evidence, full_manifest, drifted)

    drifted_junit = deepcopy(junit_evidence)
    drifted_junit["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="JUnit digest drift"):
        derive_subset_summary(
            full_summary, drifted_junit, full_manifest, selected_manifest
        )


def test_pure_derivation_api_accepts_exact_selected_nodeids(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    _, full_summary, full_manifest, _ = _derived_fixture(vault)
    junit_evidence = parse_junit_testcases(
        _junit_xml(), expected_nodeids=full_manifest["nodeids"]
    )

    derived = derive_subset_summary(
        full_summary,
        junit_evidence,
        full_manifest,
        ["tests/test_sample.py::test_function[value-a]"],
    )

    assert derived["pytest_collect_nodeid_digest"]["nodeid_count"] == 1
    assert derived["semantic_command"].startswith("exact-nodeid-selection:")


def test_direct_parity_is_exact_for_status_counts_nodeids_and_deselection(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    derived, _, _, _ = _derived_fixture(vault)
    direct = deepcopy(derived)
    direct.pop("evidence_origin")
    direct.pop("derivation")
    direct["summary_mode"] = "single"

    assert subset_summary_parity(derived, direct)["status"] == "pass"

    direct["counts"]["warnings"] = 1
    parity = subset_summary_parity(derived, direct)
    assert parity["status"] == "fail"
    assert "derived/direct parity mismatch: counts" in parity["blockers"]
