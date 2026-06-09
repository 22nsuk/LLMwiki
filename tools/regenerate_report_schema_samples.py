from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.auto_improve_readiness_runtime import build_readiness_report
from ops.scripts.cyclonedx_sbom import build_bom
from ops.scripts.openvex_draft import build_openvex_draft
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.sbom_export_mapping import (
    build_report as build_sbom_export_mapping_report,
)
from ops.scripts.supply_chain_provenance import (
    build_report as build_supply_chain_provenance_report,
)

from ops.scripts.release.release_run_ready import build_run_ready_plan
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault
from tests.test_release_run_ready import (
    _copy_plan_schema,
    _patch_plan_repo,
    _write_current_run_ready_evidence,
    fixed_context as fixed_run_ready_context,
)
from tests.test_supply_chain_provenance import (
    LOCKED_CI_INSTALL_SNIPPET,
    seed_dependency_inputs,
    seed_source_package_evidence,
)

FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "report_schema_samples.json"
OPENVEX_SAMPLE_ID = "urn:uuid:12345678-1234-4234-9234-123456789abd"
CYCLONEDX_SAMPLE_SERIAL_NUMBER = "urn:uuid:12345678-1234-4234-9234-123456789abc"
ARTIFACT_FRESHNESS_REPORT_PATH = "ops/reports/artifact-freshness-report.json"
ARTIFACT_FRESHNESS_SCHEMA_PATH = "ops/schemas/artifact-freshness-report.schema.json"
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


def load_report_schema_samples(fixture_path: Path = FIXTURE_PATH) -> dict:
    return json.loads(fixture_path.read_text(encoding="utf-8"))


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
    (vault / "ops" / "scripts" / "example.py").write_text("print('ok')\n", encoding="utf-8")
    (vault / "ops" / "operator").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "operator" / "operator-release-summary.json").write_text("{}", encoding="utf-8")
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
        provenance = build_supply_chain_provenance_report(vault, context=fixed_context())
        mapping = build_sbom_export_mapping_report(
            vault,
            context=fixed_context(),
            provenance_report=provenance,
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
            "sbom_export_mapping": mapping,
            "cyclonedx_bom": cyclonedx,
        }


def build_openvex_schema_sample(cyclonedx_sample: dict | None = None) -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_openvex_sample_vault(vault)
        samples = load_report_schema_samples() if cyclonedx_sample is None else {"cyclonedx_bom": cyclonedx_sample}
        (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        (vault / "ops" / "reports" / "cyclonedx-bom.json").write_text(
            json.dumps(samples["cyclonedx_bom"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
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
    policy, resolved_policy_path = load_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")
    return {
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


def build_artifact_freshness_schema_sample() -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        _normalize_sample_vault_text_newlines(vault)
        return build_artifact_freshness_schema_sample_for_vault(vault)


def _write_readiness_sample_report(vault: Path, relative_path: str, payload: dict) -> None:
    policy, resolved_policy_path = load_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")
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
    path.write_text(json.dumps(enveloped, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_goal_worktree_guard_sample_report(vault: Path) -> None:
    _policy, resolved_policy_path = load_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _seed_readiness_release_contract_reports(vault: Path) -> None:
    artifact_freshness = build_artifact_freshness_schema_sample_for_vault(vault)
    artifact_path = vault / ARTIFACT_FRESHNESS_REPORT_PATH
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact_freshness, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
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


def regenerate_report_schema_samples(
    fixture_path: Path = FIXTURE_PATH,
    *,
    include_openvex: bool = True,
) -> dict:
    payload = load_report_schema_samples(fixture_path)
    payload.update(build_supply_chain_schema_samples())
    payload["artifact_freshness_report"] = build_artifact_freshness_schema_sample()
    payload["auto_improve_readiness_report"] = build_auto_improve_readiness_schema_sample()
    payload["release_run_ready_plan"] = build_release_run_ready_plan_schema_sample()
    if include_openvex:
        payload["openvex_draft"] = build_openvex_schema_sample(payload["cyclonedx_bom"])
    fixture_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def candidate_report_schema_samples(
    fixture_path: Path = FIXTURE_PATH,
    *,
    include_openvex: bool = True,
) -> dict:
    payload = load_report_schema_samples(fixture_path)
    payload.update(build_supply_chain_schema_samples())
    payload["artifact_freshness_report"] = build_artifact_freshness_schema_sample()
    payload["auto_improve_readiness_report"] = build_auto_improve_readiness_schema_sample()
    payload["release_run_ready_plan"] = build_release_run_ready_plan_schema_sample()
    if include_openvex:
        payload["openvex_draft"] = build_openvex_schema_sample(payload["cyclonedx_bom"])
    return payload


def check_report_schema_samples(
    fixture_path: Path = FIXTURE_PATH,
    *,
    include_openvex: bool = True,
) -> list[str]:
    expected = load_report_schema_samples(fixture_path)
    candidate = candidate_report_schema_samples(
        fixture_path,
        include_openvex=include_openvex,
    )
    if candidate == expected:
        return []
    expected_text = json.dumps(expected, ensure_ascii=False, indent=2).splitlines()
    candidate_text = json.dumps(candidate, ensure_ascii=False, indent=2).splitlines()
    return list(
        difflib.unified_diff(
            expected_text,
            candidate_text,
            fromfile=str(fixture_path),
            tofile="generated-candidate",
            lineterm="",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(FIXTURE_PATH))
    parser.add_argument(
        "--skip-openvex",
        action="store_true",
        help="Leave the openvex_draft sample untouched.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if regenerated samples differ from the checked-in fixture.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.check:
        diff = check_report_schema_samples(
            Path(args.fixture),
            include_openvex=not args.skip_openvex,
        )
        if diff:
            print("report schema samples are stale; run tools/regenerate_report_schema_samples.py", file=sys.stderr)
            print("\n".join(diff[:200]), file=sys.stderr)
            return 1
        return 0
    regenerate_report_schema_samples(
        Path(args.fixture),
        include_openvex=not args.skip_openvex,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
