from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    resolve_schema_backed_report_output_path,
    write_schema_backed_report,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.path_portability_runtime import (
    infozip_c_locale_escape_path,
    max_component_metric,
    python_unicode_escape_byte_len,
    utf8_byte_len,
)
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.release.external_report_inventory_runtime import (
    active_reference_report_paths,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import (
    EXTERNAL_REPORT_REFERENCE_MANIFEST_SCHEMA_PATH,
)

PRODUCER = "ops.scripts.external_report_reference_manifest"
DEFAULT_OUT = "external-reports/report-reference-manifest.json"
SOURCE_COMMAND = (
    "python -m ops.scripts.external_report_reference_manifest --vault . "
    "--out external-reports/report-reference-manifest.json"
)
REFERENCE_EXTENSIONS = {".md", ".pdf", ".docx"}
MODES = {"advisory", "strict_review_release"}


@dataclass(frozen=True)
class ZipIdentityInput:
    name: str = ""
    sha256: str = ""
    entry_count: int | None = None
    source: str | None = None


@dataclass(frozen=True)
class ExternalReportReferenceManifestRequest:
    out_path: str = DEFAULT_OUT
    basis_zip: ZipIdentityInput = field(default_factory=ZipIdentityInput)
    current_distribution_zip: ZipIdentityInput = field(default_factory=ZipIdentityInput)
    mode: str = "advisory"
    source_command: str = SOURCE_COMMAND


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _line_count(path: Path) -> int | None:
    if path.suffix.lower() != ".md":
        return None
    return len(path.read_text(encoding="utf-8").splitlines())


def _evidence_role(path: Path) -> str:
    name = path.name.lower()
    if "review_test_structure_improvement" in name:
        return "test_structure_review"
    if "crosscheck" in name or "integrated" in name or "consolidated" in name:
        return "release_review"
    return "active_external_report"


def _path_reference(vault: Path, path: Path) -> dict[str, Any]:
    storage_path = report_path(vault, path)
    display_name = path.name
    normalization_form = "NFC" if unicodedata.is_normalized("NFC", display_name) else "non_nfc"
    escaped_path = infozip_c_locale_escape_path(storage_path)
    aliases = [storage_path]
    if escaped_path != storage_path:
        aliases.append(escaped_path)
    return {
        "path": storage_path,
        "storage_path": storage_path,
        "display_name": display_name,
        "path_aliases": aliases,
        "sha256": _sha256_file(path),
        "content_sha256": _sha256_file(path),
        "byte_count": path.stat().st_size,
        "line_count": _line_count(path),
        "evidence_role": _evidence_role(path),
        "normalization_form": normalization_form,
        "escape_diagnostics": {
            "display_path": storage_path,
            "archive_path": storage_path,
            "escape_expanded_diagnostic_path": escaped_path,
            "utf8_path_bytes": utf8_byte_len(storage_path),
            "python_unicode_escape_filename_bytes": max(
                (python_unicode_escape_byte_len(component) for component in storage_path.split("/")),
                default=0,
            ),
            "posix_escape_expanded_filename_bytes": max_component_metric(
                storage_path,
                "infozip_c_locale_escape_component_bytes",
            ),
            "infozip_c_locale_escape_filename_bytes": max_component_metric(
                storage_path,
                "infozip_c_locale_escape_component_bytes",
            ),
        },
    }


def _reference_paths(vault: Path, out_path: str) -> list[Path]:
    resolved_out = resolve_schema_backed_report_output_path(
        vault,
        out_path,
        default_relative_path=DEFAULT_OUT,
    )
    return [
        path
        for path in active_reference_report_paths(vault)
        if path.resolve() != resolved_out.resolve()
    ]


def _archive_reference_count(vault: Path) -> int:
    archive = vault / "external-reports" / "archive"
    if not archive.is_dir():
        return 0
    return sum(1 for path in archive.iterdir() if path.is_file() and path.suffix.lower() in REFERENCE_EXTENSIONS)


def _prior_manifest_reference_paths(vault: Path, out_path: str) -> tuple[list[str] | None, str]:
    resolved_out = resolve_schema_backed_report_output_path(
        vault,
        out_path,
        default_relative_path=DEFAULT_OUT,
    )
    if not resolved_out.exists():
        return None, "no_prior_manifest"
    try:
        payload = json.loads(resolved_out.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "unreadable_prior_manifest"
    references = payload.get("references")
    if not isinstance(references, list):
        return None, "unreadable_prior_manifest"
    paths = []
    for item in references:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            return None, "unreadable_prior_manifest"
        paths.append(item["path"])
    return sorted(paths), "loaded"


def _active_reference_set(previous_paths: list[str] | None, current_paths: list[str], prior_status: str) -> dict[str, Any]:
    current_sorted = sorted(current_paths)
    if previous_paths is None:
        return {
            "status": prior_status,
            "previous_report_count": None,
            "current_report_count": len(current_sorted),
            "added_paths": current_sorted if prior_status == "no_prior_manifest" else [],
            "removed_paths": [],
        }
    previous_sorted = sorted(previous_paths)
    added_paths = sorted(set(current_sorted) - set(previous_sorted))
    removed_paths = sorted(set(previous_sorted) - set(current_sorted))
    status = "current" if not added_paths and not removed_paths else "drift"
    return {
        "status": status,
        "previous_report_count": len(previous_sorted),
        "current_report_count": len(current_sorted),
        "added_paths": added_paths,
        "removed_paths": removed_paths,
    }


def _zip_entry_count(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        return len(archive.infolist())


def _computed_zip_identity(path: Path) -> dict[str, Any]:
    return _zip_identity(
        path.name,
        _sha256_file(path),
        _zip_entry_count(path),
        source="computed",
    )


def _zip_identity(
    name: str,
    sha256: str,
    entry_count: int | None,
    *,
    source: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "sha256": sha256,
        "entry_count": entry_count,
        "source": source or ("reported" if sha256 else "unspecified"),
    }


def _zip_identity_from_input(identity: ZipIdentityInput) -> dict[str, Any]:
    return _zip_identity(
        identity.name,
        identity.sha256,
        identity.entry_count,
        source=identity.source,
    )


def _distribution_provenance(
    *,
    mode: str,
    basis_zip: dict[str, Any],
    current_distribution_zip: dict[str, Any],
) -> dict[str, Any]:
    basis_known = bool(basis_zip["sha256"]) and basis_zip["entry_count"] is not None
    current_known = bool(current_distribution_zip["sha256"]) and current_distribution_zip["entry_count"] is not None
    name_mismatch = bool(
        basis_zip["name"]
        and current_distribution_zip["name"]
        and basis_zip["name"] != current_distribution_zip["name"]
    )
    if not current_known:
        status = "current_distribution_missing"
        basis_matches_current: bool | None = None
        mismatch_fields: list[str] = []
    elif not basis_known:
        status = "basis_zip_missing"
        basis_matches_current = None
        mismatch_fields = []
    else:
        mismatch_fields = [
            field
            for field in ("sha256", "entry_count")
            if basis_zip[field] != current_distribution_zip[field]
        ]
        basis_matches_current = not mismatch_fields
        status = "basis_current_match" if basis_matches_current else "basis_current_mismatch"
    return {
        "mode": mode,
        "status": status,
        "basis_zip_matches_current_distribution": basis_matches_current,
        "identity_mismatch_fields": mismatch_fields,
        "name_mismatch": name_mismatch,
    }


def build_report(
    vault: Path,
    *,
    request: ExternalReportReferenceManifestRequest | None = None,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    request = request or ExternalReportReferenceManifestRequest()
    mode = request.mode
    if mode not in MODES:
        raise ValueError(f"unsupported external report reference manifest mode: {mode}")
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    reference_paths = _reference_paths(vault, request.out_path)
    references: list[dict[str, Any]] = [_path_reference(vault, path) for path in reference_paths]
    rel_paths = [str(item["path"]) for item in references]
    previous_reference_paths, prior_manifest_status = _prior_manifest_reference_paths(
        vault,
        request.out_path,
    )
    active_reference_set = _active_reference_set(previous_reference_paths, rel_paths, prior_manifest_status)
    archive_excluded_count = _archive_reference_count(vault)
    review_basis_zip = _zip_identity_from_input(request.basis_zip)
    current_distribution_zip = _zip_identity_from_input(request.current_distribution_zip)
    distribution_provenance = _distribution_provenance(
        mode=mode,
        basis_zip=review_basis_zip,
        current_distribution_zip=current_distribution_zip,
    )

    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="external_report_reference_manifest",
            producer=PRODUCER,
            source_command=request.source_command,
            resolved_policy_path=resolved_policy_path,
            schema_path=EXTERNAL_REPORT_REFERENCE_MANIFEST_SCHEMA_PATH,
            source_paths=["ops/scripts/external_report_reference_manifest.py"],
            path_group_inputs={"external_reports": rel_paths},
            text_inputs={
                "active_reference_set_status": active_reference_set["status"],
                "basis_zip_name": request.basis_zip.name,
                "basis_zip_sha256": request.basis_zip.sha256,
                "basis_zip_entry_count": (
                    ""
                    if request.basis_zip.entry_count is None
                    else str(request.basis_zip.entry_count)
                ),
                "current_distribution_zip_name": request.current_distribution_zip.name,
                "current_distribution_zip_sha256": request.current_distribution_zip.sha256,
                "current_distribution_zip_entry_count": (
                    ""
                    if request.current_distribution_zip.entry_count is None
                    else str(request.current_distribution_zip.entry_count)
                ),
                "mode": mode,
                "zip_provenance_status": distribution_provenance["status"],
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "review_basis_zip": review_basis_zip,
        "current_distribution_zip": current_distribution_zip,
        "basis_zip": review_basis_zip,
        "distribution_provenance": distribution_provenance,
        "active_reference_set": active_reference_set,
        "archive_exclusion_policy": (
            "external-reports/archive is excluded from active reference provenance; "
            "root external-reports files are the operator-facing evidence set"
        ),
        "excluded_file_count": archive_excluded_count,
        "summary": {
            "report_count": len(references),
            "basis_zip_known": bool(request.basis_zip.sha256),
            "review_basis_zip_known": bool(request.basis_zip.sha256),
            "current_distribution_zip_known": bool(
                request.current_distribution_zip.sha256
            ),
            "basis_zip_matches_current_distribution": (
                distribution_provenance["basis_zip_matches_current_distribution"]
            ),
            "zip_provenance_status": distribution_provenance["status"],
            "active_reference_set_status": active_reference_set["status"],
            "archive_included": False,
            "excluded_file_count": archive_excluded_count,
        },
        "references": references,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=EXTERNAL_REPORT_REFERENCE_MANIFEST_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="external report reference manifest schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build external report reference manifest")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--basis-zip-name", default="")
    parser.add_argument("--basis-zip-sha256", default="")
    parser.add_argument("--basis-zip-entry-count", type=int)
    parser.add_argument(
        "--basis-zip-path",
        default="",
        help="Compute active review/release basis ZIP name, SHA-256, and entry count from this ZIP file.",
    )
    parser.add_argument("--current-distribution-zip-name", default="")
    parser.add_argument("--current-distribution-zip-sha256", default="")
    parser.add_argument("--current-distribution-zip-entry-count", type=int)
    parser.add_argument(
        "--mode",
        choices=sorted(MODES),
        default="advisory",
        help="Use strict_review_release to require a computed current distribution ZIP identity.",
    )
    parser.add_argument(
        "--strict-review-release",
        action="store_true",
        help="Alias for --mode strict_review_release.",
    )
    parser.add_argument(
        "--current-distribution-zip-path",
        default="",
        help="Compute current distribution ZIP name, SHA-256, and entry count from this ZIP file.",
    )
    args = parser.parse_args(argv)
    if args.strict_review_release:
        args.mode = "strict_review_release"
    if args.mode == "strict_review_release" and not args.current_distribution_zip_path:
        parser.error("--current-distribution-zip-path is required in strict_review_release mode")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    basis_zip_name = args.basis_zip_name
    basis_zip_sha256 = args.basis_zip_sha256
    basis_zip_entry_count = args.basis_zip_entry_count
    basis_zip_source: str | None = None
    if args.basis_zip_path:
        basis_zip_path = Path(args.basis_zip_path)
        if not basis_zip_path.is_absolute():
            basis_zip_path = (vault / basis_zip_path).resolve()
        basis_zip = _computed_zip_identity(basis_zip_path)
        basis_zip_name = str(basis_zip["name"])
        basis_zip_sha256 = str(basis_zip["sha256"])
        basis_zip_entry_count = int(basis_zip["entry_count"])
        basis_zip_source = "computed"

    current_distribution_zip_name = args.current_distribution_zip_name
    current_distribution_zip_sha256 = args.current_distribution_zip_sha256
    current_distribution_zip_entry_count = args.current_distribution_zip_entry_count
    current_distribution_zip_source: str | None = None
    if args.current_distribution_zip_path:
        zip_path = Path(args.current_distribution_zip_path)
        if not zip_path.is_absolute():
            zip_path = (vault / zip_path).resolve()
        current_distribution_zip = _computed_zip_identity(zip_path)
        current_distribution_zip_name = str(current_distribution_zip["name"])
        current_distribution_zip_sha256 = str(current_distribution_zip["sha256"])
        current_distribution_zip_entry_count = int(current_distribution_zip["entry_count"])
        current_distribution_zip_source = "computed"
    report = build_report(
        vault,
        request=ExternalReportReferenceManifestRequest(
            out_path=args.out,
            basis_zip=ZipIdentityInput(
                name=basis_zip_name,
                sha256=basis_zip_sha256,
                entry_count=basis_zip_entry_count,
                source=basis_zip_source,
            ),
            current_distribution_zip=ZipIdentityInput(
                name=current_distribution_zip_name,
                sha256=current_distribution_zip_sha256,
                entry_count=current_distribution_zip_entry_count,
                source=current_distribution_zip_source,
            ),
            mode=args.mode,
        ),
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
