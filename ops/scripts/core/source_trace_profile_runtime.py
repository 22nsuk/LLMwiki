from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ops.scripts.wiki_manifest import release_manifest_excludes_path

from .source_trace_runtime import (
    extract_source_trace_refs,
    normalize_source_trace_ref,
    report_source_trace_path,
    resolve_source_trace_ref,
)

STRICT_PROFILE = "strict"
RELEASE_ARCHIVE_PROFILE = "release_archive"
SOURCE_PACKAGE_PROFILE = "source_package"
PUBLIC_CODE_MIRROR_PROFILE = "public_code_mirror"

PRESENT = "present"
MISSING_UNCLASSIFIED = "missing_unclassified"
MISSING_EXPORT_EXCLUDED_BOUND = "missing_export_excluded_bound"
MISSING_EXPORT_EXCLUDED_UNBOUND = "missing_export_excluded_unbound"
MISSING_PRIVATE_SURFACE_EXPECTED = "missing_private_surface_expected"
MISSING_GENERATED_REBUILDABLE = "missing_generated_rebuildable"

MISSING_STATUSES = {
    MISSING_UNCLASSIFIED,
    MISSING_EXPORT_EXCLUDED_BOUND,
    MISSING_EXPORT_EXCLUDED_UNBOUND,
    MISSING_PRIVATE_SURFACE_EXPECTED,
    MISSING_GENERATED_REBUILDABLE,
}

PROFILE_ALLOWED_MISSING_STATUSES = {
    STRICT_PROFILE: set(),
    RELEASE_ARCHIVE_PROFILE: {
        MISSING_EXPORT_EXCLUDED_BOUND,
        MISSING_GENERATED_REBUILDABLE,
    },
    SOURCE_PACKAGE_PROFILE: {
        MISSING_EXPORT_EXCLUDED_BOUND,
        MISSING_GENERATED_REBUILDABLE,
    },
    PUBLIC_CODE_MIRROR_PROFILE: {
        MISSING_EXPORT_EXCLUDED_BOUND,
        MISSING_PRIVATE_SURFACE_EXPECTED,
        MISSING_GENERATED_REBUILDABLE,
    },
}

PRIVATE_SURFACE_PREFIXES = ("raw/", "wiki/", "system/")
GENERATED_REBUILDABLE_PREFIXES = (
    "ops/reports/",
    "ops/operator/",
    "ops/manifest.json",
    "ops/raw-registry.json",
    "ops/script-output-surfaces.json",
    "build/release/",
)
BOUND_EXPORT_EXCLUDED_PREFIXES = ("runs/", "external-reports/")
UNBOUND_EXPORT_EXCLUDED_PREFIXES = ("tmp/", "build/")


def _requirement(status: str, rel_path: str) -> dict[str, str]:
    if status == PRESENT:
        return {
            "authority": "path exists in the current execution profile",
            "digest": "file content is available to the caller",
            "linkage": "direct source trace target",
            "repair_target": "",
        }
    if status == MISSING_EXPORT_EXCLUDED_BOUND:
        return {
            "authority": "release archive exclusion policy and out-of-band full-vault evidence lifecycle",
            "digest": "bind via release/source-package digest plus the referenced evidence artifact when replay is required",
            "linkage": "source package self-description or release evidence bundle must explain the excluded surface",
            "repair_target": "",
        }
    if status == MISSING_GENERATED_REBUILDABLE:
        return {
            "authority": "generated-artifact rebuild target",
            "digest": "regenerate the artifact and bind the new digest through freshness/finality evidence",
            "linkage": "generated artifact index or release evidence bundle",
            "repair_target": "rerun the owning Make target before treating this as replay evidence",
        }
    if status == MISSING_PRIVATE_SURFACE_EXPECTED:
        return {
            "authority": "public/private distribution profile boundary",
            "digest": "not published in this profile",
            "linkage": "public mirror must point back to a full-vault release/evidence authority",
            "repair_target": "",
        }
    if status == MISSING_EXPORT_EXCLUDED_UNBOUND:
        return {
            "authority": "missing export-excluded target has no accepted durable linkage",
            "digest": "unbound",
            "linkage": "unbound",
            "repair_target": f"move {rel_path} to a durable source trace target or add explicit release evidence linkage",
        }
    return {
        "authority": "none",
        "digest": "unbound",
        "linkage": "unbound",
        "repair_target": f"restore or correct source trace target {rel_path}",
    }


def _has_prefix(rel_path: str, prefixes: tuple[str, ...]) -> bool:
    return any(rel_path == prefix.rstrip("/") or rel_path.startswith(prefix) for prefix in prefixes)


def _missing_status_for_path(rel_path: str, *, profile: str) -> str:
    if profile == PUBLIC_CODE_MIRROR_PROFILE and _has_prefix(rel_path, PRIVATE_SURFACE_PREFIXES):
        return MISSING_PRIVATE_SURFACE_EXPECTED
    if _has_prefix(rel_path, GENERATED_REBUILDABLE_PREFIXES):
        return MISSING_GENERATED_REBUILDABLE
    if not release_manifest_excludes_path(rel_path):
        return MISSING_UNCLASSIFIED
    if _has_prefix(rel_path, UNBOUND_EXPORT_EXCLUDED_PREFIXES):
        return MISSING_EXPORT_EXCLUDED_UNBOUND
    if _has_prefix(rel_path, BOUND_EXPORT_EXCLUDED_PREFIXES):
        return MISSING_EXPORT_EXCLUDED_BOUND
    return MISSING_EXPORT_EXCLUDED_UNBOUND


def source_trace_profile_allows_missing(status: str, *, profile: str) -> bool:
    return status in PROFILE_ALLOWED_MISSING_STATUSES.get(profile, set())


def source_trace_profile_blocks(status: str, *, profile: str) -> bool:
    return status in MISSING_STATUSES and not source_trace_profile_allows_missing(
        status,
        profile=profile,
    )


def classify_source_trace_targets(
    vault: Path,
    source_trace: str | None,
    resolution_map: dict[str, list[str]] | None = None,
    *,
    profile: str = STRICT_PROFILE,
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for ref in extract_source_trace_refs(source_trace):
        resolved = resolve_source_trace_ref(vault, ref, resolution_map)
        normalized_ref = normalize_source_trace_ref(ref)
        if resolved is None:
            status = PRESENT
            resolved_path = ""
            exists = True
        else:
            resolved_absolute = resolved if resolved.is_absolute() else (Path.cwd() / resolved).resolve()
            resolved_path = report_source_trace_path(vault.resolve(), resolved_absolute)
            exists = resolved.exists()
            classification_path = (
                resolved_path
                if normalized_ref.startswith(("/", "../")) or os.path.isabs(normalized_ref)
                else normalized_ref
            )
            status = (
                PRESENT
                if exists
                else _missing_status_for_path(classification_path, profile=profile)
            )
        requirement = _requirement(status, classification_path if resolved is not None else normalized_ref)
        targets.append(
            {
                "ref": normalized_ref,
                "resolved_path": resolved_path,
                "exists": exists,
                "classification": status,
                "profile": profile,
                "profile_allows_missing": source_trace_profile_allows_missing(
                    status,
                    profile=profile,
                ),
                "blocks_profile": source_trace_profile_blocks(status, profile=profile),
                "authority_requirement": requirement["authority"],
                "digest_requirement": requirement["digest"],
                "linkage_requirement": requirement["linkage"],
                "repair_target": requirement["repair_target"],
            }
        )
    return targets


def missing_source_trace_targets_for_profile(
    vault: Path,
    source_trace: str | None,
    resolution_map: dict[str, list[str]] | None = None,
    *,
    profile: str = STRICT_PROFILE,
) -> list[dict[str, Any]]:
    return [
        target
        for target in classify_source_trace_targets(
            vault,
            source_trace,
            resolution_map,
            profile=profile,
        )
        if target["classification"] in MISSING_STATUSES
    ]


def blocking_source_trace_targets_for_profile(
    vault: Path,
    source_trace: str | None,
    resolution_map: dict[str, list[str]] | None = None,
    *,
    profile: str = STRICT_PROFILE,
) -> list[dict[str, Any]]:
    return [
        target
        for target in missing_source_trace_targets_for_profile(
            vault,
            source_trace,
            resolution_map,
            profile=profile,
        )
        if target["blocks_profile"]
    ]


def source_trace_profile_summary(targets: list[dict[str, Any]]) -> dict[str, Any]:
    classification_counts: dict[str, int] = {}
    for target in targets:
        classification = str(target.get("classification", "")).strip()
        classification_counts[classification] = classification_counts.get(classification, 0) + 1
    return {
        "target_count": len(targets),
        "classification_counts": classification_counts,
        "missing_count": sum(
            count
            for classification, count in classification_counts.items()
            if classification in MISSING_STATUSES
        ),
        "blocking_missing_count": sum(1 for target in targets if target.get("blocks_profile")),
        "allowed_missing_count": sum(
            1
            for target in targets
            if target.get("classification") in MISSING_STATUSES
            and target.get("profile_allows_missing")
        ),
    }
