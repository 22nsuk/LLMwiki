#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.command_runtime import run_with_timeout
    from ops.scripts.output_runtime import display_path, sanitize_report_text
    from ops.scripts.release.release_run_manifest import (
        _file_identity,
        _resolve,
        build_manifest,
        git_clean,
        git_commit,
        ignored_tracked_file_count,
        remote_sync,
        run_manifest_alignment,
        write_manifest,
    )
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_runtime import (
        load_schema_with_vault_override,
        validate_with_schema,
    )
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
else:
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.command_runtime import run_with_timeout
    from ops.scripts.output_runtime import display_path, sanitize_report_text
    from ops.scripts.release.release_run_manifest import (
        _file_identity,
        _resolve,
        build_manifest,
        git_clean,
        git_commit,
        ignored_tracked_file_count,
        remote_sync,
        run_manifest_alignment,
        write_manifest,
    )
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_runtime import (
        load_schema_with_vault_override,
        validate_with_schema,
    )
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )


DEFAULT_OUT = "build/release/release-run-manifest.json"
DEFAULT_PLAN_OUT = "build/release/release-run-ready-plan.json"
PLAN_SCHEMA_PATH = "ops/schemas/release-run-ready-plan.schema.json"
DEFAULT_TIMEOUT_SECONDS = 7200
PLAN_SOURCE_COMMAND = "python -m ops.scripts.release_run_ready --vault . --plan"


@dataclass(frozen=True)
class RunReadyPlanSpec:
    name: str
    path: str
    expected_artifact_kind: str
    schema_path: str
    expected_producer: str
    stage: str
    cost_class: str
    check_target: str
    refresh_target: str
    require_pass: bool = True
    expected_source_command: str = ""
    expected_profile: str = ""
    expected_suite: str = ""
    require_full_suite: bool = False
    referenced_file_field: str = ""


PLAN_SPECS = (
    RunReadyPlanSpec(
        "test_execution_summary_full",
        "ops/reports/test-execution-summary-full.json",
        "test_execution_summary",
        "ops/schemas/test-execution-summary.schema.json",
        "ops.scripts.test_execution_summary",
        "release-test-current",
        "expensive",
        "test-execution-summary-full-current-check",
        "test-execution-summary-full-current-or-refresh",
        expected_suite="full",
        require_full_suite=True,
    ),
    RunReadyPlanSpec(
        "test_execution_summary_report_contract",
        "ops/reports/test-execution-summary.json",
        "test_execution_summary",
        "ops/schemas/test-execution-summary.schema.json",
        "ops.scripts.test_execution_summary",
        "release-test-current",
        "medium",
        "test-execution-summary-current-check",
        "test-execution-summary-current-or-refresh",
        expected_suite="report-contract-summary",
    ),
    RunReadyPlanSpec(
        "public_check_summary",
        "ops/reports/public-check-summary.json",
        "public_check_summary",
        "ops/schemas/public-check-summary.schema.json",
        "ops.scripts.public_check_summary",
        "release-public-current",
        "medium",
        "public-check-summary-current-check",
        "public-check-summary-current-or-refresh",
        expected_source_command="python -m ops.scripts.public_check_summary --vault .",
    ),
    RunReadyPlanSpec(
        "release_smoke_full",
        "ops/reports/release-smoke-report.json",
        "release_smoke_report",
        "ops/schemas/release-smoke-report.schema.json",
        "ops.scripts.release_smoke",
        "release-smoke-full-reuse",
        "expensive",
        "release-smoke-full-current-check",
        "release-smoke-full-reuse",
        expected_source_command="python -m ops.scripts.release.release_smoke --vault . --profile full",
        expected_profile="full",
    ),
    RunReadyPlanSpec(
        "release_distribution_zip_smoke",
        "build/release/release-distribution-zip-smoke.json",
        "release_smoke_report",
        "ops/schemas/release-smoke-report.schema.json",
        "ops.scripts.release_smoke",
        "release-source-package-check",
        "medium",
        "release-package-current-check",
        "release-package-current-or-refresh",
        expected_source_command="python -m ops.scripts.release.release_smoke --vault . --profile fast",
        expected_profile="fast",
        referenced_file_field="archive_file",
    ),
    RunReadyPlanSpec(
        "source_package_smoke",
        "build/source-package-smoke/source-package-smoke.json",
        "source_package_smoke",
        "ops/schemas/source-package-smoke.schema.json",
        "ops.scripts.source_package_smoke",
        "release-source-package-check",
        "medium",
        "release-source-package-smoke-current-check",
        "release-source-package-smoke-current-or-refresh",
        expected_source_command="python -m ops.scripts.source_package_smoke --vault .",
        referenced_file_field="source_zip",
    ),
    RunReadyPlanSpec(
        "source_package_clean_extract",
        "ops/reports/source-package-clean-extract.json",
        "source_package_clean_extract",
        "ops/schemas/source-package-clean-extract.schema.json",
        "ops.scripts.source_package_clean_extract",
        "release-source-package-check",
        "medium",
        "release-source-package-clean-extract-current-check",
        "release-source-package-clean-extract-current-or-refresh",
        expected_source_command="python -m ops.scripts.source_package_clean_extract --vault .",
        referenced_file_field="source_zip",
    ),
)


def _tail(text: str, *, limit: int = 4000) -> str:
    return text if len(text) <= limit else text[-limit:]


def _summary_mode(name: str, *, stdout_tail: str, stderr_tail: str) -> str:
    combined = f"{stdout_tail}\n{stderr_tail}"
    if name == "release-public-current":
        return (
            "reused"
            if "public check summary is current; reused" in combined
            else "executed"
        )
    if name == "release-smoke-full-reuse":
        return (
            "reused"
            if '"summary_mode": "reused"' in combined or "reused_from=" in combined
            else "executed"
        )
    if name == "release-source-package-check":
        required_signals = (
            "release distribution zip evidence is current; reused",
            "source package smoke evidence is current; reused",
            "source package clean extract evidence is current; reused",
        )
        return "reused" if all(signal in combined for signal in required_signals) else "executed"
    return "executed"


def _command_step(
    *,
    vault: Path,
    name: str,
    command: list[str],
    expected_fingerprint: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    before = release_source_tree_fingerprint(vault)
    started = time.monotonic()
    result = run_with_timeout(command, cwd=vault, timeout_seconds=timeout_seconds)
    after = release_source_tree_fingerprint(vault)
    status = "pass" if result.returncode == 0 and not result.timed_out and after == expected_fingerprint else "fail"
    stdout_tail = sanitize_report_text(vault, _tail(result.stdout))
    stderr_tail = sanitize_report_text(vault, _tail(result.stderr))
    return {
        "name": name,
        "status": status,
        "summary_mode": _summary_mode(name, stdout_tail=stdout_tail, stderr_tail=stderr_tail),
        "command": [sanitize_report_text(vault, item) for item in command],
        "returncode": result.returncode,
        "duration_ms": int(round((time.monotonic() - started) * 1000)),
        "source_tree_fingerprint_before": before,
        "source_tree_fingerprint_after": after,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }


def _synthetic_preflight(vault: Path, expected_fingerprint: str) -> dict[str, Any]:
    fingerprint = release_source_tree_fingerprint(vault)
    remote = remote_sync(vault)
    clean = git_clean(vault)
    ignored_count = ignored_tracked_file_count(vault)
    status = (
        "pass"
        if fingerprint == expected_fingerprint
        and clean
        and ignored_count == 0
        else "fail"
    )
    return {
        "name": "release-preflight-current",
        "status": status,
        "summary_mode": "executed",
        "command": [],
        "returncode": 0 if status == "pass" else 1,
        "duration_ms": 0,
        "source_tree_fingerprint_before": fingerprint,
        "source_tree_fingerprint_after": fingerprint,
        "stdout_tail": (
            f"git_clean={clean}; remote_sync={remote['status']}; "
            f"ignored_tracked_file_count={ignored_count}"
        ),
        "stderr_tail": "",
    }


def _release_steps(make_bin: str) -> list[tuple[str, list[str]]]:
    return [
        ("release-test-current", [make_bin, "release-test-current"]),
        ("release-public-current", [make_bin, "release-public-current"]),
        ("release-smoke-full-reuse", [make_bin, "release-smoke-full-reuse"]),
        ("release-source-package-check", [make_bin, "release-source-package-check"]),
    ]


def _unique_issue_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _revision_is_current(observed: str, current_revision: str) -> bool:
    if not observed:
        return True
    return observed in {current_revision, "source_package_without_git"}


def _payload_status(payload: dict[str, Any]) -> str:
    value = payload.get("status")
    if isinstance(value, dict):
        return str(value.get("result", "")).strip()
    return str(value or "").strip()


def _schema_errors_for_payload(
    vault: Path,
    *,
    schema_path: str,
    payload: dict[str, Any],
) -> list[str]:
    schema = load_schema_with_vault_override(vault, schema_path)
    return validate_with_schema(payload, schema)


def _currentness_status(payload: dict[str, Any]) -> str:
    currentness = payload.get("currentness")
    currentness = currentness if isinstance(currentness, dict) else {}
    return str(currentness.get("status", "")).strip()


def _referenced_file_is_current(vault: Path, payload: dict[str, Any], field: str) -> bool:
    if not field:
        return True
    reference = payload.get(field)
    if not isinstance(reference, dict) or reference.get("exists") is not True:
        return False
    path_text = str(reference.get("path", "")).strip()
    sha256 = str(reference.get("sha256", "")).strip()
    if not path_text or not sha256:
        return False
    if Path(path_text).is_absolute():
        return False
    identity = _file_identity(vault, path_text)
    return bool(identity["exists"]) and identity["sha256"] == sha256


def _semantic_plan_issues(
    vault: Path,
    *,
    spec: RunReadyPlanSpec,
    payload: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    if str(payload.get("producer", "")).strip() != spec.expected_producer:
        issues.append("producer_mismatch")
    if spec.expected_source_command and str(payload.get("source_command", "")).strip() != spec.expected_source_command:
        issues.append("source_command_mismatch")
    if _currentness_status(payload) != "current":
        issues.append("currentness_not_current")
    if str(payload.get("artifact_status", "")).strip() != "current":
        issues.append("artifact_status_not_current")
    input_fingerprints = payload.get("input_fingerprints")
    if not isinstance(input_fingerprints, dict) or not input_fingerprints:
        issues.append("input_fingerprints_missing")
    if spec.expected_profile and str(payload.get("profile", "")).strip() != spec.expected_profile:
        issues.append("profile_mismatch")
    if spec.expected_suite and str(payload.get("suite", "")).strip() != spec.expected_suite:
        issues.append("suite_mismatch")
    if spec.require_full_suite and not bool(payload.get("represents_full_suite")):
        issues.append("full_suite_evidence_missing")
    summary = payload.get("summary")
    if spec.name == "public_check_summary":
        summary = summary if isinstance(summary, dict) else {}
        if str(summary.get("public_check_status", "")).strip() != "pass":
            issues.append("summary_status_mismatch")
    if not _referenced_file_is_current(vault, payload, spec.referenced_file_field):
        issues.append("referenced_file_stale")
    return issues


def _json_plan_node(
    vault: Path,
    *,
    spec: RunReadyPlanSpec,
    current_fingerprint: str,
    current_revision: str,
) -> dict[str, Any]:
    identity = _file_identity(vault, spec.path)
    payload, diagnostics = load_optional_json_object_with_diagnostics(_resolve(vault, spec.path))
    if diagnostics.get("status") != "ok":
        payload = {}
    artifact_kind = str(payload.get("artifact_kind", "")).strip()
    status = _payload_status(payload)
    source_tree_fingerprint = str(payload.get("source_tree_fingerprint", "")).strip()
    source_revision = str(payload.get("source_revision", "")).strip()
    issues: list[str] = []
    if diagnostics.get("status") != "ok":
        issues.append("not_loadable")
    elif _schema_errors_for_payload(vault, schema_path=spec.schema_path, payload=payload):
        issues.append("schema_invalid")
    if artifact_kind != spec.expected_artifact_kind:
        issues.append("artifact_kind_mismatch")
    if diagnostics.get("status") == "ok":
        issues.extend(_semantic_plan_issues(vault, spec=spec, payload=payload))
    if source_tree_fingerprint != current_fingerprint:
        issues.append("source_tree_fingerprint_stale")
    if not _revision_is_current(source_revision, current_revision):
        issues.append("source_revision_stale")
    if spec.require_pass and status != "pass":
        issues.append("not_pass")
    issues = _unique_issue_values(issues)
    return {
        "name": spec.name,
        "path": identity["path"],
        "stage": spec.stage,
        "cost_class": spec.cost_class,
        "check_target": spec.check_target,
        "refresh_target": spec.refresh_target,
        "expected_artifact_kind": spec.expected_artifact_kind,
        "load_status": str(diagnostics.get("status", "")),
        "artifact_kind": artifact_kind,
        "status": status,
        "source_revision": source_revision,
        "source_tree_fingerprint": source_tree_fingerprint,
        "input_fingerprint": identity["sha256"],
        "can_reuse": not issues,
        "issues": issues,
    }


def _preflight_plan_node(
    vault: Path,
    *,
    current_fingerprint: str,
    current_revision: str,
) -> dict[str, Any]:
    clean = git_clean(vault)
    remote = remote_sync(vault)
    ignored_count = ignored_tracked_file_count(vault)
    issues: list[str] = []
    if not clean:
        issues.append("git_worktree_dirty")
    if ignored_count != 0:
        issues.append("ignored_tracked_files_present")
    return {
        "name": "release_preflight",
        "path": ".",
        "stage": "release-preflight-current",
        "cost_class": "cheap",
        "check_target": "release-worktree-clean-check",
        "refresh_target": "release-worktree-clean-check",
        "expected_artifact_kind": "git_worktree",
        "load_status": "ok",
        "artifact_kind": "git_worktree",
        "status": "pass" if not issues else "fail",
        "source_revision": current_revision,
        "source_tree_fingerprint": current_fingerprint,
        "input_fingerprint": current_fingerprint,
        "can_reuse": not issues,
        "issues": issues,
        "diagnostics": {
            "git_clean": clean,
            "ignored_tracked_file_count": ignored_count,
            "remote_sync": remote,
        },
    }


def _plan_cause(node: dict[str, Any]) -> dict[str, Any]:
    issues = [str(issue) for issue in node.get("issues", [])]
    issue_text = ",".join(issues) or "none"
    return {
        "id": f"{node['name']}_not_reusable",
        "node": str(node["name"]),
        "path": str(node["path"]),
        "issues": issues,
        "summary": (
            f"{node['name']} is not reusable for release-run-ready because "
            f"{issue_text}."
        ),
        "minimal_next_target": str(node["refresh_target"]),
        "cost_class": str(node["cost_class"]),
        "handoff_class": "local_evidence_refresh"
        if str(node["name"]) != "release_preflight"
        else "codehealth_source_fix",
    }


def _authority_manifest_cause(alignment: dict[str, Any]) -> dict[str, Any]:
    issues = [str(issue) for issue in alignment.get("issues", [])]
    issue_text = ",".join(issues) or str(alignment.get("alignment_status", "not_current"))
    return {
        "id": "authority_manifest_not_current",
        "node": "authority_manifest",
        "path": str(alignment.get("path", DEFAULT_OUT)),
        "issues": issues or [issue_text],
        "summary": (
            "build/release/release-run-manifest.json is not current for "
            f"release-run-ready because {issue_text}."
        ),
        "minimal_next_target": "release-run-ready",
        "cost_class": "expensive",
        "handoff_class": "local_evidence_refresh",
    }


def build_run_ready_plan(
    vault: Path,
    *,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    fingerprint = release_source_tree_fingerprint(vault)
    revision = git_commit(vault)
    nodes = [
        _preflight_plan_node(
            vault,
            current_fingerprint=fingerprint,
            current_revision=revision,
        )
    ]
    nodes.extend(
        _json_plan_node(
            vault,
            spec=spec,
            current_fingerprint=fingerprint,
            current_revision=revision,
        )
        for spec in PLAN_SPECS
    )
    authority_alignment = run_manifest_alignment(
        vault,
        DEFAULT_OUT,
        current_revision=revision,
        current_source_tree_fingerprint=fingerprint,
    )
    causes = [_plan_cause(node) for node in nodes if not node["can_reuse"]]
    if authority_alignment["alignment_status"] != "current":
        causes.append(_authority_manifest_cause(authority_alignment))
    minimal_next_target = str(causes[0]["minimal_next_target"]) if causes else ""
    plan_status = "ready" if not causes else "blocked"
    return {
        "$schema": PLAN_SCHEMA_PATH,
        "artifact_kind": "release_run_ready_plan",
        "generated_at": generated_at,
        "producer": "ops.scripts.release_run_ready",
        "source_command": PLAN_SOURCE_COMMAND,
        "source_revision": revision,
        "source_tree_fingerprint": fingerprint,
        "input_fingerprints": {
            **{
                str(node["name"]): str(node["input_fingerprint"])
                for node in nodes
            },
            "authority_manifest": str(authority_alignment["input_fingerprint"]),
        },
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "release_sidecar_diagnostic",
        "encoding": "utf-8",
        "currentness": {"status": "current", "checked_at": generated_at},
        "plan_status": plan_status,
        "execution_mode": "run_ready_preflight_plan_only",
        "minimal_next_target": minimal_next_target,
        "nodes": nodes,
        "authority_manifest_alignment": authority_alignment,
        "stale_evidence_causes": causes,
        "boundary": {
            "local_only_generated_artifacts_not_promoted": True,
            "ignored_evidence_refresh_lane": "release-evidence-sync/full-vault",
            "authority_manifest": DEFAULT_OUT,
        },
    }


def write_run_ready_plan(vault: Path, plan: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=plan,
            schema_path=PLAN_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_PLAN_OUT,
            context="release-run-ready plan schema validation failed",
        )
    )


def run_release_ready(
    *,
    vault: Path,
    out_path: str,
    make_bin: str,
    timeout_seconds: int,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    expected = release_source_tree_fingerprint(vault)
    steps: list[dict[str, Any]] = [_synthetic_preflight(vault, expected)]
    if steps[-1]["status"] == "pass":
        for name, command in _release_steps(make_bin):
            step = _command_step(
                vault=vault,
                name=name,
                command=command,
                expected_fingerprint=expected,
                timeout_seconds=timeout_seconds,
            )
            steps.append(step)
            if step["status"] != "pass":
                break
    manifest = build_manifest(
        vault,
        expected_source_tree_fingerprint=expected,
        steps=steps,
        context=context or RuntimeContext(display_timezone=dt.UTC),
    )
    write_manifest(vault, manifest, out_path)
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the single-authority release readiness workflow.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--plan", action="store_true", help="Write a read-only release-run-ready cost plan.")
    parser.add_argument("--plan-out", default=DEFAULT_PLAN_OUT)
    parser.add_argument("--require-ready", action="store_true", help="Fail plan mode when evidence is not reusable.")
    parser.add_argument("--make-bin", default="make")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    if args.plan:
        plan = build_run_ready_plan(vault)
        path = write_run_ready_plan(vault, plan, args.plan_out)
        print(display_path(vault, path))
        print(f"release_run_ready_plan_status={plan['plan_status']}")
        if plan["minimal_next_target"]:
            print(f"minimal_next_target={plan['minimal_next_target']}")
        return 1 if args.require_ready and plan["plan_status"] != "ready" else 0
    manifest = run_release_ready(
        vault=vault,
        out_path=args.out,
        make_bin=args.make_bin,
        timeout_seconds=args.timeout_seconds,
    )
    print(display_path(vault, (vault / args.out).resolve()))
    print(f"release_run_status={manifest['status']}")
    if manifest["failures"]:
        print("failures=" + ",".join(manifest["failures"]))
    return 0 if manifest["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover - direct script fallback
    raise SystemExit(main(sys.argv[1:]))
