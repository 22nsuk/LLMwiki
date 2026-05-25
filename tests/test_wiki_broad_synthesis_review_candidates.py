from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.wiki_lint import lint

from tests.test_wiki_lint_review_runtime import seed_broad_synthesis_vault

pytestmark = pytest.mark.slow


class BroadSynthesisReviewCandidatesTest(unittest.TestCase):
    def test_lint_wires_broad_synthesis_split_review_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_broad_synthesis_vault(vault, include_boundary_sections=False)

            candidate = next(
                item
                for item in lint(vault)["review_candidates"]
                if item["page"] == str((vault / "wiki" / "synthesis--broad.md").as_posix())
            )

            self.assertEqual(candidate["type"], "wiki_synthesis_multi_question_candidate")
            self.assertEqual(
                candidate["suggested_action"],
                "review_for_scope_split_or_subsynthesis_extraction",
            )


if __name__ == "__main__":
    unittest.main()
