"""Contract tests: accepted-risk-vocabulary $ref resolution.

Verifies that schemas using $ref to the accepted-risk-vocabulary can validate
documents with accepted-risk count fields, and that the vocabulary definitions
are correctly resolved via the LOCAL_SCHEMA_ALIASES registry.
"""
from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

import pytest
from ops.scripts.release_closeout_summary import (
    LEARNING_REVIEW_BLOCKER_ID,
    TAXONOMY_COVERAGE_BLOCKER_ID,
)
from ops.scripts.schema_constants_runtime import (
    ACCEPTED_RISK_VOCABULARY_SCHEMA_PATH,
    ACCEPTED_RISK_VOCABULARY_SCHEMA_URI,
    LEARNING_READINESS_VOCABULARY_SCHEMA_PATH,
    RELEASE_RISK_TAXONOMY_SCHEMA_PATH,
)
from ops.scripts.schema_runtime import load_schema, validate_with_schema

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_CLEAN_BLOCKER_LEDGER_SCHEMA_PATH = (
    REPO_ROOT / "ops" / "schemas" / "release-clean-blocker-ledger.schema.json"
)
RELEASE_CLOSEOUT_SUMMARY_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-closeout-summary.schema.json"
RELEASE_LANE_SUMMARY_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-lane-summary.schema.json"
RELEASE_RISK_TAXONOMY_POLICY_PATH = REPO_ROOT / "ops" / "policies" / "release-risk-taxonomy.json"
RELEASE_CLOSEOUT_SUMMARY_SCRIPT_PATH = REPO_ROOT / "ops" / "scripts" / "release" / "release_closeout_summary.py"


class AcceptedRiskVocabularyRegistrationTests(unittest.TestCase):
    """Verify the vocabulary schema is registered and has $id."""

    def test_vocabulary_schema_has_id(self) -> None:
        schema = load_schema(ACCEPTED_RISK_VOCABULARY_SCHEMA_PATH)
        self.assertEqual(schema["$id"], ACCEPTED_RISK_VOCABULARY_SCHEMA_URI)

    def test_vocabulary_schema_has_required_defs(self) -> None:
        schema = load_schema(ACCEPTED_RISK_VOCABULARY_SCHEMA_PATH)
        defs = schema.get("$defs", {})
        expected = {
            "accepted_risk_family_count",
            "accepted_risk_instance_count",
            "accepted_risk_count",
            "gate_attention_count",
            "operator_accepted_risk_family_count",
            "clean_lane_blocking_accepted_risk_family_count",
            "clean_lane_blocking_family_count",
            "learning_claim_blocking_family_count",
            "advisory_lifecycle_family_count",
            "release_blocking_risk_family_count",
            "conditional_operator_review_risk_family_count",
            "learning_claim_blocking_risk_family_count",
            "advisory_lifecycle_risk_family_count",
            "advisory_risk_family_count",
        }
        self.assertEqual(set(defs.keys()), expected)

    def test_vocabulary_defs_are_integer_nonnegative(self) -> None:
        schema = load_schema(ACCEPTED_RISK_VOCABULARY_SCHEMA_PATH)
        for name, defn in schema["$defs"].items():
            with self.subTest(field=name):
                self.assertEqual(defn["type"], "integer")
                self.assertEqual(defn["minimum"], 0)


class ReleaseRiskTaxonomyPolicyTests(unittest.TestCase):
    def test_release_risk_taxonomy_policy_is_schema_valid(self) -> None:
        schema = load_schema(RELEASE_RISK_TAXONOMY_SCHEMA_PATH)
        payload = json.loads(RELEASE_RISK_TAXONOMY_POLICY_PATH.read_text(encoding="utf-8"))

        self.assertEqual(validate_with_schema(payload, schema), [])

    def test_archive_advisory_is_review_backlog_not_clean_lane_blocker(self) -> None:
        payload = json.loads(RELEASE_RISK_TAXONOMY_POLICY_PATH.read_text(encoding="utf-8"))
        effects = payload["risks"]["generated_index_archive_advisory"]["effects"]

        self.assertEqual(effects["clean_lane_effect"], "does_not_block_clean_lane")
        self.assertEqual(effects["advisory_lifecycle_effect"], "review_backlog")
        self.assertEqual(effects["learning_lane_effect"], "not_applicable")

    def test_stable_artifact_contract_debt_is_review_backlog_not_clean_lane_blocker(self) -> None:
        payload = json.loads(RELEASE_RISK_TAXONOMY_POLICY_PATH.read_text(encoding="utf-8"))
        effects = payload["risks"]["artifact_freshness_stable_contract_debt_advisory"]["effects"]

        self.assertEqual(effects["clean_lane_effect"], "does_not_block_clean_lane")
        self.assertEqual(effects["advisory_lifecycle_effect"], "review_backlog")
        self.assertEqual(effects["learning_lane_effect"], "not_applicable")

    def test_closeout_static_release_risk_codes_are_registered(self) -> None:
        tree = ast.parse(RELEASE_CLOSEOUT_SUMMARY_SCRIPT_PATH.read_text(encoding="utf-8"))
        emitted_codes = {LEARNING_REVIEW_BLOCKER_ID, TAXONOMY_COVERAGE_BLOCKER_ID}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg not in {"code", "blocker_code", "accepted_code"}:
                    continue
                if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    code = keyword.value.value.strip()
                    if code:
                        emitted_codes.add(code)

        payload = json.loads(RELEASE_RISK_TAXONOMY_POLICY_PATH.read_text(encoding="utf-8"))
        registered_codes = set(payload["risks"])

        self.assertEqual(sorted(emitted_codes - registered_codes), [])

    def test_learning_release_blocker_ids_are_registered_in_release_taxonomy(self) -> None:
        vocabulary = load_schema(LEARNING_READINESS_VOCABULARY_SCHEMA_PATH)
        blocker_ids = set(vocabulary["$defs"]["release_blocker_id"]["enum"])
        taxonomy = json.loads(RELEASE_RISK_TAXONOMY_POLICY_PATH.read_text(encoding="utf-8"))
        registered_codes = set(taxonomy["risks"])

        self.assertEqual(sorted(blocker_ids - registered_codes), [])

        downstream_release_gate_ids = {
            "promotion_blocked_by_release_closeout_summary_failure",
            "promotion_blocked_by_release_batch_manifest_failure",
            "promotion_blocked_by_release_authority_preflight_failure",
            "promotion_blocked_by_release_finality_failure",
            "promotion_blocked_by_artifact_finalization_failure",
        }
        for blocker_id in downstream_release_gate_ids:
            with self.subTest(blocker_id=blocker_id):
                effects = taxonomy["risks"][blocker_id]["effects"]
                self.assertEqual(effects["clean_lane_effect"], "does_not_block_clean_lane")
                self.assertEqual(effects["conditional_lane_effect"], "operator_review_required")
                self.assertEqual(effects["learning_lane_effect"], "blocks_learning_claim")


class CleanBlockerLedgerVocabRefTests(unittest.TestCase):
    """Verify that release-clean-blocker-ledger schema resolves vocabulary $ref correctly."""

    def _schema(self) -> dict:
        return load_schema(RELEASE_CLEAN_BLOCKER_LEDGER_SCHEMA_PATH)

    def _fixture_doc(self) -> dict:
        """Build a public-safe minimal document proving the schema $ref resolves."""
        return {
            "$schema": "ops/schemas/release-clean-blocker-ledger.schema.json",
            "artifact_kind": "release_clean_blocker_ledger",
            "generated_at": "2026-05-04T00:00:00Z",
            "producer": "ops.scripts.release_clean_blocker_ledger",
            "source_command": "python -m ops.scripts.release.release_clean_blocker_ledger --vault .",
            "source_revision": "unknown",
            "source_tree_fingerprint": "fixture",
            "input_fingerprints": {"fixture": "sha256"},
            "schema_version": 1,
            "artifact_status": "current",
            "retention_policy": "canonical_report",
            "encoding": "utf-8",
            "currentness": {"status": "current", "checked_at": "2026-05-04T00:00:00Z"},
            "vault": ".",
            "policy": {"path": "ops/policies/release-closeout-batch.json", "version": 1},
            "status": "attention",
            "summary": {
                "advisory_backlog_status": "clear",
                "advisory_backlog_active_count": 0,
                "advisory_backlog_expired_count": 0,
                "advisory_backlog_missing_lifecycle_count": 0,
                "blocker_count": 0,
                "source_clean_blocker_count": 0,
                "auto_improve_blocker_count": 0,
                "accepted_risk_family_count": 0,
                "accepted_risk_instance_count": 0,
                "clean_lane_blocking_family_count": 0,
                "learning_claim_blocking_family_count": 0,
                "advisory_lifecycle_family_count": 0,
                "clean_lane_status": "pass",
                "conditional_lane_status": "pass",
                "auto_improve_lane_status": "pass",
                "machine_release_status": "allowed",
                "operator_release_status": "allowed",
                "release_authority_status": "conditional_pass",
                "sealed_release_status": "unsealed_distribution_not_provided",
                "learning_claim_guard_status": "pass",
                "learning_claim_allowed": False,
                "same_eval_reason_coverage_status": "none",
                "strict_secondary_improvement_coverage_status": "none",
                "behavior_delta_digest_coverage_status": "none",
                "placeholder_audit_status": "pass",
            },
            "learning_claim_guard": {
                "path": "ops/reports/learning-delta-scoreboard.json",
                "load_status": "ok",
                "status": "pass",
                "claims_learning_improved": False,
                "learning_claim_allowed": False,
                "same_eval_run_count": 0,
                "telemetry_coverage_status": "none",
                "same_eval_reason_coverage_status": "none",
                "strict_secondary_improvement_coverage_status": "none",
                "behavior_delta_digest_coverage_status": "none",
                "placeholder_audit_status": "pass",
                "placeholder_count": 0,
                "reason": "fixture",
            },
            "clean_lane_contract": {"status": "pass", "failed_conditions": []},
            "blockers": [],
            "source_clean_blockers": [],
            "auto_improve_blockers": [],
            "learning_claim_blockers": [],
            "advisory_backlog": [],
            "provenance": {
                "closeout_source": "fixture",
                "cohort_source": "fixture",
                "lane_summary_source": "fixture",
                "learning_delta_scoreboard_source": "fixture",
            },
        }

    def test_schema_uses_ref_for_accepted_risk_family_count(self) -> None:
        """The schema property must use $ref not inline type/minimum."""
        schema = self._schema()
        summary_props = schema.get("properties", {}).get("summary", {}).get("properties", {})
        arfc = summary_props.get("accepted_risk_family_count", {})
        self.assertIn("$ref", arfc, "accepted_risk_family_count should use $ref in clean-blocker-ledger")

    def test_schema_uses_ref_for_clean_lane_blocking_family_count(self) -> None:
        schema = self._schema()
        summary_props = schema.get("properties", {}).get("summary", {}).get("properties", {})
        clbfc = summary_props.get("clean_lane_blocking_family_count", {})
        self.assertIn("$ref", clbfc, "clean_lane_blocking_family_count should use $ref")

    def test_live_document_passes_schema_after_ref_promotion(self) -> None:
        """A public-safe ledger fixture validates successfully after $ref promotion."""
        schema = self._schema()
        doc = self._fixture_doc()
        errors = validate_with_schema(doc, schema)
        self.assertEqual(errors, [], f"Unexpected schema errors after $ref promotion: {errors}")

    def test_negative_accepted_risk_count_fails_validation(self) -> None:
        """Negative integer fails — proves vocabulary minimum:0 constraint is inherited via $ref."""
        schema = self._schema()
        doc = self._fixture_doc()
        doc["summary"]["accepted_risk_family_count"] = -1  # invalid: below minimum
        errors = validate_with_schema(doc, schema)
        self.assertGreater(len(errors), 0, "Negative count should fail schema validation")


class AcceptedRiskCrossArtifactVocabularyTests(unittest.TestCase):
    def test_release_authority_schemas_reconcile_shared_count_refs(self) -> None:
        expected_refs = {
            "accepted_risk_family_count": (
                "https://llmwiki/schemas/accepted-risk-vocabulary#/$defs/accepted_risk_family_count"
            ),
            "accepted_risk_instance_count": (
                "https://llmwiki/schemas/accepted-risk-vocabulary#/$defs/accepted_risk_instance_count"
            ),
        }
        schema_paths = {
            "release-clean-blocker-ledger": (RELEASE_CLEAN_BLOCKER_LEDGER_SCHEMA_PATH, "summary"),
            "release-closeout-summary": (RELEASE_CLOSEOUT_SUMMARY_SCHEMA_PATH, "summary"),
            "release-lane-summary": (RELEASE_LANE_SUMMARY_SCHEMA_PATH, "lane_summary"),
        }

        for artifact_name, (schema_path, property_name) in schema_paths.items():
            schema = load_schema(schema_path)
            summary_props = schema.get("properties", {}).get(property_name, {}).get("properties", {})
            for field, expected_ref in expected_refs.items():
                with self.subTest(artifact=artifact_name, field=field):
                    self.assertEqual(summary_props.get(field, {}).get("$ref"), expected_ref)
