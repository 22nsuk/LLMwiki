from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from ops.scripts.artifact_io_runtime import read_json_object, resolve_repo_artifact_path
from ops.scripts.output_runtime import display_path

DEFAULT_BATCH_MANIFEST = "ops/reports/release-closeout-batch-manifest.json"
DEFAULT_OUT = "build/release/release-audit-pack.zip"
PACK_MANIFEST_NAME = "release-audit-pack-manifest.json"
DETERMINISTIC_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_repo_rel_path(value: str) -> str:
    rel_path = value.replace("\\", "/").strip()
    path = Path(rel_path)
    if path.is_absolute() or ".." in path.parts or not rel_path:
        raise ValueError(f"unsafe audit pack path: {value!r}")
    return rel_path


def _write_bytes_to_archive(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(name, DETERMINISTIC_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, payload)


def _write_file_to_archive(archive: zipfile.ZipFile, source: Path, name: str) -> None:
    _write_bytes_to_archive(archive, name, source.read_bytes())


def _artifact_entries(batch_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in batch_manifest.get("artifacts", []):
        if not isinstance(item, dict):
            continue
        rel_path = _safe_repo_rel_path(str(item.get("path", "")))
        entries.append(
            {
                "path": rel_path,
                "expected_sha256": str(item.get("digest", "")),
                "required": bool(item.get("required", False)),
                "role": str(item.get("role", "")),
                "artifact_kind": str(item.get("artifact_kind", "")),
            }
        )
    return entries


def _optional_payload_entries(batch_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    audit_materialization = batch_manifest.get("audit_materialization")
    if not isinstance(audit_materialization, dict):
        return []
    entries: list[dict[str, Any]] = []
    for item in audit_materialization.get("optional_payloads", []):
        if not isinstance(item, dict):
            continue
        rel_path = _safe_repo_rel_path(str(item.get("path", "")))
        entries.append(
            {
                "path": rel_path,
                "expected_sha256": str(item.get("sha256", "")),
                "required": False,
                "role": f"optional_{str(item.get('kind', 'payload')).strip() or 'payload'}",
                "artifact_kind": str(item.get("kind", "")),
                "status": str(item.get("status", "")),
            }
        )
    return entries


def _source_zip_identity(batch_manifest: dict[str, Any]) -> dict[str, str]:
    distribution = batch_manifest.get("distribution_package")
    if not isinstance(distribution, dict):
        distribution = {}
    external_bound = batch_manifest.get("external_source_zip_bound")
    if not isinstance(external_bound, dict):
        external_bound = {}
    return {
        "status": str(distribution.get("status", "")),
        "path": str(distribution.get("path", "")),
        "sha256": str(distribution.get("sha256", "")),
        "external_source_zip_bound_status": str(external_bound.get("status", "")),
        "external_source_zip_bound_sha256": str(external_bound.get("sha256", "")),
    }


def _write_pack_entry(
    archive: zipfile.ZipFile,
    *,
    vault: Path,
    entry: dict[str, Any],
    missing_paths: list[str],
    digest_mismatches: list[dict[str, str]],
    packed_entries: list[dict[str, str]],
) -> None:
    rel_path = str(entry["path"])
    source = vault / rel_path
    if not source.is_file():
        missing_paths.append(rel_path)
        return
    actual = _sha256_file(source)
    expected = str(entry["expected_sha256"])
    if expected and actual != expected:
        digest_mismatches.append(
            {
                "path": rel_path,
                "expected_sha256": expected,
                "actual_sha256": actual,
            }
        )
    _write_file_to_archive(archive, source, rel_path)
    packed_entries.append(
        {
            "path": rel_path,
            "sha256": actual,
            "role": str(entry["role"]),
        }
    )


def _pack_manifest(
    batch_manifest: dict[str, Any],
    *,
    batch_manifest_rel: str,
    include_optional_payloads: bool,
    optional_entries: list[dict[str, Any]],
    missing_optional: list[str],
    packed_entries: list[dict[str, str]],
) -> dict[str, Any]:
    audit_materialization = batch_manifest.get("audit_materialization")
    optional_payload_policy = (
        audit_materialization.get("optional_payload_policy", {})
        if isinstance(audit_materialization, dict)
        else {}
    )
    return {
        "source_of_truth": batch_manifest_rel,
        "batch_id": str(batch_manifest.get("batch_id", "")),
        "source_zip": _source_zip_identity(batch_manifest),
        "evidence_set_digest": str(
            batch_manifest.get("audit_materialization", {}).get(
                "evidence_set_digest", ""
            )
        ),
        "include_optional_payloads": include_optional_payloads,
        "optional_payload_policy": optional_payload_policy,
        "optional_payload_count": len(optional_entries),
        "missing_optional_payloads": missing_optional,
        "packed_entry_count": len(packed_entries),
        "packed_entries": packed_entries,
    }


def build_audit_pack(
    vault: Path,
    *,
    batch_manifest_path: str = DEFAULT_BATCH_MANIFEST,
    out_path: str = DEFAULT_OUT,
    include_optional_payloads: bool = False,
) -> dict[str, Any]:
    resolved_batch_manifest = resolve_repo_artifact_path(
        vault,
        batch_manifest_path,
        default_relative_path=DEFAULT_BATCH_MANIFEST,
    )
    batch_manifest = read_json_object(resolved_batch_manifest)
    entries = _artifact_entries(batch_manifest)
    optional_entries = _optional_payload_entries(batch_manifest) if include_optional_payloads else []
    missing_required: list[str] = []
    missing_optional: list[str] = []
    digest_mismatches: list[dict[str, str]] = []
    packed_entries: list[dict[str, str]] = []

    resolved_out = resolve_repo_artifact_path(vault, out_path, default_relative_path=DEFAULT_OUT)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    batch_manifest_rel = display_path(vault, resolved_batch_manifest)

    with zipfile.ZipFile(resolved_out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _write_file_to_archive(archive, resolved_batch_manifest, batch_manifest_rel)
        packed_entries.append(
            {
                "path": batch_manifest_rel,
                "sha256": _sha256_file(resolved_batch_manifest),
                "role": "canonical_closure_manifest",
            }
        )
        for entry in entries:
            missing_non_required: list[str] = []
            missing_paths = missing_required if entry["required"] else missing_non_required
            _write_pack_entry(
                archive,
                vault=vault,
                entry=entry,
                missing_paths=missing_paths,
                digest_mismatches=digest_mismatches,
                packed_entries=packed_entries,
            )

        for entry in optional_entries:
            _write_pack_entry(
                archive,
                vault=vault,
                entry=entry,
                missing_paths=missing_optional,
                digest_mismatches=digest_mismatches,
                packed_entries=packed_entries,
            )

        _write_bytes_to_archive(
            archive,
            PACK_MANIFEST_NAME,
            (
                json.dumps(
                    _pack_manifest(
                        batch_manifest,
                        batch_manifest_rel=batch_manifest_rel,
                        include_optional_payloads=include_optional_payloads,
                        optional_entries=optional_entries,
                        missing_optional=missing_optional,
                        packed_entries=packed_entries,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8"),
        )

    status = "pass" if not missing_required and not digest_mismatches else "fail"
    return {
        "status": status,
        "path": display_path(vault, resolved_out),
        "sha256": _sha256_file(resolved_out),
        "source_of_truth": batch_manifest_rel,
        "packed_entry_count": len(packed_entries) + 1,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "digest_mismatches": digest_mismatches,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize a portable audit pack from the release closeout batch manifest.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--batch-manifest", default=DEFAULT_BATCH_MANIFEST)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument(
        "--include-optional-payloads",
        action="store_true",
        help="Include optional JUnit/log payload files listed by audit_materialization.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    result = build_audit_pack(
        vault,
        batch_manifest_path=args.batch_manifest,
        out_path=args.out,
        include_optional_payloads=args.include_optional_payloads,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
