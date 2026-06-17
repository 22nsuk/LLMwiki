#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

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
    RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_SCHEMA_PATH,
    RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_SCHEMA_PATH,
)
from ops.scripts.core.schema_runtime import (
    load_schema_with_vault_override,
    validate_with_schema,
)

DEFAULT_OUT = "ops/reports/raw-registry-cross-environment-evidence-bundle.json"
DEFAULT_REPORTS_DIR = "ops/reports"
PRODUCER = "ops.scripts.raw_registry_cross_environment_evidence_bundle"
SOURCE_COMMAND = (
    "python -m ops.scripts.raw_registry_cross_environment_evidence_bundle "
    "--vault . --reports-dir ops/reports "
    "--out ops/reports/raw-registry-cross-environment-evidence-bundle.json"
)
DEFAULT_EXPECTED_PROFILES = ("linux-c-utf8", "windows-utf8", "macos-utf8")
REPORT_PREFIX = "raw-registry-cross-environment-matrix-"
REPORT_SUFFIX = ".json"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _resolve_input_path(vault: Path, raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    return (vault / path).resolve()


def _safe_input_path(vault: Path, path: Path) -> str:
    resolved_vault = vault.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_vault)
    except ValueError:
        return f"external-report-inputs/{path.name}"
    return report_path(vault, resolved_path)


def _profile_from_report_path(path: Path) -> str:
    name = path.name
    if name.startswith(REPORT_PREFIX) and name.endswith(REPORT_SUFFIX):
        return name[len(REPORT_PREFIX) : -len(REPORT_SUFFIX)]
    return path.stem or "unknown"


def _artifact_name(profile: str) -> str:
    return f"raw-registry-cross-environment-{profile}"


def _report_paths_from_directory(
    vault: Path,
    reports_dir: str | Path,
    expected_profiles: tuple[str, ...],
) -> list[tuple[Path, str]]:
    directory = _resolve_input_path(vault, reports_dir)
    by_profile: dict[str, Path] = {
        profile: directory / f"{REPORT_PREFIX}{profile}{REPORT_SUFFIX}"
        for profile in expected_profiles
    }
    for path in sorted(directory.glob(f"{REPORT_PREFIX}*{REPORT_SUFFIX}")):
        profile = _profile_from_report_path(path)
        by_profile.setdefault(profile, path)
    return [(path, profile) for profile, path in sorted(by_profile.items())]


def _report_paths_from_arguments(vault: Path, reports: list[str]) -> list[tuple[Path, str]]:
    paths = [(_resolve_input_path(vault, item), "") for item in reports]
    return sorted((path, _profile_from_report_path(path)) for path, _ in paths)


def _semantic_compare_status(report: dict[str, Any], profile: str) -> str:
    for row in report.get("matrix", []):
        if not isinstance(row, dict) or row.get("profile") != profile:
            continue
        for check in row.get("checks", []):
            if not isinstance(check, dict):
                continue
            if check.get("check") == "stored_live_semantic_match":
                return str(check.get("status", "unknown"))
        return "missing"
    return "missing"


def _runner_os(report: dict[str, Any], profile: str) -> str:
    for row in report.get("matrix", []):
        if isinstance(row, dict) and row.get("profile") == profile:
            return str(row.get("ci_runner") or "")
    current_environment = report.get("current_environment", {})
    if isinstance(current_environment, dict):
        return str(current_environment.get("platform_system") or "")
    return ""


def _diagnostic(code: str, path: str, message: str, *, severity: str = "error") -> dict[str, str]:
    return {
        "severity": severity,
        "code": code,
        "path": path,
        "message": message,
    }


def _single_matrix_fallback_diagnostic(vault: Path, reports_dir: str | Path) -> dict[str, str] | None:
    single_matrix_path = _resolve_input_path(vault, reports_dir) / "raw-registry-cross-environment-matrix.json"
    if not single_matrix_path.is_file():
        return None
    return _diagnostic(
        "single_matrix_fallback_present",
        _safe_input_path(vault, single_matrix_path),
        (
            "legacy single cross-environment matrix exists; collect per-profile "
            "raw-registry-cross-environment-matrix-{linux-c-utf8,windows-utf8,macos-utf8}.json "
            "reports for portability evidence bundle completeness"
        ),
        severity="info",
    )


def _status_diagnostics_for_evidence_item(item: dict[str, Any]) -> list[dict[str, str]]:
    if item.get("load_status") != "ok":
        return []
    path = str(item.get("report_path") or "")
    profile = str(item.get("profile") or "unknown")
    diagnostics: list[dict[str, str]] = []
    semantic_status = str(item.get("semantic_compare_status") or "unknown")
    if semantic_status == "missing":
        diagnostics.append(
            _diagnostic(
                "semantic_compare_missing",
                path,
                (
                    f"profile {profile} is missing the stored_live_semantic_match check; "
                    "the evidence bundle cannot prove live/stored raw-registry semantic parity"
                ),
            )
        )
    elif semantic_status == "fail":
        diagnostics.append(
            _diagnostic(
                "semantic_compare_failed",
                path,
                f"profile {profile} reported stored/live raw-registry semantic mismatch",
            )
        )
    elif semantic_status == "skipped":
        diagnostics.append(
            _diagnostic(
                "semantic_compare_skipped",
                path,
                (
                    f"profile {profile} skipped stored/live raw-registry semantic comparison; "
                    "full-vault inputs are required to prove parity"
                ),
                severity="warning",
            )
        )

    report_status = str(item.get("status") or "unknown")
    if report_status == "fail":
        diagnostics.append(
            _diagnostic(
                "report_status_fail",
                path,
                f"profile {profile} matrix report status is fail",
            )
        )
    elif report_status == "warn":
        diagnostics.append(
            _diagnostic(
                "report_status_warn",
                path,
                f"profile {profile} matrix report status is warn",
                severity="warning",
            )
        )
    return diagnostics


def _load_evidence_item(
    *,
    vault: Path,
    path: Path,
    expected_profile: str,
    matrix_schema: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    safe_path = _safe_input_path(vault, path)
    exists = path.is_file()
    sha256 = _sha256_file(path) if exists else ""
    size_bytes = path.stat().st_size if exists else 0
    payload, diagnostics = load_optional_json_object_with_diagnostics(path)
    load_status = str(diagnostics.get("status", "unknown"))
    item_diagnostics: list[dict[str, str]] = []
    profile = str(payload.get("profile") or expected_profile or _profile_from_report_path(path))

    if not exists:
        item_diagnostics.append(
            _diagnostic(
                "missing_report",
                safe_path,
                "expected per-profile matrix report is missing",
            )
        )
    elif load_status != "ok":
        item_diagnostics.append(
            _diagnostic(
                f"report_{load_status}",
                safe_path,
                str(diagnostics.get("message") or "report could not be loaded as a JSON object"),
            )
        )
    else:
        schema_errors = validate_with_schema(payload, matrix_schema)
        if schema_errors:
            load_status = "schema_error"
            item_diagnostics.append(
                _diagnostic(
                    "report_schema_error",
                    safe_path,
                    "; ".join(schema_errors[:3]),
                )
            )
        if payload.get("artifact_kind") != "raw_registry_cross_environment_matrix":
            load_status = "schema_error"
            item_diagnostics.append(
                _diagnostic(
                    "wrong_artifact_kind",
                    safe_path,
                    "report is not a raw_registry_cross_environment_matrix artifact",
                )
            )

    semantic_status = _semantic_compare_status(payload, profile) if load_status == "ok" else "unknown"
    report_status = str(payload.get("status") or ("missing" if not exists else "invalid" if load_status != "ok" else "unknown"))
    return (
        {
            "profile": profile,
            "runner_os": _runner_os(payload, profile) if load_status == "ok" else "",
            "generated_at": str(payload.get("generated_at") or ""),
            "status": report_status,
            "report_path": safe_path,
            "exists": exists,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "load_status": load_status,
            "semantic_compare_status": semantic_status,
            "uploaded_artifact_name": _artifact_name(profile),
            "diagnostics": item_diagnostics,
        },
        item_diagnostics,
    )


def _bundle_status(evidence: list[dict[str, Any]], diagnostics: list[dict[str, str]]) -> str:
    if any(item.get("severity") == "error" for item in diagnostics):
        return "fail"
    if any(item["status"] == "fail" or item["semantic_compare_status"] in {"fail", "missing"} for item in evidence):
        return "fail"
    if any(item.get("severity") == "warning" for item in diagnostics):
        return "warn"
    if any(item["status"] == "warn" or item["semantic_compare_status"] == "skipped" for item in evidence):
        return "warn"
    return "pass"


def _summary(evidence: list[dict[str, Any]], diagnostics: list[dict[str, str]]) -> dict[str, int]:
    return {
        "expected_profile_count": len(evidence),
        "report_count": sum(1 for item in evidence if item["exists"]),
        "valid_report_count": sum(1 for item in evidence if item["load_status"] == "ok"),
        "missing_report_count": sum(1 for item in evidence if item["load_status"] == "missing"),
        "invalid_report_count": sum(
            1 for item in evidence if item["load_status"] not in {"ok", "missing"}
        ),
        "failed_report_count": sum(1 for item in evidence if item["status"] == "fail"),
        "diagnostic_count": len(diagnostics),
    }


def _failure_causes(diagnostics: list[dict[str, str]]) -> list[dict[str, str]]:
    return [item for item in diagnostics if item.get("severity") in {"error", "warning"}]


def build_evidence_bundle(
    vault: Path,
    *,
    reports_dir: str | Path = DEFAULT_REPORTS_DIR,
    reports: list[str] | None = None,
    expected_profiles: tuple[str, ...] = DEFAULT_EXPECTED_PROFILES,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    matrix_schema = load_schema_with_vault_override(vault, RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_SCHEMA_PATH)
    candidates = (
        _report_paths_from_arguments(vault, reports)
        if reports
        else _report_paths_from_directory(vault, reports_dir, expected_profiles)
    )

    evidence: list[dict[str, Any]] = []
    diagnostics: list[dict[str, str]] = []
    if not reports:
        single_matrix_diagnostic = _single_matrix_fallback_diagnostic(vault, reports_dir)
        if single_matrix_diagnostic is not None:
            diagnostics.append(single_matrix_diagnostic)
    seen_profiles: set[str] = set()
    for path, expected_profile in candidates:
        item, item_diagnostics = _load_evidence_item(
            vault=vault,
            path=path,
            expected_profile=expected_profile,
            matrix_schema=matrix_schema,
        )
        status_diagnostics = _status_diagnostics_for_evidence_item(item)
        item_diagnostics.extend(status_diagnostics)
        if item["profile"] in seen_profiles:
            duplicate = _diagnostic(
                "duplicate_profile",
                item["report_path"],
                f"profile {item['profile']} appears more than once in the evidence bundle",
            )
            item["diagnostics"].append(duplicate)
            item_diagnostics.append(duplicate)
        seen_profiles.add(str(item["profile"]))
        evidence.append(item)
        diagnostics.extend(item_diagnostics)

    file_inputs = {
        f"report_{item['profile']}": item["report_path"]
        for item in evidence
        if item["report_path"] and item["report_path"].startswith(("ops/", "runs/", ".github/"))
    }
    report_path_list = "\n".join(item["report_path"] for item in evidence)
    status = _bundle_status(evidence, diagnostics)
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="raw_registry_cross_environment_evidence_bundle",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/registry/raw_registry_cross_environment_evidence_bundle.py",
                "ops/scripts/registry/raw_registry_cross_environment_matrix.py",
            ],
            file_inputs=file_inputs,
            text_inputs={
                "expected_profiles": "\n".join(expected_profiles),
                "report_paths": report_path_list,
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": status,
        "reports_dir": report_path(vault, _resolve_input_path(vault, reports_dir)),
        "expected_profiles": list(expected_profiles),
        "summary": _summary(evidence, diagnostics),
        "evidence": evidence,
        "diagnostics": diagnostics,
        "failure_causes": _failure_causes(diagnostics),
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="raw registry cross-environment evidence bundle schema validation failed",
        )
    )


def _cli_failure_summary(vault: Path, report: dict[str, Any], destination: Path) -> dict[str, Any]:
    return {
        "status": str(report.get("status") or "unknown"),
        "report": display_path(vault, destination),
        "summary": report.get("summary") if isinstance(report.get("summary"), dict) else {},
        "failure_causes": report.get("failure_causes")
        if isinstance(report.get("failure_causes"), list)
        else [],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect raw registry cross-environment matrix evidence")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--reports-dir", default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--report", action="append", default=[])
    parser.add_argument("--expected-profile", action="append", default=[])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    expected_profiles = tuple(args.expected_profile) or DEFAULT_EXPECTED_PROFILES
    report = build_evidence_bundle(
        vault,
        reports_dir=args.reports_dir,
        reports=list(args.report) or None,
        expected_profiles=expected_profiles,
        policy_path=args.policy,
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    if report["status"] != "pass":
        print(json.dumps(_cli_failure_summary(vault, report, destination), ensure_ascii=False, indent=2))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
