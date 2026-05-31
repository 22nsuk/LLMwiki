from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ops.scripts.core.path_runtime import normalize_repo_path_text
from ops.scripts.core.policy_runtime import report_path


BUCKET_CHECKED_IN_CANONICAL_SOURCE_SIDE = "checked_in_canonical_source_side"
BUCKET_BUILD_RELEASE_AUTHORITATIVE_SIDECAR = "build_release_authoritative_sidecar"
BUCKET_OBSERVATIONAL_DIAGNOSTIC = "observational_diagnostic"
BUCKET_ARCHIVAL_HISTORICAL = "archival_historical"
REPORT_BUCKETS = {
    BUCKET_CHECKED_IN_CANONICAL_SOURCE_SIDE,
    BUCKET_BUILD_RELEASE_AUTHORITATIVE_SIDECAR,
    BUCKET_OBSERVATIONAL_DIAGNOSTIC,
    BUCKET_ARCHIVAL_HISTORICAL,
}
DOCUMENTATION_STATUS_PASS = "pass"
DOCUMENTATION_STATUS_FAIL = "fail"
DEFAULT_BUCKET_DOC_PATH = "docs/repository-surfaces.md"
_DOCUMENTATION_REQUIRED_FRAGMENTS = (
    BUCKET_CHECKED_IN_CANONICAL_SOURCE_SIDE,
    BUCKET_BUILD_RELEASE_AUTHORITATIVE_SIDECAR,
    BUCKET_OBSERVATIONAL_DIAGNOSTIC,
    BUCKET_ARCHIVAL_HISTORICAL,
    "ops/reports/",
    "build/release/",
)
_BUILD_RELEASE_DIAGNOSTIC_SUFFIXES = (
    "-plan.json",
    "-preflight.json",
    "-preseal.json",
)


def _normalized_report_path(path: str | Path) -> str:
    normalized = normalize_repo_path_text(Path(path).as_posix())
    if normalized is None or normalized in {".", ".."} or normalized.startswith("../"):
        raise ValueError(f"report path must be vault-relative: {path}")
    return normalized


def _is_archive_path(rel_path: str) -> bool:
    parts = rel_path.split("/")
    return "archive" in parts or rel_path.startswith("ops/reports/archival/")


def _is_ops_reports_canonical(rel_path: str) -> bool:
    if not rel_path.startswith("ops/reports/"):
        return False
    remainder = rel_path.removeprefix("ops/reports/")
    return "/" not in remainder and remainder.endswith(".json")


def _is_build_release_authoritative(rel_path: str) -> bool:
    if not rel_path.startswith("build/release/") or not rel_path.endswith(".json"):
        return False
    name = Path(rel_path).name
    if any(name.endswith(suffix) for suffix in _BUILD_RELEASE_DIAGNOSTIC_SUFFIXES):
        return False
    return "dry-run" not in rel_path


def classify_report_bucket(path: str | Path) -> str:
    rel_path = _normalized_report_path(path)
    if _is_archive_path(rel_path):
        return BUCKET_ARCHIVAL_HISTORICAL
    if _is_build_release_authoritative(rel_path):
        return BUCKET_BUILD_RELEASE_AUTHORITATIVE_SIDECAR
    if _is_ops_reports_canonical(rel_path):
        return BUCKET_CHECKED_IN_CANONICAL_SOURCE_SIDE
    return BUCKET_OBSERVATIONAL_DIAGNOSTIC


def report_bucket_documentation_status(
    vault: Path,
    *,
    docs_path: str | Path = DEFAULT_BUCKET_DOC_PATH,
) -> dict[str, Any]:
    path = vault / _normalized_report_path(docs_path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    missing = [fragment for fragment in _DOCUMENTATION_REQUIRED_FRAGMENTS if fragment not in text]
    return {
        "status": DOCUMENTATION_STATUS_PASS if not missing else DOCUMENTATION_STATUS_FAIL,
        "path": report_path(vault, path),
        "missing_fragments": missing,
    }


def assign_report_bucket(
    path: str | Path,
    *,
    documentation_compliance_status: str = DOCUMENTATION_STATUS_PASS,
) -> dict[str, Any]:
    rel_path = _normalized_report_path(path)
    bucket = classify_report_bucket(rel_path)
    return {
        "report_path": rel_path,
        "bucket": bucket,
        "rationale": _bucket_rationale(rel_path, bucket),
        "is_canonical": bucket == BUCKET_CHECKED_IN_CANONICAL_SOURCE_SIDE,
        "documentation_compliance_status": (
            documentation_compliance_status
            if documentation_compliance_status in {DOCUMENTATION_STATUS_PASS, DOCUMENTATION_STATUS_FAIL}
            else DOCUMENTATION_STATUS_FAIL
        ),
    }


def assign_report_buckets(
    vault: Path,
    paths: list[str | Path],
    *,
    docs_path: str | Path = DEFAULT_BUCKET_DOC_PATH,
) -> dict[str, Any]:
    documentation = report_bucket_documentation_status(vault, docs_path=docs_path)
    return {
        "documentation_compliance_status": documentation["status"],
        "documentation": documentation,
        "assignments": [
            assign_report_bucket(
                path,
                documentation_compliance_status=str(documentation["status"]),
            )
            for path in paths
        ],
    }


def _bucket_rationale(rel_path: str, bucket: str) -> str:
    if bucket == BUCKET_ARCHIVAL_HISTORICAL:
        return "path is under an archive/archival evidence surface"
    if bucket == BUCKET_BUILD_RELEASE_AUTHORITATIVE_SIDECAR:
        return "active build/release JSON sidecar is bound by staged release authority"
    if bucket == BUCKET_CHECKED_IN_CANONICAL_SOURCE_SIDE:
        return "top-level ops/reports JSON is source-side canonical evidence"
    return "path is diagnostic, scratch, nested report output, or otherwise non-authoritative"


def move_report_delete_first(
    vault: Path,
    *,
    source_path: str | Path,
    destination_path: str | Path,
) -> dict[str, Any]:
    source_rel = _normalized_report_path(source_path)
    destination_rel = _normalized_report_path(destination_path)
    source = vault / source_rel
    destination = vault / destination_rel
    if not source.exists():
        raise FileNotFoundError(source_rel)
    if destination.exists():
        raise FileExistsError(destination_rel)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(source.as_posix(), destination.as_posix())
    return {
        "source_path": source_rel,
        "destination_path": destination_rel,
        "source_bucket": classify_report_bucket(source_rel),
        "destination_bucket": classify_report_bucket(destination_rel),
        "source_exists_after_move": source.exists(),
        "destination_exists_after_move": destination.exists(),
        "delete_first": True,
    }
