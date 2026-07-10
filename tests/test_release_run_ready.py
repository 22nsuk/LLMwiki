from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from ops.scripts.core.command_runtime import TimedProcessResult
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.release.release_run_ready import (
    PLAN_SPECS,
    _command_step,
    _release_steps,
    build_run_ready_plan,
    main,
    run_release_ready,
    write_run_ready_plan,
)
from tests.release_run_ready_sample_runtime import (
    PLAN_SCHEMA_PATH,
    RUN_MANIFEST_SCHEMA_PATH,
    _copy_plan_schema,
    _copy_run_manifest_schema,
    _file_identity,
    _patch_plan_repo,
    _run_ready_plan_bytes,
    _sha256_file,
    _source_package_smoke_payload,
    _write_current_run_ready_evidence,
    _write_json,
    fixed_context,
)

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
READY_PLAN_GOLDEN_SHA256 = (
    "e08277ffaa84abb63472bdbda942ba6c24ce2320b343d662fad2d46aa0b64dd6"
)
FORBIDDEN_PRIVATE_PREFIXES = (
    "raw/",
    "wiki/",
    "system/",
    "runs/",
    "external-reports/",
    "ops/operator/",
)


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
        (
            "release-source-package-check",
            [
                "make",
                "release-source-package-check",
                "RELEASE_CLOSEOUT_DISTRIBUTION_ZIP=build/release/LLMwiki-source.zip",
                "SOURCE_PACKAGE_SMOKE_OUT=build/source-package-smoke/source-package-smoke.json",
            ],
        ),
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


def test_run_ready_plan_blocks_on_authority_manifest_input_fingerprint_drift(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    _write_current_run_ready_evidence(vault)
    manifest_path = vault / "build" / "release" / "release-run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_fingerprints"]["distribution_zip"] = "0" * 64
    _write_json(vault, "build/release/release-run-manifest.json", manifest)

    with _patch_plan_repo():
        plan = build_run_ready_plan(vault, context=fixed_context())

    alignment = plan["authority_manifest_alignment"]
    assert plan["plan_status"] == "blocked"
    assert plan["minimal_next_target"] == "release-run-ready"
    assert alignment["alignment_status"] == "stale"
    assert "input_fingerprint_stale" in alignment["issues"]
    assert plan["stale_evidence_causes"][0]["node"] == "authority_manifest"
    assert "input_fingerprint_stale" in plan["reason_codes"]
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_blocks_on_authority_manifest_persisted_failures(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    _write_current_run_ready_evidence(vault)
    manifest_path = vault / "build" / "release" / "release-run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "pass"
    manifest["failures"] = ["git_worktree_dirty"]
    _write_json(vault, "build/release/release-run-manifest.json", manifest)

    with _patch_plan_repo():
        plan = build_run_ready_plan(vault, context=fixed_context())

    alignment = plan["authority_manifest_alignment"]
    assert plan["plan_status"] == "blocked"
    assert plan["minimal_next_target"] == "release-run-ready"
    assert alignment["alignment_status"] == "stale"
    assert "failures_present" in alignment["issues"]
    assert plan["stale_evidence_causes"][0]["node"] == "authority_manifest"
    assert "failures_present" in plan["reason_codes"]
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_aligns_authority_manifest_to_selected_distribution_zip(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    selected_zip = _write_current_run_ready_evidence(
        vault,
        source_zip_path="build/release/custom-source.zip",
    )

    with _patch_plan_repo():
        plan = build_run_ready_plan(
            vault,
            distribution_zip="build/release/custom-source.zip",
            context=fixed_context(),
        )

    alignment = plan["authority_manifest_alignment"]
    assert plan["plan_status"] == "ready"
    assert alignment["alignment_status"] == "current"
    assert plan["stale_evidence_causes"] == []
    assert plan["input_fingerprints"]["authority_manifest"] == _sha256_file(
        vault / "build/release/release-run-manifest.json"
    )
    assert selected_zip["path"] == "build/release/custom-source.zip"
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_rejects_distribution_smoke_for_different_zip_path(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    _write_current_run_ready_evidence(
        vault,
        source_zip_path="build/release/custom-source.zip",
    )
    default_zip = _file_identity(vault, "build/release/LLMwiki-source.zip")
    distribution_smoke_path = (
        vault / "build" / "release" / "release-distribution-zip-smoke.json"
    )
    distribution_smoke = json.loads(distribution_smoke_path.read_text(encoding="utf-8"))
    distribution_smoke["archive_file"] = default_zip
    _write_json(
        vault,
        "build/release/release-distribution-zip-smoke.json",
        distribution_smoke,
    )

    with _patch_plan_repo():
        plan = build_run_ready_plan(
            vault,
            distribution_zip="build/release/custom-source.zip",
            context=fixed_context(),
        )

    distribution_node = next(
        node
        for node in plan["nodes"]
        if node["name"] == "release_distribution_zip_smoke"
    )
    expected_target = (
        "release-package-current-or-refresh "
        "RELEASE_CLOSEOUT_DISTRIBUTION_ZIP=build/release/custom-source.zip"
    )
    assert plan["plan_status"] == "blocked"
    assert distribution_node["can_reuse"] is False
    assert "referenced_file_stale" in distribution_node["issues"]
    assert distribution_node["refresh_target"] == expected_target
    assert distribution_node["next_targets"] == [expected_target]
    assert plan["minimal_next_target"] == expected_target
    assert expected_target in plan["next_targets"]
    assert plan["authority_manifest_alignment"]["alignment_status"] == "current"
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_rejects_default_distribution_smoke_for_custom_zip_path(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    _write_current_run_ready_evidence(vault)
    custom_zip = _file_identity(vault, "build/release/custom-source.zip")
    distribution_smoke_path = (
        vault / "build" / "release" / "release-distribution-zip-smoke.json"
    )
    distribution_smoke = json.loads(distribution_smoke_path.read_text(encoding="utf-8"))
    distribution_smoke["archive_file"] = custom_zip
    _write_json(
        vault,
        "build/release/release-distribution-zip-smoke.json",
        distribution_smoke,
    )

    with _patch_plan_repo():
        plan = build_run_ready_plan(vault, context=fixed_context())

    distribution_node = next(
        node
        for node in plan["nodes"]
        if node["name"] == "release_distribution_zip_smoke"
    )
    assert plan["plan_status"] == "blocked"
    assert distribution_node["can_reuse"] is False
    assert "referenced_file_stale" in distribution_node["issues"]
    assert distribution_node["refresh_target"] == "release-package-current-or-refresh"
    assert plan["authority_manifest_alignment"]["alignment_status"] == "current"
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_blocks_on_authority_manifest_distribution_zip_path_drift(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    _write_current_run_ready_evidence(vault)
    default_zip = vault / "build" / "release" / "LLMwiki-source.zip"
    custom_zip = vault / "build" / "release" / "custom-source.zip"
    custom_zip.write_bytes(default_zip.read_bytes())

    with _patch_plan_repo():
        plan = build_run_ready_plan(
            vault,
            distribution_zip="build/release/custom-source.zip",
            context=fixed_context(),
        )

    alignment = plan["authority_manifest_alignment"]
    distribution_node = next(
        node
        for node in plan["nodes"]
        if node["name"] == "release_distribution_zip_smoke"
    )
    assert plan["plan_status"] == "blocked"
    assert alignment["alignment_status"] == "stale"
    assert "input_fingerprint_stale" not in alignment["issues"]
    assert "distribution_zip_path_stale" in alignment["issues"]
    assert "referenced_file_stale" in distribution_node["issues"]
    assert "distribution_zip_path_stale" in plan["reason_codes"]
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_uses_selected_source_package_smoke_path(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    _write_current_run_ready_evidence(
        vault,
        source_package_smoke_path="tmp/custom-source-package-smoke.json",
    )

    with _patch_plan_repo():
        plan = build_run_ready_plan(
            vault,
            source_package_smoke="tmp/custom-source-package-smoke.json",
            context=fixed_context(),
        )

    source_smoke_node = next(
        node for node in plan["nodes"] if node["name"] == "source_package_smoke"
    )
    assert plan["plan_status"] == "ready"
    assert source_smoke_node["path"] == "tmp/custom-source-package-smoke.json"
    assert source_smoke_node["can_reuse"] is True
    assert plan["authority_manifest_alignment"]["alignment_status"] == "current"
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_normalizes_in_vault_absolute_source_package_smoke_path(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    _write_current_run_ready_evidence(
        vault,
        source_package_smoke_path="tmp/custom-source-package-smoke.json",
    )

    with _patch_plan_repo():
        plan = build_run_ready_plan(
            vault,
            source_package_smoke=(
                vault / "tmp/custom-source-package-smoke.json"
            ).as_posix(),
            context=fixed_context(),
        )

    source_smoke_node = next(
        node for node in plan["nodes"] if node["name"] == "source_package_smoke"
    )
    assert plan["plan_status"] == "ready"
    assert source_smoke_node["path"] == "tmp/custom-source-package-smoke.json"
    assert source_smoke_node["can_reuse"] is True
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_sanitizes_invalid_selected_source_package_smoke_path(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    _write_current_run_ready_evidence(vault)
    outside_path = (tmp_path.parent / "outside-source-package-smoke.json").as_posix()

    with _patch_plan_repo():
        plan = build_run_ready_plan(
            vault,
            source_package_smoke=outside_path,
            context=fixed_context(),
        )

    source_smoke_node = next(
        node for node in plan["nodes"] if node["name"] == "source_package_smoke"
    )
    serialized = json.dumps(plan, ensure_ascii=False)
    assert plan["plan_status"] == "blocked"
    assert source_smoke_node["path"] == "."
    assert source_smoke_node["can_reuse"] is False
    assert "not_loadable" in source_smoke_node["issues"]
    assert outside_path not in serialized
    assert tmp_path.as_posix() not in serialized
    assert validate_with_schema(plan, load_schema(PLAN_SCHEMA_PATH)) == []


def test_run_ready_plan_custom_source_smoke_target_includes_output_override(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_plan_schema(vault)
    _write_current_run_ready_evidence(vault)

    with _patch_plan_repo():
        plan = build_run_ready_plan(
            vault,
            source_package_smoke="tmp/custom-source-package-smoke.json",
            context=fixed_context(),
        )

    source_smoke_node = next(
        node for node in plan["nodes"] if node["name"] == "source_package_smoke"
    )
    expected_target = (
        "release-source-package-smoke-current-or-refresh "
        "SOURCE_PACKAGE_SMOKE_OUT=tmp/custom-source-package-smoke.json"
    )
    assert plan["plan_status"] == "blocked"
    assert source_smoke_node["path"] == "tmp/custom-source-package-smoke.json"
    assert source_smoke_node["can_reuse"] is False
    assert source_smoke_node["refresh_target"] == expected_target
    assert source_smoke_node["next_targets"] == [expected_target]
    assert plan["minimal_next_target"] == expected_target
    assert expected_target in plan["next_targets"]
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


def test_run_release_ready_passes_selected_distribution_zip_to_manifest(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_run_manifest_schema(vault)
    selected_zip = _file_identity(vault, "build/release/custom-source.zip")
    selected_smoke = "tmp/custom-source-package-smoke.json"
    _write_json(
        vault,
        selected_smoke,
        _source_package_smoke_payload(selected_zip),
    )

    clean_repo = {
        "release_source_tree_fingerprint": lambda _vault: "fp-current",
        "git_commit": lambda _vault: "abc123",
        "git_clean": lambda _vault: True,
        "remote_sync": lambda _vault: {
            "status": "pass",
            "upstream": "origin/main",
            "ahead": 0,
            "behind": 0,
        },
        "ignored_tracked_file_count": lambda _vault: 0,
    }
    commands: list[list[str]] = []

    def pass_step(
        *,
        vault: Path,
        name: str,
        command: list[str],
        expected_fingerprint: str,
        timeout_seconds: int,
    ) -> dict[str, object]:
        del vault, timeout_seconds
        commands.append(command)
        return {
            "name": name,
            "status": "pass",
            "summary_mode": "executed",
            "command": command,
            "returncode": 0,
            "duration_ms": 1,
            "source_tree_fingerprint_before": expected_fingerprint,
            "source_tree_fingerprint_after": expected_fingerprint,
            "stdout_tail": "",
            "stderr_tail": "",
        }

    with (
        patch.multiple("ops.scripts.release.release_run_ready", **clean_repo),
        patch.multiple("ops.scripts.release.release_run_manifest", **clean_repo),
        patch("ops.scripts.release.release_run_ready._command_step", pass_step),
    ):
        manifest = run_release_ready(
            vault=vault,
            out_path="build/release/release-run-manifest.json",
            make_bin="make",
            timeout_seconds=60,
            distribution_zip="build/release/custom-source.zip",
            source_package_smoke=selected_smoke,
            context=fixed_context(),
        )

    assert manifest["status"] == "pass"
    assert [
        "make",
        "release-source-package-check",
        "RELEASE_CLOSEOUT_DISTRIBUTION_ZIP=build/release/custom-source.zip",
        "SOURCE_PACKAGE_SMOKE_OUT=tmp/custom-source-package-smoke.json",
    ] in commands
    assert manifest["distribution_zip"]["path"] == "build/release/custom-source.zip"
    assert manifest["source_package_smoke"]["path"] == selected_smoke
    assert manifest["distribution_zip"]["sha256"] == selected_zip["sha256"]
    assert manifest["input_fingerprints"]["distribution_zip"] == selected_zip["sha256"]
    assert (
        manifest["input_fingerprints"]["source_package_smoke_source_zip"]
        == selected_zip["sha256"]
    )
    assert manifest["failures"] == []
    persisted = json.loads(
        (vault / "build/release/release-run-manifest.json").read_text(encoding="utf-8")
    )
    assert persisted["distribution_zip"]["path"] == "build/release/custom-source.zip"
    assert persisted["source_package_smoke"]["path"] == selected_smoke
    assert validate_with_schema(persisted, load_schema(RUN_MANIFEST_SCHEMA_PATH)) == []


def test_run_release_ready_rejects_unsafe_paths_before_make(
    tmp_path: Path,
) -> None:
    vault = tmp_path
    _copy_run_manifest_schema(vault)

    clean_repo = {
        "release_source_tree_fingerprint": lambda _vault: "fp-current",
        "git_commit": lambda _vault: "abc123",
        "git_clean": lambda _vault: True,
        "remote_sync": lambda _vault: {
            "status": "pass",
            "upstream": "origin/main",
            "ahead": 0,
            "behind": 0,
        },
        "ignored_tracked_file_count": lambda _vault: 0,
    }

    def fail_step(**_kwargs: object) -> dict[str, object]:
        raise AssertionError("unsafe selected release input reached make execution")

    with (
        patch.multiple("ops.scripts.release.release_run_ready", **clean_repo),
        patch.multiple("ops.scripts.release.release_run_manifest", **clean_repo),
        patch("ops.scripts.release.release_run_ready._command_step", fail_step),
    ):
        manifest = run_release_ready(
            vault=vault,
            out_path="build/release/release-run-manifest.json",
            make_bin="make",
            timeout_seconds=60,
            distribution_zip="/tmp/not-in-vault.zip",
            source_package_smoke="/tmp/not-in-vault-smoke.json",
            context=fixed_context(),
        )

    assert manifest["status"] == "fail"
    assert "distribution_zip_path_not_vault_relative" in manifest["failures"]
    assert "source_package_smoke_path_not_vault_relative" in manifest["failures"]
    persisted = json.loads(
        (vault / "build/release/release-run-manifest.json").read_text(encoding="utf-8")
    )
    assert persisted["distribution_zip"]["path"] == ""
    assert persisted["source_package_smoke"]["path"] == ""
    assert validate_with_schema(persisted, load_schema(RUN_MANIFEST_SCHEMA_PATH)) == []


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
