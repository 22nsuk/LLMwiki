from __future__ import annotations

import hashlib
import json
from contextlib import AbstractContextManager
from pathlib import Path
from unittest.mock import patch

from ops.scripts.core.artifact_binding_runtime import (
    REVISION_BINDING_MODE,
    binding_file_digest,
)
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.release.release_run_ready import (
    build_run_ready_plan,
    write_run_ready_plan,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-run-ready-plan.schema.json"
RUN_MANIFEST_SCHEMA_PATH = (
    REPO_ROOT / "ops" / "schemas" / "release-run-manifest.schema.json"
)
ZERO_SHA256 = "0" * 64


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


def _copy_run_manifest_schema(vault: Path) -> None:
    path = vault / "ops" / "schemas" / "release-run-manifest.schema.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        RUN_MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )


def _write_json(vault: Path, rel_path: str, payload: dict[str, object]) -> None:
    path = vault / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _json_payload_sha256(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    ).hexdigest()


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
        "input_fingerprints": {
            "source": "fp-current",
            "public_check_config": ZERO_SHA256,
        },
        "summary": {
            "public_export_status": "pass",
            "public_check_status": "pass",
            "export_file_count": 1,
            "export_source_file_count": 1,
            "export_root_fingerprint": ZERO_SHA256,
            "public_export_manifest_sha256": ZERO_SHA256,
            "public_surface_policy_sha256": ZERO_SHA256,
            "public_check_config_fingerprint": ZERO_SHA256,
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
    payload = {
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
    payload["input_fingerprints"] = {
        **payload["input_fingerprints"],
        "source_zip": str(source_zip["sha256"]),
    }
    return payload


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


def _release_closeout_summary_payload() -> dict[str, object]:
    return {
        **_common_envelope(
            schema="ops/schemas/release-closeout-summary.schema.json",
            artifact_kind="release_closeout_summary",
            producer="ops.scripts.release_closeout_summary",
            source_command="python -m ops.scripts.release_closeout_summary --vault . --profile default",
        ),
        "status": {"result": "pass"},
        "release_authority_status": "release_ready",
        "machine_release_allowed": True,
        "summary": {"ready_component_count": 1, "blocker_count": 0},
    }


def _release_run_manifest_payload(
    source_zip: dict[str, object],
    *,
    source_package_smoke_sha256: str,
    closeout_summary_fingerprint: str,
    source_package_smoke_path: str = "build/source-package-smoke/source-package-smoke.json",
) -> dict[str, object]:
    return {
        **_common_envelope(
            schema="ops/schemas/release-run-manifest.schema.json",
            artifact_kind="release_run_manifest",
            producer="ops.scripts.release_run_manifest",
            source_command="python -m ops.scripts.release_run_manifest --vault .",
            retention_policy="release_sidecar_authority",
        ),
        "input_fingerprints": {
            "distribution_zip": str(source_zip["sha256"]),
            "source_package_smoke": source_package_smoke_sha256,
            "source_package_smoke_source_zip": str(source_zip["sha256"]),
            "closeout_summary": closeout_summary_fingerprint,
        },
        "schema_version": 5,
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
            "path": source_package_smoke_path,
            "exists": True,
            "status": "pass",
            "sha256": ZERO_SHA256,
            "source_zip_sha256": str(source_zip["sha256"]),
        },
        "failures": [],
    }


def _write_current_run_ready_evidence(
    vault: Path,
    *,
    source_zip_path: str = "build/release/LLMwiki-source.zip",
    source_package_smoke_path: str = "build/source-package-smoke/source-package-smoke.json",
) -> dict[str, object]:
    source_zip = _file_identity(vault, source_zip_path)
    source_package_smoke = _source_package_smoke_payload(source_zip)
    closeout_summary_path = "ops/reports/release-closeout-summary.json"
    _write_json(vault, closeout_summary_path, _release_closeout_summary_payload())
    _binding_format, closeout_summary_fingerprint = binding_file_digest(
        vault / closeout_summary_path,
        binding_mode=REVISION_BINDING_MODE,
    )
    evidence = {
        "build/release/release-run-manifest.json": _release_run_manifest_payload(
            source_zip,
            source_package_smoke_sha256=_json_payload_sha256(source_package_smoke),
            closeout_summary_fingerprint=closeout_summary_fingerprint,
            source_package_smoke_path=source_package_smoke_path,
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
        source_package_smoke_path: source_package_smoke,
        "ops/reports/source-package-clean-extract.json": _source_package_clean_extract_payload(
            source_zip
        ),
    }
    for rel_path, payload in evidence.items():
        _write_json(vault, rel_path, payload)
    return source_zip


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
