from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from ops.scripts.policy_runtime import load_policy
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.wiki_eval_coverage_runtime import build_report
from tests.minimal_vault_runtime import seed_eval_coverage_smoke_vault, set_policy_value


REPO_ROOT = Path(__file__).resolve().parents[1]
WIKI_EVAL_COVERAGE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "wiki-eval-coverage-report.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.timezone.utc),
    )


class WikiEvalCoverageReportRuntimeTests(unittest.TestCase):
    def test_build_report_passes_on_minimal_vault_without_coverage_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_eval_coverage_smoke_vault(vault)

            policy, policy_path = load_policy(vault)
            report = build_report(vault, policy, policy_path, context=fixed_context())
            schema = load_schema(WIKI_EVAL_COVERAGE_SCHEMA_PATH)

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(report["summary"]["coverage_gap_count"], 0)
            cohort_ids = {cohort["cohort_id"] for cohort in report["cohorts"]}
            self.assertIn("stage1_source_substance_coverage", cohort_ids)
            self.assertIn("stage2_synthesis_source_count_coverage", cohort_ids)

    def test_build_report_surfaces_gap_when_stage2_rule_is_disabled_for_matching_cohort(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_eval_coverage_smoke_vault(vault)
            set_policy_value(vault, ("stage2_eval", "source_count_consistency_enabled"), False)

            policy, policy_path = load_policy(vault)
            report = build_report(vault, policy, policy_path)

            self.assertEqual(report["status"], "warn")
            candidate = next(
                item
                for item in report["review_candidates"]
                if item["cohort_id"] == "stage2_synthesis_source_count_coverage"
            )
            self.assertEqual(candidate["type"], "eval_coverage_gap_candidate")
            self.assertEqual(candidate["stage"], "stage2")
            self.assertEqual(candidate["gap_reasons"], ["no_active_rules", "no_pages_covered"])


if __name__ == "__main__":
    unittest.main()
