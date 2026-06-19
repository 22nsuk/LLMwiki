#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, TypedDict

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.release_authority_state_runtime import (
        release_status_v2_view_with_readiness_fallback,
    )
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_runtime import (
        load_schema_with_vault_override,
        validate_with_schema,
    )
    from ops.scripts.core.source_revision_runtime import resolve_source_revision
    from ops.scripts.core.source_tree_fingerprint_runtime import (
        release_source_tree_change_sample,
        release_source_tree_fingerprint,
    )
else:
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.release_authority_state_runtime import (
        release_status_v2_view_with_readiness_fallback,
    )
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_runtime import (
        load_schema_with_vault_override,
        validate_with_schema,
    )
    from ops.scripts.core.source_revision_runtime import resolve_source_revision
    from ops.scripts.core.source_tree_fingerprint_runtime import (
        release_source_tree_change_sample,
        release_source_tree_fingerprint,
    )


DEFAULT_OUT = "build/release/release-run-manifest.json"
SCHEMA_PATH = "ops/schemas/release-run-manifest.schema.json"
PRODUCER = "ops.scripts.release_run_manifest"
SOURCE_COMMAND = "python -m ops.scripts.release_run_manifest --vault ."
DEFAULT_DISTRIBUTION_ZIP = "build/release/LLMwiki-source.zip"
DEFAULT_SOURCE_PACKAGE_SMOKE = "build/source-package-smoke/source-package-smoke.json"
DEFAULT_CLOSEOUT_SUMMARY = "ops/reports/release-closeout-summary.json"
SCHEMA_VERSION = 5
SAFE_VAULT_RELATIVE_PATH_RE = re.compile(
    r"^(?!/)(?!.*//)(?!.*(?:^|/)\.\.?(?:/|$))[A-Za-z0-9._+/-]+$"
)


class _StepDurationRow(TypedDict):
    name: str
    status: str
    duration_ms: int


def _run_git(vault: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=vault,
        check=False,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def git_commit(vault: Path) -> str:
    return resolve_source_revision(vault).revision


def git_clean(vault: Path) -> bool:
    return _run_git(vault, "status", "--porcelain") == ""


def remote_sync(vault: Path) -> dict[str, Any]:
    upstream = _run_git(vault, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if not upstream:
        return {"status": "unknown", "upstream": "", "ahead": 0, "behind": 0}
    counts = _run_git(vault, "rev-list", "--left-right", "--count", "HEAD...@{u}").split()
    ahead = int(counts[0]) if len(counts) == 2 and counts[0].isdigit() else 0
    behind = int(counts[1]) if len(counts) == 2 and counts[1].isdigit() else 0
    return {
        "status": "pass" if ahead == 0 and behind == 0 else "fail",
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
    }


def ignored_tracked_file_count(vault: Path) -> int:
    output = _run_git(vault, "ls-files", "-ci", "--exclude-standard")
    return len([line for line in output.splitlines() if line.strip()])


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(vault: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (vault / path).resolve()


def _file_identity(vault: Path, path_value: str | Path) -> dict[str, Any]:
    path = _resolve(vault, path_value)
    exists = path.is_file()
    return {
        "path": display_path(vault, path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else 0,
        "sha256": _sha256_file(path) if exists else "",
    }


def _safe_vault_relative_path(vault: Path, path_value: object) -> str:
    raw_text = str(path_value).strip()
    if not raw_text or "\\" in raw_text:
        return ""
    if not SAFE_VAULT_RELATIVE_PATH_RE.fullmatch(raw_text):
        return ""
    rel_path = PurePosixPath(raw_text)
    if rel_path.is_absolute() or any(part in {"", ".", ".."} for part in rel_path.parts):
        return ""
    resolved = (vault / Path(*rel_path.parts)).resolve()
    try:
        resolved.relative_to(vault.resolve())
    except ValueError:
        return ""
    return rel_path.as_posix()


def _loaded_run_manifest_identity(vault: Path, manifest_path: str | Path) -> dict[str, Any]:
    identity = _file_identity(vault, manifest_path)
    payload, diagnostics = load_optional_json_object_with_diagnostics(_resolve(vault, manifest_path))
    load_status = str(diagnostics.get("status", "unknown")).strip() or "unknown"
    if load_status != "ok" or not isinstance(payload, dict):
        payload = {}
    schema_errors = (
        validate_with_schema(payload, load_schema_with_vault_override(vault, SCHEMA_PATH))
        if load_status == "ok"
        else []
    )
    return {
        **identity,
        "load_status": load_status,
        "schema_valid": not schema_errors,
        "artifact_kind": str(payload.get("artifact_kind", "")).strip(),
        "status": _status_label(payload.get("status")),
        "source_revision": str(payload.get("source_revision", "")).strip(),
        "source_tree_fingerprint": str(
            payload.get("final_source_tree_fingerprint")
            or payload.get("source_tree_fingerprint")
            or ""
        ).strip(),
        "artifact_status": str(payload.get("artifact_status", "")).strip(),
        "currentness_status": str(
            payload.get("currentness", {}).get("status", "")
            if isinstance(payload.get("currentness"), dict)
            else ""
        ).strip(),
    }


def run_manifest_alignment(
    vault: Path,
    manifest_path: str | Path = DEFAULT_OUT,
    *,
    current_revision: str | None = None,
    current_source_tree_fingerprint: str | None = None,
) -> dict[str, Any]:
    current_revision = current_revision if current_revision is not None else git_commit(vault)
    current_source_tree_fingerprint = (
        current_source_tree_fingerprint
        if current_source_tree_fingerprint is not None
        else release_source_tree_fingerprint(vault)
    )
    identity = _loaded_run_manifest_identity(vault, manifest_path)
    issues: list[str] = []
    if identity["load_status"] != "ok":
        issues.append("not_loadable")
    if identity["load_status"] == "ok" and not identity["schema_valid"]:
        issues.append("schema_invalid")
    if identity["artifact_kind"] and identity["artifact_kind"] != "release_run_manifest":
        issues.append("artifact_kind_mismatch")
    if identity["artifact_status"] and identity["artifact_status"] != "current":
        issues.append("artifact_status_not_current")
    if identity["currentness_status"] and identity["currentness_status"] != "current":
        issues.append("currentness_not_current")
    if identity["status"] and identity["status"] != "pass":
        issues.append("not_pass")
    if identity["source_revision"] and identity["source_revision"] != current_revision:
        issues.append("source_revision_stale")
    if (
        identity["source_tree_fingerprint"]
        and identity["source_tree_fingerprint"] != current_source_tree_fingerprint
    ):
        issues.append("source_tree_fingerprint_stale")
    if identity["load_status"] == "ok" and not identity["source_tree_fingerprint"]:
        issues.append("source_tree_fingerprint_missing")
    alignment_status = "current" if not issues else "stale"
    if not identity["exists"]:
        alignment_status = "missing"
    return {
        "path": identity["path"],
        "exists": identity["exists"],
        "load_status": identity["load_status"],
        "artifact_kind": identity["artifact_kind"],
        "status": identity["status"],
        "artifact_status": identity["artifact_status"],
        "currentness_status": identity["currentness_status"],
        "source_revision": identity["source_revision"],
        "current_source_revision": current_revision,
        "source_tree_fingerprint": identity["source_tree_fingerprint"],
        "current_source_tree_fingerprint": current_source_tree_fingerprint,
        "input_fingerprint": identity["sha256"] or current_source_tree_fingerprint,
        "alignment_status": alignment_status,
        "issues": _unique_failures(issues),
        "recommended_next_target": "release-run-ready",
    }


def _status_label(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(value.get("result", "")).strip()
    return str(value).strip()


def _source_package_smoke(vault: Path, path_value: str) -> dict[str, Any]:
    identity = _file_identity(vault, path_value)
    payload, diagnostics = load_optional_json_object_with_diagnostics(_resolve(vault, path_value))
    if diagnostics.get("status") != "ok":
        payload = {}
    source_zip = payload.get("source_zip") if isinstance(payload, dict) else {}
    source_zip = source_zip if isinstance(source_zip, dict) else {}
    input_fingerprints = payload.get("input_fingerprints") if isinstance(payload, dict) else {}
    input_fingerprints = input_fingerprints if isinstance(input_fingerprints, dict) else {}
    source_zip_sha256 = str(source_zip.get("sha256") or "").strip()
    source_zip_input_sha256 = str(input_fingerprints.get("source_zip") or "").strip()
    return {
        "path": identity["path"],
        "exists": identity["exists"],
        "status": _status_label(payload.get("status")),
        "sha256": identity["sha256"],
        "source_zip_sha256": source_zip_sha256 or source_zip_input_sha256,
        "_source_zip_input_sha256": source_zip_input_sha256,
    }


def _unique_failures(failures: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for failure in failures:
        if failure and failure not in seen:
            seen.add(failure)
            result.append(failure)
    return result


def _closeout_authority_axes(vault: Path, closeout_summary: str) -> dict[str, Any]:
    path = _resolve(vault, closeout_summary)
    payload, diagnostics = load_optional_json_object_with_diagnostics(path)
    if diagnostics.get("status") != "ok" or not isinstance(payload, dict):
        return {
            "release_authority_status": "unknown",
            "machine_release_allowed": False,
        }
    status_view = release_status_v2_view_with_readiness_fallback(payload)
    return {
        "release_authority_status": str(status_view.get("release_authority_status", "unknown")).strip(),
        "machine_release_allowed": bool(payload.get("machine_release_allowed", False)),
    }


def _share_of_total(duration_ms: int, total_duration_ms: int) -> float:
    if total_duration_ms <= 0:
        return 0.0
    return round(duration_ms / total_duration_ms, 6)


def _step_group(name: str) -> str:
    mapping = {
        "release-test-current": "test",
        "release-public-current": "public",
        "release-smoke-full-reuse": "smoke",
        "release-source-package-check": "source_package",
    }
    return mapping.get(name, "other")


def _step_duration_summary(steps: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_steps: list[_StepDurationRow] = [
        {
            "name": str(step.get("name", "unknown")).strip() or "unknown",
            "status": str(step.get("status", "unknown")).strip() or "unknown",
            "duration_ms": max(0, int(step.get("duration_ms", 0) or 0)),
        }
        for step in steps
    ]
    total_duration_ms = sum(step["duration_ms"] for step in normalized_steps)
    ordered_steps = sorted(
        normalized_steps,
        key=lambda item: (-item["duration_ms"], item["name"]),
    )
    slowest: _StepDurationRow = (
        ordered_steps[0]
        if ordered_steps
        else {"name": "", "status": "not_run", "duration_ms": 0}
    )
    grouped: dict[str, list[_StepDurationRow]] = {
        "test": [],
        "public": [],
        "smoke": [],
        "source_package": [],
        "other": [],
    }
    for step in normalized_steps:
        grouped[_step_group(step["name"])].append(step)

    def group_summary(items: list[_StepDurationRow]) -> dict[str, Any]:
        ordered = sorted(items, key=lambda item: (-item["duration_ms"], item["name"]))
        total = sum(item["duration_ms"] for item in items)
        slowest_name = ordered[0]["name"] if ordered else ""
        return {
            "matched_step_count": len(items),
            "total_duration_ms": total,
            "slowest_step_name": slowest_name,
            "share_of_total": _share_of_total(total, total_duration_ms),
        }

    return {
        "total_duration_ms": total_duration_ms,
        "step_count": len(normalized_steps),
        "passed_step_count": sum(1 for step in normalized_steps if step["status"] == "pass"),
        "failed_step_count": sum(1 for step in normalized_steps if step["status"] == "fail"),
        "slowest_step": {
            "name": slowest["name"],
            "status": slowest["status"],
            "duration_ms": slowest["duration_ms"],
            "share_of_total": _share_of_total(slowest["duration_ms"], total_duration_ms),
        },
        "steps_by_duration_desc": [
            {
                "name": step["name"],
                "status": step["status"],
                "duration_ms": step["duration_ms"],
                "share_of_total": _share_of_total(step["duration_ms"], total_duration_ms),
            }
            for step in ordered_steps
        ],
        "comparison_groups": {
            key: group_summary(grouped[key])
            for key in ("test", "public", "smoke", "source_package")
        },
    }


def build_manifest(
    vault: Path,
    *,
    expected_source_tree_fingerprint: str,
    steps: list[dict[str, Any]] | None = None,
    distribution_zip: str = DEFAULT_DISTRIBUTION_ZIP,
    source_package_smoke: str = DEFAULT_SOURCE_PACKAGE_SMOKE,
    closeout_summary: str = DEFAULT_CLOSEOUT_SUMMARY,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    final_fingerprint = release_source_tree_fingerprint(vault)
    commit = git_commit(vault)
    clean = git_clean(vault)
    remote = remote_sync(vault)
    ignored_count = ignored_tracked_file_count(vault)
    step_rows = list(steps or [])
    zip_identity = _file_identity(vault, distribution_zip)
    smoke = _source_package_smoke(vault, source_package_smoke)
    authority_axes = _closeout_authority_axes(vault, closeout_summary)
    failures: list[str] = []
    if expected_source_tree_fingerprint != final_fingerprint:
        failures.append("source_tree_fingerprint_drift")
    if not clean:
        failures.append("git_worktree_dirty")
    if ignored_count != 0:
        failures.append("ignored_tracked_files_present")
    if not zip_identity["exists"]:
        failures.append("distribution_zip_missing")
    if not _safe_vault_relative_path(vault, zip_identity["path"]):
        failures.append("distribution_zip_path_not_vault_relative")
    if not smoke["exists"] or smoke["status"] != "pass":
        failures.append("source_package_smoke_not_pass")
    smoke_source_zip_sha256 = str(smoke["source_zip_sha256"])
    smoke_source_zip_input_sha256 = str(smoke.get("_source_zip_input_sha256", ""))
    if not smoke_source_zip_sha256:
        failures.append("source_package_smoke_source_zip_fingerprint_missing")
    elif (
        smoke_source_zip_input_sha256
        and smoke_source_zip_input_sha256 != smoke_source_zip_sha256
    ):
        failures.append("source_package_smoke_source_zip_fingerprint_mismatch")
    elif zip_identity["sha256"] != smoke_source_zip_sha256:
        failures.append("source_package_smoke_source_zip_mismatch")
    failures.extend(
        f"step_failed:{step.get('name', 'unknown')}"
        for step in step_rows
        if step.get("status") != "pass"
    )
    status = "pass" if not failures else "fail"
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "release_run_manifest",
        "generated_at": generated_at,
        "producer": PRODUCER,
        "source_command": SOURCE_COMMAND,
        "source_revision": commit,
        "source_tree_fingerprint": final_fingerprint,
        "input_fingerprints": {
            "distribution_zip": zip_identity["sha256"],
            "source_package_smoke": smoke["sha256"],
            "source_package_smoke_source_zip": smoke_source_zip_sha256,
        },
        "schema_version": SCHEMA_VERSION,
        "artifact_status": "current",
        "retention_policy": "release_sidecar_authority",
        "encoding": "utf-8",
        "currentness": {"status": "current", "checked_at": generated_at},
        "status": status,
        "release_authority_status": authority_axes["release_authority_status"],
        "machine_release_allowed": authority_axes["machine_release_allowed"],
        "expected_source_tree_fingerprint": expected_source_tree_fingerprint,
        "final_source_tree_fingerprint": final_fingerprint,
        "git_commit": commit,
        "git_clean": clean,
        "remote_sync": remote,
        "ignored_tracked_file_count": ignored_count,
        "steps": step_rows,
        "step_duration_summary": _step_duration_summary(step_rows),
        "distribution_zip": zip_identity,
        "source_package_smoke": {
            "path": smoke["path"],
            "exists": smoke["exists"],
            "status": smoke["status"],
            "sha256": smoke["sha256"],
            "source_zip_sha256": smoke_source_zip_sha256,
        },
        "failures": _unique_failures(failures),
    }


def write_manifest(vault: Path, manifest: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=manifest,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release-run manifest schema validation failed",
        )
    )


def load_steps(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("steps JSON must be an array")
    return [item for item in payload if isinstance(item, dict)]


def distribution_zip_path_from_manifest(vault: Path, manifest_path: str) -> str:
    payload, diagnostics = load_optional_json_object_with_diagnostics(_resolve(vault, manifest_path))
    if diagnostics.get("status") != "ok" or not isinstance(payload, dict):
        return ""
    schema_errors = validate_with_schema(payload, load_schema_with_vault_override(vault, SCHEMA_PATH))
    if schema_errors:
        return ""
    distribution_zip = payload.get("distribution_zip")
    if not isinstance(distribution_zip, dict):
        return ""
    return _safe_vault_relative_path(vault, distribution_zip.get("path", ""))


def _input_fingerprints(payload: dict[str, Any]) -> dict[str, str]:
    input_fingerprints = payload.get("input_fingerprints")
    if not isinstance(input_fingerprints, dict):
        return {}
    return {str(key): str(value) for key, value in input_fingerprints.items()}


def _check_manifest(previous_payload: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    failures = [str(item) for item in manifest.get("failures", []) if str(item)]
    if _input_fingerprints(previous_payload) != _input_fingerprints(manifest):
        failures.append("release_run_manifest_input_fingerprint_drift")
    return {
        **manifest,
        "status": "pass" if not failures else "fail",
        "failures": _unique_failures(failures),
    }


def _input_fingerprint_drift_line(
    previous_payload: dict[str, Any],
    manifest: dict[str, Any],
) -> str:
    return (
        "input_fingerprint_drift=expected:"
        + json.dumps(_input_fingerprints(previous_payload), sort_keys=True)
        + ";current:"
        + json.dumps(_input_fingerprints(manifest), sort_keys=True)
    )


def _check_failure_diagnostics(
    vault: Path,
    *,
    previous_payload: dict[str, Any],
    manifest: dict[str, Any],
) -> list[str]:
    failures = [str(item) for item in manifest.get("failures", [])]
    if not failures:
        return []
    lines = [
        f"release_run_manifest_status={manifest.get('status', '')}",
        "failures=" + ",".join(failures),
    ]
    if "source_tree_fingerprint_drift" not in failures:
        if "release_run_manifest_input_fingerprint_drift" in failures:
            lines.append(_input_fingerprint_drift_line(previous_payload, manifest))
        return lines
    generated_at = str(previous_payload.get("generated_at", "")).strip()
    change_sample = release_source_tree_change_sample(
        vault,
        generated_at=generated_at,
    ) if generated_at else {
        "changed_after_generated_at_count": 0,
        "changed_after_generated_at_path_limit": 0,
        "changed_after_generated_at": [],
    }
    changed_items = change_sample.get("changed_after_generated_at", [])
    if not isinstance(changed_items, list):
        changed_items = []
    changed_paths = [
        f"{item['path']}@{item['mtime']}"
        for item in changed_items
        if isinstance(item, dict)
    ]
    lines.extend(
        [
            "source_tree_fingerprint_drift="
            f"expected:{manifest.get('expected_source_tree_fingerprint', '')};"
            f"current:{manifest.get('final_source_tree_fingerprint', '')}",
            "minimal_remediation_target=release-run-ready",
            "changed_after_generated_at_count="
            f"{change_sample.get('changed_after_generated_at_count', 0)}",
        ]
    )
    if changed_paths:
        lines.append("changed_after_generated_at=" + ",".join(changed_paths))
    if "release_run_manifest_input_fingerprint_drift" in failures:
        lines.append(_input_fingerprint_drift_line(previous_payload, manifest))
    return lines


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or verify the release-run manifest.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--expected-source-tree-fingerprint", default="")
    parser.add_argument("--steps-json")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--distribution-zip", default=DEFAULT_DISTRIBUTION_ZIP)
    parser.add_argument("--source-package-smoke", default=DEFAULT_SOURCE_PACKAGE_SMOKE)
    parser.add_argument("--closeout-summary", default=DEFAULT_CLOSEOUT_SUMMARY)
    parser.add_argument("--print-distribution-zip", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    previous_payload: dict[str, Any] = {}
    if args.print_distribution_zip:
        distribution_zip_path = distribution_zip_path_from_manifest(vault, args.out)
        if distribution_zip_path:
            print(distribution_zip_path)
            return 0
        return 1
    if args.check:
        payload, diagnostics = load_optional_json_object_with_diagnostics(_resolve(vault, args.out))
        if diagnostics.get("status") != "ok":
            print(json.dumps({"status": "fail", "reason": diagnostics}, ensure_ascii=False, indent=2))
            return 1
        schema_errors = validate_with_schema(payload, load_schema_with_vault_override(vault, SCHEMA_PATH))
        if schema_errors:
            print(
                json.dumps(
                    {"status": "fail", "reason": {"schema_errors": schema_errors}},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
        previous_payload = payload
        expected = str(payload.get("expected_source_tree_fingerprint", "")).strip()
        steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    else:
        expected = args.expected_source_tree_fingerprint or release_source_tree_fingerprint(vault)
        steps = load_steps(args.steps_json)
    manifest = build_manifest(
        vault,
        expected_source_tree_fingerprint=expected,
        steps=steps,
        distribution_zip=args.distribution_zip,
        source_package_smoke=args.source_package_smoke,
        closeout_summary=args.closeout_summary,
    )
    if args.check:
        manifest = _check_manifest(previous_payload, manifest)
        print(display_path(vault, _resolve(vault, args.out)))
        for line in _check_failure_diagnostics(
            vault,
            previous_payload=previous_payload,
            manifest=manifest,
        ):
            print(line)
        return 0 if manifest["status"] == "pass" else 1
    path = write_manifest(vault, manifest, args.out)
    print(display_path(vault, path))
    return 0 if manifest["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover - direct script fallback
    raise SystemExit(main())
