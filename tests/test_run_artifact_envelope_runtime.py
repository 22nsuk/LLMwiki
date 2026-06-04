from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from ops.scripts.artifact_freshness_runtime import EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY
from ops.scripts.backfill_archived_run_artifacts import ARCHIVED_RUN_ARTIFACT_SPECS
from ops.scripts.run_artifact_envelope_runtime import maybe_embed_run_artifact_envelope

from tests.minimal_vault_runtime import seed_minimal_vault

REPO_ROOT = Path(__file__).resolve().parents[1]


def _behavior_delta_payload() -> dict:
    return {
        "$schema": "ops/schemas/behavior-delta.schema.json",
        "run_id": "run-envelope",
        "generated_at": "2026-04-16T00:00:00Z",
        "policy": {
            "path": "ops/policies/wiki-maintainer-policy.yaml",
            "version": 1,
        },
        "primary_targets": ["ops/scripts/example.py"],
        "supporting_targets": [],
        "test_files": ["tests/test_example.py"],
        "inputs": {
            "baseline_eval_report": "runs/run-envelope/baseline-eval.json",
            "candidate_eval_report": "runs/run-envelope/candidate-eval.json",
            "baseline_lint_report": "runs/run-envelope/baseline-lint.json",
            "candidate_lint_report": "runs/run-envelope/candidate-lint.json",
            "baseline_mechanism_report": "runs/run-envelope/baseline-mechanism-assessment.json",
            "candidate_mechanism_report": "runs/run-envelope/candidate-mechanism-assessment.json",
            "changed_files_manifest": "runs/run-envelope/changed-files-manifest.json",
        },
        "summary": {
            "behavior_changed": False,
            "changed_file_count": 0,
            "delta_count": 0,
            "intended_change_count": 0,
            "unexpected_change_count": 0,
            "unknown_intent_count": 0,
            "risk_counts": {"none": 0, "low": 0, "medium": 0, "high": 0},
            "contract_touch_count": 0,
            "coverage_gap_count": 0,
            "regression_count": 0,
        },
        "deltas": [],
        "diagnostics": {"notes": [], "skipped_files": []},
    }


def _embedded_envelope(payload: dict) -> dict:
    for item in payload["metadata"]["properties"]:
        if item["name"] == EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY:
            return json.loads(item["value"])
    raise AssertionError("missing embedded artifact envelope")


def _canonical_source_path(rel_path: str) -> str:
    normalized = Path(rel_path).as_posix()
    if (REPO_ROOT / normalized).exists():
        return normalized
    parts = normalized.split("/")
    if len(parts) == 3 and parts[:2] == ["ops", "scripts"] and parts[2].endswith(".py"):
        matches = sorted((REPO_ROOT / "ops" / "scripts").glob(f"*/{parts[2]}"))
        if len(matches) == 1:
            return matches[0].relative_to(REPO_ROOT).as_posix()
    return ""


class RunArtifactEnvelopeRuntimeTests(unittest.TestCase):
    def test_envelope_fingerprints_payload_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            first = maybe_embed_run_artifact_envelope(
                vault,
                "runs/run-envelope/behavior-delta.json",
                _behavior_delta_payload(),
                schema_path="ops/schemas/behavior-delta.schema.json",
            )
            changed_payload = deepcopy(_behavior_delta_payload())
            changed_payload["summary"]["changed_file_count"] = 1
            second = maybe_embed_run_artifact_envelope(
                vault,
                "runs/run-envelope/behavior-delta.json",
                changed_payload,
                schema_path="ops/schemas/behavior-delta.schema.json",
            )

            first_fingerprint = _embedded_envelope(first)["input_fingerprints"][
                "run_artifact_payload_before_envelope"
            ]
            second_fingerprint = _embedded_envelope(second)["input_fingerprints"][
                "run_artifact_payload_before_envelope"
            ]
            self.assertNotEqual(first_fingerprint, second_fingerprint)

    def test_supported_run_artifact_missing_timestamp_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            payload = _behavior_delta_payload()
            payload.pop("generated_at")

            with self.assertRaisesRegex(ValueError, "generated_at"):
                maybe_embed_run_artifact_envelope(
                    vault,
                    "runs/run-envelope/behavior-delta.json",
                    payload,
                    schema_path="ops/schemas/behavior-delta.schema.json",
                )

    def test_missing_policy_leaves_schema_validation_independent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "policies" / "wiki-maintainer-policy.yaml").unlink()
            payload = _behavior_delta_payload()

            result = maybe_embed_run_artifact_envelope(
                vault,
                "runs/run-envelope/behavior-delta.json",
                payload,
                schema_path="ops/schemas/behavior-delta.schema.json",
            )

            self.assertEqual(result, payload)

    def test_archived_run_artifact_spec_source_paths_resolve(self) -> None:
        unresolved: list[str] = []
        for spec in ARCHIVED_RUN_ARTIFACT_SPECS.values():
            for rel_path in spec.source_paths:
                if not _canonical_source_path(rel_path):
                    unresolved.append(f"{spec.filename}: {rel_path}")

        self.assertEqual(unresolved, [])


if __name__ == "__main__":
    unittest.main()
