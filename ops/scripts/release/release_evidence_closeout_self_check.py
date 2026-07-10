"""Release evidence closeout self-check artifact generation.

Builds a snapshot of release evidence and batch state immediately after closeout
to enable drift detection. Captures batch manifest, cohort evidence, and input
digest fingerprints for cross-run comparison.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_binding_runtime import (
    BINDING_MODES,
    binding_file_digest,
    is_sha256_digest,
)
from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    write_schema_backed_report,
)
from ops.scripts.core.output_runtime import display_path
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import (
    RELEASE_EVIDENCE_CLOSEOUT_SELF_CHECK_SCHEMA_PATH,
)

PRODUCER = "ops.scripts.release_evidence_closeout_self_check"
DEFAULT_OUT = "ops/reports/release-evidence-closeout-self-check.json"
DEFAULT_BATCH_MANIFEST = "ops/reports/release-closeout-batch-manifest.json"
DEFAULT_EVIDENCE_COHORT = "ops/reports/release-evidence-cohort.json"
SOURCE_COMMAND = (
    "python -m ops.scripts.release_evidence_closeout_self_check "
    "--vault . "
    f"--batch-manifest {DEFAULT_BATCH_MANIFEST} "
    f"--evidence-cohort {DEFAULT_EVIDENCE_COHORT} "
    f"--out {DEFAULT_OUT}"
)
_MISSING = object()


REQUIRED_DRIFT_WATCH_PATHS = [
    {
        "field_path": "batch_manifest.release_authority_status",
        "check_description": "Release authority status snapshot at closeout",
    },
    {
        "field_path": "batch_manifest.sealed_release_status",
        "check_description": "Distribution and artifact sealing status snapshot at closeout",
    },
    {
        "field_path": "batch_manifest.distribution_package.status",
        "check_description": "Distribution package materialization status at closeout",
    },
    {
        "field_path": "cohort.clean_lane_contract.status",
        "check_description": "Clean lane contract status at closeout",
    },
    {
        "field_path": "cohort.summary.accepted_risk_family_count",
        "check_description": "Accepted risk family count at closeout",
    },
]


def _file_fingerprint(path: Path) -> str:
    """Compute SHA256 hash of a file for change detection."""
    if not path.exists():
        return ""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _json_field_digest(data: dict[str, Any], *keys: str) -> str:
    """Compute SHA256 hash of nested JSON field for change detection."""
    try:
        value = data
        for key in keys:
            if not isinstance(value, dict):
                return ""
            value = value[key]
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
    except (KeyError, TypeError):
        return ""


def _resolve_dotted_path(data: Any, dotted_path: str) -> Any:
    """Resolve a dotted path in nested JSON-like data."""
    value = data
    for part in dotted_path.split("."):
        if isinstance(value, dict):
            if part not in value:
                return _MISSING
            value = value[part]
            continue
        if isinstance(value, list) and part.isdigit():
            index = int(part)
            if index >= len(value):
                return _MISSING
            value = value[index]
            continue
        return _MISSING
    return value


def _component_count(data: dict[str, Any] | None) -> int:
    """Extract component count from release evidence documents."""
    if not data or not isinstance(data, dict):
        return 0
    summary = data.get("summary")
    if isinstance(summary, dict):
        artifact_count = summary.get("artifact_count")
        if isinstance(artifact_count, int) and not isinstance(artifact_count, bool):
            return artifact_count
    if "artifacts" in data and isinstance(data["artifacts"], list):
        return len(data["artifacts"])
    if "components" in data and isinstance(data["components"], list):
        return len(data["components"])
    return 0


def _artifact_digest_watch(vault: Path, batch_data: dict[str, Any] | None) -> dict[str, Any]:
    if not batch_data or not isinstance(batch_data, dict):
        return {
            "status": "unavailable",
            "authority_schema_status": "missing",
            "manifest_schema_version": 0,
            "artifact_count": 0,
            "match_count": 0,
            "mismatch_count": 0,
            "missing_artifact_count": 0,
            "artifacts": [],
            "summary": "batch artifact digest watch unavailable because batch manifest is missing or unreadable",
        }
    declared_schema_version = batch_data.get("schema_version")
    schema_version = declared_schema_version if type(declared_schema_version) is int else 0
    if schema_version != 2:
        return {
            "status": "mismatch",
            "authority_schema_status": "unsupported",
            "manifest_schema_version": schema_version,
            "artifact_count": 0,
            "match_count": 0,
            "mismatch_count": 0,
            "missing_artifact_count": 0,
            "artifacts": [],
            "summary": (
                "batch artifact digest watch rejected non-current authority schema; "
                f"expected exact integer=2; actual={declared_schema_version!r}"
            ),
        }

    raw_artifacts = batch_data.get("artifacts")
    artifacts = raw_artifacts if isinstance(raw_artifacts, list) else []
    watched: list[dict[str, Any]] = []
    match_count = 0
    mismatch_count = 0
    missing_count = 0

    for index, item in enumerate(artifacts):
        if not isinstance(item, dict):
            watched.append(
                {
                    "path": f"<invalid-artifact-{index}>",
                    "binding_mode": "missing",
                    "expected_binding_digest": "missing",
                    "actual_binding_digest": "not_checked",
                    "declared_raw_digest": "missing",
                    "actual_raw_digest": "not_checked",
                    "status": "mismatch",
                    "reason": "binding_metadata_invalid",
                }
            )
            mismatch_count += 1
            continue
        rel_path = str(item.get("path", "")).strip()
        display_rel_path = rel_path or f"<missing-path-{index}>"
        binding_mode = str(item.get("binding_mode", "")).strip()
        expected_binding_digest = str(item.get("binding_digest", "")).strip() or "missing"
        declared_raw_digest = str(item.get("raw_digest", "")).strip() or "missing"
        artifact_path = vault / rel_path if rel_path else None
        actual_raw_digest = (
            _file_fingerprint(artifact_path)
            if artifact_path is not None and artifact_path.is_file()
            else "missing" if artifact_path is not None else "not_checked"
        )
        binding_metadata_valid = bool(
            rel_path
            and is_sha256_digest(expected_binding_digest)
            and binding_mode in BINDING_MODES
        )
        actual_binding_digest = "not_checked"
        if binding_metadata_valid and artifact_path is not None:
            actual_binding_digest = binding_file_digest(
                artifact_path,
                binding_mode=binding_mode,
            )[1]
        digest_status = (
            "match"
            if binding_metadata_valid
            and expected_binding_digest == actual_binding_digest
            else "mismatch"
        )
        if actual_raw_digest == "missing":
            missing_count += 1
        if digest_status == "match":
            match_count += 1
        else:
            mismatch_count += 1
        watched.append(
            {
                "path": display_rel_path,
                "binding_mode": binding_mode or "missing",
                "expected_binding_digest": expected_binding_digest,
                "actual_binding_digest": actual_binding_digest,
                "declared_raw_digest": declared_raw_digest,
                "actual_raw_digest": actual_raw_digest,
                "status": digest_status,
                "reason": (
                    "match"
                    if digest_status == "match"
                    else "binding_digest_mismatch"
                    if binding_metadata_valid
                    else "binding_metadata_invalid"
                ),
            }
        )

    status = "match" if not mismatch_count else "mismatch"
    return {
        "status": status,
        "authority_schema_status": "current",
        "manifest_schema_version": schema_version,
        "artifact_count": len(watched),
        "match_count": match_count,
        "mismatch_count": mismatch_count,
        "missing_artifact_count": missing_count,
        "artifacts": watched,
        "summary": (
            f"batch artifact digest watch status={status}; artifact_count={len(watched)}; "
            f"mismatch_count={mismatch_count}; missing_artifact_count={missing_count}"
        ),
    }


def _extract_clean_lane_status(cohort_data: dict[str, Any] | None) -> str:
    """Extract clean lane contract status from cohort evidence."""
    if not cohort_data or not isinstance(cohort_data, dict):
        return "unknown"
    try:
        return str(cohort_data.get("clean_lane_contract", {}).get("status", "unknown"))
    except (KeyError, AttributeError):
        return "unknown"


def _extract_release_readiness(batch_data: dict[str, Any] | None) -> dict[str, Any]:
    """Extract release readiness summary from batch manifest."""
    if not batch_data or not isinstance(batch_data, dict):
        return {}
    try:
        return batch_data.get("summary", {})
    except (KeyError, AttributeError):
        return {}


def _load_optional(vault: Path, rel_path: str) -> tuple[dict[str, Any], str]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(vault / rel_path)
    return payload, str(diagnostics.get("status", "unknown")).strip() or "unknown"


def build_report(
    vault: Path,
    batch_manifest_path: str,
    evidence_cohort_path: str,
    context: RuntimeContext | None = None,
    *,
    policy_path: str | None = None,
    source_command: str = SOURCE_COMMAND,
) -> dict[str, Any]:
    """Build closeout self-check artifact.

    Args:
        vault: Project vault root
        batch_manifest_path: Relative path to batch manifest (e.g., ops/reports/...)
        evidence_cohort_path: Relative path to cohort evidence (e.g., ops/reports/...)
        context: Runtime context (clock, timezone)

    Returns:
        Self-check artifact dict
    """
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()

    batch_path = vault / batch_manifest_path
    cohort_path = vault / evidence_cohort_path

    batch_data, batch_load_status = _load_optional(vault, batch_manifest_path)
    cohort_data, cohort_load_status = _load_optional(vault, evidence_cohort_path)

    watch_sources = {
        "batch_manifest": batch_data,
        "cohort": cohort_data,
    }
    artifact_digest_watch = _artifact_digest_watch(vault, batch_data)
    missing_required_watch_paths: list[str] = []
    drift_watch_list: list[dict[str, Any]] = []
    for spec in REQUIRED_DRIFT_WATCH_PATHS:
        field_path = spec["field_path"]
        snapshot_value = _resolve_dotted_path(watch_sources, field_path)
        if snapshot_value is _MISSING or snapshot_value is None:
            missing_required_watch_paths.append(field_path)
            snapshot_value = None
        drift_watch_list.append(
            {
                "field_path": field_path,
                "snapshot_value": snapshot_value,
                "check_description": spec["check_description"],
            }
        )

    digest_mismatch_count = int(artifact_digest_watch["mismatch_count"])
    result = "pass"
    summary = "Closeout self-check snapshot captured"
    if (
        missing_required_watch_paths
        or digest_mismatch_count
        or artifact_digest_watch["status"] != "match"
    ):
        result = "fail"
        summary_parts: list[str] = []
        if missing_required_watch_paths:
            summary_parts.append("Required drift watch paths missing: " + ", ".join(missing_required_watch_paths))
        if digest_mismatch_count or artifact_digest_watch["status"] != "match":
            summary_parts.append(artifact_digest_watch["summary"])
        summary = "; ".join(summary_parts)

    status = {
        "result": result,
        "summary": summary,
        "missing_required_watch_paths": missing_required_watch_paths,
    }

    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="release_evidence_closeout_self_check",
            producer=PRODUCER,
            source_command=source_command,
            resolved_policy_path=resolved_policy_path,
            schema_path=RELEASE_EVIDENCE_CLOSEOUT_SELF_CHECK_SCHEMA_PATH,
            source_paths=["ops/scripts/release/release_evidence_closeout_self_check.py"],
            file_inputs={
                "batch_manifest": batch_manifest_path,
                "evidence_cohort": evidence_cohort_path,
            },
            text_inputs={
                "batch_manifest_load_status": batch_load_status,
                "evidence_cohort_load_status": cohort_load_status,
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": status,
        "closeout_inputs": {
            "batch_manifest_path": batch_manifest_path,
            "evidence_cohort_path": evidence_cohort_path,
            "batch_manifest_fingerprint": _file_fingerprint(batch_path),
            "evidence_cohort_fingerprint": _file_fingerprint(cohort_path),
        },
        "closeout_snapshot": {
            "batch_manifest_component_count": _component_count(batch_data),
            "cohort_component_count": _component_count(cohort_data),
            "batch_manifest_input_digest": _json_field_digest(batch_data, "input_fingerprints") if batch_data else "",
            "cohort_input_digest": _json_field_digest(cohort_data, "input_fingerprints") if cohort_data else "",
            "clean_lane_contract_status": _extract_clean_lane_status(cohort_data),
            "release_readiness_summary": _extract_release_readiness(batch_data),
        },
        "batch_artifact_digest_watch": artifact_digest_watch,
        "drift_watch_list": drift_watch_list,
    }



def write_report(vault: Path, report: dict[str, Any], out_path: str | None) -> Path:
    """Write report to vault with schema validation."""
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=RELEASE_EVIDENCE_CLOSEOUT_SELF_CHECK_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release evidence closeout self-check artifact write failed",
        )
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Build release evidence closeout self-check artifact")
    parser.add_argument("--vault", default=".", help="Vault root path")
    parser.add_argument("--policy-path")
    parser.add_argument(
        "--batch-manifest",
        default=DEFAULT_BATCH_MANIFEST,
        help="Relative path to batch manifest",
    )
    parser.add_argument(
        "--evidence-cohort",
        default=DEFAULT_EVIDENCE_COHORT,
        help="Relative path to evidence cohort",
    )
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output path")

    args = parser.parse_args(argv)

    vault = Path(args.vault).resolve()

    try:
        report = build_report(
            vault,
            args.batch_manifest,
            args.evidence_cohort,
            policy_path=args.policy_path,
        )
        out_path = write_report(vault, report, args.out)
        print(display_path(vault, out_path))
        return 0
    except Exception as e:  # broad-exception: cli_boundary
        print(f"Error building self-check artifact: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
