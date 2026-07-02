from __future__ import annotations

import configparser
import os
import re
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

import pytest

from ops.scripts.test.test_lane_registry_runtime import (
    authoritative_markers,
    compatibility_names,
    documentation_authority,
    documentation_out_of_scope,
    load_registry,
    pack_mark_expr,
    pack_selection_mode,
    pack_selectors,
    pack_summary_suite,
    pytest_marker_docs,
    selection_by_make_target,
)
from tests.makefile_static_helpers import (
    _assert_assignment_exists,
    _assert_recipe_contains_tokens,
    _makefile_assignment_value,
    _makefile_text,
    _pytest_collect_nodeid_path_counts,
    _recipe_lines,
    _target_block,
    _target_dependencies,
)

pytestmark = [
    pytest.mark.public,
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
    pytest.mark.schema_static_smoke,
    pytest.mark.default_test_boundary,
]


MAKEFILE = Path("Makefile")
README = Path("README.md")
DOCS_DEVELOPMENT = Path("docs/development.md")
CONFTEST = Path("tests/conftest.py")
PYTEST_INI = Path("pytest.ini")
REPO_ROOT = Path(__file__).resolve().parents[1]


def _test_lane_registry() -> dict[str, object]:
    return load_registry(REPO_ROOT)


def _changed_path_minimum_rule(
    registry: dict[str, object],
    rule_id: str,
) -> dict[str, object]:
    changed_path_minimums = registry.get("changed_path_minimums")
    if not isinstance(changed_path_minimums, dict):
        raise AssertionError("registry missing changed_path_minimums object")
    rules = changed_path_minimums.get("rules")
    if not isinstance(rules, list):
        raise AssertionError("registry missing changed_path_minimums.rules list")
    for rule in rules:
        if isinstance(rule, dict) and rule.get("rule_id") == rule_id:
            return rule
    raise AssertionError(f"registry missing changed-path rule: {rule_id}")


def _makefile_assignment_items(text: str, variable: str) -> tuple[str, ...]:
    prefix = f"{variable} ?="
    lines = text.splitlines()
    collecting = False
    items: list[str] = []
    for line in lines:
        if not collecting:
            if not line.startswith(prefix):
                continue
            collecting = True
            remainder = line[len(prefix) :].strip()
        else:
            if not line.startswith(("\t", " ")):
                break
            remainder = line.strip()

        continued = remainder.endswith("\\")
        remainder = remainder[:-1].strip() if continued else remainder
        if remainder:
            items.extend(remainder.split())
        if collecting and not continued:
            break

    if not collecting:
        raise AssertionError(f"missing Makefile assignment: {variable}")
    return tuple(items)


def _collect_marker_paths(mark_expr: str) -> set[str]:
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-m",
            mark_expr,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"pytest collect failed for marker expression {mark_expr!r}.\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    paths: set[str] = set()
    paths.update(_pytest_collect_nodeid_path_counts(completed.stdout))
    return paths


def _assert_marker_expression_variable_matches_pack(
    case: unittest.TestCase,
    registry: dict[str, object],
    text: str,
    *,
    variable: str,
    pack_id: str,
    mark_expr_variable: str,
) -> tuple[str, ...]:
    case.assertEqual(pack_selection_mode(registry, pack_id), "marker_expression")
    case.assertEqual(
        pack_mark_expr(registry, pack_id),
        _makefile_assignment_value(text, mark_expr_variable),
    )
    items = _makefile_assignment_items(text, variable)
    expected_items = (
        "-m",
        f'"$({mark_expr_variable})"',
    )
    case.assertEqual(items, expected_items)
    return items


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _pytest_ini_marker_docs() -> dict[str, str]:
    parser = configparser.ConfigParser()
    parser.read_string(PYTEST_INI.read_text(encoding="utf-8"))
    markers_value = parser["pytest"]["markers"]
    marker_docs: dict[str, str] = {}
    for line in markers_value.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        marker, separator, description = stripped.partition(":")
        if not separator:
            raise AssertionError(f"invalid pytest.ini marker declaration: {stripped}")
        marker_docs[marker.strip()] = description.strip()
    return marker_docs


def _assert_refresh_generated_split_targets(case: unittest.TestCase, text: str) -> None:
    case.assertIn(
        "refresh-generated-core: registry-preflight raw-registry-export manifest script-output-surfaces routing-provenance-aggregate outcome-metrics promotion-decision-trends artifact-freshness mechanism-review mutation-proposal",
        text,
    )
    case.assertEqual(
        _recipe_lines(text, "refresh-generated-observability"),
        [
            "$(MAKE) make-target-inventory",
            "$(MAKE) workflow-dependency-planner",
            "$(MAKE) release-workflow-order-guard",
            "$(MAKE) function-budget-refactor-proposals",
            "$(MAKE) outcome-provenance-gate-policy",
            "$(MAKE) generated-artifact-converge",
        ],
    )
    case.assertIn(
        "refresh-generated: refresh-generated-core refresh-generated-observability",
        text,
    )
    case.assertEqual(
        _recipe_lines(text, "generated-artifact-converge"),
        [
            '$(PYTHON) -m ops.scripts.generated_artifact_converge_summary --vault "$(VAULT)" --phase before --out "$(GENERATED_ARTIFACT_CONVERGE_SUMMARY_BEFORE_OUT)"',
            "$(MAKE) generated-artifact-finality-suffix",
            '$(PYTHON) -m ops.scripts.generated_artifact_converge_summary --vault "$(VAULT)" --phase after --before "$(GENERATED_ARTIFACT_CONVERGE_SUMMARY_BEFORE_OUT)" --out "$(GENERATED_ARTIFACT_CONVERGE_SUMMARY_OUT)"',
        ],
    )
    case.assertEqual(
        _recipe_lines(text, "generated-artifact-script-output"),
        ["$(MAKE) script-output-surfaces"],
    )
    case.assertEqual(
        _recipe_lines(text, "sync-derived"),
        [
            "$(MAKE) pytest-markers-sync",
            "$(MAKE) test-selectors-sync",
            "$(MAKE) sync-public-policy",
            "$(MAKE) script-output-surfaces",
            "$(MAKE) script-lifecycle-policy",
            "$(MAKE) script-module-surfaces",
            "$(MAKE) release-governance-sync",
            "$(MAKE) make-target-inventory",
            "$(MAKE) report-schema-samples-regenerate",
        ],
    )
    case.assertEqual(
        _recipe_lines(text, "sync-derived-check"),
        [
            "$(MAKE) pytest-markers-sync-check",
            "$(MAKE) test-selectors-sync-check",
            "$(MAKE) sync-public-policy-check",
            "$(MAKE) script-output-surfaces-check",
            "$(MAKE) script-lifecycle-policy-check",
            "$(MAKE) script-module-surfaces-check",
            "$(MAKE) release-governance-sync-check",
            "$(MAKE) make-target-inventory-check",
            "$(MAKE) report-schema-samples-check",
        ],
    )
    case.assertNotIn(
        "generated-artifact-converge", _target_block(text, "sync-derived-check")
    )
    case.assertEqual(
        _recipe_lines(text, "pytest-markers-sync"),
        [
            '$(PYTHON) -m ops.scripts.test.generate_pytest_ini_markers --vault "$(VAULT)"'
        ],
    )
    case.assertEqual(
        _recipe_lines(text, "pytest-markers-sync-check"),
        ["@$(MAKE) _internal-pytest-markers-sync-check"],
    )
    case.assertEqual(
        _recipe_lines(text, "_internal-pytest-markers-sync-check"),
        [
            '$(PYTHON) -m ops.scripts.test.generate_pytest_ini_markers --vault "$(VAULT)" --check'
        ],
    )
    case.assertEqual(
        _recipe_lines(text, "generated-artifact-finality-suffix"),
        [
            "$(MAKE) artifact-freshness",
            "$(MAKE) external-report-action-matrix",
            "$(MAKE) generated-artifact-index",
            "$(MAKE) artifact-freshness",
            "$(MAKE) external-report-action-matrix",
            "$(MAKE) generated-artifact-index-body",
            "$(MAKE) artifact-freshness",
        ],
    )
    case.assertIn(
        "GENERATED_ARTIFACT_CONVERGE_SUMMARY_OUT ?= tmp/generated-artifact-converge-summary.json",
        text,
    )
    case.assertIn(
        "GENERATED_ARTIFACT_CONVERGE_SUMMARY_BEFORE_OUT ?= tmp/generated-artifact-converge-summary.before.json",
        text,
    )
    for phony_target in (
        "refresh-generated-core",
        "refresh-generated-observability",
        "pytest-markers-sync",
        "pytest-markers-sync-check",
        "_internal-pytest-markers-sync-check",
        "sync-derived",
        "sync-derived-check",
        "generated-artifact-converge",
        "generated-artifact-script-output",
        "generated-artifact-finality-suffix",
        "command-log-summary-backfill",
        "generated-artifact-retention-clean",
        "script-output-surfaces",
        "script-module-surfaces",
        "script-module-surfaces-check",
        "script-lifecycle-policy",
        "script-lifecycle-policy-check",
        "function-budget-refactor-proposals",
        "function-budget-edit-check",
        "outcome-provenance-gate-policy",
        "external-report-action-matrix",
        "artifact-relocation-audit",
    ):
        with case.subTest(phony_target=phony_target):
            case.assertIn(phony_target, _target_block(text, ".PHONY"))


def _assert_observability_output_variables(case: unittest.TestCase, text: str) -> None:
    expected_variables = (
        "FUNCTION_BUDGET_REFACTOR_PROPOSALS_OUT ?= ops/reports/function-budget-refactor-proposals.json",
        "FUNCTION_BUDGET_REFACTOR_PROPOSALS_CANDIDATE_OUT ?= tmp/function-budget-refactor-proposals.candidate.json",
        "OUTCOME_PROVENANCE_GATE_POLICY_OUT ?= ops/reports/outcome-provenance-gate-policy.json",
        "OUTCOME_PROVENANCE_GATE_POLICY_CANDIDATE_OUT ?= tmp/outcome-provenance-gate-policy.candidate.json",
        "EXTERNAL_REPORT_ACTION_MATRIX_OUT ?= ops/reports/external-report-action-matrix.json",
        "SCRIPT_OUTPUT_SURFACES_OUT ?= ops/script-output-surfaces.json",
        "SCRIPT_MODULE_SURFACES_OUT ?= ops/script-module-surfaces.json",
        "SCRIPT_LIFECYCLE_POLICY_OUT ?= ops/script-lifecycle-policy.json",
        "SCRIPT_LIFECYCLE_OVERRIDES ?= ops/script-lifecycle-overrides.json",
        "SCRIPT_MODULE_SURFACE_OVERRIDES ?= ops/script-module-surface-overrides.json",
        "GENERATED_ARTIFACT_RETENTION_CLEAN_OUT ?= tmp/generated-artifact-retention-clean.json",
        "GENERATED_ARTIFACT_RETENTION_CLEAN_APPLY ?=",
        "COMMAND_LOG_SUMMARY_BACKFILL_OUT ?= tmp/command-log-summary-backfill.json",
        "COMMAND_LOG_SUMMARY_BACKFILL_APPLY ?=",
        "COMMAND_LOG_SUMMARY_BACKFILL_ALL ?=",
        "COMMAND_LOG_SUMMARY_BACKFILL_INCLUDE_RUN_COMMANDS ?=",
        "COMMAND_LOG_SUMMARY_BACKFILL_CLOSE_PROMOTED_UNREFERENCED ?=",
        "COMMAND_LOG_SUMMARY_BACKFILL_DELETE_RAW ?=",
        "COMMAND_LOG_SUMMARY_BACKFILL_OPERATOR_CONFIRMATION ?=",
        "COMMAND_LOG_SUMMARY_BACKFILL_RUN_ID ?=",
        "CLEAN_FIXTURE_REGENERATION_GUARD_OUT ?= tmp/clean-fixture-regeneration-guard.json",
        "MAKE_TARGET_INVENTORY_OUT ?= tmp/make-target-inventory.json",
        "WORKFLOW_DEPENDENCY_PLANNER_OUT ?= ops/reports/workflow-dependency-planner.json",
        "WORKFLOW_DEPENDENCY_PLANNER_CANDIDATE_OUT ?= tmp/workflow-dependency-planner.candidate.json",
        "WORKFLOW_DEPENDENCY_PLANNER_CHECK_OUT ?= tmp/workflow-dependency-planner-check.json",
        "RELEASE_WORKFLOW_ORDER_GUARD_OUT ?= ops/reports/release-workflow-order-guard.json",
        "RELEASE_WORKFLOW_ORDER_GUARD_CANDIDATE_OUT ?= tmp/release-workflow-order-guard.candidate.json",
    )
    for variable in expected_variables:
        with case.subTest(variable=variable):
            case.assertIn(variable, text)


def _assert_script_surface_and_inventory_targets(
    case: unittest.TestCase, text: str
) -> None:
    script_output_block = _target_block(text, "script-output-surfaces")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.script_output_surfaces --vault "$(VAULT)" --out "$(SCRIPT_OUTPUT_SURFACES_OUT)"',
        script_output_block,
    )
    case.assertNotIn("ops.scripts.canonical_artifact_promote", script_output_block)
    case.assertNotIn("--preserve-existing-on-semantic-match", script_output_block)
    case.assertNotIn(
        "--semantic-match-includes-source-tree-fingerprint", script_output_block
    )
    script_output_check_block = _target_block(text, "script-output-surfaces-check")
    case.assertIn("script-output-surfaces-check", _target_block(text, ".PHONY"))
    case.assertIn("ops.scripts.script_output_surfaces", script_output_check_block)
    case.assertIn('--stored "$(SCRIPT_OUTPUT_SURFACES_OUT)"', script_output_check_block)
    case.assertIn("--check", script_output_check_block)
    case.assertNotIn("SCRIPT_OUTPUT_SURFACES_CANDIDATE_OUT", script_output_check_block)
    case.assertNotIn(
        "ops.scripts.canonical_artifact_promote", script_output_check_block
    )
    script_module_block = _target_block(text, "script-module-surfaces")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.script_module_surfaces --vault "$(VAULT)" --out "$(SCRIPT_MODULE_SURFACES_OUT)" --overrides "$(SCRIPT_MODULE_SURFACE_OVERRIDES)"',
        script_module_block,
    )
    script_module_check_block = _target_block(text, "script-module-surfaces-check")
    case.assertIn("script-module-surfaces-check", _target_block(text, ".PHONY"))
    case.assertIn("ops.scripts.script_module_surfaces", script_module_check_block)
    case.assertIn('--stored "$(SCRIPT_MODULE_SURFACES_OUT)"', script_module_check_block)
    case.assertIn(
        '--overrides "$(SCRIPT_MODULE_SURFACE_OVERRIDES)"',
        script_module_check_block,
    )
    case.assertIn("--check", script_module_check_block)
    case.assertNotIn("SCRIPT_MODULE_SURFACES_CANDIDATE_OUT", script_module_check_block)
    case.assertNotIn(
        "ops.scripts.canonical_artifact_promote", script_module_check_block
    )
    script_lifecycle_block = _target_block(text, "script-lifecycle-policy")
    case.assertIn("script-lifecycle-policy", _target_block(text, ".PHONY"))
    case.assertIn(
        '$(PYTHON) -m ops.scripts.core.script_lifecycle_policy --vault "$(VAULT)" --out "$(SCRIPT_LIFECYCLE_POLICY_OUT)" --overrides "$(SCRIPT_LIFECYCLE_OVERRIDES)"',
        script_lifecycle_block,
    )
    script_lifecycle_check_block = _target_block(text, "script-lifecycle-policy-check")
    case.assertIn("script-lifecycle-policy-check", _target_block(text, ".PHONY"))
    case.assertIn(
        "ops.scripts.core.script_lifecycle_policy",
        script_lifecycle_check_block,
    )
    case.assertIn(
        '--stored "$(SCRIPT_LIFECYCLE_POLICY_OUT)"',
        script_lifecycle_check_block,
    )
    case.assertIn(
        '--overrides "$(SCRIPT_LIFECYCLE_OVERRIDES)"',
        script_lifecycle_check_block,
    )
    case.assertIn("--check", script_lifecycle_check_block)
    retention_clean_block = _target_block(text, "generated-artifact-retention-clean")
    command_log_backfill_block = _target_block(text, "command-log-summary-backfill")
    case.assertIn("command-log-summary-backfill", _target_block(text, ".PHONY"))
    case.assertIn(
        "ops.scripts.command_log_summary_backfill", command_log_backfill_block
    )
    case.assertIn(
        '--out "$(COMMAND_LOG_SUMMARY_BACKFILL_OUT)"', command_log_backfill_block
    )
    case.assertIn("--apply", command_log_backfill_block)
    case.assertIn("--all", command_log_backfill_block)
    case.assertIn("--include-run-commands", command_log_backfill_block)
    case.assertIn("--close-promoted-unreferenced", command_log_backfill_block)
    case.assertIn("--delete-raw", command_log_backfill_block)
    case.assertIn("--operator-confirmation", command_log_backfill_block)
    case.assertIn("--run-id", command_log_backfill_block)
    case.assertIn("generated-artifact-retention-clean", _target_block(text, ".PHONY"))
    case.assertIn(
        "ops.scripts.generated_artifact_retention_clean", retention_clean_block
    )
    case.assertIn(
        '--out "$(GENERATED_ARTIFACT_RETENTION_CLEAN_OUT)"', retention_clean_block
    )
    case.assertIn("--apply", retention_clean_block)
    guard_block = _target_block(text, "clean-fixture-regeneration-guard")
    case.assertIn("clean-fixture-regeneration-guard", _target_block(text, ".PHONY"))
    case.assertIn(
        '$(PYTHON) -m ops.scripts.clean_fixture_regeneration_guard --vault "$(VAULT)" --out "$(CLEAN_FIXTURE_REGENERATION_GUARD_OUT)"',
        guard_block,
    )
    case.assertIn(
        "script-output-surfaces-clean-regenerate: clean-fixture-regeneration-guard script-output-surfaces",
        text,
    )
    case.assertIn("make-target-inventory", _target_block(text, ".PHONY"))
    case.assertIn("make-target-inventory-check", _target_block(text, ".PHONY"))
    case.assertIn(
        '$(PYTHON) -m ops.scripts.make_target_inventory --vault "$(VAULT)" --out "$(MAKE_TARGET_INVENTORY_OUT)"',
        _target_block(text, "make-target-inventory"),
    )
    case.assertIn(
        '$(PYTHON) -m ops.scripts.make_target_inventory --vault "$(VAULT)" --check',
        _target_block(text, "make-target-inventory-check"),
    )


def _assert_workflow_dependency_planner_target(
    case: unittest.TestCase, text: str
) -> None:
    case.assertIn("workflow-dependency-planner", _target_block(text, ".PHONY"))
    case.assertIn("workflow-dependency-planner-check", _target_block(text, ".PHONY"))
    planner_block = _target_block(text, "workflow-dependency-planner")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.workflow_dependency_planner --vault "$(VAULT)" --out "$(WORKFLOW_DEPENDENCY_PLANNER_CANDIDATE_OUT)"',
        planner_block,
    )
    case.assertIn("ops.scripts.canonical_artifact_promote", planner_block)
    case.assertIn(
        "--schema ops/schemas/workflow-dependency-planner.schema.json", planner_block
    )
    case.assertIn("--expected-artifact-kind workflow_dependency_planner", planner_block)
    case.assertIn(
        "--expected-producer ops.scripts.workflow_dependency_planner", planner_block
    )
    planner_check_block = _target_block(text, "workflow-dependency-planner-check")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.workflow_dependency_planner --vault "$(VAULT)" --out "$(WORKFLOW_DEPENDENCY_PLANNER_CHECK_OUT)"',
        planner_check_block,
    )
    case.assertNotIn("canonical_artifact_promote", planner_check_block)
    for target in ("static", "check", "check-all", "release-check", "release-clean"):
        with case.subTest(target=target):
            case.assertNotIn("workflow-dependency-planner", _target_block(text, target))
    case.assertNotIn(
        "$(MAKE) workflow-dependency-planner",
        _target_block(text, "release-evidence-converge"),
    )
    case.assertNotIn(
        "$(MAKE) workflow-dependency-planner", _target_block(text, "check-finalized")
    )


def _assert_release_workflow_order_guard_target(
    case: unittest.TestCase, text: str
) -> None:
    case.assertIn("release-workflow-order-guard", _target_block(text, ".PHONY"))
    order_guard_block = _target_block(text, "release-workflow-order-guard")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.release_workflow_order_guard --vault "$(VAULT)" --out "$(RELEASE_WORKFLOW_ORDER_GUARD_CANDIDATE_OUT)"',
        order_guard_block,
    )
    case.assertIn("ops.scripts.canonical_artifact_promote", order_guard_block)
    case.assertIn(
        "--schema ops/schemas/release-workflow-order-guard.schema.json",
        order_guard_block,
    )
    case.assertIn(
        "--expected-artifact-kind release_workflow_order_guard", order_guard_block
    )
    case.assertIn(
        "--expected-producer ops.scripts.release_workflow_order_guard",
        order_guard_block,
    )
    case.assertNotIn(
        "$(MAKE) release-workflow-order-guard",
        _target_block(text, "release-evidence-converge"),
    )
    case.assertNotIn(
        "$(MAKE) release-workflow-order-guard", _target_block(text, "check-finalized")
    )


def _assert_function_budget_and_outcome_targets(
    case: unittest.TestCase, text: str
) -> None:
    proposal_block = _target_block(text, "function-budget-refactor-proposals")
    edit_check_block = _target_block(text, "function-budget-edit-check")
    case.assertIn(
        "function-budget-refactor-proposals: wiki-lint-review-classification", text
    )
    case.assertIn(
        '$(PYTHON) -m ops.scripts.function_budget_refactor_proposals --vault "$(VAULT)" --classification "$(WIKI_LINT_REVIEW_CLASSIFICATION_OUT)" --out "$(FUNCTION_BUDGET_REFACTOR_PROPOSALS_CANDIDATE_OUT)"',
        proposal_block,
    )
    case.assertIn(
        "--schema ops/schemas/function-budget-refactor-proposals.schema.json",
        proposal_block,
    )
    case.assertIn(
        "function-budget-edit-check: function-budget-refactor-proposals", text
    )
    case.assertIn("$(MAKE) complexity-budget-touched-check", edit_check_block)

    outcome_policy_block = _target_block(text, "outcome-provenance-gate-policy")
    case.assertIn(
        "outcome-provenance-gate-policy: outcome-metrics routing-provenance-aggregate",
        text,
    )
    case.assertIn(
        '$(PYTHON) -m ops.scripts.outcome_provenance_gate_policy --vault "$(VAULT)" --out "$(OUTCOME_PROVENANCE_GATE_POLICY_CANDIDATE_OUT)"',
        outcome_policy_block,
    )
    case.assertIn(
        "--schema ops/schemas/outcome-provenance-gate-policy.schema.json",
        outcome_policy_block,
    )
    case.assertIn(
        "--expected-artifact-kind outcome_provenance_gate_policy", outcome_policy_block
    )
    case.assertIn(
        "--expected-producer ops.scripts.outcome_provenance_gate_policy",
        outcome_policy_block,
    )

    promotion_trends_block = _target_block(text, "promotion-decision-trends")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.promotion_decision_trends --vault "$(VAULT)" --recent-window "$(PROMOTION_DECISION_TRENDS_RECENT_WINDOW)"',
        promotion_trends_block,
    )


def _assert_external_report_action_matrix_target(
    case: unittest.TestCase, text: str
) -> None:
    external_action_block = _target_block(text, "external-report-action-matrix")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.external_report_action_matrix --vault "$(VAULT)" --out "$(EXTERNAL_REPORT_ACTION_MATRIX_OUT)"',
        external_action_block,
    )
    case.assertIn("compatibility aggregate", _target_block(text, "refresh-generated"))


class MakefileStaticGateTests(unittest.TestCase):
    def test_root_makefile_keeps_only_common_variables_and_aggregate_aliases(
        self,
    ) -> None:
        root_text = MAKEFILE.read_text(encoding="utf-8")
        allowed_assignments = {
            "VENV_DIR",
            "VENV_PYTHON",
            "PYTHON",
            "BOOTSTRAP_PYTHON",
            "VAULT",
            "EXECUTION_LANE_POLICY",
        }
        assignment_names = {
            match.group(1)
            for match in re.finditer(
                r"^([A-Z0-9_]+)\s*(?:\?|:)?=", root_text, flags=re.MULTILINE
            )
        }

        self.assertEqual(assignment_names, allowed_assignments)
        for mk_file in (
            "mk/core.mk",
            "mk/static.mk",
            "mk/test.mk",
            "mk/eval.mk",
            "mk/artifact.mk",
            "mk/registry.mk",
            "mk/mechanism.mk",
            "mk/release.mk",
            "mk/public.mk",
            "mk/supply_chain.mk",
        ):
            with self.subTest(mk_file=mk_file):
                self.assertIn(f"include {mk_file}", root_text)
                self.assertLess(
                    root_text.index(f"include {mk_file}"),
                    root_text.index(".PHONY: check"),
                )
        self.assertLess(
            root_text.index("include mk/test.mk"),
            root_text.index("export PYTEST_DISABLE_PLUGIN_AUTOLOAD"),
        )

    def test_help_target_indexes_operator_entrypoints(self) -> None:
        text = _makefile_text()
        block = _target_block(text, "help")

        self.assertIn("help", _target_block(text, ".PHONY"))
        for heading in (
            "Setup:",
            "Source checks:",
            "Inventory and derived surfaces:",
            "Report contracts:",
            "Public mirror:",
            "Mechanism:",
            "Release:",
        ):
            self.assertIn(heading, block)
        for target in (
            "make dev-install",
            "make check",
            "make test",
            "make static",
            "make local-cache-clean",
            "make local-tool-state-clean",
            "make uv-cache-prune",
            "make strict-preview-audit",
            "make sync-derived",
            "make sync-derived-check",
            "make pytest-markers-sync",
            "make make-target-inventory",
            "make make-target-inventory-check",
            "make test-selectors-sync",
            "make test-selectors-sync-check",
            "make review-surface-manifest",
            "make test-report-contract-core",
            "make external-report-lifecycle-refresh",
            "make sync-public-policy",
            "make goal-runtime-run-admission",
            "make release-evidence-converge",
            "make release-auto-promotion-ready",
        ):
            self.assertIn(target, block)

    def test_check_targets_include_static_gate(self) -> None:
        text = _makefile_text()

        for target in ("check", "check-serial", "check-all", "check-all-serial"):
            with self.subTest(target=target):
                dependencies = _target_dependencies(text, target)
                self.assertEqual(dependencies[:2], ("uv-lock-check", "static"))
                self.assertIn("registry-preflight-check", dependencies)
                self.assertNotIn("registry-preflight", dependencies)
        self.assertEqual(
            _target_dependencies(text, "static"),
            ("static-local", "lock-freshness-check"),
        )
        self.assertEqual(
            _target_dependencies(text, "static-local"), ("ruff", "typecheck")
        )
        self.assertEqual(
            _target_dependencies(text, "lock-freshness-check"), ("uv-lock-check",)
        )
        self.assertEqual(
            _recipe_lines(text, "uv-lock-check"),
            [
                'UV_DEFAULT_INDEX="$(UV_CANONICAL_INDEX_URL)" $(UV) lock --check $(UV_LOCK_CHECK_INDEX_FLAGS)'
            ],
        )
        self.assertIn("UV_CANONICAL_INDEX_URL ?= https://pypi.org/simple", text)
        self.assertIn(
            'UV_LOCK_CHECK_INDEX_FLAGS ?= --default-index "$(UV_CANONICAL_INDEX_URL)"',
            text,
        )
        self.assertIn("static-local", _target_block(text, ".PHONY"))
        self.assertIn("lock-freshness-check", _target_block(text, ".PHONY"))
        self.assertIn("uv-lock-check", _target_block(text, ".PHONY"))

    def test_strict_targets_include_warning_budget_gate(self) -> None:
        text = _makefile_text()

        self.assertIn(
            "check-strict: check warning-budget complexity-budget-touched-check", text
        )
        self.assertIn("check-conditional: check", text)
        self.assertIn(
            "check-clean: check-clean-lane-guard check-conditional warning-budget release-evidence-cohort-check",
            text,
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target check-clean',
            _target_block(text, "check-clean-lane-guard"),
        )
        self.assertIn(
            "release-evidence-converge-lane-guard", _target_block(text, ".PHONY")
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-evidence-converge',
            _target_block(text, "release-evidence-converge-lane-guard"),
        )
        self.assertIn(
            "release-evidence-closeout-lane-guard", _target_block(text, ".PHONY")
        )
        self.assertIn(
            "release-evidence-closeout-lane-guard is a compatibility alias",
            _target_block(text, "release-evidence-closeout-lane-guard"),
        )
        self.assertIn("release-builder-full-lane-guard", _target_block(text, ".PHONY"))
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-builder-full',
            _target_block(text, "release-builder-full-lane-guard"),
        )
        self.assertIn("release-smoke-lane-guard", _target_block(text, ".PHONY"))
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-smoke',
            _target_block(text, "release-smoke-lane-guard"),
        )
        self.assertIn(
            "release-distribution-zip: release-distribution-zip-lane-guard",
            text,
        )
        self.assertIn(
            "release-distribution-zip-lane-guard", _target_block(text, ".PHONY")
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-distribution-zip',
            _target_block(text, "release-distribution-zip-lane-guard"),
        )
        self.assertIn("release-conditional: release-evidence-refresh-fast", text)
        self.assertIn(
            "release-clean: release-check warning-budget release-evidence-converge release-evidence-cohort-check",
            text,
        )
        self.assertIn(
            "release-provenance-clean: release-clean supply-chain-check", text
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.warning_budget --vault "$(VAULT)"',
            _target_block(text, "warning-budget"),
        )

    def test_static_gate_runs_ruff_and_full_ops_mypy_target(self) -> None:
        text = _makefile_text()

        self.assertIn("RUFF_TARGETS ?= ops/scripts tests tools", text)
        self.assertIn("MYPY_TARGETS ?= ops/scripts", text)
        self.assertIn("TOOL_CACHE_ROOT ?= tmp/tool-cache", text)
        self.assertIn("TOOL_CACHE_PLATFORM ?=", text)
        self.assertIn(
            "RUFF_CACHE_DIR ?= $(TOOL_CACHE_ROOT)/ruff/$(TOOL_CACHE_PLATFORM)", text
        )
        self.assertIn(
            "MYPY_CACHE_DIR ?= $(TOOL_CACHE_ROOT)/mypy/$(TOOL_CACHE_PLATFORM)", text
        )
        self.assertIn("static-local: ruff typecheck", text)
        self.assertIn("lock-freshness-check: uv-lock-check", text)
        self.assertIn("static: static-local lock-freshness-check", text)
        self.assertIn(
            'UV_DEFAULT_INDEX="$(UV_CANONICAL_INDEX_URL)" $(UV) lock --check $(UV_LOCK_CHECK_INDEX_FLAGS)',
            _target_block(text, "uv-lock-check"),
        )
        self.assertIn(
            "$(PYTHON) -m ruff check $(RUFF_CACHE_FLAGS) $(RUFF_TARGETS)",
            _target_block(text, "ruff"),
        )
        self.assertIn(
            "$(PYTHON) -m mypy $(MYPY_CACHE_FLAGS) $(MYPY_TARGETS)",
            _target_block(text, "typecheck"),
        )

    def test_local_cache_clean_removes_only_regenerable_repo_caches(self) -> None:
        text = _makefile_text()
        block = _target_block(text, "local-cache-clean")

        self.assertIn("local-cache-clean", _target_block(text, ".PHONY"))
        self.assertIn(
            "LOCAL_CACHE_CLEAN_PATHS ?= .pytest_cache .hypothesis .ruff_cache .mypy_cache $(TOOL_CACHE_ROOT)",
            text,
        )
        self.assertIn(
            "LOCAL_TOOL_STATE_CLEAN_PATHS ?= .agents .obsidian .serena .vscode .ouroboros .ouroboros_eval_artifact.md",
            text,
        )
        self.assertIn("LOCAL_CACHE_CLEAN_FIND_ROOTS ?= ops tests tools", text)
        self.assertIn("rm -rf $(LOCAL_CACHE_CLEAN_PATHS)", block)
        self.assertIn(
            "find $(LOCAL_CACHE_CLEAN_FIND_ROOTS) -type d -name __pycache__", block
        )
        self.assertIn("find $(LOCAL_CACHE_CLEAN_FIND_ROOTS) -type f", block)
        self.assertNotIn("LOCAL_TOOL_STATE_CLEAN_PATHS", block)
        self.assertNotIn(".kiro", block)
        self.assertNotIn(".venv", block)
        self.assertNotIn("ops/reports", block)
        self.assertNotIn("build/release", block)

    def test_local_tool_state_clean_is_explicit_and_keeps_migration_state_out(
        self,
    ) -> None:
        text = _makefile_text()
        block = _target_block(text, "local-tool-state-clean")

        self.assertIn("local-tool-state-clean", _target_block(text, ".PHONY"))
        self.assertIn("rm -rf $(LOCAL_TOOL_STATE_CLEAN_PATHS)", block)
        self.assertNotIn(".kiro", block)
        self.assertNotIn(".venv", block)
        self.assertNotIn("ops/reports", block)

    def test_uv_cache_prune_keeps_global_uv_cleanup_explicit_and_non_destructive(
        self,
    ) -> None:
        text = _makefile_text()
        block = _target_block(text, "uv-cache-prune")

        self.assertIn("uv-cache-prune", _target_block(text, ".PHONY"))
        self.assertIn("UV_CACHE_PRUNE_FLAGS ?=", text)
        self.assertIn("$(UV) cache prune $(UV_CACHE_PRUNE_FLAGS)", block)
        self.assertNotIn("cache clean", block)
        self.assertNotIn("--force", block)

    def test_pytest_entrypoints_disable_third_party_plugin_autoload(self) -> None:
        text = _makefile_text()

        self.assertIn("PYTEST_DISABLE_PLUGIN_AUTOLOAD ?= 1", text)
        self.assertIn("export PYTEST_DISABLE_PLUGIN_AUTOLOAD", text)
        self.assertIn("LLMWIKI_MAKE_PYTEST_ENTRYPOINT ?= 1", text)
        self.assertIn("export LLMWIKI_MAKE_PYTEST_ENTRYPOINT", text)
        self.assertIn("PYTHONDONTWRITEBYTECODE ?= 1", text)
        self.assertIn("export PYTHONDONTWRITEBYTECODE", text)
        self.assertIn("PYTEST_XDIST_WORKERS ?= 4", text)
        self.assertIn("PYTEST_XDIST_MAXPROCESSES ?= 4", text)
        self.assertIn(
            "PYTEST_XDIST_MAXPROCESSES_FLAGS ?= --maxprocesses=$(PYTEST_XDIST_MAXPROCESSES)",
            text,
        )
        self.assertIn(
            "PYTEST_LOADFILE_FLAGS ?= -p xdist.plugin -n $(PYTEST_XDIST_WORKERS) $(PYTEST_XDIST_MAXPROCESSES_FLAGS) --dist=loadfile",
            text,
        )
        self.assertNotIn("-n auto --dist=loadfile", text)
        self.assertIn("PYTEST_PARALLEL_FLAGS ?= $(PYTEST_LOADFILE_FLAGS)", text)
        self.assertIn("PYTEST_CACHE_ISOLATION_FLAGS ?= -p no:cacheprovider", text)
        self.assertIn(
            "PYTEST_FLAGS ?= $(PYTEST_PARALLEL_FLAGS) $(PYTEST_CACHE_ISOLATION_FLAGS)",
            text,
        )
        self.assertIn(
            "PYTEST_REPORT_CONTRACT_FLAGS ?= $(PYTEST_LOADFILE_FLAGS) $(PYTEST_CACHE_ISOLATION_FLAGS)",
            text,
        )
        self.assertIn(
            "PYTEST_RELEASE_SEALING_FLAGS ?= $(PYTEST_LOADFILE_FLAGS) $(PYTEST_CACHE_ISOLATION_FLAGS)",
            text,
        )

    def test_pytest_ini_declares_registry_markers(self) -> None:
        registry = _test_lane_registry()
        pytest_ini_text = PYTEST_INI.read_text(encoding="utf-8")
        marker_docs = _pytest_ini_marker_docs()

        self.assertTrue(authoritative_markers(registry).issubset(set(marker_docs)))
        self.assertEqual(marker_docs, pytest_marker_docs(registry))
        self.assertIn("# >>> pytest-marker-registry >>>", pytest_ini_text)
        self.assertIn("# <<< pytest-marker-registry <<<", pytest_ini_text)
        self.assertNotIn(
            "deprecated compatibility alias for artifact_finalization", pytest_ini_text
        )

    def test_registry_make_target_marker_expressions_match_makefile_variables(
        self,
    ) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()
        variable_by_target = {
            "test-slow": "PYTEST_SLOW_MARK_EXPR",
            "test-integration": "PYTEST_INTEGRATION_MARK_EXPR",
            "test-integration-heavy": "PYTEST_INTEGRATION_HEAVY_MARK_EXPR",
            "test-public": "PYTEST_PUBLIC_MARK_EXPR",
            "test-report-contract-all": "PYTEST_REPORT_CONTRACT_MARK_EXPR",
            "test-release-sealing-all": "PYTEST_RELEASE_SEALING_MARK_EXPR",
            "test-subprocess": "PYTEST_SUBPROCESS_MARK_EXPR",
        }

        for target, variable in variable_by_target.items():
            with self.subTest(target=target, variable=variable):
                self.assertEqual(
                    _normalize_whitespace(_makefile_assignment_value(text, variable)),
                    _normalize_whitespace(selection_by_make_target(registry)[target]),
                )

    def test_registry_marker_expression_packs_match_makefile_variables(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()

        _assert_marker_expression_variable_matches_pack(
            self,
            registry,
            text,
            variable="FAST_SMOKE_TESTS",
            pack_id="fast_smoke",
            mark_expr_variable="PYTEST_FAST_SMOKE_MARK_EXPR",
        )
        _assert_marker_expression_variable_matches_pack(
            self,
            registry,
            text,
            variable="DEFAULT_TEST_BOUNDARY_TESTS",
            pack_id="default_test_boundary",
            mark_expr_variable="PYTEST_DEFAULT_TEST_BOUNDARY_MARK_EXPR",
        )
        _assert_marker_expression_variable_matches_pack(
            self,
            registry,
            text,
            variable="RUNTIME_HOTSPOT_SMOKE_TESTS",
            pack_id="runtime_hotspot_smoke",
            mark_expr_variable="PYTEST_RUNTIME_HOTSPOT_SMOKE_MARK_EXPR",
        )
        _assert_marker_expression_variable_matches_pack(
            self,
            registry,
            text,
            variable="REPORT_CONTRACT_CORE_TESTS",
            pack_id="report_contract_core",
            mark_expr_variable="PYTEST_REPORT_CONTRACT_CORE_MARK_EXPR",
        )
        _assert_marker_expression_variable_matches_pack(
            self,
            registry,
            text,
            variable="RELEASE_SEALING_CORE_TESTS",
            pack_id="release_sealing_core",
            mark_expr_variable="PYTEST_RELEASE_SEALING_CORE_MARK_EXPR",
        )
        _assert_marker_expression_variable_matches_pack(
            self,
            registry,
            text,
            variable="REPORT_CONTRACT_ALL_TESTS",
            pack_id="report_contract_all",
            mark_expr_variable="PYTEST_REPORT_CONTRACT_MARK_EXPR",
        )
        _assert_marker_expression_variable_matches_pack(
            self,
            registry,
            text,
            variable="SUBPROCESS_TESTS",
            pack_id="subprocess_checks",
            mark_expr_variable="PYTEST_SUBPROCESS_MARK_EXPR",
        )
        _assert_marker_expression_variable_matches_pack(
            self,
            registry,
            text,
            variable="SCHEMA_STATIC_SMOKE_TESTS",
            pack_id="schema_static_smoke",
            mark_expr_variable="PYTEST_SCHEMA_STATIC_SMOKE_MARK_EXPR",
        )
        _assert_marker_expression_variable_matches_pack(
            self,
            registry,
            text,
            variable="RELEASE_CLOSEOUT_REGRESSION_TESTS",
            pack_id="release_closeout_regression",
            mark_expr_variable="PYTEST_RELEASE_CLOSEOUT_REGRESSION_MARK_EXPR",
        )

    def test_core_marker_packs_collect_via_registered_marker_expression(self) -> None:
        registry = _test_lane_registry()

        for pack_id in (
            "report_contract_core",
            "schema_static_smoke",
            "release_sealing_core",
        ):
            with self.subTest(pack_id=pack_id):
                collected_paths = _collect_marker_paths(pack_mark_expr(registry, pack_id))
                self.assertTrue(collected_paths)
                self.assertTrue(
                    all(
                        path.startswith("tests/") and path.endswith(".py")
                        for path in collected_paths
                    )
                )

    def test_release_sealing_core_preserves_release_sealing_marker_compatibility(
        self,
    ) -> None:
        env = os.environ.copy()
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "-p",
                "no:cacheprovider",
                "-m",
                "release_sealing_core and not release_sealing",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        self.assertEqual(
            completed.returncode,
            5,
            msg=(
                "release_sealing_core node IDs must keep their release_sealing marker "
                "compatibility.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            ),
        )
        self.assertEqual(_pytest_collect_nodeid_path_counts(completed.stdout), {})

    def test_make_dry_run_sees_generated_selector_fragment(self) -> None:
        registry = _test_lane_registry()
        test_mk_text = Path("mk/test.mk").read_text(encoding="utf-8")
        self.assertIn("include mk/test-selectors.generated.mk", test_mk_text)
        self.assertIn(
            "test-selectors-sync-check", _target_block(test_mk_text, ".PHONY")
        )
        self.assertIn(
            "_internal-test-selectors-sync-check", _target_block(test_mk_text, ".PHONY")
        )
        self.assertEqual(
            _recipe_lines(test_mk_text, "test-selectors-sync-check"),
            ["@$(MAKE) _internal-test-selectors-sync-check"],
        )
        self.assertEqual(
            _recipe_lines(test_mk_text, "_internal-test-selectors-sync-check"),
            [
                (
                    "$(PYTHON) -m ops.scripts.test.generate_test_mk_selectors "
                    '--vault "$(VAULT)" --check'
                )
            ],
        )

        marker_target_by_pack = {
            "runtime_hotspot_smoke": "runtime-hotspot-smoke",
            "report_contract_core": "test-report-contract-core",
            "release_sealing_core": "test-release-sealing-core",
        }
        for pack_id, target in marker_target_by_pack.items():
            with self.subTest(pack_id=pack_id, target=target):
                completed = subprocess.run(
                    ["make", "-n", target],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )

                self.assertEqual(
                    completed.returncode,
                    0,
                    msg=(
                        f"make -n {target} failed.\n"
                        f"stdout:\n{completed.stdout}\n"
                        f"stderr:\n{completed.stderr}"
                    ),
                )
                self.assertIn(
                    f'-m "{pack_mark_expr(registry, pack_id)}"', completed.stdout
                )

        completed = subprocess.run(
            ["make", "-n", "test-boundary-contract-smoke"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        self.assertEqual(
            completed.returncode,
            0,
            msg=(
                "make -n test-boundary-contract-smoke failed.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            ),
        )
        self.assertIn('-m "default_test_boundary"', completed.stdout)

        completed = subprocess.run(
            ["make", "-n", "test-subprocess"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        self.assertEqual(
            completed.returncode,
            0,
            msg=(
                "make -n test-subprocess failed.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            ),
        )
        self.assertIn('-m "subprocess"', completed.stdout)

        completed = subprocess.run(
            ["make", "-n", "fast-smoke"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        self.assertEqual(
            completed.returncode,
            0,
            msg=(
                "make -n fast-smoke failed.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            ),
        )
        self.assertIn('-m "fast_smoke"', completed.stdout)

    def test_registry_make_target_compatibility_entries_exist_in_makefile(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()

        for target in compatibility_names(registry, "make_target"):
            with self.subTest(target=target):
                _target_block(text, target)

    def test_pyproject_does_not_define_conflicting_pytest_marker_block(self) -> None:
        pyproject_text = Path("pyproject.toml").read_text(encoding="utf-8")

        self.assertNotIn("[tool.pytest.ini_options]", pyproject_text)
        self.assertNotIn('"finalization: local artifact self-checks', pyproject_text)

    def test_readme_and_pytest_ini_pin_supported_pytest_entrypoints(self) -> None:
        registry = _test_lane_registry()
        readme_text = README.read_text(encoding="utf-8")
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")
        conftest_text = CONFTEST.read_text(encoding="utf-8")
        pytest_ini_text = PYTEST_INI.read_text(encoding="utf-8")
        normalized_readme_text = _normalize_whitespace(readme_text)
        normalized_development_text = _normalize_whitespace(development_text)

        self.assertIn("docs/development.md", readme_text)
        self.assertIn("make help", readme_text)
        self.assertIn("make help", development_text)
        self.assertIn("make uv-lock-check", development_text)
        self.assertIn("UV_CANONICAL_INDEX_URL", development_text)
        self.assertIn("DEV_INSTALL_INDEX_URL", development_text)
        self.assertIn("uv.lock", development_text)
        self.assertIn(
            "For a full developer regression, use `make test-all`.",
            readme_text,
        )
        self.assertIn(
            "Bare `pytest` is not a supported entrypoint.",
            normalized_readme_text,
        )
        self.assertIn(
            "`make test-execution-summary-full-current-or-refresh`",
            development_text,
        )
        self.assertIn(
            "`test-execution-summary-full-refresh-no-converge`", development_text
        )
        self.assertIn("`make test-all`", development_text)
        self.assertIn(
            "focused `.venv/bin/python -m pytest tests/...`", development_text
        )
        self.assertIn("Bare `pytest` is unsupported.", normalized_development_text)
        self.assertIn("ops/test-lane-registry.json", development_text)
        self.assertIn("mk/test.mk", development_text)
        self.assertIn("Volatile counts and durations belong", development_text)
        self.assertNotRegex(
            development_text,
            r"\b(?:\d+\s+(?:tests|subtests|minutes)|20\d{2}-\d{2}-\d{2})\b",
        )
        self.assertIn("plain `pytest` is not a supported entrypoint", conftest_text)
        self.assertIn("selectorless `.venv/bin/python -m pytest`", conftest_text)
        self.assertIn("BARE_PYTEST_GUIDANCE", conftest_text)
        self.assertIn("SELECTORLESS_PYTEST_GUIDANCE", conftest_text)
        self.assertIn("LLMWIKI_MAKE_PYTEST_ENTRYPOINT", conftest_text)
        self.assertIn("make test-all", conftest_text)
        self.assertIn(
            "make test-execution-summary-full-current-or-refresh", conftest_text
        )
        self.assertNotRegex(pytest_ini_text, r"(?im)^pythonpath\s*=")
        for entrypoint in (
            "make fast-smoke",
            "make test",
            "make test-all",
            "make release-run-ready",
            "make release-post-commit-finalize",
            "make release-authority-settle",
        ):
            with self.subTest(entrypoint=entrypoint):
                self.assertIn(entrypoint, development_text)
        for alias in (
            "make test-report-contract",
            "make report-contracts",
            "make report-contracts-core",
            "make report-contracts-all",
            "make report-contracts-extended",
            "make test-release-sealing",
        ):
            with self.subTest(alias=alias):
                self.assertNotIn(f"- `{alias}`", development_text)
                self.assertNotIn(
                    alias, compatibility_names(registry, "documented_entrypoint")
                )

    def test_development_change_type_gates_split_make_ci_proofs(self) -> None:
        registry = _test_lane_registry()
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")
        make_or_ci_rule = _changed_path_minimum_rule(registry, "make_or_ci_contract")
        commands = make_or_ci_rule.get("commands")

        self.assertIsInstance(commands, list)
        assert isinstance(commands, list)
        self.assertIn("make workflow-dependency-planner-check", commands)
        changed_path_command = " + ".join(f"`{command}`" for command in commands)
        self.assertIn(
            f"| Make/CI changed-path minimum proof | {changed_path_command} |",
            development_text,
        )
        self.assertIn(
            "| Registry/Make/CI lane-contract proof | "
            "`make test-report-contract-core` |",
            development_text,
        )
        self.assertNotIn(
            "| Make or CI lane | `make static` | `make test-report-contract-core` |",
            development_text,
        )

    def test_python_command_allows_interpreter_flags(self) -> None:
        text = _makefile_text()

        self.assertNotIn('"$(PYTHON)"', text)
        self.assertIn("PUBLIC_PYTHON ?= $(if $(wildcard $(firstword $(PYTHON)))", text)
        self.assertIn(
            "$(PYTHON) -m ruff check $(RUFF_CACHE_FLAGS) $(RUFF_TARGETS)",
            _target_block(text, "ruff"),
        )

    def test_repo_virtualenv_is_canonical_make_default(self) -> None:
        text = _makefile_text()

        self.assertIn("VENV_DIR ?= .venv", text)
        self.assertIn("VENV_PYTHON ?= $(VENV_DIR)/bin/python", text)
        self.assertIn(
            "PYTHON ?= $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),python3)",
            text,
        )

    def test_schema_static_smoke_is_named_windows_ci_target(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()
        block = _target_block(text, "test-schema-static-smoke")

        self.assertIn("test-schema-static-smoke", _target_block(text, ".PHONY"))
        _assert_marker_expression_variable_matches_pack(
            self,
            registry,
            text,
            variable="SCHEMA_STATIC_SMOKE_TESTS",
            pack_id="schema_static_smoke",
            mark_expr_variable="PYTEST_SCHEMA_STATIC_SMOKE_MARK_EXPR",
        )
        self.assertIn(
            "$(PYTHON) -m pytest -q $(SCHEMA_STATIC_SMOKE_TESTS) $(PYTEST_SERIAL_FLAGS)",
            block,
        )

    def test_makefile_exposes_lane_targets_and_compatibility_aliases(self) -> None:
        text = _makefile_text()

        for target in (
            "test-fast",
            "ci-report-contract-tier",
            "test-report-contract-core",
            "test-report-contract-all",
            "test-release-sealing-core",
            "test-release-sealing-all",
            "test-subprocess",
            "release-source-package-smoke",
            "release-source-package-check",
            "release-run-ready",
            "release-run-ready-check",
            "release-sealed-run-ready",
            "release-sealed-run-ready-plan",
            "release-sealed-run-ready-check",
            "release-auto-promotion-goal-run-id-guard",
            "release-auto-promotion-preflight",
            "release-auto-promotion-preflight-check",
            "release-auto-promotion-safe-cleanup",
            "release-auto-promotion-safe-cleanup-cleanup-only",
            "release-auto-promotion-safe-cleanup-finalize",
            "release-auto-promotion-preseal",
            "release-auto-promotion-preseal-check",
            "release-auto-promotion-ready",
            "release-auto-promotion-ready-plan",
            "release-auto-promotion-operator-summary",
            "release-auto-promotion-ready-check",
            "release-authority-post-ready-finality-current-check",
            "release-authority-post-ready-finality-current-or-refresh",
            "release-authority-settle",
            "release-builder-full",
        ):
            with self.subTest(target=target):
                self.assertIn(target, _target_block(text, ".PHONY"))
        phony_block = _target_block(text, ".PHONY")
        for removed_alias in (
            "report-contracts",
            "report-contracts-core",
            "report-contracts-all",
            "report-contracts-extended",
            "test-report-contract",
            "report-contract-summary",
            "test-release-sealing",
            "test-execution-summary-aggregate",
        ):
            with self.subTest(removed_alias=removed_alias):
                self.assertNotRegex(
                    phony_block,
                    rf"(?<![A-Za-z0-9_.-]){re.escape(removed_alias)}(?![A-Za-z0-9_.-])",
                )

        self.assertIn(
            "PYTEST_REPORT_CONTRACT_MARK_EXPR ?= report_contract",
            text,
        )
        self.assertIn(
            "PYTEST_REPORT_CONTRACT_CORE_MARK_EXPR ?= report_contract_core",
            text,
        )
        self.assertIn(
            "PYTEST_RELEASE_CHECK_MARK_EXPR ?= not report_contract",
            text,
        )
        self.assertIn(
            "PYTEST_RUNTIME_HOTSPOT_SMOKE_MARK_EXPR ?= runtime_hotspot_smoke",
            text,
        )
        self.assertIn(
            "PYTEST_RELEASE_SEALING_CORE_MARK_EXPR ?= release_sealing_core",
            text,
        )
        self.assertIn("PYTEST_RELEASE_SEALING_MARK_EXPR ?= release_sealing", text)
        self.assertIn("PYTEST_SUBPROCESS_MARK_EXPR ?= subprocess", text)
        self.assertIn(
            "PYTEST_SCHEMA_STATIC_SMOKE_MARK_EXPR ?= schema_static_smoke", text
        )
        self.assertIn(
            "PYTEST_DEFAULT_TEST_BOUNDARY_MARK_EXPR ?= default_test_boundary",
            text,
        )
        self.assertIn(
            "PYTEST_RELEASE_CLOSEOUT_REGRESSION_MARK_EXPR ?= release_closeout_regression",
            text,
        )
        self.assertIn("RELEASE_SEALING_CORE_TESTS ?=", text)
        self.assertIn("RELEASE_SEALING_TESTS ?= $(RELEASE_SEALING_CORE_TESTS)", text)
        self.assertIn("SUBPROCESS_TESTS ?=", text)
        self.assertIn(
            '$(PYTHON) -m pytest -m "$(PYTEST_FAST_MARK_EXPR)" $(PYTEST_FLAGS)',
            _target_block(text, "test-fast"),
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(PYTEST_FLAGS)",
            _target_block(text, "unit-tests-all"),
        )
        self.assertIn(
            '$(PYTHON) -m pytest -m "$(PYTEST_RELEASE_CHECK_MARK_EXPR)" $(PYTEST_FLAGS)',
            _target_block(text, "unit-tests-release-check"),
        )
        self.assertIn("test: test-fast test-boundary-contract-smoke", text)
        self.assertIn("unit-tests: test-fast", text)
        self.assertIn(
            "release-builder-full: release-builder-full-lane-guard bootstrap-preflight static release-evidence-converge",
            text,
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(RELEASE_SEALING_TESTS) $(PYTEST_RELEASE_SEALING_FLAGS)",
            _target_block(text, "test-release-sealing-core"),
        )
        self.assertIn(
            '$(PYTHON) -m pytest -m "$(PYTEST_RELEASE_SEALING_MARK_EXPR)" $(PYTEST_RELEASE_SEALING_FLAGS)',
            _target_block(text, "test-release-sealing-all"),
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(SUBPROCESS_TESTS) $(PYTEST_SERIAL_FLAGS)",
            _target_block(text, "test-subprocess"),
        )
        self.assertIn("RELEASE_CLOSEOUT_REGRESSION_TESTS ?=", text)
        self.assertIn(
            "RELEASE_CLOSEOUT_REGRESSION_FRESHNESS_CHECK_OUT ?= tmp/release-closeout-regression-artifact-freshness-check.json",
            text,
        )
        self.assertIn(
            "RELEASE_CLOSEOUT_COST_EVIDENCE_CI_OUT ?= tmp/release-closeout-fixed-point-cost-trend-ci.json",
            text,
        )
        self.assertIn(
            "RELEASE_CLOSEOUT_FINALITY_VERIFY_CI_OUT ?= tmp/release-closeout-finality-verify-ci.json",
            text,
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(RELEASE_CLOSEOUT_REGRESSION_TESTS) $(PYTEST_SERIAL_FLAGS)",
            _target_block(text, "test-release-closeout-regression-pack"),
        )
        self.assertIn(
            "release-closeout-regression-dry-run",
            _target_block(text, ".PHONY"),
        )
        self.assertIn(
            "release-closeout-cost-evidence-ci-artifact",
            _target_block(text, ".PHONY"),
        )
        self.assertIn(
            "release-closeout-finality-verify-ci-artifact",
            _target_block(text, ".PHONY"),
        )
        self.assertIn(
            "release-closeout-post-check-finalizer-ci-artifact",
            _target_block(text, ".PHONY"),
        )
        regression_dry_run = _target_block(text, "release-closeout-regression-dry-run")
        self.assertIn("release-closeout-regression-dry-run: tmp-json-clean", text)
        self.assertIn(
            "$(MAKE) test-release-closeout-regression-pack", regression_dry_run
        )
        self.assertIn(
            '--out "$(RELEASE_CLOSEOUT_REGRESSION_FRESHNESS_CHECK_OUT)"',
            regression_dry_run,
        )
        self.assertIn("--fail-on-fail", regression_dry_run)
        self.assertNotIn("release_closeout_finality_attestation", regression_dry_run)
        finality_verify_artifact = _target_block(
            text, "release-closeout-finality-verify-ci-artifact"
        )
        self.assertIn(
            "ops.scripts.release_closeout_finality_attestation",
            finality_verify_artifact,
        )
        self.assertIn("--verify", finality_verify_artifact)
        self.assertIn(
            '--verify-out "$(RELEASE_CLOSEOUT_FINALITY_VERIFY_CI_OUT)"',
            finality_verify_artifact,
        )
        self.assertNotIn("--no-fail", finality_verify_artifact)
        cost_artifact = _target_block(
            text, "release-closeout-cost-evidence-ci-artifact"
        )
        self.assertIn(
            "ops.scripts.release_closeout_fixed_point_cost_trend", cost_artifact
        )
        self.assertIn('--out "$(RELEASE_CLOSEOUT_COST_EVIDENCE_CI_OUT)"', cost_artifact)
        self.assertIn("--no-fail", cost_artifact)
        post_check_artifact = _target_block(
            text, "release-closeout-post-check-finalizer-ci-artifact"
        )
        self.assertIn("--recommended-targets-out", post_check_artifact)
        self.assertIn(
            '"$(RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_RECOMMENDED_TARGETS_OUT)"',
            post_check_artifact,
        )
        self.assertIn("--no-fail", post_check_artifact)

    def test_developer_full_suite_runs_full_pytest_without_marker_filter(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()
        release_check_expr = pack_mark_expr(registry, "release_check_unit_complement")

        _assert_assignment_exists(
            self,
            text,
            "PYTEST_RELEASE_CHECK_MARK_EXPR",
            release_check_expr,
        )
        self.assertEqual(release_check_expr, "not report_contract")
        for target, flags in (
            ("unit-tests-all", "$(PYTEST_FLAGS)"),
            ("unit-tests-all-serial", "$(PYTEST_SERIAL_FLAGS)"),
            ("unit-tests-all-parallel", "$(PYTEST_PARALLEL_FLAGS)"),
        ):
            with self.subTest(target=target):
                self.assertIn(
                    f"$(PYTHON) -m pytest {flags}",
                    _target_block(text, target),
                )
        self.assertIn(
            '$(PYTHON) -m pytest -m "$(PYTEST_RELEASE_CHECK_MARK_EXPR)" $(PYTEST_FLAGS)',
            _target_block(text, "unit-tests-release-check"),
        )

    def test_source_package_targets_pin_clean_extract_smoke_lane(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()

        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_SMOKE_ROOT",
            "build/source-package-smoke",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_SMOKE_OUT",
            "$(SOURCE_PACKAGE_SMOKE_ROOT)/source-package-smoke.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_SMOKE_EXTRACT_PARENT",
            "$(SOURCE_PACKAGE_SMOKE_ROOT)/extract",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_SMOKE_PYTHON",
            "$(PUBLIC_PYTHON)",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_CLEAN_EXTRACT_OUT",
            "ops/reports/source-package-clean-extract.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_CLEAN_EXTRACT_ROOT",
            "tmp/source-package-clean-extract",
        )
        self.assertIn("release-package-current-check", _target_block(text, ".PHONY"))
        self.assertIn(
            "release-package-current-or-refresh", _target_block(text, ".PHONY")
        )
        self.assertIn(
            "release-source-package-smoke-current-check", _target_block(text, ".PHONY")
        )
        self.assertIn(
            "release-source-package-smoke-current-or-refresh",
            _target_block(text, ".PHONY"),
        )
        self.assertIn(
            "release-source-package-clean-extract", _target_block(text, ".PHONY")
        )
        self.assertIn(
            "release-source-package-clean-extract-current-check",
            _target_block(text, ".PHONY"),
        )
        self.assertIn(
            "release-source-package-clean-extract-current-or-refresh",
            _target_block(text, ".PHONY"),
        )
        self.assertIn(
            "--reuse-if-current", _target_block(text, "release-package-current-check")
        )
        self.assertIn(
            "$(MAKE) release-package-current-check",
            _target_block(text, "release-package-current-or-refresh"),
        )
        self.assertIn(
            '$(MAKE) release-distribution-zip RELEASE_DISTRIBUTION_ZIP_OUT="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
            _target_block(text, "release-package-current-or-refresh"),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "release-source-package-smoke-current-check",
            (
                "ops.scripts.source_package_smoke",
                '--source-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
                '--extract-parent "$(SOURCE_PACKAGE_SMOKE_EXTRACT_PARENT)"',
                '--source-python "$(SOURCE_PACKAGE_SMOKE_PYTHON)"',
                '--out "$(SOURCE_PACKAGE_SMOKE_OUT)"',
                "--reuse-if-current",
                "--reuse-only",
            ),
        )
        self.assertIn(
            "$(MAKE) release-source-package-smoke-current-check",
            _target_block(text, "release-source-package-smoke-current-or-refresh"),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "release-source-package-clean-extract-current-check",
            (
                "ops.scripts.source_package_clean_extract",
                '--source-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
                '--extract-parent "$(SOURCE_PACKAGE_CLEAN_EXTRACT_EXTRACT_PARENT)"',
                '--source-python "$(SOURCE_PACKAGE_SMOKE_PYTHON)"',
                '--test-summary-out "$(SOURCE_PACKAGE_CLEAN_EXTRACT_TEST_SUMMARY_OUT)"',
                '--pytest-flags="$(SOURCE_PACKAGE_CLEAN_EXTRACT_PYTEST_FLAGS)"',
                '--zip-smoke-report "$(RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT)"',
                '--out "$(SOURCE_PACKAGE_CLEAN_EXTRACT_OUT)"',
                "--reuse-if-current",
                "--reuse-only",
            ),
        )
        self.assertIn(
            "$(MAKE) release-source-package-clean-extract-current-check",
            _target_block(
                text, "release-source-package-clean-extract-current-or-refresh"
            ),
        )
        self.assertEqual(
            pack_selectors(registry, "source_package"),
            ("release-source-package-smoke",),
        )
        self.assertEqual(
            pack_summary_suite(registry, "source_package")["summary_target"],
            "build/source-package-smoke/source-package-smoke.json",
        )
        self.assertIn(
            "$(MAKE) release-package-current-or-refresh",
            _target_block(text, "release-source-package-check"),
        )
        self.assertIn(
            "$(MAKE) release-source-package-smoke-current-or-refresh",
            _target_block(text, "release-source-package-check"),
        )
        self.assertIn(
            "$(MAKE) release-source-package-clean-extract-current-or-refresh",
            _target_block(text, "release-source-package-check"),
        )

    def test_readme_ci_tier_summary_matches_current_workflow_shape(self) -> None:
        registry = _test_lane_registry()
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")

        self.assertIn(
            "CI splits registry-backed lanes into parallel jobs", development_text
        )
        self.assertIn(".github/workflows/ci.yml", development_text)
        self.assertIn("ops/test-lane-registry.json", development_text)
        self.assertIn("make help", development_text)
        for entrypoint in (
            "make test-fast",
            "make test-all",
            "make public-check",
            "make release-run-ready",
        ):
            with self.subTest(entrypoint=entrypoint):
                self.assertIn(entrypoint, development_text)
        for alias in (
            "make test-report-contract",
            "make report-contracts",
            "make report-contracts-core",
            "make report-contracts-all",
            "make report-contracts-extended",
            "make test-release-sealing",
        ):
            with self.subTest(alias=alias):
                self.assertNotIn(f"- `{alias}`", development_text)
                self.assertNotIn(
                    alias, compatibility_names(registry, "documented_entrypoint")
                )

    def test_registry_documents_authority_boundary_for_lane_contract(self) -> None:
        registry = _test_lane_registry()
        release_workflow_rule = _changed_path_minimum_rule(
            registry,
            "release_workflow_static_contract",
        )

        self.assertEqual(
            documentation_authority(registry),
            (
                "README.md",
                "docs/development.md",
                "ops/README.md",
                ".github/workflows/ci.yml",
            ),
        )
        self.assertEqual(
            documentation_out_of_scope(registry),
            ("ARCHITECTURE.md", ".github/workflows/release.yml"),
        )
        self.assertEqual(
            release_workflow_rule["path_patterns"],
            [".github/workflows/release.yml"],
        )
        self.assertIn(
            "tests/test_release_workflow_static.py",
            " ".join(str(command) for command in release_workflow_rule["commands"]),
        )
        self.assertNotIn(
            "tests/test_release_workflow_static.py",
            _collect_marker_paths(pack_mark_expr(registry, "report_contract_core")),
        )

    def test_architecture_public_surface_includes_github_workflows(self) -> None:
        architecture_text = Path("ARCHITECTURE.md").read_text(encoding="utf-8")

        self.assertIn("- `.github/`", architecture_text)
        self.assertIn("- `docs/`", architecture_text)

    def test_report_contract_targets_collect_schema_and_generated_artifact_checks(
        self,
    ) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()
        core_block = _target_block(text, "test-report-contract-core")
        all_block = _target_block(text, "test-report-contract-all")

        self.assertIn("test-report-contract-core", _target_block(text, ".PHONY"))
        self.assertIn("test-report-contract-all", _target_block(text, ".PHONY"))
        self.assertIn("ci-report-contract-tier", _target_block(text, ".PHONY"))
        ci_block = _target_block(text, "ci-report-contract-tier")
        self.assertIn("workflow_dispatch:*", ci_block)
        self.assertNotIn("push:refs/heads/main", ci_block)
        self.assertIn("push:refs/heads/release/*", ci_block)
        self.assertIn("push:refs/tags/*", ci_block)
        self.assertIn("$(MAKE) test-report-contract-all", ci_block)
        self.assertIn("$(MAKE) test-report-contract-core", ci_block)
        self.assertIn(
            "$(MAKE) external-report-reference-manifest-release-check", ci_block
        )
        self.assertIn("REPORT_CONTRACT_CORE_TESTS ?=", text)
        self.assertNotIn("REPORT_CONTRACT_EXTENDED_TESTS", text)
        self.assertIn("REPORT_CONTRACT_TESTS ?=", text)
        self.assertIn("REPORT_CONTRACT_TESTS ?= $(REPORT_CONTRACT_CORE_TESTS)", text)
        _assert_marker_expression_variable_matches_pack(
            self,
            registry,
            text,
            variable="REPORT_CONTRACT_CORE_TESTS",
            pack_id="report_contract_core",
            mark_expr_variable="PYTEST_REPORT_CONTRACT_CORE_MARK_EXPR",
        )
        _assert_marker_expression_variable_matches_pack(
            self,
            registry,
            text,
            variable="REPORT_CONTRACT_ALL_TESTS",
            pack_id="report_contract_all",
            mark_expr_variable="PYTEST_REPORT_CONTRACT_MARK_EXPR",
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_REPORT_CONTRACT_FLAGS)",
            core_block,
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(REPORT_CONTRACT_ALL_TESTS) $(PYTEST_REPORT_CONTRACT_FLAGS)",
            all_block,
        )

    def test_report_contract_summary_uses_current_report_contract_lane(
        self,
    ) -> None:
        text = _makefile_text()
        core_block = _target_block(text, "test-report-contract-core")
        all_block = _target_block(text, "test-report-contract-all")

        self.assertIn("test-report-contract-core", _target_block(text, ".PHONY"))
        self.assertIn("test-report-contract-all", _target_block(text, ".PHONY"))
        phony_block = _target_block(text, ".PHONY")
        self.assertNotRegex(
            phony_block,
            r"(?<![A-Za-z0-9_.-])test-report-contract(?![A-Za-z0-9_.-])",
        )
        self.assertNotRegex(
            phony_block,
            r"(?<![A-Za-z0-9_.-])report-contract-summary(?![A-Za-z0-9_.-])",
        )
        self.assertIn(
            "REPORT_CONTRACT_SUMMARY_DESELECT_POLICY ?= ops/policies/report-contract-deselections.json",
            text,
        )
        self.assertIn("REPORT_CONTRACT_SUMMARY_TESTS ?= $(REPORT_CONTRACT_TESTS)", text)
        self.assertNotIn("--deselect=tests/test_", core_block)
        self.assertNotIn("--deselect=tests/test_", all_block)
        self.assertIn(
            "$(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_REPORT_CONTRACT_FLAGS)",
            core_block,
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(REPORT_CONTRACT_ALL_TESTS) $(PYTEST_REPORT_CONTRACT_FLAGS)",
            all_block,
        )
        self.assertNotIn("test-report-contract is a compatibility alias", text)
        self.assertNotIn("report-contract-summary:", text)

    def test_dev_install_creates_editable_environment(self) -> None:
        text = _makefile_text()

        block = _target_block(text, "dev-install")
        self.assertIn(
            "DEV_LOCKED_REQUIREMENTS ?= tmp/locked-requirements.dev.txt", text
        )
        self.assertIn("DEV_INSTALL_INDEX_URL ?= $(UV_CANONICAL_INDEX_URL)", text)
        self.assertIn(
            "UV_EXPORT_DEV_REQUIREMENTS_FLAGS ?= --frozen --extra dev --format requirements-txt --no-hashes --no-emit-project",
            text,
        )
        self.assertIn(
            'UV_DEFAULT_INDEX="$(DEV_INSTALL_INDEX_URL)" $(UV) export $(UV_EXPORT_DEV_REQUIREMENTS_FLAGS) -o "$(DEV_LOCKED_REQUIREMENTS)"',
            block,
        )
        self.assertIn(
            'UV_DEFAULT_INDEX="$(DEV_INSTALL_INDEX_URL)" $(UV) pip install --python "$(VENV_PYTHON)" -r "$(DEV_LOCKED_REQUIREMENTS)"',
            block,
        )
        self.assertIn(
            'UV_DEFAULT_INDEX="$(DEV_INSTALL_INDEX_URL)" $(UV) pip install --python "$(VENV_PYTHON)" --no-deps -e .',
            block,
        )
        self.assertNotIn('UV_DEFAULT_INDEX="$(UV_CANONICAL_INDEX_URL)"', block)
        self.assertIn('"$(VENV_PYTHON)" -m pip install -e ".[dev]"', block)

    def test_legacy_root_requirements_files_are_retired(self) -> None:
        pyproject = tomllib.loads(
            (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )

        self.assertIn("dev", pyproject["project"]["optional-dependencies"])
        self.assertFalse((REPO_ROOT / "requirements.txt").exists())
        self.assertFalse((REPO_ROOT / "requirements-dev.txt").exists())

    def test_bootstrap_preflight_target_writes_canonical_report_with_project_python(
        self,
    ) -> None:
        text = _makefile_text()

        self.assertIn("bootstrap-preflight", _target_block(text, ".PHONY"))
        self.assertIn(
            "BOOTSTRAP_PREFLIGHT_OUT ?= ops/reports/bootstrap-preflight-report.json",
            text,
        )
        self.assertIn("BOOTSTRAP_PREFLIGHT_ENVIRONMENT_CLASS ?= developer", text)
        self.assertIn(
            '$(PYTHON) -m ops.scripts.bootstrap_preflight --vault "$(VAULT)" --dev --environment-class "$(BOOTSTRAP_PREFLIGHT_ENVIRONMENT_CLASS)" --out "$(BOOTSTRAP_PREFLIGHT_OUT)"',
            _target_block(text, "bootstrap-preflight"),
        )

    def test_refresh_generated_splits_core_outputs_from_observability_outputs(
        self,
    ) -> None:
        text = _makefile_text()

        _assert_refresh_generated_split_targets(self, text)
        _assert_observability_output_variables(self, text)
        _assert_script_surface_and_inventory_targets(self, text)
        _assert_workflow_dependency_planner_target(self, text)
        _assert_release_workflow_order_guard_target(self, text)
        _assert_function_budget_and_outcome_targets(self, text)
        _assert_external_report_action_matrix_target(self, text)

    def test_mechanism_run_linux_tmp_target_pins_native_temp_environment(self) -> None:
        text = _makefile_text()
        block = _target_block(text, "run-mechanism-experiment-linux-tmp")

        self.assertIn("MECHANISM_RUN_ARGS ?=", text)
        self.assertIn(
            "run-mechanism-experiment-linux-tmp", _target_block(text, ".PHONY")
        )
        self.assertIn(
            'TMPDIR=/tmp TEMP=/tmp TMP=/tmp $(PYTHON) -m ops.scripts.run_mechanism_experiment --vault "$(VAULT)" $(MECHANISM_RUN_ARGS)',
            block,
        )

    def test_ruff_strict_preview_target_uses_full_scope_targets(self) -> None:
        text = _makefile_text()

        self.assertIn(
            "RUFF_STRICT_PREVIEW_RULES ?= PTH201",
            text,
        )
        self.assertIn(
            "RUFF_STRICT_PREVIEW_TARGETS ?= $(STRICT_PREVIEW_AUDIT_TARGETS)", text
        )
        self.assertIn(
            '$(PYTHON) tools/ruff_strict_preview.py --vault "$(VAULT)" --targets "$(RUFF_STRICT_PREVIEW_TARGETS)" --select "$(RUFF_STRICT_PREVIEW_RULES)" --cache-dir "$(RUFF_CACHE_DIR)" --exit-zero',
            _target_block(text, "ruff-strict-preview"),
        )

    def test_strict_preview_audit_target_expands_all_public_runtime_targets(
        self,
    ) -> None:
        text = _makefile_text()

        self.assertIn("STRICT_PREVIEW_AUDIT_TARGETS ?= ops/scripts tests tools", text)
        self.assertIn("STRICT_PREVIEW_AUDIT_OUT ?= tmp/strict-preview-audit.json", text)
        block = _target_block(text, "strict-preview-audit")
        self.assertIn("tools/strict_preview_audit.py", block)
        self.assertIn('--targets "$(STRICT_PREVIEW_AUDIT_TARGETS)"', block)
        self.assertIn('--ruff-select "$(RUFF_STRICT_PREVIEW_RULES)"', block)
        self.assertIn('--ruff-cache-dir "$(RUFF_CACHE_DIR)"', block)
        self.assertIn(
            '--mypy-flags "$(MYPY_CACHE_FLAGS) $(MYPY_STRICT_PREVIEW_FLAGS)"', block
        )
        self.assertNotIn("--fail-on-attention", block)

    def test_mypy_strict_preview_target_uses_full_scope_targets(self) -> None:
        text = _makefile_text()

        self.assertIn(
            "MYPY_STRICT_PREVIEW_FLAGS ?= --check-untyped-defs --disallow-untyped-defs --disallow-incomplete-defs",
            text,
        )
        self.assertIn(
            "MYPY_STRICT_PREVIEW_TARGETS ?= $(STRICT_PREVIEW_AUDIT_TARGETS)",
            text,
        )
        self.assertIn(
            "$(PYTHON) -m mypy --config-file pyproject.toml $(MYPY_CACHE_FLAGS) $(MYPY_STRICT_PREVIEW_FLAGS) $(MYPY_STRICT_PREVIEW_TARGETS)",
            _target_block(text, "mypy-strict-preview"),
        )

    def test_raw_intake_and_review_classification_targets_exist(self) -> None:
        text = _makefile_text()

        self.assertIn(
            "RAW_INTAKE_ABSORPTION_MATRIX ?= runs/run-20260422-raw-intake-registration-and-promotion/absorption/raw-intake-absorption-matrix-2026-04-22.json",
            text,
        )
        self.assertIn(
            "RAW_INTAKE_ROUTE_PROPOSAL_OUT ?= tmp/raw-intake-route-proposal-report.json",
            text,
        )
        self.assertIn(
            "RAW_INTAKE_SOURCE_QUALITY_OUT ?= tmp/raw-intake-source-quality-report.json",
            text,
        )
        self.assertIn(
            "RAW_INTAKE_SEED_SOURCE_HINTS_OUT ?= tmp/raw-intake-seed-source-hints-report.json",
            text,
        )
        self.assertIn(
            "RAW_INTAKE_ABSORPTION_CLOSEOUT_OUT ?= tmp/raw-intake-absorption-closeout-report.json",
            text,
        )
        self.assertIn(
            "WIKI_LINT_REVIEW_CLASSIFICATION_OUT ?= tmp/wiki-lint-review-classification.json",
            text,
        )
        self.assertIn("raw-intake-route-proposal", _target_block(text, ".PHONY"))
        self.assertIn("raw-intake-source-quality", _target_block(text, ".PHONY"))
        self.assertIn("raw-intake-seed-source-hints", _target_block(text, ".PHONY"))
        self.assertIn(
            "raw-intake-seed-source-hints-write", _target_block(text, ".PHONY")
        )
        self.assertIn("raw-intake-absorption-closeout", _target_block(text, ".PHONY"))
        self.assertIn("wiki-lint-review-classification", _target_block(text, ".PHONY"))
        self.assertIn(
            "ops.scripts.raw_intake_route_proposal",
            _target_block(text, "raw-intake-route-proposal"),
        )
        self.assertIn(
            "ops.scripts.raw_intake_source_quality",
            _target_block(text, "raw-intake-source-quality"),
        )
        self.assertIn(
            "ops.scripts.registry.raw_intake_seed_source_hints",
            _target_block(text, "raw-intake-seed-source-hints"),
        )
        self.assertIn(
            "--write",
            _target_block(text, "raw-intake-seed-source-hints-write"),
        )
        self.assertIn(
            "--mode absorption_closeout --fail-on-fail",
            _target_block(text, "raw-intake-absorption-closeout"),
        )
        self.assertIn(
            "ops.scripts.wiki_lint_review_classification",
            _target_block(text, "wiki-lint-review-classification"),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
