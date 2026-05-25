from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.release_clean_lane_evidence_review import build_report
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-clean-lane-evidence-review.schema.json"


def write_closeout_summary(path: Path, *, source_tree_status: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "status": "pass",
                "release_readiness_state": "conditional_pass",
                "machine_release_allowed": False,
                "source_tree_coherence": {
                    "status": source_tree_status,
                    "component_count": 2,
                    "components": [
                        {
                            "name": "release_smoke",
                            "source_tree_fingerprint": "aaa",
                        },
                        {
                            "name": "test_summary",
                            "source_tree_fingerprint": "bbb",
                        },
                    ],
                },
                "accepted_risks": [
                    {
                        "source": "generated_index",
                        "source_path": "ops/reports/generated-artifact-index.json",
                        "code": "generated_index_archive_advisory",
                        "clean_lane_effect": "does_not_block_clean_lane",
                        "conditional_lane_effect": "not_applicable",
                        "advisory_lifecycle_effect": "review_backlog",
                        "required_evidence": [],
                    },
                    {
                        "source": "source_tree_coherence",
                        "source_path": "ops/reports/release-closeout-summary.json",
                        "code": "source_tree_coherence_attention",
                        "clean_lane_effect": "blocks_clean_lane",
                        "conditional_lane_effect": "operator_review_required",
                        "advisory_lifecycle_effect": "not_applicable",
                        "required_evidence": ["regenerate in one chain"],
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


class ReleaseCleanLaneEvidenceReviewTests(unittest.TestCase):
    def test_separates_clean_non_blocking_and_same_chain_refresh_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            closeout = vault / "ops" / "reports" / "release-closeout-summary.json"
            write_closeout_summary(closeout, source_tree_status="attention")

            report = build_report(vault, closeout_summary_path=closeout)

            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["summary"]["accepted_risk_count"], 2)
            self.assertEqual(report["summary"]["already_clean_non_blocking_count"], 1)
            self.assertEqual(report["summary"]["same_chain_refresh_required_count"], 1)
            self.assertEqual(
                report["evidence_units"][1]["demotion_status"],
                "requires_same_chain_refresh",
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_source_tree_attention_can_be_demoted_after_coherent_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            closeout = vault / "ops" / "reports" / "release-closeout-summary.json"
            write_closeout_summary(closeout, source_tree_status="pass")

            report = build_report(vault, closeout_summary_path=closeout)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["clean_pass_candidate_count"], 2)
            self.assertEqual(
                report["evidence_units"][1]["demotion_status"], "clean_pass_ready"
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
