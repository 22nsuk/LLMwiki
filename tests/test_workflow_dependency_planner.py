from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.workflow_dependency_planner import build_report, write_report
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "workflow-dependency-planner.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 5, 9, 0, tzinfo=dt.timezone.utc),
    )


class WorkflowDependencyPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
        (self.vault / ".github" / "workflows" / "ci.yml").write_text("name: CI\n", encoding="utf-8")
        (self.vault / "Makefile").write_text(
            ".PHONY: static ruff typecheck release-evidence-closeout release-smoke-full "
            "test-execution-summary generated-artifact-converge script-output-surfaces "
            "external-report-action-matrix generated-artifact-index artifact-freshness "
            "operator-release-summary report-contract-closeout\n"
            "static: ruff typecheck\n"
            "\t@echo static\n"
            "ruff:\n"
            "\t@echo ruff\n"
            "typecheck:\n"
            "\t@echo typecheck\n"
            "release-evidence-closeout:\n"
            "\t$(MAKE) static\n"
            "\t$(MAKE) release-smoke-full\n"
            "\t$(MAKE) test-execution-summary\n"
            "release-smoke-full:\n"
            "\t@echo smoke\n"
            "test-execution-summary:\n"
            "\t@echo tests\n"
            "generated-artifact-converge:\n"
            "\t$(MAKE) script-output-surfaces\n"
            "\t$(MAKE) external-report-action-matrix\n"
            "\t$(MAKE) generated-artifact-index\n"
            "\t$(MAKE) artifact-freshness\n"
            "script-output-surfaces:\n"
            "\t@echo surfaces\n"
            "external-report-action-matrix:\n"
            "\t@echo matrix\n"
            "generated-artifact-index:\n"
            "\t@echo index\n"
            "artifact-freshness:\n"
            "\t@echo freshness\n"
            "operator-release-summary:\n"
            "\t@echo operator\n"
            "report-contract-closeout:\n"
            "\t$(MAKE) test-execution-summary\n"
            "\t$(MAKE) generated-artifact-converge\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_fixed_point_policy(self) -> None:
        path = self.vault / "ops" / "policies" / "release-closeout-fixed-point.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "writers": [
                        {
                            "name": "alpha",
                            "target": "alpha-writer",
                            "produces": ["ops/reports/alpha.json"],
                            "depends_on": [],
                            "expensive_prerequisites_once": ["seed-writer"],
                        },
                        {
                            "name": "beta",
                            "target": "beta-writer",
                            "produces": ["ops/reports/beta.json"],
                            "depends_on": ["alpha-writer"],
                            "expensive_prerequisites_once": [],
                        },
                    ],
                    "tracked_artifacts": [
                        "ops/reports/alpha.json",
                        "ops/reports/beta.json",
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def test_build_report_maps_make_edges_and_validates_schema(self) -> None:
        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(validate_with_schema(report, load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH)), [])
        self.assertIn(
            {"from": "release-evidence-closeout", "to": "static", "source": "make_recipe"},
            report["dependency_edges"],
        )
        self.assertIn(
            {"from": "release-evidence-closeout", "to": "release-smoke-full", "source": "make_recipe"},
            report["dependency_edges"],
        )
        self.assertEqual(report["summary"]["missing_dependency_count"], 0)
        self.assertEqual(report["evidence_dag"]["status"], "attention")
        self.assertIn("Makefile", report["input_fingerprints"])
        self.assertIn(".github/workflows/ci.yml", report["input_fingerprints"])

    def test_included_mk_files_are_part_of_workflow_graph(self) -> None:
        (self.vault / "mk").mkdir(exist_ok=True)
        (self.vault / "Makefile").write_text(
            "include mk/release.mk\n",
            encoding="utf-8",
        )
        (self.vault / "mk" / "release.mk").write_text(
            ".PHONY: release-evidence-closeout static\n"
            "release-evidence-closeout: static\n"
            "\t$(MAKE) generated-artifact-index\n"
            "static:\n"
            "\t@echo static\n"
            "generated-artifact-index:\n"
            "\t@echo index\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertIn("mk/release.mk", report["input_fingerprints"])
        self.assertIn(
            {"from": "release-evidence-closeout", "to": "static", "source": "make_prerequisite"},
            report["dependency_edges"],
        )
        self.assertIn(
            {"from": "release-evidence-closeout", "to": "generated-artifact-index", "source": "make_recipe"},
            report["dependency_edges"],
        )

    def test_changed_path_selects_report_contract_closeout(self) -> None:
        report = build_report(
            self.vault,
            changed_paths=["tests/test_generated_report_contracts.py"],
            context=fixed_context(),
        )

        workflow = next(item for item in report["selected_workflows"] if item["workflow_id"] == "report_contract_closeout")
        self.assertEqual(workflow["recommended_lane"], "report-contract-closeout")
        self.assertEqual(workflow["matched_paths"], ["tests/test_generated_report_contracts.py"])
        self.assertEqual([step["target"] for step in workflow["steps"]], ["report-contract-closeout", "operator-release-summary"])
        self.assertEqual(report["status"], "pass")

    def test_planner_inputs_select_planner_closeout(self) -> None:
        for path in [
            "ops/scripts/core/workflow_dependency_planner.py",
            "ops/schemas/workflow-dependency-planner.schema.json",
            "ops/README.md",
            "pyproject.toml",
            ".github/workflows/ci.yml",
        ]:
            with self.subTest(path=path):
                report = build_report(
                    self.vault,
                    changed_paths=[path],
                    context=fixed_context(),
                )

                workflow = next(
                    item
                    for item in report["selected_workflows"]
                    if item["workflow_id"] == "workflow_dependency_planner_closeout"
                )
                self.assertEqual(report["status"], "pass")
                self.assertEqual(workflow["recommended_lane"], "workflow-dependency-planner")
                self.assertEqual(workflow["matched_paths"], [path])
                self.assertEqual(workflow["steps"][0]["target"], "workflow-dependency-planner")
                self.assertIn(
                    "test-artifact-finalization",
                    [step["target"] for step in workflow["steps"]],
                )
                self.assertEqual(report["diagnostics"]["unknown_change_paths"], [])

    def test_canonical_release_script_path_selects_release_evidence_closeout(self) -> None:
        report = build_report(
            self.vault,
            changed_paths=["ops/scripts/release/operator_release_summary.py"],
            context=fixed_context(),
        )

        workflow = next(
            item
            for item in report["selected_workflows"]
            if item["workflow_id"] == "release_evidence_closeout"
        )
        self.assertEqual(workflow["recommended_lane"], "release-evidence-closeout")
        self.assertEqual(workflow["matched_paths"], ["ops/scripts/release/operator_release_summary.py"])
        self.assertEqual([step["target"] for step in workflow["steps"]], ["release-evidence-closeout", "operator-release-summary"])
        self.assertEqual(report["diagnostics"]["unknown_change_paths"], [])

    def test_planner_closeout_steps_are_derived_from_fixed_point_policy(self) -> None:
        self._write_fixed_point_policy()

        report = build_report(
            self.vault,
            changed_paths=["ops/scripts/core/workflow_dependency_planner.py"],
            context=fixed_context(),
        )

        workflow = next(
            item
            for item in report["selected_workflows"]
            if item["workflow_id"] == "workflow_dependency_planner_closeout"
        )
        self.assertEqual(
            [step["target"] for step in workflow["steps"][:4]],
            [
                "workflow-dependency-planner",
                "seed-writer",
                "alpha-writer",
                "beta-writer",
            ],
        )
        self.assertIn(
            "test-artifact-finalization",
                [step["target"] for step in workflow["steps"]],
        )

    def test_evidence_dag_maps_fixed_point_policy_report_flow(self) -> None:
        self._write_fixed_point_policy()

        report = build_report(self.vault, context=fixed_context())

        dag = report["evidence_dag"]
        self.assertEqual(dag["status"], "pass")
        self.assertEqual(dag["source"], "ops/policies/release-closeout-fixed-point.json")
        self.assertEqual(report["summary"]["evidence_node_count"], 2)
        self.assertEqual(report["summary"]["evidence_edge_count"], 1)
        self.assertEqual(
            dag["nodes"],
            [
                {
                    "order": 1,
                    "name": "alpha",
                    "target": "alpha-writer",
                    "primary_report": "ops/reports/alpha.json",
                    "produces": ["ops/reports/alpha.json"],
                    "output_role": "canonical_report",
                    "source": "fixed_point_policy_writer",
                },
                {
                    "order": 2,
                    "name": "beta",
                    "target": "beta-writer",
                    "primary_report": "ops/reports/beta.json",
                    "produces": ["ops/reports/beta.json"],
                    "output_role": "canonical_report",
                    "source": "fixed_point_policy_writer",
                },
            ],
        )
        self.assertEqual(
            dag["edges"],
            [
                {
                    "from": "alpha-writer",
                    "to": "beta-writer",
                    "source": "fixed_point_policy_depends_on",
                    "from_reports": ["ops/reports/alpha.json"],
                    "to_reports": ["ops/reports/beta.json"],
                }
            ],
        )
        self.assertEqual(validate_with_schema(report, load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH)), [])

    def test_planner_closeout_places_cohort_after_learning_revalidation(self) -> None:
        policy_path = self.vault / "ops" / "policies" / "release-closeout-fixed-point.json"
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(
            (REPO_ROOT / "ops" / "policies" / "release-closeout-fixed-point.json").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
        makefile = self.vault / "Makefile"
        makefile.write_text(
            makefile.read_text(encoding="utf-8")
            + "closure-registry-envelope:\n"
            + "\t@echo closure\n"
            + "manual-mutate-defect-registry:\n"
            + "\t@echo mutation registry\n"
            + "release-risk-taxonomy-matrix:\n"
            + "\t@echo risk taxonomy\n"
            + "generated-artifact-index-body:\n"
            + "\t@echo index body\n"
            + "release-closeout-summary-report:\n"
            + "\t@echo closeout\n"
            + "learning-readiness-signoff-revalidation:\n"
            + "\t@echo learning revalidation\n"
            + "release-evidence-cohort:\n"
            + "\t@echo cohort\n"
            + "release-evidence-dashboard-report:\n"
            + "\t@echo dashboard\n"
            + "release-lane-summary:\n"
            + "\t@echo lane\n"
            + "release-clean-blocker-ledger:\n"
            + "\t@echo ledger\n"
            + "release-closeout-batch-manifest-promote:\n"
            + "\t@echo batch\n"
            + "release-evidence-closeout-self-check:\n"
            + "\t@echo self check\n",
            encoding="utf-8",
        )
        report = build_report(
            self.vault,
            changed_paths=["ops/scripts/core/workflow_dependency_planner.py"],
            context=fixed_context(),
        )

        workflow = next(
            item
            for item in report["selected_workflows"]
            if item["workflow_id"] == "workflow_dependency_planner_closeout"
        )
        steps = [step["target"] for step in workflow["steps"]]

        self.assertLess(
            steps.index("learning-readiness-signoff-revalidation"),
            steps.index("release-evidence-cohort"),
        )
        self.assertLess(
            steps.index("release-evidence-cohort"),
            steps.index("release-evidence-dashboard-report"),
        )

    def test_planner_schema_change_keeps_report_contract_closeout(self) -> None:
        report = build_report(
            self.vault,
            changed_paths=["ops/schemas/workflow-dependency-planner.schema.json"],
            context=fixed_context(),
        )

        workflow_ids = {item["workflow_id"] for item in report["selected_workflows"]}
        self.assertIn("workflow_dependency_planner_closeout", workflow_ids)
        self.assertIn("report_contract_closeout", workflow_ids)

    def test_unknown_changed_path_is_attention_not_failure(self) -> None:
        report = build_report(
            self.vault,
            changed_paths=["notes/private-scratch.txt"],
            context=fixed_context(),
        )

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["diagnostics"]["unknown_change_paths"], ["notes/private-scratch.txt"])

    def test_missing_make_dependency_fails_with_diagnostic(self) -> None:
        (self.vault / "Makefile").write_text(
            ".PHONY: release-evidence-closeout\n"
            "release-evidence-closeout:\n"
            "\t$(MAKE) missing-target\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            report["diagnostics"]["missing_dependencies"],
            [
                {
                    "consumer": "release-evidence-closeout",
                    "dependency": "missing-target",
                    "source": "make_recipe",
                }
            ],
        )
        self.assertEqual(validate_with_schema(report, load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH)), [])

    def test_changed_files_manifest_is_consumed(self) -> None:
        manifest = self.vault / "tmp" / "changed-files.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps({"changed_files": [{"path": "external-reports/review.md"}]}),
            encoding="utf-8",
        )

        report = build_report(
            self.vault,
            changed_files_manifest="tmp/changed-files.json",
            context=fixed_context(),
        )

        self.assertEqual(report["selected_change_paths"], ["external-reports/review.md"])
        self.assertIn("changed_files_manifest", report["input_fingerprints"])
        self.assertEqual(report["selected_workflows"][0]["workflow_id"], "external_report_reference_closeout")

    def test_write_report_validates_schema(self) -> None:
        report = build_report(self.vault, context=fixed_context())

        destination = write_report(self.vault, report, "ops/reports/workflow-dependency-planner.json")

        self.assertEqual(destination, self.vault / "ops" / "reports" / "workflow-dependency-planner.json")
        self.assertTrue(destination.exists())


if __name__ == "__main__":
    unittest.main()
