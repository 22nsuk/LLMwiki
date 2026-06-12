#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import zipfile
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        describe_output_file,
        write_schema_backed_report,
    )
    from ops.scripts.core.output_runtime import display_path, resolve_output_path
    from ops.scripts.core.policy_runtime import (
        load_policy,
        zip_normalization_from_policy,
    )
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_constants_runtime import (
        REVIEW_ARCHIVE_REPORT_SCHEMA_PATH,
    )
    from ops.scripts.public.export_public_repo import iter_public_files
    from ops.scripts.public.public_surface_policy import (
        PUBLIC_EXCLUDED_FILES,
        PUBLIC_EXCLUDED_PREFIXES,
    )
else:
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        describe_output_file,
        write_schema_backed_report,
    )
    from ops.scripts.core.output_runtime import display_path, resolve_output_path
    from ops.scripts.core.policy_runtime import (
        load_policy,
        zip_normalization_from_policy,
    )
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_constants_runtime import (
        REVIEW_ARCHIVE_REPORT_SCHEMA_PATH,
    )
    from ops.scripts.public.export_public_repo import iter_public_files
    from ops.scripts.public.public_surface_policy import (
        PUBLIC_EXCLUDED_FILES,
        PUBLIC_EXCLUDED_PREFIXES,
    )


DEFAULT_REVIEW_ARCHIVE_OUT = "build/review/llm-wiki-vnext-review.zip"
DEFAULT_REVIEW_ARCHIVE_REPORT = "ops/reports/review-archive-report.json"
PRODUCER = "ops.scripts.review_archive"
ADVISORY_PROFILE = "default"
CLEAN_PROFILE = "clean"
DEFAULT_PROFILE = CLEAN_PROFILE
PROFILES = {ADVISORY_PROFILE, CLEAN_PROFILE}
DEFAULT_SOURCE_COMMAND = (
    "python -m ops.scripts.release.review_archive --vault . "
    "--archive-out build/review/llm-wiki-vnext-review.zip --out ops/reports/review-archive-report.json --profile default"
)
CLEAN_SOURCE_COMMAND = (
    "python -m ops.scripts.release.review_archive --vault . "
    "--archive-out build/review/llm-wiki-vnext-review.zip --out ops/reports/review-archive-report.json --profile clean"
)
CLEAN_PROFILE_RULES = (
    "tmp/**/*.candidate.json",
    "public-surface __pycache__ directories",
    "public-surface *.pyc files",
)


def _source_command(profile: str) -> str:
    return CLEAN_SOURCE_COMMAND if profile == CLEAN_PROFILE else DEFAULT_SOURCE_COMMAND


def _normalized_zip_info(
    arcname: str,
    *,
    timestamp_utc: dt.datetime,
    file_mode: int,
) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(
        filename=arcname,
        date_time=timestamp_utc.astimezone(dt.UTC).timetuple()[:6],
    )
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (file_mode & 0xFFFF) << 16
    return info


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _public_review_manifest(vault: Path) -> dict:
    files = []
    for rel_path in iter_public_files(vault):
        file_path = vault / rel_path
        files.append(
            {
                "path": rel_path,
                "sha256": _sha256_file(file_path),
                "size_bytes": file_path.stat().st_size,
            }
        )
    return {"files": files}


def _manifest_digest(manifest: dict) -> str:
    normalized = {
        "files": sorted(
            (
                {
                    "path": str(item.get("path", "")),
                    "sha256": str(item.get("sha256", "")),
                    "size_bytes": int(item.get("size_bytes", 0) or 0),
                }
                for item in manifest.get("files", [])
                if isinstance(item, dict)
            ),
            key=lambda item: str(item["path"]),
        )
    }
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _archive_manifest(archive_path: Path, *, root_prefix: str) -> dict:
    files = []
    prefix = f"{root_prefix}/"
    with zipfile.ZipFile(archive_path) as archive:
        for name in sorted(archive.namelist()):
            if name.endswith("/"):
                continue
            rel_path = name[len(prefix):] if name.startswith(prefix) else name
            content = archive.read(name)
            files.append(
                {
                    "path": rel_path,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size_bytes": len(content),
                }
            )
    return {"files": files}


def _zip_datetime_utc(value: tuple[int, int, int, int, int, int]) -> str:
    timestamp = dt.datetime(*value, tzinfo=dt.UTC)
    return timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _archive_timestamp_normalization(
    archive_path: Path,
    *,
    expected_timestamp_utc: dt.datetime,
) -> dict:
    expected = expected_timestamp_utc.astimezone(dt.UTC).replace(microsecond=0)
    expected_tuple = expected.timetuple()[:6]
    expected_text = expected.strftime("%Y-%m-%dT%H:%M:%SZ")
    member_timestamps: dict[str, str] = {}
    mismatches: list[str] = []
    with zipfile.ZipFile(archive_path) as archive:
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            if info.is_dir():
                continue
            observed = _zip_datetime_utc(info.date_time)
            member_timestamps[info.filename] = observed
            if info.date_time != expected_tuple:
                mismatches.append(info.filename)
    unique_timestamps = sorted(set(member_timestamps.values()))
    return {
        "status": "pass" if not mismatches else "fail",
        "timestamp_semantics": "normalized_archive_timestamp",
        "expected_timestamp_utc": expected_text,
        "observed_timestamp_count": len(unique_timestamps),
        "observed_min_timestamp_utc": unique_timestamps[0] if unique_timestamps else "",
        "observed_max_timestamp_utc": unique_timestamps[-1] if unique_timestamps else "",
        "mismatch_count": len(mismatches),
        "mismatch_paths": mismatches,
    }


def _public_surface_roots(vault: Path) -> list[Path]:
    roots = []
    for rel_prefix in ("ops", "tests", "tools", ".codex", ".github"):
        root = vault / rel_prefix
        if root.exists():
            roots.append(root)
    return roots


def snapshot_hygiene(vault: Path, *, profile: str) -> dict:
    if profile not in PROFILES:
        raise ValueError(f"unsupported review archive profile: {profile}")

    forbidden_paths: list[str] = []
    if (vault / "tmp").is_dir():
        forbidden_paths.extend(
            path.relative_to(vault).as_posix()
            for path in sorted((vault / "tmp").rglob("*.candidate.json"))
            if path.is_file()
        )
    for root in _public_surface_roots(vault):
        forbidden_paths.extend(
            path.relative_to(vault).as_posix()
            for path in sorted(root.rglob("*.pyc"))
            if path.is_file()
        )
        forbidden_paths.extend(
            path.relative_to(vault).as_posix()
            for pycache_dir in sorted(root.rglob("__pycache__"))
            if pycache_dir.is_dir()
            for path in sorted(pycache_dir.rglob("*"))
            if path.is_file()
        )
    forbidden_paths = sorted(set(forbidden_paths))
    enforced = profile == CLEAN_PROFILE
    status = "pass" if not enforced or not forbidden_paths else "fail"
    return {
        "profile": profile,
        "status": status,
        "enforced": enforced,
        "forbidden_count": len(forbidden_paths),
        "forbidden_paths": forbidden_paths,
        "rules": list(CLEAN_PROFILE_RULES),
        "summary": (
            f"clean profile {'enforced' if enforced else 'not enforced'}; "
            f"forbidden_count={len(forbidden_paths)}"
        ),
    }


def _ensure_snapshot_hygiene_clean(hygiene: dict) -> None:
    if hygiene["status"] == "pass":
        return
    paths = ", ".join(hygiene["forbidden_paths"][:10])
    overflow = int(hygiene["forbidden_count"]) - min(int(hygiene["forbidden_count"]), 10)
    suffix = f" (+{overflow} more)" if overflow else ""
    raise ValueError(f"review archive clean profile blocked forbidden snapshot residue: {paths}{suffix}")


def build_review_archive(
    vault: Path,
    archive_path: Path,
    *,
    profile: str = DEFAULT_PROFILE,
    context: RuntimeContext | None = None,
) -> dict:
    hygiene = snapshot_hygiene(vault, profile=profile)
    _ensure_snapshot_hygiene_clean(hygiene)
    policy, resolved_policy_path = load_policy(vault)
    zip_normalization = zip_normalization_from_policy(policy)
    manifest = _public_review_manifest(vault)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for entry in manifest["files"]:
            rel_path = entry["path"]
            file_path = vault / rel_path
            arcname = f"{vault.name}/{rel_path}"
            zf.writestr(
                _normalized_zip_info(
                    arcname,
                    timestamp_utc=zip_normalization["timestamp_utc"],
                    file_mode=zip_normalization["file_mode"],
                ),
                file_path.read_bytes(),
            )
    archive_manifest = _archive_manifest(archive_path, root_prefix=vault.name)
    archive_timestamp_normalization = _archive_timestamp_normalization(
        archive_path,
        expected_timestamp_utc=zip_normalization["timestamp_utc"],
    )
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    archive_display_path = display_path(vault, archive_path)
    manifest_digest = _manifest_digest(manifest)
    archive_manifest_digest = _manifest_digest(archive_manifest)
    representative = manifest_digest == archive_manifest_digest
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="review_archive_report",
            producer=PRODUCER,
            source_command=_source_command(profile),
            resolved_policy_path=resolved_policy_path,
            schema_path=REVIEW_ARCHIVE_REPORT_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/release/review_archive.py",
                "ops/scripts/public/export_public_repo.py",
                "ops/scripts/public/public_surface_policy.py",
            ],
        ),
        "vault": display_path(vault, vault),
        "policy": {
            "path": display_path(vault, resolved_policy_path),
            "version": policy["version"],
        },
        "generated_at": generated_at,
        "profile": profile,
        "status": "pass",
        "archive_path": archive_display_path,
        "archive_file": {
            "path": archive_display_path,
            **describe_output_file(archive_path),
        },
        "packed_file_count": len(manifest["files"]),
        "manifest": manifest,
        "manifest_digest": manifest_digest,
        "archive_manifest": archive_manifest,
        "archive_manifest_digest": archive_manifest_digest,
        "archive_timestamp_normalization": archive_timestamp_normalization,
        "current_snapshot_representativeness": {
            "status": "representative" if representative else "drift",
            "representative_of_current_tree": representative,
            "representative_of_current_zip": representative,
            "checked_at": generated_at,
            "current_manifest_digest": manifest_digest,
            "archive_manifest_digest": archive_manifest_digest,
            "next_action": "none" if representative else "regenerate review archive before sharing",
        },
        "snapshot_hygiene": hygiene,
        "exclusion_policy": "public_surface_policy",
        "excluded_prefixes": list(PUBLIC_EXCLUDED_PREFIXES),
        "excluded_files": sorted(PUBLIC_EXCLUDED_FILES),
    }


def write_report(vault: Path, report: dict, out_path: str | None) -> Path | None:
    if not out_path:
        return None
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=REVIEW_ARCHIVE_REPORT_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_REVIEW_ARCHIVE_REPORT,
            context="review archive report schema validation failed",
            trailing_newline=False,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", default=".")
    parser.add_argument("--archive-out", default=DEFAULT_REVIEW_ARCHIVE_OUT)
    parser.add_argument("--out", default=DEFAULT_REVIEW_ARCHIVE_REPORT)
    parser.add_argument("--profile", choices=sorted(PROFILES), default=DEFAULT_PROFILE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    archive_path = resolve_output_path(
        vault,
        args.archive_out,
        default_relative_path=DEFAULT_REVIEW_ARCHIVE_OUT,
    )
    report = build_review_archive(vault, archive_path, profile=args.profile)
    destination = write_report(vault, report, args.out)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if destination is not None:
        print(f"written_to={display_path(vault, destination)}")


if __name__ == "__main__":
    main()
