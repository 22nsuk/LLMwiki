#!/usr/bin/env python3
from __future__ import annotations
import hashlib
import sys

import argparse
import datetime as dt
import json
import locale
import os
import platform
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        load_optional_json_object_with_diagnostics,
        SchemaBackedReportWriteRequest,
        resolve_schema_backed_report_output_path,
        write_schema_backed_report,
    )
    from ops.scripts.path_portability_runtime import (
        INFOZIP_C_LOCALE_COMPONENT_BYTE_LIMIT,
        component_portability_metrics,
    )
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.raw_markdown_runtime import raw_markdown_quality_pass
    from ops.scripts.raw_registry_runtime import ALIAS_POLICY_VERSION, PATH_ALIAS_RESOLUTION_MODE
    from ops.scripts.registry_diagnostics_runtime import (
        RegistryDiagnosticEmitter,
        registry_diagnostic_paths,
        registry_inventory_context_pass,
        registry_page_presence_pass,
        registry_raw_inventory_consistency_pass,
        registry_source_target_page_naming_pass,
        registry_shared_inventory_diagnostics_pass,
        registry_summary_consistency_pass,
    )
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import (
        RAW_REGISTRY_PREFLIGHT_REPORT_SCHEMA_PATH,
        RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_SCHEMA_PATH,
    )
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        load_optional_json_object_with_diagnostics,
        SchemaBackedReportWriteRequest,
        resolve_schema_backed_report_output_path,
        write_schema_backed_report,
    )
    from ops.scripts.path_portability_runtime import (
        INFOZIP_C_LOCALE_COMPONENT_BYTE_LIMIT,
        component_portability_metrics,
    )
    from ops.scripts.policy_runtime import load_policy, report_path
    from .raw_markdown_runtime import raw_markdown_quality_pass
    from .raw_registry_runtime import ALIAS_POLICY_VERSION, PATH_ALIAS_RESOLUTION_MODE
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import (
        RAW_REGISTRY_PREFLIGHT_REPORT_SCHEMA_PATH,
        RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_SCHEMA_PATH,
    )
    from ops.scripts.registry_diagnostics_runtime import (
        RegistryDiagnosticEmitter,
        registry_diagnostic_paths,
        registry_inventory_context_pass,
        registry_page_presence_pass,
        registry_raw_inventory_consistency_pass,
        registry_source_target_page_naming_pass,
        registry_shared_inventory_diagnostics_pass,
        registry_summary_consistency_pass,
    )


POSIX_ESCAPE_EXPANDED_COMPONENT_BYTE_LIMIT = INFOZIP_C_LOCALE_COMPONENT_BYTE_LIMIT
RAW_WEB_SNAPSHOT_PREFIX = "raw/web-snapshots/"
DEFAULT_OUT = "ops/reports/raw-registry-preflight-report.json"
REPRODUCIBILITY_DEFAULT_OUT = "ops/reports/raw-registry-preflight-reproducibility.json"
PRODUCER = "ops.scripts.raw_registry_preflight"
SOURCE_COMMAND = "python -m ops.scripts.raw_registry_preflight --vault ."
RELEASE_ARCHIVE_SOURCE_COMMAND = (
    "python -m ops.scripts.raw_registry_preflight --vault . --release-archive-profile"
)
REPRODUCIBILITY_SOURCE_COMMAND = (
    "python -m ops.scripts.raw_registry_preflight "
    "--vault . "
    "--out ops/reports/raw-registry-preflight-report.json "
    "--reproducibility-out ops/reports/raw-registry-preflight-reproducibility.json"
)
EXTRACTION_TOOL = "python_zipfile_with_infozip_c_locale_path_budget"
ENVIRONMENT_FINGERPRINT_ALGORITHM = "sha256-json-v1"
REPRODUCIBILITY_COMPARE_FIELDS = (
    "$schema",
    "artifact_kind",
    "source_tree_fingerprint",
    "input_fingerprints",
    "path_alias_resolution_mode",
    "alias_policy_version",
    "environment_fingerprint",
    "metric_semantics",
    "status",
    "unsupported_environment",
    "stats.entry_count",
    "stats.error_count",
    "stats.warning_count",
    "stats.path_alias_match_count",
    "stats.content_hash_fallback_count",
)
REPRODUCIBILITY_IGNORED_FIELDS = (
    "generated_at",
    "currentness.checked_at",
)
METRIC_SEMANTICS = {
    "entry_count": {
        "scope": "registry_entries",
        "description": "Parsed raw registry entries after inventory enrichment.",
    },
    "error_count": {
        "scope": "diagnostics",
        "description": "Number of preflight diagnostics emitted with fail severity.",
    },
    "warning_count": {
        "scope": "diagnostics",
        "description": "Number of preflight diagnostics emitted with warn severity.",
    },
    "path_alias_match_count": {
        "scope": "entries_with_missing_canonical_storage_path",
        "description": (
            "Entries whose canonical storage_path was absent but a manual, exported, "
            "or deterministic environment alias existed on disk."
        ),
    },
    "content_hash_fallback_count": {
        "scope": "entries_with_missing_canonical_storage_path_and_aliases",
        "description": (
            "Entries whose path locators were absent but exactly one raw inventory file "
            "matched the entry content_sha256."
        ),
    },
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _runtime_locale() -> str:
    for name in ("LC_ALL", "LC_CTYPE", "LANG"):
        value = os.environ.get(name)
        if value:
            return value
    return "C"


def _environment_fingerprint_inputs() -> dict[str, str]:
    return {
        "alias_policy_version": ALIAS_POLICY_VERSION,
        "extraction_tool": EXTRACTION_TOOL,
        "filesystem_encoding": sys.getfilesystemencoding(),
        "filesystem_errors": sys.getfilesystemencodeerrors(),
        "locale": _runtime_locale(),
        "os_name": os.name,
        "path_alias_resolution_mode": PATH_ALIAS_RESOLUTION_MODE,
        "path_list_separator": os.pathsep,
        "path_separator": os.sep,
        "platform_system": platform.system() or "unknown",
        "posix_escape_expanded_component_byte_limit": str(
            POSIX_ESCAPE_EXPANDED_COMPONENT_BYTE_LIMIT
        ),
        "preferred_encoding": locale.getpreferredencoding(False),
    }


def environment_fingerprint() -> dict[str, Any]:
    inputs = _environment_fingerprint_inputs()
    return {
        "algorithm": ENVIRONMENT_FINGERPRINT_ALGORITHM,
        "value": _sha256_json(inputs),
        "inputs": inputs,
    }


def _raw_path_posix_portability_pass(vault: Path, emitter: RegistryDiagnosticEmitter) -> None:
    raw_root = vault / "raw"
    if not raw_root.exists():
        return
    for raw_file in sorted(raw_root.rglob("*")):
        if not raw_file.is_file():
            continue
        rel_path = raw_file.relative_to(vault).as_posix()
        for index, component in enumerate(rel_path.split("/")):
            metrics = component_portability_metrics(component)
            component_bytes = metrics["infozip_c_locale_escape_component_bytes"]
            if component_bytes <= POSIX_ESCAPE_EXPANDED_COMPONENT_BYTE_LIMIT:
                continue
            recommended_action = (
                "rename_raw_web_snapshot_to_slug_hash_and_preserve_alias"
                if rel_path.startswith(RAW_WEB_SNAPSHOT_PREFIX)
                else "shorten_raw_path_component_preserving_registry_alias"
            )
            emitter.issue(
                {
                    "type": "raw_path_posix_portability_budget",
                    "page": rel_path,
                    "detail": {
                        "path": rel_path,
                        "component": component,
                        "component_index": index,
                        "escape_mode": "infozip_c_locale",
                        "utf8_component_bytes": metrics["utf8_component_bytes"],
                        "python_unicode_escape_component_bytes": metrics[
                            "python_unicode_escape_component_bytes"
                        ],
                        "posix_escape_expanded_component_bytes": component_bytes,
                        "infozip_c_locale_escape_component_bytes": component_bytes,
                        "limit_bytes": POSIX_ESCAPE_EXPANDED_COMPONENT_BYTE_LIMIT,
                        "recommended_action": recommended_action,
                    },
                },
                "raw_path_posix_portability_budget",
            )


def _release_archive_omits_corpus_surfaces(vault: Path) -> bool:
    return not any((vault / surface).exists() for surface in ("raw", "wiki", "system"))


def _empty_resolution_stats() -> dict[str, bool | int]:
    return {
        "path_alias_match_count": 0,
        "content_hash_fallback_count": 0,
        "unsupported_environment": False,
    }


def _run_inventory_diagnostics(
    vault: Path,
    paths: Any,
    *,
    policy: dict[str, Any],
    emitter: RegistryDiagnosticEmitter,
) -> tuple[list[dict], dict]:
    inventory_context = registry_inventory_context_pass(
        vault,
        paths,
        registry_contract=policy["registry_contract"],
        corpus_routing=policy.get("corpus_routing", {}),
        emitter=emitter,
    )
    if inventory_context is None:
        return [], {
            "path_alias_match_count": 0,
            "content_hash_fallback_count": 0,
            "unsupported_environment": False,
        }
    registry_shared_inventory_diagnostics_pass(
        vault,
        paths,
        context=inventory_context,
        emitter=emitter,
        registered_raw_path_detail_key="storage_path",
    )
    registry_raw_inventory_consistency_pass(
        vault,
        paths,
        context=inventory_context,
        emitter=emitter,
    )
    registry_summary_consistency_pass(
        vault,
        paths,
        context=inventory_context,
        emitter=emitter,
    )
    registry_source_target_page_naming_pass(
        vault,
        paths,
        context=inventory_context,
        source_page_slug_review=policy["frontmatter_contract"]["metadata_review"].get(
            "source_page_slug",
            {},
        ),
        emitter=emitter,
    )
    return inventory_context.registry_entries, inventory_context.resolution_stats


def _run_preflight_diagnostics(
    vault: Path,
    policy: dict[str, Any],
) -> tuple[Any, RegistryDiagnosticEmitter, list[dict], dict]:
    registry_contract = policy["registry_contract"]
    paths = registry_diagnostic_paths(vault, registry_contract)
    emitter = RegistryDiagnosticEmitter(lint_thresholds=policy["lint_thresholds"])
    entries: list[dict] = []
    resolution_stats: dict = {
        "path_alias_match_count": 0,
        "content_hash_fallback_count": 0,
        "unsupported_environment": False,
    }
    if registry_page_presence_pass(
        vault,
        paths,
        registry_contract=registry_contract,
        emitter=emitter,
        summary_detail_mode="path",
    ):
        entries, resolution_stats = _run_inventory_diagnostics(
            vault,
            paths,
            policy=policy,
            emitter=emitter,
        )
    raw_markdown_quality_pass(
        vault,
        emitter=emitter,
        raw_markdown_contract=policy["raw_markdown_normalization_contract"],
    )
    _raw_path_posix_portability_pass(vault, emitter)
    return paths, emitter, entries, resolution_stats


def _preflight_stats(
    *,
    entries: list[dict],
    emitter: RegistryDiagnosticEmitter,
    resolution_stats: dict,
) -> dict[str, int]:
    return {
        "entry_count": len(entries),
        "error_count": len(emitter.errors),
        "warning_count": len(emitter.warnings),
        "path_alias_match_count": int(resolution_stats.get("path_alias_match_count", 0)),
        "content_hash_fallback_count": int(resolution_stats.get("content_hash_fallback_count", 0)),
    }


def preflight(
    vault: Path,
    policy_path: str | None = None,
    *,
    context: RuntimeContext | None = None,
    release_archive_profile: bool = False,
) -> dict:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    registry_contract = policy["registry_contract"]
    paths = registry_diagnostic_paths(vault, registry_contract)
    if release_archive_profile and _release_archive_omits_corpus_surfaces(vault):
        emitter = RegistryDiagnosticEmitter(lint_thresholds=policy["lint_thresholds"])
        entries: list[dict[str, Any]] = []
        resolution_stats = _empty_resolution_stats()
        raw_registry_entry_pages = []
    else:
        paths, emitter, entries, resolution_stats = _run_preflight_diagnostics(vault, policy)
        raw_registry_entry_pages = [
            report_path(vault, page) for page in paths.raw_registry_entry_pages
        ]
    status = "fail" if emitter.errors else "warn" if emitter.warnings else "pass"
    generated_at = runtime_context.isoformat_z()
    env_fingerprint = environment_fingerprint()
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="raw_registry_preflight_report",
            producer=PRODUCER,
            source_command=RELEASE_ARCHIVE_SOURCE_COMMAND
            if release_archive_profile
            else SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=RAW_REGISTRY_PREFLIGHT_REPORT_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/raw_registry_preflight.py",
                "ops/scripts/raw_registry_runtime.py",
                "ops/scripts/registry_diagnostics_runtime.py",
            ],
            path_group_inputs={
                "raw_registry_entry_pages": raw_registry_entry_pages,
                "raw_inventory": [
                    path.relative_to(vault).as_posix()
                    for path in sorted((vault / "raw").rglob("*"))
                    if path.is_file()
                ]
                if (vault / "raw").exists()
                else [],
            },
            text_inputs={
                "alias_policy_version": ALIAS_POLICY_VERSION,
                "environment_fingerprint": env_fingerprint["value"],
                "metric_semantics": _canonical_json(METRIC_SEMANTICS),
                "path_alias_resolution_mode": PATH_ALIAS_RESOLUTION_MODE,
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "generated_at": generated_at,
        "summary_page": report_path(vault, paths.raw_registry_path),
        "entry_pages": raw_registry_entry_pages,
        "status": status,
        "extraction_tool": EXTRACTION_TOOL,
        "locale": _runtime_locale(),
        "path_alias_resolution_mode": PATH_ALIAS_RESOLUTION_MODE,
        "alias_policy_version": ALIAS_POLICY_VERSION,
        "environment_fingerprint": env_fingerprint,
        "metric_semantics": METRIC_SEMANTICS,
        "unsupported_environment": bool(resolution_stats.get("unsupported_environment", False)),
        "errors": emitter.errors,
        "warnings": emitter.warnings,
        "stats": _preflight_stats(
            entries=entries,
            emitter=emitter,
            resolution_stats=resolution_stats,
        ),
    }


def _timestamp_output_from_report(destination: Path, report: dict) -> Path:
    generated_at = str(report.get("generated_at", ""))
    try:
        timestamp = dt.datetime.fromisoformat(generated_at.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return destination
    os.utime(destination, (timestamp, timestamp))
    return destination


def load_stored_preflight_report(vault: Path, stored_report_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    stored_report, diagnostics = load_optional_json_object_with_diagnostics(stored_report_path)
    normalized_diagnostics = dict(diagnostics)
    normalized_diagnostics["path"] = report_path(vault, stored_report_path)
    return stored_report, normalized_diagnostics


def _field_value(payload: dict[str, Any], field_path: str) -> tuple[bool, Any]:
    current: Any = payload
    for part in field_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _comparison(field_path: str, stored_report: dict[str, Any], live_report: dict[str, Any]) -> dict[str, Any]:
    has_stored, stored_value = _field_value(stored_report, field_path)
    has_live, live_value = _field_value(live_report, field_path)
    if not has_stored:
        status = "missing_stored"
    elif not has_live:
        status = "missing_live"
    elif stored_value == live_value:
        status = "match"
    else:
        status = "mismatch"
    return {
        "field": field_path,
        "status": status,
        "stored_value": stored_value,
        "live_value": live_value,
    }


def _preflight_report_summary(report: dict[str, Any]) -> dict[str, Any]:
    errors = report.get("errors", [])
    warnings = report.get("warnings", [])
    return {
        "generated_at": report.get("generated_at", ""),
        "source_tree_fingerprint": report.get("source_tree_fingerprint", ""),
        "input_fingerprints": report.get("input_fingerprints", {}),
        "status": report.get("status", "unknown"),
        "path_alias_resolution_mode": report.get("path_alias_resolution_mode", ""),
        "alias_policy_version": report.get("alias_policy_version", ""),
        "environment_fingerprint": report.get("environment_fingerprint", {}),
        "metric_semantics": report.get("metric_semantics", {}),
        "stats": report.get("stats", {}),
        "error_count": len(errors) if isinstance(errors, list) else None,
        "warning_count": len(warnings) if isinstance(warnings, list) else None,
    }


def _diff_status(load_status: str, comparisons: list[dict[str, Any]]) -> str:
    if load_status == "missing":
        return "stored_missing"
    if load_status != "ok":
        return "stored_unavailable"
    if any(item["status"] != "match" for item in comparisons):
        return "mismatch"
    return "match"


def build_reproducibility_report(
    vault: Path,
    *,
    live_report: dict[str, Any],
    stored_report: dict[str, Any],
    stored_diagnostics: dict[str, Any],
    stored_report_path: Path,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    comparisons = [
        _comparison(field_path, stored_report, live_report)
        for field_path in REPRODUCIBILITY_COMPARE_FIELDS
    ]
    load_status = str(stored_diagnostics.get("status", "unknown"))
    diff_status = _diff_status(load_status, comparisons)
    env_fingerprint = live_report.get("environment_fingerprint", environment_fingerprint())
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="raw_registry_preflight_reproducibility",
            producer=PRODUCER,
            source_command=REPRODUCIBILITY_SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/raw_registry_preflight.py",
                "ops/scripts/raw_registry_runtime.py",
                "ops/scripts/registry_diagnostics_runtime.py",
            ],
            file_inputs={
                "stored_preflight_report": stored_report_path,
            },
            text_inputs={
                "compare_fields": "\n".join(REPRODUCIBILITY_COMPARE_FIELDS),
                "ignored_fields": "\n".join(REPRODUCIBILITY_IGNORED_FIELDS),
                "live_preflight_report": _canonical_json(live_report),
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": "pass" if diff_status == "match" else "warn",
        "diff_status": diff_status,
        "stored_report": {
            "path": report_path(vault, stored_report_path),
            "load_status": load_status,
            "diagnostics": stored_diagnostics,
            "summary": _preflight_report_summary(stored_report) if load_status == "ok" else {},
        },
        "live_report": {
            "summary": _preflight_report_summary(live_report),
        },
        "compare_fields": list(REPRODUCIBILITY_COMPARE_FIELDS),
        "ignored_fields": list(REPRODUCIBILITY_IGNORED_FIELDS),
        "comparisons": comparisons,
        "path_alias_resolution_mode": live_report.get(
            "path_alias_resolution_mode",
            PATH_ALIAS_RESOLUTION_MODE,
        ),
        "alias_policy_version": live_report.get("alias_policy_version", ALIAS_POLICY_VERSION),
        "environment_fingerprint": env_fingerprint,
        "metric_semantics": live_report.get("metric_semantics", METRIC_SEMANTICS),
    }


def write_report(vault: Path, report: dict, out_path: str | None) -> Path:
    destination = write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=RAW_REGISTRY_PREFLIGHT_REPORT_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="raw registry preflight report schema validation failed",
            trailing_newline=False,
        )
    )
    return _timestamp_output_from_report(destination, report)


def write_reproducibility_report(vault: Path, report: dict, out_path: str | None) -> Path:
    destination = write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=REPRODUCIBILITY_DEFAULT_OUT,
            context="raw registry preflight reproducibility report schema validation failed",
            trailing_newline=False,
        )
    )
    return _timestamp_output_from_report(destination, report)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    ap.add_argument("--out")
    ap.add_argument("--stored-report")
    ap.add_argument("--reproducibility-out")
    ap.add_argument("--release-archive-profile", action="store_true")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    vault = Path(args.vault)
    report = preflight(vault, args.policy, release_archive_profile=args.release_archive_profile)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        write_report(vault, report, args.out)
    else:
        print(text)
    if args.reproducibility_out:
        stored_report_path = resolve_schema_backed_report_output_path(
            vault,
            args.stored_report or args.out,
            default_relative_path=DEFAULT_OUT,
        )
        stored_report, stored_diagnostics = load_stored_preflight_report(vault, stored_report_path)
        reproducibility_report = build_reproducibility_report(
            vault,
            live_report=report,
            stored_report=stored_report,
            stored_diagnostics=stored_diagnostics,
            stored_report_path=stored_report_path,
            policy_path=args.policy,
        )
        write_reproducibility_report(vault, reproducibility_report, args.reproducibility_out)
    raise SystemExit(1 if report["status"] == "fail" else 0)


if __name__ == "__main__":
    main()
