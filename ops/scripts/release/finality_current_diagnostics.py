from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXED_POINT_POLICY_PATH = "ops/policies/release-closeout-fixed-point.json"
SEALED_PREFLIGHT_PATH = "ops/reports/release-closeout-sealed-rehearsal-check.json"
FRESHNESS_INDEX_COHORT_TARGETS = {
    "ops/reports/artifact-freshness-report.json": "artifact-freshness",
    "ops/reports/generated-artifact-index.json": "generated-artifact-index-body",
    "ops/reports/release-evidence-cohort.json": "release-evidence-cohort",
}


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def fixed_point_writer_targets_by_path(vault: Path) -> dict[str, str]:
    policy_path = vault / FIXED_POINT_POLICY_PATH
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    writers = policy.get("writers")
    if not isinstance(writers, list):
        return {}
    result: dict[str, str] = {}
    for writer in writers:
        if not isinstance(writer, dict):
            continue
        target = str(writer.get("target", "")).strip()
        produces = writer.get("produces")
        if not target or not isinstance(produces, list):
            continue
        for path in produces:
            rel_path = str(path).strip()
            if rel_path:
                result[rel_path] = target
    return result


def classify_batch_replay_digest_mismatches(
    vault: Path,
    digest_mismatches: list[dict[str, str]],
    *,
    source_freshness: dict[str, Any] | None = None,
    content_matches: bool | None = None,
) -> dict[str, Any]:
    freshness_index_cohort = [
        item
        for item in digest_mismatches
        if item["path"] in FRESHNESS_INDEX_COHORT_TARGETS
    ]
    sealed_preflight = [
        item for item in digest_mismatches if item["path"] == SEALED_PREFLIGHT_PATH
    ]
    fixed_point_writer_by_path = fixed_point_writer_targets_by_path(vault)
    fixed_point_writer_mismatches = [
        {
            **item,
            "writer_target": fixed_point_writer_by_path.get(item["path"], ""),
        }
        for item in digest_mismatches
        if item["path"] not in FRESHNESS_INDEX_COHORT_TARGETS
        and item["path"] != SEALED_PREFLIGHT_PATH
        and fixed_point_writer_by_path.get(item["path"])
    ]

    classes: list[str] = []
    recommended_targets: list[str] = []
    recommended_initial_targets: list[str] = []
    source_freshness_status = (
        str(source_freshness.get("status", "")).strip()
        if isinstance(source_freshness, dict)
        else ""
    )
    if freshness_index_cohort:
        classes.append("batch_manifest_freshness_index_cohort_digest_mismatch")
        recommended_initial_targets.extend(
            FRESHNESS_INDEX_COHORT_TARGETS[item["path"]]
            for item in freshness_index_cohort
        )
    if sealed_preflight:
        classes.append("sealed_preflight_artifact_mismatch")
        recommended_targets.append("release-authority-sealed-preflight")
    if fixed_point_writer_mismatches:
        classes.append("fixed_point_tracked_writer_mismatch")
        recommended_initial_targets.extend(
            item["writer_target"]
            for item in fixed_point_writer_mismatches
            if item["writer_target"]
        )
    if source_freshness_status and source_freshness_status != "pass":
        classes.append("batch_manifest_source_freshness_mismatch")
        recommended_targets.append("release-finality-resettle-current-or-refresh")
    if content_matches is False and not digest_mismatches:
        classes.append("batch_manifest_content_mismatch")
        recommended_targets.append("release-closeout-batch-manifest-promote")
    if digest_mismatches and not classes:
        classes.append("batch_manifest_replay_digest_mismatch")

    if recommended_initial_targets:
        recommended_targets.append("release-closeout-fixed-point")
    if classes:
        recommended_targets.extend(
            [
                "release-closeout-batch-manifest-replay-verify",
                "release-closeout-finality-verify",
            ]
        )

    recommended_targets = dedupe_preserve_order(recommended_targets)
    recommended_initial_targets = dedupe_preserve_order(recommended_initial_targets)
    recommended_lane = (
        "release-authority-sealed-preflight + release-closeout-fixed-point"
        if "sealed_preflight_artifact_mismatch" in classes
        and recommended_initial_targets
        else "release-authority-sealed-preflight"
        if classes == ["sealed_preflight_artifact_mismatch"]
        else "release-closeout-fixed-point"
        if recommended_initial_targets
        else "release-finality-resettle-current-or-refresh"
    )
    return {
        "status": "pass" if not classes else "fail",
        "classes": classes,
        "primary_class": classes[0] if classes else "current",
        "recommended_lane": recommended_lane,
        "recommended_targets": recommended_targets,
        "recommended_fixed_point_initial_targets": recommended_initial_targets,
        "digest_mismatches": digest_mismatches,
        "source_freshness_status": source_freshness_status or "unknown",
        "source_freshness": source_freshness or {},
        "content_matches": content_matches,
        "freshness_index_cohort_digest_mismatches": freshness_index_cohort,
        "sealed_preflight_artifact_digest_mismatches": sealed_preflight,
        "fixed_point_tracked_writer_mismatches": fixed_point_writer_mismatches,
        "summary": (
            "batch manifest replay artifact digests are current"
            if not classes
            else (
                f"primary_class={classes[0] if classes else 'unclassified'}; "
                f"recommended_lane={recommended_lane}; "
                f"recommended_targets={','.join(recommended_targets)}"
            )
        ),
    }
