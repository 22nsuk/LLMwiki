from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.release_workflow_order_guard import build_report, write_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public

SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-workflow-order-guard.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 10, 4, 0, tzinfo=dt.UTC),
    )


class ReleaseWorkflowOrderGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy_support_file("ops/schemas/release-workflow-order-guard.schema.json")
        self._write_fixed_point_policy()
        self._write_makefile()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _write_fixed_point_policy(self, *, invert_dependency: bool = False) -> None:
        writers = [
            {
                "name": "generated-artifact-index",
                "target": "generated-artifact-index-body",
                "produces": ["ops/reports/generated-artifact-index.json"],
                "depends_on": ["artifact-freshness"] if invert_dependency else [],
                "expensive_prerequisites_once": ["release-risk-taxonomy-matrix"],
            },
            {
                "name": "artifact-freshness",
                "target": "artifact-freshness",
                "produces": ["ops/reports/artifact-freshness-report.json"],
                "depends_on": ["generated-artifact-index-body"],
                "expensive_prerequisites_once": [],
            },
        ]
        path = self.vault / "ops" / "policies" / "release-closeout-fixed-point.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": 1, "writers": writers, "tracked_artifacts": []}, indent=2),
            encoding="utf-8",
        )

    def _write_makefile(
        self,
        *,
        misorder_check_finalized: bool = False,
        misorder_release_source_ready: bool = False,
        misorder_release_source_ready_post_verify: bool = False,
    ) -> None:
        check_finalized_lines = (
            "\t$(MAKE) auto-improve-readiness-report-body\n"
            "\t$(MAKE) generated-artifact-converge\n"
            "\t$(MAKE) release-closeout-post-check-finalizer-dry-run\n"
            "\t$(MAKE) release-closeout-fixed-point\n"
            "\t$(MAKE) tmp-json-clean\n"
            "\t$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required\n"
            "\t$(MAKE) release-closeout-finality-verify\n"
        )
        if misorder_check_finalized:
            check_finalized_lines = (
                "\t$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required\n"
                "\t$(MAKE) release-closeout-fixed-point\n"
                "\t$(MAKE) tmp-json-clean\n"
                "\t$(MAKE) release-closeout-finality-verify\n"
            )
        release_source_ready_lines = (
            "\t$(MAKE) release-source-ready-prepare\n"
            "\t$(MAKE) release-source-ready-commit\n"
            "\t$(MAKE) release-source-ready-post-verify\n"
        )
        if misorder_release_source_ready:
            release_source_ready_lines = (
                "\t$(MAKE) release-source-ready-prepare\n"
                "\t$(MAKE) release-source-ready-post-verify\n"
                "\t$(MAKE) release-source-ready-commit\n"
            )
        release_source_ready_prepare_lines = (
            "\t$(MAKE) release-source-ready-snapshot\n"
            "\t$(MAKE) release-converge-all-surfaces\n"
        )
        release_source_ready_post_verify_lines = (
            "\t$(MAKE) release-check-all-surfaces\n"
            "\t$(MAKE) release-source-ready-status\n"
        )
        if misorder_release_source_ready_post_verify:
            release_source_ready_post_verify_lines = (
                "\t$(MAKE) release-check-all-surfaces\n"
                "\t$(MAKE) goal-runtime-local-evidence-refresh\n"
                "\t$(MAKE) generated-artifact-converge\n"
                "\t$(MAKE) remediation-backlog\n"
                "\t$(MAKE) release-closeout-fixed-point\n"
                "\t$(MAKE) release-source-ready-status\n"
            )
        release_converge_all_lines = (
            "\t$(MAKE) release-converge\n"
            "\t$(MAKE) sync-public-policy\n"
            "\t$(MAKE) public-check-all\n"
            "\t$(MAKE) release-converge-post\n"
        )
        phony = " ".join(
            [
                "check",
                "check-finalized",
                "release-evidence-converge",
                "release-evidence-closeout",
                "release-finality-resettle",
                "release-source-ready",
                "release-source-ready-snapshot",
                "release-source-ready-prepare",
                "release-source-ready-commit",
                "release-source-ready-post-verify",
                "release-source-ready-status",
                "release-converge-all-surfaces",
                "release-converge",
                "release-converge-post",
                "release-check-all-surfaces",
                "sync-public-policy",
                "public-check-all",
                "goal-runtime-local-evidence-refresh",
                "auto-improve-readiness-worktree-guard",
                "remediation-backlog",
                "generated-artifact-converge",
                "generated-artifact-index",
                "artifact-freshness",
                "release-closeout-summary",
                "release-evidence-dashboard",
                "release-lane-summary",
                "release-clean-blocker-ledger",
                "auto-improve-readiness-report-body",
                "script-output-surfaces",
                "external-report-action-matrix",
                "release-closeout-post-check-finalizer-dry-run",
                "release-closeout-fixed-point",
                "tmp-json-clean",
                "release-closeout-finality-verify",
            ]
        )
        self.vault.joinpath("Makefile").write_text(
            f".PHONY: {phony}\n"
            "check:\n"
            "\t@true\n"
            "check-finalized: check\n"
            f"{check_finalized_lines}"
            "release-evidence-converge:\n"
            "\t$(MAKE) auto-improve-readiness-report-body\n"
            "\t$(MAKE) generated-artifact-converge\n"
            "\t$(MAKE) release-closeout-summary\n"
            "\t$(MAKE) release-evidence-dashboard\n"
            "\t$(MAKE) release-lane-summary\n"
            "\t$(MAKE) release-clean-blocker-ledger\n"
            "\t$(MAKE) generated-artifact-converge\n"
            "\t$(MAKE) release-closeout-post-check-finalizer-dry-run\n"
            "\t$(MAKE) release-closeout-fixed-point\n"
            "\t$(MAKE) tmp-json-clean\n"
            "\t$(MAKE) release-closeout-finality-verify\n"
            "release-evidence-closeout: release-evidence-converge\n"
            "\t@echo compatibility alias\n"
            "release-finality-resettle:\n"
            "\t$(MAKE) workflow-dependency-planner\n"
            "\t$(MAKE) generated-artifact-converge\n"
            "\t$(MAKE) release-closeout-fixed-point\n"
            "\t$(MAKE) tmp-json-clean\n"
            "\t$(MAKE) release-closeout-finality-verify\n"
            "release-source-ready:\n"
            f"{release_source_ready_lines}"
            "release-source-ready-prepare:\n"
            f"{release_source_ready_prepare_lines}"
            "release-source-ready-post-verify:\n"
            f"{release_source_ready_post_verify_lines}"
            "release-converge-all-surfaces:\n"
            f"{release_converge_all_lines}"
            "release-converge:\n"
            "\t$(MAKE) release-converge-post\n"
            "release-converge-post:\n"
            "\t$(MAKE) generated-artifact-converge\n"
            "\t$(MAKE) remediation-backlog\n"
            "\t$(MAKE) release-closeout-fixed-point\n"
            "\t$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required\n"
            "release-source-ready-snapshot:\n"
            "\t@true\n"
            "release-source-ready-commit:\n"
            "\t@true\n"
            "release-source-ready-status:\n"
            "\t@true\n"
            "release-check-all-surfaces:\n"
            "\t@true\n"
            "sync-public-policy:\n"
            "\t@true\n"
            "public-check-all:\n"
            "\t@true\n"
            "goal-runtime-local-evidence-refresh:\n"
            "\t@true\n"
            "auto-improve-readiness-worktree-guard:\n"
            "\t@true\n"
            "remediation-backlog:\n"
            "\t@true\n"
            "generated-artifact-converge:\n"
            "\t$(MAKE) script-output-surfaces\n"
            "\t$(MAKE) external-report-action-matrix\n"
            "\t$(MAKE) generated-artifact-index\n"
            "\t$(MAKE) artifact-freshness\n"
            "script-output-surfaces:\n"
            "\t@true\n"
            "external-report-action-matrix:\n"
            "\t@true\n"
            "generated-artifact-index:\n"
            "\t@true\n"
            "artifact-freshness:\n"
            "\t@true\n",
            encoding="utf-8",
        )

    def test_guard_passes_for_current_closeout_sequence_and_validates_schema(self) -> None:
        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
        self.assertIn("release-evidence-converge", {item["target"] for item in report["target_recipes"]})
        self.assertIn("release-source-ready", {item["target"] for item in report["target_recipes"]})
        self.assertEqual(report["fixed_point_policy"]["writer_count"], 2)
        planner_hook = next(item for item in report["checks"] if item["id"] == "workflow_dependency_planner_closeout_hooks")
        self.assertEqual(planner_hook["status"], "pass")
        resettle_check = next(item for item in report["checks"] if item["id"] == "release_finality_resettle_sequence")
        self.assertEqual(resettle_check["status"], "pass")
        self.assertIn("release-finality-resettle", {item["target"] for item in report["target_recipes"]})
        self.assertTrue(write_report(self.vault, report).exists())

    def test_guard_fails_when_check_finalized_skips_initial_dry_run(self) -> None:
        self._write_makefile(misorder_check_finalized=True)

        report = build_report(self.vault, context=fixed_context())

        check = next(item for item in report["checks"] if item["id"] == "check_finalized_post_check_sequence")
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["violations"][0]["expected_role"], "release-closeout-post-check-finalizer-dry-run")

    def test_guard_fails_when_check_finalized_runs_steps_after_finality_verify(self) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "\t$(MAKE) release-closeout-finality-verify\n",
                "\t$(MAKE) release-closeout-finality-verify\n\t$(MAKE) external-report-action-matrix\n",
                1,
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(item for item in report["checks"] if item["id"] == "check_finalized_finality_terminal")
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["violations"][0]["reason"], "finality_verify_must_be_terminal")

    def test_guard_fails_when_fixed_point_policy_order_is_not_topological(self) -> None:
        self._write_fixed_point_policy(invert_dependency=True)

        report = build_report(self.vault, context=fixed_context())

        check = next(item for item in report["checks"] if item["id"] == "fixed_point_policy_topological_order")
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["violations"][0]["reason"], "dependency_not_before_target")

    def test_guard_fails_when_unplanned_closeout_target_repeats(self) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "\t$(MAKE) release-lane-summary\n",
                "\t$(MAKE) release-lane-summary\n"
                "\t$(MAKE) release-lane-summary\n",
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_evidence_converge_repetition_budget"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["violations"][0]["target"], "release-lane-summary")
        self.assertEqual(
            check["violations"][0]["reason"],
            "unexpected_repeated_closeout_target",
        )

    def test_guard_fails_when_release_source_ready_status_is_not_terminal(self) -> None:
        self._write_makefile(misorder_release_source_ready=True)

        report = build_report(self.vault, context=fixed_context())

        check = next(item for item in report["checks"] if item["id"] == "release_source_ready_transaction_sequence")
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(
            check["violations"][-1]["reason"],
            "release_source_ready_post_verify_must_be_terminal",
        )

    def test_guard_fails_when_release_source_ready_post_verify_runs_writers(
        self,
    ) -> None:
        self._write_makefile(misorder_release_source_ready_post_verify=True)

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_source_ready_post_verify_sequence"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertTrue(
            any(
                violation.get("reason") == "post_verify_must_be_write_free"
                for violation in check["violations"]
            )
        )


if __name__ == "__main__":
    unittest.main()
