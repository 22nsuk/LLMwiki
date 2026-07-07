from __future__ import annotations

import ast
import datetime as dt
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.derived_surfaces import (
    currentness_output_paths as derived_surface_currentness_output_paths,
    currentness_path_patterns as derived_surface_currentness_path_patterns,
    load_manifest as load_derived_surfaces_manifest,
)
from ops.scripts.core.makefile_runtime import load_makefile_text, makefile_source_paths
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.core.workflow_dependency_planner import build_report, write_report
from ops.scripts.test.generate_release_governance_from_lane_registry import (
    validate_alignment,
)
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract, pytest.mark.report_contract_core]


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "workflow-dependency-planner.schema.json"
FOCUSED_PYTEST_TEMPLATE = (
    "PYTHONDONTWRITEBYTECODE=1 "
    ".venv/bin/python -m pytest -q -p no:cacheprovider {path}"
)
FOCUSED_WORKFLOW_PLANNER_TEST_COMMAND = FOCUSED_PYTEST_TEMPLATE.replace(
    "{path}",
    "tests/test_workflow_dependency_planner.py",
)
FOCUSED_RELEASE_WORKFLOW_TEST_COMMAND = FOCUSED_PYTEST_TEMPLATE.replace(
    "{path}",
    "tests/test_release_workflow_static.py",
)
FOCUSED_DERIVED_SURFACES_TEST_COMMAND = FOCUSED_PYTEST_TEMPLATE.replace(
    "{path}",
    "tests/test_derived_surfaces.py",
)
RUNTIME_HOTSPOT_SMOKE_COMMAND = "make runtime-hotspot-smoke"
FOCUSED_PYTEST_PREFIX = FOCUSED_PYTEST_TEMPLATE.partition("{path}")[0]


def _imports_makefile_static_helpers(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "tests.makefile_static_helpers"
        ):
            return True
        if isinstance(node, ast.Import) and any(
            alias.name == "tests.makefile_static_helpers" for alias in node.names
        ):
            return True
    return False


def _makefile_static_helper_importers() -> list[str]:
    return [
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted((REPO_ROOT / "tests").glob("test_*.py"))
        if _imports_makefile_static_helpers(path)
    ]


def _focused_pytest_paths(command: str) -> list[str]:
    if not command.startswith(FOCUSED_PYTEST_PREFIX):
        return []
    return command.removeprefix(FOCUSED_PYTEST_PREFIX).split()


def _make_target_pytest_paths(target: str) -> list[str]:
    recipe_lines = _make_target_recipe_lines(target)
    pytest_lines = [line for line in recipe_lines if " -m pytest " in line]
    if len(pytest_lines) != 1:
        raise AssertionError(f"{target} should have exactly one pytest recipe line")
    tokens = pytest_lines[0].split()
    return [token for token in tokens if token.startswith("tests/")]


def _make_target_recipe_lines(target: str) -> list[str]:
    text, _source_paths = load_makefile_text(REPO_ROOT)
    recipe_lines: list[str] = []
    in_target = False
    for line in text.splitlines():
        if not in_target:
            if ":" not in line:
                continue
            target_names = line.split(":", 1)[0].split()
            in_target = target in target_names
            continue
        if line.startswith("\t"):
            recipe_lines.append(line[1:])
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        break
    if not in_target:
        raise AssertionError(f"missing Make target: {target}")
    return recipe_lines


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 5, 9, 0, tzinfo=dt.UTC),
    )


class WorkflowDependencyPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        registry = self.vault / "ops" / "test-lane-registry.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(
            (REPO_ROOT / "ops" / "test-lane-registry.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        derived_surfaces_manifest = self.vault / "ops" / "policies" / "derived-surfaces.json"
        derived_surfaces_manifest.parent.mkdir(parents=True, exist_ok=True)
        derived_surfaces_manifest.write_text(
            (REPO_ROOT / "ops" / "policies" / "derived-surfaces.json").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
        (self.vault / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
        (self.vault / ".github" / "workflows" / "ci.yml").write_text("name: CI\n", encoding="utf-8")
        (self.vault / "Makefile").write_text(
            ".PHONY: static ruff typecheck release-evidence-converge release-smoke-full "
            "release-evidence-closeout "
            "test-execution-summary-report-contract generated-artifact-converge generated-artifact-script-output "
            "generated-artifact-finality-suffix script-output-surfaces "
            "external-report-action-matrix generated-artifact-index generated-artifact-index-body artifact-freshness "
            "release-closeout-summary-report release-closeout-fixed-point "
            "tmp-json-clean release-closeout-finality-verify "
            "operator-release-summary report-contract-closeout workflow-dependency-planner sync-derived\n"
            "static: ruff typecheck\n"
            "\t@echo static\n"
            "ruff:\n"
            "\t@echo ruff\n"
            "typecheck:\n"
            "\t@echo typecheck\n"
            "release-evidence-converge:\n"
            "\t$(MAKE) static\n"
            "\t$(MAKE) release-smoke-full\n"
            "\t$(MAKE) test-execution-summary-report-contract\n"
            "release-evidence-closeout: release-evidence-converge\n"
            "\t@echo compatibility alias\n"
            "release-smoke-full:\n"
            "\t@echo smoke\n"
            "test-execution-summary-report-contract:\n"
            "\t@echo tests\n"
            "generated-artifact-converge:\n"
            "\t$(MAKE) generated-artifact-finality-suffix\n"
            "generated-artifact-script-output:\n"
            "\t$(MAKE) script-output-surfaces\n"
            "generated-artifact-finality-suffix:\n"
            "\t$(MAKE) artifact-freshness\n"
            "\t$(MAKE) external-report-action-matrix\n"
            "\t$(MAKE) generated-artifact-index\n"
            "\t$(MAKE) artifact-freshness\n"
            "\t$(MAKE) external-report-action-matrix\n"
            "\t$(MAKE) generated-artifact-index-body\n"
            "\t$(MAKE) artifact-freshness\n"
            "script-output-surfaces:\n"
            "\t@echo surfaces\n"
            "external-report-action-matrix:\n"
            "\t@echo matrix\n"
            "generated-artifact-index:\n"
            "\t@echo index\n"
            "generated-artifact-index-body:\n"
            "\t@echo index body\n"
            "artifact-freshness:\n"
            "\t@echo freshness\n"
            "operator-release-summary:\n"
            "\t@echo operator\n"
            "release-closeout-summary-report:\n"
            "\t@echo closeout summary\n"
            "release-closeout-fixed-point:\n"
            "\t@echo fixed point\n"
            "tmp-json-clean:\n"
            "\t@echo tmp clean\n"
            "release-closeout-finality-verify:\n"
            "\t@echo finality\n"
            "workflow-dependency-planner:\n"
            "\t@echo planner\n"
            "sync-derived:\n"
            "\t@echo sync derived\n"
            "report-contract-closeout:\n"
            "\t$(MAKE) test-execution-summary-report-contract\n"
            "\t$(MAKE) generated-artifact-converge\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def derived_surface_currentness_paths(self) -> list[str]:
        return derived_surface_currentness_path_patterns(
            load_derived_surfaces_manifest(self.vault)
        )

    def derived_surface_output_only_currentness_paths(self) -> list[str]:
        return [
            path
            for path in derived_surface_currentness_output_paths(
                load_derived_surfaces_manifest(self.vault)
            )
            if not path.startswith(("mk/", ".github/"))
        ]

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
            {"from": "release-evidence-converge", "to": "static", "source": "make_recipe"},
            report["dependency_edges"],
        )
        self.assertIn(
            {"from": "release-evidence-converge", "to": "release-smoke-full", "source": "make_recipe"},
            report["dependency_edges"],
        )
        self.assertEqual(report["summary"]["missing_dependency_count"], 0)
        self.assertEqual(report["evidence_dag"]["status"], "attention")
        self.assertIn("Makefile", report["input_fingerprints"])
        self.assertIn(".github/workflows/ci.yml", report["input_fingerprints"])
        self.assertIn("test_lane_registry", report["input_fingerprints"])
        self.assertEqual(report["changed_path_minimum_plan"]["budget_status"], "not_applicable")

    def test_included_mk_files_are_part_of_workflow_graph(self) -> None:
        (self.vault / "mk").mkdir(exist_ok=True)
        (self.vault / "Makefile").write_text(
            "include mk/release.mk\n",
            encoding="utf-8",
        )
        (self.vault / "mk" / "release.mk").write_text(
            ".PHONY: release-evidence-converge static\n"
            "release-evidence-converge: static\n"
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
            {"from": "release-evidence-converge", "to": "static", "source": "make_prerequisite"},
            report["dependency_edges"],
        )
        self.assertIn(
            {"from": "release-evidence-converge", "to": "generated-artifact-index", "source": "make_recipe"},
            report["dependency_edges"],
        )

    def test_makefile_source_paths_preserve_make_include_semantics(self) -> None:
        makefile = self.vault / "Makefile"
        makefile.write_text("include mk/missing.mk\n", encoding="utf-8")

        with self.assertRaisesRegex(
            FileNotFoundError,
            "missing required Make include: mk/missing.mk",
        ):
            makefile_source_paths(self.vault)

        makefile.write_text("-include mk/missing.mk\n", encoding="utf-8")
        self.assertEqual(makefile_source_paths(self.vault), ["Makefile"])

        makefile.write_text(
            "include-demo:\n"
            "\tinclude mk/not-a-make-include.mk\n",
            encoding="utf-8",
        )
        self.assertEqual(makefile_source_paths(self.vault), ["Makefile"])

    def test_optional_mk_includes_can_define_internal_targets(self) -> None:
        (self.vault / "mk").mkdir(exist_ok=True)
        (self.vault / "Makefile").write_text(
            "DERIVED_SURFACES_MK_OUT ?= mk/derived.generated.mk\n"
            "-include $(DERIVED_SURFACES_MK_OUT)\n"
            "sync-derived:\n"
            "\t$(MAKE) _internal-sync-derived\n",
            encoding="utf-8",
        )
        (self.vault / "mk" / "derived.generated.mk").write_text(
            "_internal-sync-derived:\n"
            "\t@echo internal sync\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertIn("mk/derived.generated.mk", report["input_fingerprints"])
        self.assertNotIn(
            {
                "consumer": "sync-derived",
                "dependency": "_internal-sync-derived",
                "source": "make_recipe",
            },
            report["diagnostics"]["missing_dependencies"],
        )

    def test_changed_path_selects_report_contract_closeout(self) -> None:
        for changed_path in [
            "tests/test_report_schemas.py",
            "ops/policies/wiki-maintainer-policy.yaml",
        ]:
            with self.subTest(changed_path=changed_path):
                report = build_report(
                    self.vault,
                    changed_paths=[changed_path],
                    context=fixed_context(),
                )

                workflow = next(
                    item
                    for item in report["selected_workflows"]
                    if item["workflow_id"] == "report_contract_closeout"
                )
                self.assertEqual(workflow["recommended_lane"], "report-contract-closeout")
                self.assertEqual(workflow["matched_paths"], [changed_path])
                self.assertEqual(
                    [step["target"] for step in workflow["steps"]],
                    ["report-contract-closeout", "operator-release-summary"],
                )
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
                    "release-closeout-finality-verify",
                    [step["target"] for step in workflow["steps"]],
                )
                self.assertEqual(report["diagnostics"]["unknown_change_paths"], [])

    def test_generic_runtime_script_path_selects_validation_and_minimums(
        self,
    ) -> None:
        changed_path = "ops/scripts/core/artifact_io_runtime.py"

        report = build_report(
            self.vault,
            changed_paths=[changed_path],
            context=fixed_context(),
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["diagnostics"]["unknown_change_paths"], [])
        workflow = next(
            item
            for item in report["selected_workflows"]
            if item["workflow_id"] == "runtime_python_source_validation"
        )
        self.assertEqual(workflow["recommended_lane"], "runtime-source")
        self.assertEqual(workflow["matched_paths"], [changed_path])
        self.assertEqual(workflow["matched_rules"], ["runtime_python_source_change"])
        self.assertEqual(
            [step["target"] for step in workflow["steps"]],
            ["static", "test"],
        )
        plan = report["changed_path_minimum_plan"]
        self.assertEqual(plan["status"], "pass")
        self.assertEqual(plan["coverage_class"], "runtime_source")
        self.assertEqual(
            plan["selected_commands"],
            ["make static", "make test", "make sync-derived-check"],
        )
        self.assertEqual(
            [item["matched_rule_id"] for item in plan["path_recommendations"]],
            ["python_runtime_source+derived_surface_currentness"],
        )
        self.assertEqual(
            validate_with_schema(report, load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH)),
            [],
        )

    def test_planner_source_uses_focused_changed_path_minimum(self) -> None:
        report = build_report(
            self.vault,
            changed_paths=["ops/scripts/core/workflow_dependency_planner.py"],
            context=fixed_context(),
        )

        plan = report["changed_path_minimum_plan"]
        self.assertEqual(plan["status"], "pass")
        self.assertEqual(plan["coverage_class"], "workflow_dependency_planner")
        self.assertEqual(
            plan["selected_commands"],
            [
                "make static",
                "make workflow-dependency-planner-check",
                FOCUSED_WORKFLOW_PLANNER_TEST_COMMAND,
                "make sync-derived-check",
            ],
        )
        self.assertEqual(
            [item["matched_rule_id"] for item in plan["path_recommendations"]],
            ["workflow_dependency_planner_source+derived_surface_currentness"],
        )
        self.assertEqual(report["diagnostics"]["unknown_change_paths"], [])
        self.assertEqual(
            validate_with_schema(report, load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH)),
            [],
        )

    def test_canonical_release_script_path_selects_release_evidence_converge(self) -> None:
        report = build_report(
            self.vault,
            changed_paths=["ops/scripts/release/operator_release_summary.py"],
            context=fixed_context(),
        )

        workflow = next(
            item
            for item in report["selected_workflows"]
            if item["workflow_id"] == "release_evidence_converge"
        )
        self.assertEqual(workflow["recommended_lane"], "release-evidence-converge")
        self.assertEqual(workflow["matched_paths"], ["ops/scripts/release/operator_release_summary.py"])
        self.assertEqual([step["target"] for step in workflow["steps"]], ["release-evidence-converge", "operator-release-summary"])
        converge_step = workflow["steps"][0]
        self.assertEqual(converge_step["fanout_targets"], [])
        self.assertEqual(report["diagnostics"]["unknown_change_paths"], [])

    def test_canonical_report_change_selects_finality_resettle_lane(self) -> None:
        report = build_report(
            self.vault,
            changed_paths=["ops/reports/release-closeout-summary.json"],
            context=fixed_context(),
        )

        workflow = next(
            item
            for item in report["selected_workflows"]
            if item["workflow_id"] == "canonical_report_finalization"
        )
        self.assertEqual(workflow["recommended_lane"], "release-finality-resettle")
        self.assertEqual(workflow["matched_paths"], ["ops/reports/release-closeout-summary.json"])
        self.assertEqual(
            [step["target"] for step in workflow["steps"]],
            [
                "workflow-dependency-planner",
                "release-authority-sealed-preflight",
                "release-terminal-finality",
            ],
        )
        self.assertEqual(
            workflow["steps"][2]["fanout_targets"],
            [
                "generated-artifact-finality-suffix",
                "release-closeout-summary-report",
                "release-closeout-fixed-point",
                "release-closeout-post-check-finalizer-dry-run",
                "release-closeout-finality-verify",
            ],
        )
        self.assertEqual(
            workflow["steps"][2]["primary_report"],
            "ops/reports/release-closeout-finality-attestation.json",
        )
        self.assertEqual(report["diagnostics"]["unknown_change_paths"], [])

    def test_changed_artifact_class_selects_scoped_generated_artifact_lane(self) -> None:
        cases = [
            (
                "ops/script-output-surfaces.json",
                "script_output_surface_finalization",
                "generated-artifact-script-output",
                "script_output_surface_inventory_changed",
                ["script-output-surfaces"],
            ),
            (
                "ops/reports/generated-artifact-index.json",
                "canonical_report_finalization",
                "release-terminal-finality",
                "canonical_report_finality_suffix_changed",
                [
                    "generated-artifact-finality-suffix",
                    "release-closeout-summary-report",
                    "release-closeout-fixed-point",
                    "release-closeout-post-check-finalizer-dry-run",
                    "release-closeout-finality-verify",
                ],
            ),
            (
                "mk/artifact.mk",
                "generated_artifact_converge_closeout",
                "generated-artifact-script-output",
                "generated_artifact_converge_contract_changed",
                ["script-output-surfaces"],
            ),
        ]
        for changed_path, workflow_id, target, reason_code, fanout in cases:
            with self.subTest(changed_path=changed_path):
                report = build_report(
                    self.vault,
                    changed_paths=[changed_path],
                    context=fixed_context(),
                )

                workflow = next(
                    item
                    for item in report["selected_workflows"]
                    if item["workflow_id"] == workflow_id
                )
                step = next(item for item in workflow["steps"] if item["target"] == target)
                self.assertEqual(step["reason_code"], reason_code)
                self.assertEqual(step["fanout_targets"], fanout)
                self.assertEqual(report["diagnostics"]["unknown_change_paths"], [])

    def test_observation_change_selects_finality_resettle_lane(self) -> None:
        report = build_report(
            self.vault,
            changed_paths=[
                "ops/reports/task-improvement-observations/task-20260522-active-external-report-review/improvement-observations.json"
            ],
            context=fixed_context(),
        )

        workflow = next(
            item
            for item in report["selected_workflows"]
            if item["workflow_id"] == "observation_inventory_closeout"
        )
        self.assertEqual(workflow["recommended_lane"], "release-finality-resettle")
        self.assertEqual(
            [step["target"] for step in workflow["steps"][:2]],
            ["workflow-dependency-planner", "release-authority-sealed-preflight"],
        )
        self.assertEqual([step["target"] for step in workflow["steps"]][-1], "release-terminal-finality")

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
        self.assertEqual([step["target"] for step in workflow["steps"]][-1], "release-closeout-finality-verify")

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
        plan = report["changed_path_minimum_plan"]
        self.assertEqual(plan["status"], "attention")
        self.assertEqual(plan["coverage_class"], "conservative")
        self.assertEqual(plan["selected_commands"], ["make static", "make test"])
        self.assertTrue(plan["static_required"])
        self.assertEqual(plan["budget_status"], "within_budget")
        self.assertTrue(plan["final_checkpoint_required"])
        self.assertFalse(plan["release_proof_replacement"])

    def test_changed_path_minimum_pytest_commands_use_workspace_venv_entrypoint(
        self,
    ) -> None:
        registry_path = self.vault / "ops" / "test-lane-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        config = registry["changed_path_minimums"]

        commands = list(config["command_duration_seconds"])
        for rule in config["rules"]:
            commands.extend(rule["commands"])
        pytest_commands = sorted(
            {str(command) for command in commands if "pytest" in str(command)}
        )

        self.assertIn(FOCUSED_PYTEST_TEMPLATE, pytest_commands)
        self.assertIn(FOCUSED_WORKFLOW_PLANNER_TEST_COMMAND, pytest_commands)
        self.assertIn(FOCUSED_RELEASE_WORKFLOW_TEST_COMMAND, pytest_commands)
        self.assertIn(FOCUSED_DERIVED_SURFACES_TEST_COMMAND, pytest_commands)
        for command in pytest_commands:
            with self.subTest(command=command):
                self.assertNotIn("uv run python -m pytest", command)
                self.assertIn("PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest", command)
                self.assertIn("-p no:cacheprovider", command)

    def test_changed_path_minimum_plan_selects_focused_test_without_full_proof_claim(
        self,
    ) -> None:
        report = build_report(
            self.vault,
            changed_paths=["tests/test_workflow_dependency_planner.py"],
            context=fixed_context(),
        )

        plan = report["changed_path_minimum_plan"]
        self.assertEqual(plan["status"], "pass")
        self.assertEqual(plan["coverage_class"], "focused_test")
        self.assertEqual(
            plan["selected_commands"],
            [
                "make static",
                FOCUSED_WORKFLOW_PLANNER_TEST_COMMAND,
            ],
        )
        self.assertEqual(plan["budget_status"], "within_budget")
        self.assertEqual(
            plan["final_checkpoint_commands"],
            ["make release-run-ready"],
        )
        self.assertFalse(plan["release_proof_replacement"])
        self.assertEqual(validate_with_schema(report, load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH)), [])

    def test_changed_path_minimum_plan_routes_makefile_static_helper_to_split_gates(
        self,
    ) -> None:
        report = build_report(
            self.vault,
            changed_paths=["tests/makefile_static_helpers.py"],
            context=fixed_context(),
        )

        plan = report["changed_path_minimum_plan"]
        self.assertEqual(plan["status"], "pass")
        self.assertEqual(plan["coverage_class"], "makefile_static_gates")
        self.assertEqual(plan["unknown_paths"], [])
        self.assertEqual(
            plan["selected_commands"],
            ["make static", "make makefile-static-gates"],
        )
        self.assertCountEqual(
            _make_target_pytest_paths("makefile-static-gates"),
            _makefile_static_helper_importers(),
        )
        self.assertEqual(
            plan["command_duration_seconds"],
            {
                "make static": 60,
                "make makefile-static-gates": 210,
            },
        )
        self.assertEqual(plan["estimated_duration_seconds"], 270)
        self.assertEqual(plan["budget_status"], "within_budget")
        self.assertFalse(plan["release_proof_replacement"])
        self.assertEqual(
            {item["matched_rule_id"] for item in plan["path_recommendations"]},
            {"makefile_static_helpers"},
        )
        self.assertEqual(
            validate_with_schema(
                report,
                load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH),
            ),
            [],
        )

    def test_changed_path_minimum_plan_routes_runtime_hotspot_to_hotspot_smoke(
        self,
    ) -> None:
        report = build_report(
            self.vault,
            changed_paths=[
                "ops/scripts/mechanism/auto_improve_runtime.py",
                "ops/scripts/mechanism/auto_improve_maintenance_decision_runtime.py",
                "ops/scripts/mechanism/mutation_proposal_runtime.py",
                "ops/scripts/mechanism/auto_improve_readiness_payload_runtime.py",
                "ops/scripts/release/release_evidence_dashboard_closeout_runtime.py",
                "ops/scripts/release/release_evidence_dashboard_learning_delta_runtime.py",
            ],
            context=fixed_context(),
        )

        plan = report["changed_path_minimum_plan"]
        self.assertEqual(plan["status"], "pass")
        self.assertEqual(plan["coverage_class"], "runtime_hotspot")
        self.assertEqual(plan["unknown_paths"], [])
        self.assertEqual(
            plan["selected_commands"],
            [
                "make static",
                RUNTIME_HOTSPOT_SMOKE_COMMAND,
                "make sync-derived-check",
            ],
        )
        self.assertEqual(
            plan["command_duration_seconds"],
            {
                "make static": 60,
                RUNTIME_HOTSPOT_SMOKE_COMMAND: 240,
                "make sync-derived-check": 120,
            },
        )
        self.assertEqual(plan["estimated_duration_seconds"], 420)
        self.assertEqual(plan["budget_status"], "over_budget")
        self.assertFalse(plan["release_proof_replacement"])
        self.assertEqual(
            {item["matched_rule_id"] for item in plan["path_recommendations"]},
            {"runtime_hotspot_source+derived_surface_currentness"},
        )
        self.assertNotIn("make test-fast", plan["selected_commands"])
        self.assertEqual(validate_with_schema(report, load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH)), [])

    def test_changed_path_minimum_plan_routes_release_workflow_to_focused_static_test(
        self,
    ) -> None:
        report = build_report(
            self.vault,
            changed_paths=[".github/workflows/release.yml"],
            context=fixed_context(),
        )

        plan = report["changed_path_minimum_plan"]
        self.assertEqual(plan["status"], "pass")
        self.assertEqual(plan["coverage_class"], "release_workflow_static")
        self.assertEqual(plan["unknown_paths"], [])
        self.assertEqual(
            plan["selected_commands"],
            [
                "make static",
                "make workflow-dependency-planner-check",
                FOCUSED_RELEASE_WORKFLOW_TEST_COMMAND,
                "make sync-derived-check",
            ],
        )
        self.assertEqual(
            plan["command_duration_seconds"],
            {
                "make static": 60,
                "make workflow-dependency-planner-check": 60,
                FOCUSED_RELEASE_WORKFLOW_TEST_COMMAND: 30,
                "make sync-derived-check": 120,
            },
        )
        self.assertEqual(plan["estimated_duration_seconds"], 270)
        self.assertEqual(plan["budget_status"], "within_budget")
        self.assertFalse(plan["release_proof_replacement"])
        self.assertEqual(
            plan["path_recommendations"][0]["matched_rule_id"],
            "release_workflow_static_contract+derived_surface_currentness",
        )
        self.assertNotIn("make test-report-contract-core", plan["selected_commands"])
        self.assertEqual(validate_with_schema(report, load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH)), [])

    def test_changed_path_minimum_plan_keeps_ci_workflow_on_generic_orchestration_rule(
        self,
    ) -> None:
        report = build_report(
            self.vault,
            changed_paths=[".github/workflows/ci.yml"],
            context=fixed_context(),
        )

        plan = report["changed_path_minimum_plan"]
        self.assertEqual(plan["status"], "pass")
        self.assertEqual(plan["coverage_class"], "orchestration")
        self.assertEqual(
            plan["selected_commands"],
            [
                "make static",
                "make workflow-dependency-planner-check",
                "make sync-derived-check",
            ],
        )
        self.assertEqual(
            plan["path_recommendations"][0]["matched_rule_id"],
            "make_or_ci_contract+derived_surface_currentness",
        )
        self.assertNotIn(FOCUSED_RELEASE_WORKFLOW_TEST_COMMAND, plan["selected_commands"])
        self.assertEqual(validate_with_schema(report, load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH)), [])

    def test_changed_path_minimum_plan_uses_registry_owned_final_checkpoint(
        self,
    ) -> None:
        registry_path = self.vault / "ops" / "test-lane-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["changed_path_minimums"]["final_checkpoint_commands"] = [
            "make release-run-ready-plan-check",
            "make release-run-ready",
        ]
        registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")

        report = build_report(
            self.vault,
            changed_paths=["tests/test_workflow_dependency_planner.py"],
            context=fixed_context(),
        )

        plan = report["changed_path_minimum_plan"]
        self.assertEqual(
            plan["final_checkpoint_commands"],
            ["make release-run-ready-plan-check", "make release-run-ready"],
        )
        self.assertEqual(
            plan["selected_commands"],
            [
                "make static",
                FOCUSED_WORKFLOW_PLANNER_TEST_COMMAND,
            ],
        )
        self.assertFalse(plan["release_proof_replacement"])

    def test_changed_path_minimum_budget_status_is_deterministic(self) -> None:
        report = build_report(
            self.vault,
            changed_paths=[
                "ops/scripts/core/workflow_dependency_planner.py",
                "ops/schemas/workflow-dependency-planner.schema.json",
            ],
            context=fixed_context(),
        )

        plan = report["changed_path_minimum_plan"]
        self.assertEqual(plan["coverage_class"], "mixed")
        self.assertEqual(plan["estimated_duration_seconds"], 450)
        self.assertEqual(plan["duration_budget_seconds"], 300)
        self.assertEqual(plan["budget_status"], "over_budget")
        self.assertEqual(
            plan["command_duration_seconds"],
            {
                "make static": 60,
                "make workflow-dependency-planner-check": 60,
                FOCUSED_WORKFLOW_PLANNER_TEST_COMMAND: 30,
                "make test-report-contract-core": 180,
                "make sync-derived-check": 120,
            },
        )
        self.assertEqual(validate_with_schema(report, load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH)), [])

    def test_changed_path_minimum_budget_dedupes_repeated_selected_commands(self) -> None:
        report = build_report(
            self.vault,
            changed_paths=[
                "ops/scripts/core/workflow_dependency_planner.py",
                "ops/scripts/core/artifact_freshness_runtime.py",
            ],
            context=fixed_context(),
        )

        plan = report["changed_path_minimum_plan"]
        self.assertEqual(
            plan["selected_commands"],
            [
                "make static",
                "make test",
                "make sync-derived-check",
                "make workflow-dependency-planner-check",
                FOCUSED_WORKFLOW_PLANNER_TEST_COMMAND,
            ],
        )
        self.assertEqual(plan["estimated_duration_seconds"], 420)
        self.assertEqual(plan["budget_status"], "over_budget")
        self.assertEqual(
            plan["command_duration_seconds"],
            {
                "make static": 60,
                "make sync-derived-check": 120,
                "make workflow-dependency-planner-check": 60,
                FOCUSED_WORKFLOW_PLANNER_TEST_COMMAND: 30,
                "make test": 150,
            },
        )
        self.assertEqual(
            [item["duration_seconds"] for item in plan["path_recommendations"]],
            [300, 270],
        )
        self.assertEqual(validate_with_schema(report, load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH)), [])

    def test_changed_path_minimum_budget_falls_back_without_command_estimates(self) -> None:
        registry_path = self.vault / "ops" / "test-lane-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["changed_path_minimums"].pop("command_duration_seconds")
        registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")

        report = build_report(
            self.vault,
            changed_paths=[
                "ops/scripts/core/workflow_dependency_planner.py",
                "ops/scripts/core/artifact_freshness_runtime.py",
            ],
            context=fixed_context(),
        )

        plan = report["changed_path_minimum_plan"]
        self.assertEqual(
            plan["selected_commands"],
            [
                "make static",
                "make test",
                "make sync-derived-check",
                "make workflow-dependency-planner-check",
                FOCUSED_WORKFLOW_PLANNER_TEST_COMMAND,
            ],
        )
        self.assertEqual(plan["estimated_duration_seconds"], 570)
        self.assertEqual(validate_with_schema(report, load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH)), [])

    def test_changed_path_minimum_plan_matches_public_docs(self) -> None:
        for changed_path in ["docs/release.md", "ops/README.md"]:
            with self.subTest(changed_path=changed_path):
                report = build_report(
                    self.vault,
                    changed_paths=[changed_path],
                    context=fixed_context(),
                )

                plan = report["changed_path_minimum_plan"]
                self.assertEqual(report["status"], "pass")
                self.assertEqual(report["diagnostics"]["unknown_change_paths"], [])
                self.assertEqual(plan["status"], "pass")
                self.assertEqual(plan["coverage_class"], "public_boundary")
                self.assertEqual(plan["selected_commands"], ["make static", "make public-check"])

    def test_registry_covered_paths_are_not_workflow_unknown(self) -> None:
        report = build_report(
            self.vault,
            changed_paths=[
                "docs/development.md",
                "ops/test-lane-registry.json",
                "tests/release_run_ready_sample_runtime.py",
            ],
            context=fixed_context(),
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["diagnostics"]["unknown_change_paths"], [])
        self.assertEqual(report["changed_path_minimum_plan"]["status"], "pass")
        self.assertEqual(
            validate_with_schema(report, load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH)),
            [],
        )

    def test_changed_path_minimum_plan_matches_report_schema_sample_generator(self) -> None:
        changed_paths = [
            "tools/regenerate_report_schema_samples.py",
            "tests/release_run_ready_sample_runtime.py",
            "tests/supply_chain_sample_runtime.py",
        ]

        for changed_path in changed_paths:
            with self.subTest(changed_path=changed_path):
                report = build_report(
                    self.vault,
                    changed_paths=[changed_path],
                    context=fixed_context(),
                )

                plan = report["changed_path_minimum_plan"]
                self.assertEqual(plan["status"], "pass")
                self.assertEqual(
                    plan["coverage_class"],
                    "report_schema_sample_generation",
                )
                self.assertEqual(
                    plan["selected_commands"],
                    [
                        "make static",
                        "make report-schema-samples-check",
                        (
                            "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m "
                            "pytest -q -p no:cacheprovider "
                            "tests/test_report_schema_sample_regeneration.py"
                        ),
                        "make test-report-contract-core",
                        "make sync-derived-check",
                    ],
                )
                self.assertEqual(plan["unknown_paths"], [])

    def test_changed_path_minimum_plan_matches_derived_surfaces_manifest(self) -> None:
        changed_paths = [
            "ops/policies/derived-surfaces.json",
            "ops/schemas/derived-surfaces.schema.json",
        ]

        for changed_path in changed_paths:
            with self.subTest(changed_path=changed_path):
                report = build_report(
                    self.vault,
                    changed_paths=[changed_path],
                    context=fixed_context(),
                )

                plan = report["changed_path_minimum_plan"]
                self.assertEqual(plan["status"], "pass")
                self.assertEqual(plan["coverage_class"], "derived_surfaces_manifest")
                self.assertEqual(plan["unknown_paths"], [])
                self.assertEqual(
                    plan["selected_commands"],
                    [
                        "make static",
                        "make sync-derived-check",
                        FOCUSED_DERIVED_SURFACES_TEST_COMMAND,
                    ],
                )
                self.assertEqual(
                    plan["command_duration_seconds"],
                    {
                        "make static": 60,
                        "make sync-derived-check": 120,
                        FOCUSED_DERIVED_SURFACES_TEST_COMMAND: 30,
                    },
                )
                self.assertEqual(plan["estimated_duration_seconds"], 210)
                self.assertEqual(plan["budget_status"], "within_budget")
                self.assertEqual(
                    {item["matched_rule_id"] for item in plan["path_recommendations"]},
                    {"derived_surfaces_manifest_contract"},
                )
                self.assertEqual(
                    validate_with_schema(
                        report,
                        load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH),
                    ),
                    [],
                )

    def test_changed_path_minimum_plan_derives_currentness_from_derived_surfaces(
        self,
    ) -> None:
        report = build_report(
            self.vault,
            changed_paths=self.derived_surface_output_only_currentness_paths(),
            context=fixed_context(),
        )

        plan = report["changed_path_minimum_plan"]
        self.assertEqual(plan["status"], "pass")
        self.assertEqual(plan["coverage_class"], "generated_artifact_currentness")
        self.assertEqual(plan["unknown_paths"], [])
        self.assertEqual(plan["selected_commands"], ["make sync-derived-check"])
        self.assertEqual(
            {item["matched_rule_id"] for item in plan["path_recommendations"]},
            {"derived_surface_currentness"},
        )
        self.assertIn("derived_surfaces_manifest", report["input_fingerprints"])
        self.assertEqual(
            plan["command_duration_seconds"],
            {"make sync-derived-check": 120},
        )
        self.assertEqual(plan["estimated_duration_seconds"], 120)
        self.assertEqual(plan["budget_status"], "within_budget")
        self.assertEqual(
            validate_with_schema(
                report,
                load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH),
            ),
            [],
        )

    def test_invalid_derived_surfaces_manifest_is_attention(self) -> None:
        manifest = self.vault / "ops" / "policies" / "derived-surfaces.json"
        manifest.write_text("{not json", encoding="utf-8")

        report = build_report(
            self.vault,
            changed_paths=["ops/script-output-surfaces.json"],
            context=fixed_context(),
        )

        self.assertEqual(report["status"], "attention")
        diagnostics = report["diagnostics"]["derived_surfaces_manifest"]
        self.assertEqual(diagnostics["status"], "failed")
        self.assertEqual(diagnostics["path"], "ops/policies/derived-surfaces.json")
        self.assertIn("JSONDecodeError", diagnostics["message"])
        self.assertEqual(diagnostics["currentness_output_count"], 0)
        plan = report["changed_path_minimum_plan"]
        self.assertEqual(plan["status"], "attention")
        self.assertEqual(plan["unknown_paths"], ["ops/script-output-surfaces.json"])
        self.assertEqual(
            validate_with_schema(
                report,
                load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH),
            ),
            [],
        )

    def test_changed_path_minimum_plan_covers_registry_and_generated_currentness_artifacts(
        self,
    ) -> None:
        report = build_report(
            self.vault,
            changed_paths=[
                "ops/test-lane-registry.json",
                *self.derived_surface_output_only_currentness_paths(),
            ],
            context=fixed_context(),
        )

        plan = report["changed_path_minimum_plan"]
        self.assertEqual(plan["status"], "pass")
        self.assertEqual(plan["coverage_class"], "mixed")
        self.assertEqual(plan["unknown_paths"], [])
        self.assertEqual(
            plan["selected_commands"],
            [
                "make sync-derived-check",
                "make static",
                "make workflow-dependency-planner-check",
                FOCUSED_WORKFLOW_PLANNER_TEST_COMMAND,
            ],
        )
        self.assertEqual(
            plan["command_duration_seconds"],
            {
                "make static": 60,
                "make sync-derived-check": 120,
                "make workflow-dependency-planner-check": 60,
                FOCUSED_WORKFLOW_PLANNER_TEST_COMMAND: 30,
            },
        )
        self.assertEqual(plan["estimated_duration_seconds"], 270)
        self.assertEqual(plan["budget_status"], "within_budget")
        self.assertEqual(validate_with_schema(report, load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH)), [])

    def test_missing_make_dependency_fails_with_diagnostic(self) -> None:
        (self.vault / "Makefile").write_text(
            ".PHONY: release-evidence-converge\n"
            "release-evidence-converge:\n"
            "\t$(MAKE) missing-target\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            report["diagnostics"]["missing_dependencies"],
            [
                {
                    "consumer": "release-evidence-converge",
                    "dependency": "missing-target",
                    "source": "make_recipe",
                }
            ],
        )
        self.assertEqual(validate_with_schema(report, load_schema(WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH)), [])

    def test_changed_files_manifest_is_consumed(self) -> None:
        manifest = self.vault / "tmp" / "changed-files.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init"],
            cwd=self.vault,
            check=True,
            text=True,
            capture_output=True,
        )
        untracked_doc = self.vault / "docs" / "development.md"
        untracked_doc.parent.mkdir(parents=True, exist_ok=True)
        untracked_doc.write_text("untracked doc\n", encoding="utf-8")
        manifest.write_text(
            json.dumps({"changed_files": [{"path": "external-reports/review.md"}]}),
            encoding="utf-8",
        )

        report = build_report(
            self.vault,
            changed_files_manifest="tmp/changed-files.json",
            changed_paths_from_git=True,
            context=fixed_context(),
        )

        self.assertEqual(report["selected_change_paths"], ["external-reports/review.md"])
        self.assertIn("changed_files_manifest", report["input_fingerprints"])
        self.assertEqual(report["selected_workflows"][0]["workflow_id"], "external_report_reference_closeout")

    def test_changed_paths_from_git_reads_untracked_paths(self) -> None:
        subprocess.run(
            ["git", "init"],
            cwd=self.vault,
            check=True,
            text=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=self.vault,
            check=True,
            text=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=LLMwiki Test",
                "-c",
                "user.email=llmwiki-test@example.invalid",
                "commit",
                "-m",
                "baseline",
            ],
            cwd=self.vault,
            check=True,
            text=True,
            capture_output=True,
        )
        changed_path = self.vault / "docs" / "development.md"
        changed_path.parent.mkdir(parents=True, exist_ok=True)
        changed_path.write_text("untracked doc\n", encoding="utf-8")

        report = build_report(
            self.vault,
            changed_paths_from_git=True,
            context=fixed_context(),
        )

        self.assertEqual(report["selected_change_paths"], ["docs/development.md"])
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["diagnostics"]["unknown_change_paths"], [])
        self.assertEqual(
            report["changed_path_minimum_plan"]["selected_commands"],
            ["make static", "make public-check"],
        )

    def test_write_report_validates_schema(self) -> None:
        report = build_report(self.vault, context=fixed_context())

        destination = write_report(self.vault, report, "ops/reports/workflow-dependency-planner.json")

        self.assertEqual(destination, self.vault / "ops" / "reports" / "workflow-dependency-planner.json")
        self.assertTrue(destination.exists())


class ReleaseGovernanceLaneRegistryTests(unittest.TestCase):
    def test_release_governance_ci_matrix_matches_lane_registry(self) -> None:
        report = validate_alignment(REPO_ROOT)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["mismatched_fields"], [])


if __name__ == "__main__":
    unittest.main()
