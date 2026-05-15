from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.wiki_lint import lint
from tests.minimal_vault_runtime import seed_eval_coverage_smoke_vault, set_policy_value

pytestmark = pytest.mark.slow


class WikiEvalCoverageRuntimeTest(unittest.TestCase):
    def test_wiki_lint_wires_eval_coverage_review_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_eval_coverage_smoke_vault(vault)
            set_policy_value(vault, ("stage2_eval", "source_count_consistency_enabled"), False)

            report = lint(vault)

            candidate = next(
                item
                for item in report["review_candidates"]
                if item["type"] == "eval_coverage_gap_candidate"
            )
            self.assertEqual(candidate["cohort_id"], "stage2_synthesis_source_count_coverage")
            self.assertEqual(candidate["suggested_action"], "review_stage2_synthesis_source_count_eval_surface")


if __name__ == "__main__":
    unittest.main()
