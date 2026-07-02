from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

import hypothesis.strategies as st
import pytest
from hypothesis import given

from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.core.source_tree_fingerprint_runtime import (
    release_source_tree_change_sample,
)
from ops.scripts.release.release_closeout_summary import (
    BASE_PROFILE,
    PROVENANCE_PROFILE,
    SBOM_PROFILE,
    SOURCE_SPECS,
    _artifact_freshness_gate,
    _closeout_render_inputs,
    _load_closeout_sources,
    _prepare_closeout_state,
    _render_closeout_report,
    build_report,
    main,
    source_specs_for_profile,
    write_report,
)
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-closeout-summary.schema.json"
ENVELOPE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "artifact-envelope.schema.json"
SIGNOFF_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "learning-readiness-signoff.schema.json"
FIXED_POINT_POLICY_PATH = "ops/policies/release-closeout-fixed-point.json"
SCHEMA_BY_KIND = {
    "bootstrap_preflight_report": "ops/schemas/bootstrap-preflight-report.schema.json",
    "release_smoke_report": "ops/schemas/release-smoke-report.schema.json",
    "test_execution_summary": "ops/schemas/test-execution-summary.schema.json",
    "raw_registry_preflight_report": "ops/schemas/raw-registry-preflight-report.schema.json",
    "artifact_freshness_report": "ops/schemas/artifact-freshness-report.schema.json",
    "generated_artifact_index_report": "ops/schemas/generated-artifact-index.schema.json",
    "auto_improve_readiness_report": "ops/schemas/auto-improve-readiness-report.schema.json",
    "source_package_clean_extract": "ops/schemas/source-package-clean-extract.schema.json",
    "external_report_reference_manifest": "ops/schemas/external-report-reference-manifest.schema.json",
    "supply_chain_gate_report": "ops/schemas/supply-chain-gate-report.schema.json",
    "sbom_readiness_gate_report": "ops/schemas/sbom-readiness-gate-report.schema.json",
}


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 29, 9, 0, tzinfo=dt.UTC),
    )


def _freshness_components(*, ready: bool = True, source_status: str = "pass") -> list[dict[str, Any]]:
    return [
        {
            "name": "artifact_freshness",
            "load_status": "ok",
            "ready": ready,
            "source_status": source_status,
        }
    ]


def _freshness_payload(
    *,
    status: str,
    summary: dict[str, int] | None = None,
    artifact_records: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    payload: dict[str, Any] = {"status": status}
    if summary is not None:
        payload["summary"] = summary
    if artifact_records is not None:
        payload["artifact_records"] = artifact_records
    return {"artifact_freshness": payload}


@given(
    schema_invalid_count=st.integers(min_value=0, max_value=5),
    stable_contract_debt_issue_count=st.integers(min_value=0, max_value=5),
)
def test_property_3_clean_pass_implies_not_blocking(
    schema_invalid_count: int,
    stable_contract_debt_issue_count: int,
) -> None:
    """Feature: release-evidence-sync, Property 3: clean_pass implies not blocking"""
    gate = _artifact_freshness_gate(
        REPO_ROOT,
        _freshness_components(ready=True, source_status="pass"),
        _freshness_payload(
            status="pass",
            summary={
                "schema_invalid_artifact_count": schema_invalid_count,
                "stable_contract_debt_issue_count": stable_contract_debt_issue_count,
            },
        ),
    )

    if schema_invalid_count == 0:
        assert gate["display_effect"] == "none"
        assert gate["blocking"] is False
    else:
        assert gate["display_effect"] == "advisory"
        assert gate["blocking"] is False


@given(
    stable_contract_debt_issue_count=st.integers(min_value=1, max_value=5),
    use_release_owned_attention=st.booleans(),
)
def test_property_4_release_owned_only_attention_is_advisory(
    stable_contract_debt_issue_count: int,
    use_release_owned_attention: bool,
) -> None:
    """Feature: release-evidence-sync, Property 4: release-owned-only attention is advisory"""
    summary = {
        "schema_invalid_artifact_count": 0,
        "schema_unavailable_artifact_count": 0,
        "root_ephemeral_artifact_count": 0,
        "non_utf8_text_artifact_count": 0,
        "stale_artifact_count": 0 if not use_release_owned_attention else 1,
        "mtime_sensitive_attention_artifact_count": 0,
        "mtime_sensitive_attention_issue_count": 0,
        "operational_attention_artifact_count": 0 if not use_release_owned_attention else 1,
        "operational_attention_issue_count": 0 if not use_release_owned_attention else 1,
        "stable_contract_debt_issue_count": stable_contract_debt_issue_count if not use_release_owned_attention else 0,
    }
    artifact_records = None
    if use_release_owned_attention:
        artifact_records = [
            {
                "path": "ops/reports/auto-improve-readiness.json",
                "issues": ["source_tree_fingerprint_mismatch"],
            }
        ]
    gate = _artifact_freshness_gate(
        REPO_ROOT,
        _freshness_components(ready=False, source_status="attention"),
        _freshness_payload(
            status="attention",
            summary=summary,
            artifact_records=artifact_records,
        ),
    )

    assert gate["gate_effect"] == "advisory"
    assert gate["display_effect"] == "advisory"
    assert gate["blocking"] is False


class ReleaseCloseoutSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        fixed_point_policy = self.vault / FIXED_POINT_POLICY_PATH
        fixed_point_policy.parent.mkdir(parents=True, exist_ok=True)
        fixed_point_policy.write_text(
            (REPO_ROOT / FIXED_POINT_POLICY_PATH).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        self._normalize_release_surface_mtimes()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _assert_release_decision(
        self,
        report: dict[str, Any],
        *,
        state: str,
        machine_release_allowed: bool,
        operator_release_allowed: bool,
        requires_accepted_risk_review: bool,
    ) -> None:
        self.assertEqual(report["release_readiness_state"], state)
        self.assertEqual(report["machine_release_allowed"], machine_release_allowed)
        self.assertEqual(report["operator_release_allowed"], operator_release_allowed)
        self.assertEqual(report["requires_accepted_risk_review"], requires_accepted_risk_review)

    def _source_spec(self, name: str) -> Any:
        for profile in (BASE_PROFILE, PROVENANCE_PROFILE, SBOM_PROFILE):
            for spec in source_specs_for_profile(profile):
                if spec.name == name:
                    return spec
        raise AssertionError(f"missing source spec fixture for {name}")

    def _write_source_report(self, name: str, payload: dict[str, Any]) -> None:
        spec = self._source_spec(name)
        policy, resolved_policy_path = load_policy(self.vault, "ops/policies/wiki-maintainer-policy.yaml")
        report = {
            **build_canonical_report_envelope(
                self.vault,
                generated_at="2026-04-29T08:00:00Z",
                artifact_kind=spec.artifact_kind,
                producer=f"tests.{name}",
                source_command=f"pytest {name}",
                resolved_policy_path=resolved_policy_path,
                schema_path=SCHEMA_BY_KIND[spec.artifact_kind],
                source_paths=[],
            ),
            "vault": report_path(self.vault, self.vault),
            "policy": {
                "path": report_path(self.vault, resolved_policy_path),
                "version": policy.get("version"),
            },
            **payload,
        }
        path = self.vault / spec.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        generated_at = dt.datetime.fromisoformat(str(report["generated_at"]).replace("Z", "+00:00"))
        os.utime(path, (generated_at.timestamp(), generated_at.timestamp()))

    def _write_release_surface_file(self, rel_path: str, text: str) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_dependency_lockfiles(self) -> None:
        self._write_release_surface_file("pyproject.toml", "[project]\nname = 'llmwiki-test'\n")
        self._write_release_surface_file(
            "uv.lock",
            "version = 1\n[[package]]\nname = 'pytest'\nversion = '8.3.5'\n",
        )
        for rel_path in (
            "pyproject.toml",
            "uv.lock",
        ):
            self._touch_release_surface_file(rel_path, "2026-04-29T07:59:59Z")

    def _touch_release_surface_file(self, rel_path: str, when: str) -> None:
        path = self.vault / rel_path
        timestamp = dt.datetime.fromisoformat(when.replace("Z", "+00:00")).timestamp()
        os.utime(path, (timestamp, timestamp))

    def _normalize_release_surface_mtimes(self, when: str = "2026-04-29T07:59:59Z") -> None:
        timestamp = dt.datetime.fromisoformat(when.replace("Z", "+00:00")).timestamp()
        sample = release_source_tree_change_sample(
            self.vault,
            generated_at="1970-01-01T00:00:00Z",
            path_limit=100000,
        )
        for item in sample["changed_after_generated_at"]:
            path = self.vault / str(item["path"])
            os.utime(path, (timestamp, timestamp))

    def _write_learning_signoff(self, payload: dict[str, Any] | None = None) -> None:
        policy, resolved_policy_path = load_policy(self.vault, "ops/policies/wiki-maintainer-policy.yaml")
        report = {
            **build_canonical_report_envelope(
                self.vault,
                generated_at="2026-04-29T08:30:00Z",
                artifact_kind="learning_readiness_signoff",
                producer="tests.learning_readiness_signoff",
                source_command="operator signoff fixture",
                resolved_policy_path=resolved_policy_path,
                schema_path="ops/schemas/learning-readiness-signoff.schema.json",
                source_paths=[],
            ),
            "vault": report_path(self.vault, self.vault),
            "policy": {
                "path": report_path(self.vault, resolved_policy_path),
                "version": policy.get("version"),
            },
            "linked_blocker_id": "learning_blocked_by_review_required",
            "accepted_by": "operator@example.test",
            "accepted_at": "2026-04-29T08:30:00Z",
            "expires_at": "2026-04-30T08:30:00Z",
            "risk_owner": "runtime-maintainer",
            "revalidation_condition": "rerun release evidence closeout before the next release",
            "rollback_trigger": "learning telemetry regresses or auto-improve queue blocks",
            **(payload or {}),
        }
        path = self.vault / "ops" / "reports" / "learning-readiness-signoff.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_learning_delta_scoreboard(
        self,
        *,
        claims_learning_improved: bool,
        learning_claim_allowed: bool = False,
        guard_status: str = "blocked",
    ) -> None:
        path = self.vault / "ops" / "reports" / "learning-delta-scoreboard.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "status": "pass",
                    "summary": {
                        "claims_learning_improved": claims_learning_improved,
                        "learning_claim_allowed": learning_claim_allowed,
                    },
                    "learning_claim_guard": {
                        "status": guard_status,
                        "reason": "test learning claim guard fixture",
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        generated_at = dt.datetime(2026, 4, 29, 8, 30, tzinfo=dt.UTC)
        os.utime(path, (generated_at.timestamp(), generated_at.timestamp()))

    def _write_happy_sources(self) -> None:
        self._write_source_report(
            "bootstrap_preflight",
            {
                "status": "pass",
                "python": {"version": "3.14.3", "minimum": "3.12.0", "status": "pass"},
                "include_dev": True,
                "environment": {
                    "environment_class": "release-builder-clean",
                    "dependency_source": "current_python_environment",
                    "install_attempted": False,
                    "interpreter": ".venv/bin/python",
                    "interpreter_selection": "active interpreter",
                    "include_dev": True,
                    "executor_tooling": {
                        "status": "pass",
                        "environment_class": "release-builder-clean",
                        "workspace_virtualenv_bin": ".venv/bin",
                        "workspace_virtualenv_present": True,
                        "workspace_virtualenv_codex_present": False,
                        "codex_on_path": "",
                        "codex_outside_workspace_virtualenv": "",
                        "workspace_virtualenv_codex_shadowing_path": False,
                        "failures": [],
                    },
                },
                "dependencies": [],
                "summary": {
                    "dependency_count": 0,
                    "missing_dependency_count": 0,
                    "missing_packages": [],
                    "executor_tooling_failure_count": 0,
                    "executor_tooling_failures": [],
                },
                "guidance": "Run make dev-install, then rerun make bootstrap-preflight.",
            },
        )
        self._write_source_report(
            "release_smoke",
            {
                "status": "pass",
                "archive_budget": {
                    "pass": True,
                    "zip_path_byte_budget": {"status": "pass"},
                    "zip_component_byte_budget": {"status": "pass"},
                    "posix_escape_expanded_filename_budget": {"status": "pass"},
                    "top_offenders": [],
                },
            },
        )
        self._write_source_report(
            "source_package_clean_extract",
            {
                "status": "pass",
                "deselection_budget_status": {"status": "pass"},
                "source_package_reproducibility_status": "pass",
            },
        )
        self._write_source_report(
            "external_report_reference_manifest",
            {
                "status": "pass",
                "distribution_provenance": {
                    "mode": "strict_review_release",
                    "status": "basis_current_match",
                },
            },
        )
        self._write_source_report(
            "test_summary",
            {
                "status": "pass",
                "command": (
                    "pytest tests/test_report_schemas.py "
                    "tests/test_report_schema_sample_regeneration.py "
                    "tests/test_auto_improve_iteration_runtime.py::"
                    "AutoImproveIterationRuntimeTests::test_run_telemetry_preservation_contract_matches_schema_surface"
                ),
                "deselected_tests": [],
                "deselection_lifecycle": {
                    "status": "pass",
                    "checked_at": "2026-04-29T08:00:00Z",
                    "actual_deselected_count": 0,
                    "max_allowed_deselected_count": 0,
                    "over_budget": False,
                    "expired_count": 0,
                    "release_blocking_count": 0,
                    "missing_lifecycle_count": 0,
                    "duplicate_policy_entry_count": 0,
                    "unused_policy_entry_count": 0,
                    "risk_owner": "runtime-maintainer",
                    "expires_at": "",
                    "count_increase_gate_effect": "fail",
                    "expiry_gate_effect": "fail",
                    "next_action": "none",
                    "blockers": [],
                },
            },
        )
        self._write_source_report(
            "live_make_check",
            {
                "status": "pass",
                "suite": "full",
                "suite_scope": "full_suite",
                "represents_full_suite": True,
                "nodeid_outcome_consistency": {
                    "status": "pass",
                    "nodeid_count": 1052,
                    "outcome_count": 1052,
                    "counted_outcomes": {
                        "passed": 1052,
                        "skipped": 0,
                        "xfailed": 0,
                        "xpassed": 0,
                    },
                    "delta": 0,
                    "reason": "collected nodeid count matches pytest outcomes",
                },
                "execution_environment": {
                    "toolchain_contract": {
                        "status": "pass",
                        "release_evidence_effect": "eligible",
                        "python_supported": True,
                        "pytest_supported": True,
                    },
                },
            },
        )
        self._write_source_report("raw_registry", {"status": "pass"})
        self._write_source_report("artifact_freshness", {"status": "pass"})
        self._write_source_report("generated_index", {"status": "pass"})
        self._write_source_report(
            "auto_improve_readiness",
            {
                "execution_readiness": {"can_run": True},
                "learning_readiness": {"status": "learning_likely"},
                "learning_claim_blockers": [],
            },
        )

    def test_build_report_passes_when_all_required_inputs_are_closeout_clean_pass(self) -> None:
        self._write_dependency_lockfiles()
        self._write_happy_sources()

        report = build_report(self.vault, context=fixed_context())

        self.assertTrue(report["checked_in_release_ready"])
        self.assertTrue(report["live_rerun_release_ready"])
        self.assertFalse(report["conditional_release_ready"])
        self.assertTrue(report["clean_release_ready"])
        self._assert_release_decision(
            report,
            state="clean_pass",
            machine_release_allowed=True,
            operator_release_allowed=True,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(
            report["accepted_risk_count_by_scope"],
            {
                "total": 0,
                "policy": 0,
                "test_deselection_policy": 0,
                "operator_signoff": 0,
                "upstream_report": 0,
                "instances": 0,
                "families": 0,
                "release_blocking_family_count": 0,
                "advisory_only_family_count": 0,
                "clean_lane_blocking_family_count": 0,
                "conditional_operator_review_family_count": 0,
                "learning_claim_blocking_family_count": 0,
                "advisory_lifecycle_family_count": 0,
            },
        )
        self.assertEqual(report["status"], "pass")
        self.assertEqual(
            report["status_semantics"]["top_level_status_meaning"],
            "legacy_checked_in_release_ready_claim",
        )
        self.assertEqual(report["release_authority_status"], "clean_pass")
        self.assertEqual(report["semantic_release_status"], "clean_pass")
        self.assertEqual(
            report["pre_distribution_package_binding_status"],
            "not_materialized_by_summary",
        )
        self.assertEqual(
            report["source_closeout_distribution_binding_status"],
            "unsealed_distribution_not_provided",
        )
        self.assertEqual(
            report["sealed_release_status"], "unsealed_distribution_not_provided"
        )
        self.assertEqual(report["status_v2_preview"], report["status_v2"])
        self.assertEqual(report["status_v2"]["schema_version"], 2)
        self.assertEqual(
            report["status_v2"]["status_axes"]["release_authority_status"],
            report["release_authority_status"],
        )
        self.assertEqual(
            report["status_v2"]["status_axes"]["sealed_release_status"],
            report["sealed_release_status"],
        )
        self.assertEqual(
            report["status_v2"]["status_axes"][
                "pre_distribution_package_binding_status"
            ],
            report["pre_distribution_package_binding_status"],
        )
        self.assertEqual(
            report["status_v2"]["status_axes"][
                "source_closeout_distribution_binding_status"
            ],
            report["source_closeout_distribution_binding_status"],
        )
        self.assertEqual(
            report["status_v2"]["sealed_status_field"],
            "source_closeout_distribution_binding_status",
        )
        self.assertEqual(
            report["status_v2"]["proposed_top_level_status_replacement"],
            "source_closeout_distribution_binding_status",
        )
        self.assertIn(
            "source_closeout_distribution_binding_status",
            report["status_v2"]["recommended_consumer_fields"],
        )
        self.assertEqual(
            report["status_v2"]["status_classification"], "semantic_clean_unsealed"
        )
        self.assertEqual(report["status_v2"]["authority_reason_ids"], [])
        self.assertEqual(
            report["status_v2"]["sealed_reason_ids"],
            [
                "sealed_release_not_clean_pass",
                "distribution_package_not_materialized",
            ],
        )
        self.assertEqual(
            report["release_authority_vocabulary"]["distribution_package_status"],
            "not_provided",
        )
        self.assertEqual(
            report["release_authority_vocabulary"]["operator_summary_round_trip"][
                "status"
            ],
            "pass",
        )
        self.assertEqual(
            report["release_authority_vocabulary"]["operator_summary_round_trip"][
                "parsed"
            ]["sealed_release_status"],
            "unsealed_distribution_not_provided",
        )
        self.assertEqual(report["profile"], "base")
        self.assertEqual(report["summary"]["component_count"], 10)
        self.assertEqual([item["name"] for item in report["components"]], [spec.name for spec in SOURCE_SPECS])
        self.assertEqual(report["summary"]["blocker_count"], 0)
        self.assertEqual(report["learning_readiness_signoff"]["signoff_status"], "missing")
        self.assertEqual(report["summary"]["source_tree_coherence_status"], "pass")
        self.assertEqual(report["summary"]["release_smoke_boundedness_status"], "pass")
        self.assertEqual(report["release_smoke_boundedness_gate"]["status"], "pass")
        self.assertTrue(report["release_smoke_boundedness_gate"]["archive_budget_pass"])
        self.assertEqual(report["summary"]["live_make_check_status"], "pass")
        self.assertEqual(report["live_make_check"]["status"], "pass")
        self.assertTrue(report["live_make_check"]["ready"])
        self.assertEqual(report["live_make_check"]["nodeid_count"], 1052)
        self.assertEqual(report["source_tree_coherence"]["status"], "pass")
        self.assertEqual(report["source_tree_coherence"]["component_fingerprint_count"], 1)
        self.assertEqual(report["source_tree_coherence"]["divergence_diagnostics"]["path_limit"], 10)
        self.assertEqual(report["source_tree_coherence"]["divergence_diagnostics"]["components"], [])
        self.assertEqual(report["summary"]["test_failure_lane_fail_count"], 0)
        self.assertEqual(report["summary"]["test_failure_lane_not_run_count"], 0)
        self.assertEqual(
            {item["lane_id"]: item["status"] for item in report["test_failure_lanes"]},
            {
                "report_schema_contract": "pass",
                "runtime_telemetry_schema_contract": "pass",
            },
        )
        self.assertEqual(report["accepted_risk_delta"]["status"], "no_previous_report")
        self.assertEqual(report["source_tree_coherence"]["release_relevant_file_modified_after_component_count"], 0)
        self.assertTrue(all(item["source_tree_fingerprint"] for item in report["components"]))
        self.assertTrue(all(item["producer_input_fingerprint"] for item in report["components"]))
        self.assertTrue(
            all(item["producer_input_fingerprint"] for item in report["source_tree_coherence"]["components"])
        )
        self.assertTrue(all(item["currentness_status"] == "current" for item in report["components"]))
        self.assertEqual(report["accepted_risks"], [])
        self.assertEqual(report["dependency_reproducibility"]["status"], "locked")
        self.assertRegex(
            report["dependency_reproducibility"]["canonical_lockfile_sha256"],
            r"^[a-f0-9]{64}$",
        )
        self.assertRegex(
            report["dependency_reproducibility"]["dependency_fingerprint"],
            r"^[a-f0-9]{64}$",
        )
        self.assertIn("dependency::uv.lock", report["input_fingerprints"])
        self.assertEqual(report["downstream_input_digest_mismatch"]["status"], "no_previous_report")
        self.assertEqual(report["snapshot_phase"], "sealed_snapshot")
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])
        self.assertEqual(validate_with_schema(report, load_schema(ENVELOPE_SCHEMA_PATH)), [])

    def test_build_report_matches_explicit_load_prepare_render_pipeline(self) -> None:
        self._write_dependency_lockfiles()
        self._write_happy_sources()

        loaded = _load_closeout_sources(
            self.vault,
            policy_path=None,
            context=fixed_context(),
            profile=BASE_PROFILE,
        )
        prepared = _prepare_closeout_state(loaded)
        staged_report = _render_closeout_report(
            _closeout_render_inputs(loaded, prepared)
        )
        direct_report = build_report(self.vault, context=fixed_context())

        self.assertEqual(staged_report, direct_report)
        self.assertEqual(loaded.source_specs, source_specs_for_profile(BASE_PROFILE))
        self.assertEqual(prepared.snapshot_phase, direct_report["snapshot_phase"])
        self.assertEqual(
            prepared.readiness.release_readiness_state,
            direct_report["release_readiness_state"],
        )
        self.assertEqual(validate_with_schema(staged_report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_closeout_summary_surfaces_previous_input_digest_mismatch_as_json(self) -> None:
        self._write_happy_sources()
        baseline_report = build_report(self.vault, context=fixed_context())
        previous_closeout_path = self.vault / "ops" / "reports" / "release-closeout-summary.json"
        previous_closeout_path.parent.mkdir(parents=True, exist_ok=True)
        previous_closeout_path.write_text(json.dumps(baseline_report, ensure_ascii=False, indent=2), encoding="utf-8")

        self._write_source_report(
            "release_smoke",
            {
                "status": "pass",
                "stale_digest_probe": "changed",
            },
        )

        report = build_report(self.vault, context=fixed_context())

        mismatch = report["downstream_input_digest_mismatch"]
        self.assertEqual(mismatch["status"], "mismatch")
        self.assertEqual(mismatch["compared_input_count"], len(source_specs_for_profile(BASE_PROFILE)))
        self.assertGreaterEqual(mismatch["mismatch_count"], 1)
        mismatch_by_input = {item["input_name"]: item for item in mismatch["mismatches"]}
        self.assertIn("release_smoke", mismatch_by_input)
        self.assertEqual(
            mismatch_by_input["release_smoke"]["source_path"],
            "ops/reports/release-smoke-report.json",
        )
        self.assertNotEqual(
            mismatch_by_input["release_smoke"]["expected_digest"],
            mismatch_by_input["release_smoke"]["actual_digest"],
        )
        self.assertEqual(report["snapshot_phase"], "pre_finalization")

    @pytest.mark.release_closeout_regression
    def test_release_smoke_archive_budget_failure_blocks_clean_release(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "release_smoke",
            {
                "status": "pass",
                "archive_budget": {
                    "pass": False,
                    "zip_path_byte_budget": {"status": "pass"},
                    "zip_component_byte_budget": {"status": "fail"},
                    "posix_escape_expanded_filename_budget": {"status": "pass"},
                    "top_offenders": [{"path": "oversized/report.json"}],
                },
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertFalse(report["checked_in_release_ready"])
        self.assertFalse(report["clean_release_ready"])
        self._assert_release_decision(
            report,
            state="blocked",
            machine_release_allowed=False,
            operator_release_allowed=False,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(report["release_smoke_boundedness_gate"]["status"], "fail")
        self.assertFalse(report["release_smoke_boundedness_gate"]["archive_budget_pass"])
        self.assertEqual(report["release_smoke_boundedness_gate"]["failing_budget_count"], 1)
        self.assertIn("release_smoke_boundedness_failed", {item["code"] for item in report["blockers"]})
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_live_make_check_failure_blocks_machine_release(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "live_make_check",
            {
                "status": "fail",
                "suite": "full",
                "suite_scope": "full_suite",
                "represents_full_suite": True,
                "nodeid_outcome_consistency": {
                    "status": "fail",
                    "nodeid_count": 1052,
                    "outcome_count": 1051,
                    "counted_outcomes": {"passed": 1051, "skipped": 0, "xfailed": 0, "xpassed": 0},
                    "delta": 1,
                    "reason": "fixture mismatch",
                },
                "execution_environment": {
                    "toolchain_contract": {
                        "status": "pass",
                        "release_evidence_effect": "eligible",
                        "python_supported": True,
                        "pytest_supported": True,
                    },
                },
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertFalse(report["checked_in_release_ready"])
        self.assertFalse(report["live_rerun_release_ready"])
        self._assert_release_decision(
            report,
            state="blocked",
            machine_release_allowed=False,
            operator_release_allowed=False,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(report["summary"]["live_make_check_status"], "fail")
        self.assertEqual(report["live_make_check"]["status"], "fail")
        self.assertTrue(report["live_make_check"]["blocking"])
        blocker_codes = {item["code"] for item in report["blockers"]}
        self.assertIn("live_make_check_not_pass", blocker_codes)
        self.assertIn("live_make_check_nodeid_outcome_mismatch", blocker_codes)
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_external_report_manifest_missing_current_zip_is_typed_attention(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "external_report_reference_manifest",
            {
                "status": "pass",
                "distribution_provenance": {
                    "mode": "advisory",
                    "status": "current_distribution_missing",
                },
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertTrue(report["checked_in_release_ready"])
        self._assert_release_decision(
            report,
            state="clean_pass",
            machine_release_allowed=True,
            operator_release_allowed=True,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(report["blockers"], [])
        accepted = {item["code"]: item for item in report["accepted_risks"]}
        self.assertIn("external_report_strict_unavailable", accepted)
        self.assertEqual(
            accepted["external_report_strict_unavailable"]["source"],
            "external_report_reference_manifest",
        )
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_provenance_profile_adds_supply_chain_gate_without_changing_base_default(self) -> None:
        self._write_happy_sources()

        base_report = build_report(self.vault, context=fixed_context())
        provenance_report = build_report(self.vault, context=fixed_context(), profile=PROVENANCE_PROFILE)

        self.assertTrue(base_report["checked_in_release_ready"])
        self.assertEqual(base_report["profile"], "base")
        self._assert_release_decision(
            base_report,
            state="clean_pass",
            machine_release_allowed=True,
            operator_release_allowed=True,
            requires_accepted_risk_review=False,
        )
        self.assertFalse(provenance_report["checked_in_release_ready"])
        self.assertEqual(provenance_report["profile"], "provenance")
        self._assert_release_decision(
            provenance_report,
            state="blocked",
            machine_release_allowed=False,
            operator_release_allowed=False,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(provenance_report["summary"]["component_count"], 11)
        self.assertEqual(provenance_report["blockers"][0]["code"], "supply_chain_gate_report_missing")
        self.assertEqual(provenance_report["components"][-1]["name"], "supply_chain_gate")

        self._write_source_report("supply_chain_gate", {"status": "pass"})
        refreshed = build_report(self.vault, context=fixed_context(), profile=PROVENANCE_PROFILE)

        self.assertTrue(refreshed["checked_in_release_ready"])
        self._assert_release_decision(
            refreshed,
            state="clean_pass",
            machine_release_allowed=True,
            operator_release_allowed=True,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(validate_with_schema(refreshed, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_sbom_profile_adds_provenance_and_sbom_readiness_gates(self) -> None:
        self._write_happy_sources()
        self._write_source_report("supply_chain_gate", {"status": "pass"})

        report = build_report(self.vault, context=fixed_context(), profile=SBOM_PROFILE)

        self.assertFalse(report["checked_in_release_ready"])
        self._assert_release_decision(
            report,
            state="blocked",
            machine_release_allowed=False,
            operator_release_allowed=False,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(report["profile"], "sbom")
        self.assertEqual(report["summary"]["component_count"], 12)
        self.assertEqual(report["blockers"][0]["code"], "sbom_readiness_report_missing")
        self.assertEqual([item["name"] for item in report["components"]][-2:], ["supply_chain_gate", "sbom_readiness"])

        self._write_source_report("sbom_readiness", {"status": "pass"})
        refreshed = build_report(self.vault, context=fixed_context(), profile=SBOM_PROFILE)

        self.assertTrue(refreshed["checked_in_release_ready"])
        self._assert_release_decision(
            refreshed,
            state="clean_pass",
            machine_release_allowed=True,
            operator_release_allowed=True,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(validate_with_schema(refreshed, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_source_tree_fingerprint_divergence_is_visible_accepted_risk(self) -> None:
        self._write_release_surface_file("ops/scripts/divergence_sample.py", "print('sample')\n")
        self._write_happy_sources()
        self._touch_release_surface_file("ops/scripts/divergence_sample.py", "2026-04-29T08:00:01Z")
        self._write_source_report(
            "generated_index",
            {"status": "pass", "source_tree_fingerprint": "different-release-tree-fingerprint"},
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertTrue(report["checked_in_release_ready"])
        self.assertFalse(report["live_rerun_release_ready"])
        self.assertTrue(report["conditional_release_ready"])
        self.assertFalse(report["clean_release_ready"])
        self._assert_release_decision(
            report,
            state="conditional_pass",
            machine_release_allowed=False,
            operator_release_allowed=True,
            requires_accepted_risk_review=True,
        )
        self.assertEqual(report["source_tree_coherence"]["status"], "attention")
        self.assertEqual(report["source_tree_coherence"]["component_fingerprint_count"], 2)
        self.assertIn(
            "source_tree_coherence_attention",
            {item["code"] for item in report["accepted_risks"]},
        )
        accepted = {item["code"]: item for item in report["accepted_risks"]}
        risk_acceptance = accepted["source_tree_coherence_attention"]["risk_acceptance"]
        self.assertEqual(risk_acceptance["risk_owner"], "runtime-maintainer")
        self.assertEqual(risk_acceptance["expires_at"], "2026-05-06T09:00:00Z")
        diagnostics = report["source_tree_coherence"]["divergence_diagnostics"]
        self.assertEqual(diagnostics["path_limit"], 10)
        generated_index = next(item for item in diagnostics["components"] if item["name"] == "generated_index")
        self.assertFalse(generated_index["matches_current_source_tree_fingerprint"])
        self.assertFalse(generated_index["modified_after_generated_at"])
        self.assertEqual(generated_index["changed_after_generated_at_count"], 1)
        self.assertEqual(
            generated_index["changed_after_generated_at"],
            [{"path": "ops/scripts/divergence_sample.py", "mtime": "2026-04-29T08:00:01Z"}],
        )

    def test_attention_reports_become_accepted_risks_without_blocking_release(self) -> None:
        self._write_happy_sources()
        self._write_source_report("raw_registry", {"status": "warn"})
        self._write_source_report("artifact_freshness", {"status": "attention"})
        self._write_source_report("generated_index", {"status": "attention"})

        report = build_report(self.vault, context=fixed_context())

        self.assertTrue(report["checked_in_release_ready"])
        self.assertTrue(report["conditional_release_ready"])
        self.assertFalse(report["clean_release_ready"])
        self._assert_release_decision(
            report,
            state="conditional_pass",
            machine_release_allowed=False,
            operator_release_allowed=True,
            requires_accepted_risk_review=True,
        )
        self.assertEqual(report["accepted_risk_count_by_scope"]["total"], 3)
        self.assertEqual(report["accepted_risk_count_by_scope"]["policy"], 3)
        self.assertEqual(report["accepted_risk_count_by_scope"]["clean_lane_blocking_family_count"], 2)
        self.assertEqual(report["accepted_risk_count_by_scope"]["advisory_lifecycle_family_count"], 1)
        self.assertEqual(report["clean_lane_blocking_risk_family_count"], 2)
        self.assertEqual(report["blockers"], [])
        self.assertEqual(
            {item["code"] for item in report["accepted_risks"]},
            {
                "raw_registry_preflight_warnings",
                "artifact_freshness_attention",
                "generated_index_archive_advisory",
            },
        )
        accepted = {item["code"]: item for item in report["accepted_risks"]}
        artifact_acceptance = accepted["artifact_freshness_attention"]["risk_acceptance"]
        generated_index_acceptance = accepted["generated_index_archive_advisory"]["risk_acceptance"]
        self.assertEqual(accepted["raw_registry_preflight_warnings"]["clean_lane_effect"], "blocks_clean_lane")
        self.assertEqual(accepted["artifact_freshness_attention"]["clean_lane_effect"], "blocks_clean_lane")
        self.assertEqual(
            accepted["generated_index_archive_advisory"]["advisory_lifecycle_effect"],
            "review_backlog",
        )
        self.assertEqual(
            accepted["generated_index_archive_advisory"]["clean_lane_effect"],
            "does_not_block_clean_lane",
        )
        self.assertEqual(artifact_acceptance["accepted_by"], "release_closeout_policy")
        self.assertEqual(artifact_acceptance["risk_owner"], "runtime-maintainer")
        self.assertEqual(artifact_acceptance["expires_at"], "2026-05-06T09:00:00Z")
        self.assertEqual(generated_index_acceptance["accepted_by"], "release_closeout_policy")
        self.assertEqual(generated_index_acceptance["risk_owner"], "runtime-maintainer")
        self.assertEqual(generated_index_acceptance["expires_at"], "2026-05-06T09:00:00Z")

    def test_stable_contract_debt_artifact_freshness_attention_is_advisory(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "artifact_freshness",
            {
                "status": "attention",
                "summary": {
                    "schema_invalid_artifact_count": 0,
                    "schema_unavailable_artifact_count": 0,
                    "root_ephemeral_artifact_count": 0,
                    "non_utf8_text_artifact_count": 0,
                    "stale_artifact_count": 0,
                    "mtime_sensitive_attention_artifact_count": 0,
                    "mtime_sensitive_attention_issue_count": 0,
                    "operational_attention_artifact_count": 0,
                    "operational_attention_issue_count": 0,
                    "stable_contract_debt_issue_count": 7,
                },
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertTrue(report["clean_release_ready"])
        self._assert_release_decision(
            report,
            state="clean_pass",
            machine_release_allowed=True,
            operator_release_allowed=True,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(report["accepted_risk_count_by_scope"]["total"], 1)
        self.assertEqual(report["accepted_risk_count_by_scope"]["clean_lane_blocking_family_count"], 0)
        self.assertEqual(report["accepted_risk_count_by_scope"]["advisory_lifecycle_family_count"], 1)
        accepted = {item["code"]: item for item in report["accepted_risks"]}
        self.assertEqual(set(accepted), {"artifact_freshness_stable_contract_debt_advisory"})
        self.assertEqual(
            accepted["artifact_freshness_stable_contract_debt_advisory"]["clean_lane_effect"],
            "does_not_block_clean_lane",
        )
        self.assertEqual(
            accepted["artifact_freshness_stable_contract_debt_advisory"]["advisory_lifecycle_effect"],
            "review_backlog",
        )
        gate = report["artifact_freshness_gate"]
        self.assertEqual(gate["gate_effect"], "advisory")
        self.assertEqual(gate["display_effect"], "advisory")
        self.assertFalse(gate["blocking"])
        self.assertTrue(gate["ready"])

    def test_artifact_freshness_attention_ignores_non_release_owned_operational_drift(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "artifact_freshness",
            {
                "status": "attention",
                "summary": {
                    "schema_invalid_artifact_count": 0,
                    "schema_unavailable_artifact_count": 0,
                    "root_ephemeral_artifact_count": 0,
                    "non_utf8_text_artifact_count": 0,
                    "stale_artifact_count": 2,
                    "mtime_sensitive_attention_artifact_count": 0,
                    "mtime_sensitive_attention_issue_count": 0,
                    "operational_attention_artifact_count": 2,
                    "operational_attention_issue_count": 2,
                    "stable_contract_debt_issue_count": 0,
                },
                "artifact_records": [
                    {
                        "path": "ops/reports/learning-readiness-signoff.json",
                        "issues": ["source_tree_fingerprint_mismatch"],
                    },
                    {
                        "path": "ops/reports/public-check-summary.json",
                        "issues": ["source_revision_mismatch"],
                    },
                ],
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertTrue(report["clean_release_ready"])
        self._assert_release_decision(
            report,
            state="clean_pass",
            machine_release_allowed=True,
            operator_release_allowed=True,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(report["summary"]["artifact_freshness_status"], "attention")
        self.assertEqual(report["accepted_risk_count_by_scope"]["total"], 0)
        self.assertEqual(report["summary"]["accepted_risk_instance_count"], 0)
        self.assertEqual(report["summary"]["release_blocking_risk_family_count"], 0)
        self.assertNotIn(
            "artifact_freshness_attention",
            {item["code"] for item in report["accepted_risks"]},
        )
        gate = report["artifact_freshness_gate"]
        self.assertEqual(gate["gate_effect"], "none")
        self.assertEqual(gate["display_effect"], "none")
        self.assertFalse(gate["blocking"])
        self.assertTrue(gate["ready"])

    def test_release_owned_artifact_freshness_attention_is_gate_advisory(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "artifact_freshness",
            {
                "status": "attention",
                "summary": {
                    "schema_invalid_artifact_count": 0,
                    "schema_unavailable_artifact_count": 0,
                    "root_ephemeral_artifact_count": 0,
                    "non_utf8_text_artifact_count": 0,
                    "stale_artifact_count": 1,
                    "mtime_sensitive_attention_artifact_count": 0,
                    "mtime_sensitive_attention_issue_count": 0,
                    "operational_attention_artifact_count": 1,
                    "operational_attention_issue_count": 1,
                    "stable_contract_debt_issue_count": 0,
                },
                "artifact_records": [
                    {
                        "path": "ops/reports/auto-improve-readiness.json",
                        "issues": ["source_tree_fingerprint_mismatch"],
                    }
                ],
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertTrue(report["checked_in_release_ready"])
        self.assertFalse(report["clean_release_ready"])
        self._assert_release_decision(
            report,
            state="conditional_pass",
            machine_release_allowed=False,
            operator_release_allowed=True,
            requires_accepted_risk_review=True,
        )
        gate = report["artifact_freshness_gate"]
        self.assertEqual(gate["gate_effect"], "advisory")
        self.assertEqual(gate["display_effect"], "advisory")
        self.assertFalse(gate["blocking"])
        self.assertTrue(gate["ready"])
        accepted = {item["code"] for item in report["accepted_risks"]}
        self.assertIn("artifact_freshness_attention", accepted)

    def test_release_owned_artifact_freshness_revision_attention_is_gate_advisory(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "artifact_freshness",
            {
                "status": "attention",
                "summary": {
                    "schema_invalid_artifact_count": 0,
                    "schema_unavailable_artifact_count": 0,
                    "root_ephemeral_artifact_count": 0,
                    "non_utf8_text_artifact_count": 0,
                    "stale_artifact_count": 1,
                    "mtime_sensitive_attention_artifact_count": 0,
                    "mtime_sensitive_attention_issue_count": 0,
                    "operational_attention_artifact_count": 1,
                    "operational_attention_issue_count": 1,
                    "stable_contract_debt_issue_count": 0,
                },
                "artifact_records": [
                    {
                        "path": "ops/reports/auto-improve-readiness.json",
                        "issues": ["source_revision_mismatch"],
                    }
                ],
            },
        )

        report = build_report(self.vault, context=fixed_context())

        gate = report["artifact_freshness_gate"]
        self.assertEqual(gate["gate_effect"], "advisory")
        self.assertEqual(gate["display_effect"], "advisory")
        self.assertFalse(gate["blocking"])
        self.assertTrue(gate["ready"])
        accepted = {item["code"] for item in report["accepted_risks"]}
        self.assertIn("artifact_freshness_attention", accepted)

    def test_release_owned_artifact_freshness_mtime_attention_is_gate_advisory(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "artifact_freshness",
            {
                "status": "attention",
                "summary": {
                    "schema_invalid_artifact_count": 0,
                    "schema_unavailable_artifact_count": 0,
                    "root_ephemeral_artifact_count": 0,
                    "non_utf8_text_artifact_count": 0,
                    "stale_artifact_count": 0,
                    "mtime_sensitive_attention_artifact_count": 1,
                    "mtime_sensitive_attention_issue_count": 1,
                    "operational_attention_artifact_count": 0,
                    "operational_attention_issue_count": 0,
                    "stable_contract_debt_issue_count": 0,
                },
                "artifact_records": [
                    {
                        "path": "ops/reports/generated-artifact-index.json",
                        "issues": [],
                        "mtime_sensitive_issues": ["generated_at_older_than_file_mtime"],
                    }
                ],
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self._assert_release_decision(
            report,
            state="conditional_pass",
            machine_release_allowed=False,
            operator_release_allowed=True,
            requires_accepted_risk_review=True,
        )
        gate = report["artifact_freshness_gate"]
        self.assertEqual(gate["gate_effect"], "advisory")
        self.assertEqual(gate["display_effect"], "advisory")
        self.assertFalse(gate["blocking"])
        self.assertTrue(gate["ready"])
        accepted = {item["code"] for item in report["accepted_risks"]}
        self.assertIn("artifact_freshness_attention", accepted)

    def test_structured_test_deselections_are_accepted_risks_until_expiry(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "test_summary",
            {
                "status": "pass",
                "deselected_tests": [
                    {
                        "nodeid": "tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_eval_report_validates_and_requires_policy_identity",
                        "reason": "temporary schema contract exception",
                        "policy_ref": "ops/policies/report-contract-deselections.json#schema_contract_exception",
                        "risk_owner": "runtime-maintainer",
                        "expires_at": "2026-05-14T00:00:00Z",
                        "release_blocking": False,
                        "expected_to_pass_after_refresh": True,
                    },
                    {
                        "nodeid": "tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_eval_report_validates_and_requires_policy_identity",
                        "reason": "temporary schema contract exception",
                        "policy_ref": "ops/policies/report-contract-deselections.json#schema_contract_exception",
                        "risk_owner": "runtime-maintainer",
                        "expires_at": "2026-05-14T00:00:00Z",
                        "release_blocking": False,
                        "expected_to_pass_after_refresh": True,
                    }
                ],
                "deselection_lifecycle": {
                    "status": "pass",
                    "checked_at": "2026-04-29T08:00:00Z",
                    "actual_deselected_count": 2,
                    "max_allowed_deselected_count": 4,
                    "over_budget": False,
                    "expired_count": 0,
                    "release_blocking_count": 0,
                    "missing_lifecycle_count": 0,
                    "duplicate_policy_entry_count": 0,
                    "unused_policy_entry_count": 2,
                    "risk_owner": "runtime-maintainer",
                    "expires_at": "2026-05-14T00:00:00Z",
                    "count_increase_gate_effect": "fail",
                    "expiry_gate_effect": "fail",
                    "next_action": "none",
                    "blockers": [],
                },
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertTrue(report["checked_in_release_ready"])
        self._assert_release_decision(
            report,
            state="conditional_pass",
            machine_release_allowed=False,
            operator_release_allowed=True,
            requires_accepted_risk_review=True,
        )
        accepted = {item["code"]: item for item in report["accepted_risks"]}
        self.assertIn("test_deselection_accepted_risk", accepted)
        risk_acceptance = accepted["test_deselection_accepted_risk"]["risk_acceptance"]
        self.assertEqual(risk_acceptance["accepted_by"], "test_deselection_policy")
        self.assertEqual(risk_acceptance["expires_at"], "2026-05-14T00:00:00Z")
        self.assertEqual(risk_acceptance["risk_owner"], "runtime-maintainer")
        self.assertEqual(report["accepted_risk_count_by_scope"]["instances"], 2)
        self.assertEqual(report["accepted_risk_count_by_scope"]["families"], 1)
        self.assertEqual(report["accepted_risk_count_by_scope"]["clean_lane_blocking_family_count"], 1)
        self.assertEqual(report["summary"]["accepted_risk_instance_count"], 2)
        self.assertEqual(report["summary"]["accepted_risk_family_count"], 1)
        self.assertEqual(report["summary"]["release_blocking_risk_family_count"], 1)
        self.assertNotIn("release_blocking_risk_count", report["summary"])

    def test_test_failure_lanes_surface_report_schema_contract_failure(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "test_summary",
            {
                "status": "partial-pass",
                "command": (
                    "pytest tests/test_report_schema_sample_regeneration.py "
                    "tests/test_auto_improve_iteration_runtime.py::"
                    "AutoImproveIterationRuntimeTests::test_run_telemetry_preservation_contract_matches_schema_surface"
                ),
                "stdout_tail": (
                    "FAILED tests/test_report_schema_sample_regeneration.py::"
                    "ReportSchemaSampleRegenerationTests::test_generated_openvex_sample_matches_frozen_fixture\n"
                ),
                "deselected_tests": [],
                "deselection_lifecycle": {
                    "status": "pass",
                    "checked_at": "2026-04-29T08:00:00Z",
                    "actual_deselected_count": 0,
                    "max_allowed_deselected_count": 4,
                    "over_budget": False,
                    "expired_count": 0,
                    "release_blocking_count": 0,
                    "missing_lifecycle_count": 0,
                    "duplicate_policy_entry_count": 0,
                    "unused_policy_entry_count": 0,
                    "risk_owner": "runtime-maintainer",
                    "expires_at": "2026-05-14T00:00:00Z",
                    "count_increase_gate_effect": "fail",
                    "expiry_gate_effect": "fail",
                    "next_action": "none",
                    "blockers": [],
                },
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertFalse(report["checked_in_release_ready"])
        self.assertFalse(report["live_rerun_release_ready"])
        self.assertFalse(report["conditional_release_ready"])
        self.assertFalse(report["clean_release_ready"])
        self._assert_release_decision(
            report,
            state="blocked",
            machine_release_allowed=False,
            operator_release_allowed=False,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(report["summary"]["test_failure_lane_fail_count"], 1)
        lanes = {item["lane_id"]: item for item in report["test_failure_lanes"]}
        self.assertEqual(lanes["report_schema_contract"]["status"], "fail")
        self.assertEqual(lanes["report_schema_contract"]["failed_count"], 1)
        self.assertEqual(lanes["runtime_telemetry_schema_contract"]["status"], "pass")
        self.assertIn("test_summary_not_pass", {item["code"] for item in report["blockers"]})
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_truth_ladder_separates_checked_in_from_live_rerun_readiness(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "test_summary",
            {
                "status": "pass",
                "command": "pytest tests/test_unrelated_runtime.py",
                "deselected_tests": [],
                "deselection_lifecycle": {
                    "status": "pass",
                    "checked_at": "2026-04-29T08:00:00Z",
                    "actual_deselected_count": 0,
                    "max_allowed_deselected_count": 0,
                    "over_budget": False,
                    "expired_count": 0,
                    "release_blocking_count": 0,
                    "missing_lifecycle_count": 0,
                    "duplicate_policy_entry_count": 0,
                    "unused_policy_entry_count": 0,
                    "risk_owner": "runtime-maintainer",
                    "expires_at": "",
                    "count_increase_gate_effect": "fail",
                    "expiry_gate_effect": "fail",
                    "next_action": "none",
                    "blockers": [],
                },
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertTrue(report["checked_in_release_ready"])
        self.assertFalse(report["live_rerun_release_ready"])
        self.assertFalse(report["conditional_release_ready"])
        self.assertFalse(report["clean_release_ready"])
        self._assert_release_decision(
            report,
            state="unknown",
            machine_release_allowed=False,
            operator_release_allowed=False,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(report["summary"]["test_failure_lane_not_run_count"], 2)
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_accepted_risk_delta_explains_new_and_removed_risks(self) -> None:
        self._write_happy_sources()
        previous = build_report(self.vault, context=fixed_context())
        write_report(self.vault, previous)
        self._write_source_report("artifact_freshness", {"status": "attention"})

        report = build_report(self.vault, context=fixed_context())

        self.assertTrue(report["checked_in_release_ready"])
        self._assert_release_decision(
            report,
            state="conditional_pass",
            machine_release_allowed=False,
            operator_release_allowed=True,
            requires_accepted_risk_review=True,
        )
        self.assertEqual(report["accepted_risk_delta"]["status"], "changed")
        self.assertEqual(report["accepted_risk_delta"]["added_count"], 1)
        self.assertEqual(report["accepted_risk_delta"]["removed_count"], 0)
        self.assertEqual(
            report["accepted_risk_delta"]["added"],
            ["artifact_freshness::artifact_freshness_attention"],
        )
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_failed_deselection_lifecycle_blocks_release_closeout(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "test_summary",
            {
                "status": "pass",
                "deselected_tests": [],
                "deselection_lifecycle": {
                    "status": "fail",
                    "checked_at": "2026-04-29T08:00:00Z",
                    "actual_deselected_count": 5,
                    "max_allowed_deselected_count": 4,
                    "over_budget": True,
                    "expired_count": 0,
                    "release_blocking_count": 0,
                    "missing_lifecycle_count": 0,
                    "duplicate_policy_entry_count": 0,
                    "unused_policy_entry_count": 0,
                    "risk_owner": "runtime-maintainer",
                    "expires_at": "2026-05-14T00:00:00Z",
                    "count_increase_gate_effect": "fail",
                    "expiry_gate_effect": "fail",
                    "next_action": "refresh tests or renew/remove deselection policy entries",
                    "blockers": [
                        {
                            "code": "deselection_budget_exceeded",
                            "nodeid": "",
                            "message": "Deselected test count 5 exceeds max_count 4.",
                        }
                    ],
                },
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertFalse(report["checked_in_release_ready"])
        self._assert_release_decision(
            report,
            state="blocked",
            machine_release_allowed=False,
            operator_release_allowed=False,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(report["blockers"][0]["code"], "test_deselection_lifecycle_failed")

    def test_accepted_risks_require_risk_acceptance_metadata(self) -> None:
        self._write_happy_sources()
        self._write_source_report("artifact_freshness", {"status": "attention"})
        report = build_report(self.vault, context=fixed_context())

        invalid = json.loads(json.dumps(report))
        invalid["accepted_risks"][0].pop("risk_acceptance")

        self.assertIn(
            "$.accepted_risks[0]: missing required property 'risk_acceptance'",
            validate_with_schema(invalid, load_schema(REPORT_SCHEMA_PATH)),
        )

    def test_learning_review_blocker_blocks_learning_claim_without_blocking_source_release(self) -> None:
        self._write_happy_sources()
        self._write_learning_delta_scoreboard(claims_learning_improved=True, guard_status="blocked")
        self._write_source_report(
            "auto_improve_readiness",
            {
                "execution_readiness": {"can_run": True},
                "learning_readiness": {"status": "learning_uncertain"},
                "learning_claim_blockers": [
                    {
                        "id": "learning_blocked_by_review_required",
                        "accepted_risk": False,
                        "severity": "blocker",
                        "gate_effect": "operator_review_required",
                        "reason": "learning readiness still requires review",
                        "required_evidence": ["learning_readiness.likely_to_learn must be true"],
                    }
                ],
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertTrue(report["checked_in_release_ready"])
        self.assertEqual(report["status"], "pass")
        self._assert_release_decision(
            report,
            state="clean_pass",
            machine_release_allowed=True,
            operator_release_allowed=True,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(report["blockers"][0]["code"], "learning_blocked_by_review_required")
        self.assertEqual(report["blockers"][0]["clean_lane_effect"], "does_not_block_clean_lane")
        self.assertEqual(report["blockers"][0]["learning_lane_effect"], "blocks_learning_claim")
        self.assertEqual(report["summary"]["source_clean_blocker_count"], 0)
        self.assertEqual(report["components"][-1]["name"], "auto_improve_readiness")
        self.assertTrue(report["components"][-1]["ready"])
        self.assertEqual(report["learning_readiness_signoff"]["signoff_status"], "missing")

    def test_learning_review_blocker_does_not_block_source_release_without_learning_claim(self) -> None:
        self._write_happy_sources()
        self._write_learning_delta_scoreboard(
            claims_learning_improved=False,
            learning_claim_allowed=False,
            guard_status="pass",
        )
        self._write_source_report(
            "auto_improve_readiness",
            {
                "execution_readiness": {"can_run": True},
                "learning_readiness": {"status": "learning_uncertain"},
                "learning_claim_blockers": [
                    {
                        "id": "learning_blocked_by_review_required",
                        "accepted_risk": False,
                        "severity": "blocker",
                        "gate_effect": "operator_review_required",
                        "reason": "learning readiness still requires review",
                        "required_evidence": ["learning_readiness.likely_to_learn must be true"],
                    }
                ],
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertTrue(report["checked_in_release_ready"])
        self.assertTrue(report["clean_release_ready"])
        self._assert_release_decision(
            report,
            state="clean_pass",
            machine_release_allowed=True,
            operator_release_allowed=True,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["accepted_risks"], [])
        self.assertEqual(report["components"][-1]["name"], "auto_improve_readiness")
        self.assertTrue(report["components"][-1]["ready"])
        self.assertIn("claims_learning_improved=False", report["components"][-1]["summary"])
        self.assertIn("skipped_learning_claim_blocker_count=1", report["components"][-1]["summary"])
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_auto_improve_promotion_blockers_drive_closeout_without_legacy_duplicate(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "auto_improve_readiness",
            {
                "can_execute_trial": False,
                "can_promote_result": False,
                "execution_readiness": {"can_run": False},
                "learning_readiness": {"status": "not_runnable"},
                "learning_claim_blockers": [],
                "promotion_blockers": [
                    {
                        "id": "execution_blocked_by_no_runnable_proposal",
                        "scope": "execution_readiness",
                        "status": "open",
                        "severity": "blocker",
                        "accepted_risk": False,
                        "gate_effect": "blocks_execution",
                        "source_status": "warn",
                        "reason": "no runnable proposal is available",
                        "signal_ids": [],
                        "required_evidence": [
                            "execution_readiness.can_run must be true before an auto-improve trial can execute"
                        ],
                        "recommended_next_step": "refresh generated proposal queue evidence",
                    }
                ],
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertTrue(report["checked_in_release_ready"])
        self._assert_release_decision(
            report,
            state="clean_pass",
            machine_release_allowed=True,
            operator_release_allowed=True,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(
            [item["code"] for item in report["blockers"]],
            ["execution_blocked_by_no_runnable_proposal"],
        )
        self.assertEqual(report["blockers"][0]["clean_lane_effect"], "does_not_block_clean_lane")
        self.assertEqual(report["summary"]["source_clean_blocker_count"], 0)
        self.assertTrue(report["components"][-1]["ready"])
        self.assertIn("can_execute_trial=False", report["components"][-1]["summary"])
        self.assertIn("can_promote_result=False", report["components"][-1]["summary"])

    def test_downstream_release_gate_promotion_blockers_do_not_self_block_source_closeout(self) -> None:
        self._write_happy_sources()
        downstream_blocker_ids = [
            "promotion_blocked_by_release_closeout_summary_failure",
            "promotion_blocked_by_release_batch_manifest_failure",
            "promotion_blocked_by_release_finality_failure",
            "promotion_blocked_by_artifact_finalization_failure",
        ]
        self._write_source_report(
            "auto_improve_readiness",
            {
                "can_execute_trial": True,
                "can_promote_result": False,
                "execution_readiness": {"can_run": True},
                "learning_readiness": {"status": "learning_likely"},
                "learning_claim_blockers": [],
                "promotion_blockers": [
                    {
                        "id": blocker_id,
                        "scope": "release_gate",
                        "status": "open",
                        "severity": "blocker",
                        "accepted_risk": False,
                        "gate_effect": "blocks_promotion",
                        "source_status": "fail",
                        "reason": f"{blocker_id} fixture",
                        "signal_ids": [],
                        "required_evidence": ["downstream release gate evidence must pass"],
                        "recommended_next_step": "refresh downstream release gate evidence",
                    }
                    for blocker_id in downstream_blocker_ids
                ],
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertTrue(report["checked_in_release_ready"])
        self.assertTrue(report["clean_release_ready"])
        self._assert_release_decision(
            report,
            state="clean_pass",
            machine_release_allowed=True,
            operator_release_allowed=True,
            requires_accepted_risk_review=False,
        )
        blockers = {item["code"]: item for item in report["blockers"]}
        self.assertEqual(set(blockers), set(downstream_blocker_ids))
        for blocker_id in downstream_blocker_ids:
            with self.subTest(blocker_id=blocker_id):
                self.assertEqual(blockers[blocker_id]["clean_lane_effect"], "does_not_block_clean_lane")
                self.assertEqual(blockers[blocker_id]["learning_lane_effect"], "blocks_learning_claim")
        self.assertEqual(report["summary"]["source_clean_blocker_count"], 0)
        self.assertTrue(report["components"][-1]["ready"])

    def test_learning_readiness_signoff_converts_only_named_review_blocker(self) -> None:
        self._write_happy_sources()
        self._write_learning_delta_scoreboard(claims_learning_improved=True, guard_status="blocked")
        self._write_source_report(
            "auto_improve_readiness",
            {
                "execution_readiness": {"can_run": True},
                "learning_readiness": {"status": "learning_uncertain"},
                "learning_claim_blockers": [
                    {
                        "id": "learning_blocked_by_review_required",
                        "accepted_risk": False,
                        "severity": "blocker",
                        "gate_effect": "operator_review_required",
                        "reason": "learning readiness still requires review",
                        "required_evidence": ["learning_readiness.likely_to_learn must be true"],
                    }
                ],
            },
        )
        self._write_learning_signoff()

        report = build_report(self.vault, context=fixed_context())

        self.assertTrue(report["checked_in_release_ready"])
        self.assertFalse(report["conditional_release_ready"])
        self.assertTrue(report["clean_release_ready"])
        self._assert_release_decision(
            report,
            state="clean_pass",
            machine_release_allowed=True,
            operator_release_allowed=True,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(report["accepted_risk_count_by_scope"]["total"], 1)
        self.assertEqual(report["accepted_risk_count_by_scope"]["operator_signoff"], 1)
        self.assertEqual(report["accepted_risk_count_by_scope"]["learning_claim_blocking_family_count"], 1)
        self.assertEqual(report["clean_lane_blocking_risk_family_count"], 0)
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["learning_readiness_signoff"]["signoff_status"], "active")
        self.assertEqual(report["learning_readiness_signoff"]["linked_blocker_id"], "learning_blocked_by_review_required")
        accepted = {item["code"]: item for item in report["accepted_risks"]}
        self.assertIn("learning_blocked_by_review_required", accepted)
        self.assertEqual(accepted["learning_blocked_by_review_required"]["gate_effect"], "advisory")
        self.assertEqual(accepted["learning_blocked_by_review_required"]["clean_lane_effect"], "does_not_block_clean_lane")
        self.assertEqual(accepted["learning_blocked_by_review_required"]["learning_lane_effect"], "blocks_learning_claim")
        self.assertIn("operator@example.test", accepted["learning_blocked_by_review_required"]["message"])
        risk_acceptance = accepted["learning_blocked_by_review_required"]["risk_acceptance"]
        self.assertEqual(risk_acceptance["accepted_by"], "operator@example.test")
        self.assertEqual(risk_acceptance["expires_at"], "2026-04-30T08:30:00Z")
        self.assertEqual(risk_acceptance["risk_owner"], "runtime-maintainer")
        self.assertEqual(risk_acceptance["acceptance_source"], "ops/reports/learning-readiness-signoff.json")
        self.assertEqual(risk_acceptance["linked_blocker_id"], "learning_blocked_by_review_required")

    def test_template_learning_readiness_signoff_remains_inactive(self) -> None:
        self._write_happy_sources()
        self._write_learning_delta_scoreboard(claims_learning_improved=True, guard_status="blocked")
        self._write_source_report(
            "auto_improve_readiness",
            {
                "execution_readiness": {"can_run": True},
                "learning_readiness": {"status": "learning_uncertain"},
                "learning_claim_blockers": [
                    {
                        "id": "learning_blocked_by_review_required",
                        "accepted_risk": False,
                        "severity": "blocker",
                        "gate_effect": "operator_review_required",
                        "reason": "learning readiness still requires review",
                        "required_evidence": ["learning_readiness.likely_to_learn must be true"],
                    }
                ],
            },
        )
        template = json.loads(
            (REPO_ROOT / "ops" / "templates" / "learning-readiness-signoff.json").read_text(
                encoding="utf-8",
            )
        )
        signoff_path = self.vault / "ops" / "reports" / "learning-readiness-signoff.json"
        signoff_path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")

        report = build_report(self.vault, context=fixed_context())

        self.assertTrue(report["checked_in_release_ready"])
        self._assert_release_decision(
            report,
            state="clean_pass",
            machine_release_allowed=True,
            operator_release_allowed=True,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(report["blockers"][0]["code"], "learning_blocked_by_review_required")
        self.assertEqual(report["blockers"][0]["clean_lane_effect"], "does_not_block_clean_lane")
        self.assertEqual(report["summary"]["source_clean_blocker_count"], 0)
        self.assertEqual(report["learning_readiness_signoff"]["load_status"], "template_only")
        self.assertEqual(report["learning_readiness_signoff"]["signoff_status"], "template_only")
        self.assertFalse(report["learning_readiness_signoff"]["active"])
        self.assertIn("template-only artifact", report["learning_readiness_signoff"]["summary"])
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_learning_readiness_signoff_schema_rejects_other_blocker_ids(self) -> None:
        self._write_learning_signoff()
        path = self.vault / "ops" / "reports" / "learning-readiness-signoff.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["linked_blocker_id"] = "other_learning_blocker"

        errors = validate_with_schema(payload, load_schema(SIGNOFF_SCHEMA_PATH))

        self.assertTrue(errors)

    def test_learning_readiness_signoff_does_not_convert_other_blockers(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "auto_improve_readiness",
            {
                "execution_readiness": {"can_run": True},
                "learning_readiness": {"status": "learning_uncertain"},
                "learning_claim_blockers": [
                    {
                        "id": "other_learning_blocker",
                        "accepted_risk": False,
                        "severity": "blocker",
                        "gate_effect": "operator_review_required",
                        "reason": "different blocker must not be accepted by learning readiness signoff",
                        "required_evidence": ["separate evidence required"],
                    }
                ],
            },
        )
        self._write_learning_signoff()

        report = build_report(self.vault, context=fixed_context())

        self.assertFalse(report["checked_in_release_ready"])
        self._assert_release_decision(
            report,
            state="blocked",
            machine_release_allowed=False,
            operator_release_allowed=False,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(report["blockers"][0]["code"], "other_learning_blocker")
        self.assertNotIn(
            "other_learning_blocker",
            {item["code"] for item in report["accepted_risks"]},
        )
        self.assertIn(
            "release_risk_taxonomy_unregistered_code",
            {item["code"] for item in report["blockers"]},
        )

    def test_unregistered_accepted_risk_code_blocks_clean_lane_with_taxonomy_guard(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "auto_improve_readiness",
            {
                "execution_readiness": {"can_run": True},
                "learning_readiness": {"status": "learning_uncertain"},
                "learning_claim_blockers": [
                    {
                        "id": "new_unclassified_learning_risk",
                        "accepted_risk": True,
                        "severity": "warn",
                        "gate_effect": "advisory",
                        "reason": "fixture risk not yet classified in taxonomy",
                        "required_evidence": ["taxonomy entry required"],
                    }
                ],
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertFalse(report["checked_in_release_ready"])
        self._assert_release_decision(
            report,
            state="blocked",
            machine_release_allowed=False,
            operator_release_allowed=False,
            requires_accepted_risk_review=False,
        )
        accepted = {item["code"]: item for item in report["accepted_risks"]}
        self.assertIn("new_unclassified_learning_risk", accepted)
        self.assertEqual(accepted["new_unclassified_learning_risk"]["clean_lane_effect"], "blocks_clean_lane")
        blockers = {item["code"]: item for item in report["blockers"]}
        self.assertIn("release_risk_taxonomy_unregistered_code", blockers)
        self.assertIn("new_unclassified_learning_risk", blockers["release_risk_taxonomy_unregistered_code"]["message"])

    def test_expired_learning_readiness_signoff_does_not_convert_blocker(self) -> None:
        self._write_happy_sources()
        self._write_learning_delta_scoreboard(claims_learning_improved=True, guard_status="blocked")
        self._write_source_report(
            "auto_improve_readiness",
            {
                "execution_readiness": {"can_run": True},
                "learning_readiness": {"status": "learning_uncertain"},
                "learning_claim_blockers": [
                    {
                        "id": "learning_blocked_by_review_required",
                        "accepted_risk": False,
                        "severity": "blocker",
                        "gate_effect": "operator_review_required",
                        "reason": "learning readiness still requires review",
                        "required_evidence": ["learning_readiness.likely_to_learn must be true"],
                    }
                ],
            },
        )
        self._write_learning_signoff({"expires_at": "2026-04-29T08:59:59Z"})

        report = build_report(self.vault, context=fixed_context())

        self.assertTrue(report["checked_in_release_ready"])
        self._assert_release_decision(
            report,
            state="clean_pass",
            machine_release_allowed=True,
            operator_release_allowed=True,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(report["learning_readiness_signoff"]["signoff_status"], "expired")
        self.assertEqual(report["blockers"][0]["code"], "learning_blocked_by_review_required")
        self.assertEqual(report["blockers"][0]["clean_lane_effect"], "does_not_block_clean_lane")
        self.assertEqual(report["summary"]["source_clean_blocker_count"], 0)

    def test_missing_input_report_is_a_closeout_blocker(self) -> None:
        self._write_happy_sources()
        (self.vault / self._source_spec("release_smoke").path).unlink()

        report = build_report(self.vault, context=fixed_context())

        self.assertFalse(report["checked_in_release_ready"])
        self._assert_release_decision(
            report,
            state="blocked",
            machine_release_allowed=False,
            operator_release_allowed=False,
            requires_accepted_risk_review=False,
        )
        self.assertEqual(report["blockers"][0]["code"], "release_smoke_report_missing")
        release_component = next(item for item in report["components"] if item["name"] == "release_smoke")
        self.assertEqual(release_component["load_status"], "missing")

    def test_closeout_write_report_validates_schema_and_stays_under_vault(self) -> None:
        self._write_happy_sources()
        report = build_report(self.vault, context=fixed_context())

        destination = write_report(self.vault, report)

        self.assertEqual(destination.resolve(), (self.vault / "ops" / "reports" / "release-closeout-summary.json").resolve())
        persisted = json.loads(destination.read_text(encoding="utf-8"))
        self.assertTrue(persisted["checked_in_release_ready"])
        self.assertEqual(persisted["artifact_freshness_gate"]["gate_effect"], "none")
        self.assertEqual(persisted["artifact_freshness_gate"]["display_effect"], "none")
        self.assertEqual(persisted["release_readiness_state"], "clean_pass")
        self.assertTrue(persisted["machine_release_allowed"])

    def test_main_uses_machine_release_allowed_for_strict_exit(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "test_summary",
            {
                "status": "pass",
                "command": "pytest tests/test_unrelated_runtime.py",
                "deselected_tests": [],
                "deselection_lifecycle": {
                    "status": "pass",
                    "checked_at": "2026-04-29T08:00:00Z",
                    "actual_deselected_count": 0,
                    "max_allowed_deselected_count": 0,
                    "over_budget": False,
                    "expired_count": 0,
                    "release_blocking_count": 0,
                    "missing_lifecycle_count": 0,
                    "duplicate_policy_entry_count": 0,
                    "unused_policy_entry_count": 0,
                    "risk_owner": "runtime-maintainer",
                    "expires_at": "",
                    "count_increase_gate_effect": "fail",
                    "expiry_gate_effect": "fail",
                    "next_action": "none",
                    "blockers": [],
                },
            },
        )

        exit_code = main(["--vault", self.vault.as_posix()])

        self.assertEqual(exit_code, 1)
        persisted = json.loads(
            (self.vault / "ops" / "reports" / "release-closeout-summary.json").read_text(
                encoding="utf-8",
            )
        )
        self.assertTrue(persisted["checked_in_release_ready"])
        self.assertEqual(persisted["release_readiness_state"], "unknown")
        self.assertFalse(persisted["machine_release_allowed"])
        self.assertFalse(persisted["operator_release_allowed"])
        self.assertFalse(persisted["requires_accepted_risk_review"])

    def test_main_allow_conditional_exits_zero_for_operator_allowed_state(self) -> None:
        self._write_happy_sources()
        self._write_source_report("artifact_freshness", {"status": "attention"})

        exit_code = main(["--vault", self.vault.as_posix(), "--allow-conditional"])

        self.assertEqual(exit_code, 0)
        persisted = json.loads(
            (self.vault / "ops" / "reports" / "release-closeout-summary.json").read_text(
                encoding="utf-8",
            )
        )
        self.assertEqual(persisted["release_readiness_state"], "conditional_pass")
        self.assertEqual(persisted["release_authority_status"], "conditional_pass")
        self.assertEqual(persisted["semantic_release_status"], "conditional_pass")
        self.assertEqual(
            persisted["source_closeout_distribution_binding_status"],
            "unsealed_distribution_not_provided",
        )
        self.assertEqual(
            persisted["sealed_release_status"], "unsealed_distribution_not_provided"
        )
        self.assertEqual(
            persisted["status_v2"]["status_classification"], "conditional_release"
        )
        self.assertEqual(
            persisted["status_v2"]["authority_reason_ids"],
            [
                "release_authority_not_clean_pass",
                "machine_release_not_allowed",
            ],
        )
        self.assertFalse(persisted["machine_release_allowed"])
        self.assertTrue(persisted["operator_release_allowed"])
        self.assertTrue(persisted["requires_accepted_risk_review"])

    def test_main_no_fail_writes_failed_closeout_and_exits_zero(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "auto_improve_readiness",
            {
                "execution_readiness": {"can_run": False},
                "learning_readiness": {"status": "not_runnable"},
                "learning_claim_blockers": [],
            },
        )

        exit_code = main(["--vault", self.vault.as_posix(), "--no-fail"])

        self.assertEqual(exit_code, 0)
        persisted = json.loads(
            (self.vault / "ops" / "reports" / "release-closeout-summary.json").read_text(
                encoding="utf-8",
            )
        )
        self.assertTrue(persisted["checked_in_release_ready"])
        self.assertEqual(persisted["release_readiness_state"], "clean_pass")
        self.assertTrue(persisted["machine_release_allowed"])
        self.assertEqual(persisted["blockers"][0]["code"], "auto_improve_execution_not_ready")
        self.assertEqual(persisted["blockers"][0]["clean_lane_effect"], "does_not_block_clean_lane")


if __name__ == "__main__":
    unittest.main()
