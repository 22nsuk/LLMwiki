from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ops.scripts.eval.structural_complexity_budget import main
from tests.test_mechanism_assess import seed_policy


class StructuralComplexityBudgetCliTests(unittest.TestCase):
    def test_touched_check_allows_existing_ratchet_ceiling_warn_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)
            report = {
                "status": "attention",
                "targets": [
                    {
                        "path": "ops/scripts/release/release_evidence_dashboard.py",
                        "over_budget_metrics": ["nonempty_line_count_total"],
                        "function_budget_candidate_count": 0,
                    }
                ],
            }

            with (
                mock.patch("ops.scripts.eval.structural_complexity_budget.build_report", return_value=report),
                mock.patch("ops.scripts.eval.structural_complexity_budget.write_report"),
                self.assertRaises(SystemExit) as exc,
            ):
                main(
                    [
                        "--vault",
                        str(vault),
                        "--out",
                        "ops/reports/structural-complexity-budget-touched.json",
                        "--fail-on-attention",
                        "--target",
                        "ops/scripts/release/release_evidence_dashboard.py",
                    ]
                )

            self.assertEqual(exc.exception.code, 0)

    def test_touched_check_still_fails_on_missing_target_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)
            report = {
                "status": "fail",
                "targets": [
                    {
                        "path": "ops/scripts/release/release_evidence_dashboard.py",
                        "over_budget_metrics": [],
                        "function_budget_candidate_count": 0,
                    }
                ],
            }

            with (
                mock.patch("ops.scripts.eval.structural_complexity_budget.build_report", return_value=report),
                mock.patch("ops.scripts.eval.structural_complexity_budget.write_report"),
                self.assertRaises(SystemExit) as exc,
            ):
                main(
                    [
                        "--vault",
                        str(vault),
                        "--out",
                        "ops/reports/structural-complexity-budget-touched.json",
                        "--fail-on-attention",
                        "--target",
                        "ops/scripts/release/release_evidence_dashboard.py",
                    ]
                )

            self.assertEqual(exc.exception.code, 1)

    def test_touched_check_fails_on_new_no_headroom_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)
            stderr = io.StringIO()
            report = {
                "status": "attention",
                "targets": [
                    {
                        "path": "ops/scripts/new_runtime.py",
                        "over_budget_metrics": [],
                        "no_headroom_metrics": ["nonempty_line_count_total"],
                        "low_headroom_metrics": [],
                        "function_budget_candidate_count": 0,
                    }
                ],
            }

            with (
                mock.patch("ops.scripts.eval.structural_complexity_budget.build_report", return_value=report),
                mock.patch("ops.scripts.eval.structural_complexity_budget.write_report"),
                contextlib.redirect_stderr(stderr),
                self.assertRaises(SystemExit) as exc,
            ):
                main(
                    [
                        "--vault",
                        str(vault),
                        "--out",
                        "ops/reports/structural-complexity-budget-touched.json",
                        "--fail-on-attention",
                        "--target",
                        "ops/scripts/new_runtime.py",
                    ]
                )

            self.assertEqual(exc.exception.code, 1)
            self.assertIn("complexity ratchet regression", stderr.getvalue())
            self.assertIn("new_warn_targets=ops/scripts/new_runtime.py", stderr.getvalue())

    def test_touched_check_fails_on_ratchet_regression_before_attention_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)
            stderr = io.StringIO()
            report = {
                "status": "pass",
                "targets": [
                    {
                        "path": "ops/scripts/new_runtime.py",
                        "over_budget_metrics": ["nonempty_line_count_total"],
                        "function_budget_candidate_count": 0,
                    }
                ],
            }

            with (
                mock.patch("ops.scripts.eval.structural_complexity_budget.build_report", return_value=report),
                mock.patch("ops.scripts.eval.structural_complexity_budget.write_report"),
                contextlib.redirect_stderr(stderr),
                self.assertRaises(SystemExit) as exc,
            ):
                main(
                    [
                        "--vault",
                        str(vault),
                        "--out",
                        "ops/reports/structural-complexity-budget-touched.json",
                        "--fail-on-attention",
                        "--target",
                        "ops/scripts/new_runtime.py",
                    ]
                )

            self.assertEqual(exc.exception.code, 1)
            self.assertIn("complexity ratchet regression", stderr.getvalue())
            self.assertIn("new_warn_targets=ops/scripts/new_runtime.py", stderr.getvalue())

    def test_touched_check_fails_on_resurfaced_ratchet_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)
            policy_path = vault / "ops" / "policies" / "wiki-maintainer-policy.yaml"
            policy_text = policy_path.read_text(encoding="utf-8")
            policy_text = policy_text.replace(
                "      - ops/scripts/release/release_closeout_summary.py\n",
                "",
                1,
            )
            policy_text = policy_text.replace(
                "    resolved_targets: []",
                "    resolved_targets:\n      - ops/scripts/release/release_closeout_summary.py",
            )
            policy_path.write_text(policy_text, encoding="utf-8")
            stderr = io.StringIO()
            report = {
                "status": "pass",
                "targets": [
                    {
                        "path": "ops/scripts/release/release_closeout_summary.py",
                        "over_budget_metrics": ["python_branch_node_count"],
                        "function_budget_candidate_count": 0,
                    }
                ],
            }

            with (
                mock.patch("ops.scripts.eval.structural_complexity_budget.build_report", return_value=report),
                mock.patch("ops.scripts.eval.structural_complexity_budget.write_report"),
                contextlib.redirect_stderr(stderr),
                self.assertRaises(SystemExit) as exc,
            ):
                main(
                    [
                        "--vault",
                        str(vault),
                        "--out",
                        "ops/reports/structural-complexity-budget-touched.json",
                        "--fail-on-attention",
                        "--target",
                        "ops/scripts/release/release_closeout_summary.py",
                    ]
                )

            self.assertEqual(exc.exception.code, 1)
            self.assertIn(
                "resurfaced_targets=ops/scripts/release/release_closeout_summary.py",
                stderr.getvalue(),
            )
