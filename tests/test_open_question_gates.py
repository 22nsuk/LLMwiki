from __future__ import annotations

from pathlib import Path

import pytest

from tests.minimal_vault_runtime import seed_open_question_smoke_vault, set_policy_value
from tests.vault_test_runtime import (
    SeededMinimalVaultTestCase,
    lint_and_evaluate_with_shared_snapshot,
)

pytestmark = pytest.mark.slow


def rewrite_open_questions(vault: Path, rel_path: str, replacement: str) -> None:
    page = vault / rel_path
    text = page.read_text(encoding="utf-8")
    original = "## Open questions\n- x\n## Source trace\n"
    if original not in text:
        raise AssertionError(f"open questions block not found in {rel_path}")
    page.write_text(text.replace(original, replacement), encoding="utf-8")


class OpenQuestionGateTest(SeededMinimalVaultTestCase):
    @classmethod
    def seed_vault(cls, vault: Path) -> None:
        seed_open_question_smoke_vault(vault)

    def page_report(self, eval_report: dict, rel_suffix: str) -> dict:
        return next(page for page in eval_report["pages"] if page["page"].endswith(rel_suffix))

    def _assert_open_question_smoke(
        self,
        *,
        open_questions: str,
        expected_lint_status: str,
        expected_issue_bucket: str,
        expected_issue_type: str,
        expected_eval_name: str,
        expected_eval_pass: bool,
        expected_eval_status: str,
        allow_warn_for_medium_question_overflow: bool | None = None,
    ) -> None:
        with self.fresh_vault() as vault:
            if allow_warn_for_medium_question_overflow is not None:
                set_policy_value(
                    vault,
                    ("readiness_gate", "allow_warn_for_medium_question_overflow"),
                    allow_warn_for_medium_question_overflow,
                )
            rewrite_open_questions(vault, "wiki/source--fake.md", open_questions)

            lint_report, eval_report = lint_and_evaluate_with_shared_snapshot(vault)

            self.assertEqual(lint_report["status"], expected_lint_status)
            self.assertTrue(
                any(
                    issue["type"] == expected_issue_type
                    for issue in lint_report[expected_issue_bucket]
                )
            )
            page = self.page_report(eval_report, "wiki/source--fake.md")
            budget_eval = next(
                result
                for result in page["results"]
                if result["eval"] == expected_eval_name
            )
            self.assertEqual(budget_eval["pass"], expected_eval_pass)
            self.assertEqual(eval_report["status"], expected_eval_status)

    def test_high_severity_overflow_fails_lint_and_eval(self) -> None:
        self._assert_open_question_smoke(
            open_questions="## Open questions\n- [high] blocker one\n## Source trace\n",
            expected_lint_status="fail",
            expected_issue_bucket="errors",
            expected_issue_type="high_severity_open_question_overflow",
            expected_eval_name="high_severity_open_questions_within_budget",
            expected_eval_pass=False,
            expected_eval_status="fail",
        )

    def test_medium_severity_overflow_warns_when_downgrade_is_enabled(self) -> None:
        self._assert_open_question_smoke(
            open_questions=(
                "## Open questions\n"
                "- [medium] question one\n"
                "- [medium] question two\n"
                "- [medium] question three\n"
                "- [medium] question four\n"
                "## Source trace\n"
            ),
            expected_lint_status="warn",
            expected_issue_bucket="warnings",
            expected_issue_type="medium_severity_open_question_overflow",
            expected_eval_name="medium_severity_open_questions_within_budget",
            expected_eval_pass=True,
            expected_eval_status="pass",
            allow_warn_for_medium_question_overflow=True,
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
