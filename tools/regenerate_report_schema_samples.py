from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ops.scripts.core.artifact_freshness_debt_runtime import stale_routing
from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.observability_artifacts_runtime import (
    build_run_artifact_fingerprint,
)
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.runtime_event_logging_runtime import (
    RuntimeEventRequest,
    build_runtime_event,
)
from ops.scripts.core.schema_runtime import (
    load_schema_with_vault_override,
    validate_or_raise,
)
from ops.scripts.mechanism.auto_improve_readiness_runtime import build_readiness_report
from ops.scripts.release.release_run_ready import build_run_ready_plan
from ops.scripts.supply_chain.cyclonedx_sbom import build_bom
from ops.scripts.supply_chain.openvex_draft import build_openvex_draft
from ops.scripts.supply_chain.sbom_export_mapping import (
    build_report as build_sbom_export_mapping_report,
)
from ops.scripts.supply_chain.sbom_readiness_gate_runtime import (
    build_gate_report as build_sbom_readiness_gate_report,
)
from ops.scripts.supply_chain.supply_chain_gate_runtime import (
    build_gate_report as build_supply_chain_gate_report,
)
from ops.scripts.supply_chain.supply_chain_provenance import (
    build_report as build_supply_chain_provenance_report,
)
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault
from tests.release_run_ready_sample_runtime import (
    _copy_plan_schema,
    _patch_plan_repo,
    _write_current_run_ready_evidence,
    fixed_context as fixed_run_ready_context,
)
from tests.supply_chain_sample_runtime import (
    LOCKED_CI_INSTALL_SNIPPET,
    seed_dependency_inputs,
    seed_source_package_evidence,
)

SEED_FIXTURE_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "report_schema_sample_seeds.json"
)
OPENVEX_SAMPLE_ID = "urn:uuid:12345678-1234-4234-9234-123456789abd"
CYCLONEDX_SAMPLE_SERIAL_NUMBER = "urn:uuid:12345678-1234-4234-9234-123456789abc"
ARTIFACT_FRESHNESS_REPORT_PATH = "ops/reports/artifact-freshness-report.json"
ARTIFACT_FRESHNESS_SCHEMA_PATH = "ops/schemas/artifact-freshness-report.schema.json"
SUPPLY_CHAIN_PROVENANCE_REPORT_PATH = "ops/reports/supply-chain-provenance.json"
SBOM_EXPORT_MAPPING_REPORT_PATH = "ops/reports/sbom-export-mapping.json"
READINESS_SAMPLE_REPORT_SPECS = {
    "ops/reports/outcome-metrics.json": (
        "ops/schemas/outcome-metrics.schema.json",
        "outcome_metrics_report",
    ),
    "ops/reports/mechanism-review-candidates.json": (
        "ops/schemas/mechanism-review-candidates.schema.json",
        "mechanism_review_candidates_report",
    ),
    "ops/reports/mutation-proposals.json": (
        "ops/schemas/mutation-proposals.schema.json",
        "mutation_proposals_report",
    ),
    ARTIFACT_FRESHNESS_REPORT_PATH: (
        ARTIFACT_FRESHNESS_SCHEMA_PATH,
        "artifact_freshness_report",
    ),
    "ops/reports/test-execution-summary.json": (
        "ops/schemas/test-execution-summary.schema.json",
        "test_execution_summary",
    ),
    "ops/reports/source-package-clean-extract.json": (
        "ops/schemas/source-package-clean-extract.schema.json",
        "source_package_clean_extract",
    ),
    "ops/reports/release-closeout-summary.json": (
        "ops/schemas/release-closeout-summary.schema.json",
        "release_closeout_summary",
    ),
    "ops/reports/release-closeout-batch-manifest.json": (
        "ops/schemas/release-closeout-batch-manifest.schema.json",
        "release_closeout_batch_manifest",
    ),
    "ops/reports/release-closeout-finality-attestation.json": (
        "ops/schemas/release-closeout-finality-attestation.schema.json",
        "release_closeout_finality_attestation",
    ),
    "ops/reports/release-evidence-cohort.json": (
        "ops/schemas/release-evidence-cohort.schema.json",
        "release_evidence_cohort",
    ),
    "tmp/release-closeout-post-check-finalizer.json": (
        "ops/schemas/release-closeout-post-check-finalizer.schema.json",
        "release_closeout_post_check_finalizer",
    ),
}
SAMPLE_GENERATION_SELF_CONTAINED = "self_contained_builder"
SAMPLE_GENERATION_FIXTURE_SEED = "fixture_seed"


@dataclass(frozen=True)
class ReportSchemaSampleCoverage:
    sample_key: str
    generation: str
    builder: str
    dependencies: tuple[str, ...] = ()


REPORT_SCHEMA_SAMPLE_COVERAGE = (
    ReportSchemaSampleCoverage("eval", SAMPLE_GENERATION_FIXTURE_SEED, ""),
    ReportSchemaSampleCoverage("eval_coverage", SAMPLE_GENERATION_FIXTURE_SEED, ""),
    ReportSchemaSampleCoverage("lint", SAMPLE_GENERATION_FIXTURE_SEED, ""),
    ReportSchemaSampleCoverage("warning_budget", SAMPLE_GENERATION_FIXTURE_SEED, ""),
    ReportSchemaSampleCoverage(
        "structural_complexity_budget", SAMPLE_GENERATION_FIXTURE_SEED, ""
    ),
    ReportSchemaSampleCoverage("stage2", SAMPLE_GENERATION_FIXTURE_SEED, ""),
    ReportSchemaSampleCoverage("mechanism_review", SAMPLE_GENERATION_FIXTURE_SEED, ""),
    ReportSchemaSampleCoverage("mutation_proposal", SAMPLE_GENERATION_FIXTURE_SEED, ""),
    ReportSchemaSampleCoverage("proposal_scope", SAMPLE_GENERATION_FIXTURE_SEED, ""),
    ReportSchemaSampleCoverage("run_telemetry", SAMPLE_GENERATION_FIXTURE_SEED, ""),
    ReportSchemaSampleCoverage(
        "generated_artifact_convergence", SAMPLE_GENERATION_FIXTURE_SEED, ""
    ),
    ReportSchemaSampleCoverage(
        "run_artifact_fingerprint",
        SAMPLE_GENERATION_SELF_CONTAINED,
        "build_run_artifact_fingerprint_schema_sample",
    ),
    ReportSchemaSampleCoverage("timeout_failure", SAMPLE_GENERATION_FIXTURE_SEED, ""),
    ReportSchemaSampleCoverage(
        "shadow_apply_report", SAMPLE_GENERATION_FIXTURE_SEED, ""
    ),
    ReportSchemaSampleCoverage(
        "rollback_rehearsal_report", SAMPLE_GENERATION_FIXTURE_SEED, ""
    ),
    ReportSchemaSampleCoverage("behavior_delta", SAMPLE_GENERATION_FIXTURE_SEED, ""),
    ReportSchemaSampleCoverage(
        "promotion_decision_trends", SAMPLE_GENERATION_FIXTURE_SEED, ""
    ),
    ReportSchemaSampleCoverage(
        "routing_provenance_aggregate", SAMPLE_GENERATION_FIXTURE_SEED, ""
    ),
    ReportSchemaSampleCoverage(
        "auto_improve_session", SAMPLE_GENERATION_FIXTURE_SEED, ""
    ),
    ReportSchemaSampleCoverage("outcome_metrics", SAMPLE_GENERATION_FIXTURE_SEED, ""),
    ReportSchemaSampleCoverage(
        "supply_chain_provenance",
        SAMPLE_GENERATION_SELF_CONTAINED,
        "build_supply_chain_schema_samples",
    ),
    ReportSchemaSampleCoverage(
        "supply_chain_gate_report",
        SAMPLE_GENERATION_SELF_CONTAINED,
        "build_supply_chain_gate_report",
        dependencies=("supply_chain_provenance",),
    ),
    ReportSchemaSampleCoverage(
        "sbom_export_mapping",
        SAMPLE_GENERATION_SELF_CONTAINED,
        "build_supply_chain_schema_samples",
        dependencies=("supply_chain_provenance",),
    ),
    ReportSchemaSampleCoverage(
        "auto_improve_readiness_report",
        SAMPLE_GENERATION_SELF_CONTAINED,
        "build_auto_improve_readiness_schema_sample",
    ),
    ReportSchemaSampleCoverage(
        "runtime_event",
        SAMPLE_GENERATION_SELF_CONTAINED,
        "build_runtime_event_schema_sample",
    ),
    ReportSchemaSampleCoverage(
        "sbom_readiness_gate_report",
        SAMPLE_GENERATION_SELF_CONTAINED,
        "build_sbom_readiness_gate_report",
        dependencies=("sbom_export_mapping",),
    ),
    ReportSchemaSampleCoverage(
        "cyclonedx_bom",
        SAMPLE_GENERATION_SELF_CONTAINED,
        "build_supply_chain_schema_samples",
        dependencies=("supply_chain_provenance", "sbom_export_mapping"),
    ),
    ReportSchemaSampleCoverage(
        "openvex_draft",
        SAMPLE_GENERATION_SELF_CONTAINED,
        "build_openvex_schema_sample",
        dependencies=("cyclonedx_bom",),
    ),
    ReportSchemaSampleCoverage("review_archive", SAMPLE_GENERATION_FIXTURE_SEED, ""),
    ReportSchemaSampleCoverage(
        "artifact_freshness_report",
        SAMPLE_GENERATION_SELF_CONTAINED,
        "build_artifact_freshness_schema_sample",
    ),
    ReportSchemaSampleCoverage(
        "release_run_ready_plan",
        SAMPLE_GENERATION_SELF_CONTAINED,
        "build_release_run_ready_plan_schema_sample",
    ),
)


def report_schema_sample_coverage_table() -> tuple[ReportSchemaSampleCoverage, ...]:
    return REPORT_SCHEMA_SAMPLE_COVERAGE


def self_contained_report_schema_sample_keys() -> tuple[str, ...]:
    return tuple(
        entry.sample_key
        for entry in REPORT_SCHEMA_SAMPLE_COVERAGE
        if entry.generation == SAMPLE_GENERATION_SELF_CONTAINED
    )


def self_contained_report_schema_sample_update_keys() -> tuple[str, ...]:
    return self_contained_report_schema_sample_keys()


def seed_preserved_report_schema_sample_keys() -> tuple[str, ...]:
    return tuple(
        entry.sample_key
        for entry in REPORT_SCHEMA_SAMPLE_COVERAGE
        if entry.generation == SAMPLE_GENERATION_FIXTURE_SEED
    )


def _assert_seed_sample_coverage_matches_payload(payload: dict) -> None:
    seed_keys = list(seed_preserved_report_schema_sample_keys())
    payload_keys = list(payload)
    if seed_keys == payload_keys:
        return
    missing_from_seed = sorted(set(seed_keys) - set(payload_keys))
    unexpected_seed_keys = sorted(set(payload_keys) - set(seed_keys))
    first_order_mismatch = ""
    if not missing_from_seed and not unexpected_seed_keys:
        for index, (expected_key, actual_key) in enumerate(
            zip(seed_keys, payload_keys, strict=True)
        ):
            if expected_key != actual_key:
                first_order_mismatch = (
                    f", first_order_mismatch=index {index} "
                    f"expected={expected_key!r} actual={actual_key!r}"
                )
                break
    raise ValueError(
        "report schema sample seed fixture does not match fixture_seed coverage keys: "
        f"missing_from_seed={missing_from_seed}, "
        f"unexpected_seed_keys={unexpected_seed_keys}"
        f"{first_order_mismatch}"
    )


def load_report_schema_sample_seeds(
    seed_fixture_path: Path = SEED_FIXTURE_PATH,
) -> dict:
    payload = json.loads(seed_fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"expected report schema sample seed object: {seed_fixture_path}")
    _assert_seed_sample_coverage_matches_payload(payload)
    return payload


def _assert_sample_coverage_matches_payload(payload: dict) -> None:
    coverage_keys = [entry.sample_key for entry in REPORT_SCHEMA_SAMPLE_COVERAGE]
    payload_keys = list(payload)
    if coverage_keys == payload_keys:
        return
    missing_from_coverage = sorted(set(payload_keys) - set(coverage_keys))
    missing_from_payload = sorted(set(coverage_keys) - set(payload_keys))
    raise ValueError(
        "report schema sample coverage table does not match fixture keys: "
        f"missing_from_coverage={missing_from_coverage}, "
        f"missing_from_payload={missing_from_payload}"
    )


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 15, 0, 0, tzinfo=dt.UTC),
    )


def _normalize_sample_vault_text_newlines(vault: Path) -> None:
    for path in sorted(vault.rglob("*")):
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\r" not in raw:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        if normalized == text:
            continue
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(normalized)


def _stable_json_text(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _write_stable_json_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(_stable_json_text(payload))


def seed_openvex_sample_vault(vault: Path) -> None:
    seed_minimal_vault(vault)
    seed_dependency_inputs(vault)
    seed_source_package_evidence(vault)
    (vault / "README.md").write_text("root\n", encoding="utf-8")
    (vault / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    (vault / "THIRD_PARTY_NOTICES.md").write_text("# Notices\n", encoding="utf-8")
    (vault / "CONTRIBUTING.md").write_text("# Contributing\n", encoding="utf-8")
    (vault / "SECURITY.md").write_text("# Security\n", encoding="utf-8")
    (vault / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")
    (vault / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
    (vault / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (vault / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (vault / ".github" / "workflows" / "ci.yml").write_text(
        LOCKED_CI_INSTALL_SNIPPET,
        encoding="utf-8",
    )


def seed_supply_chain_sample_vault(vault: Path) -> None:
    seed_openvex_sample_vault(vault)
    (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "scripts" / "example.py").write_text(
        "print('ok')\n", encoding="utf-8"
    )
    (vault / "ops" / "operator").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "operator" / "operator-release-summary.json").write_text(
        "{}", encoding="utf-8"
    )
    (vault / "ops" / "script-output-surfaces.json").write_text("{}", encoding="utf-8")
    (vault / "tests" / "test_example.py").parent.mkdir(parents=True, exist_ok=True)
    (vault / "tests" / "test_example.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )


def build_supply_chain_schema_samples() -> dict[str, dict]:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_supply_chain_sample_vault(vault)
        _normalize_sample_vault_text_newlines(vault)
        provenance = build_supply_chain_provenance_report(
            vault, context=fixed_context()
        )
        provenance_path = vault / SUPPLY_CHAIN_PROVENANCE_REPORT_PATH
        _write_stable_json_file(provenance_path, provenance)
        mapping = build_sbom_export_mapping_report(
            vault,
            context=fixed_context(),
            provenance_report=provenance,
        )
        mapping_path = vault / SBOM_EXPORT_MAPPING_REPORT_PATH
        _write_stable_json_file(mapping_path, mapping)
        gate = build_supply_chain_gate_report(
            vault,
            fixed_context(),
            provenance_report=provenance,
        )
        readiness_gate = build_sbom_readiness_gate_report(
            vault,
            context=fixed_context(),
            mapping_report=mapping,
        )
        cyclonedx = build_bom(
            vault,
            context=fixed_context(),
            provenance_report=provenance,
            mapping_report=mapping,
        )
        cyclonedx["serialNumber"] = CYCLONEDX_SAMPLE_SERIAL_NUMBER
        return {
            "supply_chain_provenance": provenance,
            "supply_chain_gate_report": gate,
            "sbom_export_mapping": mapping,
            "sbom_readiness_gate_report": readiness_gate,
            "cyclonedx_bom": cyclonedx,
        }


def build_openvex_schema_sample(cyclonedx_sample: dict) -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_openvex_sample_vault(vault)
        _write_stable_json_file(
            vault / "ops" / "reports" / "cyclonedx-bom.json",
            cyclonedx_sample,
        )
        _normalize_sample_vault_text_newlines(vault)
        return build_openvex_draft(
            vault,
            context=fixed_context(),
            document_id=OPENVEX_SAMPLE_ID,
        )


def _artifact_freshness_zero_summary() -> dict[str, int]:
    return {
        "artifact_count": 0,
        "json_artifact_count": 0,
        "scanned_text_artifact_count": 0,
        "stale_artifact_count": 0,
        "mtime_sensitive_artifact_count": 0,
        "root_ephemeral_artifact_count": 0,
        "run_log_placeholder_count": 0,
        "unknown_currentness_artifact_count": 0,
        "source_revision_provenance_only_artifact_count": 0,
        "non_utf8_text_artifact_count": 0,
        "missing_schema_count": 0,
        "missing_artifact_envelope_count": 0,
        "schema_invalid_artifact_count": 0,
        "schema_unavailable_artifact_count": 0,
        "safe_to_backfill_artifact_count": 0,
        "stable_contract_debt_artifact_count": 0,
        "stable_contract_debt_issue_count": 0,
        "mtime_sensitive_attention_artifact_count": 0,
        "mtime_sensitive_attention_issue_count": 0,
        "operational_attention_artifact_count": 0,
        "operational_attention_issue_count": 0,
    }


def build_artifact_freshness_schema_sample_for_vault(vault: Path) -> dict:
    policy, resolved_policy_path = load_policy(
        vault, "ops/policies/wiki-maintainer-policy.yaml"
    )
    report = {
        **build_canonical_report_envelope(
            vault,
            generated_at=fixed_context().isoformat_z(),
            artifact_kind="artifact_freshness_report",
            producer="ops.scripts.artifact_freshness_runtime",
            source_command="python -m ops.scripts.artifact_freshness_runtime --vault .",
            resolved_policy_path=resolved_policy_path,
            schema_path=ARTIFACT_FRESHNESS_SCHEMA_PATH,
            source_paths=[],
        ),
        "vault": ".",
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy["version"],
        },
        "mtime_source": "embedded_currentness",
        "zip_metadata_path": "",
        "status": "pass",
        "gate_effect": "none",
        "recommended_next_action": "No artifact freshness debt detected.",
        "stale_routing": stale_routing(
            [],
            root_ephemeral_count=0,
            non_utf8_count=0,
        ),
        "safe_to_backfill": False,
        "mtime_sensitive": False,
        "summary": _artifact_freshness_zero_summary(),
        "top_debt": [],
        "top_debt_files": [],
        "debt_queues": [],
        "owner_surface": [],
        "root_ephemeral_patterns": [],
        "root_ephemeral_artifacts": [],
        "run_log_placeholders": [],
        "non_utf8_text_artifacts": [],
        "artifact_records": [],
    }
    validate_or_raise(
        report,
        load_schema_with_vault_override(vault, ARTIFACT_FRESHNESS_SCHEMA_PATH),
        "artifact freshness schema sample validation failed",
    )
    return report


def build_artifact_freshness_schema_sample() -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        _normalize_sample_vault_text_newlines(vault)
        return build_artifact_freshness_schema_sample_for_vault(vault)


def build_runtime_event_schema_sample() -> dict:
    return build_runtime_event(
        RuntimeEventRequest(
            context=fixed_context(),
            run_id="run-20260415-example",
            session_id="auto-improve-2026-04-15",
            phase="queue_blocked",
            component="auto_improve_readiness",
            decision="warn",
            decision_reason="recent_log_overlap",
            artifact_path="ops/reports/auto-improve-readiness.json",
            duration_ms=12,
            policy_version=1,
            proposal_id="repeated_same_eval_or_discard__example",
            candidate_id="mechanism_eval_stagnation_candidate__example",
            blocker="recent_log_overlap",
            blocker_kind="hard",
        )
    )


def build_run_artifact_fingerprint_schema_sample() -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        run_id = "run-20260415-example"
        _write_stable_json_file(
            vault / "runs" / run_id / "run-telemetry.json",
            {
                "$schema": "ops/schemas/run-telemetry.schema.json",
                "session_id": "auto-improve-2026-04-15",
                "run_id": run_id,
                "generated_at": fixed_context().isoformat_z(),
                "proposal_id": "repeated_same_eval_or_discard__example",
                "proposal_snapshot": "",
                "scope_freeze": "",
                "routing_reports": [],
                "executor_reports": [],
                "primary_targets": ["ops/scripts/example.py"],
                "supporting_targets": [],
                "test_files": ["tests/test_example.py"],
                "phase_durations": {"routing": 1.25, "execution": 12.5},
                "failure_taxonomy": "",
                "decision": "PROMOTE",
                "finalized": True,
                "finalize_result": {"run_id": run_id},
            },
        )
        _write_stable_json_file(
            vault / SUPPLY_CHAIN_PROVENANCE_REPORT_PATH,
            {
                "generated_at": fixed_context().isoformat_z(),
                "status": "pass",
            },
        )
        _normalize_sample_vault_text_newlines(vault)
        return build_run_artifact_fingerprint(
            vault,
            run_id,
            context=fixed_context(),
        )


def _write_readiness_sample_report(
    vault: Path, relative_path: str, payload: dict
) -> None:
    policy, resolved_policy_path = load_policy(
        vault, "ops/policies/wiki-maintainer-policy.yaml"
    )
    schema_path, artifact_kind = READINESS_SAMPLE_REPORT_SPECS[relative_path]
    path = vault / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    enveloped = {
        **build_canonical_report_envelope(
            vault,
            generated_at=fixed_context().isoformat_z(),
            artifact_kind=artifact_kind,
            producer="tools.regenerate_report_schema_samples",
            source_command="python tools/regenerate_report_schema_samples.py",
            resolved_policy_path=resolved_policy_path,
            schema_path=schema_path,
            source_paths=[],
        ),
        "vault": ".",
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy["version"],
        },
        **payload,
    }
    _write_stable_json_file(path, enveloped)


def _write_goal_worktree_guard_sample_report(vault: Path) -> None:
    _policy, resolved_policy_path = load_policy(
        vault, "ops/policies/wiki-maintainer-policy.yaml"
    )
    payload = {
        **build_canonical_report_envelope(
            vault,
            generated_at=fixed_context().isoformat_z(),
            artifact_kind="goal_worktree_guard",
            producer="tools.regenerate_report_schema_samples",
            source_command="python tools/regenerate_report_schema_samples.py",
            resolved_policy_path=resolved_policy_path,
            schema_path="ops/schemas/goal-worktree-guard.schema.json",
            source_paths=[],
        ),
        "vault": ".",
        "requested_mode": "git",
        "detected_mode": "git_worktree",
        "public_source_layout": {
            "required_paths": ["ops", "tests", "mk", "README.md", "Makefile"],
            "present": True,
            "missing_paths": [],
        },
        "git": {
            "available": True,
            "inside_worktree": True,
            "worktree_root": ".",
            "head_sha": "0" * 40,
            "branch": "main",
            "dirty_entry_count": 0,
            "status_porcelain_sha256": "0" * 64,
            "status_codes": {},
            "error": "",
        },
        "decisions": {
            "can_execute_goal_runtime": True,
            "can_promote_result": True,
            "zip_mode_replay_only": False,
            "fatal_blockers": [],
            "promotion_blockers": [],
        },
        "blockers": [],
        "status": "pass",
    }
    path = vault / "ops" / "reports" / "goal-worktree-guard.json"
    _write_stable_json_file(path, payload)


def _seed_readiness_release_contract_reports(vault: Path) -> None:
    artifact_freshness = build_artifact_freshness_schema_sample_for_vault(vault)
    artifact_path = vault / ARTIFACT_FRESHNESS_REPORT_PATH
    _write_stable_json_file(artifact_path, artifact_freshness)
    _write_readiness_sample_report(
        vault,
        "ops/reports/test-execution-summary.json",
        {
            "status": "pass",
            "deselection_lifecycle": {"status": "pass"},
        },
    )
    _write_readiness_sample_report(
        vault,
        "ops/reports/source-package-clean-extract.json",
        {
            "status": "pass",
            "source_package_reproducibility_status": "pass",
            "deselection_budget_status": {"status": "pass"},
        },
    )
    _write_readiness_sample_report(
        vault,
        "ops/reports/release-closeout-summary.json",
        {
            "status": "pass",
            "clean_release_ready": True,
            "release_readiness_state": "clean_pass",
            "machine_release_allowed": True,
            "operator_release_allowed": True,
        },
    )
    _write_readiness_sample_report(
        vault,
        "ops/reports/release-closeout-batch-manifest.json",
        {
            "status": "pass",
            "release_authority_status": "clean_pass",
            "sealed_release_status": "sealed_clean_pass",
            "distribution_package": {"status": "materialized"},
        },
    )
    _write_readiness_sample_report(
        vault,
        "ops/reports/release-closeout-finality-attestation.json",
        {
            "finality_status": "pass",
            "finality_failures": [],
        },
    )
    _write_readiness_sample_report(
        vault,
        "ops/reports/release-evidence-cohort.json",
        {
            "status": "pass",
            "summary": {"clean_lane_contract_status": "pass"},
            "cohort": {
                "strict_same_fingerprint": True,
                "component_fingerprint_count": 1,
            },
        },
    )
    _write_readiness_sample_report(
        vault,
        "tmp/release-closeout-post-check-finalizer.json",
        {
            "status": "pass",
            "refresh_required": False,
            "affected_path_count": 0,
        },
    )


def _seed_readiness_queue_reports(vault: Path) -> None:
    _write_readiness_sample_report(
        vault,
        "ops/reports/outcome-metrics.json",
        {
            "summary": {
                "attempts_considered": 3,
                "recent_window": 20,
                "recent_attempt_count": 3,
                "session_reports_considered": 0,
            },
            "metrics": {
                "rework_count": 0,
                "moving_averages": {"hold": 0.0, "discard": 0.0},
                "defect_escape_proxy": {"count": 0},
            },
            "recent_attempts": [],
        },
    )
    _write_readiness_sample_report(
        vault,
        "ops/reports/mechanism-review-candidates.json",
        {
            "status": "attention",
            "summary": {"candidates_emitted": 0},
            "diagnostics": {
                "bootstrap": {
                    "status": "needs_history",
                    "summary": "fallback family still needs more comparable runs",
                },
                "session_calibration": {"status": "no_session_context"},
            },
            "candidates": [],
        },
    )
    _write_readiness_sample_report(
        vault,
        "ops/reports/mutation-proposals.json",
        {
            "status": "attention",
            "summary": {
                "source_candidates_read": 0,
                "proposals_emitted": 0,
                "blocked_proposals": 0,
                "next_run_repair_proposals": 0,
                "queue_pressure_summary": "no proposals emitted | mechanism review emitted zero candidates",
            },
            "diagnostics": {
                "evidence_gaps": [
                    "mechanism review emitted zero candidates",
                    "outcome_metrics: attempts_considered=3 is below min_attempts_considered=10",
                ],
                "next_run_decision_queue": {
                    "session_reports_scanned": 0,
                    "decisions_considered": 0,
                    "open_carry_forward_decisions": 0,
                    "repair_proposals_emitted": 0,
                    "decision_counts": {},
                    "action_counts": {},
                    "selected_target_proposal_ids": [],
                },
            },
            "proposals": [],
        },
    )


def _align_readiness_sample_blocker_next_steps(report: dict) -> None:
    if report.get("release_blockers"):
        report["release_blockers"][0]["recommended_next_step"] = report["next_action"]
        report["learning_blockers"][0]["recommended_next_step"] = report["next_action"]
        report["promotion_blockers"][0]["recommended_next_step"] = report["next_action"]


def build_auto_improve_readiness_schema_sample() -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        _normalize_sample_vault_text_newlines(vault)
        _seed_readiness_release_contract_reports(vault)
        _seed_readiness_queue_reports(vault)
        _write_goal_worktree_guard_sample_report(vault)
        _normalize_sample_vault_text_newlines(vault)

        report = build_readiness_report(vault, context=fixed_context())
        _align_readiness_sample_blocker_next_steps(report)
        return report


def build_release_run_ready_plan_schema_sample() -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        _copy_plan_schema(vault)
        _write_current_run_ready_evidence(vault)
        _normalize_sample_vault_text_newlines(vault)
        with _patch_plan_repo():
            return build_run_ready_plan(vault, context=fixed_run_ready_context())


def _build_self_contained_sample_updates() -> dict:
    updates = build_supply_chain_schema_samples()
    updates["artifact_freshness_report"] = build_artifact_freshness_schema_sample()
    updates["runtime_event"] = build_runtime_event_schema_sample()
    updates["run_artifact_fingerprint"] = build_run_artifact_fingerprint_schema_sample()
    updates["auto_improve_readiness_report"] = (
        build_auto_improve_readiness_schema_sample()
    )
    updates["release_run_ready_plan"] = build_release_run_ready_plan_schema_sample()
    updates["openvex_draft"] = build_openvex_schema_sample(updates["cyclonedx_bom"])
    expected_keys = set(self_contained_report_schema_sample_update_keys())
    if set(updates) != expected_keys:
        raise ValueError(
            "self-contained report schema sample updates do not match coverage table: "
            f"missing_updates={sorted(expected_keys - set(updates))}, "
            f"unexpected_updates={sorted(set(updates) - expected_keys)}"
        )
    return updates


def _report_schema_samples_with_self_contained_updates(
    *,
    seed_fixture_path: Path = SEED_FIXTURE_PATH,
) -> dict:
    seed_payload = load_report_schema_sample_seeds(seed_fixture_path)
    updates = _build_self_contained_sample_updates()
    payload = {}
    for entry in REPORT_SCHEMA_SAMPLE_COVERAGE:
        if entry.sample_key in updates:
            payload[entry.sample_key] = updates[entry.sample_key]
        elif entry.generation == SAMPLE_GENERATION_FIXTURE_SEED:
            payload[entry.sample_key] = seed_payload[entry.sample_key]
    _assert_sample_coverage_matches_payload(payload)
    return payload


def regenerate_report_schema_samples(
    *,
    out_path: Path | None = None,
    seed_fixture_path: Path = SEED_FIXTURE_PATH,
) -> dict:
    payload = _report_schema_samples_with_self_contained_updates(
        seed_fixture_path=seed_fixture_path,
    )
    if out_path is not None:
        _write_stable_json_file(out_path, payload)
    return payload


def candidate_report_schema_samples(
    *,
    seed_fixture_path: Path = SEED_FIXTURE_PATH,
) -> dict:
    return _report_schema_samples_with_self_contained_updates(
        seed_fixture_path=seed_fixture_path,
    )


def check_report_schema_samples(
    *,
    seed_fixture_path: Path = SEED_FIXTURE_PATH,
) -> list[str]:
    candidate_report_schema_samples(seed_fixture_path=seed_fixture_path)
    return []


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-fixture", default=str(SEED_FIXTURE_PATH))
    parser.add_argument(
        "--out",
        default=None,
        help="Optional debug output path for the generated full candidate.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the seed fixture cannot produce the generated sample candidate.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.check:
            check_report_schema_samples(seed_fixture_path=Path(args.seed_fixture))
            return 0
        regenerate_report_schema_samples(
            out_path=Path(args.out) if args.out else None,
            seed_fixture_path=Path(args.seed_fixture),
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(
            "report schema sample generation failed: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1
    if args.out:
        print(args.out)
    else:
        print("report schema samples generated from seed fixture")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
