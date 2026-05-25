from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.raw_intake_source_quality import build_report, extract_clean_lead
from ops.scripts.raw_intake_source_quality import main as source_quality_main
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.cli_test_runtime import invoke_cli_main
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "raw-intake-source-quality-report.schema.json"


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


def write_source(path: Path, *, summary: str, key_points: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# source--quality",
                "",
                "## Summary",
                summary,
                "",
                "## Key points",
                *[f"- {item}" for item in key_points],
                "",
            ]
        ),
        encoding="utf-8",
    )


def matrix_entry(**overrides: str) -> dict[str, str]:
    entry = {
        "registry_id": "W-001",
        "title": "Quality route",
        "raw_path": "raw/source.md",
        "source_page": "wiki/source--quality.md",
        "current_topic_family": "family",
        "current_domain": "domain",
        "proposed_action": "keep_source_only_seed",
        "target": "source-only-review",
        "rationale": "Reviewed source-only posture.",
        "confidence": "low",
        "review_status": "reviewed",
    }
    entry.update(overrides)
    return entry


class RawIntakeSourceQualityTests(unittest.TestCase):
    def test_cli_writes_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)
            (vault / "raw").mkdir(exist_ok=True)
            (vault / "raw" / "source.md").write_text(
                "This raw source lead has enough cleaned article substance to pass "
                "the raw lead threshold without relying on navigation boilerplate.",
                encoding="utf-8",
            )
            write_source(
                vault / "wiki" / "source--quality.md",
                summary=(
                    "This source summary is intentionally long enough to satisfy "
                    "the deterministic source-quality threshold in the CLI writer test."
                ),
                key_points=[
                    "The first key point has enough substance for the combined key point character budget.",
                    "The second key point keeps the source-only quality gate comfortably above the floor.",
                ],
            )
            matrix_path = vault / "runs" / "matrix.json"
            write_matrix(matrix_path, [matrix_entry()])

            completed = invoke_cli_main(
                source_quality_main,
                [
                    "--vault",
                    str(vault),
                    "--matrix",
                    "runs/matrix.json",
                    "--out",
                    "reports/raw-intake/source-quality.json",
                ],
                cwd=launcher,
            )
            self.assertEqual(completed.exit_code, 0, msg=completed.stderr or completed.stdout)

            report_path = vault / "reports" / "raw-intake" / "source-quality.json"
            self.assertTrue(report_path.exists())
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["$schema"], "ops/schemas/raw-intake-source-quality-report.schema.json")
            self.assertEqual(payload["status"], "pass")

    def test_cleaned_lead_skips_navigation_and_link_only_lines(self) -> None:
        lead = extract_clean_lead(
            """---
title: test
---

# Page
본문 바로가기
[Home](/)
![hero](hero.png)

This is the first useful paragraph. It contains enough article substance to be
used as a cleaned lead without carrying navigation boilerplate.
"""
        )

        self.assertNotIn("본문 바로가기", lead)
        self.assertNotIn("[Home]", lead)
        self.assertTrue(lead.startswith("This is the first useful paragraph."))

    def test_reviewed_source_only_low_content_is_attention_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            (vault / "raw").mkdir(exist_ok=True)
            (vault / "raw" / "source.md").write_text("short", encoding="utf-8")
            write_source(
                vault / "wiki" / "source--quality.md",
                summary="thin",
                key_points=["one"],
            )
            matrix_path = vault / "runs" / "matrix.json"
            write_matrix(matrix_path, [matrix_entry()])

            report = build_report(vault, matrix_path=matrix_path)

            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["summary"]["review_count"], 1)
            self.assertEqual(report["findings"][0]["quality_status"], "review")
            self.assertIn("summary_below_min_chars", report["findings"][0]["issues"])
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_low_content_promoted_action_fails_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            (vault / "raw").mkdir(exist_ok=True)
            (vault / "raw" / "source.md").write_text("short", encoding="utf-8")
            write_source(
                vault / "wiki" / "source--quality.md",
                summary="thin",
                key_points=["one"],
            )
            matrix_path = vault / "runs" / "matrix.json"
            write_matrix(
                matrix_path,
                [
                    matrix_entry(
                        proposed_action="refresh_existing_synthesis",
                        confidence="medium",
                    )
                ],
            )

            report = build_report(vault, matrix_path=matrix_path)

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["summary"]["fail_count"], 1)
            self.assertEqual(report["findings"][0]["quality_status"], "fail")
            self.assertIn("cleaned_raw_lead_below_min_chars", report["findings"][0]["issues"])
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
