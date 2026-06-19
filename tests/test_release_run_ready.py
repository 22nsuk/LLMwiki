from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from unittest.mock import patch

import pytest

from ops.scripts.core.command_runtime import TimedProcessResult
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.release.release_run_ready import (
    PLAN_SPECS,
    _command_step,
    _release_steps,
    build_run_ready_plan,
    main,
    write_run_ready_plan,
)

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-run-ready-plan.schema.json"
ZERO_SHA256 = "0" * 64
READY_PLAN_GOLDEN_SHA256 = (
    "64b602874c8cd2d0d55999e6fa7a0dd1a5cd70edfe4cf2ca680a74c955b5406f"
)
FORBIDDEN_PRIVATE_PREFIXES = (
    "raw/",
    "wiki/",
    "system/",
    "runs/",
    "external-reports/",
    "ops/operator/",
)


def fixed_context() -> RuntimeContext:
    import datetime as dt

    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 31, 12, 0, tzinfo=dt.UTC),
    )


def _copy_plan_schema(vault: Path) -> None:
    path = vault / "ops" / "schemas" / "release-run-ready-plan.schema.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PLAN_SCHEMA_PATH.read_text(encoding="utf-8"), encoding="utf-8")


def _write_json(vault: Path, rel_path: str, payload: dict[str, object]) -> None:
    path = vault / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_identity(vault: Path, rel_path: str) -> dict[str, object]:
    path = vault / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"release package placeholder\n")
    return {
        "path": rel_path,
        "exists": True,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def _common_envelope(
    *,
    schema: str,
    artifact_kind: str,
    producer: str,
    source_command: str,
    retention_policy: str = "canonical_report",
) -> dict[str, object]:
    return {
        "$schema": schema,
        "artifact_kind": artifact_kind,
        "generated_at": "2026-05-31T12:00:00Z",
        "producer": producer,
        "source_command": source_command,
        "source_revision": "abc123",
        "source_tree_fingerprint": "fp-current",
        "input_fingerprints": {"source": "fp-current"},
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": retention_policy,
        "encoding": "utf-8",
        "currentness": {"status": "current", "checked_at": "2026-05-31T12:00:00Z"},
    }


def _policy() -> dict[str, object]:
    return {"path": "ops/policies/wiki-maintainer-policy.yaml", "version": 1}


def _counts() -> dict[str, int]:
    return {
        "passed": 1,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "warnings": 0,
        "subtests_passed": 0,
    }


def _test_execution_summary_payload(
    *, suite: str, represents_full_suite: bool
) -> dict[str, object]:
    full_suite_status = "represented" if represents_full_suite else "not_represented"
    suite_scope = "full_suite" if represents_full_suite else "report_contract_summary"
    return {
        **_common_envelope(
            schema="ops/schemas/test-execution-summary.schema.json",
            artifact_kind="test_execution_summary",
            producer="ops.scripts.test_execution_summary",
            source_command=f"python -m ops.scripts.test_execution_summary --vault . --suite {suite}",
        ),
        "vault": ".",
        "policy": _policy(),
        "suite": suite,
        "suite_scope": suite_scope,
        "represents_full_suite": represents_full_suite,
        "not_full_suite_reason": (
            "" if represents_full_suite else "report-contract fixture"
        ),
        "full_suite_evidence": {
            "status": full_suite_status,
            "required_command": "make test-execution-summary-full-current-or-refresh",
            "raw_pytest_command": "python -m pytest",
            "developer_regression_command": "make test-all",
            "release_builder_environment": "synthetic-public-fixture",
            "reason": "schema-backed run-ready planner fixture",
        },
        "status": "pass",
        "command": "python -m pytest tests/test_release_run_ready.py",
        "semantic_command": "-m pytest tests/test_release_run_ready.py",
        "toolchain_fingerprint": "toolchain-current",
        "returncode": 0,
        "timed_out": False,
        "timeout_seconds": 60,
        "termination_reason": "completed",
        "duration_ms": 1,
        "counts": _counts(),
        "execution_environment": {
            "python_version": "3.11.0",
            "pytest_version": "8.4.0",
            "plugin_autoload_policy": {
                "env_var": "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
                "value": "1",
                "autoload_disabled": True,
                "policy": "disabled",
            },
            "interpreter_path_class": "repo_virtualenv",
            "toolchain_contract": {
                "status": "pass",
                "python_supported": True,
                "pytest_supported": True,
                "supported_python_major_minor": ["3.11"],
                "minimum_pytest_major": 8,
                "release_evidence_effect": "eligible",
                "reason": "synthetic fixture",
            },
        },
        "test_target_fingerprints": [
            {"path": "tests/test_release_run_ready.py", "sha256": ZERO_SHA256}
        ],
        "deselected_tests": [],
        "deselection_lifecycle": {
            "status": "pass",
            "checked_at": "2026-05-31T12:00:00Z",
            "actual_deselected_count": 0,
            "max_allowed_deselected_count": 0,
            "over_budget": False,
            "expired_count": 0,
            "release_blocking_count": 0,
            "missing_lifecycle_count": 0,
            "duplicate_policy_entry_count": 0,
            "unused_policy_entry_count": 0,
            "risk_owner": "",
            "expires_at": "",
            "count_increase_gate_effect": "pass",
            "expiry_gate_effect": "pass",
            "next_action": "none",
            "blockers": [],
        },
        "pytest_collect_nodeid_digest": {
            "status": "collected",
            "command": "python -m pytest --collect-only",
            "nodeid_count": 1,
            "sha256": ZERO_SHA256,
            "reason": "synthetic fixture",
        },
        "nodeid_outcome_consistency": {
            "status": "pass",
            "nodeid_count": 1,
            "outcome_count": 1,
            "counted_outcomes": {
                "passed": 1,
                "skipped": 0,
                "xfailed": 0,
                "xpassed": 0,
            },
            "delta": 0,
            "reason": "synthetic fixture",
        },
        "evidence_artifacts": [],
        "stdout_tail": "",
        "stderr_tail": "",
    }


def _public_command(command_id: str) -> dict[str, object]:
    return {
        "id": command_id,
        "command": f"make {command_id}",
        "cwd": ".",
        "status": "pass",
        "returncode": 0,
        "timed_out": False,
        "timeout_seconds": 60,
        "termination_reason": "completed",
        "duration_ms": 1,
        "heartbeat_count": 0,
        "heartbeat_interval_seconds": 0,
        "quiet_seconds": 0,
        "observation_mode": "communicate",
        "stdout_tail": "",
        "stderr_tail": "",
        "pytest_counts": {},
    }


def _public_check_summary_payload() -> dict[str, object]:
    return {
        **_common_envelope(
            schema="ops/schemas/public-check-summary.schema.json",
            artifact_kind="public_check_summary",
            producer="ops.scripts.public_check_summary",
            source_command="python -m ops.scripts.public_check_summary --vault .",
        ),
        "vault": ".",
        "policy": _policy(),
        "status": "pass",
        "summary": {
            "public_export_status": "pass",
            "public_check_status": "pass",
            "export_file_count": 1,
            "export_source_file_count": 1,
            "export_root_fingerprint": ZERO_SHA256,
            "public_export_manifest_sha256": ZERO_SHA256,
            "public_surface_policy_sha256": ZERO_SHA256,
            "command_count": 3,
            "command_fail_count": 0,
            "negative_assertion_fail_count": 0,
            "physical_repo_split_status": "pass",
            "private_surface_history_absence_status": "pass",
            "pytest_passed": 1,
            "pytest_failed": 0,
            "pytest_errors": 0,
            "pytest_skipped": 0,
        },
        "public_export": {
            "output_dir": "build/public",
            "manifest_file": "build/public/manifest.json",
            "file_count": 1,
            "source_file_count": 1,
            "export_root_fingerprint": ZERO_SHA256,
            "manifest_sha256": ZERO_SHA256,
        },
        "public_export_negative_assertions": {
            "excluded_prefix_absence": {
                "status": "pass",
                "violation_count": 0,
                "violations": [],
            },
            "local_path_absence": {
                "status": "pass",
                "violation_count": 0,
                "violations": [],
            },
            "private_pattern_absence": {
                "status": "pass",
                "violation_count": 0,
                "violations": [],
            },
        },
        "commands": [
            _public_command("ruff"),
            _public_command("mypy"),
            _public_command("pytest_public"),
        ],
    }


def _byte_budget() -> dict[str, object]:
    return {"limit_bytes": 1024, "max_bytes": 1, "status": "pass"}


def _release_smoke_payload(
    *,
    profile: str,
    source_command: str,
    archive_file: dict[str, object],
) -> dict[str, object]:
    return {
        **_common_envelope(
            schema="ops/schemas/release-smoke-report.schema.json",
            artifact_kind="release_smoke_report",
            producer="ops.scripts.release_smoke",
            source_command=source_command,
        ),
        "vault": ".",
        "policy": _policy(),
        "profile": profile,
        "status": "pass",
        "archive_path": str(archive_file["path"]),
        "archive_file": archive_file,
        "archive_class": {
            "name": "release_smoke_zip",
            "format": "zip",
            "compression": "stored",
            "root_prefix": "LLMwiki",
            "member_path_template": "LLMwiki/{path}",
            "path_encoding": "utf-8",
            "zip_create_system": 3,
            "manifest_exclusion_policy": {
                "name": "public-fixture",
                "excluded_prefixes": [],
                "excluded_files": [],
                "excluded_cache_dirs": [],
                "excluded_dev_hidden_dirs": [],
                "excluded_suffixes": [],
                "excluded_egg_info_dirs": True,
            },
        },
        "archive_budget": {
            "pass": True,
            "zip_path_byte_budget": _byte_budget(),
            "zip_component_byte_budget": _byte_budget(),
            "posix_escape_expanded_filename_budget": _byte_budget(),
            "blocking_budget_fail_count": 0,
            "platform_warning_count": 0,
            "platform_path_diagnostics": {
                "status": "pass",
                "blocker_count": 0,
                "warning_count": 0,
                "diagnostics": [],
            },
            "top_offenders": [],
        },
        "archive_reproducibility": {
            "status": "not_run",
            "run_count": 0,
            "first_archive_sha256": "",
            "second_archive_sha256": "",
            "same_archive_sha256": False,
            "first_source_manifest_digest": "",
            "second_source_manifest_digest": "",
            "same_source_manifest_digest": False,
            "summary": "not run in fixture",
        },
        "extracted_vault": "tmp/release-smoke/extracted/LLMwiki",
        "packed_file_count": 1,
        "manifest_comparison": {
            "pass": True,
            "expected_file_count": 1,
            "extracted_file_count": 1,
            "missing_paths": [],
            "unexpected_paths": [],
            "sha_mismatches": [],
            "size_mismatches": [],
        },
        "commands": [],
    }


def _source_package_smoke_payload(source_zip: dict[str, object]) -> dict[str, object]:
    return {
        **_common_envelope(
            schema="ops/schemas/source-package-smoke.schema.json",
            artifact_kind="source_package_smoke",
            producer="ops.scripts.source_package_smoke",
            source_command="python -m ops.scripts.source_package_smoke --vault .",
            retention_policy="release_sidecar_evidence",
        ),
        "status": "pass",
        "source_zip": source_zip,
        "extract": {
            "parent": "build/source-package-smoke/extract",
            "root": "build/source-package-smoke/extract/LLMwiki",
            "archive_root_name": "LLMwiki",
            "status": "pass",
        },
        "commands": [],
        "failures": [],
    }


def _source_package_clean_extract_payload(
    source_zip: dict[str, object],
) -> dict[str, object]:
    clean_source_zip = {
        "path": source_zip["path"],
        "exists": source_zip["exists"],
        "sha256": source_zip["sha256"],
    }
    return {
        **_common_envelope(
            schema="ops/schemas/source-package-clean-extract.schema.json",
            artifact_kind="source_package_clean_extract",
            producer="ops.scripts.source_package_clean_extract",
            source_command="python -m ops.scripts.source_package_clean_extract --vault .",
            retention_policy="release_sidecar_evidence",
        ),
        "vault": ".",
        "policy": _policy(),
        "status": "pass",
        "source_zip": clean_source_zip,
        "extract": {
            "parent": "build/source-package-clean-extract/extract",
            "root": "build/source-package-clean-extract/extract/LLMwiki",
            "archive_root_name": "LLMwiki",
            "archive_root_source": "archive_self_description",
            "status": "pass",
            "summary": "synthetic clean extract fixture",
        },
        "commands": [],
        "script_output_surfaces_status": "pass",
        "ruff_status": "pass",
        "mypy_status": "pass",
        "test_source_package_status": "pass",
        "test_source_package_summary": {
            "path": "ops/reports/test-execution-summary.json",
            "load_status": "ok",
            "status": "pass",
        },
        "deselection_budget_status": {
            "status": "pass",
            "load_status": "ok",
            "actual_deselected_count": 0,
            "max_allowed_deselected_count": 0,
            "over_budget": False,
            "expires_at": "",
            "next_action": "none",
        },
        "source_package_reproducibility_status": "pass",
        "heartbeat_observability": {
            "status": "pass",
            "command_count": 0,
            "heartbeat_enabled_command_count": 0,
            "heartbeat_event_count": 0,
            "max_heartbeat_count": 0,
            "max_quiet_seconds": 0,
            "quiet_command_names": [],
            "unobserved_command_names": [],
            "next_action": "none",
        },
        "zip_smoke_report": {
            "path": "build/release/release-distribution-zip-smoke.json",
            "load_status": "ok",
            "status": "pass",
            "manifest_comparison_pass": True,
            "archive_budget_pass": True,
        },
    }


def _release_run_manifest_payload(source_zip: dict[str, object]) -> dict[str, object]:
    return {
        **_common_envelope(
            schema="ops/schemas/release-run-manifest.schema.json",
            artifact_kind="release_run_manifest",
            producer="ops.scripts.release_run_manifest",
            source_command="python -m ops.scripts.release_run_manifest --vault .",
            retention_policy="release_sidecar_authority",
        ),
        "schema_version": 4,
        "status": "pass",
        "release_authority_status": "release_ready",
        "machine_release_allowed": True,
        "expected_source_tree_fingerprint": "fp-current",
        "final_source_tree_fingerprint": "fp-current",
        "git_commit": "abc123",
        "git_clean": True,
        "remote_sync": {
            "status": "pass",
            "upstream": "origin/main",
            "ahead": 0,
            "behind": 0,
        },
        "ignored_tracked_file_count": 0,
        "steps": [],
        "step_duration_summary": {
            "total_duration_ms": 0,
            "step_count": 0,
            "passed_step_count": 0,
            "failed_step_count": 0,
            "slowest_step": {
                "name": "",
                "status": "not_run",
                "duration_ms": 0,
                "share_of_total": 0.0,
            },
            "steps_by_duration_desc": [],
            "comparison_groups": {
                "test": {
                    "matched_step_count": 0,
                    "total_duration_ms": 0,
                    "slowest_step_name": "",
                    "share_of_total": 0.0,
                },
                "public": {
                    "matched_step_count": 0,
                    "total_duration_ms": 0,
                    "slowest_step_name": "",
                    "share_of_total": 0.0,
                },
                "smoke": {
                    "matched_step_count": 0,
                    "total_duration_ms": 0,
                    "slowest_step_name": "",
                    "share_of_total": 0.0,
                },
                "source_package": {
                    "matched_step_count": 0,
                    "total_duration_ms": 0,
                    "slowest_step_name": "",
                    "share_of_total": 0.0,
                },
            },
        },
        "distribution_zip": {
            "path": source_zip["path"],
            "exists": source_zip["exists"],
            "size_bytes": source_zip["size_bytes"],
            "sha256": source_zip["sha256"],
        },
        "source_package_smoke": {
            "path": "build/source-package-smoke/source-package-smoke.json",
            "exists": True,
            "status": "pass",
            "sha256": ZERO_SHA256,
            "source_zip_sha256": source_zip["sha256"],
        },
        "failures": [],
    }


def _write_current_run_ready_evidence(vault: Path) -> None:
    source_zip = _file_identity(vault, "build/release/LLMwiki-source.zip")
    evidence = {
        "build/release/release-run-manifest.json": _release_run_manifest_payload(
            source_zip
        ),
        "ops/reports/test-execution-summary-full.json": _test_execution_summary_payload(
            suite="full",
            represents_full_suite=True,
        ),
        "ops/reports/test-execution-summary.json": _test_execution_summary_payload(
            suite="report-contract-summary",
            represents_full_suite=False,
        ),
        "ops/reports/public-check-summary.json": _public_check_summary_payload(),
        "ops/reports/release-smoke-report.json": _release_smoke_payload(
            profile="full",
            source_command="python -m ops.scripts.release.release_smoke --vault . --profile full",
            archive_file=source_zip,
        ),
        "build/release/release-distribution-zip-smoke.json": _release_smoke_payload(
            profile="fast",
            source_command="python -m ops.scripts.release.release_smoke --vault . --profile fast",
            archive_file=source_zip,
        ),
        "build/source-package-smoke/source-package-smoke.json": _source_package_smoke_payload(
            source_zip
        ),
        "ops/reports/source-package-clean-extract.json": _source_package_clean_extract_payload(
            source_zip
        ),
    }
    for rel_path, payload in evidence.items():
        _write_json(vault, rel_path, payload)


def _patch_plan_repo(
    *, clean: bool = True, ignored_count: int = 0
) -> AbstractContextManager[object]:
    return patch.multiple(
        "ops.scripts.release.release_run_ready",
        release_source_tree_fingerprint=lambda _vault: "fp-current",
        git_commit=lambda _vault: "abc123",
        git_clean=lambda _vault: clean,
        remote_sync=lambda _vault: {
            "status": "pass",
            "upstream": "origin/main",
            "ahead": 0,
            "behind": 0,
        },
        ignored_tracked_file_count=lambda _vault: ignored_count,
    )


def _run_ready_plan_bytes(
    vault: Path, *, out_path: str = "tmp/release-run-ready-plan.json"
) -> bytes:
    _copy_plan_schema(vault)
    _write_current_run_ready_evidence(vault)
    with _patch_plan_repo():
        plan = build_run_ready_plan(vault, context=fixed_context())
    path = write_run_ready_plan(vault, plan, out_path)
    return path.read_bytes()


def _string_values(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _string_values(str(key))
            yield from _string_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _string_values(item)


def _assert_no_forbidden_private_prefixes(payload: dict[str, object]) -> None:
    for text in _string_values(payload):
        assert not text.startswith(FORBIDDEN_PRIVATE_PREFIXES), text


def _write_private_sentinels(vault: Path) -> None:
    for prefix in FORBIDDEN_PRIVATE_PREFIXES:
        path = vault / prefix / "private-sentinel.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("private corpus sentinel\n", encoding="utf-8")


def test_release_run_ready_uses_source_package_check_for_stage2_evidence() -> None:
    assert _release_steps("make") == [
        ("release-test-current", ["make", "release-test-current"]),
        ("release-public-current", ["make", "release-public-current"]),
        ("release-smoke-full-reuse", ["make", "release-smoke-full-reuse"]),
        ("release-source-package-check", ["make", "release-source-package-check"]),
    ]


def test_run_ready_plan_reports_dirty_worktree_before_expensive_refresh(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)

    with _patch_plan_repo(clean=False):
        plan = build_run_ready_plan(vault, context=fixed_context())

    assert plan["plan_status"] == "blocked"
    assert plan["summary_mode"] == "blocked_next_target_plan"
    assert plan["minimal_next_target"] == "release-worktree-clean-check"
    assert plan["next_targets"][0] == "release-worktree-clean-check"
    assert "git_worktree_dirty" in plan["reason_codes"]
    assert plan["duration_summary"]["duration_budget_status"] == "within_budget"
    assert (
        plan["duration_summary"]["all_stale_targets_duration_budget_status"]
        == "over_budget"
    )
    assert (
        plan["duration_summary"]["blocked_expensive_duration_budget_status"]
        == "over_budget"
    )
    assert plan["stale_evidence_causes"][0]["node"] == "release_preflight"
    assert plan["stale_evidence_causes"][0]["handoff_class"] == "codehealth_source_fix"
    assert "git_worktree_dirty" in plan["nodes"][0]["issues"]
    assert plan["nodes"][0]["reason_codes"] == ["git_worktree_dirty"]
    assert plan["nodes"][0]["duration_budget_status"] == "within_budget"
    assert plan["boundary"]["local_only_generated_artifacts_not_promoted"] is True
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_selects_stale_full_suite_as_minimal_next_target(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    _write_json(
        vault,
        "ops/reports/test-execution-summary-full.json",
        {
            "artifact_kind": "test_execution_summary",
            "status": "pass",
            "source_tree_fingerprint": "fp-old",
            "source_revision": "abc123",
        },
    )

    with _patch_plan_repo():
        plan = build_run_ready_plan(vault, context=fixed_context())

    full_suite_node = plan["nodes"][1]
    assert full_suite_node["name"] == "test_execution_summary_full"
    assert "source_tree_fingerprint_stale" in full_suite_node["issues"]
    assert "source_tree_fingerprint_stale" in full_suite_node["reason_codes"]
    assert full_suite_node["next_targets"] == [
        "test-execution-summary-full-current-or-refresh"
    ]
    assert full_suite_node["duration_budget_status"] == "over_budget"
    assert (
        plan["minimal_next_target"] == "test-execution-summary-full-current-or-refresh"
    )
    assert plan["next_targets"][0] == "test-execution-summary-full-current-or-refresh"
    assert "source_tree_fingerprint_stale" in plan["reason_codes"]
    assert plan["duration_summary"]["duration_budget_status"] == "over_budget"
    assert (
        plan["duration_summary"]["all_stale_targets_duration_budget_status"]
        == "over_budget"
    )
    assert (
        plan["duration_summary"]["blocked_expensive_duration_budget_status"]
        == "over_budget"
    )
    assert plan["duration_summary"]["estimated_next_target_seconds"] == 7200
    assert plan["stale_evidence_causes"][0]["handoff_class"] == "local_evidence_refresh"
    assert plan["stale_evidence_causes"][0]["duration_budget_status"] == "over_budget"
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_is_ready_when_all_public_evidence_is_current(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    _write_current_run_ready_evidence(vault)

    with _patch_plan_repo():
        plan = build_run_ready_plan(vault, context=fixed_context())

    assert plan["plan_status"] == "ready"
    assert plan["summary_mode"] == "ready_reuse_plan"
    assert plan["minimal_next_target"] == ""
    assert plan["next_targets"] == []
    assert plan["reason_codes"] == []
    assert plan["duration_summary"]["duration_budget_status"] == "not_required"
    assert (
        plan["duration_summary"]["all_stale_targets_duration_budget_status"]
        == "not_required"
    )
    assert (
        plan["duration_summary"]["blocked_expensive_duration_budget_status"]
        == "not_required"
    )
    assert plan["duration_summary"]["blocked_expensive_gate_count"] == 0
    assert plan["authority_manifest_alignment"]["alignment_status"] == "current"
    assert plan["stale_evidence_causes"] == []
    assert all(node["can_reuse"] for node in plan["nodes"])
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []
    assert write_run_ready_plan(
        vault, plan, "build/release/release-run-ready-plan.json"
    ).exists()


def test_run_ready_plan_selects_stale_authority_manifest_as_minimal_next_target(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    _write_current_run_ready_evidence(vault)
    manifest_path = vault / "build" / "release" / "release-run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_revision"] = "old"
    manifest["source_tree_fingerprint"] = "fp-old"
    manifest["final_source_tree_fingerprint"] = "fp-old"
    _write_json(vault, "build/release/release-run-manifest.json", manifest)

    with _patch_plan_repo():
        plan = build_run_ready_plan(vault, context=fixed_context())

    alignment = plan["authority_manifest_alignment"]
    assert plan["plan_status"] == "blocked"
    assert plan["minimal_next_target"] == "release-run-ready"
    assert alignment["alignment_status"] == "stale"
    assert "source_revision_stale" in alignment["issues"]
    assert "source_tree_fingerprint_stale" in alignment["issues"]
    assert plan["stale_evidence_causes"][0]["node"] == "authority_manifest"
    assert (
        plan["stale_evidence_causes"][0]["minimal_next_target"] == "release-run-ready"
    )
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_rejects_schema_invalid_authority_manifest(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    _write_current_run_ready_evidence(vault)
    manifest_path = vault / "build" / "release" / "release-run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["unexpected_contract_drift"] = True
    _write_json(vault, "build/release/release-run-manifest.json", manifest)

    with _patch_plan_repo():
        plan = build_run_ready_plan(vault, context=fixed_context())

    alignment = plan["authority_manifest_alignment"]
    assert plan["plan_status"] == "blocked"
    assert plan["minimal_next_target"] == "release-run-ready"
    assert alignment["alignment_status"] == "stale"
    assert alignment["issues"] == ["schema_invalid"]
    assert plan["stale_evidence_causes"][0]["node"] == "authority_manifest"
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_labels_empty_authority_manifest_schema_invalid(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    _write_current_run_ready_evidence(vault)
    _write_json(vault, "build/release/release-run-manifest.json", {})

    with _patch_plan_repo():
        plan = build_run_ready_plan(vault, context=fixed_context())

    alignment = plan["authority_manifest_alignment"]
    assert plan["plan_status"] == "blocked"
    assert plan["minimal_next_target"] == "release-run-ready"
    assert alignment["alignment_status"] == "stale"
    assert "schema_invalid" in alignment["issues"]
    assert "source_tree_fingerprint_missing" in alignment["issues"]
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_reports_missing_authority_manifest_without_private_paths(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    _write_current_run_ready_evidence(vault)
    (vault / "build" / "release" / "release-run-manifest.json").unlink()

    with _patch_plan_repo():
        plan = build_run_ready_plan(vault, context=fixed_context())

    alignment = plan["authority_manifest_alignment"]
    assert plan["plan_status"] == "blocked"
    assert plan["minimal_next_target"] == "release-run-ready"
    assert alignment["alignment_status"] == "missing"
    assert alignment["issues"] == ["not_loadable"]
    assert alignment["recommended_next_target"] == "release-run-ready"
    _assert_no_forbidden_private_prefixes(plan)
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_allows_ephemeral_full_smoke_archive(tmp_path: Path) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    _write_current_run_ready_evidence(vault)
    full_smoke_path = vault / "ops" / "reports" / "release-smoke-report.json"
    full_smoke = json.loads(full_smoke_path.read_text(encoding="utf-8"))
    full_smoke["archive_file"] = {
        "path": "<tmp>/LLMwiki-release-smoke.zip",
        "exists": True,
        "size_bytes": 1234,
        "sha256": "1" * 64,
    }
    _write_json(vault, "ops/reports/release-smoke-report.json", full_smoke)

    with _patch_plan_repo():
        plan = build_run_ready_plan(vault, context=fixed_context())

    full_smoke_node = next(
        node for node in plan["nodes"] if node["name"] == "release_smoke_full"
    )
    distribution_node = next(
        node
        for node in plan["nodes"]
        if node["name"] == "release_distribution_zip_smoke"
    )
    assert full_smoke_node["can_reuse"] is True
    assert "referenced_file_stale" not in full_smoke_node["issues"]
    assert distribution_node["can_reuse"] is True
    assert plan["plan_status"] == "ready"
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_writes_byte_stable_ready_golden(tmp_path: Path) -> None:
    first_bytes = _run_ready_plan_bytes(tmp_path / "first")
    second_bytes = _run_ready_plan_bytes(tmp_path / "second")

    assert first_bytes == second_bytes
    assert first_bytes.endswith(b"\n")
    assert first_bytes == (
        json.dumps(json.loads(first_bytes), ensure_ascii=False, indent=2).encode(
            "utf-8"
        )
        + b"\n"
    )
    assert hashlib.sha256(first_bytes).hexdigest() == READY_PLAN_GOLDEN_SHA256


def test_run_ready_plan_rejects_schema_invalid_passing_evidence(tmp_path: Path) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    _write_current_run_ready_evidence(vault)
    full_summary_path = vault / "ops" / "reports" / "test-execution-summary-full.json"
    invalid_full_summary = json.loads(full_summary_path.read_text(encoding="utf-8"))
    del invalid_full_summary["counts"]
    _write_json(
        vault, "ops/reports/test-execution-summary-full.json", invalid_full_summary
    )

    with _patch_plan_repo():
        plan = build_run_ready_plan(vault, context=fixed_context())

    first_evidence_node = plan["nodes"][1]
    assert first_evidence_node["name"] == "test_execution_summary_full"
    assert first_evidence_node["can_reuse"] is False
    assert "schema_invalid" in first_evidence_node["issues"]
    assert plan["plan_status"] == "blocked"
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_boundary_excludes_private_roots_and_operator_signoff(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)

    with _patch_plan_repo():
        plan = build_run_ready_plan(vault, context=fixed_context())

    forbidden_prefixes = (
        "raw/",
        "wiki/",
        "system/",
        "runs/",
        "external-reports/",
        "ops/operator/",
    )
    for spec in PLAN_SPECS:
        assert not spec.path.startswith(forbidden_prefixes)

    for node in plan["nodes"]:
        path = str(node["path"])
        assert path == "." or path.startswith(("ops/reports/", "build/"))
        assert not path.startswith(forbidden_prefixes)
        boundary_text = " ".join(
            str(node[field])
            for field in (
                "name",
                "stage",
                "check_target",
                "refresh_target",
                "expected_artifact_kind",
            )
        )
        assert "operator" not in boundary_text
        assert "signoff" not in boundary_text

    handoff_classes = {
        str(cause["handoff_class"]) for cause in plan["stale_evidence_causes"]
    }
    assert handoff_classes <= {"codehealth_source_fix", "local_evidence_refresh"}
    assert "release_signoff_only" not in handoff_classes
    _assert_no_forbidden_private_prefixes(plan)
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_private_sentinels_do_not_change_ready_golden(
    tmp_path: Path,
) -> None:
    baseline_bytes = _run_ready_plan_bytes(tmp_path / "baseline")
    sentinel_vault = tmp_path / "with-private-sentinels"
    _write_private_sentinels(sentinel_vault)
    sentinel_bytes = _run_ready_plan_bytes(sentinel_vault)

    assert sentinel_bytes == baseline_bytes
    _assert_no_forbidden_private_prefixes(json.loads(sentinel_bytes))


def test_plan_mode_writes_only_requested_sidecar_without_authority_promotion(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)

    with _patch_plan_repo():
        returncode = main(
            [
                "--vault",
                str(vault),
                "--plan",
                "--plan-out",
                "tmp/release-run-ready-plan.json",
            ]
        )

    assert returncode == 0
    stdout = capsys.readouterr().out
    assert "release_run_ready_plan_status=blocked" in stdout
    assert "summary_mode=blocked_next_target_plan" in stdout
    assert (
        "minimal_next_target=test-execution-summary-full-current-or-refresh" in stdout
    )
    assert "duration_budget_status=over_budget" in stdout
    assert "all_stale_targets_duration_budget_status=over_budget" in stdout
    assert "blocked_expensive_duration_budget_status=over_budget" in stdout
    assert "duration_budget_seconds=300" in stdout
    assert "estimated_next_target_seconds=7200" in stdout
    assert "blocked_expensive_gate_count=" in stdout
    assert "next_targets=test-execution-summary-full-current-or-refresh" in stdout
    assert "reason_codes=not_loadable" in stdout
    assert (vault / "tmp" / "release-run-ready-plan.json").is_file()
    assert not (vault / "build" / "release" / "release-run-manifest.json").exists()
    assert not (vault / "ops" / "operator" / "operator-release-summary.json").exists()
    assert not (vault / "ops" / "reports").exists()


def test_command_step_records_reused_summary_mode_for_public_current(
    tmp_path: Path,
) -> None:
    vault = tmp_path

    with (
        patch(
            "ops.scripts.release.release_run_ready.run_with_timeout",
            return_value=TimedProcessResult(
                args=["make", "release-public-current"],
                returncode=0,
                stdout="public check summary is current; reused ops/reports/public-check-summary.json",
                stderr="",
                timed_out=False,
                timeout_seconds=60,
                termination_reason="completed",
            ),
        ),
        patch(
            "ops.scripts.release.release_run_ready.release_source_tree_fingerprint",
            return_value="fp-current",
        ),
    ):
        step = _command_step(
            vault=vault,
            name="release-public-current",
            command=["make", "release-public-current"],
            expected_fingerprint="fp-current",
            timeout_seconds=60,
        )

    assert step["summary_mode"] == "reused"


def test_command_step_records_executed_summary_mode_for_mixed_source_package_step(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    stdout = "\n".join(
        [
            "release distribution zip evidence is current; reused build/release/release-distribution-zip-smoke.json",
            "source package smoke evidence is current; reused build/source-package-smoke/source-package-smoke.json",
        ]
    )

    with (
        patch(
            "ops.scripts.release.release_run_ready.run_with_timeout",
            return_value=TimedProcessResult(
                args=["make", "release-source-package-check"],
                returncode=0,
                stdout=stdout,
                stderr="",
                timed_out=False,
                timeout_seconds=60,
                termination_reason="completed",
            ),
        ),
        patch(
            "ops.scripts.release.release_run_ready.release_source_tree_fingerprint",
            return_value="fp-current",
        ),
    ):
        step = _command_step(
            vault=vault,
            name="release-source-package-check",
            command=["make", "release-source-package-check"],
            expected_fingerprint="fp-current",
            timeout_seconds=60,
        )

    assert step["summary_mode"] == "executed"
