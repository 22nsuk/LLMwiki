#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_binding_runtime import (
    CONTENT_BINDING_MODE,
    RAW_BINDING_MODE,
    REVISION_BINDING_MODE,
    binding_file_digest,
    is_sha256_digest,
)
from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    resolve_schema_backed_report_output_path,
    write_schema_backed_report,
)
from ops.scripts.core.output_runtime import display_path
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.source_revision_runtime import resolve_source_revision
from ops.scripts.release.finality_current_diagnostics import (
    SEALED_PREFLIGHT_PATH,
    classify_batch_replay_binding_mismatches,
    dedupe_preserve_order as _dedupe_preserve_order,
    fixed_point_writer_targets_by_path as _fixed_point_writer_targets_by_path,
)
from ops.scripts.release.release_closeout_fixed_point import (
    fixed_point_downstream_closed_writer_targets,
    fixed_point_writer_specs_from_policy,
)
from ops.scripts.release.release_status_v2 import release_status_v2_view

DEFAULT_OUT = "ops/reports/release-closeout-finality-attestation.json"
PRODUCER = "ops.scripts.release_closeout_finality_attestation"
SCHEMA_PATH = "ops/schemas/release-closeout-finality-attestation.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.release_closeout_finality_attestation --vault ."
FIXED_POINT_REPORT_PATH = "ops/reports/release-closeout-fixed-point.json"
FIXED_POINT_PRODUCER = "ops.scripts.release_closeout_fixed_point"
BATCH_MANIFEST_PATH = "ops/reports/release-closeout-batch-manifest.json"
SELF_CHECK_PATH = "ops/reports/release-evidence-closeout-self-check.json"
EXTERNAL_REPORT_MANIFEST_PATH = "external-reports/report-reference-manifest.json"
SHA256_MISSING = "missing"
SUPPORTED_BINDING_MODES = {
    CONTENT_BINDING_MODE,
    REVISION_BINDING_MODE,
    RAW_BINDING_MODE,
}
FINALITY_ATTESTATION_SOURCE_PATHS = [
    "ops/scripts/release/release_closeout_finality_attestation.py",
    "ops/scripts/release/finality_current_diagnostics.py",
    "ops/scripts/core/artifact_binding_runtime.py",
]


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        return SHA256_MISSING
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_digest_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(path): str(digest) for path, digest in value.items()}


def _normalized_string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            return None
        result.append(item.strip())
    return result


def _authority_schema_version(value: Any) -> int:
    return value if type(value) is int else 0


def _fixed_point_policy_authority(
    vault: Path,
) -> tuple[list[dict[str, Any]], dict[str, str]] | None:
    try:
        writers = fixed_point_writer_specs_from_policy(vault)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    binding_mode_map = {
        str(path): str(writer["binding_mode"])
        for writer in writers
        for path in writer["produces"]
    }
    return writers, binding_mode_map


def _fixed_point_single_pass_execution_is_consistent(
    fixed_point: dict[str, Any],
    *,
    writers: list[dict[str, Any]],
) -> bool:
    execution = fixed_point.get("execution")
    duration_summary = fixed_point.get("duration_summary")
    command_sequence = _normalized_string_list(fixed_point.get("command_sequence"))
    if (
        not isinstance(execution, dict)
        or not isinstance(duration_summary, dict)
        or not command_sequence
        or len(command_sequence) != len(set(command_sequence))
    ):
        return False

    selected_targets = _normalized_string_list(execution.get("selected_targets"))
    command_results = execution.get("command_results")
    writer_costs = duration_summary.get("writer_costs")
    if (
        not selected_targets
        or not isinstance(command_results, list)
        or not isinstance(writer_costs, list)
        or execution.get("status") != "pass"
        or execution.get("reason") != "single_topological_pass_completed"
        or duration_summary.get("execution_pass_count") != 1
        or duration_summary.get("command_run_count") != len(command_results)
    ):
        return False

    policy_command_sequence = [str(writer["target"]) for writer in writers]
    if command_sequence != policy_command_sequence:
        return False

    try:
        downstream_closed_targets = fixed_point_downstream_closed_writer_targets(
            writers,
            selected_targets,
        )
    except ValueError:
        return False
    if selected_targets != downstream_closed_targets:
        return False
    selected_set = set(selected_targets)

    expected_result_targets = _dedupe_preserve_order(
        [
            target
            for writer in writers
            if str(writer["target"]) in selected_set
            for target in [
                *(str(item) for item in writer["expensive_prerequisites"]),
                str(writer["target"]),
            ]
        ]
    )
    writer_command_counts = dict.fromkeys(command_sequence, 0)
    result_targets: list[str] = []
    for result in command_results:
        if not isinstance(result, dict):
            return False
        target = str(result.get("target", "")).strip()
        result_targets.append(target)
        if target in writer_command_counts:
            writer_command_counts[target] += 1
        if (
            result.get("status") != "pass"
            or result.get("returncode") != 0
            or result.get("timed_out") is not False
            or _normalized_string_list(result.get("issues")) != []
            or _normalized_string_list(result.get("undeclared_tracked_writes"))
            != []
        ):
            return False
    if result_targets != expected_result_targets:
        return False

    if len(writer_costs) != len(writers):
        return False
    for item, writer in zip(writer_costs, writers, strict=True):
        if not isinstance(item, dict):
            return False
        target = str(item.get("target", "")).strip()
        selected = item.get("selected")
        run_count = item.get("run_count")
        produces = _normalized_string_list(item.get("produces"))
        expected_selected = target in selected_set
        expected_run_count = 1 if expected_selected else 0
        if (
            str(item.get("name", "")).strip() != str(writer["name"])
            or target != str(writer["target"])
            or produces != [str(path) for path in writer["produces"]]
            or type(selected) is not bool
            or type(run_count) is not int
            or selected is not expected_selected
            or run_count != expected_run_count
            or writer_command_counts[target] != expected_run_count
        ):
            return False
    return True


def _load_optional(vault: Path, rel_path: str) -> tuple[dict[str, Any], str]:
    raw_payload, diagnostics = load_optional_json_object_with_diagnostics(vault / rel_path)
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    return payload, str(diagnostics.get("status", "unknown")).strip() or "unknown"


def _revision_bound_artifacts_match_current_revision(
    vault: Path,
    binding_mode_map: dict[str, str],
    *,
    current_revision: str,
) -> bool:
    for path, binding_mode in binding_mode_map.items():
        if binding_mode != REVISION_BINDING_MODE:
            continue
        payload, load_status = _load_optional(vault, path)
        if (
            load_status != "ok"
            or str(payload.get("source_revision", "")).strip()
            != current_revision
        ):
            return False
    return True


def _tracked_paths_from_fixed_point(fixed_point: dict[str, Any]) -> list[str]:
    tracked = fixed_point.get("tracked_artifacts")
    if isinstance(tracked, list):
        paths = [
            str(item.get("path", "")).strip()
            for item in tracked
            if isinstance(item, dict) and str(item.get("path", "")).strip()
        ]
        if paths:
            return sorted(dict.fromkeys(paths))
    return []


def _raw_digest_map(vault: Path, paths: list[str]) -> dict[str, str]:
    return {path: _sha256_file(vault / path) for path in paths}


def _binding_digest_map(
    vault: Path,
    binding_mode_map: dict[str, str],
) -> dict[str, str]:
    return {
        path: binding_file_digest(
            vault / path,
            binding_mode=binding_mode,
        )[1]
        for path, binding_mode in sorted(binding_mode_map.items())
    }


def _binding_mismatches(
    expected: dict[str, str],
    actual: dict[str, str],
    *,
    binding_mode_map: dict[str, str],
) -> list[dict[str, str]]:
    mismatches: list[dict[str, str]] = []
    for path in sorted(set(expected) | set(actual)):
        expected_digest = expected.get(path, SHA256_MISSING)
        actual_digest = actual.get(path, SHA256_MISSING)
        if expected_digest == actual_digest:
            continue
        mismatches.append(
            {
                "path": path,
                "fixed_point_binding_digest": expected_digest,
                "current_binding_digest": actual_digest,
                "binding_mode": binding_mode_map.get(path, "missing"),
            }
        )
    return mismatches


def _recorded_binding_mismatches(
    *,
    recorded: dict[str, str],
    current: dict[str, str],
    binding_mode_map: dict[str, str],
) -> list[dict[str, str]]:
    paths = sorted(set(recorded) | set(current))
    return [
        {
            "path": path,
            "recorded_binding_digest": recorded.get(path, SHA256_MISSING),
            "current_binding_digest": current.get(path, SHA256_MISSING),
            "binding_mode": binding_mode_map.get(path, "missing"),
        }
        for path in paths
        if recorded.get(path, SHA256_MISSING) != current.get(path, SHA256_MISSING)
    ]


def _batch_manifest_artifact_mismatches(vault: Path) -> dict[str, Any]:
    payload, load_status = _load_optional(vault, BATCH_MANIFEST_PATH)
    if load_status != "ok":
        return {
            "binding_mismatches": [],
            "authority_failures": [f"batch_manifest_load_status:{load_status}"],
        }
    if payload.get("schema_version") != 2:
        return {
            "binding_mismatches": [],
            "authority_failures": ["batch_manifest_unsupported_schema_version"],
        }
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return {
            "binding_mismatches": [],
            "authority_failures": ["batch_manifest_artifacts_missing"],
        }
    binding_mismatches: list[dict[str, str]] = []
    authority_failures: list[str] = []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        rel_path = str(item.get("path", "")).strip()
        if not rel_path:
            continue
        role = str(item.get("role", "")).strip()
        binding_expected = str(item.get("binding_digest", "")).strip()
        binding_mode = str(item.get("binding_mode", "")).strip()
        if (
            is_sha256_digest(binding_expected)
            and binding_mode in SUPPORTED_BINDING_MODES
        ):
            binding_current = binding_file_digest(
                vault / rel_path,
                binding_mode=binding_mode,
            )[1]
        else:
            authority_failures.append(
                f"batch_manifest_artifact_binding_invalid:{rel_path}"
            )
            continue
        if binding_expected != binding_current:
            binding_mismatches.append(
                {
                    "path": rel_path,
                    "role": role,
                    "batch_manifest_binding_digest": binding_expected,
                    "current_binding_digest": binding_current,
                    "binding_mode": binding_mode,
                }
            )
    return {
        "binding_mismatches": binding_mismatches,
        "authority_failures": authority_failures,
    }


def _fixed_point_authority_maps(
    vault: Path,
    fixed_point: dict[str, Any],
) -> tuple[dict[str, str], dict[str, str], dict[str, str], str]:
    if fixed_point.get("schema_version") != 2:
        return {}, {}, {}, "unsupported_schema_version"
    current_revision = resolve_source_revision(vault).revision
    if str(fixed_point.get("source_revision", "")).strip() != current_revision:
        return {}, {}, {}, "source_revision_mismatch"
    policy_authority = _fixed_point_policy_authority(vault)
    if policy_authority is None:
        return {}, {}, {}, "invalid_writer_policy"
    writers, policy_binding_mode_map = policy_authority
    if not _fixed_point_single_pass_execution_is_consistent(
        fixed_point,
        writers=writers,
    ):
        return {}, {}, {}, "invalid_single_pass_execution"
    raw_digest_map = _normalized_digest_map(fixed_point.get("raw_digest_map"))
    binding_digest_map = _normalized_digest_map(
        fixed_point.get("binding_digest_map")
    )
    binding_mode_map = _normalized_digest_map(fixed_point.get("binding_mode_map"))
    currentness = fixed_point.get("currentness")
    currentness_status = (
        str(currentness.get("status", "")).strip()
        if isinstance(currentness, dict)
        else ""
    )
    execution = fixed_point.get("execution")
    execution_is_consistent = (
        isinstance(execution, dict)
        and execution.get("status") == "pass"
        and _normalized_digest_map(execution.get("raw_digest_map"))
        == raw_digest_map
        and _normalized_digest_map(execution.get("binding_digest_map"))
        == binding_digest_map
        and _normalized_digest_map(execution.get("binding_mode_map"))
        == binding_mode_map
    )
    tracked_artifacts = fixed_point.get("tracked_artifacts")
    tracked_artifacts = tracked_artifacts if isinstance(tracked_artifacts, list) else []
    tracked_paths = set(_tracked_paths_from_fixed_point(fixed_point))
    tracked_mode_map = {
        str(item.get("path", "")).strip(): str(
            item.get("binding_mode", "")
        ).strip()
        for item in tracked_artifacts
        if isinstance(item, dict) and str(item.get("path", "")).strip()
    }
    policy_paths = set(policy_binding_mode_map)
    if (
        len(tracked_artifacts) != len(policy_binding_mode_map)
        or tracked_mode_map != policy_binding_mode_map
        or binding_mode_map != policy_binding_mode_map
        or set(raw_digest_map) != policy_paths
        or set(binding_digest_map) != policy_paths
    ):
        return {}, {}, {}, "policy_binding_contract_mismatch"
    if (
        not tracked_paths
        or fixed_point.get("artifact_kind")
        != "release_closeout_fixed_point_report"
        or fixed_point.get("producer") != FIXED_POINT_PRODUCER
        or fixed_point.get("status") != "pass"
        or fixed_point.get("artifact_status") != "current"
        or currentness_status != "current"
        or fixed_point.get("execution_pass_count") != 1
        or not execution_is_consistent
        or any(
            digest != SHA256_MISSING
            and (
                len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            )
            for digest in [*raw_digest_map.values(), *binding_digest_map.values()]
        )
        or any(
            mode not in SUPPORTED_BINDING_MODES
            for mode in binding_mode_map.values()
        )
    ):
        return {}, {}, {}, "invalid_v2_authority"
    if not _revision_bound_artifacts_match_current_revision(
        vault,
        policy_binding_mode_map,
        current_revision=current_revision,
    ):
        return {}, {}, {}, "revision_binding_source_revision_mismatch"
    return raw_digest_map, binding_digest_map, binding_mode_map, "ok"


def _sealed_preflight_summary(vault: Path) -> dict[str, Any]:
    payload, load_status = _load_optional(vault, SEALED_PREFLIGHT_PATH)
    preflight = payload.get("preflight") if isinstance(payload, dict) else {}
    preflight = preflight if isinstance(preflight, dict) else {}
    currentness = payload.get("currentness") if isinstance(payload, dict) else {}
    currentness = currentness if isinstance(currentness, dict) else {}
    status = str(payload.get("status", "missing")).strip() if payload else "missing"
    preflight_status = str(preflight.get("preflight_status", "")).strip()
    currentness_status = str(currentness.get("status", "")).strip()
    return {
        "path": SEALED_PREFLIGHT_PATH,
        "raw_digest": _sha256_file(vault / SEALED_PREFLIGHT_PATH),
        "load_status": load_status,
        "status": status,
        "preflight_status": preflight_status,
        "currentness_status": currentness_status,
        "current": (
            load_status == "ok"
            and status == "pass"
            and preflight_status in {"", "sealed_clean_pass"}
            and currentness_status in {"", "current"}
        ),
    }


def _finality_repair_route(
    *,
    classes: list[str],
    base_targets: list[str],
    initial_targets: list[str],
    fixed_point_authority_failed: bool,
    component_raw_binding_mismatch: bool,
    has_unowned_batch_mismatch: bool,
    has_fixed_point_writer_mismatch: bool,
) -> tuple[list[str], list[str], str]:
    resettle_refresh_required = bool(
        has_unowned_batch_mismatch
        or "unclassified_finality_current_check_failure" in classes
    )
    fixed_point_refresh_required = bool(
        fixed_point_authority_failed or initial_targets
    )
    attestation_refresh_required = (
        classes == ["finality_attestation_binding_mismatch"]
        or (
            component_raw_binding_mismatch
            and not fixed_point_refresh_required
        )
    )

    targets = list(base_targets)
    if fixed_point_refresh_required:
        targets.append("release-closeout-fixed-point")
    if attestation_refresh_required:
        targets.append("release-closeout-finality-attestation")
    if resettle_refresh_required:
        targets.append("release-finality-resettle-current-or-refresh")
    elif classes:
        targets.append("release-closeout-finality-verify")

    recommended_lane = (
        "release-finality-resettle-current-or-refresh"
        if resettle_refresh_required
        else "release-authority-sealed-preflight + release-closeout-fixed-point"
        if "sealed_preflight_artifact_mismatch" in classes
        and "fixed_point_tracked_writer_binding_mismatch" in classes
        else "release-authority-sealed-preflight"
        if classes == ["sealed_preflight_artifact_mismatch"]
        else "release-closeout-fixed-point"
        if fixed_point_refresh_required or has_fixed_point_writer_mismatch
        else "release-closeout-finality-attestation"
        if attestation_refresh_required
        else "release-closeout-finality-verify"
    )
    return (
        _dedupe_preserve_order(targets),
        _dedupe_preserve_order(initial_targets),
        recommended_lane,
    )


def _current_finality_classification(vault: Path) -> dict[str, Any]:
    return {
        "status": "pass",
        "classes": [],
        "primary_class": "current",
        "recommended_lane": "none",
        "recommended_targets": [],
        "recommended_fixed_point_initial_targets": [],
        "batch_manifest_artifact_binding_mismatches": [],
        "freshness_index_cohort_binding_mismatches": [],
        "sealed_preflight_artifact_binding_mismatches": [],
        "sealed_preflight": _sealed_preflight_summary(vault),
        "fixed_point_tracked_writer_binding_mismatches": [],
        "unowned_binding_mismatches": [],
        "summary": "finality current-check is current",
    }


def _finality_fixed_point_writer_mismatches(
    vault: Path,
    *,
    batch_mismatches: list[dict[str, str]],
    batch_classification: dict[str, Any],
    fixed_point_binding_mismatches: list[dict[str, str]],
) -> list[dict[str, str]]:
    fixed_point_writer_by_path = _fixed_point_writer_targets_by_path(vault)
    batch_mismatch_paths = {str(item["path"]) for item in batch_mismatches}
    result = list(
        batch_classification["fixed_point_tracked_writer_binding_mismatches"]
    )
    result.extend(
        {
            **item,
            "writer_target": fixed_point_writer_by_path.get(item["path"], ""),
        }
        for item in fixed_point_binding_mismatches
        if item["path"] not in batch_mismatch_paths
    )
    return result


def _finality_failure_classification(
    vault: Path,
    *,
    failures: list[str],
    binding_digest_mismatches: list[dict[str, str]],
    fixed_point_binding_mismatches: list[dict[str, str]],
    batch_manifest_artifact_binding_mismatches: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if not failures:
        return _current_finality_classification(vault)
    batch_mismatches = (
        batch_manifest_artifact_binding_mismatches
        if batch_manifest_artifact_binding_mismatches is not None
        else _batch_manifest_artifact_mismatches(vault)["binding_mismatches"]
    )
    batch_classification = classify_batch_replay_binding_mismatches(
        vault,
        batch_mismatches,
    )
    freshness_index_cohort = list(
        batch_classification["freshness_index_cohort_binding_mismatches"]
    )
    sealed_preflight_artifact_mismatches = list(
        batch_classification["sealed_preflight_artifact_binding_mismatches"]
    )
    unowned_batch_mismatches = list(
        batch_classification["unowned_binding_mismatches"]
    )
    sealed_preflight = _sealed_preflight_summary(vault)
    fixed_point_writer_mismatches = _finality_fixed_point_writer_mismatches(
        vault,
        batch_mismatches=batch_mismatches,
        batch_classification=batch_classification,
        fixed_point_binding_mismatches=fixed_point_binding_mismatches,
    )

    classes: list[str] = []
    recommended_targets = list(batch_classification["recommended_targets"])
    recommended_initial_targets = list(
        batch_classification["recommended_fixed_point_initial_targets"]
    )
    fixed_point_authority_failed = any(
        failure.startswith("fixed_point_authority_status:")
        for failure in failures
    )
    if fixed_point_authority_failed:
        classes.append("fixed_point_authority_failure")
    classes.extend(str(value) for value in batch_classification["classes"])
    if sealed_preflight_artifact_mismatches or (
        sealed_preflight["load_status"] == "ok" and not sealed_preflight["current"]
    ):
        if "sealed_preflight_artifact_mismatch" not in classes:
            classes.append("sealed_preflight_artifact_mismatch")
        recommended_targets.append("release-authority-sealed-preflight")
    if fixed_point_writer_mismatches:
        if "fixed_point_tracked_writer_binding_mismatch" not in classes:
            classes.append("fixed_point_tracked_writer_binding_mismatch")
        recommended_initial_targets.extend(
            item["writer_target"]
            for item in fixed_point_writer_mismatches
            if item["writer_target"]
        )
    if (
        binding_digest_mismatches
        and not fixed_point_authority_failed
        and not fixed_point_writer_mismatches
    ):
        classes.append("finality_attestation_binding_mismatch")
    component_raw_binding_mismatch = any(
        failure.endswith("_raw_binding_mismatch") for failure in failures
    )
    if component_raw_binding_mismatch:
        classes.append("terminal_component_raw_binding_mismatch")
    if failures and not classes:
        classes.append("unclassified_finality_current_check_failure")

    (
        recommended_targets,
        recommended_initial_targets,
        recommended_lane,
    ) = _finality_repair_route(
        classes=classes,
        base_targets=recommended_targets,
        initial_targets=recommended_initial_targets,
        fixed_point_authority_failed=fixed_point_authority_failed,
        component_raw_binding_mismatch=component_raw_binding_mismatch,
        has_unowned_batch_mismatch=bool(unowned_batch_mismatches),
        has_fixed_point_writer_mismatch=bool(fixed_point_writer_mismatches),
    )
    return {
        "status": "pass" if not failures else "fail",
        "classes": classes,
        "primary_class": classes[0] if classes else "current",
        "recommended_lane": recommended_lane,
        "recommended_targets": recommended_targets,
        "recommended_fixed_point_initial_targets": recommended_initial_targets,
        "batch_manifest_artifact_binding_mismatches": batch_mismatches,
        "freshness_index_cohort_binding_mismatches": freshness_index_cohort,
        "sealed_preflight_artifact_binding_mismatches": sealed_preflight_artifact_mismatches,
        "sealed_preflight": sealed_preflight,
        "fixed_point_tracked_writer_binding_mismatches": fixed_point_writer_mismatches,
        "unowned_binding_mismatches": unowned_batch_mismatches,
        "summary": (
            "finality current-check is current"
            if not failures
            else (
                f"primary_class={classes[0] if classes else 'unclassified'}; "
                f"recommended_lane={recommended_lane}; "
                f"recommended_targets={','.join(recommended_targets)}"
            )
        ),
    }


def _fixed_point_summary(vault: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    payload, load_status = _load_optional(vault, FIXED_POINT_REPORT_PATH)
    raw_digest = _sha256_file(vault / FIXED_POINT_REPORT_PATH)
    summary = {
        "path": FIXED_POINT_REPORT_PATH,
        "raw_digest": raw_digest,
        "binding_mode": RAW_BINDING_MODE,
        "load_status": load_status,
        "schema_version": _authority_schema_version(payload.get("schema_version")),
        "status": str(payload.get("status", "missing")).strip() if payload else "missing",
        "execution_pass_count": int(payload.get("execution_pass_count", 0) or 0),
        "raw_digest_map": _normalized_digest_map(payload.get("raw_digest_map")),
        "binding_digest_map": _normalized_digest_map(
            payload.get("binding_digest_map")
        ),
        "binding_mode_map": _normalized_digest_map(payload.get("binding_mode_map")),
    }
    return payload, summary, raw_digest


def _batch_manifest_summary(vault: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    payload, load_status = _load_optional(vault, BATCH_MANIFEST_PATH)
    raw_digest = _sha256_file(vault / BATCH_MANIFEST_PATH)
    raw_finality = payload.get("finality")
    finality: dict[str, Any] = raw_finality if isinstance(raw_finality, dict) else {}
    status_view = release_status_v2_view(payload) if payload else {}
    summary = {
        "path": BATCH_MANIFEST_PATH,
        "raw_digest": raw_digest,
        "binding_mode": RAW_BINDING_MODE,
        "load_status": load_status,
        "schema_version": _authority_schema_version(payload.get("schema_version")),
        "status": str(status_view.get("compatibility_status_value", "missing")).strip()
        if payload
        else "missing",
        "release_authority_status": str(status_view.get("release_authority_status", "unknown")).strip(),
        "semantic_release_status": str(status_view.get("semantic_release_status", "unknown")).strip(),
        "sealed_release_status": str(status_view.get("sealed_release_status", "unknown")).strip(),
        "finality_required": bool(finality.get("finality_required", False)),
        "finality_attestation_path": str(finality.get("finality_attestation_path", "")).strip(),
    }
    return payload, summary, raw_digest


def _self_check_summary(vault: Path, *, batch_raw_digest: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    payload, load_status = _load_optional(vault, SELF_CHECK_PATH)
    raw_digest = _sha256_file(vault / SELF_CHECK_PATH)
    raw_status = payload.get("status")
    status_payload: dict[str, Any] = raw_status if isinstance(raw_status, dict) else {}
    raw_closeout_inputs = payload.get("closeout_inputs")
    closeout_inputs: dict[str, Any] = raw_closeout_inputs if isinstance(raw_closeout_inputs, dict) else {}
    batch_fingerprint = str(closeout_inputs.get("batch_manifest_fingerprint", "")).strip()
    summary = {
        "path": SELF_CHECK_PATH,
        "raw_digest": raw_digest,
        "binding_mode": RAW_BINDING_MODE,
        "load_status": load_status,
        "result": str(status_payload.get("result", "missing")).strip() if payload else "missing",
        "batch_manifest_fingerprint": batch_fingerprint,
        "batch_manifest_fingerprint_matches_current": bool(
            batch_fingerprint and batch_fingerprint == batch_raw_digest
        ),
    }
    return payload, summary, raw_digest


def _external_report_manifest_summary(vault: Path) -> dict[str, Any]:
    payload, load_status = _load_optional(vault, EXTERNAL_REPORT_MANIFEST_PATH)
    raw_provenance = payload.get("distribution_provenance")
    provenance: dict[str, Any] = raw_provenance if isinstance(raw_provenance, dict) else {}
    return {
        "path": EXTERNAL_REPORT_MANIFEST_PATH,
        "raw_digest": _sha256_file(vault / EXTERNAL_REPORT_MANIFEST_PATH),
        "binding_mode": RAW_BINDING_MODE,
        "load_status": load_status,
        "mode": str(provenance.get("mode", "")).strip(),
        "distribution_provenance_status": str(provenance.get("status", "")).strip(),
    }


def _finality_failures(
    *,
    fixed_point_report: dict[str, Any],
    batch_manifest: dict[str, Any],
    self_check: dict[str, Any],
    fixed_point_authority_status: str,
    matches_fixed_point_binding_digest_map: bool,
    binding_digest_mismatches: list[dict[str, str]],
) -> list[str]:
    failures: list[str] = []
    if fixed_point_report["load_status"] != "ok":
        failures.append("fixed_point_report_unavailable")
    if (
        fixed_point_report["schema_version"] != 2
        or fixed_point_report["status"] != "pass"
        or fixed_point_report["execution_pass_count"] != 1
    ):
        failures.append("fixed_point_not_current_v2_authority")
    if fixed_point_authority_status != "ok":
        failures.append(
            f"fixed_point_authority_status:{fixed_point_authority_status}"
        )
    if batch_manifest["load_status"] != "ok":
        failures.append("batch_manifest_unavailable")
    if batch_manifest["schema_version"] != 2:
        failures.append("batch_manifest_unsupported_schema_version")
    if not batch_manifest["finality_required"]:
        failures.append("batch_manifest_finality_not_required")
    if batch_manifest["finality_attestation_path"] != DEFAULT_OUT:
        failures.append("batch_manifest_finality_pointer_mismatch")
    if self_check["load_status"] != "ok":
        failures.append("self_check_unavailable")
    if self_check["result"] != "pass":
        failures.append("self_check_not_pass")
    if not self_check["batch_manifest_fingerprint_matches_current"]:
        failures.append("self_check_batch_raw_binding_mismatch")
    if (
        fixed_point_authority_status == "ok"
        and not matches_fixed_point_binding_digest_map
    ):
        failures.append("tracked_binding_digest_map_mismatch")
        failures.extend(
            f"binding_digest_mismatch:{item['path']}"
            for item in binding_digest_mismatches
        )
    return failures


def build_report(
    vault: Path,
    *,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    fixed_payload, fixed_point_report, _fixed_raw_digest = _fixed_point_summary(vault)
    _batch_payload, batch_manifest, batch_raw_digest = _batch_manifest_summary(vault)
    _self_payload, self_check, _self_raw_digest = _self_check_summary(
        vault,
        batch_raw_digest=batch_raw_digest,
    )
    external_report_manifest = _external_report_manifest_summary(vault)

    (
        fixed_point_raw_digest_map,
        fixed_point_binding_digest_map,
        fixed_point_binding_mode_map,
        fixed_point_authority_status,
    ) = _fixed_point_authority_maps(vault, fixed_payload)
    tracked_paths = sorted(fixed_point_binding_mode_map)
    tracked_raw_digest_map = _raw_digest_map(vault, tracked_paths)
    tracked_binding_digest_map = _binding_digest_map(
        vault,
        fixed_point_binding_mode_map,
    )
    binding_digest_mismatches = _binding_mismatches(
        fixed_point_binding_digest_map,
        tracked_binding_digest_map,
        binding_mode_map=fixed_point_binding_mode_map,
    )
    matches_fixed_point_binding_digest_map = (
        fixed_point_authority_status == "ok"
        and not binding_digest_mismatches
        and bool(tracked_paths)
        and bool(fixed_point_binding_digest_map)
    )
    finality_failures = _finality_failures(
        fixed_point_report=fixed_point_report,
        batch_manifest=batch_manifest,
        self_check=self_check,
        fixed_point_authority_status=fixed_point_authority_status,
        matches_fixed_point_binding_digest_map=matches_fixed_point_binding_digest_map,
        binding_digest_mismatches=binding_digest_mismatches,
    )
    finality_status = "pass" if not finality_failures else "fail"

    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="release_closeout_finality_attestation",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=FINALITY_ATTESTATION_SOURCE_PATHS,
            file_inputs={
                "fixed_point_report": FIXED_POINT_REPORT_PATH,
                "batch_manifest": BATCH_MANIFEST_PATH,
                "self_check": SELF_CHECK_PATH,
                "external_report_manifest": EXTERNAL_REPORT_MANIFEST_PATH,
            },
            path_group_inputs={"tracked_artifacts": tracked_paths},
            text_inputs={
                "finality_status": finality_status,
                "matches_fixed_point_binding_digest_map": str(
                    matches_fixed_point_binding_digest_map
                ),
            },
            source_tree_excluded_files=(DEFAULT_OUT,),
        ),
        "schema_version": 2,
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "fixed_point_report": fixed_point_report,
        "batch_manifest": batch_manifest,
        "self_check": self_check,
        "external_report_manifest": external_report_manifest,
        "tracked_raw_digest_map": tracked_raw_digest_map,
        "tracked_binding_digest_map": tracked_binding_digest_map,
        "tracked_binding_mode_map": fixed_point_binding_mode_map,
        "fixed_point_authority_status": fixed_point_authority_status,
        "matches_fixed_point_binding_digest_map": matches_fixed_point_binding_digest_map,
        "binding_digest_mismatches": binding_digest_mismatches,
        "finality_status": finality_status,
        "finality_failures": finality_failures,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release closeout finality attestation schema validation failed",
        )
    )


def _attestation_load_failure_report(vault: Path, load_status: str) -> dict[str, Any]:
    load_failures = [f"attestation_load_status:{load_status}"]
    return {
        "status": "fail",
        "failures": load_failures,
        "failure_classification": _finality_failure_classification(
            vault,
            failures=load_failures,
            binding_digest_mismatches=[],
            fixed_point_binding_mismatches=[],
        ),
        "binding_digest_mismatches": [],
        "fixed_point_binding_mismatches": [],
        "component_binding_mismatches": [],
        "batch_manifest_artifact_binding_mismatches": [],
        "batch_manifest_authority_failures": [],
    }


def _attestation_component_verification(
    vault: Path,
    payload: dict[str, Any],
) -> tuple[list[str], list[dict[str, str]]]:
    failures: list[str] = []
    component_binding_mismatches: list[dict[str, str]] = []
    for field in ("fixed_point_report", "batch_manifest", "self_check", "external_report_manifest"):
        item = payload.get(field)
        if not isinstance(item, dict):
            failures.append(f"{field}_missing")
            continue
        rel_path = str(item.get("path", "")).strip()
        expected = str(item.get("raw_digest", "")).strip()
        binding_mode = str(item.get("binding_mode", "")).strip()
        if binding_mode != RAW_BINDING_MODE:
            failures.append(f"{field}_binding_mode_not_raw")
        actual = _sha256_file(vault / rel_path) if rel_path else SHA256_MISSING
        if expected != actual:
            component_binding_mismatches.append(
                {
                    "field": field,
                    "path": rel_path,
                    "binding_mode": RAW_BINDING_MODE,
                    "recorded_binding_digest": expected,
                    "current_binding_digest": actual,
                }
            )
    return failures, component_binding_mismatches


def _attestation_tracked_binding_verification(
    vault: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    fixed_payload, _fixed_summary, _fixed_digest = _fixed_point_summary(vault)
    (
        _fixed_raw_digest_map,
        fixed_binding_digest_map,
        fixed_binding_mode_map,
        fixed_authority_status,
    ) = _fixed_point_authority_maps(vault, fixed_payload)
    current_binding_digest_map = _binding_digest_map(
        vault,
        fixed_binding_mode_map,
    )
    recorded_binding_digest_map = _normalized_digest_map(
        payload.get("tracked_binding_digest_map")
    )
    if fixed_authority_status != "ok":
        return {
            "failures": [
                f"fixed_point_authority_status:{fixed_authority_status}"
            ],
            "binding_digest_mismatches": [],
            "fixed_point_binding_mismatches": [],
            "binding_mode_map_mismatch": False,
            "recorded_binding_digest_map": recorded_binding_digest_map,
            "current_binding_digest_map": {},
        }
    recorded_binding_mode_map = _normalized_digest_map(
        payload.get("tracked_binding_mode_map")
    )
    binding_digest_mismatches = _recorded_binding_mismatches(
        recorded=recorded_binding_digest_map,
        current=current_binding_digest_map,
        binding_mode_map=fixed_binding_mode_map,
    )
    fixed_point_binding_mismatches = _binding_mismatches(
        fixed_binding_digest_map,
        current_binding_digest_map,
        binding_mode_map=fixed_binding_mode_map,
    )
    failures: list[str] = []
    if recorded_binding_mode_map != fixed_binding_mode_map:
        failures.append("tracked_binding_mode_map_current_mismatch")
    if binding_digest_mismatches or not recorded_binding_digest_map:
        failures.append("tracked_binding_digest_map_current_mismatch")
    if fixed_point_binding_mismatches or not fixed_binding_digest_map:
        failures.append("fixed_point_binding_digest_map_current_mismatch")
    return {
        "failures": failures,
        "binding_digest_mismatches": binding_digest_mismatches,
        "fixed_point_binding_mismatches": fixed_point_binding_mismatches,
        "binding_mode_map_mismatch": recorded_binding_mode_map
        != fixed_binding_mode_map,
        "recorded_binding_digest_map": recorded_binding_digest_map,
        "current_binding_digest_map": current_binding_digest_map,
    }


def _attestation_batch_and_status_failures(
    vault: Path,
    payload: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    failures: list[str] = []
    batch_diagnostics = _batch_manifest_artifact_mismatches(vault)
    failures.extend(batch_diagnostics["authority_failures"])
    if batch_diagnostics["binding_mismatches"]:
        failures.append("batch_manifest_artifact_binding_current_mismatch")
    sealed_preflight = _sealed_preflight_summary(vault)
    if sealed_preflight["load_status"] == "ok" and not sealed_preflight["current"]:
        failures.append("sealed_preflight_not_current")
    if str(payload.get("finality_status", "")).strip() != "pass":
        failures.append("attestation_finality_status_not_pass")
    return failures, batch_diagnostics


def _verify_attestation_diagnostics(
    vault: Path,
    attestation_path: str = DEFAULT_OUT,
) -> dict[str, Any]:
    resolved = resolve_schema_backed_report_output_path(
        vault,
        attestation_path,
        default_relative_path=DEFAULT_OUT,
    )
    payload, diagnostics = load_optional_json_object_with_diagnostics(resolved)
    load_status = str(diagnostics.get("status", "unknown")).strip() or "unknown"
    if load_status != "ok":
        return _attestation_load_failure_report(vault, load_status)
    if payload.get("schema_version") != 2:
        return _attestation_load_failure_report(vault, "unsupported_schema_version")

    current_revision = resolve_source_revision(vault).revision
    attestation_revision = str(payload.get("source_revision", "")).strip()
    source_revision_failures = (
        []
        if attestation_revision == current_revision
        else ["attestation_source_revision_mismatch"]
    )

    component_failures, component_binding_mismatches = _attestation_component_verification(
        vault,
        payload,
    )
    tracked = _attestation_tracked_binding_verification(vault, payload)
    batch_failures, batch_diagnostics = _attestation_batch_and_status_failures(
        vault,
        payload,
    )
    failures = [
        *source_revision_failures,
        *component_failures,
        *tracked["failures"],
        *(
            f"{item['field']}_raw_binding_mismatch"
            for item in component_binding_mismatches
        ),
        *batch_failures,
    ]
    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "failure_classification": _finality_failure_classification(
            vault,
            failures=failures,
            binding_digest_mismatches=tracked["binding_digest_mismatches"],
            fixed_point_binding_mismatches=tracked[
                "fixed_point_binding_mismatches"
            ],
            batch_manifest_artifact_binding_mismatches=batch_diagnostics[
                "binding_mismatches"
            ],
        ),
        "binding_digest_mismatches": tracked["binding_digest_mismatches"],
        "fixed_point_binding_mismatches": tracked[
            "fixed_point_binding_mismatches"
        ],
        "component_binding_mismatches": component_binding_mismatches,
        "batch_manifest_artifact_binding_mismatches": batch_diagnostics[
            "binding_mismatches"
        ],
        "batch_manifest_authority_failures": batch_diagnostics[
            "authority_failures"
        ],
        "attestation_source_revision": attestation_revision,
        "current_source_revision": current_revision,
    }


def verify_attestation(vault: Path, attestation_path: str = DEFAULT_OUT) -> tuple[bool, list[str]]:
    report = _verify_attestation_diagnostics(vault, attestation_path)
    failures = [str(item) for item in report.get("failures", [])]
    return report["status"] == "pass", failures


def verify_attestation_report(vault: Path, attestation_path: str = DEFAULT_OUT) -> dict[str, Any]:
    return _verify_attestation_diagnostics(vault, attestation_path)


def write_verify_report(vault: Path, report: dict[str, Any], out_path: str) -> Path:
    raw_path = Path(out_path)
    destination = raw_path if raw_path.is_absolute() else vault / raw_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or verify release closeout finality attestation.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--attestation", default=DEFAULT_OUT)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--verify-out")
    parser.add_argument("--no-fail", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    if args.verify:
        report = verify_attestation_report(vault, args.attestation)
        if args.verify_out:
            write_verify_report(vault, report, args.verify_out)
        stream = sys.stdout if report["status"] == "pass" else sys.stderr
        print(json.dumps(report, sort_keys=True), file=stream)
        return 0 if report["status"] == "pass" or args.no_fail else 1
    report = build_report(vault, policy_path=args.policy_path)
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    return 0 if report["finality_status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
