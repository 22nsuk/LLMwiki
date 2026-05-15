from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.raw_intake_route_proposal import build_report, main as route_proposal_main
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.cli_test_runtime import invoke_cli_main
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault


SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "raw-intake-route-proposal-report.schema.json"


def write_matrix(path: Path, entries: list[dict]) -> None:
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


def matrix_entry(**overrides: str) -> dict[str, str]:
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
            self.assertEqual(
                first["proposals"][0]["route_key"],
                second["proposals"][0]["route_key"],
            )
            self.assertEqual(first["proposals"][0]["route_basis"]["current_domain"], "domain")
            self.assertEqual(validate_with_schema(first, load_schema(SCHEMA_PATH)), [])

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
