from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.registry.raw_intake_route_proposal import (
    build_report,
    main as route_proposal_main,
)
from tests.cli_test_runtime import invoke_cli_main
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "raw-intake-route-proposal-report.schema.json"
MATRIX_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "raw-intake-absorption-matrix.schema.json"


def write_matrix(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/raw-intake-absorption-matrix.schema.json",
                "generated_at": "2026-04-22T00:00:00Z",
                "scope": "unit-test",
                "source_count": len(entries),
                "action_counts": {},
                "confidence_counts": {},
                "target_counts": {},
                "matrix": entries,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def matrix_entry(**overrides: Any) -> dict[str, Any]:
    entry = {
        "registry_id": "W-001",
        "title": "Deterministic route",
        "raw_path": "raw/source.md",
        "source_page": "wiki/source--deterministic.md",
        "current_topic_family": "family",
        "current_domain": "domain",
        "proposed_action": "refresh_existing_synthesis",
        "target": "synthesis--target",
        "rationale": "Reviewed target selected from the absorption matrix.",
        "confidence": "medium",
        "review_status": "reviewed",
    }
    entry.update(overrides)
    return entry


class RawIntakeRouteProposalTests(unittest.TestCase):
    def test_cli_writes_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)
            matrix_path = vault / "runs" / "matrix.json"
            write_matrix(matrix_path, [matrix_entry()])

            completed = invoke_cli_main(
                route_proposal_main,
                [
                    "--vault",
                    str(vault),
                    "--matrix",
                    "runs/matrix.json",
                    "--out",
                    "reports/raw-intake/route-proposal.json",
                ],
                cwd=launcher,
            )
            self.assertEqual(completed.exit_code, 0, msg=completed.stderr or completed.stdout)

            report_path = vault / "reports" / "raw-intake" / "route-proposal.json"
            self.assertTrue(report_path.exists())
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["$schema"], "ops/schemas/raw-intake-route-proposal-report.schema.json")
            self.assertEqual(payload["status"], "pass")

    def test_route_proposal_is_deterministic_and_schema_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            matrix_path = vault / "runs" / "matrix.json"
            write_matrix(matrix_path, [matrix_entry()])

            first = build_report(vault, matrix_path=matrix_path)
            second = build_report(vault, matrix_path=matrix_path)

            self.assertEqual(first["status"], "pass")
            self.assertEqual(first["summary"]["review_satisfied_count"], 1)
            self.assertEqual(first["summary"]["audit_clear_count"], 1)
            self.assertEqual(
                first["proposals"][0]["route_key"],
                second["proposals"][0]["route_key"],
            )
            self.assertEqual(first["proposals"][0]["route_basis"]["current_domain"], "domain")
            self.assertEqual(first["proposals"][0]["route_audit"]["audit_status"], "clear")
            self.assertEqual(first["proposals"][0]["identity_audit"]["status"], "skipped")
            self.assertEqual(first["summary"]["identity_skipped_count"], 1)
            self.assertEqual(validate_with_schema(first, load_schema(SCHEMA_PATH)), [])

    def test_route_identity_audit_passes_when_raw_and_source_page_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            raw_path = vault / "raw" / "source.md"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(
                """---
title: "Stable Identity"
source: "https://example.test/source"
---

# Stable Identity
""",
                encoding="utf-8",
            )
            source_page = vault / "wiki" / "source--stable-identity.md"
            source_page.write_text(
                """---
title: "Stable Identity"
page_type: "source"
corpus: "wiki"
raw_path: "raw/source.md"
aliases:
  - "source--stable-identity"
tags:
  - "corpus/wiki"
  - "type/source"
---

# source--stable-identity

## Title
Stable Identity

## Source
- raw 경로: `raw/source.md`
- 원문 URL: `https://example.test/source`
""",
                encoding="utf-8",
            )
            matrix_path = vault / "runs" / "matrix.json"
            write_matrix(
                matrix_path,
                [
                    matrix_entry(
                        title="Stable Identity",
                        source_url="https://example.test/source",
                        source_page="wiki/source--stable-identity.md",
                    )
                ],
            )
            matrix_payload = json.loads(matrix_path.read_text(encoding="utf-8"))
            self.assertEqual(
                validate_with_schema(matrix_payload, load_schema(MATRIX_SCHEMA_PATH)),
                [],
            )

            report = build_report(vault, matrix_path=matrix_path)

            identity = report["proposals"][0]["identity_audit"]
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["identity_pass_count"], 1)
            self.assertEqual(identity["status"], "pass")
            self.assertEqual(
                {check["name"] for check in identity["checks"] if check["status"] == "pass"},
                {
                    "matrix_title_matches_raw_title",
                    "matrix_title_matches_source_page_title",
                    "matrix_raw_path_matches_source_page_raw_path",
                    "matrix_source_url_matches_raw_source_url",
                    "raw_source_url_matches_source_page_url",
                },
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_route_identity_audit_fails_title_mismatch_before_closeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            raw_path = vault / "raw" / "source.md"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(
                """---
title: "Raw Title"
source: "https://example.test/source"
---

# Raw Title
""",
                encoding="utf-8",
            )
            matrix_path = vault / "runs" / "matrix.json"
            write_matrix(
                matrix_path,
                [
                    matrix_entry(
                        title="Different Route Title",
                        source_url="https://example.test/source",
                    )
                ],
            )

            report = build_report(vault, matrix_path=matrix_path)

            proposal = report["proposals"][0]
            identity = proposal["identity_audit"]
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["summary"]["blocking_issue_count"], 1)
            self.assertEqual(report["summary"]["identity_fail_count"], 1)
            self.assertIn("identity_mismatch", proposal["issues"])
            self.assertEqual(identity["status"], "fail")
            self.assertIn(
                {
                    "name": "matrix_title_matches_raw_title",
                    "status": "fail",
                    "expected": "Different Route Title",
                    "observed": "Raw Title",
                },
                identity["checks"],
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_route_audit_flags_broad_term_matches_before_source_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            matrix_path = vault / "runs" / "matrix.json"
            write_matrix(
                matrix_path,
                [
                    matrix_entry(
                        title="Won power price access route candidate",
                        current_domain="market-access-review",
                        rationale="Power and price signals may be route hints but need review.",
                    )
                ],
            )
            matrix_payload = json.loads(matrix_path.read_text(encoding="utf-8"))
            self.assertEqual(
                validate_with_schema(matrix_payload, load_schema(MATRIX_SCHEMA_PATH)),
                [],
            )

            report = build_report(vault, matrix_path=matrix_path)

            audit = report["proposals"][0]["route_audit"]
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["audit_review_required_count"], 1)
            self.assertEqual(
                audit["candidate_route"]["proposed_action"],
                "refresh_existing_synthesis",
            )
            self.assertEqual(audit["matched_rule"], "broad_term_review")
            self.assertEqual(audit["matched_terms"], ["access", "power", "price", "won"])
            self.assertEqual(audit["audit_status"], "review_required")
            self.assertIn("manual_override_reason_missing", audit["review_reasons"])
            self.assertEqual(
                {item["term"] for item in audit["match_evidence"]},
                {"access", "power", "price", "won"},
            )
            self.assertEqual(
                {item["match_kind"] for item in audit["match_evidence"]},
                {"token_boundary"},
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_route_audit_uses_token_boundaries_for_broad_terms(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            matrix_path = vault / "runs" / "matrix.json"
            write_matrix(
                matrix_path,
                [
                    matrix_entry(
                        title="Empowered accessory wonder material",
                        current_domain="pricing-accessory-wonderful",
                    )
                ],
            )

            report = build_report(vault, matrix_path=matrix_path)

            audit = report["proposals"][0]["route_audit"]
            self.assertEqual(report["summary"]["audit_clear_count"], 1)
            self.assertEqual(report["summary"]["audit_review_required_count"], 0)
            self.assertEqual(audit["audit_status"], "clear")
            self.assertEqual(audit["matched_terms"], [])
            self.assertEqual(audit["match_evidence"], [])
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_route_audit_ignores_route_vocabulary_in_target_and_rationale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            matrix_path = vault / "runs" / "matrix.json"
            write_matrix(
                matrix_path,
                [
                    matrix_entry(
                        title="Neutral source title",
                        current_domain="neutral-source-domain",
                        target=(
                            "synthesis--ai-infrastructure-rerating-power-bottlenecks-"
                            "and-transition-risk-2026-04-14"
                        ),
                        rationale=(
                            "Material, power, cooling, access, and price route vocabulary "
                            "belongs to the maintained route rationale."
                        ),
                    )
                ],
            )

            report = build_report(vault, matrix_path=matrix_path)

            audit = report["proposals"][0]["route_audit"]
            self.assertEqual(report["summary"]["audit_clear_count"], 1)
            self.assertEqual(report["summary"]["audit_review_required_count"], 0)
            self.assertEqual(audit["audit_status"], "clear")
            self.assertEqual(audit["match_evidence"], [])
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_route_audit_records_explicit_rule_and_manual_override_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            matrix_path = vault / "runs" / "matrix.json"
            write_matrix(
                matrix_path,
                [
                    matrix_entry(
                        matched_rule="operator_reviewed_family_route",
                        matched_terms=["power"],
                        manual_override_reason=(
                            "Operator reviewed the candidate before page generation and kept "
                            "the route because the source is about energy-market power pricing."
                        ),
                    )
                ],
            )

            report = build_report(vault, matrix_path=matrix_path)

            audit = report["proposals"][0]["route_audit"]
            self.assertEqual(report["summary"]["audit_manual_override_count"], 1)
            self.assertEqual(audit["matched_rule"], "operator_reviewed_family_route")
            self.assertEqual(audit["matched_terms"], ["power"])
            self.assertEqual(audit["audit_status"], "manual_override_recorded")
            self.assertTrue(
                audit["manual_override_reason"].startswith("Operator reviewed")
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_route_audit_schema_requires_manual_override_reason_when_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            matrix_path = vault / "runs" / "matrix.json"
            write_matrix(
                matrix_path,
                [
                    matrix_entry(
                        matched_rule="operator_reviewed_family_route",
                        matched_terms=["power"],
                        manual_override_reason="operator reviewed",
                    )
                ],
            )
            report = build_report(vault, matrix_path=matrix_path)
            report["proposals"][0]["route_audit"]["manual_override_reason"] = ""

            errors = validate_with_schema(report, load_schema(SCHEMA_PATH))

            self.assertTrue(errors)
            self.assertTrue(
                any("manual_override_reason" in error for error in errors),
                errors,
            )

    def test_route_audit_schema_requires_match_evidence_when_review_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            matrix_path = vault / "runs" / "matrix.json"
            write_matrix(
                matrix_path,
                [matrix_entry(title="Power route candidate")],
            )
            report = build_report(vault, matrix_path=matrix_path)
            route_audit = report["proposals"][0]["route_audit"]
            route_audit["match_evidence"] = []
            route_audit["review_reasons"] = ["broad_route_term_match"]

            errors = validate_with_schema(report, load_schema(SCHEMA_PATH))

            self.assertTrue(errors)
            self.assertTrue(
                any("match_evidence" in error for error in errors),
                errors,
            )

    def test_absorption_closeout_fails_unreviewed_actions_before_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            matrix_path = vault / "runs" / "matrix.json"
            write_matrix(
                matrix_path,
                [
                    matrix_entry(
                        review_status="pending",
                        target="",
                    )
                ],
            )

            report = build_report(
                vault,
                matrix_path=matrix_path,
                mode="absorption_closeout",
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["summary"]["blocking_issue_count"], 1)
            self.assertIn("unreviewed_route_assignment", report["proposals"][0]["issues"])
            self.assertIn("missing_target", report["proposals"][0]["issues"])
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
