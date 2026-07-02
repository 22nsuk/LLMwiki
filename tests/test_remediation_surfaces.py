from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.mechanism.system_log_split import migrate_system_log
from ops.scripts.public.review_surface_manifest import (
    CANONICAL_MD_OUT,
    EPHEMERAL_JSON_OUT,
    ReviewSurfaceOutputContractError,
    build_manifest,
    render_markdown,
    validate_review_surface_output_paths,
)
from ops.scripts.registry.source_substance_cohort_classify import build_report
from ops.scripts.test.generate_release_governance_from_lane_registry import (
    validate_alignment,
)
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = [
    pytest.mark.public,
    pytest.mark.report_contract,
    pytest.mark.default_test_boundary,
]


class RemediationSurfaceTests(unittest.TestCase):
    def test_release_governance_alignment_passes_for_repo(self) -> None:
        report = validate_alignment(REPO_ROOT)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["mismatched_fields"], [])

    def test_review_surface_manifest_counts_public_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "docs").mkdir(exist_ok=True)
            (vault / "docs" / "note.md").write_text("# note\n", encoding="utf-8")
            manifest = build_manifest(vault)
            self.assertEqual(manifest["status"], "pass")
            self.assertGreaterEqual(manifest["surfaces"]["docs"]["file_count"], 1)
            contract = manifest["output_contract"]
            self.assertEqual(contract["canonical_surface"], CANONICAL_MD_OUT)
            self.assertEqual(contract["ephemeral_surface"], EPHEMERAL_JSON_OUT)
            markdown = render_markdown(manifest)
            self.assertIn("## Recommended commands", markdown)
            self.assertIn("intentionally ephemeral", markdown)
            self.assertIn(EPHEMERAL_JSON_OUT, markdown)

    def test_review_surface_output_contract_rejects_noncanonical_paths(self) -> None:
        with self.assertRaises(ReviewSurfaceOutputContractError):
            validate_review_surface_output_paths(
                json_out="ops/reports/review-surface-manifest.json",
                md_out=CANONICAL_MD_OUT,
            )
        with self.assertRaises(ReviewSurfaceOutputContractError):
            validate_review_surface_output_paths(
                json_out=EPHEMERAL_JSON_OUT,
                md_out="docs/other-scope.md",
            )
        with self.assertRaises(ReviewSurfaceOutputContractError):
            validate_review_surface_output_paths(
                json_out="build/review-surface-manifest.json",
                md_out=CANONICAL_MD_OUT,
            )

    def test_repo_review_scope_doc_matches_canonical_contract(self) -> None:
        self.assertTrue((REPO_ROOT / CANONICAL_MD_OUT).is_file())
        text = (REPO_ROOT / CANONICAL_MD_OUT).read_text(encoding="utf-8")
        self.assertIn("Canonical full-vault reviewer-facing inventory", text)
        self.assertIn(EPHEMERAL_JSON_OUT, text)
        self.assertFalse((REPO_ROOT / "ops/reports/review-surface-manifest.json").exists())

    def test_system_log_split_writes_events_and_decision_stub(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            log_path = vault / "system" / "system-log.md"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                "\n".join(
                    [
                        "---",
                        "title: System Log",
                        "---",
                        "",
                        "# System Log",
                        "",
                        "---",
                        "",
                        "## [2026-06-20 12:00] bootstrap | First entry",
                        "",
                        "body",
                    ]
                ),
                encoding="utf-8",
            )
            result = migrate_system_log(vault)
            self.assertEqual(result["status"], "migrated")
            self.assertEqual(result["migrated_count"], 1)
            self.assertIn("# System Log", log_path.read_text(encoding="utf-8"))
            events = (vault / "system" / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(events), 1)
            payload = json.loads(events[0])
            self.assertEqual(
                payload["heading"],
                "[2026-06-20 12:00] bootstrap | First entry",
            )
            self.assertTrue((vault / "system" / "decision-log.md").is_file())

    def test_source_substance_cohort_classify_demotes_weak_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            wiki = vault / "wiki"
            wiki.mkdir(parents=True, exist_ok=True)
            page = wiki / "source--weak-2026-05-29.md"
            page.write_text(
                "\n".join(
                    [
                        "# Weak source",
                        "",
                        "## Summary",
                        "Weak source repeats the title without source-specific facts.",
                        "",
                        "## Key points",
                        "- Weak source",
                        "- one",
                        "- two",
                        "- three",
                        "",
                        "## Limitations / caveats",
                        "- snapshot caveat only",
                        "",
                        "## Open questions",
                        "- none",
                    ]
                ),
                encoding="utf-8",
            )
            report = build_report(vault)
            self.assertEqual(report["summary"]["page_count"], 1)
            self.assertEqual(report["entries"][0]["classification"], "registry_only_demote")
