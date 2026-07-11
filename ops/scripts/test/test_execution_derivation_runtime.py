from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    write_schema_backed_report,
)
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import (
    load_schema_with_vault_override,
    validate_or_raise,
)
from ops.scripts.core.source_tree_fingerprint_runtime import (
    release_source_tree_fingerprint,
)
from ops.scripts.test.test_execution_evidence_runtime import (
    nodeid_outcome_consistency,
    sha256_file,
    sha256_text,
)

COLLECTION_MANIFEST_SCHEMA_PATH = "ops/schemas/test-execution-collection-manifest.schema.json"
PRODUCER = "ops.scripts.test_execution_summary"
OUTCOME_LABELS = ("passed", "failed", "errors", "skipped", "xfailed", "xpassed")


def canonical_json_sha256(payload: Any) -> str:
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return sha256_text(f"{serialized}\n")


def serialized_report_sha256(payload: Any) -> str:
    return sha256_text(f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n")


def canonical_nodeids(nodeids: Sequence[str]) -> list[str]:
    values = [str(nodeid).strip() for nodeid in nodeids]
    invalid = [
        nodeid
        for nodeid in values
        if not nodeid
        or "\n" in nodeid
        or "\r" in nodeid
        or "\\" in nodeid
        or nodeid.startswith("/")
        or ".py::" not in nodeid
    ]
    if invalid:
        raise ValueError(f"invalid canonical pytest nodeid: {invalid[0]!r}")
    duplicates = sorted(
        nodeid for nodeid, count in Counter(values).items() if count > 1
    )
    if duplicates:
        raise ValueError(f"duplicate canonical pytest nodeid: {duplicates[0]}")
    return sorted(values)


def nodeids_sha256(nodeids: Sequence[str]) -> str:
    canonical = canonical_nodeids(nodeids)
    payload = "\n".join(canonical)
    return sha256_text(f"{payload}\n" if payload else "")


def build_collection_manifest(
    vault: Path,
    *,
    suite: str,
    semantic_command: str,
    nodeids: Sequence[str],
    selection_kind: str,
    deselected_tests: list[dict[str, Any]],
    deselection_lifecycle: dict[str, Any],
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    if selection_kind not in {"full_suite", "selector_subset"}:
        raise ValueError(f"unsupported collection selection_kind: {selection_kind}")
    canonical = canonical_nodeids(nodeids)
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="test_execution_collection_manifest",
            producer=PRODUCER,
            source_command=(
                "python -m ops.scripts.test_execution_summary --collection-only "
                f"--suite {suite} -- <pytest-command>"
            ),
            resolved_policy_path=resolved_policy_path,
            schema_path=COLLECTION_MANIFEST_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/test/test_execution_summary.py",
                "ops/scripts/test/test_execution_derivation_runtime.py",
            ],
            text_inputs={
                "suite": suite,
                "selection_kind": selection_kind,
                "semantic_command": semantic_command,
                "nodeids": "\n".join(canonical),
                "deselected_tests": json.dumps(
                    deselected_tests, sort_keys=True, separators=(",", ":")
                ),
                "deselection_lifecycle": json.dumps(
                    deselection_lifecycle, sort_keys=True, separators=(",", ":")
                ),
            },
        ),
        "suite": suite,
        "selection_kind": selection_kind,
        "semantic_command": semantic_command,
        "semantic_command_sha256": sha256_text(semantic_command),
        "nodeid_count": len(canonical),
        "nodeids_sha256": nodeids_sha256(canonical),
        "nodeids": canonical,
        "deselected_tests": deepcopy(deselected_tests),
        "deselection_lifecycle": deepcopy(deselection_lifecycle),
    }


def write_collection_manifest(
    vault: Path,
    manifest: dict[str, Any],
    out_path: str | Path,
) -> dict[str, Any]:
    destination = write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=manifest,
            schema_path=COLLECTION_MANIFEST_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=str(out_path),
            context="test execution collection manifest schema validation failed",
        )
    )
    return {
        "manifest_path": report_path(vault, destination),
        "manifest_sha256": sha256_file(destination),
        "manifest_schema": COLLECTION_MANIFEST_SCHEMA_PATH,
        "manifest_nodeids_sha256": str(manifest["nodeids_sha256"]),
        "source_tree_fingerprint": str(manifest["source_tree_fingerprint"]),
        "source_revision": str(manifest["source_revision"]),
    }


def load_collection_manifest_digest(
    vault: Path,
    path_value: str | Path,
) -> dict[str, Any]:
    path = Path(path_value)
    if not path.is_absolute():
        path = vault / path
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("test execution collection manifest must be a JSON object")
    validate_collection_manifest_schema(vault, manifest)
    blockers = validate_collection_manifest_payload(manifest)
    if blockers:
        raise ValueError("; ".join(blockers))
    if manifest.get("source_tree_fingerprint") != release_source_tree_fingerprint(vault):
        raise ValueError("collection manifest source_tree_fingerprint drift")
    return {
        "status": "collected",
        "command": str(manifest["semantic_command"]),
        "nodeid_count": int(manifest["nodeid_count"]),
        "sha256": str(manifest["nodeids_sha256"]),
        "reason": "reused exact schema-backed collection manifest",
        "duration_ms": 0,
        "manifest_path": report_path(vault, path),
        "manifest_sha256": sha256_file(path),
        "manifest_schema": COLLECTION_MANIFEST_SCHEMA_PATH,
        "manifest_nodeids_sha256": str(manifest["nodeids_sha256"]),
        "source_tree_fingerprint": str(manifest["source_tree_fingerprint"]),
        "source_revision": str(manifest["source_revision"]),
    }


def validate_collection_manifest_payload(manifest: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    try:
        nodeids = canonical_nodeids(manifest.get("nodeids", []))
    except (TypeError, ValueError) as exc:
        return [str(exc)]
    if nodeids != manifest.get("nodeids"):
        blockers.append("collection manifest nodeids are not in canonical sorted order")
    if int(manifest.get("nodeid_count", -1)) != len(nodeids):
        blockers.append("collection manifest nodeid_count does not match nodeids")
    if manifest.get("nodeids_sha256") != nodeids_sha256(nodeids):
        blockers.append("collection manifest nodeids_sha256 does not match nodeids")
    command = str(manifest.get("semantic_command", ""))
    if not command:
        blockers.append("collection manifest semantic_command is missing")
    if manifest.get("semantic_command_sha256") != sha256_text(command):
        blockers.append("collection manifest semantic command digest drift")
    return blockers


def validate_collection_manifest_schema(vault: Path, manifest: dict[str, Any]) -> None:
    validate_or_raise(
        manifest,
        load_schema_with_vault_override(vault, COLLECTION_MANIFEST_SCHEMA_PATH),
        context="test execution collection manifest schema validation failed",
    )


def collection_manifest_reference_is_current(
    vault: Path, digest: dict[str, Any]
) -> bool:
    path_value = str(digest.get("manifest_path", ""))
    if not path_value:
        return False
    relative_path = Path(path_value)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return False
    path = vault / relative_path
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            return False
        validate_collection_manifest_schema(vault, manifest)
    except (OSError, json.JSONDecodeError, ValueError):
        return False
    return (
        not validate_collection_manifest_payload(manifest)
        and sha256_file(path) == digest.get("manifest_sha256")
        and manifest.get("source_tree_fingerprint")
        == digest.get("source_tree_fingerprint")
        and manifest.get("source_revision") == digest.get("source_revision")
        and manifest.get("nodeid_count") == digest.get("nodeid_count")
        and manifest.get("nodeids_sha256") == digest.get("sha256")
    )


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xunit_identity_for_nodeid(nodeid: str) -> tuple[str, str]:
    parts = nodeid.split("::")
    if len(parts) < 2:
        raise ValueError(f"nodeid has no test name: {nodeid}")
    module_name = parts[0][:-3].replace("/", ".")
    return ".".join([module_name, *parts[1:-1]]), parts[-1]


def _junit_outcome(testcase: ET.Element) -> str:
    children = [
        child
        for child in testcase
        if _xml_local_name(str(child.tag)) in {"failure", "error", "skipped"}
    ]
    if len(children) > 1:
        raise ValueError("JUnit testcase contains multiple outcome elements")
    if not children:
        return "passed"
    child = children[0]
    tag = _xml_local_name(str(child.tag))
    message = str(child.attrib.get("message", ""))
    if tag == "failure":
        return (
            "xpassed"
            if "xfail-marked test passes unexpectedly" in message
            else "failed"
        )
    if tag == "error":
        return "errors"
    if child.attrib.get("type") == "pytest.xfail":
        return "xfailed"
    return (
        "xpassed" if "xfail-marked test passes unexpectedly" in message else "skipped"
    )


def parse_junit_testcases(
    junit_xml: str | bytes,
    *,
    expected_nodeids: Sequence[str],
) -> dict[str, Any]:
    expected = canonical_nodeids(expected_nodeids)
    identity_map: dict[tuple[str, str], str] = {}
    for nodeid in expected:
        identity = _xunit_identity_for_nodeid(nodeid)
        if identity in identity_map:
            raise ValueError(
                "collection nodeids are ambiguous under pytest xunit2 classname/name: "
                f"{identity_map[identity]} and {nodeid}"
            )
        identity_map[identity] = nodeid
    raw = junit_xml.encode("utf-8") if isinstance(junit_xml, str) else bytes(junit_xml)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"JUnit XML is unreadable: {exc}") from exc
    outcomes: dict[str, str] = {}
    unmatched: list[str] = []
    duplicates: list[str] = []
    for testcase in (
        element
        for element in root.iter()
        if _xml_local_name(str(element.tag)) == "testcase"
    ):
        classname = testcase.attrib.get("classname")
        name = testcase.attrib.get("name")
        if not classname or not name:
            raise ValueError("JUnit testcase is missing xunit2 classname or name")
        matched_nodeid = identity_map.get((classname, name))
        if matched_nodeid is None:
            unmatched.append(f"{classname}::{name}")
        elif matched_nodeid in outcomes:
            duplicates.append(matched_nodeid)
        else:
            outcomes[matched_nodeid] = _junit_outcome(testcase)
    missing = sorted(set(expected) - set(outcomes))
    if missing or duplicates or unmatched:
        details = []
        if missing:
            details.append(f"missing={missing}")
        if duplicates:
            details.append(f"duplicate={sorted(duplicates)}")
        if unmatched:
            details.append(f"unmatched_or_extra={sorted(unmatched)}")
        raise ValueError(
            "JUnit testcase authority derivation failed: " + "; ".join(details)
        )
    counts = Counter(outcomes.values())
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "testcase_count": len(outcomes),
        "outcomes": dict(sorted(outcomes.items())),
        "counts": {label: int(counts.get(label, 0)) for label in OUTCOME_LABELS},
    }


def _require_matching_outcomes(
    full_summary: dict[str, Any], junit_evidence: dict[str, Any]
) -> None:
    summary_counts = full_summary.get("counts", {})
    junit_counts = junit_evidence.get("counts", {})
    mismatched = [
        label
        for label in OUTCOME_LABELS
        if int(summary_counts.get(label, 0) or 0)
        != int(junit_counts.get(label, 0) or 0)
    ]
    if int(summary_counts.get("subtests_passed", 0) or 0):
        mismatched.append("subtests_passed")
    if mismatched:
        raise ValueError(
            "JUnit outcomes do not match full-summary counts: "
            + ", ".join(sorted(mismatched))
        )


def _derived_status(counts: dict[str, int]) -> str:
    failed = counts["failed"] + counts["errors"]
    if failed:
        return "partial-pass" if sum(counts.values()) > failed else "fail"
    return "pass"


def _build_validated_subset_summary(
    full_summary: dict[str, Any],
    junit_evidence: dict[str, Any],
    collection_manifest: dict[str, Any],
    selected_manifest: dict[str, Any],
    *,
    full_set: set[str],
    selected: list[str],
    outcomes: dict[str, Any],
) -> dict[str, Any]:
    subset_counter = Counter(str(outcomes[nodeid]) for nodeid in selected)
    counts = {label: int(subset_counter.get(label, 0)) for label in OUTCOME_LABELS}
    counts.update({"warnings": 0, "subtests_passed": 0})
    deselected_tests = deepcopy(selected_manifest.get("deselected_tests", []))
    lifecycle = deepcopy(selected_manifest.get("deselection_lifecycle", {}))
    policy_deselected_count = len(deselected_tests)
    marker_deselected_count = len(full_set) - len(selected) - policy_deselected_count
    if marker_deselected_count < 0:
        raise ValueError(
            "selected deselection metadata exceeds full-to-subset deselection count"
        )
    semantic_command = str(selected_manifest["semantic_command"])
    selected_digest = str(selected_manifest["nodeids_sha256"])
    status = _derived_status(counts)
    derived = deepcopy(full_summary)
    derived.update(
        {
            "source_command": "python -m ops.scripts.test_execution_summary --derive-subset-from-full",
            "input_fingerprints": {
                "parent_summary": canonical_json_sha256(full_summary),
                "junit_xml": str(junit_evidence["sha256"]),
                "full_collection_manifest": canonical_json_sha256(collection_manifest),
                "selected_collection_manifest": canonical_json_sha256(
                    selected_manifest
                ),
                "selector_semantic_command": str(
                    selected_manifest["semantic_command_sha256"]
                ),
            },
            "suite": "report-contract-summary",
            "suite_scope": "report_contract_summary",
            "represents_full_suite": False,
            "not_full_suite_reason": "derived report-contract subset of exact full-suite evidence",
            "full_suite_evidence": {
                **deepcopy(full_summary["full_suite_evidence"]),
                "status": "not_represented",
                "reason": "this exact subset is bound to parent full-suite evidence",
            },
            "status": status,
            "command": semantic_command,
            "semantic_command": semantic_command,
            "returncode": 0 if status == "pass" else 1,
            "timed_out": False,
            "termination_reason": "derived_from_full_suite_junit",
            "duration_ms": 0,
            "duration_telemetry": {
                "command_duration_ms": 0,
                "collect_only_duration_ms": 0,
                "total_wall_time_ms": 0,
                "total_wall_time_source": "command_plus_collect_only",
            },
            "counts": counts,
            "test_target_fingerprints": [],
            "deselected_tests": deselected_tests,
            "deselection_lifecycle": lifecycle,
            "pytest_marker_deselected_count": marker_deselected_count,
            "policy_deselected_count": policy_deselected_count,
            "pytest_collect_nodeid_digest": {
                "status": "collected",
                "command": semantic_command,
                "nodeid_count": len(selected),
                "sha256": selected_digest,
                "reason": "exact selected collection manifest",
                "manifest_schema": COLLECTION_MANIFEST_SCHEMA_PATH,
                "manifest_nodeids_sha256": selected_digest,
                "source_tree_fingerprint": str(
                    selected_manifest["source_tree_fingerprint"]
                ),
                "source_revision": str(selected_manifest["source_revision"]),
            },
            "nodeid_outcome_consistency": nodeid_outcome_consistency(
                counts, {"status": "collected", "nodeid_count": len(selected)}
            ),
            "evidence_artifacts": [],
            "evidence_artifact_consistency": {
                "status": "skipped",
                "checked_artifact_count": 0,
                "checks": [],
                "blockers": [],
            },
            "stdout_tail": "",
            "stderr_tail": "",
            "summary_mode": "derived",
            "evidence_origin": "derived_full_suite",
            "derivation": {
                "parent_summary_sha256": canonical_json_sha256(full_summary),
                "junit_sha256": str(junit_evidence["sha256"]),
                "full_collection_manifest_sha256": canonical_json_sha256(
                    collection_manifest
                ),
                "full_collection_nodeids_sha256": str(
                    collection_manifest["nodeids_sha256"]
                ),
                "full_collection_nodeid_count": int(
                    collection_manifest["nodeid_count"]
                ),
                "selected_collection_manifest_sha256": canonical_json_sha256(
                    selected_manifest
                ),
                "selected_collection_nodeids_sha256": selected_digest,
                "selected_collection_nodeid_count": len(selected),
                "selector_semantic_command_sha256": str(
                    selected_manifest["semantic_command_sha256"]
                ),
            },
        }
    )
    for field in ("shards", "reused_from", "release_contract_diagnosis"):
        derived.pop(field, None)
    return derived


def derive_subset_summary(
    full_summary: dict[str, Any],
    junit_evidence: dict[str, Any],
    collection_manifest: dict[str, Any],
    selected_nodeids: Sequence[str] | dict[str, Any],
) -> dict[str, Any]:
    """Derive targeted summary evidence without filesystem or clock access."""
    if isinstance(selected_nodeids, dict):
        selected_manifest = selected_nodeids
    else:
        exact_nodeids = canonical_nodeids(selected_nodeids)
        semantic_command = f"exact-nodeid-selection:{nodeids_sha256(exact_nodeids)}"
        selected_manifest = {
            "nodeids": exact_nodeids,
            "nodeid_count": len(exact_nodeids),
            "nodeids_sha256": nodeids_sha256(exact_nodeids),
            "semantic_command": semantic_command,
            "semantic_command_sha256": sha256_text(semantic_command),
            "selection_kind": "selector_subset",
            "source_tree_fingerprint": full_summary.get("source_tree_fingerprint"),
            "source_revision": full_summary.get("source_revision"),
            "deselected_tests": [],
            "deselection_lifecycle": deepcopy(full_summary.get("deselection_lifecycle", {})),
        }
    blockers = [
        *validate_collection_manifest_payload(collection_manifest),
        *validate_collection_manifest_payload(selected_manifest),
    ]
    if blockers:
        raise ValueError(
            "collection manifest validation failed: " + "; ".join(blockers)
        )
    if full_summary.get("status") != "pass" or not full_summary.get(
        "represents_full_suite"
    ):
        raise ValueError("parent summary must be passing full-suite evidence")
    if collection_manifest.get("selection_kind") != "full_suite":
        raise ValueError("full collection manifest must use selection_kind=full_suite")
    if selected_manifest.get("selection_kind") != "selector_subset":
        raise ValueError(
            "selected collection manifest must use selection_kind=selector_subset"
        )
    for label, manifest in (
        ("full", collection_manifest),
        ("selected", selected_manifest),
    ):
        if manifest.get("source_tree_fingerprint") != full_summary.get(
            "source_tree_fingerprint"
        ):
            raise ValueError(f"{label} collection source_tree_fingerprint drift")
        if manifest.get("source_revision") != full_summary.get("source_revision"):
            raise ValueError(f"{label} collection source_revision drift")
    digest = full_summary.get("pytest_collect_nodeid_digest", {})
    if (
        digest.get("status") != "collected"
        or digest.get("nodeid_count") != collection_manifest.get("nodeid_count")
        or digest.get("sha256") != collection_manifest.get("nodeids_sha256")
        or digest.get("manifest_nodeids_sha256")
        != collection_manifest.get("nodeids_sha256")
        or digest.get("manifest_sha256")
        != serialized_report_sha256(collection_manifest)
        or digest.get("source_tree_fingerprint")
        != collection_manifest.get("source_tree_fingerprint")
    ):
        raise ValueError(
            "parent summary collection digest/count is not bound to full manifest"
        )
    expected_junit_sha = next(
        (
            str(item.get("sha256", ""))
            for item in full_summary.get("evidence_artifacts", [])
            if isinstance(item, dict) and item.get("kind") == "junit_xml"
        ),
        "",
    )
    if not expected_junit_sha or expected_junit_sha != junit_evidence.get("sha256"):
        raise ValueError("JUnit digest drift from parent summary")
    _require_matching_outcomes(full_summary, junit_evidence)
    full_set = set(collection_manifest["nodeids"])
    selected = canonical_nodeids(selected_manifest["nodeids"])
    extra_selected = sorted(set(selected) - full_set)
    if extra_selected:
        raise ValueError(
            f"selected collection is not a subset of full collection: {extra_selected}"
        )
    outcomes = junit_evidence.get("outcomes", {})
    if set(outcomes) != full_set:
        raise ValueError(
            "JUnit outcome nodeids do not exactly match full collection manifest"
        )
    return _build_validated_subset_summary(
        full_summary,
        junit_evidence,
        collection_manifest,
        selected_manifest,
        full_set=full_set,
        selected=selected,
        outcomes=outcomes,
    )


def _lifecycle_without_clock(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    return {key: item for key, item in value.items() if key != "checked_at"}


def subset_summary_parity(
    derived_summary: dict[str, Any], direct_summary: dict[str, Any]
) -> dict[str, Any]:
    checks = {
        "status": derived_summary.get("status") == direct_summary.get("status"),
        "semantic_command": derived_summary.get("semantic_command")
        == direct_summary.get("semantic_command"),
        "counts": derived_summary.get("counts") == direct_summary.get("counts"),
        "nodeid_digest": derived_summary.get("pytest_collect_nodeid_digest", {}).get(
            "sha256"
        )
        == direct_summary.get("pytest_collect_nodeid_digest", {}).get("sha256"),
        "nodeid_count": derived_summary.get("pytest_collect_nodeid_digest", {}).get(
            "nodeid_count"
        )
        == direct_summary.get("pytest_collect_nodeid_digest", {}).get("nodeid_count"),
        "deselected_tests": derived_summary.get("deselected_tests")
        == direct_summary.get("deselected_tests"),
        "deselection_lifecycle": _lifecycle_without_clock(
            derived_summary.get("deselection_lifecycle")
        )
        == _lifecycle_without_clock(direct_summary.get("deselection_lifecycle")),
        "pytest_marker_deselected_count": derived_summary.get(
            "pytest_marker_deselected_count"
        )
        == direct_summary.get("pytest_marker_deselected_count"),
        "policy_deselected_count": derived_summary.get("policy_deselected_count")
        == direct_summary.get("policy_deselected_count"),
    }
    failed = [name for name, matches in checks.items() if not matches]
    return {
        "status": "pass" if not failed else "fail",
        "checks": checks,
        "blockers": [f"derived/direct parity mismatch: {name}" for name in failed],
    }
