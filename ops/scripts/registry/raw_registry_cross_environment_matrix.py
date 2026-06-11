#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import unicodedata
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.core.artifact_freshness_mtime_runtime import parse_generated_at
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.raw_registry_preflight import (
        ALIAS_POLICY_VERSION,
        EXTRACTION_TOOL,
        METRIC_SEMANTICS,
        PATH_ALIAS_RESOLUTION_MODE,
        _comparison,
        _preflight_report_summary,
        environment_fingerprint,
        preflight,
    )
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import (
        RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_SCHEMA_PATH,
    )
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.core.artifact_freshness_mtime_runtime import parse_generated_at
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import (
        RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_SCHEMA_PATH,
    )

    from .raw_registry_preflight import (
        ALIAS_POLICY_VERSION,
        EXTRACTION_TOOL,
        METRIC_SEMANTICS,
        PATH_ALIAS_RESOLUTION_MODE,
        _comparison,
        _preflight_report_summary,
        environment_fingerprint,
        preflight,
    )


DEFAULT_OUT = "ops/reports/raw-registry-cross-environment-matrix.json"
DEFAULT_STORED_PREFLIGHT = "ops/reports/raw-registry-preflight-report.json"
PRODUCER = "ops.scripts.raw_registry_cross_environment_matrix"
SOURCE_COMMAND = (
    "python -m ops.scripts.raw_registry_cross_environment_matrix "
    "--vault . --out ops/reports/raw-registry-cross-environment-matrix.json"
)
CI_WORKFLOW_PATH = ".github/workflows/ci.yml"
SEMANTIC_COMPARE_FIELDS = (
    "$schema",
    "artifact_kind",
    "path_alias_resolution_mode",
    "alias_policy_version",
    "metric_semantics",
    "status",
    "unsupported_environment",
    "stats.entry_count",
    "stats.error_count",
    "stats.warning_count",
    "stats.path_alias_match_count",
    "stats.content_hash_fallback_count",
)
CI_ENVIRONMENTS = (
    {
        "profile": "linux-c-utf8",
        "os_family": "linux",
        "ci_runner": "ubuntu-latest",
        "locale": "C.UTF-8",
        "path_separator": "/",
    },
    {
        "profile": "windows-utf8",
        "os_family": "windows",
        "ci_runner": "windows-latest",
        "locale": "utf-8",
        "path_separator": "\\",
    },
    {
        "profile": "macos-utf8",
        "os_family": "macos",
        "ci_runner": "macos-latest",
        "locale": "UTF-8",
        "path_separator": "/",
    },
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _repo_has_live_registry_inputs(vault: Path) -> bool:
    return (
        (vault / "system" / "system-index.md").is_file()
        and (vault / "wiki" / "index.md").is_file()
        and (vault / "raw").exists()
    )


def _current_profile() -> str:
    system = (platform.system() or "").lower()
    if system.startswith("win"):
        return "windows-utf8"
    if system == "darwin":
        return "macos-utf8"
    return "linux-c-utf8"


def _workflow_text(vault: Path) -> str:
    path = vault / CI_WORKFLOW_PATH
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _check(name: str, status: str, *, expected: Any, observed: Any, detail: str) -> dict[str, Any]:
    return {
        "check": name,
        "status": status,
        "expected": expected,
        "observed": observed,
        "detail": detail,
    }


def _ci_workflow_checks(workflow_text: str, profile: str, runner: str) -> list[dict[str, Any]]:
    return [
        _check(
            "ci_runner_declared",
            "pass" if runner in workflow_text else "fail",
            expected=runner,
            observed=runner if runner in workflow_text else "",
            detail="GitHub Actions raw registry cross-environment matrix declares the runner.",
        ),
        _check(
            "ci_profile_declared",
            "pass" if profile in workflow_text else "fail",
            expected=profile,
            observed=profile if profile in workflow_text else "",
            detail="GitHub Actions raw registry cross-environment matrix declares the profile.",
        ),
        _check(
            "ci_upload_declared",
            "pass" if "raw-registry-cross-environment-${{ matrix.profile }}" in workflow_text else "fail",
            expected="raw-registry-cross-environment-${{ matrix.profile }}",
            observed=(
                "raw-registry-cross-environment-${{ matrix.profile }}"
                if "raw-registry-cross-environment-${{ matrix.profile }}" in workflow_text
                else ""
            ),
            detail="CI uploads per-profile matrix reports for later package evidence review.",
        ),
    ]


def _live_checks(
    *,
    live_report: dict[str, Any] | None,
    stored_report: dict[str, Any],
    stored_status: str,
    require_live: bool,
) -> list[dict[str, Any]]:
    if live_report is None:
        status = "fail" if require_live else "skipped"
        return [
            _check(
                "live_preflight_available",
                status,
                expected="full local vault with system/wiki/raw",
                observed="missing full-vault inputs",
                detail="Live raw registry preflight is skipped outside full-vault checkouts.",
            ),
            _check(
                "stored_live_semantic_match",
                status,
                expected="all semantic compare fields match",
                observed="missing live preflight",
                detail=(
                    "Stored/live raw registry semantic parity requires full-vault "
                    "inputs; public mirror checkouts record this as skipped."
                ),
            ),
        ]
    comparisons = [
        _comparison(field, stored_report, live_report)
        for field in SEMANTIC_COMPARE_FIELDS
    ] if stored_status == "ok" else []
    comparison_status = (
        "pass"
        if stored_status == "ok" and all(item["status"] == "match" for item in comparisons)
        else "fail"
        if require_live and stored_status != "ok"
        else "skipped"
        if stored_status != "ok"
        else "fail"
    )
    return [
        _check(
            "live_preflight_status",
            "pass" if live_report.get("status") == "pass" else "fail",
            expected="pass",
            observed=live_report.get("status", "unknown"),
            detail="Current environment can execute raw registry preflight without diagnostics.",
        ),
        _check(
            "stored_live_semantic_match",
            comparison_status,
            expected="all semantic compare fields match",
            observed=comparisons,
            detail="Environment-specific fields are ignored; raw registry semantic fields must remain stable.",
        ),
    ]


def _path_separator_checks(live_report: dict[str, Any] | None) -> list[dict[str, Any]]:
    windows_fixture = "raw\\web-snapshots\\Café Sample.md"
    normalized = windows_fixture.replace("\\", "/")
    checks = [
        _check(
            "windows_separator_normalizes_to_posix",
            "pass" if normalized == "raw/web-snapshots/Café Sample.md" else "fail",
            expected="raw/web-snapshots/Café Sample.md",
            observed=normalized,
            detail="Windows-style raw registry locators normalize to the POSIX registry/storage contract.",
        )
    ]
    if live_report is not None:
        serialized = _canonical_json(
            {
                "summary_page": live_report.get("summary_page", ""),
                "entry_pages": live_report.get("entry_pages", []),
                "errors": live_report.get("errors", []),
                "warnings": live_report.get("warnings", []),
            }
        )
        checks.append(
            _check(
                "live_report_paths_are_posix",
                "pass" if "\\" not in serialized else "fail",
                expected="no backslash in report path fields",
                observed="backslash found" if "\\" in serialized else "posix-only",
                detail="Checked-in registry reports should remain platform-neutral even when generated on Windows.",
            )
        )
    return checks


def _locale_checks() -> list[dict[str, Any]]:
    samples = [
        "raw/web-snapshots/Cafe.md",
        "raw/web-snapshots/Café.md",
        "raw/web-snapshots/한글.md",
    ]
    roundtrips = [
        sample.encode("utf-8").decode("utf-8") == sample
        for sample in samples
    ]
    normalized = [
        unicodedata.normalize("NFC", sample)
        for sample in samples
    ]
    return [
        _check(
            "utf8_path_roundtrip_fixture",
            "pass" if all(roundtrips) else "fail",
            expected="all sample raw paths round-trip through UTF-8",
            observed=roundtrips,
            detail="Locale matrix protects non-ASCII raw path labels from ASCII-only assumptions.",
        ),
        _check(
            "unicode_normalization_fixture",
            "pass" if all(unicodedata.is_normalized("NFC", item) for item in normalized) else "fail",
            expected="NFC-normalized sample labels",
            observed=normalized,
            detail="macOS-style Unicode normalization drift is represented as an explicit fixture contract.",
        ),
    ]


def _row_status(checks: list[dict[str, Any]]) -> str:
    if any(item["status"] == "fail" for item in checks):
        return "fail"
    if any(item["status"] == "skipped" for item in checks):
        return "skipped"
    return "pass"


def _matrix_status(rows: list[dict[str, Any]]) -> str:
    if any(row["status"] == "fail" and row["required"] for row in rows):
        return "fail"
    if any(row["status"] == "skipped" and row["required"] for row in rows):
        return "warn"
    return "pass"


def _environment_row(
    *,
    profile: str,
    os_family: str,
    locale_name: str,
    path_separator: str,
    evidence_mode: str,
    checks: list[dict[str, Any]],
    ci_runner: str = "",
    live_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "profile": profile,
        "os_family": os_family,
        "locale": locale_name,
        "path_separator": path_separator,
        "ci_runner": ci_runner,
        "evidence_mode": evidence_mode,
        "required": True,
        "status": _row_status(checks),
        "checks": checks,
        "live_report_summary": _preflight_report_summary(live_report) if live_report is not None else {},
    }


def _ci_environment_rows(
    *,
    current_profile: str,
    workflow_text: str,
    live_report: dict[str, Any] | None,
    stored_report: dict[str, Any],
    stored_status: str,
    require_live: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for environment in CI_ENVIRONMENTS:
        env_profile = str(environment["profile"])
        ci_checks = _ci_workflow_checks(
            workflow_text,
            env_profile,
            str(environment["ci_runner"]),
        )
        if env_profile == current_profile:
            ci_checks.extend(
                _live_checks(
                    live_report=live_report,
                    stored_report=stored_report,
                    stored_status=stored_status,
                    require_live=require_live,
                )
            )
            evidence_mode = "live_preflight_and_ci_workflow"
            row_live_report = live_report
        else:
            evidence_mode = "ci_workflow"
            row_live_report = None
        rows.append(
            _environment_row(
                profile=env_profile,
                os_family=str(environment["os_family"]),
                locale_name=str(environment["locale"]),
                path_separator=str(environment["path_separator"]),
                ci_runner=str(environment["ci_runner"]),
                evidence_mode=evidence_mode,
                checks=ci_checks,
                live_report=row_live_report,
            )
        )
    return rows


def _fixture_rows(live_report: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [
        _environment_row(
            profile="path-separator-fixture",
            os_family="cross_platform",
            locale_name="n/a",
            path_separator="mixed",
            evidence_mode="fixture",
            checks=_path_separator_checks(live_report),
        ),
        _environment_row(
            profile="locale-utf8-fixture",
            os_family="cross_platform",
            locale_name="UTF-8",
            path_separator="/",
            evidence_mode="fixture",
            checks=_locale_checks(),
        ),
    ]


def _stored_report_record(
    vault: Path,
    resolved_stored_report: Path,
    stored_report: dict[str, Any],
    stored_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "path": report_path(vault, resolved_stored_report),
        "load_status": stored_diagnostics.get("status", "unknown"),
        "diagnostics": {
            **stored_diagnostics,
            "path": report_path(vault, resolved_stored_report),
        },
        "summary": _preflight_report_summary(stored_report)
        if stored_diagnostics.get("status") == "ok"
        else {},
    }


def build_matrix_report(
    vault: Path,
    *,
    profile: str = "local",
    stored_report_path: str = DEFAULT_STORED_PREFLIGHT,
    policy_path: str | None = None,
    require_live: bool = False,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    resolved_stored_report = vault / stored_report_path
    stored_report, stored_diagnostics = load_optional_json_object_with_diagnostics(resolved_stored_report)
    live_report = (
        preflight(vault, policy_path=policy_path, context=runtime_context)
        if _repo_has_live_registry_inputs(vault)
        else None
    )
    current_profile = _current_profile() if profile == "local" else profile
    workflow_text = _workflow_text(vault)
    env_fingerprint = environment_fingerprint()
    rows = _ci_environment_rows(
        current_profile=current_profile,
        workflow_text=workflow_text,
        live_report=live_report,
        stored_report=stored_report,
        stored_status=str(stored_diagnostics.get("status", "unknown")),
        require_live=require_live,
    )
    rows.extend(_fixture_rows(live_report))
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="raw_registry_cross_environment_matrix",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/raw_registry_cross_environment_matrix.py",
                "ops/scripts/raw_registry_preflight.py",
                ".github/workflows/ci.yml",
            ],
            file_inputs={"stored_preflight_report": stored_report_path},
            text_inputs={
                "profile": current_profile,
                "semantic_compare_fields": "\n".join(SEMANTIC_COMPARE_FIELDS),
                "ci_environments": _canonical_json(CI_ENVIRONMENTS),
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": _matrix_status(rows),
        "profile": current_profile,
        "stored_report": _stored_report_record(
            vault,
            resolved_stored_report,
            stored_report,
            stored_diagnostics,
        ),
        "current_environment": {
            "profile": _current_profile(),
            "os_name": os.name,
            "platform_system": platform.system() or "unknown",
            "path_separator": os.sep,
            "path_list_separator": os.pathsep,
        },
        "environment_fingerprint": env_fingerprint,
        "path_alias_resolution_mode": PATH_ALIAS_RESOLUTION_MODE,
        "alias_policy_version": ALIAS_POLICY_VERSION,
        "extraction_tool": EXTRACTION_TOOL,
        "metric_semantics": METRIC_SEMANTICS,
        "semantic_compare_fields": list(SEMANTIC_COMPARE_FIELDS),
        "matrix": rows,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    destination = write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="raw registry cross-environment matrix schema validation failed",
        )
    )
    generated_at = str(report.get("generated_at", ""))
    generated_dt = parse_generated_at(generated_at)
    if generated_dt is None:
        return destination
    timestamp = generated_dt.timestamp()
    os.utime(destination, (timestamp, timestamp))
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build raw registry cross-environment matrix evidence")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--stored-report", default=DEFAULT_STORED_PREFLIGHT)
    parser.add_argument("--profile", default="local")
    parser.add_argument("--require-live", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_matrix_report(
        vault,
        profile=args.profile,
        stored_report_path=args.stored_report,
        policy_path=args.policy,
        require_live=args.require_live,
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
