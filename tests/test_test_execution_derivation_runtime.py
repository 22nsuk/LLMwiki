from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from ops.scripts.core.artifact_freshness_runtime import (
    build_report as build_freshness_report,
)
from ops.scripts.core.command_runtime import TimedProcessResult
from ops.scripts.core.policy_runtime import (
    DEFAULT_POLICY_PATH,
    LOCAL_CORPUS_POLICY_PATH,
    load_policy,
    write_local_corpus_policy,
)
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.test.test_execution_derivation_runtime import (
    JUNIT_SUBTESTS_PASSED_PROPERTY,
    build_collection_manifest,
    collection_manifest_reference_is_current,
    collection_manifest_reference_is_rebindable,
    derive_subset_summary,
    load_collection_manifest_digest,
    nodeids_sha256,
    parse_junit_testcases,
    serialized_report_sha256,
    subset_summary_parity,
    validate_full_suite_evidence_bindings,
    write_collection_manifest,
)
from ops.scripts.test.test_execution_summary import (
    build_aggregate_report,
    build_report,
    write_report,
)
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
<testsuites><testsuite name="pytest" errors="0" failures="0" skipped="0" tests="2">
  <testcase classname="tests.test_sample" name="test_function[value-a]" time="0.001" />
  <testcase classname="tests.test_sample.TestGroup" name="test_method[value-b]" time="0.001" />
</testsuite></testsuites>
"""


def _junit_xml_with_subtests(
    *,
    first_property: str = "2",
    second_property: str = "1",
    tests: str = "5",
) -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="0" failures="0" skipped="0" tests="{tests}">
  <testcase classname="tests.test_sample" name="test_function[value-a]" time="0.001">
    <properties><property name="{JUNIT_SUBTESTS_PASSED_PROPERTY}" value="{first_property}" /></properties>
  </testcase>
  <testcase classname="tests.test_sample.TestGroup" name="test_method[value-b]" time="0.001">
    <properties><property name="{JUNIT_SUBTESTS_PASSED_PROPERTY}" value="{second_property}" /></properties>
  </testcase>
</testsuite></testsuites>
""".encode()


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
    assert evidence["subtests_passed"] == 0
    assert evidence["subtests_passed_by_nodeid"] == dict.fromkeys(sorted(nodeids), 0)


@pytest.mark.parametrize(
    "parameter_id",
    [
        pytest.param("a::b", id="double-colon"),
        pytest.param(r"        if b:\n", id="escaped-newline"),
        pytest.param(r"folder\file", id="windows-path-value"),
    ],
)
def test_xunit2_parametrized_name_preserves_parameter_id(parameter_id: str) -> None:
    nodeid = f"tests/test_param.py::test_value[{parameter_id}]"
    xml = (
        '<testsuite name="pytest" tests="1" errors="0" failures="0" skipped="0">'
        f'<testcase classname="tests.test_param" name="test_value[{parameter_id}]" />'
        "</testsuite>"
    )

    evidence = parse_junit_testcases(xml, expected_nodeids=[nodeid])

    assert evidence["outcomes"] == {nodeid: "passed"}


@pytest.mark.parametrize(
    "nodeid",
    [
        pytest.param(r"tests\test_param.py::test_value", id="windows-file-path"),
        pytest.param("/tests/test_param.py::test_value", id="absolute-file-path"),
        pytest.param("tests/test_param.py::test_value[a\nb]", id="literal-newline"),
        pytest.param("tests/test_param.py::test_value[a\rb]", id="literal-carriage-return"),
    ],
)
def test_collection_digest_rejects_noncanonical_paths_and_line_breaks(nodeid: str) -> None:
    with pytest.raises(ValueError, match="invalid canonical pytest nodeid"):
        nodeids_sha256([nodeid])


def test_xunit2_testcase_properties_account_for_passing_subtests_by_nodeid() -> None:
    nodeids = [
        "tests/test_sample.py::test_function[value-a]",
        "tests/test_sample.py::TestGroup::test_method[value-b]",
    ]

    evidence = parse_junit_testcases(
        _junit_xml_with_subtests(), expected_nodeids=nodeids
    )

    assert evidence["testcase_count"] == 2
    assert evidence["subtests_passed"] == 3
    assert evidence["subtests_passed_by_nodeid"] == {
        nodeids[0]: 2,
        nodeids[1]: 1,
    }


@pytest.mark.parametrize(
    ("xml", "message"),
    [
        pytest.param(
            _junit_xml_with_subtests().replace(
                f'<property name="{JUNIT_SUBTESTS_PASSED_PROPERTY}" value="1" />'.encode(),
                b"",
            ),
            "missing testcase property",
            id="missing-property",
        ),
        pytest.param(
            _junit_xml_with_subtests().replace(
                f'<property name="{JUNIT_SUBTESTS_PASSED_PROPERTY}" value="2" />'.encode(),
                (
                    f'<property name="{JUNIT_SUBTESTS_PASSED_PROPERTY}" value="2" />'
                    f'<property name="{JUNIT_SUBTESTS_PASSED_PROPERTY}" value="0" />'
                ).encode(),
            ),
            "duplicate",
            id="duplicate-property",
        ),
        pytest.param(
            _junit_xml_with_subtests(first_property="many"),
            "not an integer",
            id="non-integer-property",
        ),
        pytest.param(
            _junit_xml_with_subtests(tests="6"),
            "do not match testsuite aggregate",
            id="aggregate-mismatch",
        ),
    ],
)
def test_subtest_property_authority_fails_closed(xml: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_junit_testcases(
            xml,
            expected_nodeids=[
                "tests/test_sample.py::test_function[value-a]",
                "tests/test_sample.py::TestGroup::test_method[value-b]",
            ],
        )


@pytest.mark.parametrize(
    ("xml", "message"),
    [
        pytest.param(
            b'<testsuite><testcase classname="tests.test_sample" name="test_function[value-a]" /></testsuite>',
            "missing=",
            id="missing-testcase",
        ),
        pytest.param(
            b'<testsuite><testcase classname="tests.test_sample" name="test_function[value-a]" />'
            b'<testcase classname="tests.test_sample" name="test_function[value-a]" /></testsuite>',
            "duplicate=",
            id="duplicate-testcase",
        ),
        pytest.param(
            b'<testsuite><testcase classname="tests.test_sample" name="test_function[value-a]" />'
            b'<testcase classname="tests.test_other" name="test_extra" /></testsuite>',
            "unmatched_or_extra=",
            id="unmatched-testcase",
        ),
        pytest.param(
            b'<testsuite><testcase name="test_function[value-a]" /></testsuite>',
            "missing xunit2",
            id="missing-xunit-identity",
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


def _derived_fixture(
    vault: Path,
    *,
    junit_xml: bytes | None = None,
    stdout: str = "2 passed in 0.01s",
    policy_path: str | None = None,
) -> tuple[dict, dict, dict, dict]:
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
        policy_path=policy_path,
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
        "local_corpus_policy": full_manifest["input_fingerprints"].get(
            "local_corpus_policy", "independent" if policy_path else "missing"
        ),
    }
    result = TimedProcessResult(
        args=["python", "-m", "pytest"],
        returncode=0,
        stdout=stdout,
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
        policy_path=policy_path,
        context=FIXED_CONTEXT,
    )
    xml = junit_xml if junit_xml is not None else _junit_xml()
    junit_evidence = parse_junit_testcases(xml, expected_nodeids=nodeids)
    full_summary["evidence_artifacts"] = [
        {
            "kind": "junit_xml",
            "path": "build/release-payloads/full.junit.xml",
            "exists": True,
            "size_bytes": len(xml),
            "sha256": hashlib.sha256(xml).hexdigest(),
            "source": "pytest_junit_xml",
            "observed_count": int(junit_evidence["testcase_count"])
            + int(junit_evidence["subtests_passed"]),
            "consistency_status": "pass",
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
        policy_path=policy_path,
        context=FIXED_CONTEXT,
    )
    derived = derive_subset_summary(
        full_summary, junit_evidence, full_manifest, selected_manifest
    )
    return derived, full_summary, full_manifest, selected_manifest


def test_full_suite_sidecar_binding_rejects_collection_and_junit_drift(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    _, full_summary, full_manifest, _ = _derived_fixture(vault)
    manifest_bytes = f"{json.dumps(full_manifest, ensure_ascii=False, indent=2)}\n".encode()

    counts = validate_full_suite_evidence_bindings(
        full_summary,
        full_manifest,
        collection_bytes=manifest_bytes,
        junit_bytes=_junit_xml(),
    )

    assert counts == {"collection_count": 2, "junit_count": 2}
    with pytest.raises(ValueError, match="manifest file digest mismatch"):
        validate_full_suite_evidence_bindings(
            full_summary,
            full_manifest,
            collection_bytes=manifest_bytes + b" ",
            junit_bytes=_junit_xml(),
        )
    with pytest.raises(ValueError, match="JUnit digest mismatch"):
        validate_full_suite_evidence_bindings(
            full_summary,
            full_manifest,
            collection_bytes=manifest_bytes,
            junit_bytes=_junit_xml() + b" ",
        )


def test_selected_subset_sums_only_its_parent_subtest_properties(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)

    derived, full_summary, full_manifest, selected_manifest = _derived_fixture(
        vault,
        junit_xml=_junit_xml_with_subtests(),
        stdout="2 passed, 3 subtests passed in 0.01s",
    )

    assert full_summary["counts"]["subtests_passed"] == 3
    assert derived["counts"]["passed"] == 1
    assert derived["counts"]["subtests_passed"] == 2
    assert derived["pytest_marker_deselected_count"] == 0
    assert (
        derived["derivation"]["full_collection_nodeid_count"]
        - derived["derivation"]["selected_collection_nodeid_count"]
        == 1
    )

    mismatched_summary = deepcopy(full_summary)
    mismatched_summary["counts"]["subtests_passed"] = 2
    with pytest.raises(ValueError, match="subtests_passed"):
        derive_subset_summary(
            mismatched_summary,
            parse_junit_testcases(
                _junit_xml_with_subtests(), expected_nodeids=full_manifest["nodeids"]
            ),
            full_manifest,
            selected_manifest,
        )

    drifted_evidence = parse_junit_testcases(
        _junit_xml_with_subtests(), expected_nodeids=full_manifest["nodeids"]
    )
    nodeid_with_two_subtests = next(
        nodeid
        for nodeid, count in drifted_evidence["subtests_passed_by_nodeid"].items()
        if count == 2
    )
    drifted_evidence["subtests_passed_by_nodeid"][nodeid_with_two_subtests] = 1
    with pytest.raises(ValueError, match="subtest accounting does not match"):
        derive_subset_summary(
            full_summary,
            drifted_evidence,
            full_manifest,
            selected_manifest,
        )


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
    assert collection_manifest_reference_is_rebindable(vault, digest) is True
    loaded_digest = load_collection_manifest_digest(
        vault,
        identity["manifest_path"],
        expected_suite="full-shard-1",
        expected_semantic_command="-m pytest",
    )
    assert loaded_digest["sha256"] == manifest["nodeids_sha256"]
    assert loaded_digest["manifest_sha256"] == identity["manifest_sha256"]
    assert loaded_digest["local_corpus_policy"] == "missing"
    for dependency in ("independent", "0" * 64):
        inconsistent = {**digest, "local_corpus_policy": dependency}
        assert not collection_manifest_reference_is_current(vault, inconsistent)
        assert not collection_manifest_reference_is_rebindable(vault, inconsistent)
    legacy_digest = {key: value for key, value in digest.items() if key != "local_corpus_policy"}
    assert collection_manifest_reference_is_current(vault, legacy_digest)

    with pytest.raises(ValueError, match="semantic_command mismatch"):
        load_collection_manifest_digest(
            vault,
            identity["manifest_path"],
            expected_suite="full-shard-1",
            expected_semantic_command="-m pytest -m report_contract_core",
        )
    with pytest.raises(ValueError, match="suite mismatch"):
        load_collection_manifest_digest(
            vault,
            identity["manifest_path"],
            expected_suite="report-contract-summary",
            expected_semantic_command="-m pytest",
        )

    stale_manifest = deepcopy(manifest)
    stale_manifest["source_revision"] = "previous-revision"
    write_collection_manifest(
        vault, stale_manifest, "build/release-payloads/full.collection.json"
    )
    with pytest.raises(ValueError, match="source_revision drift"):
        load_collection_manifest_digest(
            vault,
            identity["manifest_path"],
            expected_suite="full-shard-1",
            expected_semantic_command="-m pytest",
        )
    write_collection_manifest(
        vault, manifest, "build/release-payloads/full.collection.json"
    )

    path = vault / identity["manifest_path"]
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '"nodeid_count": 1', '"nodeid_count": 2'
        ),
        encoding="utf-8",
    )
    assert collection_manifest_reference_is_current(vault, digest) is False
    assert collection_manifest_reference_is_rebindable(vault, digest) is False


def test_collection_manifest_paths_stay_inside_vault(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    schema_name = "test-execution-collection-manifest.schema.json"
    shutil.copyfile(
        REPO_ROOT / "ops" / "schemas" / schema_name,
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
        vault,
        manifest,
        "build/release-payloads/full.collection.json",
    )
    inside = vault / identity["manifest_path"]

    loaded = load_collection_manifest_digest(
        vault,
        inside,
        expected_suite="full-shard-1",
        expected_semantic_command="-m pytest",
    )
    assert loaded["manifest_path"] == identity["manifest_path"]

    outside = tmp_path / "outside.collection.json"
    outside.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="outside vault"):
        load_collection_manifest_digest(
            vault,
            outside,
            expected_suite="full-shard-1",
            expected_semantic_command="-m pytest",
        )

    symlink = vault / "build/release-payloads/outside.collection.json"
    symlink.symlink_to(outside)
    with pytest.raises(ValueError, match="outside vault"):
        load_collection_manifest_digest(
            vault,
            symlink.relative_to(vault),
            expected_suite="full-shard-1",
            expected_semantic_command="-m pytest",
        )
    escaped_digest = {
        **identity,
        "manifest_path": symlink.relative_to(vault).as_posix(),
        "nodeid_count": manifest["nodeid_count"],
        "sha256": manifest["nodeids_sha256"],
    }
    assert collection_manifest_reference_is_current(vault, escaped_digest) is False
    assert collection_manifest_reference_is_rebindable(vault, escaped_digest) is False


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


def test_derivation_preserves_and_checks_local_policy_inputs(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    (vault / "ops/policies/wiki-maintainer-policy.local.yaml").write_text(
        "schema_version: 1\noverrides: {}\n", encoding="utf-8"
    )
    derived, full_summary, full_manifest, selected_manifest = _derived_fixture(vault)
    expected = full_summary["input_fingerprints"]["local_corpus_policy"]
    assert derived["input_fingerprints"]["local_corpus_policy"] == expected
    junit = parse_junit_testcases(_junit_xml(), expected_nodeids=full_manifest["nodeids"])
    exact = derive_subset_summary(full_summary, junit, full_manifest, selected_manifest["nodeids"])
    assert exact["input_fingerprints"]["local_corpus_policy"] == expected
    for fingerprints in ({}, {"local_corpus_policy": "stale"}):
        drifted = deepcopy(selected_manifest)
        drifted["input_fingerprints"] = fingerprints
        with pytest.raises(ValueError, match="local corpus policy drift"):
            derive_subset_summary(full_summary, junit, full_manifest, drifted)


@pytest.mark.parametrize("transition", ["create", "edit", "remove"])
@pytest.mark.parametrize("selection", ["manifest", "nodeids"])
@pytest.mark.parametrize("custom_policy", [False, True], ids=["default", "custom"])
def test_derived_summary_freshness_tracks_parent_policy_scope(
    tmp_path: Path, transition: str, selection: str, custom_policy: bool
) -> None:
    seed_minimal_vault(tmp_path)
    policy_path = "ops/policies/custom-policy.yaml" if custom_policy else None
    if policy_path:
        (tmp_path / policy_path).write_bytes((tmp_path / DEFAULT_POLICY_PATH).read_bytes())
    policy, _ = load_policy(tmp_path)
    if transition != "create":
        write_local_corpus_policy(tmp_path, policy)
    derived, parent, full_manifest, selected_manifest = _derived_fixture(
        tmp_path, policy_path=policy_path
    )
    if selection == "nodeids":
        derived = derive_subset_summary(
            parent,
            parse_junit_testcases(_junit_xml(), expected_nodeids=full_manifest["nodeids"]),
            full_manifest,
            selected_manifest["nodeids"],
        )
    relative_path = "ops/reports/test-execution-summary-report-contract-derived.json"
    write_report(tmp_path, derived, relative_path)
    before = build_freshness_report(
        tmp_path, context=FIXED_CONTEXT, mtime_source="embedded_currentness"
    )
    record = next(row for row in before["artifact_records"] if row["path"] == relative_path)
    assert record["schema_validation_status"] == "pass"
    assert record["currentness_status"] == "current"

    if transition == "remove":
        (tmp_path / LOCAL_CORPUS_POLICY_PATH).unlink()
    else:
        policy["page_shape"]["special_page_required_sections"]["system/system-index.md"].append(
            "Synthetic required section"
        )
        write_local_corpus_policy(tmp_path, policy)
    after = build_freshness_report(
        tmp_path, context=FIXED_CONTEXT, mtime_source="embedded_currentness"
    )
    record = next(row for row in after["artifact_records"] if row["path"] == relative_path)
    assert record["schema_validation_status"] == "pass"
    assert record["source_tree_fingerprint_status"] == "current"
    assert record["currentness_status"] == ("current" if custom_policy else "stale")
    assert record["input_fingerprint_mismatch_keys"] == (
        [] if custom_policy else ["local_corpus_policy"]
    )
    assert after["summary"]["stale_artifact_count"] == (0 if custom_policy else 1)
    if not custom_policy:
        assert record["recommended_next_action"] == "regenerate_canonical_report"
        assert record["safe_to_backfill"] is False
    refreshed, _, _, _ = _derived_fixture(tmp_path, policy_path=policy_path)
    write_report(tmp_path, refreshed, relative_path)
    current = build_freshness_report(
        tmp_path, context=FIXED_CONTEXT, mtime_source="embedded_currentness"
    )
    record = next(row for row in current["artifact_records"] if row["path"] == relative_path)
    assert record["currentness_status"] == "current"
    assert record["input_fingerprint_mismatch_keys"] == []
    assert current["summary"]["stale_artifact_count"] == 0


@pytest.mark.parametrize("transition", ["create", "edit", "remove"])
@pytest.mark.parametrize("selection", ["manifest", "nodeids"])
def test_derived_custom_aggregate_retains_default_shard_dependency(
    tmp_path: Path, transition: str, selection: str
) -> None:
    seed_minimal_vault(tmp_path)
    custom = "ops/policies/custom-policy.yaml"
    (tmp_path / custom).write_bytes((tmp_path / DEFAULT_POLICY_PATH).read_bytes())
    local = tmp_path / LOCAL_CORPUS_POLICY_PATH
    if transition != "create":
        local.write_text("schema_version: 1\noverrides: {}\n", encoding="utf-8")
    _, parent, full_manifest, selected_manifest = _derived_fixture(tmp_path)
    shard_path = "ops/reports/full-shard.json"
    write_report(tmp_path, parent, shard_path)
    aggregate = build_aggregate_report(
        tmp_path, shard_paths=[shard_path], suite="full", policy_path=custom, context=FIXED_CONTEXT
    )
    assert aggregate["status"] == "pass"
    assert aggregate["represents_full_suite"] is True
    selected = selected_manifest if selection == "manifest" else selected_manifest["nodeids"]
    derived = derive_subset_summary(
        aggregate, parse_junit_testcases(_junit_xml(), expected_nodeids=full_manifest["nodeids"]),
        full_manifest, selected,
    )
    relative_path = "ops/reports/derived-custom-aggregate.json"
    write_report(tmp_path, derived, relative_path)
    before = build_freshness_report(tmp_path, context=FIXED_CONTEXT, mtime_source="embedded_currentness")
    record = next(row for row in before["artifact_records"] if row["path"] == relative_path)
    assert record["currentness_status"] == "current"
    if transition == "remove":
        local.unlink()
    else:
        local.write_text("schema_version: 1\noverrides: {}\n# changed\n", encoding="utf-8")
    after = build_freshness_report(tmp_path, context=FIXED_CONTEXT, mtime_source="embedded_currentness")
    record = next(row for row in after["artifact_records"] if row["path"] == relative_path)
    assert record["schema_validation_status"] == "pass"
    assert record["source_tree_fingerprint_status"] == "current"
    assert record["currentness_status"] == "stale"
    assert record["input_fingerprint_mismatch_keys"] == ["local_corpus_policy"]


@pytest.mark.parametrize("transition", ["create", "edit", "remove"])
def test_derived_custom_summary_retains_default_selector_dependency(
    tmp_path: Path, transition: str
) -> None:
    seed_minimal_vault(tmp_path)
    custom = "ops/policies/custom-policy.yaml"
    (tmp_path / custom).write_bytes((tmp_path / DEFAULT_POLICY_PATH).read_bytes())
    local = tmp_path / LOCAL_CORPUS_POLICY_PATH
    if transition != "create":
        local.write_text("schema_version: 1\noverrides: {}\n", encoding="utf-8")
    _, parent, full_manifest, custom_selection = _derived_fixture(tmp_path, policy_path=custom)
    selected = build_collection_manifest(
        tmp_path, suite=custom_selection["suite"],
        semantic_command=custom_selection["semantic_command"], nodeids=custom_selection["nodeids"],
        selection_kind="selector_subset", deselected_tests=[],
        deselection_lifecycle=_lifecycle(), context=FIXED_CONTEXT,
    )
    derived = derive_subset_summary(
        parent, parse_junit_testcases(_junit_xml(), expected_nodeids=full_manifest["nodeids"]),
        full_manifest, selected,
    )
    relative_path = "ops/reports/derived-custom-selection.json"
    write_report(tmp_path, derived, relative_path)
    if transition == "remove":
        local.unlink()
    else:
        local.write_text("schema_version: 1\noverrides: {}\n# changed\n", encoding="utf-8")
    freshness = build_freshness_report(tmp_path, context=FIXED_CONTEXT, mtime_source="embedded_currentness")
    record = next(row for row in freshness["artifact_records"] if row["path"] == relative_path)
    assert record["schema_validation_status"] == "pass"
    assert record["source_tree_fingerprint_status"] == "current"
    assert record["currentness_status"] == "stale"


def test_derivation_fails_closed_across_authority_boundaries(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    _, full_summary, full_manifest, selected_manifest = _derived_fixture(vault)
    junit_evidence = parse_junit_testcases(
        _junit_xml(), expected_nodeids=full_manifest["nodeids"]
    )

    parent_drift = deepcopy(full_summary)
    parent_drift["pytest_collect_nodeid_digest"]["manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="not bound to full manifest"):
        derive_subset_summary(
            parent_drift, junit_evidence, full_manifest, selected_manifest
        )

    revision_drift = deepcopy(selected_manifest)
    revision_drift["source_revision"] = "different-revision"
    with pytest.raises(ValueError, match="source_revision drift"):
        derive_subset_summary(
            full_summary, junit_evidence, full_manifest, revision_drift
        )

    outcome_drift = deepcopy(junit_evidence)
    outcome_drift["outcomes"].pop(next(iter(outcome_drift["outcomes"])))
    with pytest.raises(ValueError, match="do not exactly match"):
        derive_subset_summary(
            full_summary, outcome_drift, full_manifest, selected_manifest
        )

    with pytest.raises(ValueError, match="not a subset"):
        derive_subset_summary(
            full_summary,
            junit_evidence,
            full_manifest,
            ["tests/test_outside.py::test_not_collected"],
        )

    deselection_overcount = deepcopy(selected_manifest)
    deselection_overcount["deselected_tests"] = [{"nodeid": "one"}, {"nodeid": "two"}]
    with pytest.raises(ValueError, match="deselection metadata exceeds"):
        derive_subset_summary(
            full_summary,
            junit_evidence,
            full_manifest,
            deselection_overcount,
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


def test_derived_summary_uses_selected_manifest_suite(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    _, full_summary, full_manifest, selected_manifest = _derived_fixture(vault)
    selected_manifest["suite"] = "public"

    derived = derive_subset_summary(
        full_summary,
        parse_junit_testcases(
            _junit_xml(), expected_nodeids=full_manifest["nodeids"]
        ),
        full_manifest,
        selected_manifest,
    )

    assert derived["suite"] == "public"
    assert derived["suite_scope"] == "public_contract"
    assert derived["not_full_suite_reason"] == (
        "derived public subset of exact full-suite evidence"
    )


def test_direct_parity_is_exact_for_status_counts_nodeids_and_deselection(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    _, full_summary, full_manifest, selected_manifest = _derived_fixture(vault)
    command = [
        "python",
        "-m",
        "pytest",
        "-m",
        "report_contract_core",
        "-p",
        "no:cacheprovider",
    ]
    direct = build_report(
        vault,
        command=command,
        result=TimedProcessResult(
            args=command,
            returncode=0,
            stdout="1 passed in 0.01s",
            stderr="",
            timed_out=False,
            timeout_seconds=30,
            termination_reason="completed",
        ),
        duration_ms=10,
        suite="report-contract-summary",
        collect_nodeids=True,
        collect_nodeid_digest={
            "status": "collected",
            "command": "python -m pytest --collect-only",
            "nodeid_count": selected_manifest["nodeid_count"],
            "sha256": selected_manifest["nodeids_sha256"],
            "reason": "",
        },
        context=FIXED_CONTEXT,
    )
    selected_manifest = build_collection_manifest(
        vault,
        suite="report-contract-summary",
        semantic_command=selected_manifest["semantic_command"],
        nodeids=selected_manifest["nodeids"],
        selection_kind="selector_subset",
        deselected_tests=direct["deselected_tests"],
        deselection_lifecycle=direct["deselection_lifecycle"],
        context=FIXED_CONTEXT,
    )
    derived = derive_subset_summary(
        full_summary,
        parse_junit_testcases(
            _junit_xml(), expected_nodeids=full_manifest["nodeids"]
        ),
        full_manifest,
        selected_manifest,
    )

    assert direct["pytest_marker_deselected_count"] == 0
    assert derived["pytest_marker_deselected_count"] == 0
    direct_parity = subset_summary_parity(derived, direct)
    assert direct_parity["status"] == "pass", direct_parity

    observed_deselection = deepcopy(direct)
    observed_deselection["pytest_marker_deselected_count"] = 1
    parity = subset_summary_parity(derived, observed_deselection)
    assert parity["status"] == "fail"
    assert (
        "derived/direct parity mismatch: pytest_marker_deselected_count"
        in parity["blockers"]
    )
