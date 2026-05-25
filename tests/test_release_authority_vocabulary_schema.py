"""Contract tests for the release-authority vocabulary schema."""
from __future__ import annotations

import unittest

import pytest
from ops.scripts.schema_constants_runtime import (
    RELEASE_AUTHORITY_VOCABULARY_SCHEMA_PATH,
    RELEASE_AUTHORITY_VOCABULARY_SCHEMA_URI,
)
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from ops.scripts import release_authority_vocabulary as vocabulary

pytestmark = pytest.mark.public


class ReleaseAuthorityVocabularySchemaTests(unittest.TestCase):
    def test_vocabulary_schema_is_registered(self) -> None:
        schema = load_schema(RELEASE_AUTHORITY_VOCABULARY_SCHEMA_PATH)

        self.assertEqual(schema["$id"], RELEASE_AUTHORITY_VOCABULARY_SCHEMA_URI)

    def test_reason_ids_match_runtime_helper_constants(self) -> None:
        schema = load_schema(RELEASE_AUTHORITY_VOCABULARY_SCHEMA_PATH)
        reason_ids = set(schema["$defs"]["release_authority_reason_id"]["enum"])
        expected = {
            vocabulary.REASON_RELEASE_AUTHORITY_NOT_CLEAN_PASS,
            vocabulary.REASON_MACHINE_RELEASE_NOT_ALLOWED,
            vocabulary.REASON_SEALED_RELEASE_NOT_CLEAN_PASS,
            vocabulary.REASON_DISTRIBUTION_PACKAGE_NOT_MATERIALIZED,
            vocabulary.REASON_ARTIFACT_INVENTORY_NOT_CURRENT,
        }

        self.assertEqual(reason_ids, expected)

    def test_operator_summary_round_trips_decision_fields(self) -> None:
        payload = vocabulary.release_authority_vocabulary_payload(
            release_authority_status="conditional_pass",
            semantic_release_status="conditional_pass",
            sealed_release_status="sealed_conditional_pass",
            machine_release_allowed=False,
            clean_release_ready=False,
            batch_integrity_status="pass",
            distribution_package={"status": "not_provided"},
        )

        round_trip = payload["operator_summary_round_trip"]

        self.assertEqual(round_trip["status"], "pass")
        self.assertEqual(round_trip["mismatch_count"], 0)
        self.assertEqual(round_trip["mismatches"], [])
        self.assertEqual(round_trip["parser"], vocabulary.OPERATOR_SUMMARY_PARSER_ID)
        self.assertEqual(round_trip["parsed"], round_trip["expected"])
        self.assertIn(
            "release_authority_status=conditional_pass",
            payload["operator_summary"],
        )
        self.assertEqual(
            round_trip["parsed"]["blocker_reason_ids"],
            [
                "release_authority_not_clean_pass",
                "machine_release_not_allowed",
                "sealed_release_not_clean_pass",
                "distribution_package_not_materialized",
            ],
        )

    def test_operator_summary_round_trip_detects_tampered_wording(self) -> None:
        payload = vocabulary.release_authority_vocabulary_payload(
            release_authority_status="clean_pass",
            semantic_release_status="clean_pass",
            sealed_release_status="sealed_clean_pass",
            machine_release_allowed=True,
            clean_release_ready=True,
            batch_integrity_status="pass",
            distribution_package={"status": "materialized"},
        )
        tampered_summary = payload["operator_summary"].replace(
            "machine_release_allowed=true",
            "machine_release_allowed=false",
        )

        round_trip = vocabulary.release_authority_operator_summary_round_trip(
            operator_summary=tampered_summary,
            expected=payload["operator_summary_round_trip"]["expected"],
        )

        self.assertEqual(round_trip["status"], "fail")
        self.assertEqual(round_trip["mismatch_count"], 1)
        self.assertEqual(
            round_trip["mismatches"],
            [
                {
                    "field": "machine_release_allowed",
                    "expected": "true",
                    "actual": "false",
                }
            ],
        )

    def test_operator_summary_schema_parser_id_matches_runtime(self) -> None:
        schema = load_schema(RELEASE_AUTHORITY_VOCABULARY_SCHEMA_PATH)

        self.assertEqual(
            schema["$defs"]["operator_summary_parser"]["const"],
            vocabulary.OPERATOR_SUMMARY_PARSER_ID,
        )
        self.assertEqual(
            tuple(schema["$defs"]["operator_summary_field"]["enum"]),
            vocabulary.OPERATOR_SUMMARY_FIELDS,
        )

    def test_batch_manifest_schema_uses_vocabulary_ref(self) -> None:
        schema = load_schema("ops/schemas/release-closeout-batch-manifest.schema.json")
        reason_ref = schema["$defs"]["release_authority_reason_id"]

        self.assertEqual(
            reason_ref["$ref"],
            "https://llmwiki/schemas/release-authority-vocabulary#/$defs/release_authority_reason_id",
        )

    def test_reason_id_schema_rejects_legacy_batch_failure_id(self) -> None:
        schema = load_schema(RELEASE_AUTHORITY_VOCABULARY_SCHEMA_PATH)
        reason_schema = schema["$defs"]["release_authority_reason_id"]

        self.assertEqual(
            validate_with_schema(vocabulary.REASON_RELEASE_AUTHORITY_NOT_CLEAN_PASS, reason_schema),
            [],
        )

        errors = validate_with_schema("batch_release_authority_not_clean_pass", reason_schema)
        self.assertTrue(errors)
        self.assertTrue(
            any(vocabulary.REASON_RELEASE_AUTHORITY_NOT_CLEAN_PASS in error for error in errors)
        )


if __name__ == "__main__":
    unittest.main()
